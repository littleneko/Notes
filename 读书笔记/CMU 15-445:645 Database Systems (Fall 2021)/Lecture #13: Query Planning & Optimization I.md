# Overview

Because SQL is declarative, the query only tells the DBMS what to compute, but not how to compute it. Thus, the DBMS needs to translate a SQL statement into an executable query plan. But there are different ways to execute each operator in a query plan (e.g., join algorithms) and there will be differences in performance among these plans. The job of the DBMS’s optimizer is to pick an optimal plan for any given query.

There are two high-level strategies for query optimization.

==**Heuristics / Rules**==

* Rewrite the query to remove stupid / inefficient things.

* These techniques may need to examine catalog, but they do not need to examine data.

==**Cost-based Search**==

* Use a model to estimate the cost of executing a plan.
* Evaluate multiple equivalent plans for a query and pick the one with the lowest cost.

![image-20220307222735524](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220307222735524.png)

## Logical vs. Physical Plans

The optimizer generates a mapping of a *logical algebra expression* to the optimal equivalent physical algebra expression. The logical plan is roughly equivalent to the relational algebra expressions in the query.

*Physical operators* define a specific execution strategy using an access path for the different operators in the query plan. Physical plans may depend on the physical format of the data that is processed (i.e. sorting, compression).

There does not always exist a one-to-one mapping from logical to physical plans.

# Relational Algebra Equivalence

Much of query optimization relies on the underlying concept that the high level properties of relational algebra are preserved across equivalent expressions. ==Two relational algebra expressions are *equivalent* if they generate the same set of tuples==.

This technique of transforming the underlying relational algebra representation of a logical plan is known as ==*query rewriting*==.

## Predicate Pushdown

One example of relational algebra equivalence is *predicate pushdown*, in which a predicate is applied in a different position of the sequence to avoid unnecessary work. Figure 2 shows an example of predicate pushdown.

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220307223951065.png" alt="image-20220307223951065" style="zoom: 33%;" />

![image-20220307223140320](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220307223140320.png)

## Other

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220307223427694.png" alt="image-20220307223427694" style="zoom: 33%;" />

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220307223502178.png" alt="image-20220307223502178" style="zoom:33%;" />

# Logical Query Optimization

Transform a logical plan into an equivalent logical plan using pattern matching rules. 

==The goal is to increase the **likelihood** of **enumerating** the optimal plan in the search==.

Cannot compare plans because there is no cost model but can "direct" a transformation to a preferred side.

Some selection optimizations include:

* ==Perform filters as early as possible (**predicate pushdown**)==.
* ==Reorder predicates so that the DBMS applies the most selective one first==.
* ==Breakup a complex predicate and pushing it down (**split conjunctive predicates**)==.

## Predicate Pushdown ⭐️

An example of predicate pushdown is shown in Figure 2.

## Projection Pushdown ⭐️

Some projection optimizations include:

* Perform projections as early as possible to create smaller tuples and reduce intermediate results (==projection pushdown==).
* Project out all attributes except the ones requested or requires. 

An example of projection pushdown in shown in Figure 3.

![image-20220307224939150](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220307224939688.png)

##  Remove Impossible or Unnecessary Predicates

Another optimization that a DBMS can use is to remove impossible or unnecessary predicates. In this optimization, the DBMS elides evaluation of predicates whose result does not change per tuple in a table. Bypassing these predicates reduces computation cost. Figure 4 shows two examples of unnecessary predicates.

![image-20220307231009628](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220307231009628.png)

## Merge Predicates

![image-20220307231115274](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220307231115274.png)

## Eliminate Unnecessary Joins ⭐️

The ordering of JOIN operations is a key determinant of query performance. Exhaustive enumeration of all possible join orders is inefficient, so join-ordering optimization requires a cost model. However, we can still eliminate unnecessary joins with a heuristic approach to optimization. An example of join elimination is shown in Figure 6.

![image-20220307231237429](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220307231237429.png)

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220307231521266.png" alt="image-20220307231521266" style="zoom:33%;" />

## Nested Sub-Queries ⭐️

The DBMS can also optimize nested sub-queries without referencing a cost model. There are two different approaches to this type of optimization:

### Rewrite

Re-write the query by ==de-correlating== and / or ==flattening== it. An example of this is shown in Figure 7.

![image-20220307230711328](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220307230711328.png)

### Decompose

![image-20220307230824383](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220307230824383.png)

## Example ⭐️

A example with ==Split Conjunctive Predicates==, ==Predicate Pushdown==, ==Replace Cartesian Products with Joins== and ==Projection Pushdown==.

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220307225849131.png" alt="image-20220307225849131" style="zoom: 33%;" />

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220307225916186.png" alt="image-20220307225916186" style="zoom:33%;" />

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220307225940757.png" alt="image-20220307225940757" style="zoom:33%;" />

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220307230008346.png" alt="image-20220307230008346" style="zoom:33%;" />

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220307230054402.png" alt="image-20220307230054402" style="zoom:33%;" />