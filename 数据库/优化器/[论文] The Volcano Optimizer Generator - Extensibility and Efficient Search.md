#  Introduction

* First, this new optimizer generator had to be usable both in the Volcano project with the existing query execution software as well as in other projects as a stand-alone tool.

* Second, the new system had to be more efficient, both in optimization time and in memory consumption for the search.
* Third, it had to provide effective, efficient, and extensible support for physical properties such as sort order and compression status.
* Fourth, it had to permit use of heuristics and data model semantics to guide the search and to prune futile parts of the search space.
* Finally, it had to support flexible cost models that permit generating dynamic plans for incompletely specified queries.

**The Outside View of the Volcano Optimizer Generator**

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220322224101873.png" alt="image-20220322224101873" style="zoom: 50%;" />

# Design Principles

1. 查询处理都是基于关系代数；
2. 使用规则和模式 (patterns and rules) 来处理等价转换；
3. 不使用中间表示状态，直接将查询转换为计划，没有中间表示状态；(Third, the choices that the query optimizer can make to map a query into an optimal equivalent query evaluation plan are represented as algebraic equivalences in the Volcano optimizer generator's input. Other systems use multiple intermediate levels when transforming a query into a plan. For example, the cost-based optimizer component of the extensible relational Starburst database system uses an "expansion grammar" with multiple levels of "non-terminals" such as commutative binary join, non-commutative binary join, etc. )
4. 使用编译的方式而不是解释的方式；
5. 使用动态规划 (dynamic programming) 的搜索方式

# Optimizer Generator Input and Optimizer Operation

The user queries to be optimized by a generated optimizer are specified as an algebra expression (tree) of *logical operators*.

The output of the optimizer is a plan, which is an expression over the algebra of algorithms.

Optimization consists of mapping a logical algebra expression into the optimal equivalent physical algebra expression.

---

==**Transformation Rules**==:  The algebraic rules of expression equivalence, e.g., commutativity or associativity (交换律和结合律), are specified using transformation rules.

==**Implementation Rules**==: The possible mappings of **operators** to **algorithms** are specified using implementation rules.

> **Tips**:
>
> Logical -> Logical: JOIN(A,B) to JOIN(B,A) 
>
> Logical -> Physical:  JOIN(A,B) to HASH_JOIN(A,B)

> It is important that the rule language allow for complex mappings. For example, a join followed by a projection (without duplicate removal) should be implemented in a single procedure; therefore, it is possible to map multiple logical operators to a single physical operator. 

---

==**Logical Properties**==: Logical properties can be derived from the logical algebra expression and include schema, expected size, etc.

==**Physical Properties**==: Physical properties depend on algorithms, e.g., sort order, partitioning, etc.

> When optimizing a many-sorted algebra, the logical properties also include the type (or sort) of an intermediate result, which can be inspected by a rule's condition code to ensure that rules are only applied to expressions of the correct type. Logical properties are attached to equivalence classes - sets of equivalent logical expressions and plans - whereas physical properties are attached to specific plans and algorithm choices.

**Physical Property Vector**: The set of physical properties is summarized for each intermediate result in a physical property vector, which is defined by the optimizer implementor and treated as an abstract data type by the Volcano optimizer generator and its search engine.

---

==**Enforcers**==: There are some operators in the physical algebra that do not correspond to any operator in the logical algebra, for example sorting and decompression. ==The purpose of these operators is not to perform any logical data manipulation but to enforce physical properties in their outputs that are required for subsequent query processing algorithms==. We call these operators enforcers;

---

==**Applicability Function**==: Each optimization goal (and subgoal) is a pair of a logical expression and a physical property vector. In order to decide whether or not an algorithm or enforcer can be used to execute the root node of a logical expression, a generated optimizer matches the implementation rule, executes the condition code associated with the rule, and then invokes an applicability function that determines whether or not the algorithm or enforcer can deliver the logical expression with physical properties that satisfy the physical property vector.

The applicability functions also determine the physical property vectors that the algorithm's inputs must satisfy. For example, when optimizing a join expression whose result should be sorted on the join attribute, hybrid hash join does not qualify while merge-join qualifies with the requirement that its inputs be sorted.

There is also a provision to ensure that algorithms do not qualify redundantly, e.g., merge-join must not be considered as input to the sort in this example.

==**Cost Function**==: After the optimizer decides to explore using an algorithm or enforcer, it invokes the algorithm's cost function to estimate its cost.

# The Search Engine

In order to prevent redundant optimization effort by detecting redundant (i.e., multiple equivalent) derivations of the same logical expressions and plans during optimization, expression and plans are captured in a hash table of expressions and equivalence classes. 

---

The original invocation of the FindBestPlan procedure indicates the logical expression passed to the optimizer as the query to be optimized, physical properties as requested by the user (for example, sort order as in the ORDER BY clause of SQL), and a cost limit.

If the expression cannot be found in the hash table, or if the expression has been optimized before but not for the presently required physical properties, actual optimization is begun.

There are three sets of possible "moves" the optimizer can explore at any point. 

1. First, the expression can be transformed using a ==transformation rule==. 
2. Second, ==there might be some **algorithms** that can deliver the logical expression with the desired physical properties==, e.g., hybrid hash join for unsorted output and merge-join for join output sorted on the join attribute. 
3. Third, an ==enforcer== might be useful to permit additional algorithm choices, e.g., a sort operator to permit using hybrid hash join even if the final output is to be sorted.

---

==**Branch-and-Bound**==: The cost limit is used to improve the search algorithm using branch-and-bound pruning. Once a complete plan is known for a logical expression (the user query or some part of it) and a physical property vector, no other plan or partial plan with higher cost can be part of the optimal query evaluation plan. 

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220322231128905.png" alt="image-20220322231128905" style="zoom: 50%;" />