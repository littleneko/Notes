# Primary type categories
<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1637693553183-1d3eb3fc-a816-47c4-93da-41099537682e.png" alt="image.png" style="zoom:50%;" />

以 `std::is_integral<>` 为例：

```cpp
  /// is_integral
  template<typename _Tp>
    struct is_integral
    : public __is_integral_helper<__remove_cv_t<_Tp>>::type
    { };
```
`is_integral` 继承自 `__is_integral_helper<>` ，首先，移除掉 `_Tp` 的 `const`/`volatile`/`const volatile` 属性，然后使用 `__is_integral_helper<>::type` 判断 `_Tp` 是否是 `integer` 类型。


`__is_integral_helper<>` 是一个类模板，默认情况下 `type` 是 `false_type`，然后针对不同类型进行**模板特化**，`bool`/`char`/`int`/`long` 等特化类型都是返回 `true_type` 。因此在模板实例化时，这些类型都会匹配到相应的特化模板，得到的 `type` 就是 `true_type`
```cpp
  template<typename>
    struct __is_integral_helper
    : public false_type { };

  template<>
    struct __is_integral_helper<bool>
    : public true_type { };

  template<>
    struct __is_integral_helper<char>
    : public true_type { };

  template<>
    struct __is_integral_helper<signed char>
    : public true_type { };

  template<>
    struct __is_integral_helper<unsigned char>
    : public true_type { };

// 此处省略一万行

  template<>
    struct __is_integral_helper<short>
    : public true_type { };

  template<>
    struct __is_integral_helper<unsigned short>
    : public true_type { };

  template<>
    struct __is_integral_helper<int>
    : public true_type { };

  template<>
    struct __is_integral_helper<unsigned int>
    : public true_type { };

  template<>
    struct __is_integral_helper<long>
    : public true_type { };

  template<>
    struct __is_integral_helper<unsigned long>
    : public true_type { };

// 此处省略一万行
```


# Composite type categories
<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1637693650207-0ae1da26-ae5d-4242-823e-c7714993ddeb.png" alt="image.png" style="zoom:50%;" />

# Type properties
<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1637693691609-d41a80e9-cac9-426a-a4ba-6b5d2ff0388c.png" alt="image.png" style="zoom:50%;" />

# Type relationships
<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1637693720587-a127db99-f43c-4c83-9957-e086a35985c3.png" alt="image.png" style="zoom:50%;" />

# Const-volatility specifiers
<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1637693749464-613c4c04-9ba0-466e-96e0-a9ac83080f58.png" alt="image.png" style="zoom:50%;" />


# References
<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1637693769292-900c5f71-e2f5-4b7d-b643-2882d04bad9d.png" alt="image.png" style="zoom:50%;" />

# Miscellaneous transformations
<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1637693790157-12df3b0d-f0ce-4e37-b866-2b9d0b64792a.png" alt="image.png" style="zoom:50%;" />


# Links

1. [https://en.cppreference.com/w/cpp/header/type_traits](https://en.cppreference.com/w/cpp/header/type_traits)
1. [https://en.cppreference.com/w/cpp/types/is_integral](https://en.cppreference.com/w/cpp/types/is_integral)
1. [https://en.cppreference.com/w/cpp/types/decay](https://en.cppreference.com/w/cpp/types/decay)
1. [https://zhuanlan.zhihu.com/p/98106799](https://zhuanlan.zhihu.com/p/98106799)
