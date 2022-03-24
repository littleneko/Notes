# Introduction

这篇 Paper 要解决的问题就是在用户在不知道数据库具体的实现细节的情况下，数据库的优化器如何讲用户的 SQL 转化为尽可能高效的具体的查询数据的方式。

In System R a user need not know how the tuples are physically stored and what access paths are available (e.g. which columns have indexes). SQL statements do not require the user to specify anything about the access path to be used for tuple retrieval. Nor does a user specify in what order joins are to be performed. The System R optimizer chooses both join order and an access path for each table in the SQL statement. Of the many possible choices, the optimizer chooses the one which minimizes “total access cost” for performing the entire statement.

# The Research Storage System

The Research Storage System (==**RSS**==) 是 System R 中负责存储的子系统，它负责维护 relations 的物理存储、这些 Relations 的 access paths、锁、日志和恢复， 它提供一个面向 tuple 的接口（==**RSI**==）给用户访问。

Relations 在 RSS 中以行存的方式存储（a collection of tuples whose columns are physically contiguous），存在 4K 大小的 page 里，tuple 不会跨 page 存储。多个 pages 组成 segment，一个 segment 可能会包含一个或多个 Relations，但是一个 Relations 只会存储在一个 Segment 中。

访问 Relations 的主要方法是 RSS scan，即通过 OPEN、NEXT、CLOSE 命令访问。有两种方式访问，一种是顺序扫描（segment scan），另一种是索引扫描（index scan）。

两种访问方式都可以携带一系列可以直接作用到 tuple 上而不需要返回到 RSI 调用者处理的（==which are applied to a tuple before it is returned to the RSI caller==）谓词（predicates），我们称之为 search arguments (or ==**SARGS**==)，==sargable predicate== 就是一个例子。

> **sargable predicate**: search arguable predicate，表示在 index 做查找时可以顺带计算的过滤条件，其形态为 columns op const，columns 是在 index 上的索引列，这个概念广为使用，在 MySQL 的 condition 优化中很常见。

# Costs for single relation access paths

这里先讨论的是在一个 relation 上面的优化，也就是一个 table 上面的。这里使用下面这个基本的公式来计算一种 access pathde 成本：

```
COST = PAGE FETCHES + W * (RSI CALLS)
```

COST 主要是两个部分组成，PAGE FETCHES 代表了 I/O 的成本，RSI CALLS (storage system interface (RSI)) 代表了 CPU 的成本，W 则是一个比例因子。具体来说，RSI CALLS 代表了预测的从 RSS 返回的元组的数量。在 System R 中，大部分的 CPU 花在 RSS 中，因此 RSI Caller 是一个很好的估计 CPU 成本的方法。 

System R 会维持下面的一些统计信息：

For each relation T

* **NCARD(T)**: the cardinality of relation T. (T 中元组的基数)
* **TCARD(T)**: the number of pages in the segment that hold tuples of relation T. (segment 中的 page 的数量)
* **P(T)**: the fraction of data pages in the segment that hold tuples of relation T.   `P(T) = TCARD(T) / (no. of non-empty pages in the segment)`.  

For each index I on relation T

* **ICARD(I)**: number of distinct keys in index I. (不同 key 的数量)
* **NINDX(I)**: the number of pages in index I. (这个索引使用的 pages 的数量)

一个查询返回的元组的数量与查询中的 where 中的断言有很大的关系，在这个 where 的谓词中，每一个具体的谓词会被赋予一个选择因子 F（==**selectivity factor**==），使用这个因子大概代表会满足这个谓词的元组占所有元组的比例。这样，这里的重点之一就是为了这些因子的估计，这里使用了启发式和基于统计信息的方法：

```
column = value
  F = 1 / ICARD(column index) if there is an index on column. 
  This assumes an even distribution of tuples among the index key values. F = 1/10 otherwise

column1 = column2
  F = 1/MAX(ICARD(column1 index), ICARD(column2 index)) if there are indexes on both column1 and column2. 
  This assumes that each key value in the index with the smaller cardinality has a matching value in the other index.
  F = 1/ICARD(column-i index) if there is only an index on column-i 
  F = 1/10 otherwise
  
column > value (or any other open-ended comparison)
  F = (high key value - value) / (high key value - low key value)
  Linear interpolation of the value within the range of key values yields F if the column is an arithmetic type and value is known at access path selection time.
  F = 1/3 otherwise (i.e. column not arithmetic)
  There is no significance to this number, other than the fact that it is less selec- tive than the guesses for equal predicates for which there are no indexes, and that it is less than 1/2. We hypothesize that few queries use predicates that are satis- fied by more than half the tuples.
  
column BETWEEN value1 AND value2
  F = (value2 - value1) / (high key value - low key value)
  A ratio of the BETWEEN value range to the entire key value range is used as the selectivity factor if column is arithmetic and both value1 and value2 are known at access path selection.
  F = 1/4 otherwise
  Again there is no significance to this choice except that it is between the default selectivity factors for an equal predicate and a range predicate.
  
column IN (list of values)
   F = (number of items in list) * (selectivity factor for column = value) This is allowed to be no more than 1/2.
   
columnA IN subquery
  F = (expected cardinality of the subquery result) / (product of the cardinalities of all the relations in the subquery’s FROM-list).
  The computation of query cardinality will be discussed below. This formula is derived by the following argument: Consider the simplest case, where subquery is of the form “SELECT columnB FROM relationC ...”. Assume that the set of all columnB values in relationC contains the set of all columnA values. If all the tuples of relationC are selected by the subquery, then the predicate is always TRUE and F = 1. If the tuples of the subquery are restricted by a selectivity factor F’, then assume that the set of unique values in the subquery result that match columnA values is proportionately restricted, i.e. the selectivity factor for the predicate should be F’. F’ is the product of all the sub- query’s selectivity factors, namely (subquery cardinality) / (cardinality of all pos- sible subquery answers). With a little optimism, we can extend this reasoning to include subqueries which are joins and subqueries in which columnB is replaced by an arithmetic expression involving column names. This leads to the formula given above.
  
(pred expression1) OR (pred expression2)
  F = F(pred1) + F(pred2) - F(pred1) * F(pred2)
  
(pred1) AND (pred2)
   F = F(pred1) * F(pred2)
  Note that this assumes that column values are independent.
  
NOT pred
F = 1 - F(pred)
```

对于 single relation 的 cost 计算方法如下：

* Unique index matching an equal predicate: `1+1+W`
* Clustered index I matching one or more boolean factors: `F(preds) * (NINDX(I) + TCARD) + W * RSICARD`
* Non-clustered index I matching one or more boolean factors: `F(preds) * (NINDX(I) + NCARD) + W * RSICARD or F(preds) * (NINDX(I) + TCARD) + W * RSICARD` if this number fits in the System R buffer
* Clustered index I not matching any boolean factors: `(NINDX(I) + TCARD) + W * RSICARD`
* Non-clustered index I not matching any boolean factors: `(NINDX(I) + NCARD) + W * RSICARD` or `(NINDX(I) + TCARD) + W * RSICARD` if this number fits in the System R buffer
* Segment scan: `TCARD/P + W * RSICARD`

对于 clustered indexes 来说，我们认为 page 在 buffer 中存活的时间足够长，可以遍历完所有 tuple（注：因此用 TCARD）；对于 non-clustered indexes 来说，我们认为每次读一条数据都要重新加载一次 page 到 buffer（注：因此用 NCARD）。

> We assume for clustered indexes that a page remains in the buffer long enough for every tuple to be retrieved from it. For non-clustered indexes, it is assumed that for those relations not fitting in the buffer, the relation is sufficiently large with respect to the buffer size that a page fetch is required for every tuple retrieval.

---

**关于 interesting order**：

Choosing an optimal access path for a single relation consists of using these selectivity factors in formulas together with the statistics on available access
paths. Before this process is described, a definition is needed. Using an index access path or sorting tuples produces tuples in the index value or sort key order. We say that a tuple order is an ==*interesting order*== if that order is one specified by the query block’s GROUP BY or ORDER BY clauses.

If there are GROUP BY or ORDER BY clauses, then the cost for producing that interesting ordering must be compared to the cost of the cheapest unordered path plus the cost of sorting QCARD tuples into the proper order. 

# Access path selection for joins

Paper 中先介绍了 2-way join 的方法，从而衍生出 n-way join 实际上就是多个 2-way join 的组合。

However, it should be emphasized that the first 2-way join does not have to be completed before the second 2-way join is started.

It should be noted that although the cardinality of the join of n relations is the same regardless of join order, the cost of joining in different orders can be substantially different.

Join 的优化两个重要的的问题就是

1. 选择怎么样的 join 算法， Paper 中讲了 nested-loop based joins 和 merging-scan based joins，当然现在 hash join 也是一个很常用的方法。

   > **Tips**:
   >
   > 关于 join 中的 outer 和 inner，最简单的理解方式就是 nested loop join 和 sort merg join 中内外两个循环
   >
   > ```
   > for r1 in outter:
   >   	for r2 in inner:
   >     		merge r1 x r2
   > ```

2. 另外一个更加复杂的问题就是如何选择 join 的顺序了，为了减少考虑的 join 顺序，也使用了一些启发式（heuristic）的方法

A heuristic is used to reduce the join order permutations which are considered. When possible, the search is reduced by consideration only of join orders which have join predicates relating the inner relation to the other relations already participating in the join. This means that in joining relations t1,t2,...,tn only those orderings til,ti2,...,tin are examined in which for all j (j=2,...,n) either

(1) tij has at least one join predicate with some relation tik, where k < j, or

(2) for all k > j, tik has no join predicate with til,tit,...,or ti(j-1).

This means that all joins requiring Cartesian products are performed as late in the join sequence as possible. For example, if Tl,T2,T3 are the three relations in a query block’s FROM list, and there are join predicates between Tl and T2 and between T2 and T3 on different columns than the Tl-T2 join, then the following permutations are not considered:

* T1 - T3 - T2
* T3 - T1 - T2

## Computation of costs

Let *C-outer(path1)* be the cost of scanning the outer relation via path1, and *N* be ==the cardinality of the outer relation tuples which satisfy the applicable predicates==. *N* is computed by:

```
N = (product of the cardinalities of all relations T of the join so far) * (product of the selectivity factors of all applicable predicates).
```

Let *C-inner(path2)* be the cost of scanning the inner relation, applying all applicable predicates. Note that in the merge scan join this means ==scanning the contiguous group of the inner relation which corresponds to one join column value in the outer relation==.

Then the cost of a nested loop join is

```
C-nested-loop-join(pathl,path2)= C-outer(path1) + N * C-inner(path2)
```

The cost of a merge scan join can be broken up into ==the cost of actually doing the merge== plus ==the cost of sorting the outer or inner relations==, if required. The cost of doing the merge is

```
C-merge(pathl,path2)= C-outer(path1) + N * C-inner(path2)
```

For the case where the inner relation is sorted into a temporary relation none of the single relation access path formulas in section 4 apply. In this case the inner scan is like a segment scan except that the merging scans method makes use of the fact that the inner relation is sorted so that it is not necessary to scan the entire inner relation looking for a match. For this case we use the following formula for the cost of the inner scan.
```
C-inner(sorted list) = TEMPPAGES/N + W*RSICARD
```

where TEMPPAGES is the number of pages required to hold the inner relation. This formula assumes that ==during the merge each page of the inner relation is fetched once==.

---

**nested loop join 和 merge scan join 的 cost 计算公式相同**？

It is interesting to observe that the cost formula for nested loop joins and the cost formula for merging scans are essentially the same. The reason that merging scans is sometimes better than nested loops is that the cost of the inner scan may be much less. After sorting, the inner relation is clustered on the join column which tends to minimize the number of pages fetched, and it is not necessary to scan the entire inner relation (looking for a match) for each tuple of the outer relation.

> 实际上 C-inner(path2) 并不相等，sort merge join 更小

The cost of sorting a relation, *C-sort(path)*, includes the cost of retrieving the data using the specified access path, sorting the data, which may involve several passes, and putting the results into a temporary list.

## Example of tree

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220322003304511.png" alt="image-20220322003304511" style="zoom: 50%;" />

对于 single relation 的 access path 如图 2，在这个例子中，我们有如下假设：

* 对于 EMP 表来说，扫描 EMP.JOB 索引是花费最小的，因此剪枝掉 EMP segment scan 的 access path
* 对于 DEPT 表来说，扫描 DEPT.DNO 索引是花费最小的，因此剪枝掉 DEPT segment scan 的 access path
* 对于 JOB 表来说，segment scan 花费是最小的，因此保留所有 access path

> **Tips**:
>
> 为什么 JOB 中需要保留 JOB.JOB 的 access path？因为该 access patch 可以提供 sort order，后续结合 sort merge join 可能得到最小的 cost。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220322003329748.png" alt="image-20220322003329748" style="zoom: 50%;" />

把上面的 access path 保存在 search tree 中的结果如图 3。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220322004213030.png" alt="image-20220322004213030" style="zoom: 50%;" />

接下来我们构建 2 表 join 的 search tree，首先我们使用 nested loop join，有如下假设：

* EMP-JOB 花费最小的 path 是使用 JOB.JOB 索引，因此只保留 index JOB.JOB 的 path，剪枝掉 JOB seg scan 的 path
* EMP-DEPT 和 DEPT-EMP 中花费最小的 path 是使用 DEPT.DNO 索引

![image-20220322004639142](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220322004639142.png)

接下来，我们构建使用 merge scan join 的 search tree：

There is a scan on the EMP relation in DNO order, so it is possible to use this scan and the DNO scan on the DEPT relation to do a merging scans join, without any sorting.

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220322005306284.png" alt="image-20220322005306284" style="zoom:50%;" />

最终，我们构建出一个完整的 search tree

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220322005521926.png" alt="image-20220322005521926" style="zoom:50%;" />