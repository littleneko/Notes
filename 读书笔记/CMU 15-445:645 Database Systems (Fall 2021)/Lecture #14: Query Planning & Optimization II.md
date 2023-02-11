# Cost Estimations

DBMS’s use cost models to estimate the cost of executing a plan. These models evaluate equivalent plans for a query to help the DBMS select the most optimal one.

The cost of a query depends on several underlying metrics, including:

* **CPU**: small cost, but tough to estimate.
* **Disk I/O**: the number of block transfers.
* **Memory**: the amount of DRAM used.
* **Network**: the number of messages sent.

Exhaustive enumeration of all valid plans for a query is much too slow for an optimizer to perform. ==For joins alone, which are commutative and associative, there are $4^n$ different orderings of every n-way join==. Optimizers must limit their search space in order to work efficiently.

To approximate costs of queries, DBMS’s maintain internal *statistics* about tables, attributes, and indexes in their internal catalogs. Different systems maintain these statistics in different ways. Most systems attempt to avoid on-the-fly computation by maintaining an internal table of statistics. These internal tables may then be updated in the background.

For each relation $R$, the DBMS maintains the following information:

* $N_R$: Number of tuples in $R$
* $V (A, R)$: Number of distinct values of attribute $A$

With the information listed above, the optimizer can derive the ==*selection cardinality*== $SC(A, R)$ statistic. The selection cardinality is the average number of records with a value for an attribute $A$ given $\frac {N_R} {V(A, R)}$. ==Note that this assumes data uniformity== where every value has the same frequency as all
other values. This assumption is often incorrect, but it simplifies the optimization process.

## Selection Statistics

The selection cardinality can be used to determine the number of tuples that will be selected for a given input.

Equality predicates on unique keys are simple to estimate (see **Figure 1**). A more complex predicate is shown in **Figure 2**.

The *selectivity* (sel) of a predicate $P$ is the fraction of tuples that qualify. The formula used to compute selective depends on the type of predicate. Selectivity for complex predicates is hard to estimate accurately which can pose a problem for certain systems. An example of a selectivity computation is shown in **Figure 3**.

![image-20230209001058588](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20230209001058588.png)

![image-20230209001123418](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20230209001123418.png)

![image-20230209001141036](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20230209001141036.png)

==Observe that the selectivity of a predicate is equivalent to the probability of that predicate==. This allows probability rules to be applied in many selectivity computations. This is particularly useful when dealing with complex predicates. For example, ==if we assume that multiple predicates involved in a conjunction are *independent*, we can compute the total selectivity of the conjunction as the product of the selectivities of the individual predicates==.

### Equality Predicate

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20230209001446098.png" alt="image-20230209001446098" style="zoom: 25%;" />

### Range Predicate

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20230209001514536.png" alt="image-20230209001514536" style="zoom:25%;" />

### Negation Query

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20230209001544903.png" alt="image-20230209001544903" style="zoom:25%;" />

### Conjunction

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20230209001808591.png" alt="image-20230209001808591" style="zoom:25%;" />

### Disjunction

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20230209001838915.png" alt="image-20230209001838915" style="zoom:25%;" />

### Join

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20230209002209147.png" alt="image-20230209002209147" style="zoom:25%;" />

## Selectivity Computation Assumptions

In computing the selection cardinality of predicates, the following three assumptions are used.

* **Uniform Data**: The distribution of values (except for the heavy hitters) is the same.
* **Independent Predicates**: The predicates on attributes are independent.
* **Inclusion Principle**: The domain of join keys overlap such that each key in the inner relation will also exist in the outer table.

These assumptions are often not satisfied by real data. For example, correlated attributes break the assumption of independence of predicates.

# Histograms

Real data is often skewed and is tricky to make assumptions about. However, storing every single value of a data set is expensive. One way to reduce the amount of memory used by storing data in a *histogram* to group together values. An example of a graph with buckets is shown in **Figure 4**.

![image-20230209002405136](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20230209002405136.png)

Another approach is to use a *equi-depth* histogram that varies the width of buckets so that the total number of occurrences for each bucket is roughly the same. An example is shown in **Figure 5**.

![image-20230209002501740](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20230209002501740.png)

In place of histograms, some systems may use *sketches* to generate approximate statistics about a data set.

# Sampling

DBMS’s can use *sampling* to apply predicates to a smaller copy of the table with a similar distribution (see **Figure 6**). The DBMS updates the sample whenever the amount of changes to the underlying table exceeds some threshold (e.g., 10% of the tuples).

![image-20230209002716440](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20230209002716440.png)

# Plan Enumeration

After performing rule-based rewriting, the DBMS will enumerate different plans for the query and estimate their costs. It then chooses the best plan for the query after exhausting all plans or some timeout.

## Single-Relation Query Plans

For single-relation query plans, the biggest obstacle is choosing the best access method (i.e., sequential scan, binary search, index scan, etc.) Most new database systems just use heuristics, instead of a sophisticated cost model, to pick an access method.

For OLTP queries, this is especially easy because they are *sargable* (Search Argument Able), which means that there exists a best index that can be selected for the query. This can also be implemented with simple heuristics.

## Multi-Relation Query Plans

### Left-deep Join Trees
As the number of joins increases, the number of alternative plans grows rapidly. To deal with this, we need to restrict the search space. **IBM System R** made the fundamental decision to only consider ==left-deep join trees== (see **Figure 7**). This is because left-deep join trees are ==better suited for the pipeline model== since the the DBMS does not need to materialize the outputs of the join operators. If the DBMS’s optimizer only considers left-deep trees, then it will ==reduce the amount of memory== that the search processes uses and potentially ==reduce the search time==. Most modern DBMSs do not make this restriction during optimization.

![image-20230209003100121](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20230209003100121.png)

### Dynamic programming

==*Dynamic programming*== can be used to reduce the number of cost estimations.

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/021200101805_01.png" alt="021200101805_01" style="zoom: 15%;" />


### Candidate Plans

To make query plans, the DBMS must first enumerate the orderings, then the plans for each operator, followed by the access paths for each table. See **Figure 8** for an example. 

![image-20230209003329497](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20230209003329497.png)

### Postgres Optimizer

略