在 C++11 之前，只有**原始指针**（**raw pointer**）可用，虽然原始指针是一个强大的工具，但也有一些问题：

1. 它的声明不能明确指示它是指向==单个对象==还是==数组==。
1. 它的声明没有告诉你当你用完后==是否应该销毁==它所指向的对象，即指针是否拥有（==_**owns**_==）它所指之物。
1. 如果你决定你应该销毁指针所指对象，没人告诉你应该==如何销毁==，是调用 delete 还是其他析构机制（比如把指针传给专门的销毁函数）。
1. 如果你发现该用 delete，原因 1 意味着你不可能知道该用单个对象的形式（"delete"）还是数组形式（"delete[]"），如果用错了将导致未定义的行为。
1. 如果你确定了指针拥有它所指之物，并且知道怎么销毁它，也很难确定你在所有执行路径上都执行了==**_恰好一次_**==（_**exactly once**_）销毁操作（包括异常路径）；少一条路径会导致资源泄漏，销毁多次会导致未定义行为。
1. 一般来说没有办法告诉你指针是否变成了==悬空指针==（dangling pointers），即内存中不再存在指针所指之物，在对象销毁后指针仍然指向它们就会产生悬空指针。

---

原始指针确实是强大的工具，但是另一方面几十年的经验表明，只要注意力和规范稍有疏忽，这个强大的工具就会攻击它的主人。

==**智能指针**==（_smart pointers_）是解决这些问题的一种方法，智能指针是原始指针的包裹（wrappers），它的行为看起来像被包裹的原始指针，但避免了原始指针的很多陷阱。你应该更倾向于智能指针而不是原始指针，智能指针可以做几乎所有原始指针能做的事情，而且出错的机会更少。


在 C++ 11 中有四种智能指针：`std::auto_ptr`、`std::unique_ptr`、`std:shared_ptr`、`std::weak_ptr`，都是被设计用来帮助管理动态对象的生命周期，比如在适当的时间以适当的方式销毁对象，避免资源泄漏（包括出现异常的时候）。


`std::auto_ptr` 是来自 C++98 的已废弃遗留物，它是一次标准化的尝试，后来变成了 C++11 的`std::unique_ptr`。要正确的模拟原生指针需要移动语义，但是 C++98 没有这个东西。作为一种变通的方法，`std::auto_ptr` 使用移动代替了拷贝，这导致了令人奇怪的代码（拷贝一个 `std::auto_ptr` 会将它本身设置为 null！）和令人沮丧的使用限制（比如不能将 `std::auto_ptr` 放入容器）。	


# 对独占资源使用 std:unique_ptr
当你需要一个智能指针时，`std::unique_ptr` 通常是最合适的。可以合理假设，默认情况下，`std::unique_ptr` 大小等同于原始指针，而且对于大多数操作（包括取消引用），他们执行的指令完全相同。这意味着你甚至可以在内存和时间都比较紧张的情况下使用它。如果原始指针够小够快，那么 `std::unique_ptr` 一样可以。

`std::unique_ptr` 体现了专有所有权（==_exclusive ownership_==）语义。一个 non-null `std::unique_ptr` 始终拥有其指向的内容。移动一个 `std::unique_ptr` 将所有权从源指针转移到目的指针（源指针被设为 null。）拷贝一个 `std::unique_ptr` 是不允许的，因为如果你能拷贝一个 `std::unique_ptr`，你会得到指向相同资源的两个 `std::unique_ptr` ，每个都认为自己拥有（并且应当最后销毁）资源。因此 `std::unique_ptr` 是一种==只可移动类型==（move-only type）。当析构时，一个 non-null `std::unique_ptr` 销毁它指向的资源。默认情况下，资源析构通过对 `std::unique_ptr` 里原始指针调用 delete 来实现。


## 使用场景
`std::unique_ptr` 的常见用法是作为继承层次结构中对象的工厂函数返回类型，假设我们有一个投资类型（比如股票、债券、房地产等）的继承结构，使用基类 `Investment`。
```cpp
class Investment { ... };
class Stock: public Investment { ... };
class Bond: public Investment { ... };
class RealEstate: public Investment { ... };
```
<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1631362512887-c3e70f93-46dc-4a6b-b874-a4189f51230b.png" alt="image.png" style="zoom:50%;" />

这种继承关系的工厂函数在堆上分配一个对象然后返回指针，==调用方在不需要的时候有责任销毁对象==。这个使用场景完美匹配 `std::unique_ptr`，==因为调用者对工厂返回的资源负责（即对该资源的专有所有权)==，并且`std::unique_ptr` 在自己被销毁时会自动销毁指向的内容，`Investment` 的工厂函数可以这样声明：

```cpp
// return std::unique_ptr to an object created from the given args
template<typename... Ts>
std::unique_ptr<Investment> makeInvestment(Ts&&... params);
```
调用者应该在单独的作用域中使用返回的 `std::unique_ptr` 智能指针：
```cpp
{
    …
    // pInvestment 是 std::unique_ptr<Investment> 类型
    auto pInvestment = makeInvestment( arguments );
    …
}  // 销毁 *pInvestment
```


## 构造和销毁
默认情况下，销毁将通过 `delete` 进行，但是在构造过程中，`std::unique_ptr` 对象可以被设置为使用（对资源的）自定义删除器：当资源需要销毁时可调用的任意函数（或者函数对象，包括 lambda 表达式）。如果通过`makeInvestment` 创建的对象不应仅仅被 delete，而应该先写一条日志，`makeInvestment` 可以以如下方式实现。
```cpp
// custom deleter(a lambda expression) revised return type
auto delInvmt = [](Investment* pInvestment) {
                  makeLogEntry(pInvestment);
                  delete pInvestment;
                };

template<typename... Ts>
std::unique_ptr<Investment, decltype(delInvmt)> makeInvestment(Ts&&... params) {
    // ptr to be returned
    std::unique_ptr<Investment, decltype(delInvmt)> pInv(nullptr, delInvmt);
	if ( /* a Stock object should be created */ )
    {
      pInv.reset(new Stock(std::forward<Ts>(params)...));
    }
    else if ( /* a Bond object should be created */ )
    {
      pInv.reset(new Bond(std::forward<Ts>(params)...));
    }
    else if ( /* a RealEstate object should be created */ )
    {
      pInv.reset(new RealEstate(std::forward<Ts>(params)...));
    }
    return pInv;
}
```
注意：

1. 尝试将原始指针（比如 new 创建）赋值给 `std::unique_ptr` 不能通过编译，因为是一种从原始指针到智能指针的隐式转换，这种隐式转换会出问题，所以 C++11 的智能指针禁止这个行为，这就是通过 reset 来让 pInv 接管通过 new 创建的对象的所有权的原因。
1. 使用 new 时，我们使用 `std::forward` 把传给 makeInvestment 的实参==完美转发==出去，这使调用者提供的所有信息可用于正在创建的对象的构造函数。
1. 自定义删除器的形参类型是 `Investment*`，不管在 `makeInvestment` 内部创建的对象的真实类型（如Stock，Bond，或 RealEstate）是什么，它最终在 lambda 表达式中，作为 `Investment*` 对象被删除。==这意味着我们通过基类指针删除派生类实例，为此，基类 `Investment` 必须有虚析构函数==。
1. 当使用默认删除器时（如 delete），你可以合理假设 `std::unique_ptr` 对象和原始指针大小相同。当自定义删除器时，情况可能不再如此。==函数指针形式的删除器，通常会使 `std::unique_ptr` 的从一个字（word）大小增加到两个==。对于函数对象形式的删除器来说，变化的大小取决于函数对象中存储的状态多少，无状态函数（stateless function）对象（比如不捕获变量的 lambda 表达式）对大小没有影响，这意味==当自定义删除器可以实现为函数或者 lambda 时，尽量使用 lambda==。

## 对数组和单个对象的支持
`std::unique_ptr` 有两种形式，一种用于单个对象（`std::unique_ptr<T>`），一种用于数组（`std::unique_ptr<T[]>`），结果就是，指向哪种形式没有歧义。`std::unique_ptr` 的 API 设计会自动匹配你的用法，比如 `operator[]` 就是数组对象，解引用操作符（`operator*` 和 `operator->`）就是单个对象专有。


你应该对数组 `std::unique_ptr` 的存在兴趣泛泛，因为 `std::array`，`std::vector`，`std::string` 这些更好用的数据容器应该取代原始数组。`std::unique_ptr<T[]>` 有用的唯一情况是你使用类似 C 的 API 返回一个指向堆数组的原始指针，而你想接管这个数组的所有权。


## 转换为 std::shared_ptr
`std::unique_ptr` 是 C++11 中表示专有所有权的方法，但是其最吸引人的功能之一是它==可以轻松高效的转换为`std::shared_ptr==：

```cpp
// converts std::unique_ptr to std::shared_ptr
std::shared_ptr<Investment> sp = makeInvestment( arguments );
```
## Summary

1. `std::unique_ptr` 是轻量级、快速的、只可移动（move-only）的管理专有所有权语义资源的智能指针
1. 默认情况，资源销毁通过 `delete` 实现，但是支持自定义删除器，有状态的删除器和函数指针会增加`std::unique_ptr` 对象的大小
1. 将 `std::unique_ptr` 转化为 `std::shared_ptr` 非常简单

# 对共享资源使用 std::shared_ptr
`std::shared_ptr` 将“一个自动工作的世界（像是垃圾回收），一个销毁可预测的世界（像是析构）”两者结合起来。一个通过 `std::shared_ptr` 访问的对象其生命周期由指向它的有共享所有权（==_shared ownership_==）的指针来管理。没有特定的 `std::shared_ptr` 拥有该对象，相反，所有指向它的 `std::shared_ptr` 都能相互合作确保在它不再使用的那个点进行析构。当最后一个指向某对象的 `std::shared_ptr` 不再指向它（比如因为 `std::shared_ptr` 被销毁或者指向另一个不同的对象），`std::shared_ptr` 会销毁它所指向的对象。就垃圾回收来说，客户端不需要关心指向对象的生命周期，而对象的析构是确定性的。


## std::shared_ptr 的使用
`std::shared_ptr` 通过引用计数（==_reference count_==）来确保它是否是最后一个指向某种资源的指针，引用计数关联资源并跟踪有多少 `std::shared_ptr` 指向该资源。`std::shared_ptr` 构造函数（constructors）递增引用计数值（注意是通常，原因参见下面），==析构函数（destructors）递减值，拷贝赋值运算符（copy assignment operators）做前面这两个工作==（如果 sp1 和 sp2 是 `std::shared_ptr` 并且指向不同对象，赋值 "sp1 = sp2;" 会使 sp1 指向 sp2 指向的对象。直接效果就是 sp1 原来所指向的对象的引用计数减一，sp2 所指向的对象的引用计数加一）。如果 `std::shared_ptr` 在计数值递减后发现引用计数值为零，没有其他 `std::shared_ptr` 指向该资源，它就会销毁资源。


引用计数暗示着性能问题：

1. ==**`std::shared_ptr ` 大小是原始指针的两倍**==，原因是它内部包含一个指向资源的原始指针，还包含一个指向资源的引用计数值的原始指针。（这种实现法并不是标准要求的，但是我熟悉的所有标准库都这样实现）
1. ==**引用计数的内存必须动态分配**==。 概念上，引用计数与所指对象关联，==但是实际上被指向的对象不知道这件事情，因此它们没有办法存放一个引用计数值==（一个好消息是任何对象（甚至是内置类型的）都可以由`std::shared_ptr` 管理）。使用 `std::make_shared` 创建 `std::shared_ptr` 可以避免引用计数的动态分配，但是还存在一些 `std::make_shared` 不能使用的场景，这时候引用计数就会动态分配。
1. ==**递增递减引用计数必须是原子性的**==，原因是多个 reader、writer 可能在不同的线程。比如，指向某种资源的`std::shared_ptr` 可能在一个线程执行析构（因此递减指向的对象的引用计数），在另一个不同的线程，一个指向相同对象的 `std::shared_ptr` 可能在执行拷贝操作（因此递增了同一个引用计数）。原子操作通常比非原子操作要慢，所以即使引用计数通常只有一个 word 大小，你也应该假定读写它们是存在开销的。

---

上面说到 `std::shared_ptr` 构造函数只是“通常”递增指向对象的引用计数会不会让你有点好奇？创建一个指向对象的 `std::shared_ptr` 就产生了又一个指向那个对象的 `std::shared_ptr`，为什么不是“总是”增加引用计数值？原因是==移动构造函数==（move construction）的存在。从另一个 `std::shared_ptr` 移动构造新 `std::shared_ptr` 会将原来的 `std::shared_ptr` 设置为 null，那意味着老的 `std::shared_ptr` 不再指向资源，同时新的 `std::shared_ptr` 指向资源，这样的结果就是不需要修改引用计数值。因此==移动 `std::shared_ptr` 会比拷贝它要快：拷贝要求递增引用计数值，移动不需要==。移动赋值运算符同理，所以移动构造比拷贝构造快，移动赋值运算符也比拷贝赋值运算符快。


类似 `std::unique_ptr`，`std::shared_ptr` 使用 delete 作为资源的默认销毁机制，但是它也支持自定义的删除器。这种支持有别于 `std::unique_ptr`，==对于 `std::unique_ptr` 来说，删除器类型是智能指针类型的一部分，对于 `std::shared_ptr` 则不是==。
```cpp
// 删除器类型是指针类型的一部分
std::unique_ptr<Widget, decltype(loggingDel)> upw(new Widget, loggingDel);
// 删除器类型不是指针类型的一部分
std::shared_ptr<Widget> spw(new Widget, loggingDel);
```


`std::shared_ptr` 的设计更为灵活。考虑有两个 `std::shared_ptr<Widget>`，每个自带不同的删除器（比如通过 lambda 表达式自定义删除器）：
```cpp
auto customDeleter1 = [](Widget *pw) { … };     //自定义删除器，
auto customDeleter2 = [](Widget *pw) { … };     //每种类型不同
std::shared_ptr<Widget> pw1(new Widget, customDeleter1);
std::shared_ptr<Widget> pw2(new Widget, customDeleter2);
```
因为 pw1 和 pw2 有相同的类型，所以它们都可以放到存放那个类型的对象的容器中：
```cpp
std::vector<std::shared_ptr<Widget>> vpw{ pw1, pw2 };
```
它们也能相互赋值，也可以传入一个形参为 `std::shared_ptr<Widget>` 的函数。但是自定义删除器类型不同的 `std::unique_ptr` 就不行，因为 `std::unique_ptr` 把删除器视作类型的一部分。


## Control Block
另一个不同于 `std::unique_ptr` 的地方是，指定自定义删除器不会改变 `std::shared_ptr` 对象的大小。不管删除器是什么，一个 `std::shared_ptr` 对象都是两个指针大小。我前面提到了 `std::shared_ptr` 对象包含了所指对象的引用计数的指针，没错，但是有点误导人。因为引用计数是另一个更大的数据结构的一部分，那个数据结构通常叫做控制块（control block），每个 `std::shared_ptr` 管理的对象都有个相应的控制块。控制块除了包含引用计数值外还有一个自定义删除器的拷贝，当然前提是存在自定义删除器。如果用户还指定了自定义分配器，控制块也会包含一个分配器的拷贝。控制块可能还包含一些额外的数据，比如一个次级引用计数 weak count。我们可以想象 `std::shared_ptr` 对象在内存中是这样：

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1631365981001-44cc34de-0d07-40de-8e56-8ac9b68aa2fb.png" alt="image.png" style="zoom:50%;" />

当指向对象的 `std::shared_ptr` 一创建，对象的控制块就建立了，至少我们期望是如此。通常，对于一个创建指向对象的 `std::shared_ptr` 的函数来说不可能知道是否有其他 `std::shared_ptr` 早已指向那个对象，所以控制块的创建会遵循下面几条规则：

1. ==**`std::make_shared` 总是创建一个控制块**==。它创建一个要指向的新对象，所以可以肯定 `std::make_shared` 调用时对象不存在其他控制块。
1. ==**当从独占指针（即 `std::unique_ptr` 或者 `std::auto_ptr`）上构造出 `std::shared_ptr` 时会创建控制块**==。独占指针没有使用控制块，所以指针指向的对象没有关联控制块。（作为构造的一部分，`std::shared_ptr` 侵占独占指针所指向的对象的独占权，所以独占指针被设置为 null）。
1. ==**当从原始指针上构造出 `std::shared_ptr` 时会创建控制块**==。如果你想从一个早已存在控制块的对象上创建 `std::shared_ptr`，你将假定传递一个 `std::shared_ptr` 或者 `std::weak_ptr` 作为构造函数实参，而不是原始指针。==用 `std::shared_ptr` 或者 `std::weak_ptr` 作为构造函数实参创建 `std::shared_ptr` 不会创建新控制块，因为它可以依赖传递来的智能指针指向控制块==。



这些规则造成的后果就是==从原始指针上构造超过一个 `std::shared_ptr` 会产生为定义行为==，原因是指向的对象有多个控制块关联，多个控制块意味着多个引用计数值，多个引用计数值意味着对象将会被销毁多次（每个引用计数一次）。那意味着像下面的代码是有问题的，很有问题，问题很大：
```cpp
auto pw = new Widget;                           // pw是原始指针
…
std::shared_ptr<Widget> spw1(pw, loggingDel);   // 为*pw创建控制块
…
std::shared_ptr<Widget> spw2(pw, loggingDel);   // 为*pw创建第二个控制块
```
现在，传给 spw1 的构造函数一个原始指针，它会为指向的对象创建一个控制块（因此有个引用计数值），这种情况下，指向的对象是 \*pw（即 pw 指向的对象），就其本身而言没什么问题，但是将同样的原始指针传递给 spw2 的构造函数会再次为 \*pw 创建一个控制块（所以也有个引用计数值）。因此 \*pw 有两个引用计数值，每一个最后都会变成零，然后最终导致 \*pw 销毁两次，第二个销毁会产生未定义行为。


因此，使用 `std::shared_ptr` 时需要注意：

1. ==避免传给 `std::shared_ptr` 构造函数原始指针==。通常替代方案是使用 `std::make_shared`，不过上面例子中，我们使用了自定义删除器，用 `std::make_shared` 就没办法做到；
1. ==如果你必须传给 `std::shared_ptr` 构造函数原始指针，直接传 new 出来的结果，不要传指针变量==。因此如果上面代这样重写，就没有问题了：
```cpp
std::shared_ptr<Widget> spw1(new Widget,loggingDel);    // 直接使用 new 的结果

std::shared_ptr<Widget> spw2(spw1);         // spw2 使用 spw1 一样的控制块
```


## this 指针和 `std::shared_ptr`
一个尤其令人意外的地方是使用 this 指针作为 `std::shared_ptr` 构造函数实参的时候可能导致创建多个控制块。假设我们的程序使用 `std::shared_ptr` 管理 Widget 对象，我们有一个数据结构用于跟踪已经处理过的Widget 对象：
```cpp
std::vector<std::shared_ptr<Widget>> processedWidgets;
```
继续，假设 Widget 有一个用于处理的成员函数：
```cpp
class Widget {
public:
    …
    void process();
    …
};
```
下面是一个对于 `Widget::process` 看起来合理的实现：
```cpp
void Widget::process()
{
    ... 
    // process the Widget
	// add it to list of processed Widgets; 
    processedWidgets.emplace_back(this);
}
// this is wrong!
```
错误的部分是传递 this，上面的代码可以通过编译，但是向 `std::shared_ptr` 的容器传递一个原始指针（this），`std::shared_ptr` 会由此为指向的 Widget（\*this）创建一个控制块。这看起来没什么问题，直到你意识到如果成员函数外面早已存在指向那个 Widget 对象的 `std::shared_ptr`，它是未定义行为。


解决办法是 `std::enable_shared_from_this` ，如果你想创建一个用 `std::shared_ptr` 管理的类，这个类能够用 this 指针安全地创建一个 `std::shared_ptr`，`std::enable_shared_from_this` 就可作为基类的模板类。在我们的例子中，Widget 将会继承自 `std::enable_shared_from_this`：
```cpp
class Widget: public std::enable_shared_from_this<Widget> {
public:
     ...
     void process();
     ...
};
```
`std::enable_shared_from_this` 是一个基类模板，它的模板参数总是某个继承自它的类，所以 Widget 继承自 `std::enable_shared_from_this<Widget>`，某类型继承自一个由该类型进行模板化得到的基类可能会让你觉得很奇怪，不过这种设计模式还有个标准名字：_The Curiously Recurring Template Pattern (==CRTP==)_。

`std::enable_shared_from_this` 定义了一个成员函数，成员函数会创建指向当前对象的 `std::shared_ptr` 却不创建多余控制块。这个成员函数就是 `shared_from_this`，无论在哪当你想在成员函数中使用 `std::shared_ptr` 指向 this 所指对象时都请使用它。这里有个 `Widget::process` 的安全实现：

```cpp
void Widget::process()
{
    // as before, process the Widget
	...
    // add std::shared_ptr to current object to processedWidgets
	processedWidgets.emplace_back(shared_from_this()); 
}
```
从内部来说，`shared_from_this` 查找当前对象控制块，然后创建一个新的 `std::shared_ptr` 关联这个控制块。设计的依据是当前对象已经存在一个关联的控制块。要想符合设计依据的情况，必须已经存在一个指向当前对象的 `std::shared_ptr`（比如调用 `shared_from_this` 的成员函数外面已经存在一个 `std::shared_ptr`）。==如果没有 `std::shared_ptr` 指向当前对象（即当前对象没有关联控制块），行为是未定义的，`shared_from_this` 通常抛出一个异常==。

==要想防止客户端在存在一个指向对象的 `std::shared_ptr` 前先调用含有 `shared_from_this` 的成员函数，继承自 `std::enable_shared_from_this` 的类通常将它们的构造函数声明为 private，并且让客户端通过返回 `std::shared_ptr` 的工厂函数创建对象==。以 Widget 为例，代码可以是这样：

```cpp
class Widget: public std::enable_shared_from_this<Widget> {
public:
	// factory function that perfect-forwards args to a private ctor
	template<typename... Ts>
	static std::shared_ptr<Widget> create(Ts&&... params);
  	...
  	void process(); 		// as before
  	...
private:
    ... 					// ctors
};
```
## std::shared_ptr 的限制
`std::shared_ptr` 不能处理的另一个东西是数组，和 `std::unique_ptr` 不同的是，`std::shared_ptr` 的 API 设计之初就是针对单个对象的，因此你应该使用 `std::array`，`std::vector`，`std::string` 而不是数组。


## Summary

1. `std::shared_ptr` 为有共享所有权的任意资源提供一种自动垃圾回收的便捷方式。
1. 较之于 `std::unique_ptr`，`std::shared_ptr` 对象通常大两倍，控制块会产生开销，需要原子性的引用计数修改操作。
1. 默认资源销毁是通过 delete，但是也支持自定义删除器，删除器的类型是什么对于 `std::shared_ptr` 的类型没有影响。
1. 避免从原始指针变量上创建 `std::shared_ptr`。

# 当需要允许悬空的 std::shared_ptr 时使用 std::weak_ptr
如果有一个像 `std::shared_ptr` 但是不参与资源所有权共享的指针是很方便的，换句话说，是一个类似`std::shared_ptr` 但不影响对象引用计数的指针。这种类型的智能指针必须要解决 `std::shared_ptr` 的问题：指向的对象可能已经销毁了。一个真正的智能指针应该通过追踪它何时悬空（dangles）来处理这个问题，比如它所指向的对象已经不存在了，这就是对 `std::weak_ptr` 最精确的描述。


## 创建和使用
你可能想知道什么时候该用 `std::weak_ptr`，你可能想知道关于 `std::weak_ptr` API 的更多。它什么都好除了不太智能，`std::weak_ptr` 不能解引用，也不能测试是否为空值。这是由于 `std::weak_ptr` 不是一个独立的智能指针，它是 `std::shared_ptr` 的增强。


这种关系在它创建之时就建立了，`std::weak_ptr` 通常从 `std::shared_ptr` 上创建。当从 `std::shared_ptr` 上创建 `std::weak_ptr` 时两者指向相同的对象，但是 `std::weak_ptr` 不会影响所指对象的引用计数：
```cpp
auto spw =                      // spw 创建之后，指向的 Widget 的
    std::make_shared<Widget>(); // 引用计数（ref count，RC）为 1。
                                // std::make_shared的信息参见条款21
…
std::weak_ptr<Widget> wpw(spw); // wpw 向与 spw 所指相同的 Widget，RC 仍为 1
…
spw = nullptr;                  // RC 变为 0，Widget 被销毁。
                                // wpw现 在悬空
```
悬空的 `std::weak_ptr` 被称作已经 expired（过期），你可以直接检查这种情况：
```cpp
if (wpw.expired()) …            //如果wpw没有指向对象…
```
但是通常你期望的是检查 `std::weak_ptr` 是否已经过期，如果没有过期则访问其指向的对象，这做起来可不是想着那么简单。由于缺少解引用操作，没有办法写这样的代码。即使有，将检查和解引用分开会引入竞态条件：==在调用 expired 和解引用操作之间，另一个线程可能对指向这对象的 `std::shared_ptr` 重新赋值或者析构，并由此造成对象已析构==。这种情况下，你的解引用将会产生未定义行为。


你需要的是一个原子操作检查 `std::weak_ptr` 是否已经过期，如果没有过期就访问所指对象。这可以通过从`std::weak_ptr` 创建 `std::shared_ptr` 来实现，具体有两种形式可以从 `std::weak_ptr` 上创建 `std::shared_ptr` ，具体用哪种取决于 `std::weak_ptr` 过期时你希望 `std::shared_ptr` 表现出什么行为。一种形式是 `std::weak_ptr::lock` ，它返回一个 `std::shared_ptr` ，如果 `std::weak_ptr` 过期这个 `std::shared_ptr` 为空：
```cpp
std::shared_ptr<Widget> spw1 = wpw.lock();  // 如果 wpw 过期，spw1 就为空
 											
auto spw2 = wpw.lock();                     // 同上，但是使用 auto
```
另一种形式是以 `std::weak_ptr` 为实参构造 `std::shared_ptr` ，这种情况中，如果 `std::weak_ptr` 过期，会抛出一个异常：
```cpp
std::shared_ptr<Widget> spw3(wpw);          // 如果 wpw 过期，抛出 std::bad_weak_ptr 异常
```
## 使用场景
### 缓存对象
考虑一个工厂函数，它基于一个唯一 ID 从只读对象上产出智能指针，工厂函数会返回一个该对象类型的`std::unique_ptr` ：
```cpp
std::unique_ptr<const Widget> loadWidget(WidgetID id);
```
如果调用 loadWidget 是一个昂贵的操作（比如它操作文件或者数据库 I/O）并且重复使用 ID 很常见，一个合理的优化是再写一个函数除了完成 loadWidget 做的事情之外再缓存它的结果。当每个请求获取的 Widget 阻塞了缓存也会导致本身性能问题，所以另一个合理的优化可以是当 Widget 不再使用的时候销毁它的缓存。


对于可缓存的工厂函数，返回 `std::unique_ptr` 不是好的选择。调用者应该接收缓存对象的智能指针，调用者也应该确定这些对象的生命周期，但是缓存本身也需要一个指针指向它所缓存的对象。缓存对象的指针需要知道它是否已经悬空，因为当工厂客户端使用完工厂产生的对象后，对象将被销毁，关联的缓存条目会悬空。所以缓存应该使用 `std::weak_ptr`，这可以知道是否已经悬空。这意味着工厂函数返回值类型应该是 `std::shared_ptr`，因为只有当对象的生命周期由 `std::shared_ptr` 管理时，`std::weak_ptr` 才能检测到悬空。


下面是一个简单的的 loadWidget 缓存版本的实现：
```cpp
std::shared_ptr<const Widget> fastLoadWidget(WidgetID id)
{
    static std::unordered_map<WidgetID,
                              std::weak_ptr<const Widget>> cache;

    auto objPtr = cache[id].lock();     // objPtr 是去缓存对象的
                                        // std::shared_ptr（或
                                        // 当对象不在缓存中时为 null）

    if (!objPtr) {                      // 如果不在缓存中
        objPtr = loadWidget(id);        // 加载它
        cache[id] = objPtr;             // 缓存它
    }
    return objPtr;
}
```
fastLoadWidget 的实现忽略了以下事实：缓存可能会累积过期的 `std::weak_ptr`，这些指针对应了不再使用的 Widget（也已经被销毁了），其改进方案并不会加深我们对 `std::weak_ptr` 的理解，这里就不再继续了。


### 观察者设计模式
让我们考虑第二个场景：观察者设计模式（Observer design pattern）。此模式的主要组件是 subjects（状态可能会更改的对象）和 observers（状态发生更改时要通知的对象）。在大多数实现中，每个 subject 都包含一个数据成员，该成员持有指向其 observers 的指针，这使 subjects 很容易发布状态更改通知。subjects 对控制observers 的生命周期（即它们什么时候被销毁）没有兴趣，但是 subjects 对确保另一件事具有极大的兴趣，就是一个 observer 被销毁时，不再尝试访问它。一个合理的设计是每个 subject 持有一个 `std::weak_ptr` 容器指向 observers，因此可以在使用前检查是否已经悬空。


### 循环引用
作为最后一个使用 `std::weak_ptr` 的例子，考虑一个持有三个对象 A、B、C 的数据结构，A 和 C 共享 B 的所有权，因此持有 `std::shared_ptr`：

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1631370463904-be3d250f-7109-4ff7-9bb8-c85177a57bee.png" alt="image.png" style="zoom:50%;" />

假定从 B 指向 A 的指针也很有用。应该使用哪种指针？

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1631370502229-2eba5445-d66f-44e3-b8bf-f6c77e0b6519.png" alt="image.png" style="zoom:50%;" />

有三种选择：

- 原始指针。使用这种方法，如果 A 被销毁，但是 C 继续指向 B，B 就会有一个指向 A 的悬空指针。而且 B 不知道指针已经悬空，所以 B 可能会继续访问，就会导致未定义行为。
- `std::shared_ptr`。这种设计，A 和 B 都互相持有对方的 `std::shared_ptr`，导致的 `std::shared_ptr` 环状结构（A 指向 B，B 指向 A）阻止 A 和 B 的销毁。尽管 A 和 B 无法从其他数据结构访问了（比如，C 不再指向 B），每个的引用计数都还是 1。如果发生了这种情况，A 和 B 都被泄漏：程序无法访问它们，但是资源并没有被回收。
- `std::weak_ptr` 。这避免了上述两个问题。如果 A 被销毁，B 指向它的指针悬空，但是 B 可以检测到这件事。尤其是，尽管 A 和 B 互相指向对方，B 的指针不会影响 A 的引用计数，因此在没有 `std::shared_ptr` 指向 A 时不会导致 A 无法被销毁。



使用 `std::weak_ptr` 显然是这些选择中最好的。但是，需要注意使用 `std::weak_ptr` 打破 `std::shared_ptr` 循环并不常见。在严格分层的数据结构比如树中，子节点只被父节点持有。当父节点被销毁时，子节点就被销毁。从父到子的链接关系可以使用 `std::unique_ptr` 很好的表征。从子到父的反向连接可以使用原始指针安全实现，因为子节点的生命周期肯定短于父节点。因此没有子节点解引用一个悬垂的父节点指针这样的风险。


当然，不是所有的使用指针的数据结构都是严格分层的，所以当发生这种情况时，比如上面所述缓存和观察者列表的实现之类的，知道 `std::weak_ptr` 随时待命也是不错的。


## Summary

1. 用 `std::weak_ptr` 替代可能会悬空的 `std::shared_ptr`。
1. `std::weak_ptr` 的潜在使用场景包括：缓存、观察者列表、打破 `std::shared_ptr` 环状结构。

# Links

1. [https://en.cppreference.com/w/cpp/memory](https://en.cppreference.com/w/cpp/memory)
1. Meyers S. Effective modern C++: 42 specific ways to improve your use of C++ 11 and C++ 14[M]. " O'Reilly Media, Inc.", 2014.
1. [https://github.com/kelthuzadx/EffectiveModernCppChinese](https://github.com/kelthuzadx/EffectiveModernCppChinese)
