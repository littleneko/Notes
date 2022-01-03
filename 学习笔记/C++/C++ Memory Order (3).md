# Explanation

## Relaxed ordering

`memory_order_relaxed` 只保证原子性，不具有任何数据同步的限制，在保证单线程执行效果一致的情况下，编译器在编译时和 CPU 在运行时可以进行各种重排，因此下面的代码在 C++ 标准中允许出现 r1 == r2 == 42 的情况（在 x86 上实际不会出现）。

```cpp
// Thread 1:
r1 = y.load(std::memory_order_relaxed); // A
x.store(r1, std::memory_order_relaxed); // B
// Thread 2:
r2 = x.load(std::memory_order_relaxed); // C 
y.store(42, std::memory_order_relaxed); // D
```

`memory_order_relaxed` 适用于==计数场景==，下面的代码在执行完后可以保证最后输出的值是 10000。

```cpp
#include <vector>
#include <iostream>
#include <thread>
#include <atomic>
 
std::atomic<int> cnt = {0};
 
void f()
{
    for (int n = 0; n < 1000; ++n) {
        cnt.fetch_add(1, std::memory_order_relaxed);
    }
}
 
int main()
{
    std::vector<std::thread> v;
    for (int n = 0; n < 10; ++n) {
        v.emplace_back(f);
    }
    for (auto& t : v) {
        t.join();
    }
    std::cout << "Final counter value is " << cnt << '\n';
}
```

## Release-Acquire ordering

如果在线程 A 中对原子变量 M 使用 `memory_order_release` 写入（store），在线程 B 中对同一个原子变量 M 使用 `memory_order_acquire` 读（load），那么在线程 A 中所有 _happened-before_ M.store 之前的内存写操作（==包括非原子变量和 relaxed 的原子变量==）在线程 B 中都变成了 _visible side-effects_。即一旦线程 B 的load 读到了 M 的新值，就保证可以看到 A 在 release 之前的写。


上述情况只发生在对同一个原子变量 release 和 qcquire 的两个线程之间，其他线程可以看到不同的内存顺序。


> **Tips**:
> 互斥锁，比如  std::mutex 或 atomic spinlock 也是一个 release-acquire 同步。

```cpp
#include <thread>
#include <atomic>
#include <cassert>
#include <string>
 
std::atomic<std::string*> ptr;
int data;
 
void producer()
{
    std::string* p  = new std::string("Hello");
    data = 42;
    ptr.store(p, std::memory_order_release);
}
 
void consumer()
{
    std::string* p2;
    while (!(p2 = ptr.load(std::memory_order_acquire)))
        ;
    assert(*p2 == "Hello"); // never fires
    assert(data == 42); // never fires
}
 
int main()
{
    std::thread t1(producer);
    std::thread t2(consumer);
    t1.join(); t2.join();
}
```

consumer 线程通过循环等待 ptr 初始化，一旦读到了非 null 的 ptr，因为 `memory_order_release` 和`memory_order_acquire` 的同步效果，producer 里 p 和 data 的内存写入都对 consumer 中后续两个 assert 可见了。


```cpp
#include <thread>
#include <atomic>
#include <cassert>
#include <vector>
 
std::vector<int> data;
std::atomic<int> flag = {0};
 
void thread_1()
{
    data.push_back(42);
    flag.store(1, std::memory_order_release);
}
 
void thread_2()
{
    int expected=1;
    while (!flag.compare_exchange_strong(expected, 2, std::memory_order_acq_rel)) {
        expected = 1;
    }
}
 
void thread_3()
{
    while (flag.load(std::memory_order_acquire) < 2)
        ;
    assert(data.at(0) == 42); // will never fire
}
 
int main()
{
    std::thread a(thread_1);
    std::thread b(thread_2);
    std::thread c(thread_3);
    a.join(); b.join(); c.join();
}
```

上面的代码展示了 release-acquire 的传递性，thread 2 acquire 拿到 flag == 1 后，一定可以读到 data 为 42，然后 thread release 更改 flag 为 2，thread 3 acquire 拿到 flag == 2 后，也一定能读到 data 为 42。


## Release-Consume ordering

如果在线程 A 中对原子变量 M 使用 `memory_order_release` 写入（store），在线程 B 中对同一个原子变量 M 使用 `memory_order_consume` 读（load），那么在线程 A 中所有 _happened-before_ M.store 之前的内存写操作（包括非原子变量和 relaxed 的原子变量）中与 M 有 ==_carries dependency_== 关系的变量，在线程 B 中都变成了 _visible side-effects_。即一旦线程 B 的 load 读到了 M 的新值，就保证可以看到 A 在 release 之前的写。


> **Tips**:
> 因为 Release-Consume ordering 要记录 dependency chains，现在没有编译器实现了该 ordering，实际上都等同于 Release-Acquire ordering。在 C++ 17 以后，memory_order_consume 已经被抛弃，不建议使用。

 

```cpp
#include <thread>
#include <atomic>
#include <cassert>
#include <string>
 
std::atomic<std::string*> ptr;
int data;
 
void producer()
{
    std::string* p  = new std::string("Hello");
    data = 42;
    ptr.store(p, std::memory_order_release);
}
 
void consumer()
{
    std::string* p2;
    while (!(p2 = ptr.load(std::memory_order_consume)))
        ;
    assert(*p2 == "Hello"); // never fires: *p2 carries dependency from ptr
    assert(data == 42); // may or may not fire: data does not carry dependency from ptr
}
 
int main()
{
    std::thread t1(producer);
    std::thread t2(consumer);
    t1.join(); t2.join();
}
```

因为 data 并不依赖 ptr，所以并不保证 p2 load 之后能看到 data == 42；因为 ptr carries dependency p，所以可以保证 p2 load 之后一定能看到 \*p == "Hello"。


## Sequentially-consistent ordering

使用 `memory_order_seq_cst` 除了有 release/acquire 的效果，还会外加一个单独全序（_single total modification order_），也就是保证所有的线程观察到内存操作完全同样的顺序。


下面是一个需要 sequentially-consistent ordering 的例子：

```cpp
#include <thread>
#include <atomic>
#include <cassert>
 
std::atomic<bool> x = {false};
std::atomic<bool> y = {false};
std::atomic<int> z = {0};
 
void write_x()
{
    x.store(true, std::memory_order_seq_cst);
}
 
void write_y()
{
    y.store(true, std::memory_order_seq_cst);
}
 
void read_x_then_y()
{
    while (!x.load(std::memory_order_seq_cst))
        ;
    if (y.load(std::memory_order_seq_cst)) {
        ++z;
    }
}
 
void read_y_then_x()
{
    while (!y.load(std::memory_order_seq_cst))
        ;
    if (x.load(std::memory_order_seq_cst)) {
        ++z;
    }
}
 
int main()
{
    std::thread a(write_x);
    std::thread b(write_y);
    std::thread c(read_x_then_y);
    std::thread d(read_y_then_x);
    a.join(); b.join(); c.join(); d.join();
    assert(z.load() != 0);  // will never happen
}
```

要使 z == 0，只有以下情况：

1. read_x_then_y ==依次==观察到 x == true; y == false
1. read_y_then_x ==依次==观察到 y == true; x == false

这在 sequentially-consistent ordering 下是不可能发生的，否则两个线程观察到的 x 和 y 的修改顺序就不一致了。而上述情况在其他内存序下可能发生，因为并不保证所有线程看到的内存序是一致的。


# Relationship with volatile

Within a thread of execution, accesses (reads and writes) through volatile glvalues cannot be reordered past observable side-effects (including other volatile accesses) that are sequenced-before or sequenced-after within the same thread, ==but this order is not guaranteed to be observed by another thread==, since volatile access does not establish inter-thread synchronization.


In addition, volatile accesses are ==not atomic== (concurrent read and write is a data race) and ==do not order memory== (non-volatile memory accesses may be freely reordered around the volatile access).


# Misc

release-acquire 和 release-consumer 一定是成对出现才能保证上述 ordering，比如把 Release-Acquire 中的
consumer 改成下面这样：

```cpp
void consumer()
{
    std::string* p2;
    while (!(p2 = ptr.load(std::memory_order_release)))
        ;
    assert(*p2 == "Hello"); // never fires
    assert(data == 42); // never fires
}
```

虽然在 producer 中使用了 release 保证了 data = 42 不会被重排到 store 之后，即保证了在线程 A 中写 data 一定在写 ptr 之前，但是并不保证在其他线程中看到 ptr 的更改后就一定能看到 data 的更改。

---



==**memory fence 不等于可见性**==，即使线程2恰好在线程1在把 ready 设置为 true 后读取了 ready 也不意味着它能看到 true，因为同步 cache 是有延时的。==memory fence 保证的是可见性的**顺序**：“假如我看到了 a 的最新值，那么我一定也得看到 b 的最新值”==。

```cpp
// Thread1
// ready was initialized to false
p.init();
ready.store(true, std::memory_order_release); // 操作A
 
// Thread2
if (ready.load(std::memory_order_acquire)) {  // 操作B
	p.bar();
}
```


# Links

1. [https://en.cppreference.com/w/cpp/atomic/memory_order](https://en.cppreference.com/w/cpp/atomic/memory_order)
1. [https://en.wikipedia.org/wiki/Memory_ordering](https://en.wikipedia.org/wiki/Memory_ordering)
1. [https://blog.csdn.net/wxj1992/article/details/103649056?spm=1001.2014.3001.5501](https://blog.csdn.net/wxj1992/article/details/103649056?spm=1001.2014.3001.5501)