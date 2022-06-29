前面第一篇和第三篇中分别提到了 `bthread_jump_fcontext()` 和 `bthread_make_fcontext()` 函数，两个函数分别实现了栈的切换和创建。协程可以理解为用户态线程，linux 的线程有自己的栈空间，线程间切换由操作系统完成；同理协程也同样需要自己的栈空间，bthread 中使用 _mmap_ 分配的内存作为协程栈（参考上一篇的 `get_stack()` 函数）；不同的是协程的切换需要自己编写代码完成，bthread 中协程的切换和操作系统中进程/线程的上下文切换类似，主要工作都是做一些现场保存以及栈指针变更。
# bthread_jump_fcontext()
我们先来看看该函数的调用关系（截取了关键路径）：
```cpp
void TaskGroup::run_main_task() {
    TaskGroup* dummy = this;
    bthread_t tid;
    while (wait_task(&tid)) {
        TaskGroup::sched_to(&dummy, tid);
        DCHECK_EQ(this, dummy);
        DCHECK_EQ(_cur_meta->stack, _main_stack);
        // ... ...
    }
}
```
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
```cpp
void TaskGroup::sched_to(TaskGroup** pg, TaskMeta* next_meta) {
    TaskGroup* g = *pg;
    TaskMeta* const cur_meta = g->_cur_meta;
    // Switch to the task
    if (__builtin_expect(next_meta != cur_meta, 1)) {
        g->_cur_meta = next_meta;
				if (cur_meta->stack != NULL) {
            if (next_meta->stack != cur_meta->stack) {
                // 从本协程切出 
                jump_stack(cur_meta->stack, next_meta->stack);
                // 此处是返回地址，即协程恢复时开始执行的位置
                // probably went to another group, need to assign g again.
                g = tls_task_group;
            }
        }
    // ... ...
    }
    *pg = g;
}
```
```cpp
// file: stack_inl.h
inline void jump_stack(ContextualStack* from, ContextualStack* to) {
    bthread_jump_fcontext(&from->context, to->context, 0/*not skip remained*/);
}
```
调用 `bthread_jump_fcontext()` 的两个参数都是 `ContextualStack::bthread_fcontext_t` 类型，第一个参数表示要切出去的 bthread context，第二个参数表示即将执行的 bthread context。其中 bthread 栈的contex 初始值来自  `get_stack()` 中 `bthread_make_fcontext()` 的返回值。


栈切换分为两种情况讨论：

1. 一种是 bthread 是新创建的，即栈空间刚调用 `bthread_make_fcontext()` 完成初始化，需要从该 bthread 的起始处（entry）开始执行（`TaskGroup::task_runner()`）；
1. 第二种是执行到一半被切换出去的 bthread，需要接着上次执行的位置开始执行。



另外，要切出去和切入的 bthread 类型，也分为两种（因为 pthread worker 实际上也是作为一种特殊类型的 bthread 对待的，在代码处理上不需要做区分）：

1. pthread worker（main bthread）
1. bthread （即在 `ending_sched()` 中寻找下一个 bthread 并切换过去）



Content Switch 也是通过基本的函数调用实现的，所以介绍 Context Switch 之前需要先了解基础的寄存器的信息和函数调用信息（见附录1，2）。


x86_64 linux 下 `bthread_jump_fcontext()` 实现如下：
```cpp
#if defined(BTHREAD_CONTEXT_PLATFORM_linux_x86_64) && defined(BTHREAD_CONTEXT_COMPILER_gcc)
__asm (
".text\n"
".globl bthread_jump_fcontext\n"
".type bthread_jump_fcontext,@function\n"
".align 16\n"
"bthread_jump_fcontext:\n"
"    pushq  %rbp  \n"
"    pushq  %rbx  \n"
"    pushq  %r15  \n"
"    pushq  %r14  \n"
"    pushq  %r13  \n"
"    pushq  %r12  \n"
"    leaq  -0x8(%rsp), %rsp\n"
"    cmp  $0, %rcx\n"
"    je  1f\n"
"    stmxcsr  (%rsp)\n"
"    fnstcw   0x4(%rsp)\n"
"1:\n"
"    movq  %rsp, (%rdi)\n"
"    movq  %rsi, %rsp\n"
"    cmp  $0, %rcx\n"
"    je  2f\n"
"    ldmxcsr  (%rsp)\n"
"    fldcw  0x4(%rsp)\n"
"2:\n"
"    leaq  0x8(%rsp), %rsp\n"
"    popq  %r12  \n"
"    popq  %r13  \n"
"    popq  %r14  \n"
"    popq  %r15  \n"
"    popq  %rbx  \n"
"    popq  %rbp  \n"
"    popq  %r8\n"
"    movq  %rdx, %rax\n"
"    movq  %rdx, %rdi\n"
"    jmp  *%r8\n"
".size bthread_jump_fcontext,.-bthread_jump_fcontext\n"
".section .note.GNU-stack,\"\",%progbits\n"
".previous\n"
);
```
**汇编指令解释**：

- `pushq  %rbp`
- `pushq  %rbx`
- `pushq  %r15`
- `pushq  %r14`
- `pushq  %r13`
- `pushq  %r12` :	相关寄存器入栈，保存现场必须的步骤（==注意这里栈还是切换前的 bthread 栈，可能是 TaskGroup 的 \_main_stack==）



- `leaq  -0x8(%rsp), %rsp` :	栈顶下移 8 字节，为 FPU 浮点运算预留



- `cmp  $0, %rcx`
- `je  1f` :	如果第 4 个参数为 0 则直接跳转到 1 处，也就是跳过 stmxcsr、fnstcw 这两个指令。对于我们的场景而言，没有第 4 个参数，因此条件成立，跳转到 1
- `stmxcsr  (%rsp)` : 	保存当前 MXCSR 内容到 rsp 指向的位置
- `fnstcw   0x4(%rsp)` : 	保存当前 FPU 状态字到 rsp+4 指向的位置



- `movq  %rsp, (%rdi)` :	==把当前栈顶指针 %rsp 保存到 &from->context 指向的内存处，即 from->context 指向了当前 %rsp 指向的内存位置==
- `movq  %rsi, %rsp` :	==从 to->context 恢复栈顶指针 %rsp，栈切换完成==



- `cmp  $0, %rcx`
- `je  2f`
- `ldmxcsr  (%rsp)`
- `fldcw  0x4(%rsp)` : 	上面第 fnstcw 的逆操作，需要注意的是这里的栈顶指针已经是新 bthread 的栈顶了



- `leaq  0x8(%rsp), %rsp` : 	栈顶上移 8 字节，跳过 FPU 和 MXCSR

  

- `popq  %r12`
- `popq  %r13`
- `popq  %r14`
- `popq  %r15`
- `popq  %rbx`
- `popq  %rbp`: 	压栈的逆操作，注意这里是把新 bthread 的相关寄存器出栈



- `popq  %r8` : 	==对于新的 bthread，这里 pop 出来的就是 entry；对于已经执行过的 bthread，这里 pop 出来的就是 bthread 被中断时下一条指令的地址==



- `movq  %rdx  %rax`
- `movq  %rdx, %rdi` : 	%rdx 表示的是函数的第 3 个参数，也就是是否 skip remained，当前都是0。先后存入到 %rax 和 %rdi 中



- `jmp  *%r8` : 	==跳转到 %r8 的指令开始执行，即新 bthread 的入口或上次被切出去的位置==



注意其中两条重要的指令 `movq  %rsp, (%rdi)` 和 `movq  %rsi, %rsp` ，正是这两条指令完成了旧 bthread 到新 bthread 栈帧的切换，在这两条指令之前执行的指令都是在旧 bthread 的栈帧上执行的，之后的指令就是在新 bthread 栈帧上执行的了。


> **Tips**:
> 注意 `bthread_jump_fcontext()` 的第一个参数传入的是 `&from->context`（注意取地址符 &），第二个参数是 `to->context`，因此该函数原型应该是 `bthread_jump_fcontext(void**, void*)`；第一个参数是一个指针的指针，在 `movq  %rsp, (%rdi)` 中把 `from->context` 指针修改成了寄存器 `%rsp` 的值，即 `from->context` 指向了当前栈的栈顶的位置；同理第二个参数 `to->context` 是取其值恢复给 `%rsp`，注意是该指针变量的值，而不是 *context。
> 初始时 main bthread 的 from->context == NULL，在 `bthread_jump_fcontext()` 后，该指针变量被修改成了 %rsp 的值。

# 各种切换场景分析
## main bthread (pthread) -> 新 bthread
我们再回顾一下 `bthread_make_fcontext()` 完成后的内存空间，在完成后各内存位置的状态如下图所示，其中 context = %rax。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1628100785226-b120426f-2afc-4476-852f-218b9d5770f9.png" alt="bthread_stack.png" style="zoom:50%;" />

从 worker （即 main bthread，pthread）开始执行一个全新的 bthread 时栈的变化：

![bthread_context_switch.png](https://littleneko.oss-cn-beijing.aliyuncs.com/img/1629649303668-59ce9072-0342-47d2-9025-0b0a3ff8b95a.png)

注意这里对 `bthread_jump_fcontext()` 的调用同样也是一个函数调用，遵循函数调用的规则，因此上图中 sched_to 帧的 “_返回地址_” 即为 `bthread_jump_fcontext()`（假设 inline 函数 `jump_stack()` 已经展开) 的下一条语句 `g = tls_task_group`，因此当 bthread 全部执行完后，最后一个 next_meta 为 main bthread，然后从 main bthread 的 context 中恢复 %rsp 等寄存器，最后 ret 指令会 pop 出该地址，跳转到该地址指向的指令继续执行。


然后函数调用会一层层返回，最终就回到了 `TaskGroup::run_main_task()` 中，继续执行 sched_to 的下一行代码： `DCHECK_EQ(this, dummy);`。


第二张图即执行 `movq  %rsp, (%rdi)` 和 `movq  %rsi, %rsp` 之前的栈，最后当前栈的 %rsp 停在了如图所示的位置，然后该值被保存到 %rdi 所指向的内存处，即把 %rsp 保存到 main bthread 的 context 变量中。之后把目标 bthread 的 context 值恢复到 %rsp 完成栈的切换，即 %rsp 指向了第三张图中标识的位置。


对于一个全新的 bthread，其进行栈切换后，_%rsp_ 的位置如图 3，然后按顺序弹出各个寄存器的值（实际上都是空的），最后弹出到 _%r8_ 中的即为 bthread 的入口函数 `TaskGroup::task_runner()` ，然后跳转（jmp）到该函数执行任务。此时图 3 中的内存空间即为执行 task_runner 的栈，栈顶即图中 %rsp 的位置。


当然，从 main bthread 切换到的下一个  bthread 也可能是一个执行到一半被切出去的 bthread，下面我们先来分析 bthread 中途被切出去的情况。


> **Tips**:
> 栈切换的核心就是 %rsp 寄存器的保存和恢复，只要修改了 %rsp 即把栈切换到了另一块内存区域，因为 %rsp 指向的内存位置就是当前栈顶的位置。 

## bthread 主动切出（yield/sleep/bmutex）
bthread 可能在执行到一半的时候被切出，bthread 并没有 hook 会导致阻塞的系统调用，只支持主动释放 CPU 控制权，主要通过 yield 和 sleep 实现，另外 bmutex 获取不到锁的时候也会释放 CPU 控制权。


我们先来看看 yield 的实现：
```cpp
// file: bthread.cpp
//
int bthread_yield(void) {
    bthread::TaskGroup* g = bthread::tls_task_group;
    // 只有在 bthread 中才能使用 bthread 的 yield
    // 在 main bthread 即 pthread 中需要调用系统的 sched_yield()
    if (NULL != g && !g->is_current_pthread_task()) {
        bthread::TaskGroup::yield(&g);
        return 0;
    }
    // pthread_yield is not available on MAC
    return sched_yield();
}

// file: task_group.cpp
//
void TaskGroup::yield(TaskGroup** pg) {
    TaskGroup* g = *pg;
    ReadyToRunArgs args = { g->current_tid(), false };
    g->set_remained(ready_to_run_in_worker, &args);
    sched(pg);
}

void TaskGroup::sched(TaskGroup** pg) {
    TaskGroup* g = *pg;
    bthread_t next_tid = 0;
    // Find next task to run, if none, switch to idle thread of the group.
#ifndef BTHREAD_FAIR_WSQ
    const bool popped = g->_rq.pop(&next_tid);
#else
    const bool popped = g->_rq.steal(&next_tid);
#endif
    if (!popped && !g->steal_task(&next_tid)) {
        // Jump to main task if there's no task to run.
        next_tid = g->_main_tid;
    }
    sched_to(pg, next_tid);
}
```
可以看到其流程也是找到下一个 TaskMeta，并 sched_to 过去，和正常的 bthread 执行完切换到下一个 bthread 没区别。

与上面第一种场景唯一的区别是，`bthread_jump_fcontext()` 的调用栈不再是 `TaskGroup::run_main_task()` -> `TaskGroup::sched_to()` -> `bthread_jump_fcontext()` ，而是 bthread 中某个 "调用 `bthread_yield()` 的位置" -> ... -> `bthread_jump_fcontext()` 。因此当该 bthread 再次被调度并执行的时候，函数最后返回的地方就是 `bthread_yield()` 的下一条语句的位置。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1629651659261-ec74551b-0f2c-4f2a-98ba-22ddcb0a6681.png" alt="bthread_context_switch_2.png" style="zoom:50%;" />

usleep 和 bmutex 获取锁失败的时候，同样是调用的 yield 或 sched，这里旧不具体分析了。


## bthread -> bthread （正常执行完）
所谓的 bthread 正常执行完，实际上是 `TaskGroup::task_runner()` 函数中，`thread_return = m->fn(m->arg);` 正常执行完，然后会来到 ending_sched，寻找下一个任务。


## bthread -> main bthread（pthread）
在 end_sched 中，如果没有下一个任务了，就返回 main bthread 的 id，然后 task_runner 会结束循环，返回到 run_main_task，等待被唤醒。


# 切出的 bthread 重新添加到队列
bthread 执行到一半主动切出后，需要添加到任务队列中才能被再次调度，这个操作是在什么时候发生的呢？


以 yield 为例，m我们再来看看 `TaskGroup::yield()` 函数：
```cpp
void TaskGroup::yield(TaskGroup** pg) {
    TaskGroup* g = *pg;
    ReadyToRunArgs args = { g->current_tid(), false };
    g->set_remained(ready_to_run_in_worker, &args);
    sched(pg);
}
```
在 sched 之前，调用了 `TaskGroup::set_remained()` 设置了一个回调函数，该回调函数会在 `TaskGroup::task_runner()` 中执行用户任务函数前执行。
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

#ifndef NDEBUG
        --g->_sched_recursive_guard;
#endif
    }
    
    // 下面是执行用户任务函数的逻辑
    // ... ...
}
```
`TaskGroup::ready_to_run_in_worker()` 实际上完成了把切出去的 bthread_id 重新添加到 `TaskGroup::_rq` 中的逻辑。
```cpp
void TaskGroup::ready_to_run_in_worker(void* args_in) {
    ReadyToRunArgs* args = static_cast<ReadyToRunArgs*>(args_in);
    return tls_task_group->ready_to_run(args->tid, args->nosignal);
}
```
# 附录1：x86-64 下函数调用及栈帧原理
<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1628793868088-f0e01fa0-d45b-412a-a9c7-afea41a027dd.png" alt="image.png" style="zoom: 33%;" /><img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1628793883484-39969158-8028-408b-8af3-385a95a2ddd1.png" alt="image.png" style="zoom: 33%;" />

(进入子函数)								(从子函数返回)

**函数调用的时候，执行的操作：**

1. 父函数将调用参数从后往前压栈
1. 将 _返回地址_ 压栈
1. 跳转到子函数起始执行地址
1. 子函数将父函数栈帧起始(基)地址 %rbp 压栈
1. 将 %rbp 的值设置为当前的 %rsp（即将 %rbp 指向子函数的栈帧起始地址）



上述过程中，保存返回地址和跳转到子函数处执行由 call 一条指令完成，在 call 指令执行完成时，已经进入了子程序中，因而将上一栈帧 %rbp 压栈的操作，需要由子程序来完成。函数调用时在汇编层面的指令序列如下：
```
...   # 参数压栈
call FUNC  # 将返回地址压栈，并跳转到子函数 FUNC 处执行
...  # 函数调用的返回位置

FUNC:  # 子函数入口
pushq %rbp  # 保存旧的帧指针，相当于创建新的栈帧
movq  %rsp, %rbp  # 让 %rbp 指向新栈帧的起始位置
subq  $N, %rsp  # 在新栈帧中预留一些空位，供子程序使用，用 (%rsp+K) 或 (%rbp-K) 的形式引用空位
```
保存返回地址和保存上一栈帧的 %rbp 都是为了函数返回时，恢复父函数的栈帧结构。在使用高级语言进行函数调用时，由编译器自动完成上述整个流程。对于 "Caller Save" 和 "Callee Save" 寄存器的保存和恢复，也都是由编译器自动完成的。


**函数返回的时候：**
函数返回就是设置返回值，并且将栈恢复到原来的状态，然后跳转到父函数返回地址处继续执行

1. 将当前的栈指针 %rsp 设置为其栈帧起始地址 %rbp（相当于 pop 数据）
1. 从栈中 pop 出父函数栈帧的起始地址到 %rbp（还原父函数的 %rbp）（1, 2 当前合并为 leave 指令）
1. 从栈中 pop 出父函数的返回地址，跳转到返回地址继续执行（当前为 ret 指令，返回值放置在 RAX 中）
```
movq %rbp, %rsp    # 使 %rsp 和 %rbp 指向同一位置，即子栈帧的起始处
popq %rbp # 将栈中保存的父栈帧的 %rbp 的值赋值给 %rbp，并且 %rsp 上移一个位置指向父栈帧的结尾处12
ret
```
可以看出，调用 leave 后，%rsp 指向的正好是返回地址，x86-64 提供的 ret 指令，其作用就是从当前 %rsp 指向的位置（即栈顶）弹出数据，并跳转到此数据代表的地址处，在leave 执行后，%rsp 指向的正好是返回地址，因而 ret 的作用就是把 %rsp 上移一个位置，并跳转到返回地址执行。可以看出，leave 指令用于恢复父函数的栈帧，ret 用于跳转到返回地址处，leave 和ret 配合共同完成了子函数的返回。当执行完成 ret 后，%rsp 指向的是父栈帧的结尾处，父栈帧尾部存储的调用参数由编译器自动释放。
# 附录2：汇编相关
**寄存器（64位）：**

- %rax		返回值
- %rbx		被调用者保存寄存器
- %rcx		第4个参数
- %rdx		第3个参数
- %rsi		 第2个参数
- %rdi		 第1个参数
- %rbp	   被调用者保存寄存器
- %rsp		栈指针
- %r8		  第5个参数
- %r9		  第6个参数
- %r10		调用者保存寄存器
- %r11		调用者保存寄存器
- %r12		被调用者保存寄存器
- %r13		被调用者保存寄存器
- %r14		被调用者保存寄存器
- %r15		被调用者保存寄存器



**汇编指令（64位）**

- pushq	    将寄存器的值入栈
- popq	      值从栈 pop 到寄存器里
- movq	    将一个 寄存器的值/立即数/内存 保存到另一个寄存器/内存
- leaq		   将地址直接赋值给操作数（load effective address）
- cmp		  比较两个操作数的大小，比较结果存入flag寄存器，eg：执行完ZF=1说明相等，因为零标志为1说明结果为0
- je		      根据ZF标志以决定是否转移，ZF=1则跳转
- jmp		   无条件跳转
- stmxcsr	将MXCSR寄存器中的值保存到操作数中
- ldmxcsr	将操作数中的值加载到MXCSR寄存器中
- fnstcw	   把控制寄存器的内容存储到由操作数指定的字存储单元
- fldcw	     将由操作数指定的字存储单元内容存储到控制寄存器中
- jmp           无条件跳转
- **ret**	从当前 %rsp 指向的位置（即栈顶）弹出数据，并跳转到此数据代表的地址处



> **Tips**:
> 在汇编程序中，如果使用的是 64 位通用寄存器的低 32 位，则寄存器以 "e" 开头，比如 %eax，%ebx 等；对于 %r8-%r15，其低 32 位是在 64 位寄存后加 "d" 来表示，比如 %r8d, %r15d。如果操作数是 32 位的，则指令以 "l" 结尾，例如 movl $11, %esi，指令和寄存器都是 32 位的格式；如果操作数是 64 位的，则指令以 q 结尾，例如 "movq %rsp, %rbp"

# Links

1. BRPC的精华全在bthread上啦（一）：Work Stealing以及任务的执行与切换：[https://zhuanlan.zhihu.com/p/294129746](https://zhuanlan.zhihu.com/p/294129746)
1. BRPC的精华全在bthread上啦（三）：bthread上下文的创建：[https://zhuanlan.zhihu.com/p/347499412](https://zhuanlan.zhihu.com/p/347499412)
1. 高性能RPC框架BRPC核心机制分析<一>：[https://zhuanlan.zhihu.com/p/113427004](https://zhuanlan.zhihu.com/p/113427004)
1. x86-64 下函数调用及栈帧原理：[https://blog.csdn.net/lqt641/article/details/73002566](https://blog.csdn.net/lqt641/article/details/73002566)
1. libco协程库上下文切换原理详解：[https://blog.csdn.net/lqt641/article/details/73287231?spm=1001.2014.3001.5502](https://blog.csdn.net/lqt641/article/details/73287231?spm=1001.2014.3001.5502)
1. brpc源码学习（二）-bthread的创建与切换：[https://blog.csdn.net/KIDGIN7439/article/details/106426635](https://blog.csdn.net/KIDGIN7439/article/details/106426635)
1. brpc源码解析（十五）—— bthread栈创建和切换详解：[https://blog.csdn.net/wxj1992/article/details/109271030](https://blog.csdn.net/wxj1992/article/details/109271030)
1. bthread源码分析（五）上下文和栈实现：[https://blog.csdn.net/kdb_viewer/article/details/115913962](https://blog.csdn.net/kdb_viewer/article/details/115913962)
1. 基于汇编的 C/C++ 协程 - 切换上下文：[https://cloud.tencent.com/developer/article/1162058](https://cloud.tencent.com/developer/article/1162058)
1. x86寄存器问题：[https://blog.csdn.net/wang010366/article/details/52015264](https://blog.csdn.net/wang010366/article/details/52015264)
