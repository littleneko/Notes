# 函数指针和类成员函数指针

TODO


# std::function
<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1632415383999-256f06f1-0e87-4066-a665-2871c5dfa3bb.png" alt="image.png" style="zoom:50%;" />

`std::function<R(Args...)>` 存储一个返回值类型为 `R`，参数为 `Args...` 的函数，它可以存储任何 [_CopyConstructible_](https://en.cppreference.com/w/cpp/named_req/CopyConstructible) [_Callable_](https://en.cppreference.com/w/cpp/named_req/Callable) target，包括==函数==、==lambda 表达式==、==`std::bind` 对象==、==function objects==、==类的成员函数指针==或==类的成员指针==。
​

现在有下面的一些定义：
```cpp
#include <functional>
#include <iostream>
 
struct Foo {
    Foo(int num) : num_(num) {}
    void print_add(int i) const { std::cout << num_+i << '\n'; }
    int num_;
};
 
void print_num(int i)
{
    std::cout << i << '\n';
}
 
struct PrintNum {
    void operator()(int i) const
    {
        std::cout << i << '\n';
    }
};
```
这些调用都是合法的：
```cpp
int main()
{
    // store a free function
    std::function<void(int)> f_display = print_num;
    f_display(-9);
 
    // store a lambda
    std::function<void()> f_display_42 = []() { print_num(42); };
    f_display_42();
 
    // store the result of a call to std::bind
    std::function<void()> f_display_31337 = std::bind(print_num, 31337);
    f_display_31337();
 
    // store a call to a member function
    std::function<void(const Foo&, int)> f_add_display = &Foo::print_add;
    const Foo foo(314159);
    f_add_display(foo, 1);
    f_add_display(314159, 1);
 
    // store a call to a data member accessor
    std::function<int(Foo const&)> f_num = &Foo::num_;
    std::cout << "num_: " << f_num(foo) << '\n';
 
    // store a call to a member function and object
    using std::placeholders::_1;
    std::function<void(int)> f_add_display2 = std::bind( &Foo::print_add, foo, _1 );
    f_add_display2(2);
 
    // store a call to a member function and object ptr
    std::function<void(int)> f_add_display3 = std::bind( &Foo::print_add, &foo, _1 );
    f_add_display3(3);
 
    // store a call to a function object
    std::function<void(int)> f_display_obj = PrintNum();
    f_display_obj(18);
 
    auto factorial = [](int n) {
        // store a lambda object to emulate "recursive lambda"; aware of extra overhead
        std::function<int(int)> fac = [&](int n){ return (n < 2) ? 1 : n*fac(n-1); };
        // note that "auto fac = [&](int n){...};" does not work in recursive calls
        return fac(n);
    };
    for (int i{5}; i != 8; ++i) { std::cout << i << "! = " << factorial(i) << ";  "; }
}
```
其输出结果：
```
-9
42
31337
314160
314160
num_: 314159
314161
314162
18
5! = 120;  6! = 720;  7! = 5040;
```


从上面的例子中看到，在存储一个普通函数和成员函数时的区别，

1. ==普通函数直接用函数名初始化就可以，类成员函数需要显示地取地址==（`&Foo::print_add`），普通函数的函数名实际上就是其地址，即函数指针，不需要再取地址；而成员函数不支持这种隐式转换。
1. ==类成员函数 function 需要一个 `const Foo&` 参数==（`std::function<void(const Foo&, int)>`），因为类成员函数必须由一个对象调用。
```cpp
// store 普通函数
std::function<void(int)> f_display = print_num;
// 使用时直接调用
f_display(-9);

// store 类成员函数
std::function<void(const Foo&, int)> f_add_display = &Foo::print_add;
// 使用时需要传入 Foo 对象
f_add_display(foo, 1);
```


使用 `std::bind` 到类成员函数：
```cpp
// bind 类成员函数
using std::placeholders::_1;
std::function<void(int)> f_add_display2 = std::bind( &Foo::print_add, foo, _1 );
// 使用
f_add_display2(2);
```
与上面直接绑定到类成员函数相比，function 的定义不再需要一个 `const Foo&` 参数，因为已经在 bind 时传入了一个 foo 对象。
​

使用 `std::bind` 到类成员函数时，可以传入对象值和指针：
```cpp
// store a call to a member function and object
using std::placeholders::_1;
std::function<void(int)> f_add_display2 = std::bind( &Foo::print_add, foo, _1 );
f_add_display2(2);
 
// store a call to a member function and object ptr
std::function<void(int)> f_add_display3 = std::bind( &Foo::print_add, &foo, _1 );
f_add_display3(3);
```

# std::bind

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1632419116414-84f35b8c-2b03-42ff-a6d6-8ab850a87c31.png" alt="image.png" style="zoom:50%;" />

```cpp
#include <functional>
#include <iostream>
 
void f(int& n1, int& n2, const int& n3)
{
    std::cout << "In function: " << n1 << ' ' << n2 << ' ' << n3 << '\n';
    ++n1; // increments the copy of n1 stored in the function object
    ++n2; // increments the main()'s n2
    // ++n3; // compile error
}
 
int main()
{
    int n1 = 1, n2 = 2, n3 = 3;
    std::function<void()> bound_f = std::bind(f, n1, std::ref(n2), std::cref(n3));
    n1 = 10;
    n2 = 11;
    n3 = 12;
    std::cout << "Before function: " << n1 << ' ' << n2 << ' ' << n3 << '\n';
    bound_f();
    std::cout << "After function: " << n1 << ' ' << n2 << ' ' << n3 << '\n';
}
```


output:
```
Before function: 10 11 12
In function: 1 11 12
After function: 10 12 12
```


```cpp
  /**
   *  @brief Function template for std::bind.
   *  @ingroup binders
   */
  template<typename _Func, typename... _BoundArgs>
    inline _GLIBCXX20_CONSTEXPR typename
    _Bind_helper<__is_socketlike<_Func>::value, _Func, _BoundArgs...>::type
    bind(_Func&& __f, _BoundArgs&&... __args)
    {
      typedef _Bind_helper<false, _Func, _BoundArgs...> __helper_type;
      return typename __helper_type::type(std::forward<_Func>(__f),
					  std::forward<_BoundArgs>(__args)...);
    }

  template<typename _Result, typename _Func, typename... _BoundArgs>
    struct _Bindres_helper
    : _Bind_check_arity<typename decay<_Func>::type, _BoundArgs...>
    {
      typedef typename decay<_Func>::type __functor_type;
      typedef _Bind_result<_Result,
			   __functor_type(typename decay<_BoundArgs>::type...)>
	type;
    };

  /**
   *  @brief Function template for std::bind<R>.
   *  @ingroup binders
   */
  template<typename _Result, typename _Func, typename... _BoundArgs>
    inline _GLIBCXX20_CONSTEXPR
    typename _Bindres_helper<_Result, _Func, _BoundArgs...>::type
    bind(_Func&& __f, _BoundArgs&&... __args)
    {
      typedef _Bindres_helper<_Result, _Func, _BoundArgs...> __helper_type;
      return typename __helper_type::type(std::forward<_Func>(__f),
					  std::forward<_BoundArgs>(__args)...);
    }

```

# std::ref and std::cref

TODO


# Links

1. [https://en.cppreference.com/w/cpp/utility/functional/bind](https://en.cppreference.com/w/cpp/utility/functional/bind)
1. [https://en.cppreference.com/w/cpp/utility/functional/ref](https://en.cppreference.com/w/cpp/utility/functional/ref)
1. [https://en.cppreference.com/w/cpp/utility/functional/reference_wrapper](https://en.cppreference.com/w/cpp/utility/functional/reference_wrapper)
