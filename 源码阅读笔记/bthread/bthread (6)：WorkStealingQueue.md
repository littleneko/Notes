# Intrioduction

每个 worker (TaskGroup) 中有两个线程安全的队列：RemoteTaskQueue 和 WorkStealingQueue，前者使用 mutex 锁实现；后者是一个无锁队列，使用原子变量实现。



TaskGroup 中使用 WorkStealingQueue 保存 btread_id：

```c++
WorkStealingQueue<bthread_t> _rq;
```

worker 把要执行的 bthread 向队列中放，其他 worker 会来 steal，==worker 自身的 push 和 pop 都在队列的同一侧（bottom）==，==其他 worker 的 steal 在队列的另一侧（top）==。

由于：

1. WorkStealingQueue 的 push 和 pop 只会发生在当前 worker 中，因此不会有并发
1. WorkStealingQueue 的 steal 是其他 worker 调用的，所以和 push、pop、steal 之间都有可能产生并发


因此 WorkStealingQueue 与普通线程安全队列的区别是:

1. **push 之间不会有并发，push 和 pop 之间也不会有并发，push 和 steal 之间可能有并发**
1. **pop 之间不会有并发，pop 和 push 之间也不会有并发，pop 和 steal 之间可能有并发**
1. **steal 之间，steal 和 push 之间，steal 和 pop 之间都会有并发**



# 定义和初始化
```cpp
template <typename T>
class WorkStealingQueue {
public:
    // ... ...
    
private:
    // Copying a concurrent structure makes no sense.
    DISALLOW_COPY_AND_ASSIGN(WorkStealingQueue);

    butil::atomic<size_t> _bottom;
    size_t _capacity;
    T* _buffer;
    butil::atomic<size_t> BAIDU_CACHELINE_ALIGNMENT _top
}
```
\_bottom 和 \_top 都定义为原子变量，其中 \_top ALIGNMENT 到与 cache line（默认 64 字节）对齐，目的是为了防止  false sharing，即因为同一个 cache line 的数据被修改导致 _top 所在的 cache line 失效。

\_capacity 的大小必须为 2 的整数次幂，目的是为了取余操作可以使用位运算完成，提高效率；\_bottom 和 \_top 的初始值都是 1，初始状态和 put 一个元素后的状态分别如下图所示。

![image-20211206000836458](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20211206000836458.png)

所以 \_bottom 实际上是指向了下一个 put 元素的位置，\_top 指向了第一个元素的位置。



> **Tips**:
>
> _bottom 和 _top 是一直向上增长的，不会取余到 _capacity，这样做的原因是计算队列中元素个数的时候可以直接用 _top - _bottom 得到



# push
```cpp
    // Push an item into the queue.
    // Returns true on pushed.
    // May run in parallel with steal().
    // Never run in parallel with pop() or another push().
    bool push(const T& x) {
        const size_t b = _bottom.load(butil::memory_order_relaxed);
        const size_t t = _top.load(butil::memory_order_acquire);
        if (b >= t + _capacity) { // Full queue.
            return false;
        }
        _buffer[b & (_capacity - 1)] = x;
        _bottom.store(b + 1, butil::memory_order_release);
        return true;
    }
```
push 向队列的 bottom 侧添加元素，只有 worker 自己会调用，和 push 以及 pop 之间不会有并发。

1. 首先读取 _bottom，使用 `memory_order_relaxed` 内存序；然后读取 _top，使用 `memory_order_acquire`  内存序；

2. 接下来就是判断队列是否满了，满了就返回 false；否则把数据放到 _bottom 指向的位置；

3. 然后把 _bottom +1 写回，注意这里使用的是 `memory_order_release` 内存序，==目的是为了让 \_bottom + 1 对其他线程可见时，\_buffer 写入也对其他线程可见==。

> **Tips**:
>
> 注意这里 `b & (_capacity - 1)` 实际上是对 b 取余的操作，这就是要求 _capacity 必须是 2 的整数次幂的原因。

# pop

```cpp
    // Pop an item from the queue.
    // Returns true on popped and the item is written to `val'.
    // May run in parallel with steal().
    // Never run in parallel with push() or another pop().
    bool pop(T* val) {
        const size_t b = _bottom.load(butil::memory_order_relaxed);
        size_t t = _top.load(butil::memory_order_relaxed);
        if (t >= b) {
            // fast check since we call pop() in each sched.
            // Stale _top which is smaller should not enter this branch.
            return false;
        }
        const size_t newb = b - 1;
        _bottom.store(newb, butil::memory_order_relaxed);
        butil::atomic_thread_fence(butil::memory_order_seq_cst);
        t = _top.load(butil::memory_order_relaxed);
        if (t > newb) {
            _bottom.store(b, butil::memory_order_relaxed);
            return false;
        }
        *val = _buffer[newb & (_capacity - 1)];
        if (t != newb) {
            return true;
        }
        // Single last element, compete with steal()
        const bool popped = _top.compare_exchange_strong(
            t, t + 1, butil::memory_order_seq_cst, butil::memory_order_relaxed);
        _bottom.store(b, butil::memory_order_relaxed);
        return popped;
    }
```
pop 从队列的 bottom 侧取元素，和 pop 以及 push 直接不会有并发。

1. 取 _bottom 的值，使用 `memory_order_relaxed` 内存序，因为（TODO）
2. 取 _top 的值，使用 `memory_order_relaxed` 内存序，因为（TODO）
3. t >= b 表示队列中没有元素，直接返回 false。
4. pop 从 bottom 侧取数据，会和 steal 同时运行，当队列中只有一个元素时，为了防止 pop 和 steal 取到同一个元素，先将 bottom - 1，锁定一个元素。
5. ==在将 bottom 更新后，使用一个 `memory_order_seq_cst` 的 memory fence 是为了 (TODO)==
6. 再次取 _top 的值 t，使用 `memory_order_relaxed` 内存序，因为 (TODO)
5. t > newb 说明队列中没有元素，恢复 _bottom 的值。
   * 走到这里说明在再次取 _top 的值之前有 steal 线程已经取走了数据
   * 这里 store _bottom 的值使用的是 `memory_order_relaxed` 内存序，因为 _bottom 只在当前线程修改（TODO）
8. 暂存准备返回的数据
9. ==如果 t == newb 说明这是最后一个元素，与 steal 线程之间有竞争；否则直接返回== （疑问，这里在上面取 _top 使用的是 memory_order_relaxed，可能拿不到最新值，这里可能会误判不是最后一个元素，直接返回了？）
10. 如果这是最后一个元素，使用 CAS 操作更新 _top 为 t + 1，并恢复 bottom 的值。（如果成功，实际上这里相当于 pop 从 top 侧取数据了。）注意这里和 steal 不同的是，并没有使用 while 循环 CAS，因为没必要，如果失败了，表示最后一个元素已经被 steal 走了，直接返回 false 就行了。



> **Tips**:
>
> 这里对于最后一个元素的 pop 并不是更改 bottom，而是更新 _top 的值，原因是这个 pop 和 steal 之间有竞争，而 steal 是从 top 侧取的数据，需要更新 top 的值，这样 pop 和 steal 就可以正确的对最后一个元素使用 CAS 操作竞争了。

# steal

```cpp
    // Steal one item from the queue.
    // Returns true on stolen.
    // May run in parallel with push() pop() or another steal().
    bool steal(T* val) {
        size_t t = _top.load(butil::memory_order_acquire);
        size_t b = _bottom.load(butil::memory_order_acquire);
        if (t >= b) {
            // Permit false negative for performance considerations.
            return false;
        }
        do {
            butil::atomic_thread_fence(butil::memory_order_seq_cst);
            b = _bottom.load(butil::memory_order_acquire);
            if (t >= b) {
                return false;
            }
            *val = _buffer[t & (_capacity - 1)];
        } while (!_top.compare_exchange_strong(t, t + 1,
                                               butil::memory_order_seq_cst,
                                               butil::memory_order_relaxed));
        return true;
    }
```

steal 从队列的 top 侧取元素，和其他 steal 以及 push、pop 之间都有并发。

1. 首先取 \_bottom 和 \_top，都使用 `memory_order_acquire` 内存序

   1. \_bottom 使用 `memory_order_acquire` 的目的是为了 push 和 pop 的 buffer 对 steal 可见
   2. _top 使用 `memory_order_acquire` 的目的是为了其他 steal 对 buffer 的更新对当前 steal 线程可见

2. t >= b 说明队列为空，直接返回 false。这里说会有 false negative 是因为 cache line 的同步是有延迟的，不过为了性能考虑，允许 false negative。（牢记，memory fence 不等于可见性，memory fence 保证的是可见性的顺序）

3. 随后是用 CAS 操作来执行具体的 steal 逻辑，先预读后尝试为 _top 加 1，因为==会其他的 steal 和 pop（最后一个元素的时候） 竞争==，可能会失败，所以用了一个 do while 循环，只要队列不为空就持续尝试 steal。

   do while 循环的开头是一个 seq_cst fence，如果是用 mfence 实现的，由于有 pop 里的 fence 的存在，steal 里的 fence 是可以不需要的，戈神在相关 [issue](https://github.com/apache/incubator-brpc/issues/432) 里的回复是担心实现的不确定性，以及为了明确所以用单独的 fence 也加上了。



> **Tips**:
>
> ```c++
> _top.compare_exchange_strong(t, t + 1,
>                              butil::memory_order_seq_cst,
>                              butil::memory_order_relaxed)
> ```
>
> 其语义是：
>
> * 如果原子变量 _top 的值等于 t，就更新为 t + 1，使用 `memory_order_seq_cst` 内存序，函数返回 true；
> * 如果原子变量 _top 的值不等于 t，就把当前 _top 的值赋值给 t，使用 `memory_order_relaxed` 内存序，函数返回 false
>
> 因此 while 循环在更新 _top 为 t + 1 失败的情况下会不断地用最新的 bottom 和 top 的值尝试。

# atomic_thread_fence(butil::memory_order_seq_cst) 的必要性

TODO

# Links

1. [https://en.cppreference.com/w/cpp/atomic/atomic](https://en.cppreference.com/w/cpp/atomic/atomic)
1. [https://en.cppreference.com/w/cpp/atomic/memory_order](https://en.cppreference.com/w/cpp/atomic/memory_order)
1. [https://en.cppreference.com/w/cpp/atomic/atomic/compare_exchange](https://en.cppreference.com/w/cpp/atomic/atomic/compare_exchange)
1. [https://en.cppreference.com/w/cpp/language/memory_model](https://en.cppreference.com/w/cpp/language/memory_model)
1. [https://en.cppreference.com/w/cpp/thread/hardware_destructive_interference_size](https://en.cppreference.com/w/cpp/thread/hardware_destructive_interference_size)
1. [https://blog.csdn.net/wxj1992/article/details/104311730](https://blog.csdn.net/wxj1992/article/details/104311730)
1. [https://github.com/apache/incubator-brpc/issues/432](https://github.com/apache/incubator-brpc/issues/432)
1. [https://zhuanlan.zhihu.com/p/41872203](https://zhuanlan.zhihu.com/p/41872203)



