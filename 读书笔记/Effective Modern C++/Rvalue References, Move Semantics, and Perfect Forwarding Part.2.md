# 避免在通用引用上重载
假定你需要写一个函数，它使用名字作为形参，打印当前日期和时间到日志中，然后将名字加入到一个全局数据结构中。你可能写出来这样的代码：
```cpp
std::multiset<std::string> names;           // 全局数据结构

void logAndAdd(const std::string& name)
{
    auto now = std::chrono::system_clock::now();  	// 获取当前时间
    log(now, "logAndAdd");                  		// 志记信息
    names.emplace(name);                    		// 把name加到全局数据结构中；
}                                           		// emplace的信息见条款42
```
这份代码没有问题，但是同样的也没有效率。考虑这三个调用：
```cpp
std::string petName("Darla");
logAndAdd(petName);                     // 传递左值 std::string
logAndAdd(std::string("Persephone"));	// 传递右值 std::string
logAndAdd("Patty Dog");                 // 传递字符串字面值
```

- 在第一个调用中，`logAndAdd` 的形参 `name` 绑定到变量 `petName`。在 `logAndAdd` 中 `name` 最终传给`names.emplace`。因为 `name` 是左值，会拷贝到 `names` 中。没有方法避免拷贝，因为是左值（`petName`）传递给 `logAndAdd` 的。
- 在第二个调用中，形参 `name` 绑定到右值（显式从 "Persephone" 创建的临时 `std::string`）。`name` 本身是个左值，所以它被拷贝到 `names` 中，但是我们意识到，原则上，它的值可以被移动到 `names` 中。本次调用中，我们有个拷贝代价，但是我们应该能用移动勉强应付。
- 在第三个调用中，形参 `name` 也绑定一个右值，但是这次是通过 "Patty Dog" 隐式创建的临时 `std::string` 变量。就像第二个调用中，`name` 被拷贝到 `names`，但是这里，传递给 `logAndAdd` 的实参是一个字符串字面量。==如果直接将字符串字面量传递给 `emplace`，就不会创建 `std::string` 的临时变量，而是直接在`std::multiset` 中通过字面量构建 `std::string`==。在第三个调用中，我们有个 `std::string` 拷贝开销，但是我们连移动开销都不想要，更别说拷贝的。



我们可以通过使用通用引用重写 `logAndAdd` 来使第二个和第三个调用效率提升，使用 `std::forward` 转发这个引用到 `emplace`。代码如下：
```cpp
template<typename T>
void logAndAdd(T&& name)
{
    auto now = std::chrono::system_lock::now();
    log(now, "logAndAdd");
    names.emplace(std::forward<T>(name));
}

std::string petName("Darla");           // 跟之前一样
logAndAdd(petName);                     // 跟之前一样，拷贝右值到 multiset
logAndAdd(std::string("Persephone"));	// 移动右值而不是拷贝它
logAndAdd("Patty Dog");                 // 在 multiset 直接创建 std::string
                                        // 而不是拷贝一个临时 std::string
```
## 重载通用引用
在故事的最后，我们可以骄傲的交付这个代码，但是我还没有告诉你客户不总是有直接访问 `logAndAdd` 要求的名字的权限。有些客户只有索引，`logAndAdd` 拿着索引在表中查找相应的名字。为了支持这些客户，`logAndAdd` 需要重载为：
```cpp
std::string nameFromIdx(int idx);   // 返回 idx 对应的名字

void logAndAdd(int idx)             // 新的重载
{
    auto now = std::chrono::system_lock::now();
    log(now, "logAndAdd");
    names.emplace(nameFromIdx(idx));
}
```
之后的两个调用按照预期工作：
```cpp
std::string petName("Darla");           // 跟之前一样

logAndAdd(petName);                     // 跟之前一样，
logAndAdd(std::string("Persephone")); 	// 这些调用都去调用
logAndAdd("Patty Dog");                 // T&&重载版本

logAndAdd(22);                          // 调用int重载版本
```


事实上，这只能基本按照预期工作，假定一个客户将 `short` 类型索引传递给 `logAndAdd`：
```cpp
short nameIdx;
…                                       // 给 nameIdx 一个值
logAndAdd(nameIdx);                     // 错误！
```
最后一行的注释并不清楚明白，下面让我来说明发生了什么。


有两个重载的 `logAndAdd`。==使用通用引用的那个推导出 `T` 的类型是 `short`，因此可以精确匹配。对于 `int` 类型参数的重载也可以在 `short` 类型提升后匹配成功。根据正常的重载解决规则，精确匹配优先于类型提升的匹配，所以被调用的是通用引用的重载==。


在通用引用那个重载中，`name` 形参绑定到要传入的 `short` 上，然后 `name` 被 `std::forward` 给 `names` （一个 `std::multiset<std::string>` ）的 `emplace` 成员函数，然后又被转发给 `std::string` 构造函数。`std::string` 没有接受 `short` 的构造函数，所以 `logAndAdd` 调用里的 `multiset::emplace` 调用里的 `std::string` 构造函数调用失败。所有这一切的原因就是对于 `short` 类型通用引用重载优先于 `int` 类型的重载。

==**使用通用引用的函数在 C++ 中是最贪婪的函数。它们几乎可以精确匹配任何类型的实参**==（极少不适用的实参在 Item30 中介绍）。这也是把重载和通用引用组合在一块是糟糕主意的原因：通用引用的实现会匹配比开发者预期要多得多的实参类型。


## 完美转发构造函数
一个更容易掉入这种陷阱的例子是写一个完美转发构造函数。简单对 `logAndAdd` 例子进行改造就可以说明这个问题。不用写接受 `std::string` 或者用索引查找 `std::string` 的自由函数，只是想一个构造函数有着相同操作的 `Person` 类：
```cpp
class Person {
public:
    template<typename T>
    explicit Person(T&& n)              // 完美转发的构造函数，初始化数据成员
    : name(std::forward<T>(n)) {}

    explicit Person(int idx)            // int的构造函数
    : name(nameFromIdx(idx)) {}
    …

private:
    std::string name;
};
```
就像在 `logAndAdd` 的例子中，传递一个不是 `int` 的整型变量（比如 `std::size_t`，`short`，`long` 等）会调用通用引用的构造函数而不是 `int` 的构造函数，这会导致编译错误。==这里这个问题甚至更糟糕，因为 `Person` 中存在的重载比肉眼看到的更多。在适当的条件下，C++ 会生成拷贝和移动构造函数，即使类包含了模板化的构造函数，模板函数能实例化产生与拷贝和移动构造函数一样的签名，也在合适的条件范围内==。如果拷贝和移动构造被生成，`Person` 类看起来就像这样：
```cpp
class Person {
public:
    template<typename T>            // 完美转发的构造函数
    explicit Person(T&& n)
    : name(std::forward<T>(n)) {}

    explicit Person(int idx);       // int的构造函数

    Person(const Person& rhs);      // 拷贝构造函数（编译器生成）
    Person(Person&& rhs);           // 移动构造函数（编译器生成）
    …
};
```
只有你在花了很多时间在编译器领域时，下面的行为才变得直观
```cpp
Person p("Nancy"); 
auto cloneOfP(p);                   // 从 p 创建新 Person；这通不过编译！
```
这里我们试图通过一个 `Person` 实例创建另一个 `Person`，显然应该调用拷贝构造即可（`p` 是左值，我们可以把通过移动操作来完成“拷贝”的想法请出去了）。但是这份代码不是调用拷贝构造函数，而是调用完美转发构造函数。然后，完美转发的函数将尝试使用 `Person` 对象 p 初始化 `Person` 的 `std::string` 数据成员，编译器就会报错。


“为什么？”你可能会疑问，“为什么拷贝构造会被完美转发构造替代？我们显然想拷贝 `Person` 到另一个 `Person` ”。确实我们是这样想的，但是编译器严格遵循 C++ 的规则，这里的相关规则就是控制对重载函数调用的解析规则。


编译器的理由如下：`cloneOfP` 被 `non-const` 左值 p 初始化，==这意味着模板化构造函数可被实例化为采用`Person` 类型的 `non-const` 左值==。实例化之后，`Person` 类看起来是这样的：
```cpp
class Person {
public:
    explicit Person(Person& n)          // 由完美转发模板初始化
    : name(std::forward<Person&>(n)) {}

    explicit Person(int idx);           // 同之前一样

    Person(const Person& rhs);          // 拷贝构造函数（编译器生成的）
    …
};
```
在这个语句中，
```cpp
auto cloneOfP(p);
```
==其中 `p` 被传递给拷贝构造函数或者完美转发构造函数。调用拷贝构造函数要求在 `p` 前加上 `const` 的约束来满足函数形参的类型，而调用完美转发构造不需要加这些东西。从模板产生的重载函数是更好的匹配，所以编译器按照规则：调用最佳匹配的函数==。“拷贝” non-const 左值类型的 `Person` 交由完美转发构造函数处理，而不是拷贝构造函数。


如果我们将本例中的传递的对象改为 `const` 的，会得到完全不同的结果：
```cpp
const Person cp("Nancy");   // 现在对象是 const 的
auto cloneOfP(cp);          // 调用拷贝构造函数！
```
因为被拷贝的对象是 `const`，是拷贝构造函数的精确匹配。虽然模板化的构造函数可以被实例化为有完全一样的函数签名，
```cpp
class Person {
public:
    explicit Person(const Person& n);   // 从模板实例化而来
  
    Person(const Person& rhs);          // 拷贝构造函数（编译器生成的）
    …
};
```
但是没啥影响，因为重载规则规定当模板实例化函数和非模板函数（或者称为“正常”函数）匹配优先级相当时，优先使用“正常”函数。拷贝构造函数（正常函数）因此胜过具有相同签名的模板实例化函数。


当继承纳入考虑范围时，完美转发的构造函数与编译器生成的拷贝、移动操作之间的交互会更加复杂。尤其是，派生类的拷贝和移动操作的传统实现会表现得非常奇怪。来看一下：
```cpp
class SpecialPerson: public Person {
public:
    SpecialPerson(const SpecialPerson& rhs) // 拷贝构造函数，调用基类的
    : Person(rhs)                           // 完美转发构造函数！
    { … }

    SpecialPerson(SpecialPerson&& rhs)      // 移动构造函数，调用基类的
    : Person(std::move(rhs))                // 完美转发构造函数！
    { … }
};
```
如同注释表示的，派生类的拷贝和移动构造函数没有调用基类的拷贝和移动构造函数，而是调用了基类的完美转发构造函数！为了理解原因，要知道派生类将 `SpecialPerson` 类型的实参传递给其基类，然后通过模板实例化和重载解析规则作用于基类 `Person`。最终，代码无法编译，因为 `std::string` 没有接受一个 `SpecialPerson` 的构造函数。


## Summary

1. 对通用引用形参的函数进行重载，通用引用函数的调用机会几乎总会比你期望的多得多。
1. 完美转发构造函数是糟糕的实现，因为对于 non-const 左值，它们比拷贝构造函数而更匹配，而且会劫持派生类对于基类的拷贝和移动构造函数的调用。



# 通用引用重载的替代方法
## 放弃重载
在上面的第一个例子中，`logAndAdd` 是许多函数的代表，这些函数可以使用不同的名字来避免在通用引用上的重载的弊端。例如两个重载的 `logAndAdd` 函数，可以分别改名为 `logAndAddName` 和 `logAndAddNameIdx`。但是，这种方式不能用在第二个例子，`Person` 构造函数中，因为构造函数的名字被语言固定了。此外谁愿意放弃重载呢？


## 传递const T&
一种替代方案是退回到 C++98，然后将传递通用引用替换为传递 _lvalue-refrence-to-const_。事实上，这是上一节中首先考虑的方法，==缺点是效率不高==。现在我们知道了通用引用和重载的相互关系，所以放弃一些效率来确保行为正确简单可能也是一种不错的折中。


## 传值
通常在不增加复杂性的情况下提高性能的一种方法是，将按传引用形参替换为按值传递，这是违反直觉的。这里，在`Person` 的例子中展示：
```cpp
class Person {
public:
    explicit Person(std::string n)  // 代替 T&& 构造函数，
    : name(std::move(n)) {}         // std::move的使用见条款41
  
    explicit Person(int idx)        // 同之前一样
    : name(nameFromIdx(idx)) {}
    …

private:
    std::string name;
};
```
因为没有 `std::string` 构造函数可以接受整型参数，所有 `int` 或者其他整型变量（比如 `std::size_t`、`short`、`long` 等）都会使用 `int` 类型重载的构造函数。相似的，所有 `std::string` 类似的实参（还有可以用来创建 `std::string` 的东西，比如字面量 "Ruth" 等）都会使用 `std::string` 类型的重载构造函数。没有意外情况。我想你可能会说有些人使用 `0` 或者 `NULL` 指代空指针会调用 `int` 重载的构造函数让他们很吃惊，但是这些人应该参考 Item8 反复阅读直到使用 0 或者 NULL 作为空指针让他们恶心。


## 使用 tag dispatch
传递 _lvalue-reference-to-const_ 以及按值传递都不支持完美转发。如果使用通用引用的动机是完美转发，我们就只能使用通用引用了，没有其他选择。但是又不想放弃重载。所以如果不放弃重载又不放弃通用引用，如何避免在通用引用上重载呢？


实际上并不难。通过查看所有重载的所有形参以及调用点的所有传入实参，然后选择最优匹配的函数——考虑所有形参/实参的组合。==通用引用通常提供了最优匹配，但是如果通用引用仅是形参列表的一部分，该形参列表还包含了其他非通用引用的话，则非通用引用形参的较差匹配会使这个重载版本不被运行==。这就是 _tag dispatch_ 方法的基础，下面的示例会使这段话更容易理解。


我们将标签分派应用于 `logAndAdd` 例子，下面是原来的代码，以免你再分心回去查看：
```cpp
std::multiset<std::string> names;       // 全局数据结构

template<typename T>                    // 志记信息，将 name 添加到数据结构
void logAndAdd(T&& name)
{
    auto now = std::chrono::system_clokc::now();
    log(now, "logAndAdd");
    names.emplace(std::forward<T>(name));
}
```
就其本身而言，功能执行没有问题，但是如果引入一个 `int` 类型的重载来用索引查找对象，就会重新陷入上节中描述的麻烦。这个条款的目标是避免它。不通过重载，我们重新实现 `logAndAdd` 函数分拆为两个函数，一个针对整型值，一个针对其他。`logAndAdd` 本身接受所有实参类型，包括整型和非整型。


这两个真正执行逻辑的函数命名为 `logAndAddImpl`，即我们使用重载。其中一个函数接受通用引用。所以我们同时使用了重载和通用引用。但是每个函数接受第二个形参，表征传入的实参是否为整型。这第二个形参可以帮助我们避免陷入到上节中提到的麻烦中，因为我们将其安排为第二个实参决定选择哪个重载函数。


代码如下，这是最接近正确版本的：
```cpp
template<typename T>
void logAndAdd(T&& name) 
{
    logAndAddImpl(std::forward<T>(name), std::is_integral<T>());   // 不那么正确
}
```
这个函数转发它的形参给 `logAndAddImpl` 函数，但是多传递了一个表示形参 `T` 是否为整型的实参。至少，这就是应该做的。对于右值的整型实参来说，这也是正确的。但是，==如果左值实参传递给通用引用 `name`，对 `T` 类型推断会得到左值引用。所以如果左值 `int` 被传入 `logAndAdd`，`T` 将被推断为 `int&`。这不是一个整型类型，因为引用不是整型类型。这意味着 `std::is_integral<T>` 对于任何左值实参返回 `false`，即使确实传入了整型值==。


意识到这个问题基本相当于解决了它，因为 C++ 标准库有一个 [_**type trait**_](https://en.cppreference.com/w/cpp/header/type_traits)，[`std::remove_reference`](https://www.yuque.com/littleneko/note/aqw4vi)，函数名字就说明做了我们希望的：移除类型的引用说明符。所以正确实现的代码应该是这样：
```cpp
template<typename T>
void logAndAdd(T&& name)
{
    logAndAddImpl(
        std::forward<T>(name),
        std::is_instegral<typename std::remove_reference<T>::type>()
    );
}
```
处理完之后，我们可以将注意力转移到名为 `logAndAddImpl` 的函数上了。有两个重载函数，第一个仅用于非整型类型（即 `std::is_instegral<typename std::remove_reference<T>::type>` 是 `false`）：
```cpp
template<typename T>                            // 非整型实参：添加到全局数据结构中
void logAndAddImpl(T&& name, std::false_type)	// 译者注：高亮 std::false_type
{
    auto now = std::chrono::system_clock::now();
    log(now, "logAndAdd");
    names.emplace(std::forward<T>(name));
}
```
一旦你理解了高亮参数的含义，代码就很直观。概念上，`logAndAdd` 传递一个布尔值给 `logAndAddImpl` 表明是否传入了一个整型类型，但是 `true` 和 `false` 是运行时值，我们需要使用重载决议——编译时决策——来选择正确的 `logAndAddImpl` 重载。这意味着我们需要一个类型对应 `true`，另一个不同的类型对应 `false`。这个需要是经常出现的，所以标准库提供了这样两个命名 ==`std::true_type`== 和 ==`std::false_type`==。`logAndAdd` 传递给 `logAndAddImpl` 的实参是个对象，如果 `T` 是整型，对象的类型就继承自 `std::true_type`，反之继承自 `std::false_type`。最终的结果就是，当 `T` 不是整型类型时，这个 `logAndAddImpl` 重载是个可供调用的候选者。


第二个重载覆盖了相反的场景：当 `T` 是整型类型。在这个场景中，`logAndAddImpl` 简单找到对应传入索引的名字，然后传递给 `logAndAdd`：
```cpp
std::string nameFromIdx(int idx);           // 与条款26一样，整型实参：查找名字并用它调用logAndAdd
void logAndAddImpl(int idx, std::true_type) // 译者注：高亮 std::true_type
{
  logAndAdd(nameFromIdx(idx)); // 注意这里是调用了 logAndAdd 而不是前一个 logAndAddImpl 重载
}

```
通过索引找到对应的 `name`，然后让 `logAndAddImpl` 传递给 `logAndAdd`（名字会被再 `std::forward` 给另一个 `logAndAddImpl` 重载），我们避免了将日志代码放入这个 `logAndAddImpl` 重载中。


在这个设计中，类型 `std::true_type` 和 `std::false_type` 是==“_标签_”== (tag)，==其唯一目的就是强制重载解析按照我们的想法来执行。注意到我们甚至没有对这些参数进行命名。他们在运行时毫无用处，事实上我们希望编译器可以意识到这些标签形参没被使用，然后在程序执行时优化掉它们==（至少某些时候有些编译器会这样做）。通过创建标签对象，在 `logAndAdd` 内部将重载实现函数的调用“分发”（dispatch）给正确的重载，因此这个设计名称为：tag dispatch。这是模板元编程的标准构建模块，你对现代 C++ 库中的代码了解越多，你就会越多遇到这种设计。


## 约束使用通用引用的模板(std::enable_if)
tag dispatch 的关键是存在单独一个函数（没有重载）给客户端 API，这个单独的函数分发给具体的实现函数。创建一个没有重载的分发函数通常是容易的，但是上节中所述第二个问题案例 `Person` 类的完美转发构造函数是个例外。编译器可能会自行生成拷贝和移动构造函数，所以即使你只写了一个构造函数并在其中使用 tag dispatch，有一些对构造函数的调用也被编译器生成的函数处理，绕过了分发机制。


实际上，真正的问题不是编译器生成的函数会绕过 tag diapatch 设计，而是**不总会**绕过去。你希望类的拷贝构造函数总是处理该类型的左值拷贝请求，但是如同上节中所述，提供具有通用引用的构造函数，会使通用引用构造函数在拷贝 _non-const_ 左值时被调用（而不是拷贝构造函数）。那个条款还说明了当一个基类声明了完美转发构造函数，派生类实现自己的拷贝和移动构造函数时会调用那个完美转发构造函数，尽管正确的行为是调用基类的拷贝或者移动构造。


这种情况，采用通用引用的重载函数通常比期望的更加贪心，虽然不像单个分派函数一样那么贪心，而又不满足使用tag dispatch 的条件。你需要另外的技术，可以让你确定允许使用通用引用模板的条件。朋友，你需要的就是[`std::enable_if`](https://en.cppreference.com/w/cpp/types/enable_if)。

==`std::enable_if` 可以给你提供一种强制编译器执行行为的方法，像是特定模板不存在一样。这种模板被称为被禁止（disabled）==。默认情况下，所有模板是启用的（enabled），但是使用 `std::enable_if` 可以使得仅在`std::enable_if` 指定的条件满足时模板才启用。在这个例子中，我们只在传递的类型不是 `Person` 时使用 `Person` 的完美转发构造函数。如果传递的类型是 `Person` ，我们要禁止完美转发构造函数（即让编译器忽略它），因为这会让拷贝或者移动构造函数处理调用，这是我们想要使用 `Person` 初始化另一个 `Person` 的初衷。


这个主意听起来并不难，但是语法比较繁杂，尤其是之前没有接触过的话，让我慢慢引导你。有一些 `std::enbale_if` 的 contidion 部分的样板，让我们从这里开始。下面的代码是 `Person` 完美转发构造函数的声明，多展示 `std::enable_if` 的部分来简化使用难度。我仅展示构造函数的声明，因为 `std::enable_if` 的使用对函数实现没影响。实现部分跟上一节中没有区别。
```cpp
class Person {
public:
    template<typename T,
             typename = typename std::enable_if<condition>::type>   // 译者注：本行高亮，condition 为某其他特定条件
    explicit Person(T&& n);
    …
};
```
为了理解高亮部分发生了什么，我很遗憾的表示你要自行参考其他代码，因为详细解释需要花费一定空间和时间，而本书并没有足够的空间（在你自行学习过程中，请研究 “**SFINAE**” 以及 `std::enable_if`，因为 “SFINAE” 就是使 `std::enable_if` 起作用的技术）。这里我想要集中讨论条件的表示，该条件表示此构造函数是否启用。


这里我们想表示的条件是确认 `T` 不是 `Person` 类型，即模板构造函数应该在 `T` 不是 `Person` 类型的时候启用。==多亏了 _type trait_ 可以确定两个对象类型是否相同（[`std::is_same`](https://en.cppreference.com/w/cpp/types/is_same)），看起来我们需要的就是 `!std::is_same<Person, T>::value`==。这很接近我们想要的了，但是不完全正确，因为使用左值来初始化通用引用的话会推导成左值引用，比如这个代码:
```cpp
Person p("Nancy");
auto cloneOfP(p);       // 用左值初始化
```
`T` 的类型在通用引用的构造函数中被推导为 `Person&`。`Person` 和 `Person&` 类型是不同的，`std::is_same` 的结果也反映了：`std::is_same<Person, Person&>::value` 是 `false`。


如果我们更精细考虑仅当 `T` 不是 `Person` 类型才启用模板构造函数，我们会意识到当我们查看 `T` 时，应该忽略：

- **是否是个引用**。对于决定是否通用引用构造函数启用的目的来说，`Person` ，`Person&`，`Person&&` 都是跟 `Person` 一样的。
- **是不是 `const` 或者 `volatile`**。如上所述，`const Person`，`volatile Person` ，`const volatile Person` 也是跟 `Person` 一样的。



这意味着我们需要一种方法消除对于`T` 的引用、`const`、`volatile` 修饰。再次，标准库提供了这样功能的_type trait_，就是 [`std::decay`](https://en.cppreference.com/w/cpp/types/decay)，==`std::decay<T>::value` 与 `T` 是相同的，只不过会移除引用和 _**cv 限定符**_==（cv-qualifiers，即 `const` 或 `volatile` 标识符）的修饰。（这里我没有说出另外的真相，`std::decay` 如同其名一样，可以将数组或者函数退化成指针，但是在这里讨论的问题中，它刚好合适）。我们想要控制构造函数是否启用的条件可以写成：
```cpp
!std::is_same<Person, typename std::decay<T>::type>::value
```
即 `Person` 和 `T` 的类型不同，忽略了所有引用和 cv 限定符，将其带回上面 `std::enable_if` 样板的代码中，加上调整一下格式，让各部分如何组合在一起看起来更容易，`Person` 的完美转发构造函数的声明如下：
```cpp
class Person {
public:
    template<
        typename T,
        typename = typename std::enable_if<
                       !std::is_same<Person, 
                                     typename std::decay<T>::type
                                    >::value
                   >::type
    >
    explicit Person(T&& n);
    …
};
```
如果你之前从没有看到过这种类型的代码，那你可太幸福了。最后才放出这种设计是有原因的。当你有其他机制来避免同时使用重载和通用引用时（你总会这样做），确实应该那样做。不过，一旦你习惯了使用函数语法和尖括号的使用，也不坏。此外，这可以提供你一直想要的行为表现。在上面的声明中，使用 `Person` 初始化一个 `Person` ——无论是左值还是右值，const 还是 non-const，volatile 还是 non-volatile——都不会调用到通用引用构造函数。


成功了，对吗？确实！

---

啊，不对。等会再庆祝。上一节中还有一个情景需要解决，我们需要继续探讨下去。


假定从 `Person` 派生的类以常规方式实现拷贝和移动操作：
```cpp
class SpecialPerson: public Person {
public:
    SpecialPerson(const SpecialPerson& rhs) // 拷贝构造函数，调用基类的
    : Person(rhs)                           // 完美转发构造函数！
    { … }
    
    SpecialPerson(SpecialPerson&& rhs)      // 移动构造函数，调用基类的
    : Person(std::move(rhs))                // 完美转发构造函数！
    { … }
    
    …
};
```
当我们拷贝或者移动一个 `SpecialPerson` 对象时，我们希望调用基类对应的拷贝和移动构造函数，来拷贝或者移动基类部分，但是这里，我们将 `SpecialPerson` 传递给基类的构造函数，因为 `SpecialPerson` 和 `Person` 类型不同（在应用 `std::decay` 后也不同），所以完美转发构造函数是启用的，会实例化为精确匹配`SpecialPerson` 实参的构造函数。相比于派生类到基类的转化——这个转化对于在 `Person` 拷贝和移动构造函数中把 `SpecialPerson` 对象绑定到 `Person` 形参非常重要，生成的精确匹配是更优的，所以这里的代码，拷贝或者移动 `SpecialPerson` 对象就会调用 `Person` 类的完美转发构造函数来执行基类的部分。


派生类仅仅是按照常规的规则生成了自己的移动和拷贝构造函数，所以这个问题的解决还要落实在基类，尤其是控制是否使用 `Person` 通用引用构造函数启用的条件。现在我们意识到不只是禁止 `Person` 类型启用模板构造函数，而是禁止 `Person` 以及任何派生自 `Person` 的类型启用模板构造函数。讨厌的继承！


你应该不意外在这里看到标准库中也有 _type trait_ 判断一个类型是否继承自另一个类型，就是 [`std::is_base_of`](https://en.cppreference.com/w/cpp/types/is_base_of)，如果 ==`std::is_base_of<T1, T2>` 是 `true` 就表示 `T2` 派生自 `T1`==。类型也可被认为是从他们自己派生，所以 `std::is_base_of<T, T>::value` 总是 `true` 。这就很方便了，我们想要修正控制 `Person` 完美转发构造函数的启用条件，只有当 `T` 在消除引用和 `cv` 限定符之后，并且既不是 `Person` 又不是 `Person` 的派生类时，才满足条件。所以使用 `std::is_base_of` 代替 `std::is_same` 就可以了：
```cpp
class Person {
public:
    template<
        typename T,
        typename = typename std::enable_if<
                       !std::is_base_of<Person, 
                                        typename std::decay<T>::type
                                       >::value
                   >::type
    >
    explicit Person(T&& n);
    …
};
```
现在我们终于完成了最终版本。这是 C++11 版本的代码，如果我们使用 C++14，这份代码也可以工作，但是可以使用 `std::enable_if` 和 `std::decay` 的别名模板来少写 “typename” 和 “::type” 这样的麻烦东西，产生了下面这样看起来舒爽的代码：
```cpp
class Person  {                                         // C++14
public:
    template<
        typename T,
        typename = std::enable_if_t<                    // 这儿更少的代码
                       !std::is_base_of<Person,
                                        std::decay_t<T> // 还有这儿
                                       >::value
                   >                                    // 还有这儿
    >
    explicit Person(T&& n);
    …
};

```
好了，我承认，我又撒谎了。我们还没有完成，但是越发接近最终版本了。非常接近，我保证。


我们已经知道如何使用 `std::enable_if` 来选择性禁止 `Person` 通用引用构造函数，来使得一些实参类型确保使用到拷贝或者移动构造函数，但是我们还没将其应用于区分整型参数和非整型参数。毕竟，我们的原始目标是解决构造函数模糊性问题。


我们需要的所有东西——我确实意思是所有——是（1）加入一个 `Person` 构造函数重载来处理整型参数；（2）约束模板构造函数使其对于某些实参禁用。使用这些我们讨论过的技术组合起来，就能解决这个问题了：
```cpp
class Person {
public:
    template<
        typename T,
        typename = std::enable_if_t<
            !std::is_base_of<Person, std::decay_t<T>>::value
            &&
            !std::is_integral<std::remove_reference_t<T>>::value
        >
    >
    explicit Person(T&& n)          // 对于 std::strings 和可转化为
    : name(std::forward<T>(n))      // std::strings 的实参的构造函数
    { … }

    explicit Person(int idx)        // 对于整型实参的构造函数
    : name(nameFromIdx(idx))
    { … }

    …                               // 拷贝、移动构造函数等

private:
    std::string name;
};
```
看！多么优美！好吧，优美之处只是对于那些迷信模板元编程之人，但是确实提出了不仅能工作的方法，而且极具技巧。因为使用了完美转发，所以具有最大效率，因为控制了通用引用与重载的结合而不是禁止它，这种技术可以被用于不可避免要用重载的情况（比如构造函数）。


## 折中
本条款提到的前三个技术——放弃重载、传递 `const T&`、传值——在函数调用中指定每个形参的类型。后两个技术—— tag dispatch 和限制模板适用范围——使用完美转发，因此不需要指定形参类型。这一基本决定（是否指定类型）有一定后果。


通常，完美转发更有效率，因为它避免了仅仅去为了符合形参声明的类型而创建临时对象。在 Person 构造函数的例子中，完美转发允许将 "Nancy" 这种字符串字面量转发到 Person 内部的 `std::string` 的构造函数，不使用完美转发的技术则会从字符串字面值创建一个临时 `std::string` 对象，来满足 Person 构造函数指定的形参要求。


但是完美转发也有缺点。即使某些类型的实参可以传递给接受特定类型的函数，也无法完美转发。


第二个问题是当客户传递无效参数时错误消息的可理解性。例如假如客户传递了一个由 char16_t（一种 C++11 引入的类型表示 16 位字符）而不是 char（`std::string` 包含的）组成的字符串字面值来创建一个 Person 对象：
```cpp
Person p(u"Konrad Zuse");   // "Konrad Zuse" 由 const char16_t 类型字符组成
```
使用本条款中讨论的前三种方法，编译器将看到可用的采用 `int` 或者 `std::string` 的构造函数，它们或多或少会产生错误消息，表示没有可以从 `const char16_t[12]` 转换为 `int` 或者 `std::string` 的方法。


但是，基于完美转发的方法，`const char16_t` 不受约束地绑定到构造函数的形参。从那里将转发到 Person 的`std::string` 数据成员的构造函数，在这里，调用者传入的内容（`const char16_t` 数组）与所需内容（`std::string` 构造函数可接受的类型）发生的不匹配会被发现。由此产生的错误消息会让人更印象深刻，在我使用的编译器上，会产生超过 160 行错误信息。


在这个例子中，通用引用仅被转发一次（从 Person 构造函数到 `std::string` 构造函数），但是更复杂的系统中，在最终到达判断实参类型是否可接受的地方之前，通用引用会被多层函数调用转发。通用引用被转发的次数越多，产生的错误消息偏差就越大。许多开发者发现，这种特殊问题是发生在留有通用引用形参的接口上，这些接口以性能作为首要考虑点。


在 Person 这个例子中，我们知道完美转发函数的通用引用形参要作为 `std::string` 的初始化器，所以我们可以用 `static_assert` 来确认它可以起这个作用。==[`std::is_constructible`](https://en.cppreference.com/w/cpp/types/is_constructible) 这个 _type trait_ 执行编译时测试，确定一个类型的对象是否可以用另一个不同类型（或多个类型）的对象（或多个对象）来构造==，所以代码可以这样：
```cpp
class Person {
public:
    template<                       // 同之前一样
        typename T,
        typename = std::enable_if_t<
            !std::is_base_of<Person, std::decay_t<T>>::value
            &&
            !std::is_integral<std::remove_reference_t<T>>::value
        >
    >
    explicit Person(T&& n)
    : name(std::forward<T>(n))
    {
        // 断言可以用 T 对象创建 std::string
        static_assert(
        std::is_constructible<std::string, T>::value,
        "Parameter n can't be used to construct a std::string"
        );

        …               // 通常的构造函数的工作写在这

    }
    
    …                   // Person 类的其他东西（同之前一样）
};
```
如果客户代码尝试使用无法构造 `std::string` 的类型创建 Person，会导致指定的错误消息。不幸的是，在这个例子中，`static_assert` 在构造函数体中，但是转发的代码作为成员初始化列表的部分在检查之前。所以我使用的编译器，结果是由 `static_assert` 产生的清晰的错误消息在常规错误消息（多达160行以上那个）后出现。


## Summary

- 通用引用和重载的组合替代方案包括使用不同的函数名，通过 _lvalue-reference-to-const_ 传递形参，按值传递形参，使用 tag dispatch。
- 通过 `std::enable_if` 约束模板，允许组合通用引用和重载使用，但它也控制了编译器在哪种条件下才使用通用引用重载。
- 通用引用参数通常具有高效率的优势，但是可用性就值得斟酌。



# Links

1. [https://en.cppreference.com/w/cpp/header/type_traits](https://en.cppreference.com/w/cpp/header/type_traits)
1. [https://en.cppreference.com/w/cpp/types/remove_reference](https://en.cppreference.com/w/cpp/types/remove_reference)
1. [https://en.cppreference.com/w/cpp/types/enable_if](https://en.cppreference.com/w/cpp/types/enable_if)
1. [https://en.cppreference.com/w/cpp/language/sfinae](https://en.cppreference.com/w/cpp/language/sfinae)
1. [https://en.cppreference.com/w/cpp/types/is_same](https://en.cppreference.com/w/cpp/types/is_same)
1. [https://en.cppreference.com/w/cpp/types/decay](https://en.cppreference.com/w/cpp/types/decay)
1. [https://en.cppreference.com/w/cpp/types/is_base_of](https://en.cppreference.com/w/cpp/types/is_base_of)
1. [https://en.cppreference.com/w/cpp/types/is_constructible](https://en.cppreference.com/w/cpp/types/is_constructible)
1. [https://github.com/kelthuzadx/EffectiveModernCppChinese](https://github.com/kelthuzadx/EffectiveModernCppChinese)
