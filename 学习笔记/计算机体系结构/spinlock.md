# 适用场景（为什么我们要自旋锁）
很多时候我们并不能采用其他的锁，比如读写锁、互斥锁、信号量等。一方面这些锁会发生上下文切换，他的时间是不可预期的，对于一些简单的、极短的临界区完全是一种性能损耗；另一方面在中断上下文是不允许睡眠的，除了自旋锁以外的其他任何形式的锁都有可能导致睡眠或者进程切换，这是违背了中断的设计初衷，会发生不可预知的错误。基于两点，我们需要自旋锁，他是不可替代的


- 持有锁的时间比较短（多短？理论上是只要比传统的线程调度上下文切换更短的时间就是合适的）
- 锁竞争不是特别激烈的情况下


# 演化过程
## test_and_set
```c
function Lock(lock) {
    // Test_and_set will atomically read the lock (which is either a 1 or 0) 
    // and if it finds a zero, will set the lock to be 1. 
    // If the lock is held (set to 1), then it will simply return 1
    // 
    // Because this is an atomic instruction, no other processor 
    // can begin a test_and_set on this address while another 
    // test_and_set is still executing, allowing us to ensure mutual exclusion.
	while (test_and_set(lock) == 1);
}

function Unlock(lock){
	lock = 0;
}
```
或者
```c
function Lock(lock) {
	while (lock == true || test_and_set(lock) == 1);
}

function Unlock(lock){
	lock = 0;
}
```

但是上面的实现有 2 个问题：

1. the test_and_set instruction must be executed atomically by the hardware, this makes it a very heavy-weight instruction and creates lots of coherency traffic over the interconnect
2. we are not guaranteeing FIFO ordering amongst the processors competing for the lock. So a processor could be waiting for a quite a long time if it is unlucky.


## ticket lock
因为 test_and_set 实现不公平，所以我们让每个 Processer 试图获取锁时先分配一个 ticket，获取锁的顺序按分配的 ticket 顺序，类似与 [Lamport's bakery algorithm](https://en.wikipedia.org/wiki/Lamport%27s_bakery_algorithm)。
```c
ticket_lock{
	int now_serving;
	int next_ticket;
};

function Lock(ticket_lock lock){
	//get your ticket atomically
	int my_ticket = fetch_and_increment(lock.next_ticket);
	while(my_ticket != now_serving){} // 忙等待直到其他Unlock后now_serving轮到自己
}

function UnLock(ticket_lock lock){
	lock.now_serving++;
}	
```
So what problems did we solve here? First, we only perform a single atomic operation during lock. This causes far less cache coherency traffic then the busy-waiting atomic operations of the test_and_set lock. Second, we now have FIFO ordering for lock acquisition. If our processor has been waiting for a while to get the lock, no johnny-come-lately can arrive and get it before us.

BUT, there is still a problem. ==Each processor spins by reading the same variable, the now_serving member of the ticket_lock==. Why is this a problem? Well, think of it from a cache coherency perspective. Each processor is spinning, constantly reading the now_serving variable. ==Finally, the processor holding the lock releases and increments now_serving. **This invalidates the cache line for all other processors**, causing each of them to go across the interconnect and retrieve the new value==. If each request for the new cache line is serviced in serial by the directory holding the cache line, **then the time to retrieve the new value is linear in the number of waiting processors.**
**​**

> **MESI**
>
> - **M**(Modified): 这行数据有效，数据被修改了，和内存中的数据不一致，数据只存在于本 Cache 中
> - **E**(Exclusive): 这行数据有效，数据和内存中的数据一致，数据只存在于本 Cache 中
> - **S**(Shared): 这行数据有效，数据和内存中的数据一致，数据存在于很多 Cache 中
> - **I**(Invalid): 这行数据无效



## mcs_spinlock
ticket lock 的问题在于所有 spinlock 都等待同一个变量(now_serving)，当 unlock 后，该变量就 Invalid 了，所有 Processer 都要重新读取该变量，成本比较高。
We can improve scalability if the lock acquisition time is O(1) instead of O(n) (where n is the number of waiting processors). Thats where the MCS lock comes in. ==Each processor will spin on a local variable, not a variable shared with other processors==. Here's the code:

```c
mcs_node { // 每个processer有一个mcs_node
	mcs_node next;
	int is_locked;
}

mcs_lock {
	mcs_node queue;
}

function Lock(mcs_lock lock, mcs_node my_node){
	my_node.next = NULL;
    // 把自己的mcs_node添加到等待队列中并返回上一个node
	mcs_node predecessor = fetch_and_store(lock.queue, my_node);
	// if its(pre node) null, we now own the lock and can leave, else....
	if (predecessor != NULL){
		my_node.is_locked = true;
        // 自己的锁节点交给上一个锁的next域，这样当上一个锁解锁的时候就可以通知我们这个申请的锁
		// when the predecessor unlocks, it will give us the lock
		predecessor.next = my_node;
		while(my_node.is_locked){}
	}
}

function UnLock(mcs_lock lock, mcs_node my_node){
	// is there anyone to give the lock to?
	if (my_node.next == NULL){
		// need to make sure there wasn't a race here
		if (compare_and_swap(lock.queue, my_node, NULL)){
			return;
		} else {
			// someone has executed fetch_and_store but not set our next field
			while(my_node.next == NULL){}
		}
	}
	// if we made it here, there is someone waiting, so lets wake them up
	my_node.next.is_locked = false;
}
```
There is more code here, but its not too tricky. The basic intuition is that each processor is represented by a node in a queue. When we lock, if someone else holds the lock then we need to register ourselves by adding our node to the queue. We then busy wait on our node's is_locked field. When we unlock, if there is a processor waiting, we need to set that field to false to wake it up.


More specifically, in Lock( ) we use fetch_and_store to atomically place our node at the end of the queue. Whatever was in lock.queue (the old tail of the queue) is now our "predecessor" and will get the lock directly before us. If lock.queue was NULL then no one owned the lock and we simply continue. If we need to wait, we then set our predecessor's next field so that it knows that we are next in line. Finally, we busy-wait for our predecessor to wake us up.


In UnLock( ), we first check if anyone is waiting for us to finish. ==The trick here is that even though mynode.next is NULL, another processor may have just performed the fetch_and_store in Lock( ) but has yet to set our next field==. ==We use compare_and_swap to atomically make sure that our node is still then last in the queue==. If it is, we are assured that no one is waiting and we can leave. Otherwise, we need to busy-wait on the other processor to set our next field. Finally, if someone is waiting, we wake them up by setting their is_locked field to false.

So we've solved a few of the problems we mentioned before. We have minimal atomic instructions, and we've created a more scalable lock by busy-waiting on local variables that reside in their own cache line (mynode.is_locked).



实现可以参考 linux kernel 的实现：[https://elixir.bootlin.com/linux/v5.4.61/source/kernel/locking/mcs_spinlock.h](https://elixir.bootlin.com/linux/v5.4.61/source/kernel/locking/mcs_spinlock.h)


# Links

1. [https://www.cs.rochester.edu/u/scott/papers/1991_TOCS_synch.pdf](https://www.cs.rochester.edu/u/scott/papers/1991_TOCS_synch.pdf)
1. [https://www.quora.com/How-does-an-MCS-lock-work](https://www.quora.com/How-does-an-MCS-lock-work)
1. [https://en.wikipedia.org/wiki/Test-and-set](https://en.wikipedia.org/wiki/Test-and-set)
1. [https://en.wikipedia.org/wiki/Test_and_test-and-set](https://en.wikipedia.org/wiki/Test_and_test-and-set)
1. [https://en.wikipedia.org/wiki/Ticket_lock](https://en.wikipedia.org/wiki/Ticket_lock)
1. [https://en.wikipedia.org/wiki/Lamport%27s_bakery_algorithm](https://en.wikipedia.org/wiki/Lamport%27s_bakery_algorithm)
1. MESI: [https://blog.csdn.net/muxiqingyang/article/details/6615199](https://blog.csdn.net/muxiqingyang/article/details/6615199)
1. [https://elixir.bootlin.com/linux/v5.4.61/source/kernel/locking/mcs_spinlock.h](https://elixir.bootlin.com/linux/v5.4.61/source/kernel/locking/mcs_spinlock.h)
