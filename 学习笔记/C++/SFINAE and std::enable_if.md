# SFINAE
替换失败并非错误 (Substitution failure is not an error, **SFINAE**) 是指 C++ 语言在模板参数匹配失败时不认为这是一个编译错误。戴维·范德沃德最先引入 SFINAE 缩写描述相关编程技术。


具体说，当创建一个重载函数的候选集时，某些（或全部）候选函数是用模板实参替换（可能的推导）模板形参的模板实例化结果。==如果某个模板的实参替换时失败，编译器将在候选集中删除该模板，而不是当作一个编译错误从而中断编译过程，这需要C++语言标准授予如此处理的许可。如果一个或多个候选保留下来，那么函数重载的解析就是成功的，函数调用也是良好的==。


## 例子
下属简单例子解释了 SFINAE：
```cpp
struct Test {
  typedef int foo;
};

template <typename T>
void f(typename T::foo) {}  // Definition #1

template <typename T>
void f(T) {}  // Definition #2

int main() {
  f<Test>(10);  // Call #1.
  f<int>(10);   // Call #2. 并无编译错误(即使没有 int::foo)
                // thanks to SFINAE.
}
```
在限定名字解析时 (`T::foo`) 使用非类的数据类型，导致 `f<int>` 推导失败因为 `int` 并无嵌套数据类型 `foo`, 但程序仍是良好定义的，因为候选函数集中还有一个有效的函数。


虽然 SFINAE 最初引入时是用于避免在不相关模板声明可见时（如通过包含头文件）产生不良程序。许多程序员后来发现这种行为可用于==编译时[内省](https://zh.wikipedia.org/wiki/%E5%86%85%E7%9C%81_(%E8%AE%A1%E7%AE%97%E6%9C%BA%E7%A7%91%E5%AD%A6))（introspection）==，具体说，==在模板实例化时允许模板确定模板参数的特定性质==。


例如，SFINAE 用于确定一个类型是否包含特定 typedef：
```cpp
#include <iostream>

template <typename T>
struct has_typedef_foobar {
  // Types "yes" and "no" are guaranteed to have different sizes,
  // specifically sizeof(yes) == 1 and sizeof(no) == 2.
  typedef char yes[1];
  typedef char no[2];

  template <typename C>
  static yes& test(typename C::foobar*);

  template <typename>
  static no& test(...);

  // If the "sizeof" of the result of calling test<T>(nullptr) is equal to
  // sizeof(yes), the first overload worked and T has a nested type named
  // foobar.
  static const bool value = sizeof(test<T>(nullptr)) == sizeof(yes);
};

struct foo {
  typedef float foobar;
};

int main() {
  std::cout << std::boolalpha;
  std::cout << has_typedef_foobar<int>::value << std::endl;  // Prints false
  std::cout << has_typedef_foobar<foo>::value << std::endl;  // Prints true
}
```
当类型 `T` 有嵌套类型 `foobar`，`test` 的第一个定义被实例化并且空指针常量被作为参数传入。（结果类型是`yes` 。）如果不能匹配嵌套类型 `foobar` ，唯一可用函数是第二个 `test` 定义，且表达式的结果类型为 `no`。省略号（ellipsis）不仅用于接收任何类型，它的转换的优先级是最低的，因而优先匹配第一个定义，这去除了二义性。

---

**C++11 的简化:**

```cpp
#include <iostream>
#include <type_traits>

template <typename... Ts>
using void_t = void;

template <typename T, typename = void>
struct has_typedef_foobar : std::false_type {};

template <typename T>
struct has_typedef_foobar<T, void_t<typename T::foobar>> : std::true_type {};

struct foo {
  using foobar = float;
};

int main() {
  std::cout << std::boolalpha;
  std::cout << has_typedef_foobar<int>::value << std::endl;
  std::cout << has_typedef_foobar<foo>::value << std::endl;
}
```


# std::enable_if
<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1637689647209-3cfa8a13-07f2-41fb-8274-0c00a54ebeed.png" alt="image.png" style="zoom:50%;" />

If B is true, std::enable_if has a public member typedef type, equal to T; otherwise, there is no member typedef.

`std::enable_if` 是利用 SFINAE 根据类型特征有条件地从重载解析中移除函数，并为不同类型特征提供单独的函数重载和特化的便捷方式。 `std::enable_if` 可用作==附加函数参数（不适用于运算符重载==）、==返回类型（不适用于构造函数和析构函数==）或用作==类模板或函数模板参数==。


## 使用
基本用法示例：
```cpp
struct T {
    enum { int_t, float_t } type;
    template <typename Integer,
              std::enable_if_t<std::is_integral<Integer>::value, bool> = true
    >
    T(Integer) : type(int_t) {}
 
    template <typename Floating,
              std::enable_if_t<std::is_floating_point<Floating>::value, bool> = true
    >
    T(Floating) : type(float_t) {} // OK
};
```
当传入的参数是 `int` 类型时，启用第一个构造函数；而当传入的参数是 `float` 时，启用第二个构造函数。
(用于附加函数参数，返回类型的例子不在这里赘述了)


## 实现
```cpp
  /// Define a member typedef @c type only if a boolean constant is true.
  template<bool, typename _Tp = void>
    struct enable_if
    { };

  // Partial specialization for true.
  template<typename _Tp>
    struct enable_if<true, _Tp>
    { typedef _Tp type; };
```
首先定义了一个类模板 `enable_if`，有一个 `bool` 型的非类型模板参数 (non-type template parameter)和一个普通模板参数 \_Tp，默认情况下 enable_if 并没有 typedef 一个 type 成员类型。

另外还有一个 非类型模板参数 为 `true` 时的偏特化，该偏特化类型 typedef 了 一个 \_Tp 类型的 type 类型成员。


上面的例子中，==使用 `typename std::enable_if<condition, bool>::type` 作为类/函数模板参数就是为了让 `std::enable_if` 参与到函数类型中==。

- ==当 condition 为 `true` 时，enable_if 有 type 类型，Substitution 成功，因此当前的函数/类模板被启用==；
- ==当 condition 为 `false` 时，enable_if 根本就没有 type 类型，**于是 Substitution 失败 (failure) ，因此这个函数/类模板原型根本就不会被产生出来**==。

---

另外 C++ 14 中定义了 `std::enable_if_t`  的别名，更易于使用：
```cpp
  /// Alias template for enable_if
  template<bool _Cond, typename _Tp = void>
    using enable_if_t = typename enable_if<_Cond, _Tp>::type;
```


# Links

1. [https://en.wikipedia.org/wiki/Substitution_failure_is_not_an_error](https://en.wikipedia.org/wiki/Substitution_failure_is_not_an_error)
1. [https://en.cppreference.com/w/cpp/language/sfinae](https://en.cppreference.com/w/cpp/language/sfinae)
1. [https://en.cppreference.com/w/cpp/types/enable_if](https://en.cppreference.com/w/cpp/types/enable_if)
1. [https://en.cppreference.com/w/cpp/language/template_parameters](https://en.cppreference.com/w/cpp/language/template_parameters)
1. [https://zhuanlan.zhihu.com/p/21314708](https://zhuanlan.zhihu.com/p/21314708)
