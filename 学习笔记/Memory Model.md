# Overview
**什么是内存模型？**

In computing, a **memory model** describes the interactions of [threads](https://en.wikipedia.org/wiki/Thread_(computing)) through [memory](https://en.wikipedia.org/wiki/Memory_(computing)) and their shared use of the data.



**定义内存模型的意义？**

有了内存模型，编译器就可以做一些编译优化。

编译优化的原则：the compiler needs to make sure **only** that the values of (potentially shared) variables at _synchronization barriers_ are guaranteed to be the same in both the optimized and unoptimized code. In particular, reordering statements in a block of code that contains no synchronization barrier is assumed to be safe by the compiler.

# Memory Order
**Memory ordering** describes the order of accesses to computer memory by a CPU. The term can refer either to the memory ordering generated by the [compiler](https://en.wikipedia.org/wiki/Compiler) during ==[compile time](https://en.wikipedia.org/wiki/Compile_time)==, or to the memory ordering generated by a CPU during ==[runtime](https://en.wikipedia.org/wiki/Run_time_(program_lifecycle_phase))==.

In modern [microprocessors](https://en.wikipedia.org/wiki/Microprocessor), memory ordering ==characterizes the CPU's ability to reorder memory operations== – it is a type of ==[out-of-order execution](https://en.wikipedia.org/wiki/Out-of-order_execution)==. Memory reordering can be ==used to fully utilize the bus-bandwidth of different types of memory== such as [caches](https://en.wikipedia.org/wiki/CPU_cache#Cache_entries) and [memory banks](https://en.wikipedia.org/wiki/Memory_bank).

On most modern [uniprocessors](https://en.wikipedia.org/wiki/Uniprocessor_system) memory operations are not executed in the order specified by the program code. In ==single threaded programs== all operations ==appear to have been executed in the order specified==, with ==all out-of-order execution hidden to the programmer== – however in multi-threaded environments (or when interfacing with other hardware via memory buses) this can lead to problems. To avoid problems, ==[memory barriers](https://en.wikipedia.org/wiki/Memory_barrier)== can be used in these cases.

## Compile-time memory ordering

略


## Runtime memory ordering


![image.png](https://littleneko.oss-cn-beijing.aliyuncs.com/img/1631122823063-83f21415-ed33-4448-b7fb-44a6dccd6cf7.png)


# Links

1. [https://en.wikipedia.org/wiki/Memory_model_(programming)](https://en.wikipedia.org/wiki/Memory_model_(programming))
1. [https://en.wikipedia.org/wiki/Memory_ordering](https://en.wikipedia.org/wiki/Memory_ordering)
