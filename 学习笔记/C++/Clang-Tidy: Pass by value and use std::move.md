最近在看 leveldb 源码的时候，Clion 给出了如下提示：

![image-20220801231058616](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220801231058616.png)

按 Clion 给出的提示应该修改为如下所示的代码：

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220801231239936.png" alt="image-20220801231239936"  />



通常来说，传 const reference 来避免 copy 的效率应该更高，为什么这里 Clion 反而提示要传值然后 std::move 呢？

我们来分析一下两种写法的区别：

1. **传引用**：参数传递时不需要 copy，但是参数初始化 class field 的时候需要一次 copy
2. **传值**：参数传递时有一次 copy，初始化 class field 时因为是 `std::move`，不需要 copy

两种方式都是一次 copy，区别在于 copy 发生的时机，那为什么 Clang-Tidy 推荐第 2 中写法呢？



主要原因是现代 C++ 有 *copy elision* 优化（RVO 就是其中一种），在一个声明了 value 参数的函数中，当函数实际参数是 rvalue 时，编译器能判断出多余的 copy 操作，并主动忽略之，在函数内直接使用了实参对象。

回到上面的两种情况，如果 c 是一个 rvalue，那么第二种写法一次 copy 都不需要了；但是第一种写法仍然需要一次 copy。



**Example**：

```c++
class A {
public:
    A(const std::string& s): s_(s) {
        std::cout << "construct" << std::endl;
    }

    A(const A& a) {
        s_ = a.s_;
        std::cout << "copy construct" << std::endl;
    }

    A(A&& a) {
        s_ = std::move(a.s_);
        std::cout << "move construct" << std::endl;
    }

private:
    std::string s_;
};
```

如果 B 的构造函数定义成 const reference：

```c++
class B {
public:
    B(const A& a): a_(a) {}
private:
    A a_;
};
```

下面的代码执行的结果如下所示：

```c++
    A a{"abc"};
    B b(a); 						// copy
    B b(std::move(a));	// copy
```



如果 B 的构造函数定义成传值：

```C++
class B {
public:
    B(A a): a_(std::move(a) {}
private:
    A a_;
};
```

下面的代码执行的结果如下所示：

```c++
A a{"abc"};
B b(a); 						// copy + move
B b(std::move(a));	// move + move
```



可以看到，传 const reference 的时候，无论参数是否是 rvalue，都需要一次 copy；而传值的时候，如果参数是 rvalue，那么一次 copy 都不需要。



> **Tips**: 上述讨论假设 move is cheapper then copy
>



Links：

1. https://releases.llvm.org/8.0.0/tools/clang/tools/extra/docs/clang-tidy/checks/modernize-pass-by-value.html
2. https://en.cppreference.com/w/cpp/language/copy_elision