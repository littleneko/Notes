当你第一次了解到**移动语义**（_move semantics_）和**完美转发**（_perfect forwarding_）的时候，它们看起来非常直观：

- ==**移动语义**==使编译器有可能用廉价的移动操作来代替昂贵的拷贝操作。正如拷贝构造函数和拷贝赋值操作符给了你控制拷贝语义的权力，移动构造函数和移动赋值操作符也给了你控制移动语义的权力。移动语义也允许创建只可移动（move-only）的类型，例如 `std::unique_ptr`，`std::future` 和 `std::thread`。
- ==**完美转发**==使接收任意数量实参的函数模板成为可能，它可以将实参转发到其他的函数，使目标函数接收到的实参与被传递给转发函数的实参保持一致。

==**右值引用**==是连接这两个截然不同的概念的胶合剂，它是使移动语义和完美转发变得可能的基础语言机制。


实际上，`std::move` 并不移动任何东西，完美转发也并不完美。==移动操作并不永远比复制操作更廉价==；即使如此，它也并不总是像你期望的那么廉价；并且当移动操作可用的时候它也并不总是被调用。而且 `type&&` 也并非总是代表一个右值引用。


非常重要的一点是要牢记==形参永远是左值，即使它的类型是一个右值引用==。比如
```cpp
void f(Widget&& w);
```
形参 w 是一个左值，即使它的类型是一个 Widget 的 rvalue-reference。


# 区分通用引用与右值引用
```cpp
void f(Widget&& param);             // 右值引用
Widget&& var1 = Widget();           // 右值引用
auto&& var2 = var1;                 // 不是右值引用

template<typename T>
void f(std::vector<T>&& param);     // 右值引用

template<typename T>
void f(T&& param);                  // 不是右值引用
```
"T&&" 既可以是右值引用，也可以是左值引用。这种引用在源码里看起来像右值引用（即 "T&&"），但是它们可以表现得像是左值引用（即 "T&"）。它们的二重性使它们==既可以绑定到右值上（就像右值引用），也可以绑定到左值上（就像左值引用）==。 此外，它们还可以绑定到 const 或者 non-const 的对象上，也可以绑定到 volatile 或者 non-volatile 的对象上，甚至可以绑定到既 const 又 volatile 的对象上，它们可以绑定到几乎任何东西。这种空前灵活的引用值得拥有自己的名字，我把它叫做==**通用引用（universal references）**==。


在两种情况下会出现通用引用，最常见的一种是==函数模板形参（T&&）==，正如在之前的示例代码中所出现的例子：
```cpp
template<typename T>
void f(T&& param);                  // param 是一个通用引用
```
第二种情况是 ==auto 声明符（auto&&）==，它是从以上示例中拿出的：
```cpp
auto&& var2 = var1;                 // var2 是一个通用引用
```
这两种情况的共同之处就是都==**存在类型推导（type deduction）**==。在模板 f 的内部，param 的类型需要被推导，而在变量 var2 的声明中，var2 的类型也需要被推导。同以下的例子相比较（同样来自于上面的示例代码），下面的例子不带有类型推导。如果你看见 "T&&" 不带有类型推导，那么你看到的就是一个右值引用： 
```cpp
void f(Widget&& param);         // 没有类型推导，
                                // param 是一个右值引用
Widget&& var1 = Widget();       // 没有类型推导，
                                // var1 是一个右值引用
```
因为通用引用是引用，所以它们必须被初始化。一个通用引用的初始值决定了它是代表了右值引用还是左值引用。如果初始值是一个右值，那么通用引用就会是对应的右值引用，如果初始值是一个左值，那么通用引用就会是一个左值引用。对那些是函数形参的通用引用来说，初始值在调用函数的时候被提供：
```cpp
template<typename T>
void f(T&& param);              // param 是一个通用引用

Widget w;
f(w);                           // 传递给函数 f 一个左值；param 的类型
                                // 将会是 Widget&，也即左值引用

f(std::move(w));                // 传递给 f 一个右值；param 的类型会是
                                // Widget&&，即右值引用
```
对一个通用引用而言，类型推导是必要的，但是它还不够。==引用声明的形式必须正确，并且该形式是被限制的，它必须恰好为 ”T&&"==，因此 "std::vector\<T\>&&" 的声明并不是通用引用。

==即使一个简单的 const 修饰符的出现，也足以使一个引用失去成为通用引用的资格==:

```cpp
template <typename T>
void f(const T&& param);        // param 是一个右值引用
```


如果你在一个模板里面看见了一个函数形参类型为 "T&&"，你也许觉得你可以假定它是一个通用引用。错！这是由于在模板内部并不保证一定会发生类型推导。考虑如下 `push_back` 成员函数，来自 `std::vector`：
```cpp
template<class T, class Allocator = allocator<T>>   // 来自 C++ 标准
class vector
{
public:
    void push_back(T&& x);
    …
}
```
`push_back` 函数的形参当然有一个通用引用的正确形式，然而，==在这里并没有发生类型推导，因为 `push_back`在有一个特定的 `vector` 实例之前不可能存在，而实例化 `vector` 时的类型已经决定了 `push_back` 的声明==。也就是说，

```cpp
std::vector<Widget> v;
```
将会导致 `std::vector` 模板被实例化为以下代码：
```cpp
class vector<Widget, allocator<Widget>> {
public:
    void push_back(Widget&& x);             // 右值引用
    …
};
```

==作为对比，`std::vector` 内的概念上相似的成员函数 `emplace_back`，却确实包含类型推导==:

```cpp
template<class T, class Allocator = allocator<T>>   // 依旧来自 C++ 标准
class vector {
public:
    template <class... Args>
    void emplace_back(Args&&... args);
    …
};
```
这儿，类型参数（type parameter）Args 是独立于 vector 的类型参数 T 的，所以 Args 会在每次 `emplace_back` 被调用的时候被推导（Args 实际上是一个 _parameter pack_，而不是一个类型参数）。

---

类型为 `auto` 的变量可以是通用引用，更准确地说，类型声明为 `auto&&` 的变量是通用引用，因为会发生类型推导，并且它们具有正确形式（`T&&`）。`auto` 类型的通用引用不如函数模板形参中的通用引用常见，但是它们在 C++11 中常常出现，而它们在 C++14 中出现得更多，因为 C++14 的 lambda 表达式可以声明 `auto&&` 类型的形参。举个例子，如果你想写一个 C++14 标准的 lambda 表达式，来记录任意函数调用的时间开销，你可以这样写：
```cpp
auto timeFuncInvocation =
    [](auto&& func, auto&&... params)           // C++14
    {
        start timer;
        std::forward<decltype(func)>(func)(     // 对params调用func
            std::forward<delctype(params)>(params)...
        );
        stop timer and record elapsed time;
    };
```
func 是一个通用引用，可以被绑定到任何可调用对象，无论左值还是右值。args 是 0 个或者多个通用引用（即它是个通用引用 parameter pack），它可以绑定到任意数目、任意类型的对象上。多亏了 auto 类型的通用引用，函数 timeFuncInvocation 可以对近乎任意（pretty much any）函数进行计时（之所以不是全部是因为完美转发有时候并不会成功）。

---

**Summary**：

1. 如果一个函数模板形参的类型为 `T&&`，并且 ==`T` 需要被推导得知==，或者如果一个对象被声明为 `auto&&`，这个形参或者对象就是一个==通用引用==。
1. 如果类型声明的形式不是标准的 `type&&`，或者如果==类型推导没有发生==，那么 `type&&` 代表一个==右值引用==。
1. 通用引用，如果它被右值初始化，就会对应地成为右值引用；如果它被左值初始化，就会成为左值引用。

# std::move
首先需要理解的是：`std::move` 不移动（move）任何东西，`std::forward` 也不转发（forward）任何东西。`std::move` 和 `std::forward` 仅仅是执行转换（cast）的函数（事实上是函数模板），==`std::move` 无条件的将它的实参转换为右值==，而 ==`std::forward` 只在特定情况满足时下进行转换==。


这里是一个 C++11 的 `std::move` 的示例实现（它并不完全满足标准细则，但是它已经非常接近了）
```cpp
template<typename T>                            // 在 std 命名空间
typename remove_reference<T>::type&&
move(T&& param)
{
    using ReturnType =                          // 别名声明
        typename remove_reference<T>::type&&;

    return static_cast<ReturnType>(param);
}
```
`std::move` 接受一个对象的引用（准确的说，一个通用引用 (_universal reference_))，返回一个指向同对象的引用。


该函数返回类型的 `&&` 部分表明 `std::move` 函数返回的是一个右值引用，但是，==如果类型 `T` 恰好是一个左值引用，那么 `T&&` 将会成为一个左值引用。为了避免如此，type trait `std::remove_reference` 应用到了类型 `T`上，因此确保了 `&&` 被正确的应用到了一个不是引用的类型上，这保证了 `std::move` 返回的真的是右值引用==。因此，`std::move` 将它的实参转换为一个右值，这就是它的全部作用。


另外，`std::move` 在 C++14 中可以被更简单地实现。多亏了函数返回值类型推导和标准库的模板别名 `std::remove_reference_t`，`std::move` 可以这样写：
```cpp
template<typename T>
decltype(auto) move(T&& param)          // C++14，仍然在 std 命名空间
{
    using ReturnType = remove_referece_t<T>&&;
    return static_cast<ReturnType>(param);
}
```

---

当然，右值是移动操作的候选者，把 `std::move` 应用到一个对象上就是告诉编译器这个对象可以被移动，所以这就是为什么 `std::move` 叫现在的名字：更容易指定可以被移动的对象。


事实上，右值只不过 _通常_ 是移动操作的候选者。假设你有一个类，它用来表示一段注解，这个类的构造函数接受一个包含有注解的 `std::string` 作为形参，然后它复制该形参到数据成员，你声明一个值传递的形参：
```cpp
class Annotation {
public:
    explicit Annotation(const std::string text)
    ：value(std::move(text))    // “移动” text 到 value 里；这段代码执行起来
    { … }                       // 并不是看起来那样
    
    …

private:
    std::string value;
};
```
这段代码可以编译，可以链接，可以运行。这段代码将数据成员 value 设置为 text 的值。这段代码与你期望中的完美实现的唯一区别是 text 并不是被移动到 value，而是被拷贝。诚然，text 通过 `std::move` 被转换到右值，但是 text 被声明为 `const std::string`，所以在转换之前，text 是一个==左值的 `const std::string`==，而转换的结果是一个==右值的 `const std::string`== ，但是纵观全程，==const 属性一直保留==。


当编译器决定哪一个 `std::string` 的构造函数被调用时，考虑它的作用，将会有两种可能性：
```cpp
class string {                  // std::string 事实上是
public:                         // std::basic_string<char> 的类型别名
    …
    string(const string& rhs);  // 拷贝构造函数
    string(string&& rhs);       // 移动构造函数
    …
};
```
在类 Annotation 的构造函数的成员初始化列表中，`std::move(text)` 的结果是一个 `const std::string` 的右值。这个右值不能被传递给 `std::string` 的移动构造函数，因为==移动构造函数只接受一个指向 non-const 的 `std::string` 的右值引用==。然而，该右值却可以被传递给 `std::string` 的拷贝构造函数，因为 ==**lvalue-reference-to-const 允许被绑定到一个 const 右值上**==。因此，`std::string` 在成员初始化的过程中调用了拷贝构造函数，即使 text 已经被转换成了右值。==这样是为了确保维持 const 属性的正确性，从一个对象中移动出某个值通常代表着修改该对象，所以语言不允许 const 对象被传递给可以修改他们的函数（例如移动构造函数）==。


从这个例子中，可以总结出两点。

1. 第一点，==不要在你希望能移动对象的时候，声明他们为 const==。对 const 对象的移动请求会悄无声息的被转化为拷贝操作。
1. 第二点，==`std::move` 不仅不移动任何东西，而且它也不保证它执行转换的对象可以被移动==。关于 `std::move`，你能确保的唯一一件事就是将它应用到一个对象上，你能够==得到一个右值==。

# std::forward
`std::forward` 与 `std::move` 是相似的，但是与 `std::move` 总是无条件的将它的实参转为右值不同，`std::forward` 只有在满足一定条件的情况下才执行转换。`std::forward` 是有条件的转换，要明白什么时候它执行转换，什么时候不，想想 `std::forward` 的典型用法，最常见的情景是一个模板函数，接收一个通用引用形参，并将它传递给另外的函数：

```cpp
void process(const Widget& lvalArg);        // 处理左值
void process(Widget&& rvalArg);             // 处理右值

template<typename T>                        // 用以转发param到process的模板
void logAndProcess(T&& param)
{
    auto now =                              // 获取现在时间
        std::chrono::system_clock::now();
    
    makeLogEntry("Calling 'process'", now);
    process(std::forward<T>(param));
}
```
考虑两次对 `logAndProcess` 的调用，一次左值为实参，一次右值为实参：
```cpp
Widget w;

logAndProcess(w);               // 用左值调用
logAndProcess(std::move(w));    // 用右值调用
```
在 `logAndProcess` 函数的内部，形参 `param` 被传递给函数 `process` 。函数 `process` 分别对左值和右值做了重载。当我们使用左值来调用 `logAndProcess` 时，自然我们期望该左值被当作左值转发给 `process` 函数，而当我们使用右值来调用 `logAndProcess` 函数时，我们期望 `process` 函数的右值重载版本被调用。


但是 `param` ，正如所有的其他函数形参一样，是一个左值。每次在函数 `logAndProcess` 内部对函数 `process` 的调用，都会因此调用函数 `process` 的左值重载版本。为防如此，我们需要一种机制：当且仅当传递给函数 `logAndProcess` 的用以初始化 `param` 的实参是一个右值时，`param` 会被转换为一个右值。这就是 `std::forward` 做的事情。这就是为什么 `std::forward` 是一个有条件的转换：它的实参用右值初始化时，转换为一个右值。


最后，==`std::forward` 只有当它的参数被绑定到一个右值时，才将参数转换为右值==。


# std::move 和 std::forward 的使用
**规则1**：**==对右值引用使用 `std::move`，对通用引用使用 `std::forward`==**。

```cpp
class Widget {
public:
    Widget(Widget&& rhs)        // rhs 是右值引用
    : name(std::move(rhs.name)),
      p(std::move(rhs.p))
      { … }
    …
private:
    std::string name;
    std::shared_ptr<SomeDataStructure> p;
};
```
```cpp
class Widget {
public:
    template<typename T>
    void setName(T&& newName)           // newName 是通用引用
    { name = std::forward<T>(newName); }

    …
};
```
总而言之，当把右值引用转发给其他函数时，右值引用应该被**无条件**转换为右值（通过 `std::move`），因为它们**总是**绑定到右值；当转发通用引用时，通用引用应该**有条件**地转换为右值（通过 `std::forward`），因为它们只是**有时**绑定到右值。

---

**规则2**：==**不要在通用引用上使用 `std::move`，这可能会意外改变左值（比如局部变量）**==

```cpp
class Widget {
public:
    template<typename T>
    void setName(T&& newName)       // 通用引用可以编译，
    { name = std::move(newName); }  // 但是代码太太太差了！
    …

private:
    std::string name;
    std::shared_ptr<SomeDataStructure> p;
};

std::string getWidgetName();        // 工厂函数

Widget w;

auto n = getWidgetName();           // n 是局部变量

w.setName(n);                       // 把 n 移动进 w！

…                                   // 现在 n 的值未知
```
你可能会指出，如果为 const 左值和为右值分别重载 setName 可以避免整个问题，比如这样：
```cpp
class Widget {
public:
    void setName(const std::string& newName)    // 用 const 左值设置
    { name = newName; }
    
    void setName(std::string&& newName)         // 用右值设置
    { name = std::move(newName); }
    
    …
};
```
这样的话，当然可以工作，但是有缺点，首先编写和维护的代码更多（两个函数而不是单个模板）；其次，==效率下降==。比如，考虑如下场景：
```cpp
w.setName("Adela Novak");
```
使用通用引用的版本的 setName，字面字符串 “Adela Novak” 可以被传递给 setName，再传给 w 内部 `std::string` 的赋值运算符，==w 的 name 的数据成员通过字面字符串直接赋值，没有临时 `std::string` 对象被创建==。但是，==setName 重载版本，会有一个临时 `std::string` 对象被创建，setName 形参绑定到这个对象，然后这个临时 `std::string` 移动到 w 的数据成员中==。一次 setName 的调用会包括 `std::string` 构造函数调用（创建中间对象），`std::string` 赋值运算符调用（移动 newName 到 w.name），`std::string` 析构函数调用（析构中间对象）。这比调用接受 `const char*` 指针的 `std::string` 赋值运算符开销昂贵许多。增加的开销根据实现不同而不同，这些开销是否值得担心也跟应用和库的不同而有所不同，但是事实上，将通用引用模板替换成对左值引用和右值引用的一对函数重载在某些情况下会导致运行时的开销。如果把例子泛化，Widget 数据成员是任意类型（而不止是个 `std::string`），性能差距可能会变得更大，因为不是所有类型的移动操作都像 `std::string` 开销较小。
> **Tips**:
> 同 `std::vector::push_back()` 和 `std::vactor::emplace_back()` 的区别：
>
> * 如果使用 push_back(std::move(x))，需要先构造一个临时对象 x，然后把 x move 到 vector 中，最后析构 x 对象；
> * 如果使用 emplace_back(a, b, c)，会直接用 (a, b, c) 三个参数在 vector 里构造 X 对象。


---

但是，关于对左值和右值的重载函数最重要的问题不是源代码的数量，也不是代码的运行时性能。而是设计的可扩展性差。`Widget::setName` 有一个形参，因此需要两种重载实现，但是对于有更多形参的函数，每个都可能是左值或右值，重载函数的数量几何式增长：n 个参数的话，就要实现 2n 种重载。这还不是最坏的。有的函数——实际上是函数模板——接受无限制个数的参数，每个参数都可以是左值或者右值。此类函数的典型代表是 `std::make_shared`，还有对于 C++14 的 `std::make_unique`。查看他们的的重载声明：
```cpp
template<class T, class... Args>                //来自C++11标准
shared_ptr<T> make_shared(Args&&... args);

template<class T, class... Args>                //来自C++14标准
unique_ptr<T> make_unique(Args&&... args);
```
对于这种函数，对于左值和右值分别重载就不能考虑了：通用引用是仅有的实现方案

---

**规则3**：==**在按值返回的函数中，返回值绑定到右值引用或者通用引用上，需要对返回的引用使用 `std::move` 或者 `std::forward`**==。


考虑两个矩阵相加的 `operator+` 函数，左侧的矩阵为右值（可以被用来保存求值之后的和）：
```cpp
Matrix                              // 按值返回
operator+(Matrix&& lhs, const Matrix& rhs)
{
    lhs += rhs;
    return std::move(lhs);	        // 移动 lhs 到返回值中
}
```
通过在 return 语句中将 lhs 转换为右值（通过 `std::move`），lhs 可以移动到返回值的内存位置。如果省略了`std::move` 调用，
```cpp
Matrix                              // 同之前一样
operator+(Matrix&& lhs, const Matrix& rhs)
{
    lhs += rhs;
    return lhs;                     // 拷贝 lhs 到返回值中
}
```
lhs 是个左值的事实，会强制编译器拷贝它到返回值的内存空间。假定 Matrix 支持移动操作，并且比拷贝操作效率更高，在 return 语句中使用 `std::move` 的代码效率更高。


使用通用引用和 `std::forward` 的情况类似。考虑函数模板 reduceAndCopy 收到一个未规约（unreduced）对象 Fraction，将其规约，并返回一个规约后的副本。如果原始对象是右值，可以将其移动到返回值中（避免拷贝开销），但是如果原始对象是左值，必须创建副本，因此如下代码：
```cpp
template<typename T>
Fraction                            // 按值返回
reduceAndCopy(T&& frac)             // 通用引用的形参
{
    frac.reduce();
    return std::forward<T>(frac);		// 移动右值，或拷贝左值到返回值中
}
```

---

**规则4**：==**对于存在 RVO/NRVO 的场景，不要使用 `std::move` 或 `std::forward` 返回值。**==

```cpp
Widget makeWidget()                 // makeWidget 的移动版本
{
    Widget w;
    …
    return std::move(w);            // 移动 w 到返回值中（不要这样做！）
}
```
实际上，如果正常返回 w，因为有 RVO/NRVO 的存在，只会有一次构造。但是返回值变成右值引用后， RVO/NRVO 失效，需要一次构造（makeWidget 内的 w 对象）和一次移动（移动到返回值上）。


# Links

1. Meyers S. Effective modern C++: 42 specific ways to improve your use of C++ 11 and C++ 14[M]. " O'Reilly Media, Inc.", 2014.
