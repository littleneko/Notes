# Query Plan

The DBMS converts a SQL statement into a query plan. Operators in the query plan are arranged in a tree. Data flows from the leaves of this tree towards the root. The output of the root node in the tree is the result of the query. Typically operators are binary (1–2 children). The same query plan can be executed in multiple ways.

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220306183700550.png" alt="image-20220306183700550" style="zoom: 25%;" />

# Processing Models

A DBMS *processing model* defines how the system executes a query plan. It specifies things like the direction in which the query plan is evaluated and what kind of data is passed between operators along the way. There are different models of processing models that have various trade-offs for different workloads.

These models can also be implemented to invoke the operators either from **top-to-bottom** or from **bottom-to-top**. Although the top-to-bottom approach is much more common, the bottom-to-top approach can allow for tighter control of caches/registers in pipelines.

The three execution models that we consider are:

* Iterator Model
* Materialization Model
* Vectorized / Batch Model

## Iterator Model (Volcano) ⭐️

Each query plan operator implements a *Next()* function.

* On each invocation, the operator returns either a ==single tuple== or a ==null marker== if there are no more tuples.
* The operator implements a loop that calls *Next()* on its children to retrieve their tuples and then process them.

Also called ==**Volcano**== or **Pipeline** Model.

The iterator model allows for pipelining where the DBMS can process a tuple through as many operators as possible before having to retrieve the next tuple. The series of tasks performed for a given tuple in the query plan is called a ==pipeline==.

Some operators will block until children emit all of their tuples. Examples of such operators include joins, subqueries, and ordering (ORDER BY). Such operators are known as pipeline breakers.

Output control works easily with this approach (LIMIT) because an operator can stop invoking Next on its child (or children) operator(s) once it has all the tuples that it requires.

![image-20220306184442581](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220306184442581.png)

## Materialization Model ⭐️

Each operator processes its input ==all at once== and then emits its output all at once.

* The operator "materializes" its output as a single result.
* The DBMS can push down hints (e.g., LIMIT) to avoid scanning too many tuples.
* Can send either a materialized row or a single column. The output can be either whole tuples (NSM) or subsets of columns (DSM).

![image-20220306184912536](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220306184912536.png)

Better for OLTP workloads because queries only access a small number of tuples at a time.

* Lower execution / coordination overhead.
* Fewer function calls.

Not good for OLAP queries with large intermediate results.

## Vectorization Model ⭐️

Like the Iterator Model where each operator implements a Next() function, but...

Each operator emits ==a batch of tuples== instead of a single tuple.

* The operator's internal loop processes multiple tuples at a time.
* The size of the batch can vary based on hardware or query properties.

![image-20220306185140457](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220306185140457.png)

The vectorization model approach is ideal for OLAP queries that have to scan a large number of tuples because there are fewer invocations of the Next function.

The vectorization model allows operators to more easily use vectorized (**SIMD**) instructions to process batches of tuples.

## Processing Direction

* **Approach #1: Top-to-Bottom**
  – Start with the root and “pull” data from children to parents
  – Tuples are always passed with function calls
* **Approach #2: Bottom-to-Top**
  – Start with leaf nodes and “push” data from children to parents
  – Allows for tighter control of caches / registers in operator pipelines

# Access Methods

An access method is how the DBMS accesses the data stored in a table. In general, there are two approaches to access models; data is either read from a table or from an index with a sequential scan.

## Sequential Scan

A sequential table scan is almost always the least efficient method by which a DBMS may execute a query. There are a number of optimizations available to help make sequential scans faster:

* **Prefetching**: Fetch the next few pages in advance so that the DBMS does not have to block on storage I/O when accessing each page.
* **Buffer Pool Bypass**: The scan operator stores pages that it fetches from disk in its local memory instead of the buffer pool in order to avoid sequential flooding.
* **Parallelization**: Execute the scan using multiple threads/processes in parallel.
* **Zone Map**: ==Pre-compute aggregations== for each tuple attribute in a page. The DBMS can then decide whether it needs to access a page by checking its Zone Map first. The Zone Maps for each page are stored in separate pages and there are typically multiple entries in each Zone Map page. Thus, it is
  possible to reduce the total number of pages examined in a sequential scan. See figure Figure 4 for an example of a Zone Map.
* **Late Materialization**: DSM DBMSs can delay stitching together tuples until the upper parts of the query plan. This allows each operator to pass the minimal amount of information needed to the next operator (e.g. record ID, offset to record in column). ==This is only useful in column-store systems==.
* **Heap Clustering**: Tuples are stored in the heap pages using an order specified by a clustering index.

![image-20220306185540010](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220306185540010.png)

## Index Scan

In an index scan, the DBMS picks an index to find the tuples that a query needs. There are many factors involved in the DBMSs’ index selection process, including:

* What attributes the index contains
* What attributes the query references
* The attribute’s value domains
* Predicate composition
* Whether the index has unique or non-unique keys

![image-20220306185807527](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220306185807527.png)

More advanced DBMSs support ==multi-index scans==. When using multiple indexes for a query, the DBMS computes sets of record IDs using each matching index, combines these sets based on the query’s predicates, and retrieves the records and apply any predicates that may remain. The DBMS can use bitmaps, hash tables, or Bloom filters to compute record IDs through set intersection.

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220306185906442.png" alt="image-20220306185906442" style="zoom: 25%;" />

# Modification Queries

Operators that modify the database (INSERT, UPDATE, DELETE) are responsible for checking constraints and updating indexes.

**UPDATE/DELETE**:

* Child operators pass Record IDs for target tuples.
* ==Must keep track of previously seen tuples==.

**INSERT**:

* Choice #1: Materialize tuples inside of the operator.
* Choice #2: Operator inserts any tuple passed in from child operators.

## Halloween Problem

The Halloween Problem is an anomaly in which an update operation changes the physical location of a tuple, causing a scan operator to visit the tuple multiple times. This can occur on clustered tables or index scans.

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220306190852248.png" alt="image-20220306190852248" style="zoom:25%;" />

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220306190909431.png" alt="image-20220306190909431" style="zoom:25%;" />

# Expression Evaluation

The DBMS represents a WHERE clause as an expression tree (see Figure 6 for an example). The nodes in the tree represent different expression types.

Some examples of expression types that can be stored in tree nodes:

* Comparisons (=, <, >, !=)
* Conjunction (AND), Disjunction (OR)
* Arithmetic Operators (+, -, *, /, %)
* Constant and Parameter Values
* Tuple Attribute References

![image-20220306191134745](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220306191134745.png)

To evaluate an expression tree at runtime, the DBMS maintains a context handle that contains metadata for the execution, such as the ==current tuple==, ==the parameters==, and ==the table schema==. The DBMS then walks the tree to evaluate its operators and produce a result.

Evaluating predicates in this manner is slow because the DBMS must traverse the entire tree and determine the correct action to take for each operator. A better approach is to just evaluate the expression directly.