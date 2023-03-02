自 C++11 起，shared_ptr 从 boost 转正进入标准库已有 10 年了。然而当 C++ 程序员们在谈论 shared_ptr 是不是线程安全的的时候，还时常存在分歧。确实关于 shared_ptr 的线程安全性不能直接了当地用安全或不安全来简单回答的，下面我来探讨一下。

## 线程安全的定义

先回顾一下线程安全这一概念的定义，以下摘录自维基百科：

> **Thread safety** is a computer programming concept applicable to multi-threaded code. Thread-safe code only manipulates shared data structures in a manner that ensures that all threads behave properly and fulfill their design specifications without unintended interaction. There are various strategies for making thread-safe data structures.

主要表达的就是多线程操作一个共享数据的时候，能够保证所有线程的行为是符合预期的。

一般而言线程不安全的行为大多数出现了 data race 导致的，比如你调用了某个系统函数，而这个函数内部其实用到了静态变量，那么多线程执行该函数的时候，就会触发 data race，造成结果不符合预期，严重的时候，甚至会导致 core dump。

当然这里只是一个例子，线程不安全还可能由其他原因导致。

## 你认为 shared_ptr 有哪些线程安全隐患？

shared_ptr 可能的线程安全隐患大概有如下几种，==一是引用计数的加减操作是否线程安全==，==二是 shared_ptr 修改指向时，是否线程安全==。另外 shared_ptr 不是一个类，而是一个类模板，所以对于 shared_ptr 的 T 的并发操作的安全性，也会被纳入讨论范围。因此造成了探讨其线程安全性问题上的复杂性。

## 引用计数的探讨

岔开个话题，前段时间我面试过几个校招生，每当我问道是否了解 shared_ptr 的时候，对方总能巴拉巴拉说出一大堆东西。会讲到引用计数、weak_ptr 解决循环引用、自定义删除器的用法等等等等。感觉这些知识都是很八股的东西。我会立马打断去问一句：引用计数具体是怎么实现的？怎么做到多个 shared_ptr 之间的计数能共享，同步更新的呢？比如：

```cpp
shared_ptr<A> sp1 = make_shared<A>();
...
shared_ptr<A> sp2 = sp1;
...
shared_ptr<A> sp3 = sp1;
```

当 sp3 出现的时候，sp2 怎么感知到计数又加 1 了的呢？这时候很多学生都会卡住，犯了难。有的同学确实没有了解过的，就盲猜了一个，答道：用 `static` 变量存储的引用计数。

答案当然是否定的，因为如果是 static 变量的话，那么：

```cpp
shared_ptr<A> sp1 = make_shared<A>();
shared_ptr<A> sp2 = make_shared<A>();
```

这两个不相干的 sp1 和 sp2，只要模板参数 T 是同一个类型，就会共享同一个计数…

可以看下 cppreference 的描述： [std::shared_ptr - cppreference.com](https://link.juejin.cn?target=https%3A%2F%2Fen.cppreference.com%2Fw%2Fcpp%2Fmemory%2Fshared_ptr%23Implementation_notes)

shared_ptr 中除了有一个指针，指向所管理数据的地址。==还有一个指针指向一个**控制块**的地址，里面存放了所管理数据的数量（常说的引用计数）、weak_ptr 的数量、删除器、分配器等==。

也就是说对于引用计数这一变量的存储，是在堆上的，多个 shared_ptr 的对象都指向同一个堆地址。在多线程环境下，管理同一个数据的 shared_ptr 在进行计数的增加或减少的时候是线程安全的吗？

答案是肯定的，这一操作是==原子操作==。

> To satisfy thread safety requirements, the reference counters are typically incremented using an equivalent of std::atomic::fetch_add with std::memory_order_relaxed (decrementing requires stronger ordering to safely destroy the control block)

## 修改指向时是否是线程安全

这个要分情况来讨论：

### 情况一：多线程代码操作的是同一个 shared_ptr 的对象

比如 `std::thread` 的回调函数，是一个 lambda 表达式，其中引用捕获了一个 shared_ptr 对象

```cpp
    std::thread td([&sp1] () {....});
```

又或者通过回调函数的参数传入的 shared_ptr 对象，参数类型是引用:

```cpp
void fn(shared_ptr<A>& sp) {
    ...
}
...
    std::thread td(fn, sp1);
```

这时候确实是不是线程安全的。

当你在多线程回调中修改 shared_ptr 指向的时候。

```cpp
void fn(shared_ptr<A>& sp) {
    ...
    if (..) {
        sp = other_sp;
    } else if (...) {
        sp = other_sp2;
    }
}
```

shared_ptr 内数据指针要修改指向，sp 原先指向的引用计数的值要减去 1，other_sp 指向的引用计数值要加 1。然而这几步操作加起来并不是一个原子操作，如果多少线程都在修改 sp 的指向的时候，那么有可能会出问题。比如在导致计数在操作减一的时候，其内部的指向，已经被其他线程修改过了。引用计数的异常会导致某个管理的对象被提前析构，后续在使用到该数据的时候触发 core dump。

当然如果你没有修改指向的时候，是没有问题的。

### 情况二：多线程代码操作的不是同一个 shared_ptr 的对象

这里指的是管理的数据是同一份，而 shared_ptr 不是同一个对象。比如多线程回调的 lambda 的是按值捕获的对象。

```cpp
    std::thread td([sp1] () {....});
```

或者参数传递的 shared_ptr 是值传递，而非引用：

```cpp
void fn(shared_ptr<A> sp) {
    ...
}
...
    std::thread td(fn, sp1);
```

这时候每个线程内看到的 sp，他们所管理的是同一份数据，用的是同一个引用计数。但是各自是不同的对象，当发生多线程中修改 sp 指向的操作的时候，是不会出现非预期的异常行为的。

也就是说，如下操作是安全的：

```cpp
void fn(shared_ptr<A> sp) {
    ...
    if (..) {
        sp = other_sp;
    } else if (...) {
        sp = other_sp2;
    }
}
```

> **TIPS**:
>
> 第一种情况下，N 个线程修改指向前，shared_ptr 的引用计数并没有增加到 x + N（假设传入），仍然是 x；而第二种情况因为传入的是 shared_ptr 的值，引用奇数会加 N，每个线程修改指向 -1，不会有问题。（实际上第二个例子修改 sp 的指向没有任何意义啊）

## 所管理数据的线程安全性

尽管前面我们提到了如果是按值捕获（或传参）的 shared_ptr 对象，那么是该对象是线程安全的。然而话虽如此，但却可能让人误入歧途。因为我们使用 shared_ptr 更多的是操作其中的数据，对齐管理的数据进行读写。尽管在按值捕获的时候 shared_ptr 是线程安全的，我们不需要对此施加额外的同步操作（比如加解锁），但是这并不意味着 shared_ptr 所管理的对象是线程安全的！

请注意这是两回事。

如果 shared_ptr 管理的数据是 STL 容器，那么多线程如果存在同时修改的情况，是极有可能触发 core dump 的。比如多个线程中对同一个 vector 进行 push_back，或者对同一个 map 进行了 insert。甚至是对 STL 容器中并发的做 clear 操作，都有可能出发 core dump，当然这里的线程不安全性，其实是其所指向数据的类型的线程不安全导致的，并非是 shared_ptr 本身的线程安全性导致的。尽管如此，由于 shared_ptr 使用上的特殊性，所以我们有时也要将其纳入到 shared_ptr 相关的线程安全问题的讨论范围内。

这里简单提一下，除了 STL 容器的并发修改操作（这里指的是修改容器的结构，并不是修改容器中某个元素的值，后者是线程安全的，前者不是），protobuf 的 Message 对象也是不能并发操作的，比如一个线程中修改 Message 对象（set、add、clear），另外一个线程也在修改，或者在将其序列化成字符串都会触发 core dump。据我的工作经验，由于程序出现了非预期地并发修改容器对象或 PB 的 Message 对象的操作导致的 core dump 问题，在所有 core dump 事故原因中的占比是相当大的。

不管是 STL 容器或是 PB 的 Message 对象，如果无脑地加锁，当然会解决其潜在的 core dump 问题。但是效率并不一定高，关于 STL 容器在某些场景下可以规避掉该隐患，笔者曾经写过一个相关的文章，有兴趣可以了解：

[C++ STL 容器如何解决线程安全的问题](https://link.juejin.cn?target=https%3A%2F%2Fmp.weixin.qq.com%2Fs%2F2nDfyIc9UL4sCm6M0MHn2g)

除上述回答中提到的一些观点之外呢，有时候调整程序的逻辑，或许能更为优雅的解决问题。

比如我曾经见过的一段代码，一次请求过程中要异步查询 Redis 的两个 key，在异步的回调函数中对查询到的 value 进行处理。有一个处理逻辑是根据查到的 value 值，去判断是否满足一个条件，然后清空一个 unordere_map 的变量（调用 clear 成员函数）。这两个回调函数中都有可能会触发这个 clear 操作。然而这个代码在测试中出现了 core dump。原因就是这个 clear 可能同时触发，对同一个 unordere_map 对象进行 clear，是会出现这个问题的。

修改办法就是，新增两个 bool 类型的 flag 变量，初始为 false，两个异步回调函数中判断满足原先的条件后，各自修改不同的 flag 为 true。

在后续的串行操作中（异步回调结束后）判断这两个 flag，有一个为 true 就进行 unordere_map 对象的 clear。

这里扯的有点远了，已经不是 shared_ptr 本身的讨论范围了，更多是讨论解决容器本身并发问题的办法。请注意你写的是 C++ 代码，性能是很重要的，不要无脑加锁！

作者：果冻虾仁
链接：https://juejin.cn/post/7038581008945872927
来源：稀土掘金
著作权归作者所有。商业转载请联系作者获得授权，非商业转载请注明出处。