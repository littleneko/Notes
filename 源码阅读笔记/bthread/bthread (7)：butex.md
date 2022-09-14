前面介绍过 bthread 的两个特性：work stealing 和 butex，代码中对 butex 的解释是：a ==futex-like== 32-bit ==primitive== for synchronizing bthreads/pthreads，和 pthread mutex 类似，bthread 也基于 butex 实现了 bthread mutex。


> **关于 Futex**：
> In [computing](https://en.wikipedia.org/wiki/Computing), a **futex** (short for "fast userspace [mutex](https://en.wikipedia.org/wiki/Mutual_exclusion)") is a [kernel](https://en.wikipedia.org/wiki/Kernel_(operating_system)) [system call](https://en.wikipedia.org/wiki/System_call) that [programmers](https://en.wikipedia.org/wiki/Programmer) can use to implement basic [locking](https://en.wikipedia.org/wiki/Lock_(computer)), or as a building block for higher-level locking abstractions such as [semaphores](https://en.wikipedia.org/wiki/Semaphore_(programming)) and [POSIX](https://en.wikipedia.org/wiki/POSIX) mutexes or [condition variables](https://en.wikipedia.org/wiki/Condition_variable).
>
> A futex consists of a [kernelspace](https://en.wikipedia.org/wiki/Kernel_(computing)) _wait queue_ that is attached to an [atomic](https://en.wikipedia.org/wiki/Atomic_operations) [integer](https://en.wikipedia.org/wiki/Integer) in [userspace](https://en.wikipedia.org/wiki/Userspace). Multiple [processes](https://en.wikipedia.org/wiki/Process_(computing)) or [threads](https://en.wikipedia.org/wiki/Thread_(computer_science)) ==operate on the integer entirely in userspace== (using [atomic operations](https://en.wikipedia.org/wiki/Atomic_operation) to avoid interfering with one another), and only resort to relatively expensive [system calls](https://en.wikipedia.org/wiki/System_call) to request operations on the wait queue (for example to wake up waiting processes, or to put the current process on the wait queue). ==A properly programmed futex-based lock will not use system calls except when the lock is contended==; since most operations do not require arbitration between processes, this will not happen in most cases.

# butex
## Overview
```cpp
// Provides futex-like semantics which is sequenced wait and wake operations
// and guaranteed visibilities.
//
// If wait is sequenced before wake:
//    [thread1]             [thread2]
//    wait()                value = new_value
//                          wake()
// wait() sees unmatched value(fail to wait), or wake() sees the waiter.
//
// If wait is sequenced after wake:
//    [thread1]             [thread2]
//                          value = new_value
//                          wake()
//    wait()
// wake() must provide some sort of memory fence to prevent assignment
// of value to be reordered after it. Thus the value is visible to wait()
// as well.
```
和 futex 类似，butex 也提供了 wait 和 wake 接口，并且其语义也和 futex 类似。
## 数据结构定义
### Butex
```cpp
struct BAIDU_CACHELINE_ALIGNMENT Butex {
    Butex() {}
    ~Butex() {}

    butil::atomic<int> value;
    ButexWaiterList waiters;
    internal::FastPthreadMutex waiter_lock;
};
```
* `Butex::value` 是一个 int 原子变量，`butex_create()` 返回的实际上是 value，而不是 Butex 对象，在使用中通过 `container_of()` 宏拿到 Butex 对象；

* `Butex::waiters` 是一个链表，保存了等待在该 Butex 上的所有 bthread；
* `waiter_lock` TODO

---

`container_of()` 定义在 _butil/macros.h_ 中，实现了根据 Butex 对象的 value 指针得到 Butex 对象指针：
```cpp
// ptr:     the pointer to the member.
// type:    the type of the container struct this is embedded in.
// member:  the name of the member within the struct.
#ifndef container_of
# define container_of(ptr, type, member) ({                             \
            const BAIDU_TYPEOF( ((type *)0)->member ) *__mptr = (ptr);  \
            (type *)( (char *)__mptr - offsetof(type,member) );})
#endif
```
其中 `offsetof()` 宏用于求出一个 field 在 class 中对齐后的偏移字节（The macro offsetof expands to an integral constant expression of type std::size_t, the value of which is the offset, in bytes, from the beginning of an object of specified type to its specified subobject, including padding if any. ref: [offsetof](https://en.cppreference.com/w/cpp/types/offsetof)）。


因此 `offsetof(type,member)` 得到了 ptr 在 type 中的偏移， `(char *)__mptr - offsetof(type,member)` 即 "_ptr 指针 - ptr 在 type 中的偏移_"，得到的就是 ptr 在 type 对象中的首地址，然后强转成 type* 类型。


我们来看看其用法，在 wait 和 wake 中都会使用 `create_butex()` 返回的 value 指针得到 Butex 对象：
```cpp
Butex* b = container_of(static_cast<butil::atomic<int>*>(arg), Butex, value);
```
上面代码完全展开后如下：
```cpp
({
    const decltype(((Butex *) 0)->value) *__mptr = (static_cast<butil::atomic<int> *>(arg));
    (Butex * )((char *) __mptr - ((size_t) (&(((Butex *) 0)->value))));
})
```
> **Tips**:
> 通过展开后的宏发现 `offsetof()` 实际上是 `(size_t) (&(((Butex *) 0)->value))`，这里通过把 0 强转成 Butex\*，然后拿到的 value 的地址实际上就是其 offset

### ButexWaiter
```cpp
struct ButexWaiter : public butil::LinkNode<ButexWaiter> {
    // tids of pthreads are 0
    bthread_t tid;

    // Erasing node from middle of LinkedList is thread-unsafe, we need
    // to hold its container's lock.
    butil::atomic<Butex*> container;
};

// non_pthread_task allocates this structure on stack and queue it in
// Butex::waiters.
struct ButexBthreadWaiter : public ButexWaiter {
    TaskMeta* task_meta;
    TimerThread::TaskId sleep_id;
    WaiterState waiter_state;
    int expected_value;
    Butex* initial_butex;
    TaskControl* control;
};

// pthread_task or main_task allocates this structure on stack and queue it
// in Butex::waiters.
struct ButexPthreadWaiter : public ButexWaiter {
    butil::atomic<int> sig;
};

typedef butil::LinkedList<ButexWaiter> ButexWaiterList;
```
ButexWaiter 继承自 butil::LinkNode\<T\>，分为 bthread 和 pthread 两种实现，主要是保存了 bthread/pthread 的状态。


## 初始化和销毁
```cpp
// Create a butex which is a futex-like 32-bit primitive for synchronizing
// bthreads/pthreads.
// Returns a pointer to 32-bit data, NULL on failure.
// NOTE: all butexes are private(not inter-process).
void* butex_create();

// Check width of user type before casting.
template <typename T> T* butex_create_checked() {
    BAIDU_CASSERT(sizeof(T) == sizeof(int), sizeof_T_must_equal_int);
    return static_cast<T*>(butex_create());
}

// Destroy the butex.
void butex_destroy(void* butex);
```
## Wait
```cpp
// Atomically wait on |butex| if *butex equals |expected_value|, until the
// butex is woken up by butex_wake*, or CLOCK_REALTIME reached |abstime| if
// abstime is not NULL.
// About |abstime|:
//   Different from FUTEX_WAIT, butex_wait uses absolute time.
// Returns 0 on success, -1 otherwise and errno is set.
int butex_wait(void* butex, int expected_value, const timespec* abstime);
```
butex_wait 的逻辑和 FUTEX_WAIT 一样，如果 butex 的值和 expected_value 相等，就会一直阻塞在该 butext 上，直到被 wake 或者 timeout，与 FUTEX_WAIT 不同的是，超时时间是一个绝对时间。

主要代码流程下面分解来讲：

首先根据 butex 指针（实际上是 Butex::value）拿到 Butex 对象，这里不再赘述。

```cpp
    if (b->value.load(butil::memory_order_relaxed) != expected_value) {
        errno = EWOULDBLOCK;
        // Sometimes we may take actions immediately after unmatched butex,
        // this fence makes sure that we see changes before changing butex.
        butil::atomic_thread_fence(butil::memory_order_acquire);
        return -1;
    }
```
wait 的语义是如果 expected_value 和 butex.value 相等就阻塞，这里首先判断是否满足这个条件，不满足就直接返回。
注意这里加了一个 `atomic_thread_fence` 内存屏障，目的是 // todo。


```cpp
    TaskGroup* g = tls_task_group;
    if (NULL == g || g->is_current_pthread_task()) {
        return butex_wait_from_pthread(g, b, expected_value, abstime);
    }
```
如果当前 TaskGroup 在 pthread 上，就调用 pthread 相关的 wait 函数 `butex_wait_from_pthread()`，其实现后面单独讲。


```cpp
    ButexBthreadWaiter bbw;
    // tid is 0 iff the thread is non-bthread
    bbw.tid = g->current_tid();
    bbw.container.store(NULL, butil::memory_order_relaxed);
    bbw.task_meta = g->current_task();
    bbw.sleep_id = 0;
    bbw.waiter_state = WAITER_STATE_READY;
    bbw.expected_value = expected_value;
    bbw.initial_butex = b;
    bbw.control = g->control();
```
接着构造 ButexBthreadWaiter 对象并初始化相关的信息，注意 container 的初始值是 NULL，后面会用到。


```cpp
    if (abstime != NULL) {
        // Schedule timer before queueing. If the timer is triggered before
        // queueing, cancel queueing. This is a kind of optimistic locking.
        if (butil::timespec_to_microseconds(*abstime) <
            (butil::gettimeofday_us() + MIN_SLEEP_US)) {
            // Already timed out.
            errno = ETIMEDOUT;
            return -1;
        }
        bbw.sleep_id = get_global_timer_thread()->schedule(
            erase_from_butex_and_wakeup, &bbw, *abstime);
        if (!bbw.sleep_id) {  // TimerThread stopped.
            errno = ESTOP;
            return -1;
        }
    }
```
如果设置了超时时间，就设置一个定时器。


超时回调函数 `erase_from_butex_and_wakeup()` 实现
```cpp
// Callable from multiple threads, at most one thread may wake up the waiter.
static void erase_from_butex_and_wakeup(void* arg) {
    erase_from_butex(static_cast<ButexWaiter*>(arg), true, WAITER_STATE_TIMEDOUT);
}

inline bool erase_from_butex(ButexWaiter* bw, bool wakeup, WaiterState state) {
    // `bw' is guaranteed to be valid inside this function because waiter
    // will wait until this function being cancelled or finished.
    // NOTE: This function must be no-op when bw->container is NULL.
    bool erased = false;
    Butex* b;
    int saved_errno = errno;
    while ((b = bw->container.load(butil::memory_order_acquire))) {
        // b can be NULL when the waiter is scheduled but queued.
        BAIDU_SCOPED_LOCK(b->waiter_lock);
        if (b == bw->container.load(butil::memory_order_relaxed)) {
            bw->RemoveFromList();
            bw->container.store(NULL, butil::memory_order_relaxed);
            if (bw->tid) {
                static_cast<ButexBthreadWaiter*>(bw)->waiter_state = state;
            }
            erased = true;
            break;
        }
    }
    if (erased && wakeup) {
        if (bw->tid) {
            ButexBthreadWaiter* bbw = static_cast<ButexBthreadWaiter*>(bw);
            get_task_group(bbw->control)->ready_to_run_general(bw->tid);
        } else {
            ButexPthreadWaiter* pw = static_cast<ButexPthreadWaiter*>(bw);
            wakeup_pthread(pw);
        }
    }
    errno = saved_errno;
    return erased;
}
```
如果 waiter 的 container 就是 NULL，该函数就什么都不会做。containter 为 NULL 的情况：

1. container 的初始值是 NULL，然后在 `wait_for_butex()` 中把当前 bthread 加到等待队列中后才会赋值，所以如果超时的时候还没有执行 `wait_for_butex()`，container 也是 NULL。
1. wake_up 时也会把 containter 置为 NULL，如果在超时前该 bthread 已经被唤醒了，container 也是 NULL。



正常情况下的逻辑：

1. 超时后需要把当前 bthread 从 butex 的等待队列中移除（`bw->RemoveFromList()`），并且把 bw->container 置为 NULL。
1. 对于 bthread（`bw->tid != 0`），把 waiter_state 置为 `WAITER_STATE_TIMEDOUT`，表示超时了。
1. 对于 bthread，调用 `TaskGroup::ready_to_run_general(bw->tid)` 把当前 bthread 加到队列中等待执行。



```cpp
    // release fence matches with acquire fence in interrupt_and_consume_waiters
    // in task_group.cpp to guarantee visibility of `interrupted'.
    bbw.task_meta->current_waiter.store(&bbw, butil::memory_order_release);
    g->set_remained(wait_for_butex, &bbw);
    TaskGroup::sched(&g);
```
这里调用 `TaskGroup::set_remained()` 是为了在当前 bthread 切到下一个 bthread 之前先执行回调函数 `wait_for_butex()`，然后调用 `TaskGroup::sched()` 切换出当前的 bthread。



---

bthread 中 remained 函数调用的位置：

1. 在 TaskGroup 中，任务入口函数 `TaskGroup::task_runner()` 一开始就会调用 remained 的回调函数
```cpp
void TaskGroup::task_runner(intptr_t skip_remained) {
    // NOTE: tls_task_group is volatile since tasks are moved around
    //       different groups.
    TaskGroup* g = tls_task_group;

    if (!skip_remained) {
        while (g->_last_context_remained) {
            RemainedFn fn = g->_last_context_remained;
            g->_last_context_remained = NULL;
            fn(g->_last_context_remained_arg);
            g = tls_task_group;
        }
    }
    // ... ...
}
```

2. sched_to 执行完 bthread 返回的时候
```cpp
void TaskGroup::sched_to(TaskGroup** pg, TaskMeta* next_meta) {
    // jump_stack 进行栈切换
    // ... ...
    // 执行完 bthread 返回
    
    while (g->_last_context_remained) {
        RemainedFn fn = g->_last_context_remained;
        g->_last_context_remained = NULL;
        fn(g->_last_context_remained_arg);
        g = tls_task_group;
    }
}
```

---



我们接着来看看 `wait_for_butex()` 的实现：
```cpp
static void wait_for_butex(void* arg) {
    ButexBthreadWaiter* const bw = static_cast<ButexBthreadWaiter*>(arg);
    Butex* const b = bw->initial_butex;
    // 1: waiter with timeout should have waiter_state == WAITER_STATE_READY
    //    before they're queued, otherwise the waiter is already timedout
    //    and removed by TimerThread, in which case we should stop queueing.
    //
    // Visibility of waiter_state:
    //    [bthread]                         [TimerThread]
    //    waiter_state = TIMED
    //    tt_lock { add task }
    //                                      tt_lock { get task }
    //                                      waiter_lock { waiter_state=TIMEDOUT }
    //    waiter_lock { use waiter_state }
    // tt_lock represents TimerThread::_mutex. Visibility of waiter_state is
    // sequenced by two locks, both threads are guaranteed to see the correct
    // value.
    {
        BAIDU_SCOPED_LOCK(b->waiter_lock);
        if (b->value.load(butil::memory_order_relaxed) != bw->expected_value) {
            bw->waiter_state = WAITER_STATE_UNMATCHEDVALUE;
        } else if (bw->waiter_state == WAITER_STATE_READY/*1*/ &&
                   !bw->task_meta->interrupted) {
            b->waiters.Append(bw);
            bw->container.store(b, butil::memory_order_relaxed);
            return;
        }
    }
    
    // b->container is NULL which makes erase_from_butex_and_wakeup() and
    // TaskGroup::interrupt() no-op, there's no race between following code and
    // the two functions. The on-stack ButexBthreadWaiter is safe to use and
    // bw->waiter_state will not change again.
    unsleep_if_necessary(bw, get_global_timer_thread());
    tls_task_group->ready_to_run(bw->tid);
    // FIXME: jump back to original thread is buggy.
    
    // // Value unmatched or waiter is already woken up by TimerThread, jump
    // // back to original bthread.
    // TaskGroup* g = tls_task_group;
    // ReadyToRunArgs args = { g->current_tid(), false };
    // g->set_remained(TaskGroup::ready_to_run_in_worker, &args);
    // // 2: Don't run remained because we're already in a remained function
    // //    otherwise stack may overflow.
    // TaskGroup::sched_to(&g, bw->tid, false/*2*/);
}
```
注释最开始提到一种情况就是在执行 `wait_for_butex()` 之前就已经 timeout了，那么 waiter_state 就不再是 `WAITER_STATE_READY` 而是 `WAITER_STATE_TIMEDOUT` 了（什么情况下才会发生？erase_from_butex() 中的如果 container == NULL 就什么都不会做，而 container 是在这里才会赋值的）。


这里首先再次检查一次 butex 的 value 等于 expected_value，否则也不会 wait。
如果当前 waiter_state 是 `WAITER_STATE_READY` 并且 bthread 没有被 interrupted，就把当前 bthread 的信息加到 butex 的等待队列中（`b->waiters.Append(bw)`），然后给 container 赋值（container 初始为 NULL）。


如果不需要 wait，就把 bthread 重新加到执行队列中（`tls_task_group->ready_to_run(bw->tid)`）等待被调度执行。不需要 wait 的情况：

1. butex.value != expected_value （在这之前已经 wake_up 了）
1. waiter != WAITER_STATE_READY
1. interrupted



```cpp
    // erase_from_butex_and_wakeup (called by TimerThread) is possibly still
    // running and using bbw. The chance is small, just spin until it's done.
    BT_LOOP_WHEN(unsleep_if_necessary(&bbw, get_global_timer_thread()) < 0,
                 30/*nops before sched_yield*/);
    
    // If current_waiter is NULL, TaskGroup::interrupt() is running and using bbw.
    // Spin until current_waiter != NULL.
    BT_LOOP_WHEN(bbw.task_meta->current_waiter.exchange(
                     NULL, butil::memory_order_acquire) == NULL,
                 30/*nops before sched_yield*/);
```


```cpp
    bool is_interrupted = false;
    if (bbw.task_meta->interrupted) {
        // Race with set and may consume multiple interruptions, which are OK.
        bbw.task_meta->interrupted = false;
        is_interrupted = true;
    }
    // If timed out as well as value unmatched, return ETIMEDOUT.
    if (WAITER_STATE_TIMEDOUT == bbw.waiter_state) {
        errno = ETIMEDOUT;
        return -1;
    } else if (WAITER_STATE_UNMATCHEDVALUE == bbw.waiter_state) {
        errno = EWOULDBLOCK;
        return -1;
    } else if (is_interrupted) {
        errno = EINTR;
        return -1;
    }
    return 0;
```
## Wake
```cpp
// Wake up at most 1 thread waiting on |butex|.
// Returns # of threads woken up.
int butex_wake(void* butex);

// Wake up all threads waiting on |butex|.
// Returns # of threads woken up.
int butex_wake_all(void* butex);

// Wake up all threads waiting on |butex| except a bthread whose identifier
// is |excluded_bthread|. This function does not yield.
// Returns # of threads woken up.
int butex_wake_except(void* butex, bthread_t excluded_bthread);

// Wake up at most 1 thread waiting on |butex1|, let all other threads wait
// on |butex2| instead.
// Returns # of threads woken up.
int butex_requeue(void* butex1, void* butex2);
```
wake 有多种变形

1. butex_wake() 唤醒最多一个等待在 butex 上的 waiter（pthread or bthread）；
1. butex_wake_all() 唤醒所有等待在该 butext 的 waiter；
1. butex_wake_except() 唤醒除了 excluded_bthread 以外所有的 waiter；
1. butex_requeue() 用于 condition variable。



```cpp
int butex_wake(void* arg) {
    Butex* b = container_of(static_cast<butil::atomic<int>*>(arg), Butex, value);
    ButexWaiter* front = NULL;
    {
        BAIDU_SCOPED_LOCK(b->waiter_lock);
        if (b->waiters.empty()) {
            return 0;
        }
        front = b->waiters.head()->value();
        front->RemoveFromList();
        front->container.store(NULL, butil::memory_order_relaxed);
    }
    if (front->tid == 0) {
        wakeup_pthread(static_cast<ButexPthreadWaiter*>(front));
        return 1;
    }
    ButexBthreadWaiter* bbw = static_cast<ButexBthreadWaiter*>(front);
    unsleep_if_necessary(bbw, get_global_timer_thread());
    TaskGroup* g = tls_task_group;
    if (g) {
        TaskGroup::exchange(&g, bbw->tid);
    } else {
        bbw->control->choose_one_group()->ready_to_run_remote(bbw->tid);
    }
    return 1;
}
```
wake 的逻辑很简单：

1. 首先从该 butex 的等待列表中按顺序拿出第一个 waiter
1. 如果 waiter 是 pthread，就 `wakeup_pthread()`
1. 如果 waiter 是 bthread
   1. TaskGroup 不是 NULL，表示是在 bthread 中唤醒的
   1. TaskGroup 是 NULL，表示不是在 bthread 中唤醒的，随机选择一个 TaskGroup 把任务加到队列中。



```cpp
inline void TaskGroup::exchange(TaskGroup** pg, bthread_t next_tid) {
    TaskGroup* g = *pg;
    if (g->is_current_pthread_task()) {
        return g->ready_to_run(next_tid);
    }
    ReadyToRunArgs args = { g->current_tid(), false };
    g->set_remained((g->current_task()->about_to_quit
                     ? ready_to_run_in_worker_ignoresignal
                     : ready_to_run_in_worker),
                    &args);
    TaskGroup::sched_to(pg, next_tid);
}
```
# bthread mutex


# bthread condition


# countdown


# Links

1. Futex：[https://en.wikipedia.org/wiki/Futex](https://en.wikipedia.org/wiki/Futex)
1. futex(2) — Linux manual page：[https://man7.org/linux/man-pages/man2/futex.2.html](https://man7.org/linux/man-pages/man2/futex.2.html)
