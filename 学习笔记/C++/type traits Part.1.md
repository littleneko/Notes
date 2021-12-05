可能对很多 C++ 程序员而言，Type Traits 并不陌生，它被大量应用在模板元编程中。从字面上理解，Type Traits就是 “类型的特征” 的意思。在 C++ 元编程中，程序员不少时候都需要了解一些类型的特征信息，并根据这些类型信息选择应有的操作。Type Traits 有助于编写通用、可复用的代码。

可能这些描述有些虚，下面就通过简单的例子来说明 Type Traits 是如何改善我们的 C++ 代码的。假设我们要实现一个针对 16 位、32 位型或 64 位整数类型的字节交换的功能，借助于 C++ 泛型编程，我们可以很容易的实现：
```cpp
template <typename T>
T byte_swap( T value ) {
  unsigned char *bytes = reinterpret_cast< unsigned char * >( &value );
  for (size_t i = 0; i < sizeof( T ); i += 2) {
    // Take the value on the left and switch it 
    // with the value on the right
    unsigned char v = bytes[ i ];
    bytes[ i ] = bytes[ i + 1 ];
    bytes[ i + 1 ] = v;
  }
  return value;
}
```
如果传入 32 位的值 0x11223344，返回值为 0x22114433，如果传入 16 位的值 0x1122，将返回 0x2211。看起来这个功能实现的不错，但是，如果传入一个 char 类型的值呢？代码会因为访问到不属于自己的内存而引起程序崩溃。由于模板的泛型特性，我们也无法阻止用户传递这样类型的值。

为了处理用户传入的 double 和 char 类型的值，我们可以加入模板特化进行处理：
```cpp
template <>
double byte_swap( double value ) {
  assert( false && "Illegal to swap doubles" );
  return value;
}
 
template <>
char byte_swap( char value ) {
  assert( false && "Illegal to swap chars" );
  return value;
}
```
这个特化处理可以处理传入的 double 和 char 类型的值，问题是，用户还可能传入 float、unsigned char 等类型。如果我们为每种类型都添加上特化处理，可以想象得到，代码会膨胀成怎样。

这个时候 Type Traits 可以派上用场了。Type Traits 是在编译时获取有关作为模板参数传入的类型的信息的一种方式，因此我们可以做出更明智的决定。 Type Traits 的典型用法如下：

- 使用一个模板化的结构，通常以的类型特征命名。例如 is_integer，is_pointer，is_void 等等
- 结构包含一个静态 const bool 命名值
- 我们可以对特征的结构进行特化，并且把它们的布尔值设置为一个合理的状态值
- 我们可以查询其值来使用类型特征，如：my_type_trait::value



还是继续上面的例子来说明，我们可以通过定义一个类型特征来决定某个类型的值是否可交换：
```cpp
template <typename T>
struct is_swapable {
  static const bool value = false;
};
 
template <>
struct is_swapable<unsigned short> {
  static const bool value = true;
};
 
template <>
struct is_swapable<short> {
  static const bool value = true;
};
 
template <>
struct is_swapable<unsigned long> {
  static const bool value = true;
};
 
template <>
struct is_swapable<long> {
  static const bool value = true;
};
 
template <>
struct is_swapable<unsigned long long> {
  static const bool value = true;
};
 
template <>
struct is_swapable<long long> {
  static const bool value = true;
};
```
这样我们只需在 byte_swap 函数中增加一行语句：
```cpp
assert(is_swapable<T>::value && "Cannot swap this type");
```
这就是 Type Traits 的核心用法。然而，您可能还是有点不满意，这也加入了好多的代码。别着急，在 C++11 中加入了一个标准的 STL 头文件 type_traits，里面包含了几乎所有数据类型的类型特征，它可以告诉数据的基本类型、是否指针、是否数组等等。大多数情况下，我们可以直接使用内置的类型特征。

此外 C++11 还引入了一个新的 static_assert 函数，它可以在编译时就检查出错误。如果我们使用 C++11 改写上面的 byte_swap，代码如下：
```cpp
static_assert(std::is_integral<T>::value && sizeof(T) >= 2, "Cannot swap values of this type" );
```
这其中 is_integral 是 C++11 标准的一部分，而 static_assert 在编译阶段就可以引发断言错误，这可以避免传递不合适的值给 byte_swap 函数。

此外，我们还可以利用其它的类型特征来编写 type traits，比如前面的 is_swapable 就可以这样写：
```cpp
template <typename T>
struct is_swapable {
  static const bool value = std::is_integral<T>::value && sizeof(T) >= 2;
};
```
# Links

1. [https://blog.aaronballman.com/2011/11/a-simple-introduction-to-type-traits/](https://blog.aaronballman.com/2011/11/a-simple-introduction-to-type-traits/)
