# 导语

在前面的文章中我们尝试从 C++17 和 C++20 的角度分别探讨过其中无栈协程的包装机制和使用，但其中的设计由来、原理、剥析的并不多。这也导致对相关特性不太熟悉的读者要理解相关内容存在比较大的成本。本篇我们将更多的回归原理、背后的设计，尝试对整个 C++ 的协程做深入浅出的剥析，方便大家的理解。再结合上层的封装，最终给出一个 C++ 异步框架实际业务使用的一种形态，方便大家更好的在实际项目中应用无栈协程。

# 1. 浅谈协程

在开始展开协程前，我们先来看一下一些非 C++ 语言中的协程实现。

## 1.1 其他语言中的协程实现

很多语言里面，协程是作为 "一类公民" 直接加入到语言特性中的，比如：

### 1.1.1 Dart1.9 示例代码

```dart
Future<int> getPage(t) async {
    var c = new http.Client();
    try {
        var r = await c.get('http://xxx');
        print(r);
        return r.length();
    } finally {
        await c.close();
    }
}
```

### 1.1.2 Python 示例代码

```python
async def abinary(n):
  if n <= 0:
    return 1
  l = await abinary(n-1)
  r = await abinary(n-1)
  return l + 1 + r
```

### 1.1.3 C# 示例代码

```csharp
aysnc Task<string> WaitAsync() 
{
    await Task.Delay(10000);
    return "Finished";
}
```

### 1.1.4 小结

众多语言都实现了自己的协程机制，通过上面的例子，我们也能看到，相关的机制使函数的执行特殊化了，变成了可以多次中断和重入的结构。那么如果 C++ 要支持这种机制，会是一个什么情况呢? 接下来我们将先从最基本的原理逐步展开相关的探讨.

## 1.2 从操作系统的调度说起

我们接触的主流的操作系统，如 Windows，或者 Linux，或者 MacOS，都是抢占式多任务的操作系统，所以大家对抢占式多任务的操作系统会比较熟悉。相关的概念就是 进程->线程 这些，基本上各种语言通过操作系统提供的 API，都能直接获取操作系统提供的这些能力了。其实操作系统按任务的调度方式来区分，有以下两种模式：

* 协作式多任务操作系统
* 抢占式多任务操作系统



抢占式多任务操作系统我们刚刚说过了，而协程本身的特性，跟协作式多任务操作系统所提供的机制基本一致，对于每个 Task，我们可以多次的中断和继续执行，说到这里，熟悉 Dos 开发的同学肯定就会想到 "INT 21H"了，这个其实就是我们早期利用相关机制来实现多任务协同目的的一种方式了，我们也可以看成这是协程最早的雏形.

聊到中断，其中比较重要的就是执行环境的保存和恢复了，而上下文的保存能力可以是操作系统直接提供的，也可以是程序机制自身所提供的了，综上所述，我们大致可以将 C++ 中的协程的实现方案的迭代看成如下情况:

![img](https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-80a18d64cfe3986ae80bd52c41f22906_1440w.webp)

* 最早利用 setjump 来实现的协作式任务调度器
* 系统级实现，如 linux 提供的 ucontext 相关 API，Windows 提供的 Fiber 相关的 API
* 由系统级实现所衍生出的高性能方案，一般是借签系统级的实现，移除一些非必须的操作所达成的，代表的方案有大家熟知的 libco 和 boost::context，也就是我们通常所说的**有栈协程**实现
* 无栈实现，最开始是纯粹使用 **duff device** hack 出来的方案，后续被 MS 规整，部分特性依赖 compiler 实现，逐步演化成现在的 C++20 coroutine 机制了。

## 1.3 协程的执行简介

了解了协程在 C++ 中的部分历史，我们来简单了解一下协程的执行机制，这里我们直接以 C++20 为例，先来看一下概览图:

![img](https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-3abfba937b66c5e9ed84f539eb6e133b_1440w.webp)

关于协程的执行，我们主要关注以下这些地方：

### 1.3.1 中断点和重入点的定义

有栈协程和无栈协程定义中断点和重入点的方式和机制略有差异，执行到中断点和重入点的时候大家使用的保存和恢复机制不太一样，但以 Host App 的视角来看，整体的执行过程其实是比较一致的。这里我们是以 C++20 的无栈协程来举例的，通过图中的关键字 `co_await`，我们定义了 point1 和 point2 两个成对的中断点和重入点。

我们来看一下协程执行到中断点和重入点的时候具体发生的事情：

**中断点:** 协程中断执行的时候，我们需要对当前的执行状态：

* 协程执行到哪了
* 协程当前使用的 context 进行保存，并将程序的执行权归还给外界。此时我们也可以返回必要的值给外界，方便外界更好的对协程的后续执行进行控制.

**重入点:** 重入点是由中断点带出来的概念，既然函数的执行能够被中断 (suspend)，那我们肯定也需要提供机制相关的机制恢复协程的执行了，在复杂执行的时候，我们需要对协程保存的执行状态进行恢复：

* 恢复到上次挂起执行的地方继续执行
* 恢复保存的 context
* 传递必要的值到协程

整个协程的执行区别于普通函数的单次执行返回结果，一般都会有多次的中断与重入，直到协程执行完成或者被外界强行中止。

而有栈协程和无栈协程的实现，差异最大的地方就是如下两点了：

* 怎么保存和恢复当前的执行位置
* 怎么保存和恢复当前协程引用到的内存(变量等) 。本篇主要侧重无栈协程，无栈协程相关的机制后续会具体展开。对有栈协程相关机制感兴趣的可以翻阅 libco或 boost.context 相关的内容进行了解。

## 1.4 小议无栈协程的出现

其实之前介绍 C++ 协程历史的时候，我们有一个问题没有展开，为啥有了像 libco 与 boost.context 这样的高性能有栈协程实现机制后，标准委员会还会继续寻求无栈协程的解决方案，并最终将其作为 C++ 协程的实现机制呢，这里分析主要的原因是为了解决有栈协程天然存在的限制：

* 业务复杂度膨胀带来的爆栈问题
* 使用过大的栈，又会导致协程本身的切换开销上升或者占用内存过多。

而无栈协程解决这些问题的方式也非常直接，既然栈会导致问题，那么我们就直接去除对栈的依赖，通过其他方式来解决数据存储访问的问题。

目前主要的方案是如下两种:

### 1.4.1 Duff Device Hack 实现

我们后面介绍的 C++17 的实现就是基于这种方案，因为仅仅是框架级的实现，我们能够使用的实现方式会受到限制，方案本身存在如栈变量的使用有严格的限制等问题，但对于一些特殊的场合，如基于寄存器实现的 lua vm，这种方式会比较契合。

### 1.4.2 C++20 的 Coroutine

通过后面的分析，我们其实会发现这与 Duff Device Hack 实现是一脉相承的，只是通过 compiler 的配合，像栈变量的自动处理等机制，保证了用户可以低心智负担的使用它。但同时，相对其他语言的实现，因为相关特性的设计是"面向库作者的实现"，实际使用基本都需要二次封装，也就带来了社区很多负面的声音。

## 1.5 小结

前面我们对 C++ 中协程的历史做了简单的铺垫，接下来我们将对 C++17 中基于 Duff Device Hack 的无栈协程实现，以及 C++20 中的无栈协程做更深入的介绍。

# 2. C++17 Stackless Coroutine 实现

在异步操作比较多的情况下，我们就考虑用协程来取代原来的 Callback 设计。但当时的 GCC 用的是 8.3 版本，并不支持 coroutine20，所以我们最终采用的是一个基于 C++17 的无栈协程实现方案，也就是使用前面介绍的 Duff Device Hack 方式实现的无栈协程。我们先来看下当时的项目背景。

## 2.1 项目的背景介绍

当时的情况也比较简单，R 工作室内有多个项目处于预研的状态，所以大家打算协同共建一个工作室内的后台 C++ Framework，用于工作室内几个预研项目中。其中比较重要的一部分就是协程了，当时引入协程的方式和目的都比较直接，首先是使用 Duff Device Hack 的机制来实现整个无栈协程。另外就是整个核心目标是希望通过引入协程和相关的调度器来帮助简化多节点的异步编程支持。整个框架包含的几大部分如下图所示，Coroutine 机制以及相关的 Scheduler 封装是在 app_service 中作为 C++ 微服务的基础设施存在的.

![img](https://pic3.zhimg.com/80/v2-9758db0ef60e0787a0a0b7a0e613d40a_1440w.webp)



实际使用下来，协程和调度器主要带来了以下这些优点：

* 避免大量中间类的定义和使用
* 基于逻辑过程本身用串行的方式实现相关代码即可(可参考后续切场景的例子)
* 更容易写出数据驱动向的实现
* 还有比较关键的一点，可以有效避免过多的异步 Callback 导致的逻辑混乱和难于跟踪调试的问题.

## 2.2 为何从 C++17 说起

我们为什么先从 C++17 的无栈协程开始介绍，这是因为 C++17 的实现与 20 的实现一脉相承。如果我们分析 C++ 20 通过 Compiler 加工后的代码，就会发现这点。相比于 C++20 协程大量的细节隐藏在 Compiler 的处理中(当然我们后面也会介绍怎么查看 Compiler 处理的这部分逻辑)，C++17 的方案，整个组织都在我们自己的代码层面，用于理解无栈协程的整体实现显然是更合适的。另外，相关的调度器的实现，与 C++17 和 C++20 都是兼容的，像我们项目当时的实现，是可以很好的做到 C++20 与 C++17 的协程混用的，也样也方便在过渡阶段，项目可以更平滑的从 C++17 向 C++20 迁移。另外，对于一些不支持 C++20 的受限使用场景，C++17 依然具有它的实用性。

## 2.3 实现概述

我们先来看一下整个机制的概览图:

![img](https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-f979f97dc9ac1bf7d4b4bbec33d131b7_1440w.webp)



从上图中我们能够了解到，整个基于 Duff Device Hack 的无栈协程实现的方式。首先我们通过 CoPromise 对象来保存用作协程的 std::function 对象，另外我们也会记录协程当前的执行状态，其次，我们还会在 CoPromise 中内置一个 std::tuple<> 用于保存我们需要在协程挂起和恢复时保存的状态值.

另外，整个核心的执行机制是依赖于几个核心宏所组成的 switch case 状态机来驱动的。结合上特殊的 **LINE** 宏，我们可以在每个 **co_await()** 对象调用的时候，设置 CoPromise 对象当前的执行状态为 **LINE**，而下次跳转的时候，通过 switch(state) 就能正确跳转到上次执行中断的地方继续往下执行了。当然，我们会看到我们的 `case __LINE__` 其实被穿插到了 `do{ } while(0)` 中间，这个其实就利用到了 duff device 特性，允许你通过 case 快速的跳转到 for 循环或者 while 循环的内部，C 语言一个很特殊的特性。利用这点，首先我们可以完成 **co_awiat()** 宏的封装，其次，我们也能在逻辑代码的 for 循环以及 while 循环中，正确的应用 co_await()，所以说 Duff Device 特性对于整个机制来说，还是比较关键的.

如上例中所述的 Test Code 代码，**co_begin()** 和 **co_end()** 展开后构成了`switch() {}` 的开始和结束部分，而中间我们加入的 **co_await()** 宏，则会展开成用于完成中断点和重入点的 case 逻辑，整体的封装还是很巧妙的。

## 2.4 执行流程概述

整体的执行流程通过上面的分析我们也能比较简单的整理出来: 1。宏展开形成一个跨越协程函数首尾的大的swith case状态机 2。协程执行时构建新的CoPromise对象，正确的处理输入参数，输入参数会被存储在CoPromise对象的std::tuple<>上，并且每次重入时作为函数的入口参数以引用的方式转入函数内部 3。每次Resume()时根据当前CoPromise记录的state，跳转到正确的case label继续往下执行。4。执行到下一个挂起点返回控制权到调度器 5。重复3,4 直到执行结束.

从整体机制上，我们也能简单看到C++17对应实现的一些限制: - __co_begin()前不能有逻辑代码，相关的代码会因为函数的重新执行被反复调用。- 栈变量的使用，因为本身机制的原因，并不能正确的保存栈变量的值，我们需要透过机制本身提供的机制来处理状态值 - 这个指的是被当成std::tuple<>成员存储在CoPromise对象中的那些值，每次函数执行会以引用的方式作为参数传递给协程函数.

## 2.5 另外一个示例代码

```cpp
mScheduler.CreateTask([](int& c，LocalStruct& locals) -> logic::CoTaskForScheduler {
  rco_begin();
  {
    locals.local_i = 1024;
    auto* task = rco_self_task();
    printf("step1 %d\n"，locals.local_i);
  }
  rco_yield_next_frame();
  {
    c = 0;
    while(c < 5) {
      printf("in while loop c = %d\n"，c);
      rco_yield_sleep(1000);
      c++;
    }
    rco_yield_next_frame();
  }
  rco_end();
}，3，LocalStruct{});
```

从上例可以看出，虽然存在上一节中我们提到的一些限制，依照设定的规则进行编码实现，整体使用还是比较简单易懂的。上面的rco_yield_next_frame()和rco_yield_sleep()是利用Scheduler的调度能力封装出来的挂起到下一帧继续恢复执行和休眠这两个异步操作语义.

## 2.6 绕开栈变量限制的方法

提到栈变量的限制，肯定有同学会想到，是否有方法绕开栈变量的限制，用一种更灵活的方式处理协程中临时值的存取，使其在跨越中断点和重入点的情况依然有效? 答案是肯定的。因为我们有明确的与协程关联的状态存储对象CoPromise，所以如果框架中有实现反射或者适应任意类型值存取的类型擦除机制，我们当然能够很简单的对原有的实现进行扩展。在rstudio的框架实现中，我们通过在CoPromise对象上多存储一个额外的`std::map<std::string，reflection::Value>`的成员，再配合适当的包装，就很容易实现如下示例代码所展示的功能了:

```cpp
rco_begin();
{
  rco_set_value("id"，35567);
}
rco_yield_next_frame();
{
  {
    int64_t& val = rco_ref_value("id"，int64_t);
    val = 5;
  }
  locals.local_i = rco_to_value("id"，int);
}
rco_end();
```

通过额外扩展的`rco_set_value()`，`rco_ref_value()`，`rco_to_value()`，我们即完成了一个比较简单易用的通过name对各类型值进行存取的实现，当然，实际操作的其实都是在CoPromise上存储的`std::map<std::string，reflection::Value>`成员。这块是反射的一个简单应用，关于类型擦除的细节，与本篇关联不大，这里不进行具体的展开了.

## 2.7 一个内部项目中后台切场景的代码示例

本章的结尾我们以一个具体的业务实例作为参考，方便大家了解相关的实现在具体业务中的大致工作情形。一个原来参与的项目的后台服务器是多节点的设计，对于切场景来说，需要访问多个节点来完成相关的操作，大致的切场景时序图如下所示:

![img](https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-20bac84f6c850047292a8afff731d8b3_1440w.webp)

删减细节代码之后的主要异步代码如下图所示:

```cpp
rco_begin();
{
    locals.clientReq = req;
    locals.session = CServerUtil::GetSessionObj(sessionId);
    // ..。
    SSTbusppInstanceKey emptyInstKey;
    emptyInstKey.Init();
    if (locals.session->GetTargetGameSvrID() != emptyInstKey) { 
        // ..。
        rco_await(locals.gameSceneService->CheckChangeScene(locals.playerId，locals.checkChangeSceneReq));
        // ..。
        // 保存大世界信息
        // ...
        rco_await(locals.gameSceneService->ExitMainland(locals.playerId，locals.exitMainlandReq));
        // ...
    }
    auto gameMgrClient = GServer->GetRpcClient(TbusppInstanceKey{TBUSPP_SERVER_GAMEMGRSVR，""});
    locals.gameMgrService = rstudio::rpc_proxy::GameMgrService_Proxy::Create(gameMgrClient，GServer->GetRpcScheduler());
    // ...
    LOG_DEBUG(locals.playerId，"[CHANGE SCENE] ready to Queryline group");
}
rco_await(locals.gameMgrService->QueryMainland2(locals.playerId，locals.querySpaceReq));
{
    // ...
    rco_await(locals.gameSceneService->ChangeMainland(locals.playerId，locals.localInstanceKey，locals.changeMainlandReq));
    // ...
}
// ...
LOG_DEBUG(locals.playerId，"[CHANGE SCENE] send change mainland_conf");
rco_emit_finish_event(rstudio::logic::CoRpcFinishEvent(rstudio::reflection::Value(locals.clientRes)));

rco_return;
rco_end();
```

通过rco_await()发起的多个异步Rpc调用，我们很好的完成了上述时序图对应的逻辑功能实现.

> Rpc相关的协程化封装在C++20中会有个相关的示例，此处就不重复展开C++17的实现了.

# 3. C++20 Coroutine 机制简介

了解了C++17的Stackless Coroutine实现机制后，我们接着来看一下C++20 Coroutine的实现。首先我们先来通过核心对象概览图来简单了解一下C++20 Coroutine:

![img](https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-3917932516b478db6b1a51c2149ad33a_1440w.webp)

如图所示，C++ Coroutine20的核心对象有如下这些: 1。Function Body: 通常普通函数添加co_await等协程关键字处理返回值就可以作为一个协程函数。2。coroutine_handle<>: 对协程的生命周期进行控制。3。promise_type: 异常处理，结果接收，同时也可以对协程部分行为进行配置，如协程初始化时的状态，结束时的状态等。4。Awaitable对象: 业务侧的中断重入点定义和数据传输定制点，结合 `co_await` 关键字，我们就能借助compiler实现正确的中断，重入语义了.

从图上也能看到，对比其它语言较精简的Coroutine实现，C++20这套实现，还是偏复杂的，这也是我们常调侃的 "库作者向" 实现，虽然整体使用很灵活，也能跟泛型很好的搭配，但我们还是需要在框架层做大量的包装，同时业务一般需要一个地方对应用中所有的协程做管理，方便监控应用的整体运行情况等，这也使得C++这套特性没法很简单的直接在业务侧进行使用，后续我们讲到Coroutine Scheduler的时候会进一步展开相关的内容.

此处我们只需要对Coroutine的核心对象的构成和作用有个简单的认知，接下来我们会结合相关的示例代码来深入了解C++20 Coroutine的整体运作机制，了解更多细节.

# 4. 结合代码理解 Coroutine

## 4.1 一个简单的示例 - 并不简单

```cpp
#include <iostream>
#include <coroutine>

using namespace std;

struct resumable_thing
{
  struct promise_type
  {
    resumable_thing get_return_object()
    {
      return resumable_thing(coroutine_handle<promise_type>::from_promise(*this));
    }
    auto initial_suspend() { return suspend_never{}; }
    auto final_suspend() noexcept { return suspend_never{}; }
    void return_void() {}

    void unhandled_exception() {}
  };
  coroutine_handle<promise_type> _coroutine = nullptr;
  resumable_thing() = default;
  resumable_thing(resumable_thing const&) = delete;
  resumable_thing& operator=(resumable_thing const&) = delete;
  resumable_thing(resumable_thing&& other)
    : _coroutine(other._coroutine) {
      other._coroutine = nullptr;
    }
  resumable_thing& operator = (resumable_thing&& other) {
    if (&other != this) {
      _coroutine = other._coroutine;
      other._coroutine = nullptr;
    }
  }
  explicit resumable_thing(coroutine_handle<promise_type> coroutine) : _coroutine(coroutine)
  {
  }
  ~resumable_thing()
  {
    if (_coroutine) { _coroutine.destroy(); }
  }
  void resume() { _coroutine.resume(); }
};

resumable_thing counter() {
  cout << "counter: called\n";
  for (unsigned i = 1; ; i++)
  {
    co_await std::suspend_always{};
    cout << "counter:: resumed (#" << i << ")\n";
  }
}

int main()
{
  cout << "main:    calling counter\n";
  resumable_thing the_counter = counter();
  cout << "main:    resuming counter\n";
  the_counter.resume();
  the_counter.resume();
  the_counter.resume();
  the_counter.resume();
  the_counter.resume();
  cout << "main:    done\n";
  return 0;
}
```

从上面的代码我们也能看出，虽然协程函数 `counter()`的定义是简单的，使用也是简单的，但其实包含`promise_type`定义的`resumable_thing`的定义并不简单，相比其他语言，C++的使用明显复杂很多.

相关代码的输出如下:

```text
main:    calling counter
counter: called
main:    resuming counter
counter: resumed (#1)
counter: resumed (#2)
counter: resumed (#3)
counter: resumed (#4)
counter: resumed (#5)
main:    done
```

## 4.2 Coroutine20 的实现猜想

前面我们说过，C++17下对应的实现机制大致如下:

![img](https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-f979f97dc9ac1bf7d4b4bbec33d131b7_1440w.webp)

那么对于C++20来说，它的整体运作机制又是什么样子的呢? 显然，我们从示例代码和前面简单介绍的核心对象，并不能推导出它的运作机制，编译器帮我们做了很多额外的处理，这也导致我们没有办法直接从代码理解它实际的执行情况.

这其实也是C++20 Coroutine使用的一大难点，除了前文提到的，特性通过Awaitable定制点开放给你的地方，整体的运作机制，我们是很难直接得出的。另外，在一些多线程协程混用的复杂情况下，整体运作机制对于我们实现正确的框架，正确的分析解决碰到的问题至关重要。那么我们现在的问题就变成了，怎么去补全出包含编译器处理的整体代码?

## 4.3 借助 "cppinsights"

因为C++各种复杂的compiler处理机制，已经有相关的compiler预处理分析的工具被开发出来了，我们这里用的是一个叫 `cppinsights` 的工具，这是一个基于web的工具，所以我们打开网页即可使用它，网址是 [cppinsights.io](https://zhuanlan.zhihu.com/cppinsights.io) 工具的截图如下:

![img](https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-42488f05c319ef53dece8686bd369624_1440w.webp)

`cppinsights`本身是基于clang的，提供了多种clang compiler预处理信息的查看，比如我们现在需要用到的coroutine transformation:

![img](https://pic3.zhimg.com/80/v2-f735f06944f5cccb8e53b41233bc701e_1440w.webp)

对于前面的示例代码，我们通过`cppinsights`处理后生成的代码如下:

```cpp
/*************************************************************************************
 * NOTE: The coroutine transformation you've enabled is a hand coded transformation! *
 *       Most of it is _not_ present in the AST。What you see is an approximation。  *
 *************************************************************************************/
#include <iostream>
#include <coroutine>

using namespace std;

struct resumable_thing
{
  struct promise_type
  {
    inline resumable_thing get_return_object()
    {
      return resumable_thing(resumable_thing(std::coroutine_handle<promise_type>::from_promise(*this)));
    }

    inline std::suspend_never initial_suspend()
    {
      return std::suspend_never{};
    }

    inline std::suspend_never final_suspend() noexcept
    {
      return std::suspend_never{};
    }

    inline void return_void()
    {
    }

    inline void unhandled_exception()
    {
    }

    // inline constexpr promise_type() noexcept = default;
  };

  std::coroutine_handle<promise_type> _coroutine;
  inline constexpr resumable_thing() /* noexcept */ = default;
  // inline resumable_thing(const resumable_thing &) = delete;
  // inline resumable_thing & operator=(const resumable_thing &) = delete;
  inline resumable_thing(resumable_thing && other)
  : _coroutine{std::coroutine_handle<promise_type>(other._coroutine)}
  {
    other._coroutine.operator=(nullptr);
  }

  inline resumable_thing & operator=(resumable_thing && other)
  {
    if(&other != this) {
      this->_coroutine.operator=(other._coroutine);
      other._coroutine.operator=(nullptr);
    } 

  }

  inline explicit resumable_thing(std::coroutine_handle<promise_type> coroutine)
  : _coroutine{std::coroutine_handle<promise_type>(coroutine)}
  {
  }

  inline ~resumable_thing() noexcept
  {
    if(static_cast<bool>(this->_coroutine.operator bool())) {
      this->_coroutine.destroy();
    } 

  }

  inline void resume()
  {
    this->_coroutine.resume();
  }

};



struct __counterFrame
{
  void (*resume_fn)(__counterFrame *);
  void (*destroy_fn)(__counterFrame *);
  std::__coroutine_traits_impl<resumable_thing>::promise_type __promise;
  int __suspend_index;
  bool __initial_await_suspend_called;
  unsigned int i;
  std::suspend_never __suspend_44_17;
  std::suspend_always __suspend_48_14;
  std::suspend_never __suspend_44_17_1;
};

resumable_thing counter()
{
  /* Allocate the frame including the promise */
  __counterFrame * __f = reinterpret_cast<__counterFrame *>(operator new(__builtin_coro_size()));
  __f->__suspend_index = 0;
  __f->__initial_await_suspend_called = false;

  /* Construct the promise。*/
  new (&__f->__promise)std::__coroutine_traits_impl<resumable_thing>::promise_type{};

  resumable_thing __coro_gro = __f->__promise.get_return_object() /* NRVO variable */;

  /* Forward declare the resume and destroy function。*/
  void __counterResume(__counterFrame * __f);
  void __counterDestroy(__counterFrame * __f);

  /* Assign the resume and destroy function pointers。*/
  __f->resume_fn = &__counterResume;
  __f->destroy_fn = &__counterDestroy;

  /* Call the made up function with the coroutine body for initial suspend.
     This function will be called subsequently by coroutine_handle<>::resume()
     which calls __builtin_coro_resume(__handle_) */
  __counterResume(__f);


  return __coro_gro;
}

/* This function invoked by coroutine_handle<>::resume() */
void __counterResume(__counterFrame * __f)
{
  try 
  {
    /* Create a switch to get to the correct resume point */
    switch(__f->__suspend_index) {
      case 0: break;
      case 1: goto __resume_counter_1;
      case 2: goto __resume_counter_2;
    }

    /* co_await insights.cpp:44 */
    __f->__suspend_44_17 = __f->__promise.initial_suspend();
    if(!__f->__suspend_44_17.await_ready()) {
      __f->__suspend_44_17.await_suspend(std::coroutine_handle<resumable_thing::promise_type>::from_address(static_cast<void *>(__f)).operator coroutine_handle());
      __f->__suspend_index = 1;
      __f->__initial_await_suspend_called = true;
      return;
    } 

    __resume_counter_1:
    __f->__suspend_44_17.await_resume();
    std::operator<<(std::cout，"counter: called\n");
    for( __f->i = 1; ; __f->i++) {

      /* co_await insights.cpp:48 */
      __f->__suspend_48_14 = std::suspend_always{};
      if(!__f->__suspend_48_14.await_ready()) {
        __f->__suspend_48_14.await_suspend(std::coroutine_handle<resumable_thing::promise_type>::from_address(static_cast<void *>(__f)).operator coroutine_handle());
        __f->__suspend_index = 2;
        return;
      } 

      __resume_counter_2:
      __f->__suspend_48_14.await_resume();
      std::operator<<(std::operator<<(std::cout，"counter:: resumed (#").operator<<(__f->i)，")\n");
    }

    goto __final_suspend;
  } catch(...) {
    if(!__f->__initial_await_suspend_called) {
      throw ;
    } 

    __f->__promise.unhandled_exception();
  }

  __final_suspend:

  /* co_await insights.cpp:44 */
  __f->__suspend_44_17_1 = __f->__promise.final_suspend();
  if(!__f->__suspend_44_17_1.await_ready()) {
    __f->__suspend_44_17_1.await_suspend(std::coroutine_handle<resumable_thing::promise_type>::from_address(static_cast<void *>(__f)).operator coroutine_handle());
  } 

  ;
}

/* This function invoked by coroutine_handle<>::destroy() */
void __counterDestroy(__counterFrame * __f)
{
  /* destroy all variables with dtors */
  __f->~__counterFrame();
  /* Deallocating the coroutine frame */
  operator delete(__builtin_coro_free(static_cast<void *>(__f)));
}



int main()
{
  std::operator<<(std::cout，"main:    calling counter\n");
  resumable_thing the_counter = counter();
  std::operator<<(std::cout，"main:    resuming counter\n");
  the_counter.resume();
  the_counter.resume();
  the_counter.resume();
  the_counter.resume();
  the_counter.resume();
  std::operator<<(std::cout，"main:    done\n");
  return 0;
}
```

> cppinsights本身也跟Compiler Explorer做了拉通，做代码深度分析的时候，更多的结合这些开源工具，很多时候还是非常有帮助的.

那么有了compiler预处理后的代码，再来分析C++20 Coroutine的机制，就变得简单了.

## 4.4 Coroutine20 基本结构 - Compiler视角

对于compiler预处理后的代码，我们直接结合结构图来分析:

![img](https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-664d0809a1cedd23ff6d5b14e8e4080d_1440w.webp)



我们会发现，couter被编译器处理后基本就只是一个空壳函数了，原来的实现逻辑被整体搬入了一个编译器帮我们定义的函数`__coutnerResume()`中，然后出现了一个编译器帮我们定义的对象`__couterFrame`，通过分析代码很容易知道，`__counterFrame`结构主要完成几部分的事情: 1。virtual table部分，正确的告知你协程使用的resume函数以及destroy函数 2。自动处理的栈变量，如下图中所示的i 3。各种使用到的awaitable object，这是因为awaitable object本身也是有状态的，需要正确记录 4。当前执行到的位置，这个是通过整形的`__suspend_index`来记录的.

当我们观察`__counterResume()`的实现，有趣的事情来了，我们发现，其实C++20也是使用一个大的switch-case来作为协程执行的全局状态机，只不过每个case lablel后面，接的是goto，而不是像我们在C++17下面那样，直接嵌入的业务代码.

整体C++20的实现思路，基本上与17的实现思路是一脉相承的，只不过得益于compiler的支持，很多事情我们都由主动处理 -> 自动处理.

## 4.5 Compiler视角重新分析示例代码

### 4.5.1 `couter()` - Function Body



![img](https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-3083619612a2ab67beb0fca7badc5a3f_1440w.webp)

我们知道，`couter()`会被编译器改写，最终其实是变成了三个函数: 1。单纯负责生命周期以及生成正确的`__counterFrame`对象的`counter()`，只是一个协程入口函数。2。负责真正执行逻辑的 `__counterResume()`函数，它的输入参数就是`__counterFrame`对象。3。负责删除__counterFrame对象的 `__counterDestroy()`函数.

通过一拆三，编译器很好的解决了协程的入口，协程的中断重入，和协程以及相关对象的销毁的问题.

### 4.5.2 `coroutine_handle<>`



![img](https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-dd651d40505808ebdf568a48cf47e230_1440w.webp)

部分`coroutine_handle<>`的定义代码如下

```cpp
template <> struct coroutine_handle<void>{
  constexpr coroutine_handle() noexcept;
  constexpr coroutine_handle(nullptr_t) noexcept;
  coroutine_handle& operator=(nullptr_t) noexcept;
  constexpr void* address() const noexcept;
  constexpr static coroutine_handle from_address(void* addr);
  constexpr explicit operator bool() const noexcept;
  bool done() const;
  void operator()();
  void resume();
  void destroy();
private:
  void* ptr;// exposition only
};
```

我们结合前面展开的代码，已经很好理解`coroutine_handle<>`为何会有协程生命周期控制的能力了，因为它关联了`xxxFrame`对象，而通过前面的分析，`xxxFrame`的是虚表记录了协程resume和destroy的函数，所以这个地方的ptr，其实就是一个`xxxFrame`对象，正确的关联了`xxxFrame`对象，透过它，我们自然能够拥有`resume()`，`destroy()`等一系列的能力了，这里并没有任何魔法的存在.

```cpp
template <typename Promise>
struct coroutine_handle
: coroutine_handle<void>
{
  Promise& promise() const noexcept;
  static coroutine_handle from_promise(Promise&) noexcept;
};
```

另外通过继承的方式，`coroutine_handle<>`完成了与Promise对象关联和转换的功能.

### 4.5.3 `promise_type`



![img](https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-a0eb997751004b380ad20c297b77cf1c_1440w.webp)

同样，我们结合预处理后的代码:

```cpp
/* This function invoked by coroutine_handle<>::resume() */
void __counterResume(__counterFrame * __f)
{
  try 
  {
    /* Create a switch to get to the correct resume point */
    switch(__f->__suspend_index) {
      case 0: break;
      case 1: goto __resume_counter_1;
      case 2: goto __resume_counter_2;
    }
    /* initial suspend handle here~~ */
    __f->__suspend_44_17 = __f->__promise.initial_suspend();
__resume_counter_1:
    /* do somthing for yield~~ */
__resume_counter_2:
    /* do somthing for resume~~ */
    goto __final_suspend;
  } catch(...) {
    if(!__f->__initial_await_suspend_called) {
      throw ;
    } 
    __f->__promise.unhandled_exception();
  }
__final_suspend:
  /* final suspend here~~ */
  __f->__suspend_44_17_1 = __f->__promise.final_suspend();
}
```

通过`__counterResume()`的逻辑实现，promise为何可以对协程的初始化和结束行为进行控制，也很一目了然了，因为`__counterFrame`对象中关联了我们定义的`promise_type`类型，所以我们也能很直接的通过`__counterFrame`访问到`promise_type`类型，一方面充当配置项的角色，如控制`initial_suspend`，`final_suspend`。另外，`promise_type`也作为一个Wrapper，对如`co_yield`等进行转义执行，以及异常的转发处理，也是非常好理解的机制.

### 4.5.4 Awaitable 对象



![img](https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-6fe1f7212e4627f93e3a10546f3e0cf0_1440w.webp)

常见的awaitable对象如我们示例中看到的，系统预定义的: - `std:suspend_always` - `std::suspend_never` 另外我们也能通过多种方式定义awaitable对象: - 通过重载`promise_type`的`await_transform()` - 这是asio所使用的方式，侵入性比较强 - 通过为对象实现`operator co_await()` - 通过实现awaitable对象需要的三个子函数`await_ready()`，`await_suspend()`，`await_resume()` - 推荐的方式 那么当我们调用`co_await awaitable`的时候，发生的事情是什么呢，我们同样通过预处理的代码来进行了解:

```cpp
__resume_counter_1:
    __f->__suspend_44_17.await_resume();
    std::operator<<(std::cout，"counter: called\n");
    for( __f->i = 1; ; __f->i++) {

      /* co_await insights.cpp:48 */
      __f->__suspend_48_14 = std::suspend_always{};
      if(!__f->__suspend_48_14.await_ready()) {
        __f->__suspend_48_14.await_suspend(coroutine_handle);
        __f->__suspend_index = 2;
        return;
      } 
__resume_counter_2:
      __f->__suspend_48_14.await_resume();
      std::cout << "counter:: resumed (#" << __f->i << ")\n";
    }
```

对于每一次的`co_await`，编译器处理后的代码，都会形成一个`中断点` 和一个`重入点`，其实对应的是两个状态，刚开始执行的时候，进入的是中断点的逻辑，也就是我们看到的`__resume_counter_1`对应label的代码，而重入点则是`__resume_counter_2`对应label的代码，结合此处展开的实例代码，我们也能很好的理解awaitable三个子函数的具体作用了: - `await_ready()` - 判断是否需要挂起，如不需要挂起，则直接执行后续逻辑，这里也就是继续到`__resume_counter_2`这个label执行重入点的逻辑 - `await_suspend()` - 中断点触发的时候执行的逻辑，业务中我们一般在此处发起异步操作 - `await_resume()` - 重入点触发的时候执行的逻辑。整体的机制是不是清晰了很多?

## 4.6 小结 - C++20 协程的特点总结

我们总结C++20协程的特点: - 一套理解上稍显复杂，需要结合cppinsights等工具才能了解整体的运行机制 - 适当封装，还是能够很好的满足业务需求 - 对比17版本的实现，20版基本上没有什么使用上的限制 - 自动栈变量的处理，可以让业务侧以更低的心智负担来进行开发 - 通过Awaitable对象，我们能够扩展`co_await`支持的业务，这种实现侵入性低，实际使用负担小 - 对于异步操作较多，多节点较多，特别是多个异步操作级联的使用场景，很值得实装。- 最后我们讲解使用的是clang，但对于gcc，msvc，这些同样适用，标准的提案来源是一致的，都是msvc发起的那份，compiler实现上存在一些细微的差异，但基本不影响使用.

# 5. Coroutine Scheduler

## 5.1 Sheduler 实现的动机

前面我们也提到了，要做到 "库作者向特性" => 面向业务的异步框架，我们还需要一些额外的工作，这就是我们马上要介绍的Coroutine Scheduler - 协程调度器.

## 5.2 Scheduler 核心机制



![img](https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-f7637d7764faafda099bc1a09941329f_1440w.webp)

如上图所示，Scheduler主要提供对SchedTask的管理，以及两个基础机制（对比17版的三个）方便协程相关业务机制的实现:

1. **Awaitable机制**: 前面也介绍了利用c++20的co_await关键字和awaitable对象， 我们可以很好的定义挂起点， 以及交换协程和外部系统的数据。
2. **Return Callback机制**: 部分协程执行完后需要向外界反馈执行结果(如协程模式执行的Rpc Service).

## 5.3 Scheduler核心对象

### 5.3.1 ISchedTask & SchedTaskCpp20

```cpp
using CoReturnFunction = std::function<void(const CoReturnObject*)>;

class ISchedTask
{
    friend class Scheduler;
  public:
    ISchedTask() = delete;
    ISchedTask(const SchedTaskCpp17&) = delete;
    ISchedTask(uint64_t taskId，Scheduler* manager);
    virtual ~ISchedTask();
    uint64_t GetId() const;
    virtual int Run() = 0;
    virtual bool IsDone() const = 0;
    virtual CO_TASK_STATE GetCoState() const = 0;
    void BindSleepHandle(uint64_t handle);
    AwaitMode GetAwaitMode() const;
    int GetAwaitTimeout() const;
    template<typename AwaitEventType>
    auto BindResumeObject(AwaitEventType&& awaitEvent)->std::enable_if_t<std::is_base_of<ResumeObject，AwaitEventType>::value>;
    template<typename AwaitEventType>
    auto GetResumeObjectAsType()->std::enable_if_t<std::is_base_of<ResumeObject，AwaitEventType>::value，AwaitEventType*>;
    bool HasResumeObject() const noexcept;
    void ClearResumeObject();
    bool IsLastInvokeSuc() const noexcept;
    bool IsLastInvokeTimeOut() const noexcept;
    bool IsLastInvokeFailed() const noexcept;
    void AddChildTask(uint64_t tid);
    void AddWaitNofityTask(uint64_t tid);
    const auto& GetChildTaskArray() const;
    const auto& GetWaitNotifyArray() const;
    void Terminate();
    Scheduler* GetManager() const;
    static ISchedTask* CurrentTask();
    void DoYield(AwaitMode mode，int awaitTimeMs = 0);
    void SetReturnFunction(CoReturnFunction&& func);
    void DoReturn(const CoReturnObject& obj);
    void DoReturn();
  protected:
    uint64_t                    mTaskId;
    Scheduler*                  mManager;
    std::vector<uint64_t>       mChildArray;
    std::vector<uint64_t>       mWaitNotifyArray;
    //value used to return from coroutine
    AwaitMode                   mAwaitMode = AwaitMode::AwaitDoNothing;
    int                         mAwaitTimeout = 0;
    //value used to send to coroutine(now as a AwaitEvent)
    reflection::UserObject      mResumeObject;
    uint64_t                    mSleepHandle = 0;
    bool                        mIsTerminate = false;
    CoReturnFunction            mCoReturnFunc;
};

class SchedTaskCpp20: public ISchedTask
{
  public:
    SchedTaskCpp20(uint64_t taskId，CoTaskFunction&& taskFunc，Scheduler* manager);
    ~SchedTaskCpp20();
    int Run() override;
    bool IsDone() const override;
    CO_TASK_STATE GetCoState() const override;
    void BindSelfToCoTask();
    const CoResumingTaskCpp20& GetResumingTask() const;
  protected:
    CoResumingTaskCpp20         mCoResumingTask;
    CoTaskFunction              mTaskFuncion;
};
```

C++20的SchedTaskCpp20主要完成对协程对象的封装， CoTaskFunction用于存储相关的函数对象， 而CoResumingTaskCpp20则如同前面示例中的resumable_thing对象，内部有需要的promise_type实现， 我们对协程的访问也是通过它来完成的。

> 此处需要注意的是我们保存了协程对象外， 还额外保存了相关的函数对象， 这是因为如果协程本身是一个lambda，compiler并不会帮我们正确维护lambda的生命周期以及lambda所捕获的函数， 尚未清楚是实现缺陷还是功能就是如此， 所以此处需要一个额外存在的std::function<>对象， 来保证对应lambda的生命周期是正确的。

对比17的实现， 我们的SchedTask对象中主要保留了： **reflection::UserObject mResumeObject**: 主要用于异步等待的执行，当一个异步等待成功执行的时候，向协程传递值。

原来利用事件去处理最终返回值的机制也替换成了Return回调的方式，相对来说更简单直接， 利用lambda本身也能很方便的保存需要最终回传的临时值了。

### 5.3.2 Scheduler

Scheduler的代码比较多，主要就是SchedTask的管理器，另外也完成对前面提到的三种机制的支持，文章重点分析一下三种机制的实现代码.

### 5.3.3 Yield 处理

```cpp
void Scheduler::Update()
{
    RSTUDIO_PROFILER_METHOD_INFO(sUpdate，"Scheduler::Update()"，rstudio::ProfilerGroupType::kLogicJob);
    RSTUDIO_PROFILER_AUTO_SCOPE(sUpdate);

    //Handle need kill task first
    while(!mNeedKillArray.empty())
    {
        auto tid = mNeedKillArray.front();
        mNeedKillArray.pop();
        auto* tmpTask = GetTaskById(tid);
        if (tmpTask != nullptr)
        {
            DestroyTask(tmpTask);
        }
    }

    //Keep a temp queue for not excute next frame task right now
    decltype(mFrameStartTasks) tmpFrameTasks;
    mFrameStartTasks.swap(tmpFrameTasks);

    while (!tmpFrameTasks.empty())
    {
        auto task_id = tmpFrameTasks.front();
        tmpFrameTasks.pop();
        auto* task = GetTaskById(task_id);
        LOG_CHECK_ERROR(task);
        if (task)
        {
            AddToImmRun(task);
        }
    }
}

void Scheduler::AddToImmRun(ISchedTask* schedTask)
{
    LOG_PROCESS_ERROR(schedTask);
    schedTask->Run();

    if (schedTask->IsDone())
    {
        DestroyTask(schedTask);
        return;
    }

    {
        auto awaitMode = schedTask->GetAwaitMode();
        auto awaitTimeoutMs = schedTask->GetAwaitTimeout();
        switch (schedTask->GetAwaitMode())
        {
            case rstudio::logic::AwaitMode::AwaitNever:
                AddToImmRun(schedTask);
                break;
            case rstudio::logic::AwaitMode::AwaitNextframe:
                AddToNextFrameRun(schedTask);
                break;
            case rstudio::logic::AwaitMode::AwaitForNotifyNoTimeout:
            case rstudio::logic::AwaitMode::AwaitForNotifyWithTimeout:
                {
                    HandleTaskAwaitForNotify(schedTask，awaitMode，awaitTimeoutMs);
                }
                break;
            case rstudio::logic::AwaitMode::AwaitDoNothing:
                break;
            default:
                RSTUDIO_ERROR(CanNotRunToHereError());
                break;
        }
    }
    Exit0:
    return;
}
```

上面是Scheduler的Update()以及Update用到的核心函数AddToImmRun()的实现代码，在每个task->Run()后，到达下一个挂起点，返回外部代码的时候，外部代码会根据Task当前的AwaitMode对协程后续行为进行控制，主要是以下几种模式:

1. **rstudio::logic::AwaitMode::AwaitNever**: 立即将协程加入回mReadyTask队列，对应协程会被马上唤醒执行
2. **rstudio::logic::AwaitMode::AwaitNextframe**: 将协程加入到下一帧执行的队列，协程将会在下一帧被唤醒执行
3. **rstudio::logic::AwaitMode::AwaitForNotifyNoTimeout**: 等待外界通知后再唤醒执行(无超时模式)，注意该模式下如果一直没收到通知，相关协程会一直在队列中存在.
4. **rstudio::logic::AwaitMode::AwaitForNotifyWithTimeout**:同3，差别是存在一个超时时间，超时时间到了也会唤醒协程，业务方可以通过ResumeObject判断协程是被超时唤醒的.
5. **rstudio::logic::AwaitMode::AwaitDoNothing:**特殊的AwaitHandle实现会使用该模式，比如删除Task的实现，都要删除Task了，我们肯定不需要再将Task加入任何可唤醒队列了.

### 5.3.4 Resume 处理

Resume机制主要是通过唤醒在Await队列中的协程的时候向关联的Task对象传递ResumeObject实现的:

```cpp
//Not a real event notify here，just do need things
template <typename E>
auto ResumeTaskByAwaitObject(E&& awaitObj) 
    -> std::enable_if_t<std::is_base_of<ResumeObject，E>::value>
{
    auto tid = awaitObj.taskId;
    if (IsTaskInAwaitSet(tid))
    {
        //Only in await set task can be resume
        auto* task = GetTaskById(tid);
        if (RSTUDIO_LIKELY(task != nullptr))
        {
            task->BindResumeObject(std::forward<E>(awaitObj));
            AddToImmRun(task);
        }

        OnTaskAwaitNotifyFinish(tid);
    }
}
```

然后再通过rco_get_resume_object()宏在协程代码中获取对应的ResumeObject。宏的声明代码如下:

```cpp
#define rco_get_resume_object(ResumeObjectType)                     rco_self_task()->GetResumeObjectAsType<ResumeObjectType>()
```

本身就是一个简单的传值取值的过程。注意传递ResumeObject后，我们也会马上将协程加入到mReadTasks队列中以方便在接下来的Update中唤醒它.

### 5.3.5 一个 Awaitable 实现的范例

我们以Rpc的协程化Caller实现为例， 看看一个awaitable对象应该如何构造:

```cpp
class RSTUDIO_APP_SERVICE_API RpcRequest
{
  public:
    RpcRequest() = delete;
    ////RpcRequest(const RpcRequest&) = delete;
    ~RpcRequest() = default;

    RpcRequest(const logic::GameServiceCallerPtr& proxy，
               const std::string_view funcName，
               reflection::Args&& arg，int timeoutMs) :
    mProxy(proxy)
        ，mFuncName(funcName)
        ，mArgs(std::forward<reflection::Args>(arg))
        ，mTimeoutMs(timeoutMs)
    {}
    bool await_ready()
    {
        return false;
    }
    void await_suspend(coroutine_handle<>) const noexcept
    {
        auto* task = rco_self_task();
        auto context = std::make_shared<ServiceContext>();
        context->TaskId = task->GetId();
        context->Timeout = mTimeoutMs;
        auto args = mArgs;
        mProxy->DoDynamicCall(mFuncName，std::move(args)，context);
        task->DoYield(AwaitMode::AwaitForNotifyNoTimeout);
    }
    ::rstudio::logic::RpcResumeObject* await_resume() const noexcept
    {
        return rco_get_resume_object(logic::RpcResumeObject);
    }
  private:
    logic::GameServiceCallerPtr                 mProxy;
    std::string                                 mFuncName;
    reflection::Args                            mArgs;
    int                                         mTimeoutMs;
};
```

重点是前面说到的await_ready()，await_suspend()，await_resume()函数的实现。

### 5.3.6 ReturnCallback 机制

有一些场合，可能需要协程执行完成后向业务系统发起通知并传递返回值，比如Rpc Service的协程支持实现等，这个特性其实比较类似go的defer，只是这里的实现更简单，只支持单一函数的指定而不是队列。我们直接以RpcService的协程支持为例来看一下这一块的具体使用.

首先是业务侧，在创建完协程后，需要给协程绑定后续协程执行完成后做进一步操作需要的数据:

```cpp
task->SetReturnFunction(
    [this，server，entity，cmdHead，routerAddr，
     reqHead，context](const CoReturnObject* obj) {
    const auto* returnObj = dynamic_cast<const CoRpcReturnObject*>(obj);
    if (RSTUDIO_LIKELY(returnObj))
    {
        DoRpcResponse(server，entity.get()，routerAddr，&cmdHead,
                      reqHead，const_cast<ServiceContext&>(context),
                      returnObj->rpcResultType，
                      returnObj->totalRet，returnObj->retValue);
    }
});
```

这里将Connection id等信息通过lambda的capture功能直接绑定到SchedTask的返回函数，然后业务代码会利用co_return本身的功能向promise_type传递返回值:

```cpp
CoTaskInfo HeartBeatService::DoHeartBeat(
    logic::Scheduler& scheduler，int testVal)
{
    return scheduler.CreateTask20(
        [testVal]() -> logic::CoResumingTaskCpp20 {

            co_await logic::cotasks::Sleep(1000);

            printf("service yield call finish!\n");

            co_return CoRpcReturnObject(reflection::Value(testVal + 1));
        }
    );
}
```

最终我们利用promise_type的return_value()来完成对设置的回调的调用：

```cpp
void CoResumingTaskCpp20::promise_type::return_value(const CoReturnObject& obj)
{
    auto* task = rco_self_task();
    task->DoReturn(obj);
}
```

注意这个地方task上存储的ExtraFinishObject会作为event的一部分直接传递给业务系统，并在发起事件后调用删除协程任务的方法.

对比原版17的Finish Event实现， 通过Return Callback的方式来对一些特殊的返回进行处理， 这种机制是更容易使用的。

## 5.4 示例代码

```cpp
//C++ 20 coroutine
auto clientProxy = mRpcClient->CreateServiceProxy("mmo.HeartBeat");
mScheduler.CreateTask20([clientProxy]() 
                        -> rstudio::logic::CoResumingTaskCpp20 {
    auto* task = rco_self_task();

    printf("step1: task is %llu\n"，task->GetId());
    co_await rstudio::logic::cotasks::NextFrame{};

    printf("step2 after yield!\n");
    int c = 0;
    while (c < 5) {
        printf("in while loop c=%d\n"，c);
        co_await rstudio::logic::cotasks::Sleep(1000);
        c++;
    }
    for (c = 0; c < 5; c++) {
        printf("in for loop c=%d\n"，c);
        co_await rstudio::logic::cotasks::NextFrame{};
    }

    printf("step3 %d\n"，c);
    auto newTaskId = co_await rstudio::logic::cotasks::CreateTask(false，
                                        []()-> logic::CoResumingTaskCpp20 {
        printf("from child coroutine!\n");
        co_await rstudio::logic::cotasks::Sleep(2000);
        printf("after child coroutine sleep\n");
    });
    printf("new task create in coroutine: %llu\n"，newTaskId);
    printf("Begin wait for task!\n");
    co_await rstudio::logic::cotasks::WaitTaskFinish{ newTaskId，10000 };
    printf("After wait for task!\n");

    rstudio::logic::cotasks::RpcRequest 
        rpcReq{clientProxy，"DoHeartBeat"，rstudio::reflection::Args{ 3 }，5000};
    auto* rpcret = co_await rpcReq;
    if (rpcret->rpcResultType == rstudio::network::RpcResponseResultType::RequestSuc) {
        assert(rpcret->totalRet == 1);
        auto retval = rpcret->retValue.to<int>();
        assert(retval == 4);
        printf("rpc coroutine run suc，val = %d!\n"，retval);
    }
    else {
        printf("rpc coroutine run failed! result = %d \n"，(int)rpcret->rpcResultType);
    }
    co_await rstudio::logic::cotasks::Sleep(5000);
    printf("step4，after 5s sleep\n");
    co_return rstudio::logic::CoNil;
} );
```

执行结果:

```text
step1: task is 1
step2 after yield!
in while loop c=0
in while loop c=1
in while loop c=2
in while loop c=3
in while loop c=4
in for loop c=0
in for loop c=1
in for loop c=2
in for loop c=3
in for loop c=4
step3 5
new task create in coroutine: 2
Begin wait for task!
from child coroutine!
after child coroutine sleep
After wait for task!
service yield call finish!
rpc coroutine run suc，val = 4!
step4，after 5s sleep
```

对比17的实现， 主要的好处是：

1. 代码更精简了
2. Stack变量可以被Compiler自动处理， 正常使用了。
3. co_await可以直接返回值， 并有强制的类型约束了。
4. 一个协程函数就是一个返回值为logic::CoResumingTaskCpp20类型的lambda，可以充分利用lambda本身的特性还实现正确的逻辑了。

# 6. Scheduler 的使用

## 6.1 示例代码

```cpp
//C++ 20 coroutine
auto clientProxy = mRpcClient->CreateServiceProxy("mmo.HeartBeat");
mScheduler.CreateTask20([clientProxy]() 
                        -> rstudio::logic::CoResumingTaskCpp20 {
    auto* task = rco_self_task();

    printf("step1: task is %llu\n"，task->GetId());
    co_await rstudio::logic::cotasks::NextFrame{};

    printf("step2 after yield!\n");
    int c = 0;
    while (c < 5) {
        printf("in while loop c=%d\n"，c);
        co_await rstudio::logic::cotasks::Sleep(1000);
        c++;
    }
    for (c = 0; c < 5; c++) {
        printf("in for loop c=%d\n"，c);
        co_await rstudio::logic::cotasks::NextFrame{};
    }

    printf("step3 %d\n"，c);
    auto newTaskId = co_await rstudio::logic::cotasks::CreateTask(false，
                                        []()-> logic::CoResumingTaskCpp20 {
        printf("from child coroutine!\n");
        co_await rstudio::logic::cotasks::Sleep(2000);
        printf("after child coroutine sleep\n");
    });
    printf("new task create in coroutine: %llu\n"，newTaskId);
    printf("Begin wait for task!\n");
    co_await rstudio::logic::cotasks::WaitTaskFinish{ newTaskId，10000 };
    printf("After wait for task!\n");

    rstudio::logic::cotasks::RpcRequest 
        rpcReq{clientProxy，"DoHeartBeat"，rstudio::reflection::Args{ 3 }，5000};
    auto* rpcret = co_await rpcReq;
    if (rpcret->rpcResultType == rstudio::network::RpcResponseResultType::RequestSuc) {
        assert(rpcret->totalRet == 1);
        auto retval = rpcret->retValue.to<int>();
        assert(retval == 4);
        printf("rpc coroutine run suc，val = %d!\n"，retval);
    }
    else {
        printf("rpc coroutine run failed! result = %d \n"，(int)rpcret->rpcResultType);
    }
    co_await rstudio::logic::cotasks::Sleep(5000);
    printf("step4，after 5s sleep\n");
    co_return rstudio::logic::CoNil;
} );
```

## 6.2 小议 C++20 Coroutine 对比 C++17 Coroutine 带来的改进

通过前面的介绍，我们很容易得出以下几个C++20 Coroutine的优势: 1。原生关键字co_await，co_return的支持，业务侧使用代码更加精简，也进一步统一了大家对无栈协程的标准理解。2。Stack变量可以被compiler自动处理，这点对比C++17 需要自行组织状态变量来说是非常节约心智负责的。3。`co_await`可以直接返回对应类型的值，这样协程本身就有了强制的类型约束，整体业务的表达也会因为不需要从类型擦除的对象获取需要的类型，变得更顺畅.

# 7. 一个有意思的实例

我们思考一个问题，如果部分使用OOP进行设计的系统，使用协程的思路重构，会是什么样子的? 刚好笔者原来的某个项目是使用Python作为脚本，当时尝试使用Python的Coroutine实现了一版技能系统，今天我们来尝试使用C++20 Coroutine重新实现它，这样也能够对比一下，在有协程调度器存在的情况下，业务侧对协程的使用感受，与其他语言如Python中的差异.

## 7.1 一个 Python 实现的技能示例

我们以一个原来在python中利用包装的协程调度器实现的技能系统为例， 先来看看相关的实现效果和核心代码。

> python的stackless协程实现不是我们关注的重点，参考的第一个链接是相关的实现思路，感兴趣的可以打开相关链接详细了解， 此处就不再展开细说了。

### 7.1.1 实现效果

以下是相关实现的示例效果， 主要是一个火球技能和实现和一个闪电链技能的实现:

![动图封面](https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-579cd87da6b6d0078d30ca2465a18f05_b.jpg)



### 7.1.2 技能主流程代码

我们先来看一下技能的主流程代码， 可以发现使用协程方式实现， 整个代码更函数式， 区别于面向对象构造不同对象存储中间态数据的设计。

```python
# handle one skill instance create
def skill_instance_run_func(instance，user，skill_data，target，target_pos，finish_func):
    # set return callback here
    yield TaskSetExitCallback(finish_func)
    # ..。some code ignore here
    from common.gametime import GameTime
    init_time = GameTime.now_time
    for skill_step in step_list:
        step_start_time = GameTime.now_time
        # ..。some code ignore here
        ### 1。period task handle
        if skill_step.cast_type == CastSkillStep.CAST_TYPE_PERIOD:
            #..。some code ignore here
        ### 2。missle skill
        elif skill_step.cast_type == CastSkillStep.CAST_TYPE_MISSLE_TO_TARGET:
            if len(skill_step.cast_action_group_list) > 0:
                action_group = skill_step.cast_action_group_list[0]
                for i in range(skill_step.cast_count):
                    # yield for sleep
                    yield TaskSleep(skill_step.cast_period)
                    ret_val = do_skill_spend(skill_data，user，instance)
                    if not ret_val:
                        return
                    # sub coroutine(missle_handle_func)
                    task_id = yield TaskNew(missle_handle_func(
                        skill_data，instance，user，skill_step，action_group，target_id，target_pos))
                    instance.add_child_task_id(task_id)
        ### 3。guide skill
        elif skill_step.cast_type == CastSkillStep.CAST_TYPE_GUIDE_TO_TARGET:
            #..。some code ignore here
        now_time = GameTime.now_time
        step_pass_time = now_time - step_start_time
        need_sleep_time = skill_step.step_total_time - step_pass_time
        if need_sleep_time > 0:
            yield TaskSleep(need_sleep_time)
        instance.on_one_step_finish(skill_step)
    if skill_data.delay_end_time > 0:
        yield TaskSleep(skill_data.delay_end_time)
    # wait for child finish~~
    for task_id in instance.child_task_list:
        yield TaskWait(task_id)
    instance.task_id = 0
```

整体实现比较简单， 整个技能是由多个SkillStep来配置的， 整体技能的流程就是for循环执行所有SkillStep， 然后提供了多种SkillStep类型的处理， 主要是以下几类：

- **CastSkillStep.CAST_TYPE_PERIOD**：周期性触发的技能， 主要使用yield TaskSleep()
- **CastSkillStep.CAST_TYPE_MISSLE_TO_TARGET**：导弹类技能， 使用子协程功能
- **CastSkillStep.CAST_TYPE_GUIDE_TO_TARGET**：引导类技能， 使用子协程功能

最后所有step应用完毕会进入配置的休眠和等待子任务的阶段。

### 7.1.3 子任务 - 导弹类技能相关代码

对于上面介绍的导弹类技能（火球）， 核心实现也比较简单， 实现了一个飞行物按固定速度逼近目标的效果， 具体代码如下， 利用yield我们可以实现在飞行物未达到目标点的时候每帧执行一次的效果：

```python
### 1。handle for missle skill(etc: fire ball)
def missle_handle_func(skill_data，instance，user，skill_step，action_group，target_id，target_pos):
    effect = instance.create_effect(skill_step.missle_info.missle_fx_path)
    effect.set_scale(skill_step.missle_info.missle_scale)

    cur_target_pos，is_target_valid = skill_step.missle_info.get_target_position(
        user，target_id，target_pos)
    start_pos = skill_step.missle_info.get_start_position(user，target_id，target_pos)

    is_reach_target = False
    from common.gametime import GameTime
    init_time = GameTime.now_time
    while True:
        # ..。some code ignore here
        fly_distance = skill_step.missle_info.fly_speed*GameTime.elapse_time
        if fly_distance < total_distance:
            start_pos += fly_direction*math3d.vector(fly_distance，fly_distance，fly_distance)
            effect.set_position(start_pos)
        else:
            is_reach_target = True
            break
        # do yield util next frame
        yield
    effect.destroy()
    if is_reach_target:
        target_list = skill_data.get_target_list(user.caster，target_id，target_pos)
        for target in target_list:
            action_group.do(user.caster，target)
```

### 7.1.4 子任务 - 引导类技能代码

对于上面介绍的引导类技能（闪电链），依托框架本身的guide effect实现， 我们利用yield TaskSleep()就能很好的完成相关的功能了：

```python
### 2。handle for guide skill(etc: lighting chain)
def guide_handle_func(skill_data，instance，user，skill_step，start_pos，target_id，target_pos):
    effect = instance.create_effect(skill_step.guide_info.guide_fx_path)
    effect.set_scale(skill_step.guide_info.guide_scale)

    effect.set_position(start_pos)

    effect.set_guide_end_pos(target_pos - start_pos)

    # yield for sleep
    yield TaskSleep(skill_step.guide_info.guide_time)
    effect.destroy()
```

## 7.2 对应的 C++ 实现

前面的python实现只是个引子， 抛开具体的画面和细节， 我们来尝试用我们构建的C++20版协程调度器来实现相似的代码（抛开显示相关的内容， 纯粹过程模拟）：

```cpp
//C++ 20 skill test coroutine
mScheduler.CreateTask20([instance]() -> rstudio::logic::CoResumingTaskCpp20 {
    rstudio::logic::ISchedTask* task = rco_self_task();
    task->SetReturnFunction([](const rstudio::logic::CoReturnObject*) {
        //ToDo: return handle code add here
    });

    for (auto& skill_step : step_list) {
        auto step_start_time = GGame->GetTimeManager().GetTimeHardwareMS();
        switch (skill_step.cast_type) {
            case CastSkillStep::CAST_TYPE_PERIOD: {
                    //..。some code ignore here
                }
                break;
            case CastSkillStep::CAST_TYPE_MISSLE_TO_TARGET: {
                    if (skill_step.cast_action_group_list.size() > 0) {
                        auto& action_group = skill_step.cast_action_group_list[0];
                        for (int i = 0; i < skill_step.cast_count; i++) {
                            co_await rstudio::logic::cotasks::Sleep(skill_step.cast_period);
                            bool ret_val = do_skill_spend(skill_data，user，instance);
                            if (!ret_val) {
                                co_return rstudio::logic::CoNil;
                            }
                            auto task_id = co_await rstudio::logic::cotasks::CreateTask(true，
                                [&skill_step]()->rstudio::logic::CoResumingTaskCpp20 {
                                auto cur_target_pos = skill_step.missle_info.get_target_position(
                                    user，target_id，target_pos);
                                auto start_pos = skill_step.missle_info.get_start_position(
                                    user，target_id，target_pos);
                                bool is_reach_target = false;
                                auto init_time = GGame->GetTimeManager().GetTimeHardwareMS();
                                auto last_time = init_time;
                                do {
                                    auto now_time = GGame->GetTimeManager().GetTimeHardwareMS();
                                    auto elapse_time = now_time - last_time;
                                    last_time = now_time;
                                    if (now_time - init_time >= skill_step.missle_info.long_fly_time) {
                                        break;
                                    }

                                    auto cur_target_pos = skill_step.missle_info.get_target_position(
                                        user，target_id，target_pos);

                                    rstudio::math::Vector3 fly_direction = cur_target_pos - start_pos;
                                    auto total_distance = fly_direction.Normalise();
                                    auto fly_distance = skill_step.missle_info.fly_speed * elapse_time;
                                    if (fly_distance < total_distance) {
                                        start_pos += fly_direction * fly_distance;
                                    }
                                    else {
                                        is_reach_target = true;
                                        break;
                                    }

                                    co_await rstudio::logic::cotasks::NextFrame{};
                                } while (true);
                                if (is_reach_target) {
                                    //ToDo: add damage calculate here~~
                                }

                                });
                            instance.add_child_task_id(task_id);
                        }
                    }
                }
                break;
            case CastSkillStep::CAST_TYPE_GUIDE_TO_TARGET: {
                    //..。some code ignore here
                }
                break;
            default:
                break;
        }

        auto now_time = GGame->GetTimeManager().GetTimeHardwareMS();
        auto step_pass_time = now_time - step_start_time;
        auto need_sleep_time = skill_step.step_total_time - step_pass_time;
        if (need_sleep_time > 0) {
            co_await rstudio::logic::cotasks::Sleep(need_sleep_time);
        }

        instance.on_one_step_finish(skill_step);
    }

    if (skill_data.delay_end_time > 0) {
        co_await rstudio::logic::cotasks::Sleep(skill_data.delay_end_time);
    }

    for (auto tid :instance.child_task_list) {
        co_await rstudio::logic::cotasks::WaitTaskFinish(tid，10000);
    }
});
```

我们可以看到，依赖C++20的新特性和我们自己封装的调度器，我们已经可以很自然很顺畅的用比较低的心智负担来表达原来在python中实现的功能了， 这应该算是一个非常明显的进步了。

## 7.3 小结

通过上面两版实现的对比，我们不难发现: 1。结合调度器，C++ Coroutine的实现与脚本一样具备简洁性，这得益于Compiler对Stack变量的自动处理，以及规整的`co_await`等关键字支持，从某种程度上，我们可以认为这种处理提供了一个简单的类GC的能力，我们可以更低心智负担的开发相关代码。2。协程的使用同时也会带来其他一些好处，像避免多级Callback带来的代码分散逻辑混乱等问题，这个在C++17协程使用的范例中已经提到过，此处不再重复.

# 8. RoadMap

## 8.1 对 asio coroutine20 实现部分的思考

我们知道最新版的asio已经在尝试使用C++ Coroutine20来简化它大量存在的异步操作。先抛开具体的细节以及代码实现质量等问题，我们来看一下个人认为asio做得比较好的两点:

### 8.1.1 低使用成本的经典 callback 兼容方案

```cpp
asio::awaitable<void> watchdog(asio::io_context& ctx) {
  asio::steady_timer timer(ctx);
  timer.expires_after(1s);
  co_await timer.async_wait(asio::use_awaitable);
  co_return;
}
```

这个实现比较巧妙的地方在于，`steady_timer`的`async_wait()`接口，原来接受的是一个callback函数，这个地方，asio通过引入asio::use_awaitable对象，实现了callback语义到`co_await` 协程语义的转换，这对于我们兼容大量包含callback的历史代码，是非常具有参考价值的.

> asio coroutine实现的剥析，在笔者的另外一篇文章 [asio的coroutine实现分析](https://link.zhihu.com/?target=https%3A//km.woa.com/group/29321/articles/show/514606)中有详细的展开，感兴趣的读者可以自行翻阅.

### 8.1.2 利用操作符定义复合任务

```cpp
auto [e] = co_await server.async_connect(target，use_nothrow_awaitable);
  if (!e)
  {
    co_await (
        (
          transfer(client，server，client_to_server_deadline) ||
          watchdog(client_to_server_deadline)
        )
        &&
        (
          transfer(server，client，server_to_client_deadline) ||
          watchdog(server_to_client_deadline)
        )
      );
  }
```

协程的使用，不可避免的会出现协程与子协程，协程与协程之间的复合关系，Asio通过重载`||` 运算和`&&` 运算，来尝试表达多个异步任务的组合，具体的作用如下: `||`: 用来表达两个同时开始的异步任务，其中一个成功执行，则返回这个执行的结果，并取消另外一个异步任务的执行。`&&`: 用来表达两个同时执行的异步任务，两个任务都成功后返回包含这两个任务执行结果的`std::tuple<>`值，其中任意一个任务失败，则直接返回错误。通过这种机制，我们一定程度拥有了对任务的复合关系进行表达的能力，比如对一个原本不支持超时的异步任务，我们可以非常简单的`||`上一个超时异步任务，来解决它的超时支持问题。这种设计也是很值得参考的.

## 8.2 关于 executions

聊到异步，不得不说起最近几年频繁调整提案，直到最近提案才逐步成熟的executions了。我们先来简单了解一下executions:

![img](https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-072b84c618312a746a1c5e0033a89799_1440w.webp)



在底层设计上，executions与ranges非常类同，都是先解决本身的DSL表达的问题，再来构建更上层的应用，区别在于ranges主要是使用了CPO以及`|`运算符来做到这一点，而executions因为本身的复杂度基于CPO引入了更复杂的`tag invoke`机制，来组织自己的DSL，因为这种表达代码层面有很高的复杂度，也被社区广泛的戏称为 "存在大量的代码噪声"，或者说开发了一种"方言"。但不可否认，通过引入底层的DSL支撑特性，executions很好的实现了结构化并发。目前我们可以参考学习的工程化实践，主要是Meta公司开发的libunifex库，在结构化并发这部分，libunfix其实已经做得比较好了，但其本身是存在一些缺陷的，一方面，libunifex的调度器实现相比asio，还存在很大的落差，另外，一些支持工程应用的算法也有很多的缺失，需要更长周期的发展和稳定。所以对此，我们目前的策略是保持预研的状态，在实现上尝试将libunifex的调度器更多的结合asio的调度器，并实现一些我们工程化比较急需的算法，逐步引入executions的结构化并发，对异步进行更好的开发与管理。但不可否认的是，目前综合来看，executions的成熟度和易用性都远远比不上C++ Coroutine20，短时间来看，还是基于Coroutine的异步框架更值得投入.

## 8.3 关于后续的迭代

协程部分的特性目前是作为我们自研引擎框架能力的一部分提供的，一方面我们会围绕Coroutine以及Scheduler补齐更多相关的特性，如前面说到的对复合的异步任务的支持等，另外我们也会尝试一些Executions相关的探索，如异构并发支持等，相信随着标准的进一步发展，越来越多的人对这块的投入和尝试，整个C++的异步会向着使用侧更简洁，表达能力更强的方向进化.

# 9. Reference

1. [asio官网](https://link.zhihu.com/?target=https%3A//think-async.com/Asio/)
2. [libunifex源码库](https://link.zhihu.com/?target=https%3A//github.com/facebookexperimental/libunifex)
3. [c++异步从理论到实践 - 总览篇](https://zhuanlan.zhihu.com/p/515309214)
4. [A Curious Course on Coroutines and Concurrency - David Beazley [1\]](https://link.zhihu.com/?target=http%3A//www.dabeaz.com/coroutines/)
5. [Marvin's Blog【程式人生】- C++20中的Coroutine [2\]](https://link.zhihu.com/?target=https%3A//marvinsblog.net/post/2019-08-18-cpp20-coroutine-01/)