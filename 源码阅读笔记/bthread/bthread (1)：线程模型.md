# 常见线程模型
线程模型解决的问题，是如何高效的利用多个物理核，进行工作任务的调度，使得系统能够有更高有效的吞吐，更加低的延迟。而不是把时间花在大量的比如系统层面的工作，比如 context-switch、cache 的同步、线程等待等 contention 上面。
## 连接独占线程或进程
在这个模型中，线程/进程处理来自绑定连接的消息，在连接断开前不退也不做其他事情。当连接数逐渐增多时，线程/进程占用的资源和上下文切换成本会越来越大，性能很差，这就是 C10K 问题的来源。这种方法常见于早期的 web server，现在很少使用。
## 单线程 reactor
以 [libevent](https://libevent.org/) 、[libev](http://software.schmorp.de/pkg/libev.html) 等 event-loop 库为典型。这个模型一般由一个 event dispatcher 等待各类事件，待事件发生后原地调用对应的 event handler，全部调用完后等待更多事件，故为 "loop"。这个模型的实质是把多段逻辑按事件触发顺序交织在一个系统线程中。==一个 event-loop 只能使用一个核==，故此类程序要么是 IO-bound，要么是每个 handler 有确定的较短的运行时间 (比如 http server)，否则==一个耗时漫长的回调就会卡住整个程序，产生高延时==。在实践中这类程序不适合多开发者参与，一个人写了阻塞代码可能就会拖慢其他代码的响应。由于 event handler 不会同时运行，不太会产生复杂的 race condition，一些代码不需要锁。此类程序主要靠部署更多进程增加扩展性。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1628267773792-54c03ede-1b8d-48f8-bac0-9df059968d59.png" alt="image.png" style="zoom: 80%;" />

## N:1 线程库
又称为 [Fiber](https://en.wikipedia.org/wiki/Fiber_(computer_science))，以[ GNU Pth](http://www.gnu.org/software/pth/pth-manual.html) 、[StateThreads](https://sourceforge.net/projects/state-threads/) 等为典型，一般是把 N 个用户线程映射入一个系统线程。同时只运行一个用户线程，调用阻塞函数时才会切换至其他用户线程。N:1 线程库与单线程 reactor 在能力上等价，但事件回调被替换为了上下文 (栈、寄存器、signals)，运行回调变成了跳转至上下文。和 event loop 库一样，==单个 N:1 线程库无法充分发挥多核性能==，只适合一些特定的程序。只有一个系统线程==对 CPU cache 较为友好==，加上舍弃对 signal mask 的支持的话，==用户线程间的上下文切换可以很快== (100~200ns)。N:1 线程库的性能一般和 event loop 库差不多，扩展性也主要靠多进程。
## 多线程 reactor
以 [boost::asio](https://www.boost.org/doc/libs/1_56_0/doc/html/boost_asio.html) 为典型。一般由一个或多个线程分别运行 event dispatcher，待事件发生后把 event handler 交给一个 worker 线程执行。 这个模型是单线程 reactor 的自然扩展，可以利用多核。由于共用地址空间使得线程间交互变得廉价，worker thread 间一般会更及时地均衡负载，而多进程一般依赖更前端的服务来分割流量，==一个**设计良好**的多线程 reactor 程序往往能比同一台机器上的多个单线程 reactor 进程更均匀地使用不同核心==。不过==由于 **cache 一致性**的限制，多线程 reactor 并不能获得线性于核心数的性能==，在特定的场景中，粗糙的多线程 reactor 实现跑在 24 核上甚至没有精致的单线程 reactor 实现跑在 1 个核上快。由于多线程 reactor 包含多个 worker 线程，单个 event handler 阻塞未必会延缓其他 handler，所以 ==event handler 未必得非阻塞，除非所有的 worker 线程都被阻塞才会影响到整体进展==。事实上，大部分 RPC 框架都使用了这个模型，且回调中常有阻塞部分，比如同步等待访问下游的 RPC 返回。

![image.png](https://littleneko.oss-cn-beijing.aliyuncs.com/img/1628267814287-897144d2-44ae-41ef-bce8-38c3e7a1420b.png)

## M:N 线程库
即把 M 个用户线程映射入 N 个系统线程。M:N 线程库可以决定一段代码何时开始在哪运行，并何时结束，相比多线程 reactor 在调度上具备更多的灵活度。但实现全功能的 M:N 线程库是困难的，它一直是个活跃的研究话题。我们这里说的 M:N 线程库特别针对编写网络服务，在这一前提下一些需求可以简化，比如没有时间片抢占，没有 (完备的) 优先级等。M:N 线程库可以在用户态也可以在内核中实现，用户态的实现以新语言为主，比如 GHC threads 和 goroutine，这些语言可以围绕线程库设计全新的关键字并拦截所有相关的 API。而在现有语言中的实现往往得修改内核，比如 Windows UMS 和 google SwitchTo (虽然是1:1，但基于它可以实现 M:N 的效果)。相比 N:1 线程库，M:N 线程库在使用上更类似于系统线程，需要用锁或消息传递保证代码的线程安全。
# 传统线程模型的问题
## 多核扩展性
理论上代码都写成事件驱动型能最大化 reactor 模型的能力，但实际由于编码难度和可维护性，用户的使用方式大都是混合的，即回调中往往会发起同步操作，阻塞住 worker 线程使其无法处理其他请求，因此实际上多线程 reactor 并不能获得线性于核心数的性能。
## 异步编程的复杂性
异步编程中的流程控制对于专家也充满了陷阱，任何挂起操作，如 sleep 一会儿或等待某事完成，都意味着用户需要显式地保存状态，并在回调函数中恢复状态。异步代码往往得写成状态机的形式。当挂起较少时，这有点麻烦，但还是可把握的。问题在于一旦挂起发生在条件判断、循环、子函数中，写出这样的状态机并能被很多人理解和维护，几乎是不可能的。没有上下文会使得 RAII 无法充分发挥作用, 有时需要在 callback 之外 lock，callback 之内 unlock，实践中很容易出错。
# bthread 定义
bthread 是 brpc 使用的 M:N 线程库，目的是在提高程序的并发度的同时，降低编码难度，并在核数日益增多的 CPU 上提供更好的 ==_scalability_== 和 ==_cache locality_==。"M:N" 是指 M 个 bthread 会映射至 N 个 pthread，一般 M 远大于 N。由于 linux 当下的 pthread 实现(NPTL)是 1:1 的，M 个 bthread 也相当于映射至 N 个 LWP。


bthread 是一个 M:N 线程库，一个 bthread 被卡住不会影响其他 bthread。关键技术两点：==work stealing== 调度和 ==butex==，==前者让 bthread 更快地被调度到更多的核心上==，==后者让 bthread 和 pthread 可以相互等待和唤醒==。


> **Tips**:
> 官方并不认为 bthread 是协程(coroutine)，原因是 bthread 是一个 M:N 的线程库，而传统的协程定义是 N:1 线程库，也不需要 work stealing 调度和 butex 等特性。同样属于 M:N 线程模型的还有 goroutine，因为我们已经习惯把 goroutine 叫做协程，所以我们后面不再进行区分。
>
> bthread 与 goroutine 或其他协程库 (比如 [libco](https://github.com/Tencent/libco)) 的一个区别是：bthread 并没有 hook 系统 IO，无法做到在 IO 阻塞时自动切换，只能主动切换或是 butex 拿不到锁时进行切换。

## Goals

- 用户可以延续==同步的编程模式==，能在数百纳秒内建立 bthread，可以用多种原语同步。
- bthread 所有接口可在 pthread 中被调用并有合理的行为，使用 bthread 的代码可以在 pthread 中正常执行。
- 能==充分利用多核==。
- better cache locality, supporting NUMA is a plus.
# 何时使用 bthread
**Q1**: bthread 主要在 brpc 中使用，同时我们在使用 brpc 开发程序时也可以使用 bthread，那么在什么场景下需要使用 bthread 呢？
**A1**: 除非你==需要在一次 RPC 过程中让一些代码并发运行==，你不应该直接调用 bthread 函数，把这些留给 brpc 做更好

---

**Q2**: brpc 提供了异步接口，所以一个常见的问题是：我应该用异步接口还是 bthread？
**A2**: 延时不高时你应该先用简单易懂的同步接口，不行的话用异步接口，只有在需要多核并行计算时才用 bthread。

brpc 中的异步和单线程的异步是完全不同的，异步回调会运行在与调用处不同的线程中，你会获得多核扩展性，但代价是你得意识到多线程问题。你可以在回调中阻塞，只要线程够用，对 server 整体的性能并不会有什么影响。不过异步代码还是很难写的，所以我们提供了[组合访问](https://github.com/apache/incubator-brpc/blob/master/docs/cn/combo_channel.md)来简化问题，通过组合不同的 channel，你可以声明式地执行复杂的访问，而不用太关心其中的细节。

当然，延时不长，qps 不高时，我们更建议使用同步接口，这也是创建 bthread 的动机：维持同步代码也能提升交互性能。


有了 bthread 这个工具，用户甚至可以自己实现异步。以“半同步”为例，在 brpc 中用户有多种选择：

1. 发起多个异步 RPC 后挨个 Join，这个函数会阻塞直到 RPC 结束。(这里是为了和 bthread 对比，实现中我们建议你使用 ParallelChannel，而不是自己 Join)
1. 启动多个 bthread 各自执行同步 RPC 后挨个 join bthreads。

哪种效率更高呢？显然是前者。后者不仅要付出创建 bthread 的代价，在 RPC 过程中 bthread 还被阻塞着，不能用于其他用途。
如果仅仅是为了并发 RPC，别用 bthread。

---

不过当你需要==并行计算==时，问题就不同了。使用 bthread 可以简单地构建树形的并行计算，充分利用多核资源。比如检索过程中有三个环节可以并行处理，你可以建立两个 bthread 运行两个环节，在原地运行剩下的环节，最后 join 那两个 bthread。过程大致如下：
```cpp
bool search() {
  ...
  bthread th1, th2;
  if (bthread_start_background(&th1, NULL, part1, part1_args) != 0) {
    LOG(ERROR) << "Fail to create bthread for part1";
    return false;
  }
  if (bthread_start_background(&th2, NULL, part2, part2_args) != 0) {
    LOG(ERROR) << "Fail to create bthread for part2";
    return false;
  }
  part3(part3_args);
  bthread_join(th1);
  bthread_join(th2);
  return true;
}
```
# Links

1. [https://github.com/apache/incubator-brpc/blob/master/docs/cn/bthread.md](https://github.com/apache/incubator-brpc/blob/master/docs/cn/bthread.md)
1. [https://github.com/apache/incubator-brpc/blob/master/docs/cn/threading_overview.md](https://github.com/apache/incubator-brpc/blob/master/docs/cn/threading_overview.md)
1. [https://github.com/apache/incubator-brpc/blob/master/docs/cn/bthread_or_not.md](https://github.com/apache/incubator-brpc/blob/master/docs/cn/bthread_or_not.md)
1. [https://zhuanlan.zhihu.com/p/113427004](https://zhuanlan.zhihu.com/p/113427004)
