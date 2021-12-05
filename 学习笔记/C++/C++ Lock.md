# Overview
C++ 标准库为我们提供了 6 中基本的 mutex 类型：

- `std::mutex`

- `std::timed_mutex`

- `std::recursive_mutex`

- `std::recursive_timed_mutex`

- `std::shared_mutex` (since C++ 17)

- `std::shared_timed_mutex` (since C++ 14)



C++ 标准为我们提供了4 种基本的锁类型，分别如下（都是 RAII 模板）：

- `std::lock_guard` ： 方便线程对互斥量上锁。
- `std::unique_lock` ：方便线程对互斥量上锁，但提供了更好的上锁和解锁控制
- `std::shared_lock` ：方便对共享互斥量上锁（`std::shared_timed_mutex` 和 `std::shared_mutex`）（since C++ 14）
- `std::scoped_lock` ：用于对多个 mutex 进行顺序上锁，避免死锁（since C++ 17）



另外还提供了几个与锁类型相关的 Tag 类，分别如下:

- `std::adopt_lock_t`：==assume the calling thread already has ownership of the mutex==
- `std::defer_lock_t`：==do not acquire ownership of the mutex==
- `std::try_to_lock_t`：try to acquire ownership of the mutex without blocking



3 种 Tag 类都定义了常量对象，使用的时候直接使用其常量对象（`std::adopt_lock`, `std::defer_lock`, `std::try_to_lock`）即可。
```cpp
#include <mutex>
#include <thread>
 
struct bank_account {
    explicit bank_account(int balance) : balance(balance) {}
    int balance;
    std::mutex m;
};
 
void transfer(bank_account &from, bank_account &to, int amount)
{
    if(&from == &to) return; // avoid deadlock in case of self transfer
 
    // lock both mutexes without deadlock
    std::lock(from.m, to.m);
    // make sure both already-locked mutexes are unlocked at the end of scope
    std::lock_guard<std::mutex> lock1(from.m, std::adopt_lock);
    std::lock_guard<std::mutex> lock2(to.m, std::adopt_lock);
 
// equivalent approach:
//    std::unique_lock<std::mutex> lock1(from.m, std::defer_lock);
//    std::unique_lock<std::mutex> lock2(to.m, std::defer_lock);
//    std::lock(lock1, lock2);
 
    from.balance -= amount;
    to.balance += amount;
}
 
int main()
{
    bank_account my_account(100);
    bank_account your_account(50);
 
    std::thread t1(transfer, std::ref(my_account), std::ref(your_account), 10);
    std::thread t2(transfer, std::ref(your_account), std::ref(my_account), 5);
 
    t1.join();
    t2.join();
}
```
# std::lock_guard
`std::lock_gurad` 是 C++11 中定义的模板类，定义如下：
```cpp
template <class Mutex> class lock_guard;
```
lock_guard 对象通常用于管理某个锁（Lock）对象，因此与 Mutex RAII 相关，方便线程对互斥量上锁，即在某个 lock_guard 对象的生命周期内，它所管理的锁对象会一直保持上锁状态；而 lock_guard 的生命周期结束之后，它所管理的锁对象会被解锁。

模板参数 Mutex 代表互斥量类型，例如 `std::mutex` 类型，它应该是一个基本的 [BasicLockable](https://en.cppreference.com/w/cpp/named_req/BasicLockable) 类型，标准库中定义的几种基本的 mutex 类型，以及 `std::unique_lock`，都是 BasicLockable 对象。


## Lockable 对象
● **BasicLockable**: 支持 m.lock(), m.unlock()
● **Lockable**: 支持 BasicLockable 和 m.try_lock()
● **TimedLockable**: 支持Lockable 和 m.try_lock_for(rel_time), m.try_lock_until(abs_time)
​

## 初始化

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1636296534366-b6f78ec5-8adc-469e-9835-4543e87e0ca1.png" alt="image.png" style="zoom:50%;" />

1. **locking 初始化**：lock_guard 对象管理 Mutex 对象 m，==并在构造时对 m 进行上锁==（调用 m.lock()）
1. **adopting 初始化**：lock_guard 对象管理 Mutex 对象 m，与 locking 初始化不同的是， ==Mutex 对象 m 已被当前线程锁住==。
1. **拷贝构造[被禁用]**：lock_guard 对象的拷贝构造和移动构造（move construction）均被禁用，因此 lock_guard 对象==不可被拷贝构造或移动构造==。
```cpp
#include <thread>
#include <mutex>
#include <iostream>
 
int g_i = 0;
std::mutex g_i_mutex;  // protects g_i
 
void safe_increment()
{
    const std::lock_guard<std::mutex> lock(g_i_mutex);
    ++g_i;
 
    std::cout << "g_i: " << g_i << "; in thread #"
              << std::this_thread::get_id() << '\n';
 
    // g_i_mutex is automatically released when lock
    // goes out of scope
}
 
int main()
{
    std::cout << "g_i: " << g_i << "; in main()\n";
 
    std::thread t1(safe_increment);
    std::thread t2(safe_increment);
 
    t1.join();
    t2.join();
 
    std::cout << "g_i: " << g_i << "; in main()\n";
}
```
```cpp
#include <iostream>       // std::cout
#include <thread>         // std::thread
#include <mutex>          // std::mutex, std::lock_guard, std::adopt_lock

std::mutex mtx;           // mutex for critical section

void print_thread_id (int id) {
	mtx.lock();
	std::lock_guard<std::mutex> lck(mtx, std::adopt_lock);
	std::cout << "thread #" << id << '\n';
}

int main ()
{
	std::thread threads[10];
	// spawn 10 threads:
	for (int i=0; i<10; ++i)
		threads[i] = std::thread(print_thread_id,i);

	for (auto& th : threads) 
		th.join();

	return 0;
}
```
# std::unique_lock
lock_guard 最大的缺点也是简单，没有给程序员提供足够的灵活度，因此，C++11 标准中定义了另外一个与 Mutex RAII 相关类 `std::unique_lock`，该类与 `std::lock_guard` 类相似，也很方便线程对互斥量上锁，但它提供了更好的上锁和解锁控制。

顾名思义，`std::unique_lock` 对象以独占所有权的方式（ unique owership）管理 mutex 对象的上锁和解锁操作，所谓独占所有权，就是没有其他的 `std::unique_lock` 对象同时拥有某个 mutex 对象的所有权。在构造（或移动赋值）时，`std::unique_lock` 对象需要传递一个 Mutex 对象作为它的参数，新创建的 `std::unique_lock` 对象负责传入的 Mutex 对象的上锁和解锁操作。

## 初始化

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1636297032418-0bd3785c-4ccd-4a21-849d-511836912b71.png" alt="image.png" style="zoom: 67%;" />

- **默认构造函数**：新创建的 unique_lock 对象不管理任何 Mutex 对象。
- **locking 初始化**：新创建的 unique_lock 对象管理 Mutex 对象 m，并尝试调用 m.lock() 对 Mutex 对象进行上锁，如果此时另外某个 unique_lock 对象已经管理了该 Mutex 对象 m，则当前线程将会被阻塞。
- **try-locking 初始化**：新创建的 unique_lock 对象管理 Mutex 对象 m，并尝试调用 m.try_lock() 对 Mutex 对象进行上锁，但如果上锁不成功，并不会阻塞当前线程。
- **deferred 初始化**：新创建的 unique_lock 对象管理 Mutex 对象 m，==但是在初始化的时候并不锁住 Mutex 对象（ m 应该是一个没有当前线程锁住的 Mutex 对象）==。
- **adopting 初始化**：新创建的 unique_lock 对象管理 Mutex 对象 m， ==m 应该是一个已经被当前线程锁住的 Mutex 对象，并且当前新创建的 unique_lock 对象拥有对锁 (Lock) 的所有权==。
- **locking 一段时间(duration)**：新创建的 unique_lock 对象管理 Mutex 对象 m，并试图通过调用 m.try_lock_for(rel_time) 来锁住 Mutex 对象一段时间(rel_time)。
- **locking 直到某个时间点(time point)**：新创建的 unique_lock 对象管理 Mutex 对象m，并试图通过调用 m.try_lock_until(abs_time) 来在某个时间点(abs_time) 之前锁住 Mutex 对象。
- **拷贝构造 [被禁用]**：unique_lock 对象不能被拷贝构造。
- **移动(move)构造**：新创建的 unique_lock 对象获得了由 x 所管理的 Mutex 对象的所有权(包括当前 Mutex 的状态)，调用 move 构造之后， x 对象如同通过默认构造函数所创建的，就不再管理任何 Mutex 对象了。



```cpp
#include <iostream>       // std::cout
#include <thread>         // std::thread
#include <mutex>          // std::mutex, std::lock, std::unique_lock
                          // std::adopt_lock, std::defer_lock
std::mutex foo,bar;

void task_a () {
    std::lock(foo, bar);         // simultaneous lock (prevents deadlock)
    std::unique_lock<std::mutex> lck1 (foo, std::adopt_lock);
    std::unique_lock<std::mutex> lck2 (bar, std::adopt_lock);
    std::cout << "task a\n";
    // (unlocked automatically on destruction of lck1 and lck2)
}

void task_b () {
    // foo.lock(); bar.lock(); // replaced by:
    std::unique_lock<std::mutex> lck1, lck2;
    lck1 = std::unique_lock<std::mutex>(bar, std::defer_lock);
    lck2 = std::unique_lock<std::mutex>(foo, std::defer_lock);
    std::lock(lck1, lck2);       // simultaneous lock (prevents deadlock)
    std::cout << "task b\n";
    // (unlocked automatically on destruction of lck1 and lck2)
}


int main ()
{
    std::thread th1 (task_a);
    std::thread th2 (task_b);

    th1.join();
    th2.join();

    return 0;
}
```
> **Tips**:
> 	注意 std::adopt_lock 和 std::defer_lock 的区别，两个虽然都不会在构造的时候锁住 Mutex 对象，但是前者表示当前线程已经锁住了 Mutex，后者表示当前线程还没有对 Mutex 加锁。

## std::unique_lock 主要成员函数
由于 `std::unique_lock` 比 `std::lock_guard` 操作灵活，因此它提供了更多成员函数。具体分类如下：

- 上锁/解锁操作：`lock()`，`try_lock()`，`try_lock_for()`，`try_lock_until()` 和 `unlock)` (因此 `std::unique_lock` 是 _TimedLockable_ 的)
- 修改操作：移动赋值（move assignment），交换（swap，与另一个 `std::unique_lock` 对象交换它们所管理的 Mutex 对象的所有权），释放（release，返回指向它所管理的 Mutex 对象的指针，并释放所有权）
- 获取属性操作：`owns_lock()`（返回当前 `std::unique_lock` 对象是否获得了锁）、`operator bool()`（与 `owns_lock()` 功能相同）、mutex（返回当前 `std::unique_lock` 对象所管理的 Mutex 对象的指针）。



```cpp
// unique_lock::lock/unlock
#include <iostream>       // std::cout
#include <thread>         // std::thread
#include <mutex>          // std::mutex, std::unique_lock, std::defer_lock

std::mutex mtx;           // mutex for critical section

void print_thread_id (int id) {
    std::unique_lock<std::mutex> lck (mtx,std::defer_lock);
    // critical section (exclusive access to std::cout signaled by locking lck):
    lck.lock();
    std::cout << "thread # " << id << '\n';
    lck.unlock();
}

int main ()
{
    std::thread threads[10];
    // spawn 10 threads:
    for (int i=0; i<10; ++i)
        threads[i] = std::thread(print_thread_id,i+1);

    for (auto& th : threads) 
        th.join();

    return 0;
}
```
# std::shared_lock
<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1636297938230-619270f8-7f27-4930-ad56-176d361dd74b.png" alt="image.png" style="zoom:67%;" />

`std::shared_lock` 的构造函数和 `std::unique_lock` 一样，这里就不再一一介绍了，需要注意的是这里锁住 mutex 使用的是 m.lock_shared()/m.try_lock_shared()/...，而不是 m.lock()//m.try_lock()/...。

```cpp
#include <iostream>
#include <mutex>
#include <shared_mutex>
#include <thread>
 
class ThreadSafeCounter {
 public:
  ThreadSafeCounter() = default;
 
  // Multiple threads/readers can read the counter's value at the same time.
  unsigned int get() const {
    std::shared_lock lock(mutex_);
    return value_;
  }
 
  // Only one thread/writer can increment/write the counter's value.
  unsigned int increment() {
    std::unique_lock lock(mutex_);
    return ++value_;
  }
 
  // Only one thread/writer can reset/write the counter's value.
  void reset() {
    std::unique_lock lock(mutex_);
    value_ = 0;
  }
 
 private:
  mutable std::shared_mutex mutex_;
  unsigned int value_ = 0;
};
 
int main() {
  ThreadSafeCounter counter;
 
  auto increment_and_print = [&counter]() {
    for (int i = 0; i < 3; i++) {
      std::cout << std::this_thread::get_id() << ' ' << counter.increment() << '\n';
 
      // Note: Writing to std::cout actually needs to be synchronized as well
      // by another std::mutex. This has been omitted to keep the example small.
    }
  };
 
  std::thread thread1(increment_and_print);
  std::thread thread2(increment_and_print);
 
  thread1.join();
  thread2.join();
}
 
// Explanation: The output below was generated on a single-core machine. When
// thread1 starts, it enters the loop for the first time and calls increment()
// followed by get(). However, before it can print the returned value to
// std::cout, the scheduler puts thread1 to sleep and wakes up thread2, which
// obviously has time enough to run all three loop iterations at once. Back to
// thread1, still in the first loop iteration, it finally prints its local copy
// of the counter's value, which is 1, to std::cout and then runs the remaining
// two loop iterations. On a multi-core machine, none of the threads is put to
// sleep and the output is more likely to be in ascending order.
```
同样，`std::shared_lock` 的成员函数也和 `std::unique_lock` 一样，这里也就不一一介绍了。

# std::scoped_lock
`std::scoped_lock` 主要为了解决对多个 mutex 上锁的顺序导致死锁的问题。
```cpp
#include <mutex>
#include <thread>
#include <iostream>
#include <vector>
#include <functional>
#include <chrono>
#include <string>
 
struct Employee {
    Employee(std::string id) : id(id) {}
    std::string id;
    std::vector<std::string> lunch_partners;
    std::mutex m;
    std::string output() const
    {
        std::string ret = "Employee " + id + " has lunch partners: ";
        for( const auto& partner : lunch_partners )
            ret += partner + " ";
        return ret;
    }
};
 
void send_mail(Employee &, Employee &)
{
    // simulate a time-consuming messaging operation
    std::this_thread::sleep_for(std::chrono::seconds(1));
}
 
void assign_lunch_partner(Employee &e1, Employee &e2)
{
    static std::mutex io_mutex;
    {
        std::lock_guard<std::mutex> lk(io_mutex);
        std::cout << e1.id << " and " << e2.id << " are waiting for locks" << std::endl;
    }
 
    {
        // use std::scoped_lock to acquire two locks without worrying about 
        // other calls to assign_lunch_partner deadlocking us
        // and it also provides a convenient RAII-style mechanism
 
        std::scoped_lock lock(e1.m, e2.m);
 
        // Equivalent code 1 (using std::lock and std::lock_guard)
        // std::lock(e1.m, e2.m);
        // std::lock_guard<std::mutex> lk1(e1.m, std::adopt_lock);
        // std::lock_guard<std::mutex> lk2(e2.m, std::adopt_lock);
 
        // Equivalent code 2 (if unique_locks are needed, e.g. for condition variables)
        // std::unique_lock<std::mutex> lk1(e1.m, std::defer_lock);
        // std::unique_lock<std::mutex> lk2(e2.m, std::defer_lock);
        // std::lock(lk1, lk2);
        {
            std::lock_guard<std::mutex> lk(io_mutex);
            std::cout << e1.id << " and " << e2.id << " got locks" << std::endl;
        }
        e1.lunch_partners.push_back(e2.id);
        e2.lunch_partners.push_back(e1.id);
    }
 
    send_mail(e1, e2);
    send_mail(e2, e1);
}
 
int main()
{
    Employee alice("alice"), bob("bob"), christina("christina"), dave("dave");
 
    // assign in parallel threads because mailing users about lunch assignments
    // takes a long time
    std::vector<std::thread> threads;
    threads.emplace_back(assign_lunch_partner, std::ref(alice), std::ref(bob));
    threads.emplace_back(assign_lunch_partner, std::ref(christina), std::ref(bob));
    threads.emplace_back(assign_lunch_partner, std::ref(christina), std::ref(alice));
    threads.emplace_back(assign_lunch_partner, std::ref(dave), std::ref(bob));
 
    for (auto &thread : threads) thread.join();
    std::cout << alice.output() << '\n'  << bob.output() << '\n'
              << christina.output() << '\n' << dave.output() << '\n';
}
```
## std::lock()
在没有 `std::scoped_lock` 之前我们也可以使用 `std::lock()` 来实现相同的功能。
```cpp
#include <mutex>
#include <thread>
#include <iostream>
#include <vector>
#include <functional>
#include <chrono>
#include <string>
 
struct Employee {
    Employee(std::string id) : id(id) {}
    std::string id;
    std::vector<std::string> lunch_partners;
    std::mutex m;
    std::string output() const
    {
        std::string ret = "Employee " + id + " has lunch partners: ";
        for( const auto& partner : lunch_partners )
            ret += partner + " ";
        return ret;
    }
};
 
void send_mail(Employee &, Employee &)
{
    // simulate a time-consuming messaging operation
    std::this_thread::sleep_for(std::chrono::seconds(1));
}
 
void assign_lunch_partner(Employee &e1, Employee &e2)
{
    static std::mutex io_mutex;
    {
        std::lock_guard<std::mutex> lk(io_mutex);
        std::cout << e1.id << " and " << e2.id << " are waiting for locks" << std::endl;
    }
 
    // use std::lock to acquire two locks without worrying about 
    // other calls to assign_lunch_partner deadlocking us
    {
        std::lock(e1.m, e2.m);
        std::lock_guard<std::mutex> lk1(e1.m, std::adopt_lock);
        std::lock_guard<std::mutex> lk2(e2.m, std::adopt_lock);
// Equivalent code (if unique_locks are needed, e.g. for condition variables)
//        std::unique_lock<std::mutex> lk1(e1.m, std::defer_lock);
//        std::unique_lock<std::mutex> lk2(e2.m, std::defer_lock);
//        std::lock(lk1, lk2);
// Superior solution available in C++17
//        std::scoped_lock lk(e1.m, e2.m);
        {
            std::lock_guard<std::mutex> lk(io_mutex);
            std::cout << e1.id << " and " << e2.id << " got locks" << std::endl;
        }
        e1.lunch_partners.push_back(e2.id);
        e2.lunch_partners.push_back(e1.id);
    }
    send_mail(e1, e2);
    send_mail(e2, e1);
}
 
int main()
{
    Employee alice("alice"), bob("bob"), christina("christina"), dave("dave");
 
    // assign in parallel threads because mailing users about lunch assignments
    // takes a long time
    std::vector<std::thread> threads;
    threads.emplace_back(assign_lunch_partner, std::ref(alice), std::ref(bob));
    threads.emplace_back(assign_lunch_partner, std::ref(christina), std::ref(bob));
    threads.emplace_back(assign_lunch_partner, std::ref(christina), std::ref(alice));
    threads.emplace_back(assign_lunch_partner, std::ref(dave), std::ref(bob));
 
    for (auto &thread : threads) thread.join();
    std::cout << alice.output() << '\n'  << bob.output() << '\n'
              << christina.output() << '\n' << dave.output() << '\n';
}
```


# Links

1. [https://en.cppreference.com/w/cpp/thread/mutex](https://en.cppreference.com/w/cpp/thread/mutex)
1. [https://en.cppreference.com/w/cpp/thread/timed_mutex](https://en.cppreference.com/w/cpp/thread/timed_mutex)
1. [https://en.cppreference.com/w/cpp/thread/recursive_mutex](https://en.cppreference.com/w/cpp/thread/recursive_mutex)
1. [https://en.cppreference.com/w/cpp/thread/recursive_timed_mutex](https://en.cppreference.com/w/cpp/thread/recursive_timed_mutex)
1. [https://en.cppreference.com/w/cpp/thread/shared_mutex](https://en.cppreference.com/w/cpp/thread/shared_mutex)
1. [https://en.cppreference.com/w/cpp/thread/shared_timed_mutex](https://en.cppreference.com/w/cpp/thread/shared_timed_mutex)
1. [https://en.cppreference.com/w/cpp/thread/lock_guard](https://en.cppreference.com/w/cpp/thread/lock_guard)
1. [https://en.cppreference.com/w/cpp/thread/unique_lock](https://en.cppreference.com/w/cpp/thread/unique_lock)
1. [https://en.cppreference.com/w/cpp/thread/shared_lock](https://en.cppreference.com/w/cpp/thread/shared_lock)
1. [https://en.cppreference.com/w/cpp/thread/scoped_lock](https://en.cppreference.com/w/cpp/thread/scoped_lock)
1. [https://en.cppreference.com/w/cpp/thread/lock](https://en.cppreference.com/w/cpp/thread/lock)
1. [https://en.cppreference.com/w/cpp/thread/lock_tag_t](https://en.cppreference.com/w/cpp/thread/lock_tag_t)
1. [https://en.cppreference.com/w/cpp/named_req/BasicLockable](https://en.cppreference.com/w/cpp/named_req/BasicLockable)
