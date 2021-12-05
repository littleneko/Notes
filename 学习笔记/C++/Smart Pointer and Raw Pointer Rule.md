# CppCoreGuidelines 的建议
- R.20: Use `unique_ptr` or `shared_ptr` to ==represent ownership==
- R.21: ==**Prefer `unique_ptr` over `shared_ptr` unless you need to share ownership**==

​	**Example, bad** This needlessly adds and maintains a reference count.

```cpp
void f()
{
    shared_ptr<Base> base = make_shared<Derived>();
    // use base locally, without copying it -- refcount never exceeds 1
} // destroy base
```
​	**Example** This is more efficient:

```cpp
void f()
{
    unique_ptr<Base> base = make_unique<Derived>();
    // use base locally
} // destroy base
```

- R.22: Use `make_shared()` to make `shared_ptr`s
- R.23: Use `make_unique()` to make `unique_ptr`s
- R.24: Use `std::weak_ptr` to break cycles of `shared_ptr`s
- R.30: ==**Take smart pointers as parameters only to explicitly express lifetime semantics**== (F.7)
- R.31: If you have non-std smart pointers, follow the basic pattern from std
- R.32: ==**Take a `unique_ptr<widget>` parameter to express that a function assumes ownership of a widget**==

​	**Reason** Using `unique_ptr` in this way both documents and enforces the function call’s ownership transfer.

​	**Example**

```cpp
void sink(unique_ptr<widget>); // takes ownership of the widget

void uses(widget*);            // just uses the widget
```
​	**Example, bad**
```cpp
void thinko(const unique_ptr<widget>&); // usually not what you want
```



- R.33: ==**Take a `unique_ptr<widget>&` parameter to express that a function reseats the widget**==

​	**Reason** Using unique_ptr in this way both documents and enforces the function call’s reseating semantics.Note “reseat” means “making a pointer or a smart pointer refer to a different object.”

​	**Example**
```cpp
void reseat(unique_ptr<widget>&); // "will" or "might" reseat pointer
```
​	**Example, bad**
```cpp
void thinko(const unique_ptr<widget>&); // usually not what you want
```

- R.34: Take a `shared_ptr<widget>` parameter to express that a function ==is part owner==
- R.35: Take a `shared_ptr<widget>&` parameter to express that a function ==might reseat the shared pointer==
- R.36: Take a `const shared_ptr<widget>&` parameter to express that it ==might retain a reference count to the object== ???


​	**Example, good**
```cpp
void share(shared_ptr<widget>);            // share -- "will" retain refcount

void reseat(shared_ptr<widget>&);          // "might" reseat ptr

void may_share(const shared_ptr<widget>&); // "might" retain refcount
```

- R.37: Do not pass a pointer or reference obtained from an aliased smart pointer



- F.7: ==**For general use, take `T*` or `T&` arguments rather than smart pointers**==

​	**Reason** 

   1. ==Passing a smart pointer transfers or shares ownership and should **only be used when ownership semantics are intended**==. A function that does not manipulate lifetime should take *raw pointers* or *references* instead.
   1. ==Passing by smart pointer restricts the use of a function to callers that use smart pointers==. A function that needs a widget should be able to accept any widget object, not just ones whose lifetimes are managed by a particular kind of smart pointer.
   1. Passing a shared smart pointer (e.g., `std::shared_ptr` ) ==implies a run-time cost==.

​	**Example**

```cpp
// accepts any int*
void f(int*);

// can only accept ints for which you want to transfer ownership
void g(unique_ptr<int>);

// can only accept ints for which you are willing to share ownership
void g(shared_ptr<int>);

// doesn't change ownership, but requires a particular ownership of the caller
void h(const unique_ptr<int>&);

// accepts any int
void h(int&);
```
​	**Example, Bad**
```cpp
// callee
void f(shared_ptr<widget>& w)
{
    // ...
    use(*w); // only use of w -- the lifetime is not used at all
    // ...
};

// caller
shared_ptr<widget> my_widget = /* ... */;
f(my_widget);

widget stack_widget;
f(stack_widget); // error
```
​	**Example, Good**
```cpp
// callee
void f(widget& w)
{
    // ...
    use(w);
    // ...
};

// caller
shared_ptr<widget> my_widget = /* ... */;
f(*my_widget);

widget stack_widget;
f(stack_widget); // ok -- now this works
```

- I.11: ==**Never transfer ownership by a raw pointer (`T*`) or reference (`T&`)**==

​	**Reason** If there is any doubt whether the caller or the callee owns an object, leaks or premature destruction will occur.

​	**Example Consider**:

```cpp
X* compute(args)    // don't
{
    X* res = new X{};
    // ...
    return res;
}
```
Who deletes the returned X? The problem would be harder to spot if compute returned a reference. Consider returning the result by value (use move semantics if the result is large):

​	**Alternative**: Pass ownership using a “smart pointer”, such as unique_ptr (for exclusive ownership) and shared_ptr (for shared ownership). However, that is less elegant and often less efficient than returning the object itself, so use smart pointers only if reference semantics are needed.

​	**Alternative**: Sometimes older code can’t be modified because of ABI compatibility requirements or lack of resources. In that case, mark owning pointers using owner from the guidelines support library:

```cpp
owner<X*> compute(args)    // It is now clear that ownership is transferred
{
    owner<X*> res = new X{};
    // ...
    return res;
}
```


# Google C++ style 的建议
Prefer to have single, fixed owners for dynamically allocated objects. Prefer to transfer ownership with smart pointers.


**Definition**
"Ownership" is a bookkeeping technique for managing dynamically allocated memory (and other resources). The owner of a dynamically allocated object is an object or function that is responsible for ensuring that it is deleted when no longer needed. Ownership can sometimes be shared, in which case the last owner is typically responsible for deleting it. Even when ownership is not shared, it can be transferred from one piece of code to another.

"Smart" pointers are classes that act like pointers, e.g., by overloading the * and -> operators. Some smart pointer types can be used to automate ownership bookkeeping, to ensure these responsibilities are met. std::unique_ptr is a smart pointer type introduced in C++11, which expresses exclusive ownership of a dynamically allocated object; the object is deleted when the std::unique_ptr goes out of scope. It cannot be copied, but can be moved to represent ownership transfer. std::shared_ptr is a smart pointer type that expresses shared ownership of a dynamically allocated object. std::shared_ptrs can be copied; ownership of the object is shared among all copies, and the object is deleted when the last std::shared_ptr is destroyed.

**Pros**

- It's virtually impossible to manage dynamically allocated memory without some sort of ownership logic.
- Transferring ownership of an object can be cheaper than copying it (if copying it is even possible).
- Transferring ownership can be simpler than 'borrowing' a pointer or reference, because it reduces the need to coordinate the lifetime of the object between the two users.
- Smart pointers can improve readability by making ownership logic explicit, self-documenting, and unambiguous.
- Smart pointers can eliminate manual ownership bookkeeping, simplifying the code and ruling out large classes of errors.
- For const objects, shared ownership can be a simple and efficient alternative to deep copying.



**cons**

- Ownership must be represented and transferred via pointers (whether smart or plain). Pointer semantics are more complicated than value semantics, especially in APIs: you have to worry not just about ownership, but also aliasing, lifetime, and mutability, among other issues.

- The performance costs of value semantics are often overestimated, so the performance benefits of ownership transfer might not justify the readability and complexity costs.

- APIs that transfer ownership force their clients into a single memory management model.

- Code using smart pointers is less explicit about where the resource releases take place.

- std::unique_ptr expresses ownership transfer using C++11's move semantics, which are relatively new and may confuse some programmers.

- Shared ownership can be a tempting alternative to careful ownership design, obfuscating the design of a system.

- Shared ownership requires explicit bookkeeping at run-time, which can be costly.

- In some cases (e.g., cyclic references), objects with shared ownership may never be deleted.

- Smart pointers are not perfect substitutes for plain pointers.

  

**Decision**
If dynamic allocation is necessary, prefer to keep ownership with the code that allocated it. If other code needs access to the object, consider passing it a copy, or passing a pointer or reference without transferring ownership. Prefer to use std::unique_ptr to make ownership transfer explicit. For example:
```cpp
std::unique_ptr<Foo> FooFactory();
void FooConsumer(std::unique_ptr<Foo> ptr);
```
Do not design your code to use shared ownership without a very good reason. One such reason is to avoid expensive copy operations, but you should only do this if the performance benefits are significant, and the underlying object is immutable (i.e., `std::shared_ptr<const Foo>`). If you do use shared ownership, prefer to use `std::shared_ptr`.

Never use `std::auto_ptr`. Instead, use `std::unique_ptr`.

# Links

1. [https://isocpp.github.io/CppCoreGuidelines/CppCoreGuidelines#S-resource](https://isocpp.github.io/CppCoreGuidelines/CppCoreGuidelines#S-resource)
1. [https://isocpp.github.io/CppCoreGuidelines/CppCoreGuidelines#i11-never-transfer-ownership-by-a-raw-pointer-t-or-reference-t](https://isocpp.github.io/CppCoreGuidelines/CppCoreGuidelines#i11-never-transfer-ownership-by-a-raw-pointer-t-or-reference-t)
1. [https://isocpp.github.io/CppCoreGuidelines/CppCoreGuidelines#f7-for-general-use-take-t-or-t-arguments-rather-than-smart-pointers](https://isocpp.github.io/CppCoreGuidelines/CppCoreGuidelines#f7-for-general-use-take-t-or-t-arguments-rather-than-smart-pointers)
1. [https://google.github.io/styleguide/cppguide.html#Ownership_and_Smart_Pointers](https://google.github.io/styleguide/cppguide.html#Ownership_and_Smart_Pointers)
