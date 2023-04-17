# 条件变量 (std::condition_variable)
C++ 标准库对条件变量有两套实现：`std::condition_variable` 和 `std::condition_variable_any`，这两个实现都包含在 _<condition_variable>_ 头文件的声明中。两者都需要与互斥量一起才能工作（互斥量是为了同步），前者仅能与 `std::mutex` 一起工作，而后者可以和合适的互斥量一起工作，从而加上了 \_any 的后缀。因为 `std::condition_variable_any` 更加通用，不过在性能和系统资源的使用方面会有更多的开销，所以通常会将 `std::condition_variable` 作为首选类型。

以下代码展示了使用条件变量唤醒线程的方式：
```cpp
std::mutex mut;
std::queue<data_chunk> data_queue;	// 1
std::condition_variable data_cond;

void data_preparation_thread() {
	while(more_data_to_prepare()) {
		data_chunk const data = prepare_data();
		std::lock_guard<std::mutex> lk(mut);
		data_queue.push(data);	// 2
		data_cond.notify_one();	// 3
	}
}

void data_processing_thread() {
	while(true) {
		std::unique_lock<std::mutex> lk(mut);	// 4
		data_cond.wait(lk,[]{return !data_queue.empty();});	// 5
		data_chunk data = data_queue.front();
		data_queue.pop();
		lk.unlock();	// 6
		process(data);
		if(is_last_chunk(data))	break;
	}
}
```
`wait()` 会去检查这些条件（通过 Lambda 函数），当条件满足（Lambda 函数返回 true）时返回；如果条件不满足将解锁互斥量，并且将线程置于阻塞或等待状态。当准备数据的线程调用 `notify_one()` 通知条件变量时，处理数据的线程从睡眠中苏醒，重新获取互斥锁，并且再次进行条件检查。在条件满足的情况下，从 `wait()` 返回并继续持有锁。当条件不满足时，线程将对互斥量解锁，并重新等待。


这就是为什么用 `std::unique_lock` 而不使用 `std::lock_guard` 的原因，等待中的线程必须在等待期间解锁互斥量，并对互斥量再次上锁，而 `std::lock_guard` 没有这么灵活。如果互斥量在线程休眠期间保持锁住状态，准备数据的线程将无法锁住互斥量，也无法添加数据到队列中。同样，等待线程也永远不会知道条件何时满足。


## 使用条件变量实现一个线程安全的队列
// TODO


# std::future
C++ 标准库中有两种 future，声明在 <future> 头文件中: unique future (`std::future<>`) 和 shared futures (`std::shared_future<>`) ，前者只能与指定事件相关联，而后者就能关联多个事件，后者的实现中，所有实例会在同时变为就绪状态，并且可以访问与事件相关的数据。

future 对象本身并不提供同步访问，当多个线程需要访问一个独立 future 对象时，必须使用互斥量或类似同步机制进行保护。不过，当多个线程对一个 `std::shared_future<>` 副本进行访问，即使同一个异步结果，也不需要同步 future。


## 后台任务的返回值 (std::async())
使用 `std::async()` 启动一个异步任务，返回一个 `std::future` 对象，这个对象持有最终计算出来的结果，当需要这个值时，只需要调用这个对象的 `get()` 函数，就会阻塞线程直到 future 就绪为止，并返回计算结果。
```cpp
#include <future>
#include <iostream>

int find_the_answer_to_ltuae();

void do_other_stuff();

int main() {
	std::future<int> the_answer = std::async(find_the_answer_to_ltuae);
	do_other_stuff();
	std::cout << "The answer is " << the_answer.get() << std::endl;
}
```


`std::async()` 和 `std::thread` 一样，也支持传递参数：
```cpp
#include <string>
#include <future>

struct X {
	void foo(int,std::string const&);
	std::string bar(std::string const&);
};
X x;
auto f1 = std::async(&X::foo, &x, 42, "hello"); // 调用 p->foo(42, "hello"),p 是指向 x 的指针
auto f2 = std::async(&X::bar, x, "goodbye"); // 调用 tmpx.bar("goodbye"), tmpx 是 x 的拷贝副本

struct Y {
	double operator()(double);
};
Y y;
auto f3 = std::async(Y(), 3.141); // 调用 tmpy(3.141), tmpy通过 Y 的移动构造函数得到
auto f4 = std::async(std::ref(y), 2.718); // 调用 y(2.718)

X baz(X&);
std::async(baz, std::ref(x));	// 调用 baz(x)

class move_only	{
public:
	move_only();
	move_only(move_only&&);
  move_only(move_only const&) = delete;
	move_only& operator=(move_only&&);
	move_only& operator=(move_only const&) = delete;
	void operator()();
};
auto f5 = std::async(move_only()); // 调用 tmp(),tmp 是通过 std::move(move_only()) 构造得到
```


也可以向 `std::async()` 传递一些 launch 参数：

| std::launch::async | a new thread is launched to execute the task asynchronously |
| --- | --- |
| std::launch::deferred | the task is executed on the calling thread the first time its result is requested (lazy evaluation) |

```cpp
// 在新线程上执行
auto f6 = std::async(std::launch::async, Y(), 1.2);

// 在 wait() 或 get() 调用时执行
auto f7 = std::async(std::launch::deferred, baz, std::ref(x));

// 实现选择执行方式
auto f8 = std::async(std::launch::deferred | std::launch::async, baz,std::ref(x));

// 调用延迟函数
auto f9 = std::async(baz, std::ref(x));
f7.wait();
```


## future 与任务关联 (std::packaged_task<>)
`std::packaged_task<>` 会将 future 与函数或可调用对象进行绑定，当调用 `std::packaged_task<>`
对象时，就会调用相关函数或可调用对象；当 future 状态为就绪时，会存储返回值。这可以用在构建线程池或其他任务的管理中，比如，在任务所在线程上运行其他任务，或将它们串行运行在一个特殊的后台线程上，当粒度
较大的操作被分解为独立的子任务时，每个子任务都可以包含在 `std::packaged_task<>` 实例中，之后将实例传递到任务调度器或线程池中，对任务细节进行抽象，调度器仅处理 `std::packaged_task<>` 实例，而非处理单独的函数。


`std::packaged_task<>` 的模板参数是一个函数签名，函数签名的返回类型可以用来标识从 `get_future()` 返回的 `std::future<>` 的类型，而函数签名的参数列表，可用来指定 packaged_task 的函数调用操作符。


使用 `std::packaged_task<>` 执行一个图形界面线程：
```cpp
#include <deque>
#include <mutex>
#include <future>
#include <thread>
#include <utility>

std::mutex m;
std::deque<std::packaged_task<void()> > tasks;

bool	gui_shutdown_message_received();
void	get_and_process_gui_message();

void gui_thread() { 	// 1
	while(!gui_shutdown_message_received()) {	// 2
        get_and_process_gui_message();	// 3
		std::packaged_task<void()> task;
		{
			std::lock_guard<std::mutex> lk(m);
			if(tasks.empty())	// 4
                continue;
			task = std::move(tasks.front());	// 5
			tasks.pop_front();
		}
		task();	// 6
	}
}

std::thread gui_bg_thread(gui_thread);

template<typename Func>
std::future<void> post_task_for_gui_thread(Func f) {
	std::packaged_task<void()> task(f);	// 7
	std::future<void> res = task.get_future();	// 8
	std::lock_guard<std::mutex> lk(m);
	tasks.push_back(std::move(task));	// 9
	return res; // 10
}
```
图形界面线程(1)循环直到收到一条关闭图形界面的信息后关闭界面(2)。关闭界面前，进行轮询界面消息处理(3)，依次拿出每一个 task (`std::packaged_task<void()>`) 并执行这个 task。
函数(7)可以提供一个打包好的任务，通过这个任务(8)调用 `get_future()` 成员函数获取 future 对象，并且在任务推入列表(9)之前，future 将返回调用函数。


## 使用 std::promises
`std::promise<T>` 提供设定值的方式(类型为T)，这个类型会和后面看到的 `std::future<T>` 对象相关联。`std::promise`/`std::future` 对提供一种机制：future 可以阻塞等待线程，提供数据的线程可以使用 promise对相关值进行设置，并将 future 的状态置为“就绪”。


使用 promise 解决单线程多连接问题，使用一对 `std::promise<bool>/std::future<bool>` 找出传出成功的数据块，与 future 相关的只是简单的“成功/失败”标识。对于传入包，与 future 相关的数据就是数据包的有效负载。
```cpp
#include <future>

void process_connections(connection_set& connections) {
	while(!done(connections)) { // 1
		for(connection_iterator connection = connections.begin(), end = connections.end();
            connection != end;
            ++connection) {
			if(connection->has_incoming_data()) { // 3
				data_packet data = connection->incoming();
				std::promise<payload_type>& p = connection->get_promise(data.id);	// 4
				p.set_value(data.payload);
			}
			if(connection->has_outgoing_data()) { // 5
				outgoing_packet data = connection->top_of_outgoing_queue();
				connection->send(data.payload);
				data.promise.set_value(true);	// 6
			}
		}
	}
}
```
# std::experimental::latch
latch 是一种同步对象，当计数器减为 0 时，就处于就绪态了。latch 是基于其输出特性——当处于就绪态时，就会保持就绪态，直到被销毁。因此，latch 是为同步一系列事件的轻量级机制。


`std::experimental::latch` 声明在 <experimental/latch> 头文件中。构造 `std::experimental::latch` 时，将计数器的值作为构造函数的唯一参数。当等待的事件发生，就会调用 `count_down()` 成员函数。当计数器为 0 时，latch 状态变为就绪。可以调用 `wait()` 成员函数对 latch 进行阻塞，直到等待的 latch 处于就绪状态。如果需要对 latch 是否就绪的状态进行检查，可调用 `is_ready()` 成员函数。想要减少计数器 1 并阻塞直至 0，则可以调用 `count_down_and_wait()` 成员函数。


```cpp
void foo() {
	unsigned const thread_count=...;
	latch done(thread_count); // 1
	my_data data[thread_count];
	std::vector<std::future<void> > threads;
	for(unsigned i = 0; i < thread_count; ++i)
		threads.push_back(std::async(std::launch::async, [&, i]{ // 2
			data[i] = make_data(i);
			done.count_down(); // 3
			do_more_stuff(); // 4
		}));
	done.wait(); // 5
	process_data(data,thread_count); // 6
} // 7
```
# std::experimental::barrier
barrier 是一种可复用的同步机制，其用于一组线程间的内部同步。当线程抵达 barrier 时，会对线程进行阻塞，直到所有线程都达到 barrier 处，这时阻塞将会被解除。barrier可以复用——线程可以再次到达 barrier 处，等待下一个周期的所有线程。


并发技术扩展规范提供了两种栅栏机制，<experimental/barrier> 头文件中，分别为：`std::experimental::barrier` 和 `std::experimental::flex_barrier`。前者更简单，开销更低；后者更灵活，开销较大。


假设有一组线程对某些数据进行处理，每个线程都在处理独立的任务，因此在处理过程中无需同步。但当所有线程都必须处理下一个数据项前完成当前的任务时，就可以使用 `std::experimental::barrier` 来完成这项工作了。可以为同步组指定线程的数量，并为这组线程构造 barrier。当每个线程完成其处理任务时，都会到达 barrier 处，并且通过调用 barrier 对象的 `arrive_and_wait()` 成员函数，等待小组的其他线程。当最后一个线程抵达时，所有线程将被释放，barrier 重置。组中的线程可以继续接下来的任务，或是处理下一个数据项，或是进入下一个处理阶段。
```cpp
result_chunk process(data_chunk);
std::vector<data_chunk> divide_into_chunks(data_block data, unsigned num_threads);

void process_data(data_source &source, data_sink &sink) {
	unsigned const concurrency = std::thread::hardware_concurrency();
	unsigned const num_threads = (concurrency > 0) ? concurrency : 2;
    
	std::experimental::barrier sync(num_threads);
	std::vector<joining_thread> threads(num_threads);
    
	std::vector<data_chunk> chunks;
    result_block result;
	
	for (unsigned i = 0; i < num_threads; ++i) {
		threads[i] = joining_thread([&, i] {
			while (!source.done()) { // 6
				if (!i) { // 1
					data_block current_block = source.get_next_data_block();
					chunks = divide_into_chunks(current_block, num_threads);
				}
				sync.arrive_and_wait(); // 2
				result.set_chunk(i, num_threads, process(chunks[i])); // 3
				sync.arrive_and_wait(); // 4
				if (!i) { // 5
					sink.write_data(std::move(result));
				}
			}
		});
	}
} // 7
```


# Links

1. [https://en.cppreference.com/w/cpp/thread/condition_variable](https://en.cppreference.com/w/cpp/thread/condition_variable)
1. [https://en.cppreference.com/w/cpp/thread/future](https://en.cppreference.com/w/cpp/thread/future)
1. [https://en.cppreference.com/w/cpp/thread/shared_future](https://en.cppreference.com/w/cpp/thread/shared_future)
1. [https://en.cppreference.com/w/cpp/thread/async](https://en.cppreference.com/w/cpp/thread/async)
1. [https://en.cppreference.com/w/cpp/thread/launch](https://en.cppreference.com/w/cpp/thread/launch)
