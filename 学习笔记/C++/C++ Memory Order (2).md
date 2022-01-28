为了能够便捷、统一的在各平台指定内存序，C++11 标准开始在 C++ 的语言定义层面上引进 memory order，memory_order 给程序员提供了一种指定多线程之间如何进行数据同步而不需要在乎硬件具体底层实现的手段，编码者通过指定 memory_order 告诉编译器需要什么样的内存序，编译器会根据 CPU 平台类型选用合适的手段来保证对应的同步，从而能够相对便利地写出高效的跨平台的多线程代码。在此之前要指定内存序要么依赖第三方库，要么需要根据运行的平台直接调用相关 CPU 指令等，会麻烦很多。

# 相关定义

```cpp
// Defined in header <atomic>
typedef enum memory_order {
    memory_order_relaxed,
    memory_order_consume,
    memory_order_acquire,
    memory_order_release,
    memory_order_acq_rel,
    memory_order_seq_cst
} memory_order;

enum class memory_order : /*unspecified*/ {
    relaxed, consume, acquire, release, acq_rel, seq_cst
};
inline constexpr memory_order memory_order_relaxed = memory_order::relaxed;
inline constexpr memory_order memory_order_consume = memory_order::consume;
inline constexpr memory_order memory_order_acquire = memory_order::acquire;
inline constexpr memory_order memory_order_release = memory_order::release;
inline constexpr memory_order memory_order_acq_rel = memory_order::acq_rel;
inline constexpr memory_order memory_order_seq_cst = memory_order::seq_cst;
```
==**std::memory_order specifies how memory accesses, including regular, non-atomic memory accesses, are to be ordered around an atomic operation.**== Absent any constraints on a multi-core system, when multiple threads simultaneously read and write to several variables, ==one thread can observe the values change in an order different from the order another thread wrote them. Indeed, the apparent order of changes can even differ among multiple reader threads==. ==Some similar effects can occur even on uniprocessor systems due to compiler transformations allowed by the memory model==.

The default behavior of all atomic operations in the library provides for _sequentially consistent ordering_ (see discussion below). That default can hurt performance, but the library's atomic operations can be given an additional std::memory_order argument to specify the exact constraints, beyond atomicity, that the compiler and processor must enforce for that operation.

std::memory_order 指定了包括普通的非原子内存访问在内的原子操作周围的内存访问方式。可以看到，C++ 的 memory order 提供的是一种通过原子变量限制内存序的手段，也就是说原子变量不光有我们熟知的原子变量的特性，还能限制包括非原子变量在内的各种变量的内存操作，除了依附在原子变量操作的 memory order，C++11 还引入了 std::atomic_thread_fence，也能达到类似的效果。

# C++ 中的 6 种 memory order
## memory_order_relaxed
宽松内存序，只保证原子性，没有同步和顺序制约，可用于计数器。


## memory_order_consume
用于 ==**load**== operation

1. No reads or writes in the current thread dependent on the value currently loaded can be reordered before this load.（后面依赖此原子变量的访存指令勿重排至此条指令之前）
1. Writes to data-dependent variables in other threads that release the same atomic variable are visible in the current thread. (其他线程中所有对此原子变量的 release operation 及其之前的对数据依赖变量的写入都对当前线程从该 consume operation 开始往后的操作可见)

## memory_order_acquire
用于 ==**load**== operation

1. No ==reads== or ==writes== in the current thread can be reordered ==before== this ==**load**==.（后面访存指令勿重排至此条 load 指令之前）
1. All writes in other threads that release the same atomic variable are visible in the current thread. (其他线程中所有对此原子变量的 release operation 及其之前的写入都对当前线程从该 acquire operation 开始往后的操作可见)

memory_order_consume 与 memory_order_acquire 的区别是，前者只作用于后面依赖此原子变量的指令不被重排，而后者作用于所有的指令。

==即不允许 **LoadLoad** 和 **LoadStore** 重排==


## memory_order_release
用于 ==**store**== operation

1. No ==reads== or ==writes== in the current thread can be reordered ==after== this ==**store**==.（前面访存指令勿重排至此条 store 指令之后）
1. All writes in the current thread are visible in other threads that acquire the same atomic variable  and writes that carry a dependency into the atomic variable become visible in other threads that consume the same atomic.（当此条指令的结果对其他线程可见后，之前的所有指令都可见）

==即不允许 **LoadStore** 和 **StoreStore** 重排==

## memory_order_acq_rel
用于 ==**read-modify-write**== operation，acquire + release 语意

1. No memory ==reads== or ==writes== in the current thread can be reordered ==before== or ==after== this ==store==
1. All writes in other threads that release the same atomic variable are visible before the modification and the modification is visible in other threads that acquire the same atomic variable.

## memory_order_seq_cst
用于 load operation、release operation、read-modify-write operation，acq_rel 语意外加所有使用 seq_cst 的指令有严格地全序关系（即所有的线程会观察到一致的内存修改）。


# 形式化定义
## Sequenced-before
同一个线程内的一种根据表达式求值顺序来的一种关系，完整的规则定义很复杂，参考 [https://en.cppreference.com/w/cpp/language/eval_order](https://en.cppreference.com/w/cpp/language/eval_order)。

其中最直观常用的一条规则简单来说如下：每一个完整表达式的值计算和副作用都 Sequenced-before 于下一个完整表达式的值计算和副作用。从而也就有以分号结束的语语句 Sequenced-before 于下一个以分号结束的语句，比如：

```
r2 = x.load(std::memory_order_relaxed); // C 
y.store(42, std::memory_order_relaxed); // D
```

从而有 C Sequenced-before D。


## Carries dependency
在同一个线程内，如果表达式 A sequenced-before B，并且下面任何一个条件成立，那么会有 B 依赖 A：

1. A 的结果是 B 的操作数，除了
   1. if B is a call to [std::kill_dependency](https://en.cppreference.com/w/cpp/atomic/kill_dependency)
   2. if A is the left operand of the built-in `&&`, `||`,` ?:`, or `,` operators.
1. A 写了一个标量对象 M，B 从 M 里读
1. X carries dependency A, B carries dependency X

## Modification order

对于任意特定的原子变量的所有修改操作都会以一个特定于该原子变量的全序（total order）发生，所有原子操作都保证以下四个要求：

1. **Write-write coherence**： If evaluation A that modifies some atomic M (a write) *happens-before* evaluation B that modifies M, then A appears earlier than B in the *modification order* of M
2. **Read-read coherence**：if a value computation A of some atomic M (a read) *happens-before* a value computation B on M, and if the value of A comes from a write X on M, then the value of B is either ==the value stored by X==, or ==the value stored by a side effect Y on M that appears later than X in the *modification order* of M==
3. **Read-write coherence**：if a value computation A of some atomic M (a read) *happens-before* an operation B on M (a write), then the value of A comes from a side-effect (a write) X that appears earlier than B in the *modification order* of M
4. **Write-read coherence**：if a side effect (a write) X on an atomic object M *happens-before* a value computation (a read) B of M, then the evaluation B shall take ==its value from X== or ==from a side effect Y that follows X in the *modification order* of M==

注意以上 4 条规则都是对于对于一个特定的原子变量 M 的操作，不涉及到多个原子变量的操作

## Release sequence

*release sequence* headed by A 表示对原子变量 M 上的一个 *release operation* A 之后的 Modification order 最长连续子序列，由下面两部分组成：

* 当前线程内对M的写操作（until C++20）
* 其他线程对 M 的 read-modify-write 操作

## Dependency-ordered before

Between threads, evaluation A is *dependency-ordered before* evaluation B if any of the following is true

* A 对某个原子变量 M 做 release operation，在另外一个线程中，B 对 M 做 consume operation 操作，并且 B 读到了 A 写入的值（由 *release sequence* headed by A 中的任意一个操作写入的值（until C++20））。
* A is *dependency-ordered* before X and X carries a dependency into B.

## Inter-thread happens-before
## Happens-before

### Simply happens-before

### Strongly happens-before

## Visible side-effects


# Links

1. [https://en.cppreference.com/w/cpp/atomic/memory_order](https://en.cppreference.com/w/cpp/atomic/memory_order)
1. [https://en.wikipedia.org/wiki/Memory_ordering](https://en.wikipedia.org/wiki/Memory_ordering)
1. [https://github.com/apache/incubator-brpc/blob/master/docs/cn/atomic_instructions.md](https://github.com/apache/incubator-brpc/blob/master/docs/cn/atomic_instructions.md)
1. [https://blog.csdn.net/wxj1992/article/details/103649056?spm=1001.2014.3001.5501](https://blog.csdn.net/wxj1992/article/details/103649056?spm=1001.2014.3001.5501)
