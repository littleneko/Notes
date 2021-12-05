```c++
template<int B, int N>
struct Pow {
    // recursive call and recombination.
    enum{ value = B*Pow<B, N-1>::value };
};

template< int B > 
struct Pow<B, 0> { 
    // ''N == 0'' condition of termination.
    enum{ value = 1 };
};
int quartic_of_three = Pow<3, 4>::value;
```



# Links

1. [https://zhuanlan.zhihu.com/p/137853957](https://zhuanlan.zhihu.com/p/137853957)
2. [https://zhuanlan.zhihu.com/p/87917516](https://zhuanlan.zhihu.com/p/87917516)
3. [https://www.cnblogs.com/liangliangh/p/4219879.html](https://www.cnblogs.com/liangliangh/p/4219879.html)