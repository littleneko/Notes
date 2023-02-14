**RAII**，全称资源获取即初始化（Resource Acquisition Is Initialization），它是在一些面向对象语言中的一种惯用法。RAII 源于 C++，在 Java，C#，D，Ada，Vala 和 Rust 中也有应用。1984-1989 年期间，比雅尼·斯特劳斯特鲁普和安德鲁·柯尼希在设计 C++ 异常时，为解决资源管理时的异常安全性而使用了该用法，后来比雅尼·斯特劳斯特鲁普将其称为 RAII。

RAII 要求，==资源的有效期与持有资源的对象的生命期严格绑定==，即==由对象的构造函数完成资源的分配（获取），同时由析构函数完成资源的释放==。在这种要求下，只要对象能正确地析构，就不会出现资源泄露问题。

RAII 在 C++ 中的应用非常广泛，如 C++ 标准库中的 `std::lock_guard` 便是用 RAII 方式来控制互斥量:

```cpp
#include <fstream>
#include <iostream>
#include <mutex>
#include <stdexcept>
#include <string>

void WriteToFile(const std::string& message) {
  // |mutex| is to protect access to |file| (which is shared across threads).
  static std::mutex mutex;

  // Lock |mutex| before accessing |file|.
  std::lock_guard<std::mutex> lock(mutex);

  // Try to open file.
  std::ofstream file("example.txt");
  if (!file.is_open()) {
    throw std::runtime_error("unable to open file");
  }

  // Write |message| to |file|.
  file << message << std::endl;

  // |file| will be closed first when leaving scope (regardless of exception)
  // mutex will be unlocked second (from lock destructor) when leaving scope
  // (regardless of exception).
}
```

This code is exception-safe ==because C++ guarantees that all stack objects are destroyed at the end of the enclosing scope==, known as stack unwinding. The destructors of both the lock and file objects are therefore guaranteed to be called when returning from the function, ==whether an exception has been thrown or not==.

Local variables allow easy management of multiple resources within a single function: they are destroyed in the reverse order of their construction, and an object is destroyed only if fully constructed—that is, if no exception propagates from its constructor.

Using RAII greatly simplifies resource management, reduces overall code size and helps ensure program correctness. RAII is therefore recommended by industry-standard guidelines,[15] and most of the C++ standard library follows the idiom.

# Links

1. [https://en.cppreference.com/w/cpp/language/raii](https://en.cppreference.com/w/cpp/language/raii)
1. [https://en.wikipedia.org/wiki/Resource_acquisition_is_initialization](https://en.wikipedia.org/wiki/Resource_acquisition_is_initialization)
1. [https://zh.wikipedia.org/wiki/RAII](https://zh.wikipedia.org/wiki/RAII)
1. [https://zhuanlan.zhihu.com/p/34660259](https://zhuanlan.zhihu.com/p/34660259)
