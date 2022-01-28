我们都知道多核编程常用锁避免多个线程在修改同一个数据时产生 [race condition](http://en.wikipedia.org/wiki/Race_condition)。当锁成为性能瓶颈时，我们又总想试着绕开它，而不可避免地接触了原子指令。但在实践中，用原子指令写出正确的代码是一件非常困难的事，琢磨不透的 race condition、[ABA problem](https://en.wikipedia.org/wiki/ABA_problem)、[memory fence](https://en.wikipedia.org/wiki/Memory_barrier) 很烧脑，这篇文章试图通过介绍 [SMP](http://en.wikipedia.org/wiki/Symmetric_multiprocessing) 架构下的原子指令帮助大家入门。C++11 正式引入了[原子指令](http://en.cppreference.com/w/cpp/atomic/atomic)，我们就以其语法描述。


顾名思义，原子指令是**对软件**不可再分的指令，比如 `x.fetch_add(n)` 指原子地给 x 加上 n，这个指令**对软件**要么没做，要么完成，不会观察到中间状态。常见的原子指令有：

| **原子指令 (x 均为 std::atomic)** | **作用** |
| --- | --- |
| x.load() | 返回 x 的值。 |
| x.store(n) | 把 x 设为 n，什么都不返回。 |
| x.exchange(n) | 把 x 设为 n，返回设定之前的值。 |
| x.compare_exchange_strong(expected_ref, desired) | 若 x 等于 expected_ref，则设为 desired，返回成功；否则把最新值写入 expected_ref，返回失败。 |
| x.compare_exchange_weak(expected_ref, desired) | 相比 compare_exchange_strong 可能有 [spurious wakeup](http://en.wikipedia.org/wiki/Spurious_wakeup) 。 |
| x.fetch_add(n), x.fetch_sub(n) | 原子地做 x += n, x-= n，返回修改之前的值。 |

你已经可以用这些指令做原子计数，比如多个线程同时累加一个原子变量，以统计这些线程对一些资源的操作次数。但是，这可能会有两个问题：

- 这个操作没有你想象地快。
- 如果你尝试通过看似简单的原子操作控制对一些资源的访问，你的程序有很大几率会 crash。
# Cacheline
没有任何竞争或只被一个线程访问的原子操作是比较快的，“竞争”指的是多个线程同时访问同一个 [cacheline](https://en.wikipedia.org/wiki/CPU_cache#Cache_entries)。现代 CPU为了以低价格获得高性能，大量使用了 cache，并把 cache 分了多级。百度内常见的 Intel E5-2620 拥有 32K 的 L1 dcache 和 icache，256K 的 L2 cache 和 15M 的 L3 cache。其中 L1 和 L2 cache 为每个核心独有，L3 则所有核心共享。一个核心写入自己的 L1 cache 是极快的(4 cycles, \~2ns)，但当另一个核心读或写同一处内存时，它得确认看到其他核心中对应的 cacheline。对于软件来说，这个过程是原子的，不能在中间穿插其他代码，只能等待 CPU 完成[一致性同步](https://en.wikipedia.org/wiki/Cache_coherence)，这个复杂的硬件算法使得原子操作会变得很慢，在 E5-2620 上竞争激烈时 fetch_add 会耗费 700 纳秒左右。访问被多个线程频繁共享的内存往往是比较慢的。比如像一些场景临界区看着很小，但保护它的 spinlock 性能不佳，因为spinlock 使用的 exchange, fetch_add 等指令必须等待最新的 cacheline，看上去只有几条指令，花费若干微秒并不奇怪。


要提高性能，就要避免让 CPU 频繁同步 cacheline。这不单和原子指令本身的性能有关，还会影响到程序的整体性能。最有效的解决方法很直白：**尽量避免共享**。

- 一个依赖全局多生产者多消费者队列 (MPMC) 的程序难有很好的多核扩展性，因为这个队列的极限吞吐取决于同步cache 的延时，而不是核心的个数。最好是用多个 SPMC 或多个 MPSC 队列，甚至多个 SPSC 队列代替，在源头就规避掉竞争。
- 另一个例子是计数器，如果所有线程都频繁修改一个计数器，性能就会很差，原因同样在于不同的核心在不停地同步同一个 cacheline。如果这个计数器只是用作打打日志之类的，那我们完全可以让每个线程修改 thread-local 变量，在需要时再合并所有线程中的值，性能可能有[几十倍的差别](https://github.com/apache/incubator-brpc/blob/master/docs/cn/bvar.md)。

==一个相关的编程陷阱是 false sharing：对那些不怎么被修改甚至只读变量的访问，由于同一个 cacheline 中的其他变量被频繁修改，而不得不经常等待 cacheline 同步而显著变慢了。**多线程中的变量尽量按访问规律排列，频繁被其他线程修改的变量要放在独立的 cacheline中**==。要让一个变量或结构体按 cacheline 对齐，可以 include <butil/macros.h> 后使用`BAIDU_CACHELINE_ALIGNMENT` 宏，请自行 grep brpc 的代码了解用法。

# Memory fence
仅靠原子技术实现不了对资源的访问控制，即使简单如 [spinlock](https://en.wikipedia.org/wiki/Spinlock) 或[引用计数](https://en.wikipedia.org/wiki/Reference_counting)，看上去正确的代码也可能会 crash。这里的关键在于**重排指令**导致了读写顺序的变化。只要没有依赖，代码中在后面的指令就可能跑到前面去，[编译器](http://preshing.com/20120625/memory-ordering-at-compile-time/)和 [CPU](https://en.wikipedia.org/wiki/Out-of-order_execution) 都会这么做。


这么做的动机非常自然，CPU 要尽量塞满每个 cycle，在单位时间内运行尽量多的指令。如上节中提到的，访存指令在等待 cacheline 同步时要花费数百纳秒，最高效地自然是同时同步多个 cacheline，而不是一个个做。一个线程在代码中对多个变量的依次修改，可能会以不同的次序同步到另一个线程所在的核心上。不同线程对数据的需求不同，按需同步也会导致 cacheline 的读序和写序不同。


如果其中第一个变量扮演了开关的作用，控制对后续变量的访问。那么当这些变量被一起同步到其他核心时，更新顺序可能变了，第一个变量未必是第一个更新的，然而其他线程还认为它代表着其他变量有效，去访问了实际已被删除的变量，从而导致未定义的行为。比如下面的代码片段：
```cpp
// Thread 1
// ready was initialized to false
p.init();
ready = true;
```
```cpp
// Thread2
if (ready) {
    p.bar();
}
```
从人的角度，这是对的，因为线程 2 在 ready 为 true 时才会访问 p，按线程 1 的逻辑，此时 p 应该初始化好了。但对多核机器而言，这段代码可能难以正常运行：

- 线程 1 中的 ready = true 可能会被编译器或 cpu 重排到 p.init() 之前，从而使线程 2 看到 ready 为 true 时，p 仍然未初始化。这种情况同样也会在线程 2 中发生，p.bar() 中的一些代码可能被重排到检查 ready 之前。
- 即使没有重排，ready 和 p 的值也会独立地同步到线程 2 所在核心的 cache，线程 2 仍然可能在看到 ready 为 true 时看到未初始化的 p。
> 注：x86/x64 的 load 带 acquire 语意，store 带 release 语意，上面的代码刨除编译器和 CPU 因素可以正确运行。



通过这个简单例子，你可以窥见原子指令编程的复杂性了吧。为了解决这个问题，CPU 和编译器提供了 [memory fence](http://en.wikipedia.org/wiki/Memory_barrier)，让用户可以声明访存指令间的可见性 (visibility) 关系，boost 和 C++11 对 memory fence 做了抽象，总结为如下几种[memory order](http://en.cppreference.com/w/cpp/atomic/memory_order).

| **memory order** | **作用** |
| --- | --- |
| memory_order_relaxed | 没有 fencing 作用 |
| memory_order_consume | 后面依赖此原子变量的访存指令勿重排至此条指令之前 |
| memory_order_acquire | 后面访存指令勿重排至此条指令之前 |
| memory_order_release | 前面访存指令勿重排至此条指令之后。当此条指令的结果对其他线程可见后，之前的所有指令都可见 |
| memory_order_acq_rel | acquire + release 语意 |
| memory_order_seq_cst | acq_rel 语意外加所有使用 seq_cst 的指令有严格地全序关系 |

有了 memory order，上面的例子可以这么更正：
```cpp
// Thread1
// ready was initialized to false
p.init();
ready.store(true, std::memory_order_release);
```
```cpp
// Thread2
if (ready.load(std::memory_order_acquire)) {
    p.bar();
}
```
线程 2 中的 acquire 和线程 1 的 release 配对，确保线程 2 在看到 ready==true 时能看到线程 1 release 之前所有的访存操作。


注意，==memory fence 不等于可见性==，即使线程 2 恰好在线程 1 在把 ready 设置为 true 后读取了 ready 也不意味着它能看到 true，因为同步 cache 是有延时的。==memory fence 保证的是可见性的顺序：“假如我看到了 a 的最新值，那么我一定也得看到 b 的最新值”==。


一个相关问题是：如何知道看到的值是新还是旧？一般分两种情况：

- 值是特殊的。比如在上面的例子中，ready=true 是个特殊值，只要线程 2 看到 ready 为 true 就意味着更新了。只要设定了特殊值，读到或没有读到特殊值都代表了一种含义。
- 总是累加。一些场景下没有特殊值，那我们就用 fetch_add 之类的指令累加一个变量，只要变量的值域足够大，在很长一段时间内，新值和之前所有的旧值都会不相同，我们就能区分彼此了。

原子指令的例子可以看 boost.atomic 的 [Example](http://www.boost.org/doc/libs/1_56_0/doc/html/atomic/usage_examples.html)，atomic 的官方描述可以看[这里](http://en.cppreference.com/w/cpp/atomic/atomic)。
# wait-free & lock-free
原子指令能为我们的服务赋予两个重要属性：[wait-free](http://en.wikipedia.org/wiki/Non-blocking_algorithm#Wait-freedom) 和 [lock-free](http://en.wikipedia.org/wiki/Non-blocking_algorithm#Lock-freedom)。==前者指不管 OS 如何调度线程，**每个线程**都始终在做有用的事==；==后者比前者弱一些，指不管 OS 如何调度线程，**至少有一个线程**在做有用的事==。如果我们的服务中使用了锁，那么 OS 可能把一个刚获得锁的线程切换出去，这时候所有依赖这个锁的线程都在等待，而没有做有用的事，所以用了锁就不是 lock-free，更不会是 wait-free。为了确保一件事情总在确定时间内完成，实时系统的关键代码至少是 lock-free 的。在百度广泛又多样的在线服务中，对时效性也有着严苛的要求，如果 RPC 中最关键的部分满足 wait-free 或 lock-free，就可以提供更稳定的服务质量。事实上，brpc 中的读写都是 wait-free 的，具体见 [IO](https://github.com/apache/incubator-brpc/blob/master/docs/cn/io.md)。


值得提醒的是，常见想法是 lock-free 或 wait-free 的算法会更快，但事实可能相反，因为：

- lock-free 和 wait-free 必须处理更多更复杂的 race condition 和 ABA problem，完成相同目的的代码比用锁更复杂。代码越多，耗时就越长。
- 使用 mutex 的算法变相带“后退”效果。后退 (backoff) 指出现竞争时尝试另一个途径以临时避免竞争，mutex 出现竞争时会使调用者睡眠，使拿到锁的那个线程可以很快地独占完成一系列流程，总体吞吐可能反而高了。



mutex 导致低性能往往是因为临界区过大（限制了并发度），或竞争过于激烈（上下文切换开销变得突出）。lock-free/wait-free 算法的价值在于其保证了一个或所有线程始终在做有用的事，而不是绝对的高性能。但在一种情况下 lock-free 和 wait-free 算法的性能多半更高：就是算法本身可以用少量原子指令实现。实现锁也是要用原子指令的，当算法本身用一两条指令就能完成的时候，相比额外用锁肯定是更快了。


[https://github.com/apache/incubator-brpc/blob/master/docs/cn/atomic_instructions.md](https://github.com/apache/incubator-brpc/blob/master/docs/cn/atomic_instructions.md)
