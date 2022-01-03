# C/C++对于 volatile 的解释

**关键词：**
happens-before，指令重排，内存屏障，缓存一致性模型 MESI，编译器有优化，指令重排，CPU 乱序执行，Sequential Consistency

---



我们先来看看词典中对于volatile的解释，词典中对于这个单词有如下解释：


**易变的；无定性的；无常性的；可能急剧波动的**


英文释义为：**A situation that is volatile is likely to change suddenly and unexpectedly.**


## C 中的 volatile
cpprefrence 上对于 c language 中的 [volatile](https://en.cppreference.com/w/c/language/volatile) 有这样的解释：
> Every access (both read and write) made through an lvalue expression of volatile-qualified type is considered an _observable_ ==side effect== for the purpose of optimization and is evaluated strictly according to the rules of the abstract machine (that is, all writes are completed at some time before the next sequence point). This means that ==within a single thread of execution==, a volatile access ==cannot be optimized out== or ==reordered relative to another visible side effect== that is separated by a [_sequence point_](https://en.cppreference.com/w/c/language/eval_order)_ from the volatile access.

> Note that volatile ==variables are not suitable for communication between threads==; they **do not** offer ==atomicity==, ==synchronization==, or ==memory ordering==. A read from a volatile variable that is modified by another thread without synchronization or concurrent modification from two unsynchronized threads is undefined behavior due to a data race.



上面两段描述说明了在 c 中 volatile 会被作为可观测副效应（observable side effect）对待，不会被 optimized 掉，并且保证不能与另一个被序列点（sequence point）分隔了 volatile 访问的可观副效应重排。但是 volatile 并不保证多线程中的==原子性==、==同步==、和==内存顺序==。因此在执行线程中，不能将通过 volatile 左值的访问（读和写）重排到同线程内为序列点所分隔的可观测副效应（包含其他 volatile 访问）后，但不保证另一线程观察到此顺序，因为 volatile 访问不建立线程间同步。另外，volatile 访问不是原子的（共时的读和写是数据竞争），且不排序内存（非 volatile 内存访问可以自由地重排到 volatile 访问前后）。


因此，下面的伪代码并不能和预期的一样工作：
```c
int a = 0;
volatile bool flag = false;


Thread1() {
    a = 1;
    flag = true;
}

Thread2() {
    while() {
        if (flag) {
            assert(a == 1);
        }
    }
}
```
可能出现的情况是线程 2 永远也读不到线程 1 更新的 flag，或者读到 a 的值为 0。


### side effect 和 sequence point
如果一个表达式（或子表达式）只计算出值而不改变环境，我们就说它是==引用透明==的，这种表达式早算晚算对其他计算没有影响（不改变计算的环境。当然，它的值可能受到其他计算的影响）。如果一个表达式不仅算出一个值，还修改了环境，就说这个表达式有==副作用 (side effect)==（因为它多做了额外的事）。a++ 就是有副作用的表达式。这些说法也适用于其他语言里的类似问题。


程序语言通常都规定了执行中变量修改的最晚实现时刻（称为顺序点、序点或执行点，==sequence point==）。程序执行中存在一系列顺序点（时刻），语言保证一旦执行到达一个顺序点，在此之前发生的所有修改（副作用）都必须实现（必须反应到随后对同一存储位置的访问中），在此之后的所有修改都还没有发生。在顺序点之间则没有任何保证。对 C/C++ 语言这类允许表达式有副作用的语言，顺序点的概念特别重要。


关于具体哪些点是 sequence point，可以参考 [Order of evaluation](https://en.cppreference.com/w/c/language/eval_order) 和 [C语言表达式的求值](http://www.math.pku.edu.cn/teachers/qiuzy/technotes/expression2009.pdf) 中的相关内容。


## C++ 中的 volatile
> an object whose type is _volatile-qualified_, or a subobject of a volatile object, or a mutable subobject of a const-volatile object. Every access (read or write operation, member function call, etc.) made through a glvalue expression of volatile-qualified type is treated as a ==visible side-effect== for the [purposes of optimization](https://en.cppreference.com/w/cpp/language/as_if) (that is, within a single thread of execution, volatile accesses ==cannot be optimized out== or ==reordered with another visible side effect== that is [sequenced-before](https://en.cppreference.com/w/cpp/language/eval_order) or sequenced-after the volatile access. This makes volatile objects suitable for communication with a [signal handler](https://en.cppreference.com/w/cpp/utility/program/signal), but not with another thread of execution, see [std::memory_order](https://en.cppreference.com/w/cpp/atomic/memory_order)). Any attempt to refer to a volatile object through a non-volatile [glvalue](https://en.cppreference.com/w/cpp/language/value_category#glvalue) (e.g. through a reference or pointer to non-volatile type) results in undefined behavior.



可以看到，C++ 中的 volatile 的含义其实和 C 中是一样的。


# 并发编程中的问题
## 内存模型（[memory model](https://en.wikipedia.org/wiki/Memory_model_(programming))）
wiki 百科中对内存模型这样解释的：
> In computing, a **memory model** describes the interactions of [threads](https://en.wikipedia.org/wiki/Thread_(computer_science)) through [memory](https://en.wikipedia.org/wiki/Memory_(computing)) and their shared use of the [data](https://en.wikipedia.org/wiki/Data_(computing)).

实际上内存模型规定了在多线程中共享数据的问题，有了这个规定，编译器就可以在符合内存模型的条件下优化代码，比如说进行一些指令重排，优化掉一些变量。


当然，优化需要保证的是：
> the compiler needs to make sure **only** that the values of (potentially shared) variables at synchronization barriers are guaranteed to be the same in both the optimized and unoptimized code.



C++ 中一共规定了以下 6 种语义来约束多线程间的共享变量问题：
```c
typedef enum memory_order {
    memory_order_relaxed,
    memory_order_consume,
    memory_order_acquire,
    memory_order_release,
    memory_order_acq_rel,
    memory_order_seq_cst
} memory_order;
```


其具体含义是：

| **memory order** | **作用** |
| --- | --- |
| memory_order_relaxed | 没有 fencing 作用 |
| memory_order_consume | 后面依赖此原子变量的访存指令勿重排至此条指令之前 |
| memory_order_acquire | 后面访存指令勿重排至此条指令之前 |
| memory_order_release | 前面访存指令勿重排至此条指令之后。当此条指令的结果对其他线程可见后，之前的所有指令都可见 |
| memory_order_acq_rel | acquire + release 语意 |
| memory_order_seq_cst | acq_rel 语意外加所有使用 seq_cst 的指令有严格地全序关系 |

## 缓存一致性
之所以多线程之间共享变量会有可见行等问题，都是因为有各级缓存存在。当程序在运行过程中，会将运算需要的数据从主存复制一份到 CPU 的高速缓存当中，那么 CPU 进行计算时就可以直接从它的高速缓存读取数据和向其中写入数据，当运算结束之后，再将高速缓存中的数据刷新到主存当中（不一定是立即写回）。

在多处理器系统中，每个处理器都有自己的高速缓存，而它们又共享同一主内存（MainMemory）。基于高速缓存的存储交互很好地解决了处理器与内存的速度矛盾，但是也引入了新的问题：缓存一致性（CacheCoherence）。当多个处理器的运算任务都涉及同一块主内存区域时，将可能导致各自的缓存数据不一致的情况，如果真的发生这种情况，那同步回到主内存时以谁的缓存数据为准呢？为了解决一致性的问题，需要各个处理器访问缓存时都遵循一些协议，在读写时要根据协议来进行操作，这类协议有 MSI、[MESI](https://en.wikipedia.org/wiki/MESI_protocol)（IllinoisProtocol）、MOSI、Synapse、Firefly 以及 DragonProtocol，等等：

![image.png](https://littleneko.oss-cn-beijing.aliyuncs.com/img/1573920592994-bc3f3f43-8048-40c3-a8d7-af94be4607d7.png)


既然有了 MESI 等缓存一致性协议，那是不是就可以保证多线程（多核）之间的可见行问题了呢？实际上并不是，由于传统的 MESI 协议的执行成本比较大。所以 CPU 通过 Store Buffer 和 Invalidate Queue 组件来解决，但是由于这两个组件的引入，也导致缓存和主存之间的通信并不是实时的。也就是说，缓存一致性模型只能保证缓存变更可以保证其他缓存也跟着改变，但是不能保证立刻、马上执行。感兴趣的可以看《Memory Models for C/C++ Programmers 》和《x86-TSO - A Rigorous and Usable Programmer’s Model for x86 Multiprocessors》这两篇论文。


其实，在计算机内存模型中，是使用内存屏障（[Memory barrier](https://en.wikipedia.org/wiki/Memory_barrier)）来解决缓存的可见性问题的。写内存屏障（Store Memory Barrier）可以促使处理器将当前 store buffer（存储缓存）的值写回主存。读内存屏障（Load Memory Barrier）可以促使处理器处理 invalidate queue（失效队列）。进而避免由于 Store Buffer 和 Invalidate Queue 的非实时性带来的问题。
> **Tips**:
> 在 JVM 中就是通过内存屏障来实现 volatile 的可见性问题的



## 指令重排序问题
为了使得处理器内部的运算单元能尽量被充分利用，处理器可能会对输入代码进行乱序执行（Out-Of-Order Execution）优化，处理器会在计算之后将乱序执行的结果重组，保证该结果与顺序执行的结果是一致的，但并不保证程序中各个语句计算的先后顺序与输入代码中的顺序一致。因此，如果存在一个计算任务依赖另一个计算任务的中间结果，那么其顺序性并不能靠代码的先后顺序来保证。

关于指令重排，除了有编译器对语句的重排，CPU 执行的过程中，也会有乱序执行。不同的架构对于不同指令有不同的表现，具体可以参考这个链接：[https://en.wikipedia.org/wiki/Memory_ordering](https://en.wikipedia.org/wiki/Memory_ordering)

![image.png](https://littleneko.oss-cn-beijing.aliyuncs.com/img/1630777961578-d7cbe846-753d-42c9-824b-a62563933b64.png)

# C/C++中的volatile
因此，volatile 能保证的只是 volitale 变量之间不会被编译器重排，以及 volitale 不会被优化掉；除此之外，并不能保证多线程之间的可见行，以及和普通变量之间的重排，同样也不保证原子性。


下面我们来看看 volatile 到底保证了什么。


## optimized out
no-volatile 变量：

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1573924022769-7044c534-07d3-41e4-b44c-8cef10839d07.png" alt="image.png" style="zoom:50%;" />

不开启编译优化

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1573924040134-e3d401d6-cf68-4c1b-b09f-6aa4c7b6f874.png" alt="image.png" style="zoom:50%;" />

开启O3编译优化

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1573924060194-d1a7db2a-a39b-4311-b991-b1fe8aff6ad6.png" alt="image.png" style="zoom:50%;" />

可以看到开启 O3 编译优化后，变量 a 直接被优化掉了，因为编译器这里判断出来最后要 print 的值就是立即数 1。

volatile 变量 -O3 编译

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1573924114793-04dd119d-a4da-4624-b43d-884040af84e2.png" alt="image.png" style="zoom:50%;" />

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1573924082361-20b7f5ac-5ee5-4f4e-902f-dd9e2ef61464.png" alt="image.png" style="zoom:50%;" />

但是，对 `a` 加了 `volatile` 关键字后，再次开启 O3 编译优化，变量 a 并没有被优化掉。


这个特性对于单片机上的编程特别有用，考虑以下 C/C++ 代码：
```c
volatile int *p = /* ... */;
int a, b;
a = *p;
b = *p;
```


若忽略 `volatile`，那么 `p` 就只是一个「指向 `int` 类型的指针」。这样一来，`a = *p;` 和 `b = *p;` 两句，就只需要从内存中读取一次就够了。因为从内存中读取一次之后，CPU 的寄存器中就已经有了这个值；把这个值直接复用就可以了。这样一来，编译器就会做优化，把两次访存的操作优化成一次。这样做是基于一个假设：我们在代码里没有改变 `p` 指向内存地址的值，那么这个值就一定不会发生改变。
> 此处说的「读取内存」，包括了读取 CPU 缓存和读取计算机主存。

然而，由于 MMIP（Memory mapped I/O）的存在，这个假设不一定是真的。例如说，假设 `p` 指向的内存是一个硬件设备。这样一来，从 `p` 指向的内存读取数据可能伴随着**可观测的副作用**：硬件状态的修改。此时，代码的原意可能是将硬件设备返回的连续两个 `int` 分别保存在 `a` 和 `b` 当中。这种情况下，编译器的优化就会导致程序行为不符合预期了。


## 顺序性
我们再回过头去看看最开始的例子，声明一个 volatile 的 flag 变量。一个线程 Thread1 在完成一些操作后，会修改这个变量。而另外一个线程 Thread2，则不断读取这个 flag 变量，由于 flag 变量被声明了 volatile 属性，因此编译器在编译时，并不会每次都从寄存器中读取此变量，同时也不会通过各种激进的优化（直接将 `if (flag == true)` 改写为 `if (false == true)`）。在 if 条件的内部，由于 flag == true，那么假设 Thread1 中的 something 操作一定已经完成了，在基于这个假设的基础上，继续进行下面的 other things 操作。


从上面的描述中我们知道，因为 `flag` 是 `volatile` 变量，所以不会因为编译优化，把 Thread2 中的 `if(flag)` 优化成 `if(false)` ，这个看似很完美的代码有如下问题：

1. **`a` 是普通变量，因为编译优化，可能对 Thread1 中 a 和 flag 赋值操作重排，即 `flag` 被置为 `true` 时， `a` 不一定被置为 `1` 了。**
1. **由于 volatile 并不保证内存可见性，因此 Thread1 中修改了 flag 后，Thread2 可能永远也读不到新值**

那把 `a` 也加上 `volatile` 限制呢，按照官方文档的说法，编译器不会对 Thread1 中 a 和 flag 变量的赋值操作重排，即在编译得到的二进制中，a 的赋值指令一定在 flag 的赋值指令之前，看起来似乎没有问题了。但是，CPU 最终执行的时候会乱序执行，虽然在机器码中，是先给 a 赋值，再给 flag 赋值，然而 CPU 确不保证这个执行顺序。


> **Tips**：
> 实际上在 x86 架构中，load-load 是不会被乱序的，上面的情况不会出现。然而，在 ARM 和 POWER 中，却是允许 load-load 乱序的。[https://en.wikipedia.org/wiki/Memory_ordering](https://en.wikipedia.org/wiki/Memory_ordering)

# Java中的volatile
JVM有自己的内存模型，Java 加强了 `volatile` 语义：

- 保证被 volatile 修饰的共享变量对所有线程总数可见的，也就是当一个线程修改了一个被 `volatile` 修饰共享变量的值，新值总数可以被其他线程立即得知。
- 禁止指令重排序优化。



其具体实现是利用了内存屏障，这里就补详细展开了。


# 总结
总结一下 C/C++ 中的 `volatile` 保证了：

1. 不会在两个操作之间把 `volatile` 变量缓存在寄存器中。在多任务、中断、甚至 setjmp 环境下，变量可能被其他的程序改变，编译器自己无法知道，volatile 就是告诉编译器这种情况。
1. 不会把 `volatile` 变量优化掉
1. 编译阶段保证多个 `volatile` 变量的操作之间的顺序性



不保证下面的情况：

1. ==内存可见行==，即在多核CPU的缓存中修改了 `volatile` 变量，不能保证立即能在另一个核的缓存中读到（ `volatile` 只保证了不缓存在寄存器中，然而从缓存中读并不能保证缓存一致性）
1. ==`volatile` 和普通变量操作之间的顺序==，编译器和CPU都会有乱序



**Summary**:


- volatile 在 java 和 C/C++ 中的语义不一样
- C/C++ 中简单赋值操作是否保证原子性？ a = 5
- MESI 因为有 Store Buffer 和 Invalidate Queue 的存在，并不能保证一致性，必须使用内存屏障
- 指令优化例子：连续两次读一个指针，对于一些读外设内存的场景，不能优化成只读一次，两个语句返回相同的值，因为在两次读之间，同样一个地址的数据可能已经发生变化。
- x86 和 AMD64 架构的 CPU（大多数个人机器和服务器使用这两种架构的 CPU）只允许 sotre-load 乱序，而不会发生 store-store 乱序


# Links

1. volatile type qualifier: [https://en.cppreference.com/w/c/language/volatile](https://en.cppreference.com/w/c/language/volatile)
1. Order of evaluation: [https://en.cppreference.com/w/c/language/eval_order](https://en.cppreference.com/w/c/language/eval_order)
1. memory_order: [https://en.cppreference.com/w/c/atomic/memory_order](https://zh.cppreference.com/w/c/atomic/memory_order)
1. Order of evaluation: [https://en.cppreference.com/w/cpp/language/eval_order](https://en.cppreference.com/w/cpp/language/eval_order)
1. cv (const and volatile) type qualifiers: [https://en.cppreference.com/w/cpp/language/cv](https://en.cppreference.com/w/cpp/language/cv)
1. Sequence point: [https://en.wikipedia.org/wiki/Sequence_point](https://en.wikipedia.org/wiki/Sequence_point)
1. C语言表达式的求值: [http://www.math.pku.edu.cn/teachers/qiuzy/technotes/expression2009.pdf](http://www.math.pku.edu.cn/teachers/qiuzy/technotes/expression2009.pdf)
1. Memory model (programming): [https://en.wikipedia.org/wiki/Memory_model_(programming)](https://en.wikipedia.org/wiki/Memory_model_(programming))
1. Memory ordering: [https://en.wikipedia.org/wiki/Memory_ordering](https://en.wikipedia.org/wiki/Memory_ordering)
1. Memory barrier: [https://en.wikipedia.org/wiki/Memory_barrier](https://en.wikipedia.org/wiki/Memory_barrier)
1. Sequential consistency: [https://en.wikipedia.org/wiki/Sequential_consistency](https://en.wikipedia.org/wiki/Sequential_consistency)
1. MOESI protocol: [https://en.wikipedia.org/wiki/MOESI_protocol](https://en.wikipedia.org/wiki/MOESI_protocol)
1. MESI protocol: [https://en.wikipedia.org/wiki/MESI_protocol](https://en.wikipedia.org/wiki/MESI_protocol)
1. Java memory model: [https://en.wikipedia.org/wiki/Java_memory_model](https://en.wikipedia.org/wiki/Java_memory_model)
1. JAVA Memory Model: [https://docs.oracle.com/javase/specs/jls/se8/html/jls-17.html#jls-17.4](https://docs.oracle.com/javase/specs/jls/se8/html/jls-17.html#jls-17.4)
1. [http://cmsblogs.com/?p=2092](http://cmsblogs.com/?p=2092)
1. The Java Memory Model: [http://www.cs.umd.edu/~pugh/java/memoryModel/](http://www.cs.umd.edu/~pugh/java/memoryModel/)
1. Java并发编程：volatile关键字解析: [https://www.cnblogs.com/dolphin0520/p/3920373.html](https://www.cnblogs.com/dolphin0520/p/3920373.html)
1. Java内存模型（JMM）总结: [https://zhuanlan.zhihu.com/p/29881777](https://zhuanlan.zhihu.com/p/29881777)
1. 并发编程前传: [https://juejin.im/post/5c8d99d25188257ed73dd911](https://juejin.im/post/5c8d99d25188257ed73dd911)
1. C/C++ Volatile关键词深度剖析: [https://www.cnblogs.com/god-of-death/p/7852394.html](https://www.cnblogs.com/god-of-death/p/7852394.html)
1. C/C++ Volatile关键词深度剖析: [http://hedengcheng.com/?p=725](http://hedengcheng.com/?p=725)
1. CPU Cache and Memory Ordering: [http://hedengcheng.com/?p=648](http://hedengcheng.com/?p=648)
1. 谈谈 C/C++ 中的 volatile: [https://liam.page/2018/01/18/volatile-in-C-and-Cpp/](https://liam.page/2018/01/18/volatile-in-C-and-Cpp/)
1. Memory Barriers Are Like Source Control Operations: [https://preshing.com/20120710/memory-barriers-are-like-source-control-operations/](https://preshing.com/20120710/memory-barriers-are-like-source-control-operations/)
1. The Happens-Before Relation: [https://preshing.com/20130702/the-happens-before-relation/](https://preshing.com/20130702/the-happens-before-relation/)
1. Acquire and Release Semantics: [https://preshing.com/20120913/acquire-and-release-semantics/](https://preshing.com/20120913/acquire-and-release-semantics/)
1. Meyers S, Alexandrescu A. C++ and the perils of double-checked locking: Part i[J]. Dr. Dobb’s Journal, 2004, 29(7): 46-49.
1. Memory Models for C_C++ Programmers: [https://zhuanlan.zhihu.com/p/45566448](https://zhuanlan.zhihu.com/p/45566448)
1. [https://www.hollischuang.com/archives/2550](https://www.hollischuang.com/archives/2550)
1. 在线代码执行平台：[https://godbolt.org/](https://godbolt.org/)
