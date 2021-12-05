从 C++11 开始，`std::vector` 新增了 `emplace_back` 方法，其实现的功能和 `push_back` 功能一样，区别是什么呢？

```c++
void push_back( const T& value );
void push_back( T&& value );
```



```c++
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
      void
      push_back(value_type&& __x)
      { emplace_back(std::move(__x)); }

      template<typename... _Args>
#if __cplusplus > 201402L
	reference
#else
	void
#endif
	emplace_back(_Args&&... __args);
#endif
```



```c++
#if __cplusplus >= 201103L
      template<typename... _Args>
#if __cplusplus > 201402L
	reference
#else
	void
#endif
	emplace_back(_Args&&... __args)
	{
	  push_back(bool(__args...));
#if __cplusplus > 201402L
	  return back();
#endif
	}
```



```c++
template< class... Args >
void emplace_back( Args&&... args );
```



# Links

1. [https://zhuanlan.zhihu.com/p/213853588](https://zhuanlan.zhihu.com/p/213853588)