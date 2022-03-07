结论：==**优先考虑使用 `std::make_unique` 和 `std::make_shared` 而非 `new`**==。


# make 函数的优势
## 异常安全
使用 `make` 函数的原因和==异常安全==有关，假设我们有个函数按照某种优先级处理 Widget：
```cpp
void processWidget(std::shared_ptr<Widget> spw, int priority);
```
现在假设我们有一个函数来计算相关的优先级，
```cpp
int computePriority();
```
并且我们在调用 processWidget 时使用了 `new` 而不是 `std::make_shared`：
```cpp
processWidget(std::shared_ptr<Widget>(new Widget),  // 潜在的资源泄漏！
              computePriority());
```
在运行时，一个函数的实参必须先被计算，这个函数再被调用，所以在调用 `processWidget` 之前，必须执行以下操作，`processWidget` 才开始执行：

- 表达式 `new Widget` 必须计算，例如，一个 Widget 对象必须在堆上被创建
- 负责管理 new 出来指针的 `std::shared_ptr<Widget>` 构造函数必须被执行
- `computePriority` 必须运行

编译器不需要按照执行顺序生成代码，new Widget 必须在 `std::shared_ptr` 的构造函数被调用前执行，因为new 出来的结果作为构造函数的实参，但 `computePriority` 可能在这之前、之后、或者之间执行。也就是说，编译器可能按照这个执行顺序生成代码：

1. 执行 `new Widget`
1. 执行 `computePriority`
1. 运行 `std::shared_ptr` 构造函数

如果按照这样生成代码，并且在运行时 `computePriority` 产生了异常，那么第一步动态分配的 Widget 就会泄漏，因为它永远都不会被第三步的 `std::shared_ptr` 所管理了。


使用 `std::make_shared` 可以防止这种问题，调用代码看起来像是这样：
```cpp
processWidget(std::make_shared<Widget>(),   // 没有潜在的资源泄漏
              computePriority());
```
如果我们将 `std::shared_ptr`，`std::make_shared` 替换成 `std::unique_ptr`，`std::make_unique` ，同样的道理也适用。因此，在编写异常安全代码时，使用`std::make_unique` 而不是`new` 与使用 `std::make_shared` （而不是 `new`）同样重要。


## 效率提升
`std::make_shared` 的一个特性（与直接使用 `new` 相比）是==效率提升==，使用 `std::make_shared` 允许编译器生成更小，更快的代码，并使用更简洁的数据结构。考虑以下对 `new` 的直接使用：

```cpp
std::shared_ptr<Widget> spw(new Widget);
```
显然，这段代码需要进行内存分配，但它实际上执行了两次。每个 `std::shared_ptr` 指向一个控制块，其中包含被指向对象的引用计数，还有其他东西。这个控制块的内存在 `std::shared_ptr` 构造函数中分配。因此，直接使用 `new` 需要为 `Widget` 进行一次内存分配，为控制块再进行一次内存分配。


如果使用 `std::make_shared` 代替：
```cpp
auto spw = std::make_shared<Widget>();
```
一次分配足矣，==原因是 `std::make_shared` 分配一块内存，同时容纳了 Widget 对象和控制块==，这种优化减少了程序的静态大小，代码只包含一个内存分配调用；并且它提高了可执行代码的速度，原因是内存只分配一次。此外，使用 `std::make_shared` 避免了对控制块中的某些簿记信息的需要，潜在地减少了程序的总内存占用。

---

# make 函数的限制
当然，我们的建议是更倾向于（_prefer_）使用 make 函数，而不是完全依赖于它们，这是因为有些情况下它们不能或不应该被使用。


## 不能自定义删除器
==make 函数不允许指定自定义删除器==，但是 `std::unique_ptr` 和 `std::shared_ptr` 有构造函数这么做。

```cpp
auto widgetDeleter = [](Widget* pw) { … };

std::unique_ptr<Widget, decltype(widgetDeleter)> upw(new Widget, widgetDeleter);

std::shared_ptr<Widget> spw(new Widget, widgetDeleter);
```


## 完美转发使用小括号，而不是花括号
make 函数第二个限制来自于其实现中的语法细节，当构造函数重载，有使用 `std::initializer_list` 作为参数的重载形式和不用其作为参数的的重载形式，用花括号创建的对象更倾向于使用 `std::initializer_list` 作为形参的重载形式，而用小括号创建对象将调用不用 `std::initializer_list` 作为参数的的重载形式。make 函数会将它们的参数完美转发给对象构造函数，但是它们是使用小括号还是花括号？对某些类型，问题的答案会很不相同。例如，在这些调用中，
```cpp
auto upv = std::make_unique<std::vector<int>>(10, 20);
auto spv = std::make_shared<std::vector<int>>(10, 20);
```
生成的智能指针指向带有 10 个元素的 `std::vector` ，每个元素值为 20；还是指向带有两个元素的 `std::vector` ，其中一个元素值 10，另一个为 20？或者结果是不确定的？

实际上结果是两种调用都创建了 10 个元素，每个值为 20 的 `std::vector`。这意味着在 make 函数中，完美转发使用小括号，而不是花括号；坏消息是如果你想用花括号初始化指向的对象，你必须直接使用 new。


使用 make 函数会需要能够完美转发花括号初始化的能力，但是花括号初始化无法完美转发。但是有一种变通的方法：使用 auto 类型推导从花括号初始化创建 `std::initializer_list` 对象，然后将 auto 创建的对象传递给 make 函数。
```cpp
// 创建std::initializer_list
auto initList = { 10, 20 };
// 使用std::initializer_list为形参的构造函数创建std::vector
auto spv = std::make_shared<std::vector<int>>(initList);
```
## 对于重载 new 和 delete 的类的支持（对 std::shared_ptr）
一些类重载了 operator new 和 operator delete，这些函数的存在意味着对这些类型的对象的全局内存分配和释放是不合常规的。通常，这种定制操作往往只用于精确的分配、释放对象大小的内存。例如，Widget 类的 operator new 和 operator delete 只会处理 sizeof(Widget) 大小的内存块的分配和释放。这种系列行为不太适用于 `std::shared_ptr` 对自定义分配（通过 `std::allocate_shared` ）和释放（通过自定义删除器）的支持。由于 `std::allocate_shared` 需要的内存总大小不等于动态分配的对象大小，还需要再加上控制块大小。因此，使用 make 函数去创建重载了 operator new 和 operator delete 类的对象是个典型的糟糕想法。


## 延迟销毁（对 std::shared_ptr)
与直接使用 new 相比，`std::make_shared` 在大小和速度上的优势源于 `std::shared_ptr` 的控制块与指向的对象放在同一块内存中。当对象的引用计数降为 0，对象被销毁（即析构函数被调用）。但是，==因为控制块和对象被放在同一块分配的内存块中，直到控制块的内存也被销毁，对象占用的内存才被释放==。


正如我说，控制块除了引用计数，还包含 bookkeeping information。引用计数追踪有多少 `std::shared_ptr` 指向控制块，但控制块还有第 2 个计数，记录多少个 `std::weak_ptrs` 指向控制块。第 2 个引用计数就是weak count（实际上，weak count 的值不总是等于指向控制块的 `std::weak_ptr` 的数目，因为库的实现者找到一些方法在 weak count 中添加附加信息，促进更好的代码产生。为了本条款的目的，我们会忽略这一点，假定weak count 的值等于指向控制块的 `std::weak_ptr` 的数目）。当一个 `std::weak_ptr` 检测它是否过期时，它会检测指向的控制块中的引用计数（而不是 weak count），如果引用计数是 0（即对象没有`std::shared_ptr` 再指向它，已经被销毁了），`std::weak_ptr` 就已经过期，否则就没过期。

==只要 `std::weak_ptr` 引用一个控制块（即 weak count 大于零），该控制块必须继续存在。只要控制块存在，包含它的内存就必须保持分配。通过 `std::shared_ptr` 的 make 函数分配的内存，直到最后一个 `std::shared_ptr` 和最后一个指向它的 `std::weak_ptr` 已被销毁，才会释放==。


如果对象类型非常大，而且销毁最后一个 `std::shared_ptr` 和销毁最后一个 `std::weak_ptr` 之间的时间很长，那么在销毁对象和释放它所占用的内存之间可能会出现延迟。
```cpp
class ReallyBigType { … };

auto pBigObj =                          // 通过std::make_shared
    std::make_shared<ReallyBigType>();  // 创建一个大对象
                    
…           // 创建 std::shared_ptrs 和 std::weak_ptrs
            // 指向这个对象，使用它们

…           // 最后一个 std::shared_ptr 在这销毁，
            // 但 std::weak_ptrs 还在

…           // 在这个阶段，原来分配给大对象的内存还分配着

…           // 最后一个 std::weak_ptr 在这里销毁；
            // 控制块和对象的内存被释放
```
直接只用 new，一旦最后一个 `std::shared_ptr` 被销毁，ReallyBigType 对象的内存就会被释放：
```cpp
class ReallyBigType { … };              // 和之前一样

std::shared_ptr<ReallyBigType> pBigObj(new ReallyBigType);
                                        // 通过new创建大对象

…           // 像之前一样，创建 std::shared_ptrs 和 std::weak_ptrs
            // 指向这个对象，使用它们
            
…           // 最后一个 std::shared_ptr 在这销毁,
            // 但 std::weak_ptrs 还在；
            // 对象的内存被释放

…           // 在这阶段，只有控制块的内存仍然保持分配

…           // 最后一个 std::weak_ptr 在这里销毁；
            // 控制块内存被释放
```

---

# 正确地使用 new
如果你发现自己处于不可能或不合适使用 `std::make_shared` 的情况下，你将想要保证自己不受我们之前看到的异常安全问题的影响。最好的方法是确保在直接使用 new 时，在一个不做其他事情的语句中，立即将结果传递到智能指针构造函数。这可以防止编译器生成的代码在使用 new 和调用管理 new 出来对象的智能指针的构造函数之间发生异常。


例如，考虑我们前面讨论过的 `processWidget` 函数，对其非异常安全调用的一个小修改。这一次，我们将指定一个自定义删除器（目的是为了不能使用 make）:
```cpp
void processWidget(std::shared_ptr<Widget> spw, int priority);  // 和之前一样
void cusDel(Widget *ptr);                           			// 自定义删除器
```
这是非异常安全的调用：
```cpp
processWidget(std::shared_ptr<Widget>(new Widget, cusDel), computePriority());
```
这里使用自定义删除排除了对 `std::make_shared` 的使用，因此避免出现问题的方法是将 Widget 的分配和`std::shared_ptr` 的构造放入它们自己的语句中，然后使用得到的 `std::shared_ptr` 调用`processWidget`。这是该技术的本质，不过，正如我们稍后将看到的，我们可以对其进行调整以提高其性能：
```cpp
std::shared_ptr<Widget> spw(new Widget, cusDel);
processWidget(spw, computePriority());  // 正确，但是没优化，见下
```
这是可行的，因为 `std::shared_ptr` 获取了传递给它的构造函数的原始指针的所有权，即使构造函数产生了一个异常。此例中，如果 spw 的构造函数抛出异常（比如无法为控制块动态分配内存），仍然能够保证 cusDel 会在 "new Widget" 产生的指针上调用。


一个小小的性能问题是，在非异常安全调用中，我们将一个右值传递给 processWidget，但是在异常安全调用中，我们传递了左值。
因为 `processWidget` 的 `std::shared_ptr` 形参是传值，从右值构造只需要移动，而传递左值构造需要拷贝。对 `std::shared_ptr` 而言，这种区别是有意义的，因为拷贝 `std::shared_ptr` 需要对引用计数原子递增，移动则不需要对引用计数有操作。为了使异常安全代码达到非异常安全代码的性能水平，我们需要用`std::move` 将 spw 转换为右值：
```cpp
processWidget(std::move(spw), computePriority());   // 高效且异常安全
```
# Summary

1. 和直接使用 new 相比，make 函数消除了代码重复，提高了异常安全性。对于 `std::make_shared` 和`std::allocate_shared`，生成的代码更小更快。
1. 不适合使用 make 函数的情况包括需要指定自定义删除器和希望用花括号初始化。
1. 对于 `std::shared_ptr`，其他不建议使用 make 函数的情况包括：(1) 有自定义内存管理的类；(2) 特别关注内存的系统，非常大的对象，以及 `std::weak_ptr` 比对应的 `std::shared_ptr` 活得更久。

# Links

1. Meyers S. Effective modern C++: 42 specific ways to improve your use of C++ 11 and C++ 14[M]. " O'Reilly Media, Inc.", 2014.
1. [https://github.com/kelthuzadx/EffectiveModernCppChinese](https://github.com/kelthuzadx/EffectiveModernCppChinese)
