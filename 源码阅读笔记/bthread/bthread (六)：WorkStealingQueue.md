TaskGroup 中有两个线程安全的队列：RemoteTaskQueue 和 WorkStealingQueue，前者使用 mutex 锁实现，后者是一个无锁队列，使用原子变量实现。


WorkStealingQueue 与普通线程安全队列的区别是:

1. push 之间不会有并发，push 和 pop 之间也不会有并发，push 和 steal 之间可能有并发
1. pop 之间不会有并发，pop 和 push 之间也不会有并发，pop 和 steal 之间可能有并发
1. steal 之间，steal 和 push 之间，steal 和 pop 之间都会有并发



原因是：

1. WorkStealingQueue 的 push 和 pop 只会发生在当前 worker 中，因此不会有并发
1. WorkStealingQueue 的 steal 是其他 worker 调用的，所以和 push、pop、steal 之间都有可能产生并发



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
_bottom 和 _top 都定义为原子变量，其中 _top 填充与 cache line 对齐（默认 64 字节对齐），_bottom 和 _top 的初始值都是 1。
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


# Links

1. [https://en.cppreference.com/w/cpp/atomic/atomic](https://en.cppreference.com/w/cpp/atomic/atomic)
1. [https://en.cppreference.com/w/cpp/atomic/memory_order](https://en.cppreference.com/w/cpp/atomic/memory_order)
1. [https://en.cppreference.com/w/cpp/atomic/atomic/compare_exchange](https://en.cppreference.com/w/cpp/atomic/atomic/compare_exchange)
1. [https://en.cppreference.com/w/cpp/language/memory_model](https://en.cppreference.com/w/cpp/language/memory_model)
1. [https://en.cppreference.com/w/cpp/thread/hardware_destructive_interference_size](https://en.cppreference.com/w/cpp/thread/hardware_destructive_interference_size)
1. [https://blog.csdn.net/wxj1992/article/details/104311730](https://blog.csdn.net/wxj1992/article/details/104311730)



