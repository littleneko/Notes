# Logical Query Optimization

Transform a logical plan into an ==equivalent logical plan== using ==pattern matching rules==.

The goal is to increase the likelihood of enumerating the optimal plan in the search.

==Cannot compare plans== because there is ==no cost model== but ==**can "direct" a transformation to a preferred side**==.

---

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220324233047994.png" alt="image-20220324233047994" style="zoom:33%;" />

## Split Conjunctive Predicates

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220324233125952.png" alt="image-20220324233125952" style="zoom:33%;" />

## Predicate Pushdown

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220324233146992.png" alt="image-20220324233146992" style="zoom:33%;" />

## Replace Cartesian Products with Joins

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220324233236090.png" alt="image-20220324233236090" style="zoom:33%;" />

## Projection Pushdown

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220324233319189.png" alt="image-20220324233319189" style="zoom:33%;" />

# Physical Query Optimization

Transform a query plan's logical operators into physical operators.

* Add more execution information
* Select indexes / access paths
* Choose operator implementations
* Choose when to materialize (i.e., temp tables).

This stage must support cost model estimates.

---

All the queries we have looked at so far have had the following properties:

* Equi/Inner Joins
* Simple join predicates that reference only two tables.
* No cross products

Real-world queries are much more complex:

* Outer Joins
* Semi-joins
* Anti-joins

## Reordering Limittations

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220324233714769.png" alt="image-20220324233714769" style="zoom:33%;" />

## Plan Enumeration

**Approach #1: Transformation**

* Modify some part of an existing query plan to transform it into an alternative plan that is equivalent.

**Approach #2: Generative**

* Assemble building blocks to generate a query plan.

## Dynamic Programming Optimizer

Model the query as a hypergraph and then incrementally expand to enumerate new plans.

Algorithm Overview:

* Iterate connected sub-graphs and incrementally add new edges to other nodes to complete query plan.
* Use rules to determine which nodes the traversal is allowed to visit and expand.

# Cascades Optimizer ⭐️

Object-oriented implementation of the Volcano query optimizer.

Supports simplistic expression re-writing through a direct mapping function rather than an exhaustive search.

* Optimization tasks as data structures.
* Rules to place property enforcers.
* Ordering of moves by promise.
* Predicates as logical/physical operators.

## Expressions

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220324234400314.png" alt="image-20220324234400314" style="zoom:33%;" />

## Groups

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220324234510172.png" alt="image-20220324234510172" style="zoom:33%;" />

## Multi Expression

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220324234541617.png" alt="image-20220324234541617" style="zoom:33%;" />

## Rules

A rule is a transformation of an expression to a logically equivalent expression.

* ==**Transformation Rule**==: Logical to Logical
* ==**Implementation Rule**==: Logical to Physical

Each rule is represented as a pair of attributes:

* ==**Pattern**==: Defines the structure of the logical expression that can be applied to the rule.
* ==**Substitute**==: Defines the structure of the result after applying the rule.

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220324234730736.png" alt="image-20220324234730736" style="zoom:33%;" />

## Memo Table

* Stores all previously explored alternatives in a compact graph structure / hash table.
* Equivalent operator trees and their corresponding plans are stored together in groups.
* Provides memoization, duplicate detection, and property + cost management.

---

**PRINCIPLE OF OPTIMALITY**

Every sub-plan of an optimal plan is itself optimal. 

This allows the optimizer to restrict the search space to a smaller set of expressions. (注：即 ==branch-and-bound== search)

* The optimizer never has to consider a plan containing sub-plan P1 that has a greater cost than equivalent plan P2 with the same physical properties.

---

1. 初始状态的 memo 如图所示，我们最终需要的结果是 [ABC] 三表 join cost 最小的执行计划，我们首先使用 Transformation Rule 得到 [ABC] 一个等价的 Logical Expression [AB] Join [C]，接着我们进行==深度优先搜索==。

   <img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220324235005992.png" alt="image-20220324235005992" style="zoom:33%;" />

2. 当搜索到最下层的时候，对 GET(A) 使用 Implementation Rule 生成 2 个 Physical Expression，然后找到 GET(A) cost 最小的 Physical Expression 是 SeqScan(A)，并记录到 hash table 中。

   <img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220324235206470.png" alt="image-20220324235206470" style="zoom:33%;" />

3. 同理找到 B 的最小 Physical Expression

   <img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220324235329510.png" alt="image-20220324235329510" style="zoom:33%;" />

4. 然后搜索回到 [AB]，通过 Transformation Rule 得到另一个等价的 Logical Expression [B] Join [A]，这时我们发现 hash table 中已经有 Get(A) 和 Get(B) 的最优 Physical Expression 了，所以没必要继续搜索了。

   <img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220324235451021.png" alt="image-20220324235451021" style="zoom:33%;" />

5. 然后对所有的 Logical Expression 应用 Implementation Rule 得到一些 Physical Expression，然后我们得到 const 最小的 Physical Expression 是 [A] SM-Join [B]，把它记录到 hash table 中。

   <img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220324235516499.png" alt="image-20220324235516499" style="zoom:33%;" />

6. 搜索继续回到最上层，使用同样的方法找到 [C] const 最小的 Physical Expression

   <img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220324235550573.png" alt="image-20220324235550573" style="zoom:33%;" />

7. 然后对 [ABC] 应用 Transformation Rule 得到更多的 Logical Expression。

   <img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220324235635149.png" alt="image-20220324235635149" style="zoom:33%;" />

> **Tips**:
>
> * 在后面搜索的过程中，如果发现 cost 已经大于第一个的结果，可以使用 branch-and-bound 规则进行剪枝
> * 在 Cascade 的论文中， Transformation Rule 和 Implementation Rule 是混合交替使用的，有一定的规则来决定顺序

## Search Termination

**Approach #1: Wall-clock Time**

* Stop after the optimizer runs for some length of time.

**Approach #2: Cost Threshold**

* Stop when the optimizer finds a plan that has a lower cost than some threshold.

**Approach #3: Transformation Exhaustion**

* Stop when there are no more ways to transform the target plan. Usually done per group.