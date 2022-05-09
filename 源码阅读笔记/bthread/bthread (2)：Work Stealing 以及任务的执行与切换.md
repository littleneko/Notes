上一篇文章中提到 bthread 的两个重要特性，分别是：work stealing 调度和 butex，work stealing 使得 bthread 能够更快地被调度到更多的核心上，充分利用多核。接下来我们从 bthread 的入口函数一路跟踪到任务的执行流程，了解 bthread 的任务调度逻辑。
# bthread 入口
bthread 有两个入口函数： `bthread_start_background()` 和 `bthread_start_urgent()` ，后者用于 urgent 的场景，bthread 会立即执行；前者更常用，我们主要从其入手。


`bthread_start_background()` 逻辑很简单，

- 如果当前线程 _thread local_ 的 **TaskGroup** 不为空，就使用该 TaskGroup 执行任务（`TaskGroup::start_background()`，这里说使用该 TaskGroup 执行任务实际上并不准确，因为有任务窃取，并不保证这个任务是由该 TaskGroup 执行的）；
- 否则就以没有 worker 的方式执行任务（`bthread::start_from_non_worker()`）。
```cpp
// file: bthread.cpp

extern BAIDU_THREAD_LOCAL TaskGroup* tls_task_group;

int bthread_start_background(bthread_t* __restrict tid,
                             const bthread_attr_t* __restrict attr,
                             void * (*fn)(void*),
                             void* __restrict arg) {
    bthread::TaskGroup* g = bthread::tls_task_group;
    if (g) {
        // start from worker
        return g->start_background<false>(tid, attr, fn, arg);
    }
    return bthread::start_from_non_worker(tid, attr, fn, arg);
}
```
这里是否有 _thread local_ 的 TaskGroup 实际上对应了两种情况：

1. 无 thread local 的 TaskGroup 对象：==在 bthread 外部调用 `bthread_start_background()` 创建一个 bthread，对应了我们写程序时在自己的业务线程 （pthread）中创建了一个 bthread==。
1. 有 thread local 的 TaskGroup 对象：==在 bthread 内部创建 bthread，对应的场景是我们在 bthread 任务 `fn` 中又调用 `bthread_start_background()` 创建了一个 bthread，这种情况下获取到的 TaskGroup 对象就是当前 bthread 运行在的 TaskGroup==。



> **Tips**：
> 	这里调用 `TaskGroup::start_background()` 时的非类型模板参数（[Non-type template parameter](https://en.cppreference.com/w/cpp/language/template_parameters)）REMOTE 传入的是 `false`，最终在 `TaskGroup::start_background()` 中会调用 `TaskGroup::ready_to_run()` 函数把任务加到 TaskGroup 的本地队列 `_rq` 中（在  `bthread::start_from_non_worker()` 中，最终传入的 REMOTE 参数是 `ture`，会把任务添加到 TaskGroup 的远程队列 `_remote_rq` 中）。关于这两个队列的区别，下面会解释。

## TaskGroup::start_background()
函数 `start_background()` 很简单，主要流程：

1. 从资源池中拿一个任务（**TaskMeta**）（`butil::get_resource()`）
1. 初始化该 TaskMeta（赋值回调函数 `fn` 、参数 `arg` ，生成 `tid`）
1. 把任务加到 TaskGroup 的任务队列中（ `TaskGroup::ready_to_run_remote()` 和 `TaskGroup::ready_to_run()` )



`TaskGroup::start_background()` 并没有直接就执行了该任务，只是把任务加到了 TaskGroup 的任务队列中，实际上==由于有任务窃取的机制，这个任务最终不一定是由该 TaskGroup 执行的==。

```cpp
// file: task_group.cpp

template <bool REMOTE>
int TaskGroup::start_background(bthread_t* __restrict th,
                                const bthread_attr_t* __restrict attr,
                                void * (*fn)(void*),
                                void* __restrict arg) {
    if (__builtin_expect(!fn, 0)) {
        return EINVAL;
    }
    const int64_t start_ns = butil::cpuwide_time_ns();
    const bthread_attr_t using_attr = (attr ? *attr : BTHREAD_ATTR_NORMAL);
    // 1. 从资源池中拿一个 TaskMeta，避免频繁 new 对象
    butil::ResourceId<TaskMeta> slot;
    TaskMeta* m = butil::get_resource(&slot);
    if (__builtin_expect(!m, 0)) {
        return ENOMEM;	
    }
    CHECK(m->current_waiter.load(butil::memory_order_relaxed) == NULL);
    // 2. 初始化该 TaskMeta, 主要是把 fn 和 arg 保存，生成 tid
    m->stop = false;
    m->interrupted = false;
    m->about_to_quit = false;
    m->fn = fn;
    m->arg = arg;
    CHECK(m->stack == NULL);
    m->attr = using_attr;
    m->local_storage = LOCAL_STORAGE_INIT;
    m->cpuwide_start_ns = start_ns;
    m->stat = EMPTY_STAT;
    m->tid = make_tid(*m->version_butex, slot);
    *th = m->tid;
    if (using_attr.flags & BTHREAD_LOG_START_AND_FINISH) {
        LOG(INFO) << "Started bthread " << m->tid;
    }
    _control->_nbthreads << 1;
    // 3. 把任务加到 TaskGroup 的任务队列中
    if (REMOTE) {
        ready_to_run_remote(m->tid, (using_attr.flags & BTHREAD_NOSIGNAL));
    } else {
        ready_to_run(m->tid, (using_attr.flags & BTHREAD_NOSIGNAL));
    }
    return 0;
}
```
> **Tips**:
> 	这里的 TaskMeta 并不是 new 出来的，而是 `butil::get_resource(&slot)` 从资源池中拿的，bthread 的创建是非常频繁的，如果每次开启一个 bthread 就 new 一个 TaskMeta，bthread 执行完后就 delete，内存的申请和释放会非常频繁，使用资源池的目的是为了避免频繁地申请和释放内存。

## bthread::start_from_non_worker()
函数 `start_from_non_worker()` 首先会拿到全局的 TaskControl （`get_or_new_task_control()`），然后由 TaskControl 随机选取一个 TaskGroup 执行任务（`c->choose_one_group()->start_background<true>()`，这里先忽略 BTHREAD_NOSIGNAL 相关的逻辑）
```cpp
__thread TaskGroup* tls_task_group_nosignal = NULL;

BUTIL_FORCE_INLINE int
start_from_non_worker(bthread_t* __restrict tid,
                      const bthread_attr_t* __restrict attr,
                      void * (*fn)(void*),
                      void* __restrict arg) {
    TaskControl* c = get_or_new_task_control();
    if (NULL == c) {
        return ENOMEM;
    }
    if (attr != NULL && (attr->flags & BTHREAD_NOSIGNAL)) {
        // Remember the TaskGroup to insert NOSIGNAL tasks for 2 reasons:
        // 1. NOSIGNAL is often for creating many bthreads in batch,
        //    inserting into the same TaskGroup maximizes the batch.
        // 2. bthread_flush() needs to know which TaskGroup to flush.
        TaskGroup* g = tls_task_group_nosignal;
        if (NULL == g) {
            g = c->choose_one_group();
            tls_task_group_nosignal = g;
        }
        return g->start_background<true>(tid, attr, fn, arg);
    }
    return c->choose_one_group()->start_background<true>(
        tid, attr, fn, arg);
}
```
> **Tips**:
> 1. 这里调用 `TaskGroup::start_background()` 时 REMOTE 参数为 `true`，最终会调用 `TaskGroup::ready_to_run_remote()` 把任务加到 TaskGroup 远程队列的 `_remote_rq` 中。
> 1. 函数 `get_or_new_task_control()` 在没有全局 TaskControl 时会创建一个，对应的情况是第一次创建 bthread 的场景。
>
> 所以说 `TaskGroup::start_background<REMOTE>()` 的 ==REMOTE 参数实际上表示了该 bthread 是由普通的 pthread 创建还是由 bthread 创建==。

# Overview
从上面新建 bthread 的流程中，我们看到了 bthread 中 3 个重要的类，分别为：

- **TaskControl**：全局的单例对象，用于管理 TaskGroup
- **TaskGroup**：具体执行任务的类，即 worker，每个 TaskGroup 对应一个线程 （pthread）
- **TaskMeta：**保存了 bthread 的上下文信息，表示一个 bthread 任务
## TaskControl
TaskControl 由函数 `TaskControl::get_or_new_task_control()` 创建，调用关系如下：

- bthread_start_background() -> start_from_non_worker() -> TaskControl::get_or_new_task_control()
- bthread_start_urgent() -> start_from_non_worker() -> TaskControl::get_or_new_task_control()
- bthread_timer_add() -> TaskControl::get_or_new_task_control()
### bthread::get_or_new_task_control()
TaskControl 是全局唯一的，虽然每次在 pthread 中创建 bthread 时，都会走 `start_from_non_worker() -> get_or_new_task_control()` 逻辑，但是==只有在全局 TaskControl 为空（即全局第一次调用该函数）时才需要创建一个 TaskControl==， 创建 TaskControl 的逻辑如下（注意如何使用原子变量保证 TaskControl 的全局唯一性）：
```cpp
// file: bthread.cpp

pthread_mutex_t g_task_control_mutex = PTHREAD_MUTEX_INITIALIZER;
// Referenced in rpc, needs to be extern.
// Notice that we can't declare the variable as atomic<TaskControl*> which
// are not constructed before main().
TaskControl* g_task_control = NULL;


inline TaskControl* get_or_new_task_control() {
    butil::atomic<TaskControl*>* p = (butil::atomic<TaskControl*>*)&g_task_control;
    // 通过原子变量进行load，取出 TC 指针，如果不为空，直接返回
    // 使用 memory_order_consume 保证后面访问该变量的指令不会重排到其之前
    TaskControl* c = p->load(butil::memory_order_consume);
    if (c != NULL) {
        return c;
    }
    // 加锁，并再次确认 p 是否为空，如果不为空才真的 new 一个
    BAIDU_SCOPED_LOCK(g_task_control_mutex);
    c = p->load(butil::memory_order_consume);
    if (c != NULL) {
        return c;
    }
    c = new (std::nothrow) TaskControl;
    if (NULL == c) {
        return NULL;
    }
    // 初始化全局 TaskControl
    int concurrency = FLAGS_bthread_min_concurrency > 0 ?
        FLAGS_bthread_min_concurrency :
        FLAGS_bthread_concurrency;
    if (c->init(concurrency) != 0) {
        LOG(ERROR) << "Fail to init g_task_control";
        delete c;
        return NULL;
    }
    // 赋值原子变量，使用 memory_order_release 保证前面访问该变量的指令不会重排到其之后
    // 即当此条指令的结果对其他线程可见后，之前的所有指令都可见
    p->store(c, butil::memory_order_release);
    return c;
}
```
### TaskControl::init()
TaskControl 的初始化实际上是创建了 `concurrency` 个 pthread，每个 pthread 的回调函数都是 `TaskControl::worker_thread()` 。
```cpp
// file: task_control.cpp

int TaskControl::init(int concurrency) {
    // ... ...
    
	for (int i = 0; i < _concurrency; ++i) {
        const int rc = pthread_create(&_workers[i], NULL, worker_thread, this);
        if (rc) {
            LOG(ERROR) << "Fail to create _workers[" << i << "], " << berror(rc);
            return -1;
        }
    }
    
    // ... ...
}
```
### TaskControl::worker_thread()
到这里我们终于看到了 bthread  的 worker (TaskGroup) 实际执行任务的入口，`worker_thread()` 流程如下： 

1. 创建一个 TaskGroup （`TaskControl::create_group()`，同时会保存这个 TaskGroup 的指针到 _groups 中），赋值给 thread local 变量 `tls_task_group`
1. 执行该 TaskGroup 的主循环（`TaskGroup::run_main_task()`）



注意==这里 worker_thread() 函数是在 pthread 中执行的，创建的私有 TaskGroup 保存到了 thread local 变量 `tls_task_group` 中==。
```cpp
// file: task_control.cpp

void* TaskControl::worker_thread(void* arg) {
    run_worker_startfn();
    
    TaskControl* c = static_cast<TaskControl*>(arg);
    TaskGroup* g = c->create_group();
    TaskStatistics stat;
    if (NULL == g) {
        LOG(ERROR) << "Fail to create TaskGroup in pthread=" << pthread_self();
        return NULL;
    }

    // 新创建的 TaskGroup 保存到 thread local 变量中
    tls_task_group = g;
    c->_nworkers << 1;
   	// 开始 worker 的主循环
    g->run_main_task();

    // 到这里说明该 TaskGroup 已经结束了
    stat = g->main_stat();
    tls_task_group = NULL;
    g->destroy_self();
    c->_nworkers << -1;
    return NULL;
}
```
### TaskControl 定义
下面截取了部分定义
```cpp
// Control all task groups
class TaskControl {
    
private:
    butil::atomic<size_t> _ngroup;
    TaskGroup** _groups;
    butil::Mutex _modify_group_mutex;

    bool _stop;
    butil::atomic<int> _concurrency;
    std::vector<pthread_t> _workers;
    
    static const int PARKING_LOT_NUM = 4;
    ParkingLot _pl[PARKING_LOT_NUM];
};
```

- **_groups**：保存了 TaskControl 中所有的 TaskGroup 的指针，`bthread::start_from_non_worker()` 中随机选取的 TaskGroup 就是从这里拿的，在创建 TaskGroup（`TaskControl::create_group()`）会把新创建的 TaskGroup 加到其中。
- **_workers**：pthread 线程标识符的数组，表示创建了多少个 pthread worker 线程，每个 pthread worker 线程应拥有一个线程私有的 TaskGroup 对象
- **_pl**：ParkingLot 类型的数组，ParkingLot 对象用于 bthread 任务的等待通知。
## TaskGroup
### TaskGroup 定义
每一个 TaskGroup 对象是系统线程 pthread 的线程私有对象，它内部包含有任务队列，并控制 pthread 如何执行任务队列中的众多 bthread 任务，TaskGroup 中主要的成员有：
```cpp
class TaskGroup {
private:
    TaskMeta* _cur_meta;
    
    // the control that this group belongs to
    TaskControl* _control;
    int _num_nosignal;
    int _nsignaled;
    
    // ... ...
    
    RemainedFn _last_context_remained;
    void* _last_context_remained_arg;
    
    ParkingLot* _pl;
#ifndef BTHREAD_DONT_SAVE_PARKING_STATE
    ParkingLot::State _last_pl_state;
#endif
    
	size_t _steal_seed;
    size_t _steal_offset;
    
    ContextualStack* _main_stack;
    bthread_t _main_tid;
    
    WorkStealingQueue<bthread_t> _rq;
    RemoteTaskQueue _remote_rq;
    
    int _remote_num_nosignal;
    int _remote_nsignaled;
}
```

- **_cur_meta：** 该 TaskGroup 当前正在执行的任务，在 bthread 切换时会重新赋值。
- **_last_context_remained**：在 task_runner 中 执行用户函数前会先执行该函数，用于切出 bthread 重新入队等操作。
- **_main_stack** 和 **_main_tid**：一个 pthread 会在 `TaskGroup::run_main_task()` 中执行 while 死循环，不断获取并执行 bthread 任务，一个 pthread 的执行流不是永远在 bthread 中，比如等待任务时，pthread 没有执行任何 bthread，执行流就是直接在 pthread 上。==可以将 pthread 在 “等待 bthread - 获取到bthread - 进入 bthread 执行任务函数之前” 这个过程也抽象成一个 bthread，称作一个 pthread 的 “调度bthread” 或者 “主 bthread”，它的 tid 和私有栈就是 _main_tid 和 _main_stack==。
- **_rq**：pthread 1 在执行从自己私有的 TaskGroup中 取出的 bthread 1 时，==如果 bthread 1 执行过程中又创建了新的 bthread 2==，则 bthread 1 将 bthread 2 的 tid 压入 pthread 1 的 TaskGroup 的 _rq 队列中（`TaskGroup::ready_to_run()`）
- **_remote_rq**：bthread 外部即 ==pthread 中开启一个 bthread，随机选取一个 TaskGroup 的 _remote_rq 队列放入其中==（`TaskGroup::ready_to_run_remote()`）。
### TaskGroup::init()
在 `TaskControl::worker_thread()` 中，会调用 `TaskControl::create_group()` 创建一个 TaskGroup，然后使用 `init()` 初始化。
```cpp
// file: task_group.cpp

int TaskGroup::init(size_t runqueue_capacity) {
    if (_rq.init(runqueue_capacity) != 0) {
        LOG(FATAL) << "Fail to init _rq";
        return -1;
    }
    if (_remote_rq.init(runqueue_capacity / 2) != 0) {
        LOG(FATAL) << "Fail to init _remote_rq";
        return -1;
    }
    // TaskGroup 主循环也可以看作是一个 bthread，其栈类型是 STACK_TYPE_MAIN
    ContextualStack* stk = get_stack(STACK_TYPE_MAIN, NULL);
    if (NULL == stk) {
        LOG(FATAL) << "Fail to get main stack container";
        return -1;
    }
    // TaskGroup 主循环的 TaskMeta
    butil::ResourceId<TaskMeta> slot;
    TaskMeta* m = butil::get_resource<TaskMeta>(&slot);
    if (NULL == m) {
        LOG(FATAL) << "Fail to get TaskMeta";
        return -1;
    }
    m->stop = false;
    m->interrupted = false;
    m->about_to_quit = false;
    m->fn = NULL;
    m->arg = NULL;
    m->local_storage = LOCAL_STORAGE_INIT;
    m->cpuwide_start_ns = butil::cpuwide_time_ns();
    m->stat = EMPTY_STAT;
    m->attr = BTHREAD_ATTR_TASKGROUP;
    m->tid = make_tid(*m->version_butex, slot);
    m->set_stack(stk);

    _cur_meta = m;
    _main_tid = m->tid;
    _main_stack = stk;
    _last_run_ns = butil::cpuwide_time_ns();
    return 0;
}
```
TaskGroup 也是一个特殊的 bthread，其栈类型是 `STACK_TYPE_MAIN` ，没有入口函数（`get_stack()` 对于该中类型的栈并不会实际申请内存空间，只是返回一个空对象）。


TaskGroup 初始化完成后，其 `_main_stack` 就是这个特殊的栈，`_cur_meta` 是一个特殊的 TaskMeta，其任务主函数是 `NULL`。


> **Tips**:
> 理解 TaskGroup 也是一个特殊的 bthread 很关键，后面 bthread 栈切换时对于 bthread 之间的切换和从 TaskGroup 主循环中执行任务是同样的逻辑。

### TaskGroup::run_main_task()
```cpp
void TaskGroup::run_main_task() {
    TaskGroup* dummy = this;
    bthread_t tid;
    while (wait_task(&tid)) { // 等待一个任务
        // 切换到新的 bthread 栈，即开始执行新的 bthread 的代码
        TaskGroup::sched_to(&dummy, tid);
        // bthread 执行完，回到当前 pthread 栈
        DCHECK_EQ(this, dummy);
        DCHECK_EQ(_cur_meta->stack, _main_stack);
        // 这里有些疑问，尚不确定何种情景下会执行下面这段代码。
        if (_cur_meta->tid != _main_tid) {
            TaskGroup::task_runner(1/*skip remained*/);
        }
        if (FLAGS_show_per_worker_usage_in_vars && !usage_bvar) {
            char name[32];
        }
    }
}
```
worker(pthread) 在 `TaskGroup::run_main_task()` 上开启无限循环等待任务（`TaskGroup::wait_task()`），如果能拿到任务，就切换到 bthread（`TaskGroup::sched_to()` ）并开始执行 bthread 的代码。


> **Tips**:
> 注意这里 `sched_to()` 函数的第一个参数类型是 `TaskGroup**`，原因是这个 bthread 可能被 steal 到其他的 worker 上了，等到执行完返回的时候，TaskGroup 已经不是当前对象了，因此需要重置 TaskGroup 指针。



三个关键函数：`wait_task()`、`sched_to()`、`task_runner()`：

- **wait_task()**：等待一个任务，如果没有任务会挂起当前 pthread，其中会涉及任务窃取（work stealing）。
- **sched_to()**：进行栈、寄存器等运行时上下文的切换，为接下来运行的任务恢复其上下文。
- **task_runner()**：一个 bthread 被执行时，pthread 将执行 `TaskGroup::task_runner()`，在这个函数中会去执行 TaskMeta 对象的 `fn()`，即应用程序设置的 bthread 任务函数

下面将详细分析这 3 个函数。
## TaskMeta
TaskMeta 保存了一些任务信息，下面截取了部分重要的 field，包括入口函数 `fn`、栈信息 `stack` 等。
```cpp
struct TaskMeta {
    // [Not Reset]
    // butex 使用
    butil::atomic<ButexWaiter*> current_waiter;
    uint64_t current_sleep;
    
    // The thread is interrupted and should wake up from some blocking ops.
    bool interrupted;
    
    // The identifier. It does not have to be here, however many code is
    // simplified if they can get tid from TaskMeta.
    bthread_t tid;

    // User function and argument
    void* (*fn)(void*);
    void* arg;

    // Stack of this task.
    ContextualStack* stack;

    // Attributes creating this task
    bthread_attr_t attr;
    
    // Statistics
    int64_t cpuwide_start_ns;
    TaskStatistics stat;

    // bthread local storage, sync with tls_bls (defined in task_group.cpp)
    // when the bthread is created or destroyed.
    // DO NOT use this field directly, use tls_bls instead.
    LocalStorage local_storage;
}
```
# Work Stealing (TaskGroup::wait_task())
## TaskGroup::wait_task()
`TaskGroup::wait_task()` 死循环等待 `_last_pl_state` 条件，然后执行工作窃取，直到成功拿到一个任务。

```cpp
bool TaskGroup::wait_task(bthread_t* tid) {
    do {
        if (_last_pl_state.stopped()) {
            return false;
        }
        // 等待 _last_pl_state 条件
        _pl->wait(_last_pl_state);
        // 工作窃取
        if (steal_task(tid)) {
            return true;
        }
    } while (true);
}
```
> **Tips**:
> 关于 `ParkingLot` 和 `ParkingLot::State` 后面再详细分析。

### TaskGroup::steal_task()
`steal_task()` 首先从当前 TaskGroup 的 `_remote_rq` 取任务，如果没有，再调用 `TaskControl::steal_task()` 从其他 TaskGroup 窃取任务。

```cpp
    bool steal_task(bthread_t* tid) {
        if (_remote_rq.pop(tid)) {
            return true;
        }
#ifndef BTHREAD_DONT_SAVE_PARKING_STATE
        _last_pl_state = _pl->get_state();
#endif
        return _control->steal_task(tid, &_steal_seed, _steal_offset);
    }
```
### TaskControl::steal_task()
全局工作窃取（`TaskControl::steal_task()`）就是随机选取一个 TaskGroup ，然后先从它的 `_rq` 队列中窃取任务，如果没有再从 `_remote_rq` 中窃取任务。
```cpp
bool TaskControl::steal_task(bthread_t* tid, size_t* seed, size_t offset) {
    // 1: Acquiring fence is paired with releasing fence in _add_group to
    // avoid accessing uninitialized slot of _groups.
    const size_t ngroup = _ngroup.load(butil::memory_order_acquire/*1*/);
    if (0 == ngroup) {
        return false;
    }

    // NOTE: Don't return inside `for' iteration since we need to update |seed|
    bool stolen = false;
    size_t s = *seed;
    for (size_t i = 0; i < ngroup; ++i, s += offset) {
        TaskGroup* g = _groups[s % ngroup];
        // g is possibly NULL because of concurrent _destroy_group
        if (g) {
            if (g->_rq.steal(tid)) {
                stolen = true;
                break;
            }
            if (g->_remote_rq.pop(tid)) {
                stolen = true;
                break;
            }
        }
    }
    *seed = s;
    return stolen;
}
```
看到这里，大家可能很疑惑，TaskGroup 的主函数 `run_main_task()` 取任务的顺序是：

1. 当前 `TaskGroup` 的 `_remote_rq` 
1. 其他 `TaskGroup` 的 `_rq` 
1. 其他 `TaskGroup` 的 `_remote_rq`

那当前 TaskGroup 的 `_rq` 是什么时候被消费的呢？答案就是 `TaskGroup::ending_sched()` 中。
# 栈切换 (TaskGroup::sched_to())
首先根据 `next_tid` 找到对应的 TaskMeta (`next_meta`)，==如果 `next_meta` 的 stack 是 NULL（即该任务是一个还没有被执行过的新任务，因此也还没有分配栈，对于执行过程中被切换出去的任务，stack 肯定不是 NULL 了）， 就使用 `get_stack()` 分配一个新的栈内存空间给这个 TaskMeta==；然后调用一个重载的 `sched_to()` ，重载的 `sched_to()` 中会调用 `jump_stack()` 实现栈切换。


> `get_stack()` 的第二个参数即该 bthread 的入口函数 `TaskGroup::task_runner()`，在 task_runner 中会真正调用用户的任务函数 `fn`。

```cpp
inline void TaskGroup::sched_to(TaskGroup** pg, bthread_t next_tid) {
    TaskMeta* next_meta = address_meta(next_tid);
    if (next_meta->stack == NULL) {
        ContextualStack* stk = get_stack(next_meta->stack_type(), task_runner);
        if (stk) {
            next_meta->set_stack(stk);
        } else {
            // stack_type is BTHREAD_STACKTYPE_PTHREAD or out of memory,
            // In latter case, attr is forced to be BTHREAD_STACKTYPE_PTHREAD.
            // This basically means that if we can't allocate stack, run
            // the task in pthread directly.
            next_meta->attr.stack_type = BTHREAD_STACKTYPE_PTHREAD;
            next_meta->set_stack((*pg)->_main_stack);
        }
    }
    // Update now_ns only when wait_task did yield.
    sched_to(pg, next_meta);
}
```
> **Tips**:
> `get_stack()` 和 stack 相关的逻辑，后面再详细分析。

```cpp
void TaskGroup::sched_to(TaskGroup** pg, TaskMeta* next_meta) {
    TaskGroup* g = *pg;
    
    // Save errno so that errno is bthread-specific.
    const int saved_errno = errno;
    void* saved_unique_user_ptr = tls_unique_user_ptr;

    // 获取当前(切换前) bthread 的 TaskMeta
    TaskMeta* const cur_meta = g->_cur_meta;
    const int64_t now = butil::cpuwide_time_ns();
    const int64_t elp_ns = now - g->_last_run_ns;
    g->_last_run_ns = now;
    cur_meta->stat.cputime_ns += elp_ns;
    if (cur_meta->tid != g->main_tid()) {
        // 如果一个 bthread 在执行过程中生成了新的 bthread，会走到这里。
        g->_cumulated_cputime_ns += elp_ns;
    }
    ++cur_meta->stat.nswitch;
    ++ g->_nswitch;
    // Switch to the task
    if (__builtin_expect(next_meta != cur_meta, 1)) {
        // 将 _cur_meta 指向下一个将要执行的 bthread 的 TaskMeta 对象的指针
        g->_cur_meta = next_meta;
        // Switch tls_bls
        // tls_bls 存储的是当前 bthread 的一些运行期数据（统计量等），执行切换动作前，将 tls_bls 的内容复制到
        // 当前 bthread 的私有 storage 空间中，再将 tls_bls 重新指向将要执行的 bthread 的私有 storage
        cur_meta->local_storage = tls_bls;
        tls_bls = next_meta->local_storage;

        if (cur_meta->stack != NULL) {
            if (next_meta->stack != cur_meta->stack) {
                // 这里真正执行 bthread 的切换。
                // 将执行 pthread 的 cpu 的寄存器的当前状态存入 cur_meta 的 context 中，并将 next_meta 的 context 中
                // 的数据加载到 cpu 的寄存器中，开始执行 next_meta 的任务函数
                jump_stack(cur_meta->stack, next_meta->stack);
                // probably went to another group, need to assign g again.
                // 这里是 cur_meta 代表的 bthread 的恢复执行点
                // bthread 恢复执行的时候可能被 steal 到其他 pthread 上了，需要重置 TaskGroup 对象的指针 g
                g = tls_task_group;
            }
        }
        // else because of ending_sched(including pthread_task->pthread_task)
    } else {
        LOG(FATAL) << "bthread=" << g->current_tid() << " sched_to itself!";
    }
    
    while (g->_last_context_remained) {
        RemainedFn fn = g->_last_context_remained;
        g->_last_context_remained = NULL;
        fn(g->_last_context_remained_arg);
        g = tls_task_group;
    }

    // Restore errno
    errno = saved_errno;
    tls_unique_user_ptr = saved_unique_user_ptr;

    // 把当前线程 TaskGroup 赋值给 pg
    *pg = g;
}
```
`tls_bls` 表示的是 TaskMeta（bthread）内的局部存储，需要先做还原，并且赋值成下一个 TaskMeta 的局部存储。
```cpp
cur_meta->local_storage = tls_bls;
tls_bls = next_meta->local_storage;
```
`tls_bls` 定义为 TaskMeta 的 thread local 变量。 
```cpp
// Sync with TaskMeta::local_storage when a bthread is created or destroyed.
// During running, the two fields may be inconsistent, use tls_bls as the
// groundtruth.
thread_local LocalStorage tls_bls = BTHREAD_LOCAL_STORAGE_INITIALIZER;
```
## jump_stack()
`jump_stack()` 是汇编实现的栈跳转：
```cpp
inline void jump_stack(ContextualStack* from, ContextualStack* to) {
    bthread_jump_fcontext(&from->context, to->context, 0/*not skip remained*/);
}
```
在进入 `jump_stack()` 函数后，实际上就会跳转到要执行的任务了，等到任务执行完成或者主动切换出来的时候，该函数才会返回。
关于栈的创建和切换，会用单独一篇文章来讲，这里就不做详细分析了。


> **Tips**:
> 注意在 `jump_stack()` 返回后，下一步是 `g = tls_task_group` 把 TaskGroup 指针重新赋值为当前线程的 TaskGroup 指针，注释说明是 "probably went to another group, need to assign g again."。在 `jump_stack()` 中保存的返回点是其下一行代码的位置，但是 bthread 在执行过程中可能主动让出 CPU（yield/sleep/bmutex），然后被重新加到队列中，等到再次被调度的时候可能是在其他的 worker 中被执行，最终返回后，TaskGroup 指针需要更新。

# 执行任务 (TaskGroup::task_runner())
`TaskGroup::task_runner()` 的主要逻辑如下（省略了一些无关的代码），一直循环执行下面的步骤，直到 `g->_cur_meta->tid != g->_main_tid`：

1. 再次拿一次当前 pthread 的 TaskGroup（`tls_task_group`）
1. 拿到当前 TaskGroup 的 TaskMeta
1. 执行回调函数（`m->fn(m->arg)`），在任务函数中可能 yield/sleep 让出 cpu，也可能产生新的 bthread
1. 再次拿当前 pthread 的 TaskGroup (`tls_task_group`)，因为 bthread 可能被调度到其他 TaskGroup 了。
1. Increase the version and wake up all joiners （`butex_wake_except()`）
1. 查找下一个任务，并切换到其对应的运行时上下文（`ending_sched(&g)`）
```cpp
void TaskGroup::task_runner(intptr_t skip_remained) {
    // NOTE: tls_task_group is volatile since tasks are moved around
    //       different groups.
    TaskGroup* g = tls_task_group;
    
    // 这里的 _last_context_remained 可能是切出 bthread 重新入队或其他操作
    if (!skip_remained) {
        while (g->_last_context_remained) {
            RemainedFn fn = g->_last_context_remained;
            g->_last_context_remained = NULL;
            fn(g->_last_context_remained_arg);
            g = tls_task_group;
        }
    }
    
    do {
        // A task can be stopped before it gets running, in which case
        // we may skip user function, but that may confuse user:
        // Most tasks have variables to remember running result of the task,
        // which is often initialized to values indicating success. If an
        // user function is never called, the variables will be unchanged
        // however they'd better reflect failures because the task is stopped
        // abnormally.

        // Meta and identifier of the task is persistent in this run.
        TaskMeta* const m = g->_cur_meta;

        // Not catch exceptions except ExitException which is for implementing
        // bthread_exit(). User code is intended to crash when an exception is
        // not caught explicitly. This is consistent with other threading
        // libraries.
        void* thread_return;
        try {
            // 执行应用程序设置的任务函数，在任务函数中可能 yield 让出 cpu，也可能产生新的 bthread
            thread_return = m->fn(m->arg);
        } catch (ExitException& e) {
            thread_return = e.value();
        }

        // Group is probably changed
        g = tls_task_group;

        // TODO: Save thread_return
        (void)thread_return;

        // Clean tls variables, must be done before changing version_butex
        // otherwise another thread just joined this thread may not see side
        // effects of destructing tls variables.
        KeyTable* kt = tls_bls.keytable;
        if (kt != NULL) {
            return_keytable(m->attr.keytable_pool, kt);
            // After deletion: tls may be set during deletion.
            tls_bls.keytable = NULL;
            m->local_storage.keytable = NULL; // optional
        }

        // Increase the version and wake up all joiners, if resulting version
        // is 0, change it to 1 to make bthread_t never be 0. Any access
        // or join to the bthread after changing version will be rejected.
        // The spinlock is for visibility of TaskGroup::get_attr.
        {
            BAIDU_SCOPED_LOCK(m->version_lock);
            if (0 == ++*m->version_butex) {
                ++*m->version_butex;
            }
        }
        // 任务函数执行完成后，需要唤起等待该任务函数执行结束的 pthread/bthread
        butex_wake_except(m->version_butex, 0);

        g->_control->_nbthreads << -1;
        g->set_remained(TaskGroup::_release_last_context, m);
        // 将 pthread 线程执行流转入下一个可执行的 bthread（普通 bthread 或 pthread 的调度 bthread）
        ending_sched(&g);

    } while (g->_cur_meta->tid != g->_main_tid);

    // Was called from a pthread and we don't have BTHREAD_STACKTYPE_PTHREAD
    // tasks to run, quit for more tasks.
}
```
## _last_context_remained 回调
_last_context_remained 是 TaskGroup 的一个成员变量，由 `TaskGroup::set_remained()` 设置：
```cpp
    // The callback will be run in the beginning of next-run bthread.
    // Can't be called by current bthread directly because it often needs
    // the target to be suspended already.
    typedef void (*RemainedFn)(void*);
    void set_remained(RemainedFn cb, void* arg) {
        _last_context_remained = cb;
        _last_context_remained_arg = arg;
```
其应用场景：

1. `task_runner()` 执行完任务后做清理工作（`TaskGroup::_release_last_context`）
1. `start_foreground()`
1. `sleep()` 中添加回调（`_add_sleep_event`）
1. `yield()` 中把当前 bthread 重新添加回队列（`ready_to_run_in_worker()`）
1. `exchange()`
1. `butex_wait()`



sleep、yield 和 butex_wait 的场景将在后面专门的章节中介绍。
```cpp
void TaskGroup::_release_last_context(void* arg) {
    TaskMeta* m = static_cast<TaskMeta*>(arg);
    if (m->stack_type() != STACK_TYPE_PTHREAD) {
        return_stack(m->release_stack()/*may be NULL*/);
    } else {
        // it's _main_stack, don't return.
        m->set_stack(NULL);
    }
    return_resource(get_slot(m->tid));
}
```
## TaskGroup::ending_sched()
在 `TaskGroup::ending_sched()` 中也会选取任务并执行，其顺序是：

1. 当前 TaskGroup 的 \_rq
1. 当前 TaskGroup 的 \_remote_rq （从这里开始就是上面提到的 `TaskGroup::steal_task()` 的逻辑）
1. 其他 TaskGroup 的 \_rq
1. 其他 TaskGroup 的 \_remote_rq



- 如果都找不到任务，则设置 `_cur_meta` 为 `_main_tid` ，也就是让 `TaskGroup::task_runner()` 的循环终止。然后就会回到 `TaskGroup::run_main_task()` 的主循环，继续 `TaskGRoup::wait_task()` 等待新任务了。
- 如果找到了任务，就执行栈切换（`sched_to(pg, next_meta)`）并继续循环执行任务，注意这里调用的是重载后的 `sched_to()`，在调用前需要初始化下一个任务的栈（`next_meta->set_stack()`）
```cpp
void TaskGroup::ending_sched(TaskGroup** pg) {
    TaskGroup* g = *pg;
    bthread_t next_tid = 0;
    // Find next task to run, if none, switch to idle thread of the group.
#ifndef BTHREAD_FAIR_WSQ
    // When BTHREAD_FAIR_WSQ is defined, profiling shows that cpu cost of
    // WSQ::steal() in example/multi_threaded_echo_c++ changes from 1.9%
    // to 2.9%
    const bool popped = g->_rq.pop(&next_tid);
#else
    const bool popped = g->_rq.steal(&next_tid);
#endif
    if (!popped && !g->steal_task(&next_tid)) {
        // Jump to main task if there's no task to run.
        next_tid = g->_main_tid;
    }

    TaskMeta* const cur_meta = g->_cur_meta;
    TaskMeta* next_meta = address_meta(next_tid);
    if (next_meta->stack == NULL) {
        if (next_meta->stack_type() == cur_meta->stack_type()) {
            // also works with pthread_task scheduling to pthread_task, the
            // transfered stack is just _main_stack.
            next_meta->set_stack(cur_meta->release_stack());
        } else {
            ContextualStack* stk = get_stack(next_meta->stack_type(), task_runner);
            if (stk) {
                next_meta->set_stack(stk);
            } else {
                // stack_type is BTHREAD_STACKTYPE_PTHREAD or out of memory,
                // In latter case, attr is forced to be BTHREAD_STACKTYPE_PTHREAD.
                // This basically means that if we can't allocate stack, run
                // the task in pthread directly.
                next_meta->attr.stack_type = BTHREAD_STACKTYPE_PTHREAD;
                next_meta->set_stack(g->_main_stack);
            }
        }
    }
    sched_to(pg, next_meta);
}
```
# Summary
从 `bthread_start_background()` 入手，我们了解了 bthread 的三个重要组件 **TaskControl**、**TaskGroup** 和 **TaskMeta**，以及 bthread 的**任务窃取**、**栈切换**和**任务执行**流程。总结一下就是：

1. TaskControl 全局唯一
2. TaskGroup 即 bthread worker，一个 bthread worker 即一个 pthread
1. TaskGroup 创建成功后就死循环等待任务并执行
   1. 任务等待涉及到任务窃取
   1. 等到任务后就进行栈切换并执行任务（使用汇编完成）
   1. 执行完窃取的任务后会继续执行本地任务和窃取任务（while）
4. 如果一个 TaskMeta 是第一次执行，那么它的 stack 是 NULL，需要分配一个 stack（`get_stack()`）
   1. ending_sched() 中继续执行下一个 TaskMeta 的时候，有复用 _main_stack 的逻辑
5. ==**TaskGroup 中两个队列区别**==：
   1. _rq（WorkStealingQueue）：==bthread 创建的任务会加到 bthread 所属的 worker 的这个 _rq 队列中，优先级较高（任务执行时优先被消费）==。因此该队列的 push 和 pop 操作永远只会有一个线程在调用，不会有并发，但是 steal 是其他 worker 调用的，会和 push 以及 pop 之间有并发。
   1. _remote_rq（RemoteTaskQueue）：==pthread 中创建的任务（外部创建的）会随机加到一个 TaskGroup 的 _remote_rq 中，优先级较低（每个 worker 是先执行完 _rq 再执行 _remote_rq）==
6. ==**唤醒后任务窃取的顺序**==（没有就找下一个，直到找到一个就完成窃取，不是把所有的队列都取完）：
   1. 当前 TaskGroup 的 _remote_rq
   1. 其他 TaskGroup  的 _rq （由 TaskControl 随机选取）
   1. 其他 TaskGroup 的 _remote_rq
7. ==**执行完窃取的任务后继续执行任务的顺序**==（一直从这些队列取任务执行，==直到所有队列都没有任务后就 wait 休眠==**）**：
   1. 当前 TaskGroup 的 \_rq
   1. 当前 TaskGroup 的 \_remote_rq
   1. 其他 TaskGroup 的 \_rq （由 TaskControl 随机选取）
   1. 其他 TaskGroup 的 \_remote_rq
8. ==**为什么唤醒后是先取当前 TaskGroup 的 \_remote_rq？**==因为只有在当前 worker 中的 bthread 新建的 bthread 才会加到 \_rq 中，worker 进入休眠意味着当前 TaskGroup 的 \_rq 没有任务了，并且其他 TaskGroup 也都没任务可以取了；被唤醒的情况是在外部 pthread 中新建了 bthread，这个新建的 bthread 任务会被随机加到一个 TaskGroup 的 \_remote_rq 中，因此 worker 被唤醒后应该直接从 \_remote_rq 中取任务。
9. bthread worker 流程图

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1627287239983-c45ecf22-4b19-430b-b0d1-736a487523db.png" alt="bthread.png" style="zoom:50%;" />

10. TaskControl、TaskGroup、TaskMeta 关系图解

    <img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220510011557138.png" alt="image-20220510011557138" style="zoom:50%;" />

# Links

1. BRPC的精华全在bthread上啦（一）：Work Stealing以及任务的执行与切换：[https://zhuanlan.zhihu.com/p/294129746](https://zhuanlan.zhihu.com/p/294129746)
1. 多核环境下pthread调度执行bthread的过程：[https://www.tqwba.com/x_d/jishu/220699.html](https://www.tqwba.com/x_d/jishu/220699.html)
1. brpc源码学习（四）- bthread调度执行总体流程：[https://blog.csdn.net/KIDGIN7439/article/details/107837530](https://blog.csdn.net/KIDGIN7439/article/details/107837530)
