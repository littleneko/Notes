# 基本操作
## 启动线程
启动线程实际上就是构造一个 `std::thread` 对象，`std::thread` 的 _constructor_ 定义如下：

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220123152718427.png" alt="image-20220123152718427" style="zoom:50%;" />

`std::thread` 可以接受 **函数**、**类成员函数**、**function object**、**lambda** 作为其构造参数。

```cpp
// 1. 普通函数
void do_some_work();
std::thread my_thread(do_some_work);
```
```cpp
// 2. 类成员函数
class foo {
public:
    void bar() {
        do_some_work();
    }
};
foo f;
std::thread my_thread(&foo::bar, &f);
```
```cpp
// 3. function object
class background_task {
public:
	void operator()() const {
		do_something();
		do_something_else();
	}
};
background_task f;
std::thread my_thread(f);
```
```cpp
// 4. lambda
std::thread my_thread([]{
	do_something();
	do_something_else();
});
```
> **Tips**:
> 使用类成员函数初始化 thread 时需要传递成员函数的地址和对象的指针 (`std::thread my_thread(&foo::bar, &f);`)。实际上对于普通函数来说，函数名即是函数指针也就是函数的地址，但是对于类成员函数来说需要显示得取地址（如果熟悉 std::bind 会发现这里的用法和 std::bind 几乎一样）。


**Notes 1**：
**必须保证线程结束之前,访问数据的有效性**
```cpp
struct func {
	int& i;	// 注意 i 是引用
	func(int& i_) : i(i_) {}
	void operator() () {
		for (unsigned j = 0 ; j<1000000 ; ++j) {
			do_something(i); // 1 潜在访问隐患:空引用
		}
	}
};

void oops() {
	int some_local_state=0;
	func my_func(some_local_state);
	std::thread my_thread(my_func);
	my_thread.detach(); // 2 不等待线程结束
}
// 3 新线程可能还在运行
```
函数 `oops` 执行完后，func 可能还在运行，会调用 `do_something`，这时就会访问已经销毁的变量。


## 分离(detach)和等待(join)线程
使用 `detach()` 会让线程在后台运行，并且不能与其直接交互，分离的线程不能 join，不过 C++ 运行库保证，当线程退出时，相关资源的能够正确回收。


分离线程通常称为守护线程(daemon threads)，这种线程的特点就是长时间运行。线程的生命周期可能会从应用的起始到结束，可能会在后台监视文件系统，还有可能对缓存进行清理，亦或对数据结构进行优化。


如需等待线程，需要使用 `join()`。将上面代码中的 `my_thread.detach()` 替换为 `my_thread.join()`，就可以确保局部变量在线程完成后才销毁。因为主线程并没有做什么事，使用独立的线程去执行函数变得意义不大。但在实际中，原始线程要么有自己的工作要做，要么会启动多个子线程来做一些有用的工作，并等待这些线程结束。


需要注意的是只能对一个线程使用一次 `join()`，一旦使用过 `join()`，`std::thread` 对象就不能再次 join 了，当对其使用 `joinable()` 时，将返回 `false`。


**Notes 2**：
**应当避免应用被抛出的异常所终止**


如果等待线程，则需要细心挑选使用 `join()` 的位置，当在线程运行后产生的异常，会在 `join()` 调用之前抛出，这样就会跳过 `join()`。通常，在无异常的情况下使用 `join()` 时，需要在异常处理过程中调用 `join()`，从而避免生命周期的问题。


**Notes 2.1：**
在异常处理过程中调用 join()
```cpp
struct func; // 定义同上
void f() {
	int some_local_state = 0;
	func my_func(some_local_state);
	std::thread t(my_func);
	try {
		do_something_in_current_thread();
	} catch(...) {
		t.join(); 	// 1
        throw;
	}
	t.join(); // 2
}
```
**Notes 2.2:**
使用 **RAII**(Resource Acquisition Is Initialization) 
```cpp
class thread_guard {
	std::thread& t;
public:
	explicit thread_guard(std::thread& t_):t(t_){}
	~thread_guard() {
		if(t.joinable()) { 	// 1
			t.join();		// 2
		}
	}
	thread_guard(thread_guard const&)=delete; 				// 3
	thread_guard& operator=(thread_guard const&)=delete;
};

struct func; // 定义在代码2.1中

void f() {
	int some_local_state = 0;
	func my_func(some_local_state);
	std::thread t(my_func);
	thread_guard g(t);
	do_something_in_current_thread();
}	// 4
```
线程执行到 4 处时，局部对象就要被逆序销毁了。因此，`thread_guard`对象 `g` 是第一个被销毁的，这时线程在
析构函数中 join()，即使 `do_something_in_current_thread` 抛出一个异常，这个销毁依旧会发生。


# 传递参数
向可调用对象或函数传递参数很简单，只需要将这些参数作为 `std::thread` 构造函数的附加参数即可。


**Notes 3:**
**参数会移动或拷贝至新线程的内存空间中（moved or copied by value），即使函数中的形数是引用，拷贝操作也会执行**
```cpp
void f(int i, std::string const& s);
std::thread t(f, 3, "hello");
```
代码创建了一个调用 `f(3, "hello")` 的线程，注意，函数 f 需要一个 `std::string` 对象作为第二个参数，但这里使用的是字符串的字面值，也就是 `char const *` 类型，线程的上下文完成字面值向 `std::string` 的转化。需要特别注意，指向动态变量的指针作为参数的情况：
```cpp
void f(int i,std::string const& s);

void oops(int some_param) {
	char buffer[1024]; // 1
	sprintf(buffer, "%i",some_param);
	std::thread t(f,3,buffer); // 2
	t.detach();
}
```
函数 `oops` 可能会在 `buffer` 转换成 `std::string` 之前结束，从而导致未定义的行为。因为，无法保证隐式转换的操作和 `std::thread` 构造函数的拷贝操作的顺序，有可能 `std::thread` 的构造函数拷贝的是转换前的变量(buffer指针)。解决方案就是在传递到 `std::thread` 构造函数之前，就将字面值转化为 `std::string`。
```cpp
void f(int i,std::string const& s);

void not_oops(int some_param) {
	char buffer[1024];
	sprintf(buffer,"%i",some_param);
	std::thread t(f,3,std::string(buffer)); // 使用std::string,避免悬空指针
	t.detach();
}
```
**Notes 4**:
**对于需要传递引用作为参数的情形，需要使用 **`**std::ref**`** 将参数转化成引用的形式** 
```cpp
void update_data_for_widget(widget_id w, widget_data& data); // 1

void oops_again(widget_id w) {
	widget_data data;
	std::thread t(update_data_for_widget, w, std::ref(data)); // 2
	display_status();
	t.join();
	process_widget_data(data);
}
```
**Notes 5:**
**对于只支持移动的类型，需要使用 **`**std::move**`** 转移对象所有权到新线程中**
```cpp
void process_big_object(std::unique_ptr<big_object>);
std::unique_ptr<big_object> p(new big_object);
p->prepare_data(42);
std::thread t(process_big_object, std::move(p));
```

# 转移线程所有权
`std::thread` is not [_CopyConstructible_](https://en.cppreference.com/w/cpp/named_req/CopyConstructible) or [_CopyAssignable_](https://en.cppreference.com/w/cpp/named_req/CopyAssignable), although it is [_MoveConstructible_](https://en.cppreference.com/w/cpp/named_req/MoveConstructible) and [_MoveAssignable_](https://en.cppreference.com/w/cpp/named_req/MoveAssignable).
```cpp
void some_function();
void some_other_function();
std::thread t1(some_function);			// 1
std::thread t2 = std::move(t1);			// 2
t1 = std::thread(some_other_function);	// 3
std::thread t3;							// 4
t3 = std::move(t2);						// 5
t1 = std::move(t3);						// 6 赋值操作将使程序崩溃
```
首先，新线程与 t1 相关联(1)，当显式使用 `std::move()` 创建 t2 后(2)，t1 的所有权就转移给了 t2，之后，t1 和执行线程已经没有关联了，执行 some_function 的函数线程现在与 t2 关联。
最后一个移动操作，将 some_function 线程的所有权转移给 t1，不过，t1 已经有了一个关联的线程(执行 some_other_function的线程)，所以这里系统直接调用 `std::terminate()` 终止程序继续运行。


C++ 20 中新增了 `std::jthread`，It has the same general behavior as `std::thread`, except that jthread automatically rejoins on destruction, and can be cancelled/stopped in certain situations.


# Links

1. [https://en.cppreference.com/w/cpp/thread](https://en.cppreference.com/w/cpp/thread)
1. [https://en.cppreference.com/w/cpp/thread/jthread/jthread](https://en.cppreference.com/w/cpp/thread/jthread/jthread)
1. [https://en.cppreference.com/w/cpp/utility/functional/ref](https://en.cppreference.com/w/cpp/utility/functional/ref)
1. Williams, A. (2019). _C++ concurrency in action_. Simon and Schuster.
