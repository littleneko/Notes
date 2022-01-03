由第一篇文章我们知道，调用 `bthread_start_background()` 开启一个 bthread 实际上是把任务加到 `TaskGroup::rq_` 或 `TaskGroup::remote_rq_` 中，这是一个生产者生产消息的过程；同时 TaskGroup 的 worker 进行任务窃取的流程实际上是从 rq_ 或 remote_rq_ 中取任务的过程，这是一个消费者消费消息的过程。


bthread 中生产者和消费者之间的同步使用的是 `ParkingLot` 实现的，ParkingLot 实现了 `wait()` 和 `signal()` 语义，用于实现生产者和消费者之间的状态同步，其功能类似于条件变量。
# ParkingLot 初始化
我们先看看 ParkingLot 在 bthread 中和 TaskControl、TaskGroup 的关系。
在 TaskControl 中 ParkingLot 相关成员如下：
```cpp
// Control all task groups
class TaskControl 
private:
    static const int PARKING_LOT_NUM = 4;
    ParkingLot _pl[PARKING_LOT_NUM];
}
```
全局一共只有 4 个 ParkingLot，负责所有 TaskGroup 中生产者和消费者的同步。


在 TaskGroup 中 ParkingLot 相关成员如下：
```cpp
class TaskGroup {
private:
	ParkingLot* _pl;
#ifndef BTHREAD_DONT_SAVE_PARKING_STATE
    ParkingLot::State _last_pl_state;
#endif
}
```
> **Tips**：
> 其中宏 BTHREAD_DONT_SAVE_PARKING_STATE 在编译时参数一般是关闭，因此下面的讨论都是基于 #ifndef BTHREAD_DONT_SAVE_PARKING_STATE 为 true 的情况。



`TaskGroup::_pl` 的初始化：
```cpp
TaskGroup::TaskGroup(TaskControl* c)
// 省略初始化参数列表
{
    _steal_seed = butil::fast_rand();
    _steal_offset = OFFSET_TABLE[_steal_seed % ARRAY_SIZE(OFFSET_TABLE)];
    _pl = &c->_pl[butil::fmix64(pthread_numeric_id()) % TaskControl::PARKING_LOT_NUM];
    CHECK(c);
}
```
这里使用当前 TaskGroup 所在的 pthread_id 作为参数，计算出一个 hash 并对 `PARKING_LOT_NUM` 取模，因此 TaskGroup 中的 ParkingLot 指针实际上是指向了 TaskControl 全局 ParkingLot 中的某一个对象，即 TaskGroup 被分成了 4 组，共享 TaskControl 中 4 个 ParkingLot 中某一个。
# 生产者
TaskGroup 中执行任务入队的函数是 `TaskGroup::ready_to_run_remote()` 和 `TaskGroup::ready_to_run()` ，其在 `TaskGroup::start_background()` 中的调用如下：
```cpp
int TaskGroup::start_background(// ...) {    
	if (REMOTE) {
        ready_to_run_remote(m->tid, (using_attr.flags & BTHREAD_NOSIGNAL));
    } else {
        ready_to_run(m->tid, (using_attr.flags & BTHREAD_NOSIGNAL));
    }
}
```
## TaskGroup::ready_to_run() / ready_to_run_remote()
我们先看 `TaskGroup::ready_to_run()` ：
```cpp
void TaskGroup::ready_to_run(bthread_t tid, bool nosignal) {
    push_rq(tid);
    if (nosignal) {
        ++_num_nosignal;
    } else {
        const int additional_signal = _num_nosignal;
        _num_nosignal = 0;
        _nsignaled += 1 + additional_signal;
        _control->signal_task(1 + additional_signal);
    }
}
```
该函数执行 2 个操作：任务入队和通知消费者，我们先看任务入队：
```cpp
inline void TaskGroup::push_rq(bthread_t tid) {
    while (!_rq.push(tid)) {
        // Created too many bthreads: a promising approach is to insert the
        // task into another TaskGroup, but we don't use it because:
        // * There're already many bthreads to run, inserting the bthread
        //   into other TaskGroup does not help.
        // * Insertions into other TaskGroups perform worse when all workers
        //   are busy at creating bthreads (proved by test_input_messenger in
        //   brpc)
        flush_nosignal_tasks();
        LOG_EVERY_SECOND(ERROR) << "_rq is full, capacity=" << _rq.capacity();
        // TODO(gejun): May cause deadlock when all workers are spinning here.
        // A better solution is to pop and run existing bthreads, however which
        // make set_remained()-callbacks do context switches and need extensive
        // reviews on related code.
        ::usleep(1000);
    }
}

void TaskGroup::flush_nosignal_tasks() {
    const int val = _num_nosignal;
    if (val) {
        _num_nosignal = 0;
        _nsignaled += val;
        _control->signal_task(val);
    }
}
```
`TaskGroup::push_rq()` 是一个 while 循环，一直尝试 push 任务到 rq_ 中，直到成功。push 失败的唯一原因就是 \_rq 队列满了，因此如果 push 失败了就通知消费者快速消费队列中的任务。`TaskGroup::flush_nosignal_tasks()` 取队列中还没有通知的任务数 \_num_nosignal，调用 `TaskControl::signal_task()` 通知的消费者。


然后我们再来看通知消费者的流程，如果 nosignal 参数为 true，即==调用 `bthread_start_background()` 时设置了 `BTHREAD_NOSIGNAL` flag，那么只会记录当前 push 到队列中的任务数（\_num_nosignal++），并不会通知消费者==。如果 nosignal 为 false 首先取出 \_num_nosignal 并把其置为 0，然后调用 `TaskControl::signal_task()` 通知消费者。（其中 \_nsignaled 是一个计数，不用关注。）


调用 `TaskControl::signal_task()` 的参数是 `1 + additional_signal` （即 `1 + _num_nosignal`），其中 `1` 表示当前任务，`_num_nosignal` 表示 TaskGroup 中还没有通知过的任务数，因此表示通知消费者一共需要消费的任务数量。


> **关于 BTHREAD_NOSIGNAL 和 _num_nosignal**：
> BTHREAD_NOSIGNAL 是调用 `bthread_start_background()` 的第二个参数，设置了该 flag 表示任务入队的时候并不会通知消费者，只是记录现在加到队列中的任务数（_num_nosignal++）。那什么时候会通知消费者去消费队列中的任务呢？有 2 种情况：
>
> - 入队的时候发现队列满了，调用 `TaskGroup::flush_nosignal_tasks()`
> - 等到一个没有设置 BTHREAD_NOSIGNAL 的任务加到队列中时 



`TaskGroup::ready_to_run_remote()` 的逻辑基本一样，唯一的区别是操作 _remote_rq 的时候需要先加锁。
```cpp
void TaskGroup::ready_to_run_remote(bthread_t tid, bool nosignal) {
    _remote_rq._mutex.lock();
    while (!_remote_rq.push_locked(tid)) {
        flush_nosignal_tasks_remote_locked(_remote_rq._mutex);
        LOG_EVERY_SECOND(ERROR) << "_remote_rq is full, capacity="
                                << _remote_rq.capacity();
        ::usleep(1000);
        _remote_rq._mutex.lock();
    }
    if (nosignal) {
        ++_remote_num_nosignal;
        _remote_rq._mutex.unlock();
    } else {
        const int additional_signal = _remote_num_nosignal;
        _remote_num_nosignal = 0;
        _remote_nsignaled += 1 + additional_signal;
        _remote_rq._mutex.unlock();
        _control->signal_task(1 + additional_signal);
    }
}
```
> **Tips**:
> Q. 为什么 push _rq 时不需要加锁，而操作 _remote_rq 时需要加锁？
> A. 因为 `TaskGroup::_rq` 保存的是当前 bthread 产生的任务，push 不会有竞争；而 `TaskGroup::_remote_rq` 是任何线程都可以向其中放入任务，push 会有竞争。

## TaskControl::signal_task()
```cpp
void TaskControl::signal_task(int num_task) {
    if (num_task <= 0) {
        return;
    }
    // TODO(gejun): Current algorithm does not guarantee enough threads will
    // be created to match caller's requests. But in another side, there's also
    // many useless signalings according to current impl. Capping the concurrency
    // is a good balance between performance and timeliness of scheduling.
    if (num_task > 2) {
        num_task = 2;
    }
    int start_index = butil::fmix64(pthread_numeric_id()) % PARKING_LOT_NUM;
    num_task -= _pl[start_index].signal(1);
    if (num_task > 0) {
        for (int i = 1; i < PARKING_LOT_NUM && num_task > 0; ++i) {
            if (++start_index >= PARKING_LOT_NUM) {
                start_index = 0;
            }
            num_task -= _pl[start_index].signal(1);
        }
    }
    if (num_task > 0 &&
        FLAGS_bthread_min_concurrency > 0 &&    // test min_concurrency for performance
        _concurrency.load(butil::memory_order_relaxed) < FLAGS_bthread_concurrency) {
        // TODO: Reduce this lock
        BAIDU_SCOPED_LOCK(g_task_control_mutex);
        if (_concurrency.load(butil::memory_order_acquire) < FLAGS_bthread_concurrency) {
            add_workers(1);
        }
    }
}
```
num_task 如果大于2，则重置为 2，也就是说下面逻辑中 num_task 的有效值只有 1 和 2 ，注释中提到，把num_task 不超过 2，是在性能和调度时间直接的一种平衡。


> **num_task 设置为 2 的原因：**
> 注释中说是为了性能和调度时间之间的平衡，这句话如何理解呢？其实是这样，如果 signal_task() 通知的任务个数多，那么队列被消费的也就越快。消费的快本来是好事，但是也有个问题就是我们现在之所以走到 signal_task() 是因为我们在 “生产” bthread 任务，也就是说在执行 `bthread_start_background()`（或其他函数）创建新任务。这个函数调用是阻塞的，如果 signal_task() 通知的任务个数太多，则会导致 `bthread_start_background()` 阻塞的时间拉长。所以这里说是找到一种平衡。



start_index 计算方式和刚给 TaskGroup 分配 ParkingLot 的相同，主要就是找到了当前 TaskGroup 所归属的 ParkingLot，然后调用 `ParkingLot::signal(1)` 进行通知。我们先不关注 `ParkingLot::signal(1)` 的具体实现，从注释中我们知道其参数表示最多唤醒的 worker 数量（Wake up at most `num_task` workers），返回值表示成功唤醒的 worker 数量（Returns #workers woken up）。


因此 `num_task -= _pl[start_index].signal(1);` 表示==唤醒该 TaskGroup 所在 ParkingLot 组的任意一个 TaskGroup==，num_task 表示还剩下需要唤醒的 worker。
> **Tips**:
> 前面我们知道，最开始 TaskGroup 根据 pthread_id 被分成了 4 个 ParkingLot 组，这里并不是唤醒该 TaskGroup 对应的 worker，而是所在 ParkingLot 组的任意一个 worker。因为有任务窃取，所有其他 worker 也会消费当前 TaskGroup 的 \_rq 和 \_remote_rq 中的任务。



接着，==如果还有任务需要唤醒==（前面我们知道，num_task 只能是 1 或 2，因此走到这里表示 num_task 为 2 或者 `_pl[start_index].signal(1)` 返回了 0，即唤醒当前 TaskGroup 所在 ParkingLot 组的 worker 失败。），==就唤醒其他 ParkingLot 组的 worker==。

==如果任务还有剩余（表示消费者不够用）==，并且全局 TaskControl 的并发度（\_concurrency）小于 gflag 中配置的 bthread_min_concurrency，那么==就调用 `TaskControl::add_workers()` 去增加 worker 的数量==，从这里可以看到 FLAGS_bthread_concurrency 是 worker 个数的硬门槛。


从这里可以看出，如果当前唤醒的 worker 数量不够而且也不能再增加 worker 数量的时候，说明系统负载很高，该 bthread 任务就不能被立即执行，只能在队列中等待。
## ParkingLot::signal()
现在我们来看看 `ParkingLot::signal()` 函数，首先把 `ParkingLot::_pending_signal` 累加上 `num_task * 2`，然后调用 futex 实现的唤醒操作。我们先不关注 `futex_wake_private()` 的具体实现，其含义是最多唤醒 num_task 个阻塞在 \_pending_signal 上的消费者。


这里把 `_pending_signal` 置为 `num_task * 2` 实际上是为了保证 `_pending_signal` 为偶数，原因是奇数是用来判断是否停止的条件（参考 `ParkingLot::stop()` 和 `ParkingLot::State::stopped()` 函数）。
```cpp
class BAIDU_CACHELINE_ALIGNMENT ParkingLot {
public    
	// Wake up at most `num_task' workers.
    // Returns #workers woken up.
    int signal(int num_task) {
        _pending_signal.fetch_add((num_task << 1), butil::memory_order_release);
        return futex_wake_private(&_pending_signal, num_task);
}
```
# 消费者
## TaskGroup::wait_task()
消费者即 `TaskGroup::wait_task()` 函数，`TaskGroup::run_main_task()` 的第一步就是调用该函数等待一个任务。
```cpp
bool TaskGroup::wait_task(bthread_t* tid) {
    do {
        // 省略 BTHREAD_DONT_SAVE_PARKING_STATE 的情况
        if (_last_pl_state.stopped()) {
            return false;
        }
        _pl->wait(_last_pl_state);
        if (steal_task(tid)) {
            return true;
        }
    } while (true);
}
```
_last_pl_state 是 `ParkingLot::State` 类型，其定义如下：
```cpp
class BAIDU_CACHELINE_ALIGNMENT ParkingLot {
public    
	class State {
    public:
        State(): val(0) {}
        bool stopped() const { return val & 1; }
    private:
    friend class ParkingLot;
        State(int val) : val(val) {}
        int val;
    };
}
```
其判断 `State::stopped()` 的条件实际上是判断 `State::val` 是否是奇数，因为在生产任务时，`ParkingLot::signal()` 总是给 `ParkingLot::_pending_signal` 累加一个偶数（num_task * 2），而这里的 _last_pl_state.val 就是从 `ParkingLot::_pending_signal` 取的，所以正常情况下这里条件总是 false 。
> ParkingLot::_pending_signal 在什么情况下是奇数？
> `ParkingLot::_pending_signal` 为奇数的情况即主动 stop 的情况， `ParkingLot::stop()` 函数中，使用 `_pending_signal.fetch_or(1)` 把 `ParkingLot::_pending_signal` 置为了奇数。

## TaskGroup::_last_pl_state 状态同步
那 `_last_pl_state` 是在什么时候变化的呢？答案是接下来的 `steal_task(tid)` 中，在当前 TaskGroup 的 _remote_rq 无任务的时候，_last_pl_state 会从 _pl 同步一次状态。
```cpp
class TaskGroup {
private:
	bool steal_task(bthread_t* tid) {
        if (_remote_rq.pop(tid)) {
            return true;
        }
#ifndef BTHREAD_DONT_SAVE_PARKING_STATE
        _last_pl_state = _pl->get_state();
#endif
        return _control->steal_task(tid, &_steal_seed, _steal_offset);
    }
}
```
同步状态即取 `ParkingLot::_pending_signal` 的值
```cpp
    // Get a state for later wait().
    State get_state() {
        return _pending_signal.load(butil::memory_order_acquire);
    }
```
## ParkingLot::wait()
我们来看看 `ParkingLot::wait()`，其最终调用的是系统的 futex 接口，我们先不关注其具体实现，从注释中我们知道如果 `_pl._pending_signal == _last_pl_state.val`，则该函数会阻塞，也就是还没有新的任务出现就阻塞。
```cpp
    // Wait for tasks.
    // If the `expected_state' does not match, wait() may finish directly.
    void wait(const State& expected_state) {
        futex_wait_private(&_pending_signal, expected_state.val, NULL);
    }
```


TaskGroup 在消费完自己的 _rq 和 _remote_rq 后会同步一次 `_last_pl_state` 值，然后取窃取其他 TaskGroup 的任务，最后当其他 TaskGroup 任务也消费完了的时候，会回到 `wait_task()` 主循环，然后调用 `wait(_last_pl_state)`；所以如果在上一次同步 `_last_pl_state` 后又有新的任务添加到该 TaskGroup，就会调用 single，此时 `_pl._pending_signal` 就会变化，wait 函数会立即返回，不会阻塞。
# ParkingLot
前面的流程中，已经涉及到了很多 `ParkingLot` 的内容，这里总结一下。
```cpp
// Park idle workers.
class BAIDU_CACHELINE_ALIGNMENT ParkingLot {
public:
    class State {
    public:
        State(): val(0) {}
        bool stopped() const { return val & 1; }
    private:
    friend class ParkingLot;
        State(int val) : val(val) {}
        int val;
    };

    ParkingLot() : _pending_signal(0) {}

    // Wake up at most `num_task' workers.
    // Returns #workers woken up.
    int signal(int num_task) {
        _pending_signal.fetch_add((num_task << 1), butil::memory_order_release);
        return futex_wake_private(&_pending_signal, num_task);
    }

    // Get a state for later wait().
    State get_state() {
        return _pending_signal.load(butil::memory_order_acquire);
    }

    // Wait for tasks.
    // If the `expected_state' does not match, wait() may finish directly.
    void wait(const State& expected_state) {
        futex_wait_private(&_pending_signal, expected_state.val, NULL);
    }

    // Wakeup suspended wait() and make them unwaitable ever. 
    void stop() {
        _pending_signal.fetch_or(1);
        futex_wake_private(&_pending_signal, 10000);
    }
private:
    // higher 31 bits for signalling, LSB for stopping.
    butil::atomic<int> _pending_signal;
};
```
`ParkingLot::wait()` 和 `ParkingLot::signal()` 使用 futex 实现的同步，这里先介绍一下 futex。
```cpp
       long syscall(SYS_futex, uint32_t *uaddr, int futex_op, uint32_t val,
                    const struct timespec *timeout,   /* or: uint32_t val2 */
                    uint32_t *uaddr2, uint32_t val3);
```
**参数解析** ：

- uaddr：指针指向一个整型，存储一个整数。
- op：表示要执行的操作类型，比如唤醒(FUTEX_WAKE)、等待(FUTEX_WAIT)
- val：表示一个值，对于不同的 op 类型，val 语义不同。
   - 对于等待操作：如果 uaddr 存储的整型与 val 相同则继续休眠等待，等待时间就是 timeout 参数。
   - 对于唤醒操作：val 表示，最多唤醒 val 个阻塞等待 uaddr 上的“消费者”（之前对同一个uaddr调用过FUTEX_WAIT，姑且称之为消费者，其实在brpc语境中，就是阻塞的 worker）。
- timeout：表示超时时间，仅对 op 类型为等待时有用。就是休眠等待的最长时间，在 uaddr2 和 val3 可以忽略。



**返回值解析** ：

- 对于等待操作：成功返回 0，失败返回 -1
- 对于唤醒操作：成功返回唤醒的之前阻塞在 futex 上的“消费者”个数；失败返回 -1。



wake 实现：
```cpp
inline int futex_wake_private(void* addr1, int nwake) {
    return syscall(SYS_futex, addr1, (FUTEX_WAKE | FUTEX_PRIVATE_FLAG),
                   nwake, NULL, NULL, 0);
}
```
因此 `ParkingLot::signal()` 最终等价与下面的调用：
```cpp
futex(&_pending_signal, (FUTEX_WAKE | FUTEX_PRIVATE_FLAG), num_task, NULL, NULL, 0);
```


wait 实现：
```cpp
inline int futex_wait_private(
    void* addr1, int expected, const timespec* timeout) {
    return syscall(SYS_futex, addr1, (FUTEX_WAIT | FUTEX_PRIVATE_FLAG),
                   expected, timeout, NULL, 0);
}
```
因此 `ParkingLot:wait()` 最终等价与下面的调用：
```cpp
futex(&_pending_signal, (FUTEX_WAIT | FUTEX_PRIVATE_FLAG), expected_state.val, NULL, NULL, 0);
```


因此 `ParkingLot::_pending_signal` 的值没有实际的意义，并不是表示任务个数，只是用来进行生产者和消费者同步的媒介。
# Summary
总结一下：

- TaskGroup 一共被分成了 4 组，每组共用一个 ParkingLot，目的是为了减小竞争
- TaskGroup 的主循环在没有任务可以执行的时候会等待在 `_last_pl_state` 上，直到有新任务添加到队列中（即创建一个新的 bthread）
- 创建一个新的 bthread 的步骤是向 TaskGroup 的 _rq 和  _remote_rq 中添加任务，累加 `PakringLot::_pending_signal`，并调用 `ParkingLot::signal(num_task)` 唤醒等待在 `_last_pl_state`（`PakringLot::_pending_signal`）上的消费者（即当前空闲没活干的 worker）
- 一次最多唤醒 2 个空闲 worker
- 如果没有足够的空闲 worker 可以唤醒来执行任务
   - worker 数量小于 FLAGS_bthread_concurrency：创建新的 worker（为了任务被更快地执行）
   - 不满足上述条件，do nothing（只能等待任务被从队列中取出执行）



> **什么情况下消费者会阻塞在 **`**_last_pl_state**`** 上等待被唤醒？**
> 1. 系统初始化时，所有 worker（TaskGroup）都等待被唤醒
> 1. TaskGroup 的 \_rq、\_remote_rq 和其他 TaskGroup 中都没有任务时



> **关于 BTHREAD_NOSIGNAL FLAG：**
> - 设置该 FLAG：只要队列没满，就只入队；队列满的时候唤醒消费者，任务不保证会被立即执行
> - 不设置该FLAG：入队的同时唤醒消费者，如果空闲的消费者不够，还有可能创建新的 worker，让任务尽可能地被更快地执行。

# Links

1. [https://zhuanlan.zhihu.com/p/346081659](https://zhuanlan.zhihu.com/p/346081659)
