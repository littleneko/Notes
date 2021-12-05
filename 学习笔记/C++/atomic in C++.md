# CAS
```cpp
bool compare_exchange_weak( T& expected, T desired,
                            std::memory_order success,
                            std::memory_order failure ) noexcept;
bool compare_exchange_weak( T& expected, T desired,
                            std::memory_order success,
                            std::memory_order failure ) volatile noexcept;
// (1) (since C++11)

bool compare_exchange_weak( T& expected, T desired,
                            std::memory_order order =
                                std::memory_order_seq_cst ) noexcept;
bool compare_exchange_weak( T& expected, T desired,
                            std::memory_order order =
                                std::memory_order_seq_cst ) volatile noexcept;
// (2) (since C++11)

bool compare_exchange_strong( T& expected, T desired,
                              std::memory_order success,
                              std::memory_order failure ) noexcept;
bool compare_exchange_strong( T& expected, T desired,
                              std::memory_order success,
                              std::memory_order failure ) volatile noexcept;
// (3) (since C++11)

bool compare_exchange_strong( T& expected, T desired,
                              std::memory_order order =
                                  std::memory_order_seq_cst ) noexcept;
bool compare_exchange_strong( T& expected, T desired,
                              std::memory_order order =
                                  std::memory_order_seq_cst ) volatile noexcept;
// (4) (since C++11)
```


Atomically compares the object representation (until C++20)value representation (since C++20) of `*this` with that of expected, and ==if those are bitwise-equal, replaces the former with desired== (performs _read-modify-write_ operation). ==Otherwise, loads the actual value stored in `*this` into expected== (performs _load_ operation).


The memory models for the read-modify-write and load operations are success and failure respectively. In the (2) and (4) versions order is used for both read-modify-write and load operations, except that `std::memory_order_acquire` and `std::memory_order_relaxed` are used for the load operation if `order == std::memory_order_acq_rel`, or `order == std::memory_order_release` respectively.

**Parameters**

- **expected** : reference to the value expected to be found in the atomic object. ==Gets stored with the actual value of `*this` if the comparison fails==.
- **desired** : the value to store in the atomic object if it is as expected
- **success** : the memory synchronization ordering for the read-modify-write operation if the comparison succeeds. All values are permitted.
- **failure** : the memory synchronization ordering for the load operation if the comparison fails. Cannot be `std::memory_order_release` or `std::memory_order_acq_rel` and cannot specify stronger ordering than success (until C++17)
- **order** : the memory synchronization ordering for both operations

 

**Return value**
`true` if the underlying atomic value was successfully changed, `false` otherwise.

==The weak forms (1-2) of the functions are allowed to fail spuriously, that is, act as if `*this != expected` even if they are equal==. When a compare-and-exchange is in a loop, the weak version will yield better performance on some platforms.


```cpp
#include <atomic>
template<typename T>
struct node
{
    T data;
    node* next;
    node(const T& data) : data(data), next(nullptr) {}
};
 
template<typename T>
class stack
{
    std::atomic<node<T>*> head;
 public:
    void push(const T& data)
    {
      node<T>* new_node = new node<T>(data);
 
      // put the current value of head into new_node->next
      new_node->next = head.load(std::memory_order_relaxed);
 
      // now make new_node the new head, but if the head
      // is no longer what's stored in new_node->next
      // (some other thread must have inserted a node just now)
      // then put that new head into new_node->next and try again
      while(!head.compare_exchange_weak(new_node->next, new_node,
                                        std::memory_order_release,
                                        std::memory_order_relaxed))
          ; // the body of the loop is empty
 
// Note: the above use is not thread-safe in at least 
// GCC prior to 4.8.3 (bug 60272), clang prior to 2014-05-05 (bug 18899)
// MSVC prior to 2014-03-17 (bug 819819). The following is a workaround:
//      node<T>* old_head = head.load(std::memory_order_relaxed);
//      do {
//          new_node->next = old_head;
//       } while(!head.compare_exchange_weak(old_head, new_node,
//                                           std::memory_order_release,
//                                           std::memory_order_relaxed));
    }
};
int main()
{
    stack<int> s;
    s.push(1);
    s.push(2);
    s.push(3);
}
```


# Links

1. [https://en.cppreference.com/w/cpp/atomic/atomic/compare_exchange](https://en.cppreference.com/w/cpp/atomic/atomic/compare_exchange)
