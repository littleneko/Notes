# Summary
返回值优化（Return value optimization，缩写为 RVO）是 C++的 一项编译优化技术，即删除保持函数返回值的临时对象，这可能会省略两次复制构造函数，即使复制构造函数有副作用。


典型地，当一个函数返回一个对象实例，一个临时对象将被创建并通过复制构造函数把目标对象复制给这个临时对象。C++ 标准允许省略这些复制构造函数，即使这导致程序的不同行为，即使编译器把两个对象视作同一个具有副作用。


假设有如下代码：
```cpp
#include <iostream>

class C {
public:
  explicit C() { std::cout << "constructor" << std::endl; }

  C(const C &c) { std::cout << "copy constructor" << std::endl; }

  ~C() { std::cout << "destructor" << std::endl; }
};

C fun1() {
  return C();
  // or
  // C c;
  // return c;
}

int main() {
  C c = fun1();
  return 0;
}
```


关闭 RVO/NRVO（g++ 添加参数 `-fno-elide-constructors`），输出如下：
```cpp
constructor			// fun1 中对象构造
copy constructor	// 调用拷贝构造函数构造一个临时对象用于返回
destructor			// fun1 中对象析构
copy constructor	// 调用拷贝构造函数使用临时对象构造 main 中的 c 对象
destructor			// 临时对象销毁
destructor			// main 中的 a 对象销毁
```
可以看到构造了一个临时对象用于返回，一共产生了 2 次拷贝构造。


> **Tips**:
> 根据编译器的不同，你可能会看到如下结果：
> \> constructor
> \> copy constructor
> \> destructor
> \> destructor



在开启 RVO/NRVO （g++ 默认开启）时，其输出结果是：
```cpp
constructor
destructor
```
可以看到，只有一次的构造和析构。
# Background
从函数返回内置类型（built-in type）通常几乎没有开销，原因是该对象通常适合 CPU 寄存器；返回更大的 class 类型对象可能需要从一个内存位置复制到另一个内存位置，成本更高。为了避免这种情况，一种实现办法是在函数调用语句前在 stack frame 上声明一个隐藏对象，把该对象的地址隐蔽传入被调用函数，函数的返回对象直接构造或者复制构造到该地址上，例如：
```cpp
struct Data { 
  char bytes[16]; 
};

Data F() {
  Data result = {};
  // generate result
  return result;
}

int main() {
  Data d = F();
}
```
可能产生的代码如下：
```cpp
struct Data {
  char bytes[16];
};

Data* F(Data* _hiddenAddress) {
  Data result = {};
  // copy result into hidden object
  *_hiddenAddress = result;
  return _hiddenAddress;
}

int main() {
  Data _hidden;           // create hidden object
  Data d = *F(&_hidden);  // copy the result into d
}
```
这引起了 Data 对象被复制两次。


在 C++ 发展的早期阶段，无法有效地从函数返回类类型的对象，这被认为是一个缺陷。在 1991 年左右，Walter Bright 实现了一种技术来最小化复制，有效地将函数内的隐藏对象和命名对象替换为用于保存结果的对象：
```cpp
struct Data {
  char bytes[16];
};

void F(Data* p) {
  // generate result directly in *p
}

int main() {
  Data d;
  F(&d);
}
```
Bright 在他的 Zortech C++ 编译器中实现了这个优化，这种特殊的技术后来被称为“命名返回值优化”（Named return value optimization，缩写为 NRVO），指的是省略了命名对象的复制这一事实。
# Compiler support
大多数编译器都支持返回值优化，但是，可能存在编译器无法执行优化的情况。一种常见的情况是，函数可能会根据执行路径返回不同的命名对象。
```cpp
#include <string>
std::string F(bool cond = false) {
  std::string first("first");
  std::string second("second");
  // the function may return one of two named objects
  // depending on its argument. RVO might not be applied
  return cond ? first : second;
}

int main() {
  std::string result = F();
}
```
# RVO/NRVO 和 std::move 的陷阱
假设我们的 class C 支持移动构造：
```cpp
#include <iostream>

class C {
public:
  explicit C() { std::cout << "constructor" << std::endl; }

  C(const C &c) { std::cout << "copy constructor" << std::endl; }

  C(C &&c) { std::cout << "move constructor" << std::endl; }

  ~C() { std::cout << "destructor" << std::endl; }
};

C fun1() { return C(); }

int main() {
  C c = fun1();
  return 0;
}

```
在关闭 RVO/NRVO 的情况下，代码输入如下：
```cpp
constructor
move constructor
destructor
move constructor
destructor
destructor
```
可以看到，默认情况下是调用了移动构造函数而不是拷贝构造函数进行临时对象和 c 的构造。


现在，我们打开 RVO/NRO，得到的结果仍然是：
```cpp
constructor
destructor
```


现在，我们把 fun1 改成下面的实现：
```cpp
C fun1() {
  C c;
  return std::move(c);
}
```
得到的输出结果是：
```cpp
constructor
move constructor		// fun1 中的 a move 到 main 中的 a
destructor
destructor
```
居然多了一次 move 操作，原因是这里 RVO/NRVO 优化已经失效了，Why?


RVO/NRVO 优化的前提是：

1. 局部对象与函数返回值的类型相同
1. 返回的是局部对象

可以看到，最开始版本的 fun1 满足上面两个要求，因此能够被优化。但是 std::move(c) 版本的 fun1 不满足第 2 个要求，返回值并不是局部对象 c，而是 c 的引用（_a reference to c）_，所以编译器必须移动 c 到函数返回值的位置。我们试图对要返回的局部变量用 `std::move` 帮助编译器优化，反而限制了编译器的优化选项。


# Links

1. [https://en.wikipedia.org/wiki/Copy_elision#Return_value_optimization](https://en.wikipedia.org/wiki/Copy_elision#Return_value_optimization)
1. [https://zhuanlan.zhihu.com/p/346175992](https://zhuanlan.zhihu.com/p/346175992)
