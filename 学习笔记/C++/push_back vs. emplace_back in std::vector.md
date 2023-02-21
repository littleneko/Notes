从 C++11 开始，`std::vector` 新增了 `emplace_back` 方法，其实现的功能和 `push_back` 功能一样，区别是什么呢？

# push_back

push_back 有两个重载方法，分别对应左值和右值参数（注意这里的模板 T 在定义 vector 时就已经确定类型，在 调用 push_back 时不存在类型推导，因此不是通用引用）

```c++
void push_back( const T& value );
void push_back( T&& value );
```



```c++
// [23.2.4.3] modifiers
/**
 *  @brief  Add data to the end of the %vector.
 *  @param  __x  Data to be added.
 *
 *  This is a typical stack operation.  The function creates an
 *  element at the end of the %vector and assigns the given data
 *  to it.  Due to the nature of a %vector this operation can be
 *  done in constant time if the %vector has preallocated space
 *  available.
 */
_GLIBCXX20_CONSTEXPR
void
push_back(const value_type& __x)
{
		if (this->_M_impl._M_finish != this->_M_impl._M_end_of_storage)
		{
  		_GLIBCXX_ASAN_ANNOTATE_GROW(1);
  		_Alloc_traits::construct(this->_M_impl, this->_M_impl._M_finish,
			     				__x);
  		++this->_M_impl._M_finish;
  		_GLIBCXX_ASAN_ANNOTATE_GREW(1);
		}
		else
		_M_realloc_insert(end(), __x);
}
```



```c++
#if __cplusplus >= 201103L
      _GLIBCXX20_CONSTEXPR
      void
      push_back(value_type&& __x)
      { emplace_back(std::move(__x)); }
#endif
```

# emplace_back

emplace_back 的类型模板定义为 _Args，而不是 T，在调用 emplace_back 时存在类型推导，因此参数 args 是一个通用引用，而且 args 是一个可变参数模板。因此 emplace_back 可以接受左值、右值、多个参数等。

```c++
template< class... Args >
void emplace_back( Args&&... args );
```



```c++
#if __cplusplus >= 201103L
  template<typename _Tp, typename _Alloc>
    template<typename... _Args>
#if __cplusplus > 201402L
      _GLIBCXX20_CONSTEXPR
      typename vector<_Tp, _Alloc>::reference
#else
      void
#endif
      vector<_Tp, _Alloc>::
      emplace_back(_Args&&... __args)
      {
	if (this->_M_impl._M_finish != this->_M_impl._M_end_of_storage)
	  {
	    _GLIBCXX_ASAN_ANNOTATE_GROW(1);
	    _Alloc_traits::construct(this->_M_impl, this->_M_impl._M_finish,
				     std::forward<_Args>(__args)...);
	    ++this->_M_impl._M_finish;
	    _GLIBCXX_ASAN_ANNOTATE_GREW(1);
	  }
	else
	  _M_realloc_insert(end(), std::forward<_Args>(__args)...);
#if __cplusplus > 201402L
	return back();
#endif
      }
#endif
```



# 区别

```c++
#include <iostream>
#include <utility>
#include <vector>

struct A {
  std::string s;

  A(const char *s) : s(s) { std::cout << "construct\n"; }

  A(const A &o) : s(o.s) { std::cout << "copy construct\n"; }

  A(A &&o) : s(std::move(o.s)) { std::cout << "move construct\n"; }

  A &operator=(const A &other) {
    s = other.s;
    std::cout << "copy assigned\n";
    return *this;
  }

  A &operator=(A &&other) {
    s = std::move(other.s);
    std::cout << "move assigned\n";
    return *this;
  }

  virtual ~A() { std::cout << "deconstruct\n"; }
};

int main(int argc, char const *argv[]) {
  std::vector<A> v1;
  {
    // A a{"test"};
    // v1.push_back(a);										// 1. construct -> copy construct -> deconstruct
    // v1.emplace_back(a);								// 2. 同 1
    // v1.push_back(std::move(a));				// 3. construct -> move construct -> deconstruct
    // v1.emplace_back(std::move(a));			// 4. 同 3
    // v1.push_back("test");							// 5. construct -> move construct -> deconstruct
    // v1.emplace_back("test");						// 6. construct
  }
  std::cout << "END\n";
  return 0;
}
```

无论是传递左值还是右值对象，push_back 和 emplace_back 没有任何区别，唯一的区别在于直接传递 A 对象的构造函数参数时：

1. `v1.push_back("test")`：构造临时 A 对象（右值），掉用 push_back 的右值重载函数，销毁临时对象
2. `v1.emplace_back("test")`：直接在 vector 中构造 A 对象

> **Tips**:
>
> `v1.push_back("test")` 这种调用方式需要 A 对象支持隐式转换，如果构造函数定义为 explicit 则不能使用这种方式；另外如果构造函数需要多个参数，也不能使用这种方法。但是两种情况都可以使用 `v1.emplace_back("test") ` 或 `v1.emplace_back("test", "test2")` 这种方式调用。

# Links

1. [https://zhuanlan.zhihu.com/p/213853588](https://zhuanlan.zhihu.com/p/213853588)