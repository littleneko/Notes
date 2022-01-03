在上篇文章中讲章切换（ `TaskGroup::sched_to()` ）的时候，该函数取到下一个任务（TaskMeta）后，如果下一个任务的 stack 为空（即第一次执行），就为它分配一个栈（`get_stack()`）。
```cpp
// file: task_group_inl.h

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


另外，在 `TaskGroup::ending_sched()` 中，找到下一个执行的任务后，如果其栈为空，也需要初始化栈 `get_stack()` ：
```cpp
// file: task_group.cpp

void TaskGroup::ending_sched(TaskGroup** pg) {
    // 此处省略一万行
    
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
```


除此之外，在 `TaskGroup::init()` 中，也会调用 `get_stack()` ：
（调用关系：`TaskControl::worker_thread()` -> `TaskControl::create_group()` -> `TaskGroup::init()` ）
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
    ContextualStack* stk = get_stack(STACK_TYPE_MAIN, NULL);
    if (NULL == stk) {
        LOG(FATAL) << "Fail to get main stack container";
        return -1;
    }
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
不过这里调用参数和之前两处不一样，第一个参数栈类型是 `STACK_TYPE_MAIN`，第二个参数入口函数是 `NULL` ，这个 stk 最终赋值给了 `TaskGroup::_main_stack` ，这个栈就是 `TaskGroup::run_main_task()` 的栈，实际上就是 pthread 栈，并没有真的分配空间。


整个 bthread 代码中涉及到 `get_stack()` 的位置一共就这 3 处，其中前 2 个是一类，第 3 处调用是另一类。
# get_stack()
```cpp
// file: stack_inl.h

inline ContextualStack* get_stack(StackType type, void (*entry)(intptr_t)) {
    switch (type) {
    case STACK_TYPE_PTHREAD:
        return NULL;
    case STACK_TYPE_SMALL:
        return StackFactory<SmallStackClass>::get_stack(entry);
    case STACK_TYPE_NORMAL:
        return StackFactory<NormalStackClass>::get_stack(entry);
    case STACK_TYPE_LARGE:
        return StackFactory<LargeStackClass>::get_stack(entry);
    case STACK_TYPE_MAIN:
        return StackFactory<MainStackClass>::get_stack(entry);
    }
    return NULL;
}
```
根据栈类型的不同，分别调用了不同的工厂函数去做 `get_stack()` ，这里的工厂类可以分为 2 种类型，`SmallStackClass` 、`NormalStackClass` 、`LargeStackClass` 都是使用的通用模板工厂类，`MainStackClass` 使用了特化的模板工厂类（`TaskGroup::init()` 中就是调用的该模板）。
## StackFactory 通用模板
```cpp
// file: stack_inl.h

template <typename StackClass> struct StackFactory {
    struct Wrapper : public ContextualStack {
        explicit Wrapper(void (*entry)(intptr_t)) {
            if (allocate_stack_storage(&storage, *StackClass::stack_size_flag,
                                       FLAGS_guard_page_size) != 0) {
                storage.zeroize();
                context = NULL;
                return;
            }
            context = bthread_make_fcontext(storage.bottom, storage.stacksize, entry);
            stacktype = (StackType)StackClass::stacktype;
        }
        ~Wrapper() {
            if (context) {
                context = NULL;
                deallocate_stack_storage(&storage);
                storage.zeroize();
            }
        }
    };
    
    static ContextualStack* get_stack(void (*entry)(intptr_t)) {
        return butil::get_object<Wrapper>(entry);
    }
    
    static void return_stack(ContextualStack* sc) {
        butil::return_object(static_cast<Wrapper*>(sc));
    }
};
```
它包含两个成员函数，一是获取栈（`get_statck()`），另外一个是归还栈（`return_stack()`），所谓的获取栈就是创建 `ContextualStack` （子类 `Wrapper`）对象，然后做了初始化，归还栈则是获取栈的逆操作。


另外 `StackFactory` 模板中有一内部类 `Wrapper`，它是 `ContextualStack` 的子类，`StackFactory`成员函数 `get_stack()` 和 `return_stack()` 操作的其实就是 `Wrapper` 类型。


`Wrapper` 的构造函数接收一个参数 entry，entry 的类型是一个函数指针。`void(*entry)(intptr_t)` 表示的是参数类型为 intptr_t，返回值为 void 的函数指针。intptr_t 是和一个机器相关的整数类型，在 64 位机器上对应的是 long，在 32 位机器上对应的是 int。


其实 entry 只有两个值，一种是 `NULL`，另外一个就是 `TaskGroup::task_runner()`：
`void TaskGroup::task_runner(intptr_t skip_remained)`


构造函数内会调用 `allocate_stack_storage()` 分配栈空间，接着是对 storage、context、stacktype 的初始化（这三个是父类 ContextualStack 的成员）。其中 context 的初始化会调用 `bthread_make_fcontext()` 函数。


`Wrapper` 析构的时候会调用 `deallocate_stack_storage()` 释放占空间，并重置三个成员变量


> **关于 **`**butil::get_object()**`** **
> butil 中实现了一个对象池，这里的 Wrapper 对象可能是 new 的，也可能是从对象池中拿到的归还的（ `butil::return_object()` ）的对象，这里用到的是 get_object 一个参数的重载函数，拿到对象后会使用参数 entry 初始化 Wrapper 对象。

## StackFactory 特化模板
```cpp
// file: stack_inl.h

template <> struct StackFactory<MainStackClass> {
    static ContextualStack* get_stack(void (*)(intptr_t)) {
        ContextualStack* s = new (std::nothrow) ContextualStack;
        if (NULL == s) {
            return NULL;
        }
        s->context = NULL;
        s->stacktype = STACK_TYPE_MAIN;
        s->storage.zeroize();
        return s;
    }
    
    static void return_stack(ContextualStack* s) {
        delete s;
    }
};
```
特化模板比较简洁，只是简单地 new 了一个 ContextualStack 对象做了一些初始化操作并返回。
# 栈信息保存（ContextualStack）
```cpp
// file: contex.h
typedef void* bthread_fcontext_t;

// file: stack.h
struct ContextualStack {
    bthread_fcontext_t context; // 上下文信息，在栈初始化和切换时会用到
    StackType stacktype;
    StackStorage storage;
};
```
bthread 中一共定义了 4 种有意义的栈类型：
```cpp
// file: types.h

typedef unsigned bthread_stacktype_t;
static const bthread_stacktype_t BTHREAD_STACKTYPE_UNKNOWN = 0;
static const bthread_stacktype_t BTHREAD_STACKTYPE_PTHREAD = 1;
static const bthread_stacktype_t BTHREAD_STACKTYPE_SMALL = 2;
static const bthread_stacktype_t BTHREAD_STACKTYPE_NORMAL = 3;
static const bthread_stacktype_t BTHREAD_STACKTYPE_LARGE = 4

enum StackType {
    STACK_TYPE_MAIN = 0,
    STACK_TYPE_PTHREAD = BTHREAD_STACKTYPE_PTHREAD,
    STACK_TYPE_SMALL = BTHREAD_STACKTYPE_SMALL,
    STACK_TYPE_NORMAL = BTHREAD_STACKTYPE_NORMAL,
    STACK_TYPE_LARGE = BTHREAD_STACKTYPE_LARGE
};
```
StackStorage 中才是具体表示栈信息的结构
```cpp
// file: types.h

struct StackStorage {
     int stacksize; // stack 有效大小
     int guardsize; // guardpage 的大小，使用mprotect为保护地址空间，用于检测stack_overflow
    // Assume stack grows upwards.
    // http://www.boost.org/doc/libs/1_55_0/libs/context/doc/html/context/stack.html
    void* bottom;	// 栈底指正（高地址端）
    unsigned valgrind_stack_id;

    // Clears all members.
    void zeroize() {
        stacksize = 0;
        guardsize = 0;
        bottom = NULL;
        valgrind_stack_id = 0;
    }
};
```
# 栈内存分配（allocate_stack_storage()）
`allocate_stack_storage()` 声明如下：
```cpp
// file: stack.h

// Allocate a piece of stack.
int allocate_stack_storage(StackStorage* s, int stacksize, int guardsize);
```
其中 stacksize 表示栈大小的，guardsize 表示保护页大小。


在 Wrapper 中，调用如下：
```cpp
allocate_stack_storage(&storage, *StackClass::stack_size_flag, FLAGS_guard_page_size)
```
保护页大小 guardsize 由 gflags 参数定义，默认值是 4096，用于检测 stack_overflow。


栈大小 stacksize 对应三种栈类型中的 `stack_size_flag`，StackClass 即在 `get_stack()` 中根据不同的栈类型传入的 class。三类栈 class 定义如下，注意 `stack_size_flag` 都是定义为 static 的，实际上其是由 gflags 参数初始化的。
```cpp
// file: stack_inl.h
struct MainStackClass {};

struct SmallStackClass {
    static int* stack_size_flag;
    // Older gcc does not allow static const enum, use int instead.
    static const int stacktype = (int)STACK_TYPE_SMALL;
};

struct NormalStackClass {
    static int* stack_size_flag;
    static const int stacktype = (int)STACK_TYPE_NORMAL;
};

struct LargeStackClass {
    static int* stack_size_flag;
    static const int stacktype = (int)STACK_TYPE_LARGE;
};
```
```cpp
// file: stack.cpp
int* SmallStackClass::stack_size_flag = &FLAGS_stack_size_small;
int* NormalStackClass::stack_size_flag = &FLAGS_stack_size_normal;
int* LargeStackClass::stack_size_flag = &FLAGS_stack_size_large;

// file: stack.cpp
DEFINE_int32(stack_size_small, 32768, "size of small stacks");
DEFINE_int32(stack_size_normal, 1048576, "size of normal stacks");
DEFINE_int32(stack_size_large, 8388608, "size of large stacks");
```


我们正式进入 `allocate_stack_storage()` 函数：
```cpp
int allocate_stack_storage(StackStorage* s, int stacksize_in, int guardsize_in) {
    const static int PAGESIZE = getpagesize();
    const int PAGESIZE_M1 = PAGESIZE - 1;
    const int MIN_STACKSIZE = PAGESIZE * 2;
    const int MIN_GUARDSIZE = PAGESIZE;

    // Align stacksize
    const int stacksize =
        (std::max(stacksize_in, MIN_STACKSIZE) + PAGESIZE_M1) &
        ~PAGESIZE_M1;
```
`getpagesize()` 调用的系统函数获取系统页大小（Return the number of bytes in a page.  This is the system's page size,   which is not necessarily the same as the hardware page size.），在 x86 linux 上其值为 4096。


接着对传入的 `stacksize_in` 按上一步获取的页大小对齐（向上取整，实际上限制了最小值为 PAGESIZE * 2），得到实际的栈大小 stacksize。（可以看到三个栈大小的默认值都是 4096 的整数倍，实际上 stacksize_in 已经是对齐的了）。


> **Tips：**
> 整数 x 对 align_no ( = 2^N ) 取于和取整可以使用位操作完成
> - 取余：`x & (align_no - 1)`
> - 取整：`x & ~(align_no - 1)`



```cpp
        // Align guardsize
        const int guardsize =
            (std::max(guardsize_in, MIN_GUARDSIZE) + PAGESIZE_M1) &
            ~PAGESIZE_M1;
```
接下来我们忽略 guardsize_in <= 0 的情况，直接看 >0 时候的逻辑，对 guardsize_in 也进行了对齐。


```c++
        const int memsize = stacksize + guardsize;
        void* const mem = mmap(NULL, memsize, (PROT_READ | PROT_WRITE),
                               (MAP_PRIVATE | MAP_ANONYMOUS), -1, 0);

        if (MAP_FAILED == mem) {
            PLOG_EVERY_SECOND(ERROR) 
                << "Fail to mmap size=" << memsize << " stack_count="
                << s_stack_count.load(butil::memory_order_relaxed)
                << ", possibly limited by /proc/sys/vm/max_map_count";
            // may fail due to limit of max_map_count (65536 in default)
            return -1;
        }
```
然后使用 mmap 分配了一块内存，==大小 memsize 是 stacksize + guardsize==。因为 mmap 的大小 memsize 必须是 pagesize 的整数倍，所以前面需要把传入的 stacksize_in 和 guardsize_in 按 pagesize 大小对齐。


```c++
        void* aligned_mem = (void*)(((intptr_t)mem + PAGESIZE_M1) & ~PAGESIZE_M1);
        if (aligned_mem != mem) {
            LOG_ONCE(ERROR) << "addr=" << mem << " returned by mmap is not "
                "aligned by pagesize=" << PAGESIZE;
        }
```
对 mmap 返回的内存地址也判断一下是否是按 pagesize 大小对齐的。


```cpp
        const int offset = (char*)aligned_mem - (char*)mem;
        if (guardsize <= offset ||
            mprotect(aligned_mem, guardsize - offset, PROT_NONE) != 0) {
            munmap(mem, memsize);
            PLOG_EVERY_SECOND(ERROR) 
                << "Fail to mprotect " << (void*)aligned_mem << " length="
                << guardsize - offset; 
            return -1;
        }
```
当 mmap 返回的内存地址 mem 没和 pagesize 对齐的时候，对齐后的地址 aligned_mem 与 mem 的差值 offset 会大于 0（这里一定是 aligned_mem 大于 mem，因为对齐是向上取整的）。

- 如果 offset 大于保护页的大小，直接返回 -1。
- 如果 offset 小于保护页的大小（包括等于 0 的情况，即 mem 是按 pagesize 对齐的），就调用 mprotect() 把多余的字节（guardsize - offset）设置成不可访问（PROT_NONE）。



```cpp
        s_stack_count.fetch_add(1, butil::memory_order_relaxed);
        s->bottom = (char*)mem + memsize;
        s->stacksize = stacksize;
        s->guardsize = guardsize;
```
记录一下 s_stack_count，给 StackStorage 赋值：

- ==栈底地址==（`StackStorage::bottom`）：==(char*)mem + memsize==，因为 mem 是 mmap 分配的起始地址，这里 bottom 就直接指向分配内存的尾部了（高位）。
- ==栈大小==（`StackStorage::stacksize`）：stacksize
- ==栈保护大小==（`StackStorage::guardsize`）：guardsize



我们假设传入的 stacksize_in 和 guardsize_int 都是也 pagesize 对齐的（实际上正常情况确实是这样），栈大小 memsize =  stacksize_in + guardsize_int，那么唯一需要处理的问题就是 mmap 分配的 mem 地址不是和 pagesize 对齐的情况了，下图表示了最终分配的内存情况（guardsize = 1 * pagesize）

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1627665297930-02f80f10-bf5e-4221-9f1c-1dd39c97103b.png" alt="bthread_allocate_stack_storage.png" style="zoom:50%;" />

# 栈内存初始化（bthread_make_fcontext()）
在上一节中，我们为栈分配了内存，并把栈信息保存到了 `ContextualStack::StackStorage` 中，接下来就要利用这些信息真正初始化栈。
```cpp
context = bthread_make_fcontext(storage.bottom, storage.stacksize, entry);
```
`bthread_make_fcontext()` 作用是创建一个上下文，把 bthread 的入口 entry 函数的地址等信息保存起来，初始化完成的上下文信息保存在 `ContextualStack::bthread_fcontext_t` 中 。通过前文我们知道 entry 只有两种取值，一个是 `NULL`，另外一个就是 `TaskGroup::task_runner()`。

```c++
#if defined(BTHREAD_CONTEXT_PLATFORM_linux_x86_64) && defined(BTHREAD_CONTEXT_COMPILER_gcc)
__asm (
".text\n"
".globl bthread_make_fcontext\n"
".type bthread_make_fcontext,@function\n"
".align 16\n"
"bthread_make_fcontext:\n"
"    movq  %rdi, %rax\n"
"    andq  $-16, %rax\n"
"    leaq  -0x48(%rax), %rax\n"
"    movq  %rdx, 0x38(%rax)\n"
"    stmxcsr  (%rax)\n"
"    fnstcw   0x4(%rax)\n"
"    leaq  finish(%rip), %rcx\n"
"    movq  %rcx, 0x40(%rax)\n"
"    ret \n"
"finish:\n"
"    xorq  %rdi, %rdi\n"
"    call  _exit@PLT\n"
"    hlt\n"
".size bthread_make_fcontext,.-bthread_make_fcontext\n"
".section .note.GNU-stack,\"\",%progbits\n"
".previous\n"
);

#endif
```


**每一条汇编指令解释**：

1. movq	%rdi, %rax：把第 1 个参数（storage.bottom）加载到 %rax 寄存器中
1. andq     $-16, %rax：把 %rax 的值按 16 字节向下对齐（storage.bottom 是栈的最高位，即栈底）
1. leaq  	-0x48(%rax), %rax：把 %rax 的值 减 72
1. movq  	%rdx, 0x38(%rax)：把第 3 个参数（函数入口 entry）写入 %rax + 56 指向的内存位置
1. stmxcsr  	(%rax)：把 MXCSR 的值保存到 %rax 指向的内存位置
1. fnstcw   	0x4(%rax)：把控制寄存器（FPU）的值保存到 %rax + 4 指向的内存位置
1. leaq  	finish(%rip), %rcx：计算 finish 标签的地址存入 %rcx 寄存器中
1. movq  	%rcx, 0x40(%rax)：把 %rcx 的值（即 finish 标签的地址）写入到 %rax + 64 指向的内存位置



**完成后的栈内存空间如下**：

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1628100452150-930d97b5-b4c3-4e1e-8905-e2a945a7b2ff.png" alt="bthread_stack.png" style="zoom:50%;" />

中间空出来的 6 个 8 字节的位置，接下来的 `bthread_jump_fcontext()` 会用到。


**返回值**：
寄存器 `%rax` 用于保存函数的返回值，因此 `bthread_make_fcontext()` 的返回值 context 指针指向了图中 %rax 标识的内存（即 `storage.bottom - 72` 的地址）。
# Summary

- `get_stack()` 有两类调用：`TaskGroup::init()` 初始化时，栈类型为 `STACK_TYPE_MAIN`；切换栈（`TaskGroup::sched_to()`），执行任务（TaskMeta）之前，栈类型从 TaskMeta 中得到
- 栈的初始化通过模板工厂类 StackFactory 实现，一共定义了 4 种栈，SmallStackClass、NormalStackClass、LargeStackClass、MainStackClass，其区别是栈大小不同
- 栈上下文使用 ContextualStack 定义，其中 StackStorage 存储了栈底（bottom），栈大小（stacksize），保护页大小（guardsize）
- 栈内存使用 mmap 分配，需要进行 pagesize 对齐
- `bthread_make_fcontext()` 使用 StackStorage 中保存的栈信息对栈进行初始化
# Links

1. BRPC的精华全在bthread上啦（三）：bthread上下文的创建：[https://zhuanlan.zhihu.com/p/347499412](https://zhuanlan.zhihu.com/p/347499412)
1. bthread源码分析（五）上下文和栈实现：[https://blog.csdn.net/kdb_viewer/article/details/115913962](https://blog.csdn.net/kdb_viewer/article/details/115913962)
