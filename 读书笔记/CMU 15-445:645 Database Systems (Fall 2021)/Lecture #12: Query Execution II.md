# Background

Previous discussions of query executions assumed that the queries executed with a single worker (i.e thread). However, in practice, queries are often executed in parallel with multiple workers.

Parallel execution provides a number of key benefits for DBMSs:

* Increased performance in throughput (more queries per second) and latency (less time per query).
* Increased ==responsiveness== and ==availability== from the perspective of external clients of the DBMS.
* Potentially lower *total cost of ownership* (==TCO==). This cost includes both the hardware procurement and software license, as well as the labor overhead of deploying the DBMS and the energy needed to run the machines.

There are two types of parallelism that DBMSs support: ==**inter-query parallelism**== and ==**intra-query parallelism**==.

# Parallel vs Distributed Databases

In both parallel and distributed systems, the database is spread out across multiple “resources” to improve parallelism. These resources may be computational (e.g., CPU cores, CPU sockets, GPUs, additional machines) or storage (e.g., disks, memory).

It is important to distinguish between parallel and distributed systems.

**Parallel DBMSs**:

* Resources are physically close to each other.
* Resources communicate over high-speed interconnect.
* Communication is assumed to be cheap and reliable.

**Distributed DBMSs**:

* Resources can be far from each other.
* Resources communicate using slow(er) interconnect.
* Communication cost and problems cannot be ignored.

Even though a database may be physically divided over multiple resources, it still appears as a single logical database instance to the application. Thus, a SQL query executed against a single-node DBMS should generate the same result on a parallel or distributed DBMS.

# Process Models

A DBMS process model defines how the system supports concurrent requests from a multi-user application/environment. The DBMS is comprised of more or more workers that are responsible for executing tasks on behalf of the client and returning the results. An application may send a large request or multiple requests at the same time that must be divided across different workers.

There are three different process models that a DBMS may adopt: process per worker, process pool, and thread per worker.

## Process per Worker

==Each worker is a separate **OS process**==.

* Relies on OS scheduler.
* Use shared-memory for global data structures.
* A process crash doesn’t take down entire system.

**Examples**: IBM DB2, Postgres, Oracle

![image-20220306222156311](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220306222156311.png)

An advantage of the process per worker approach is that a process crash doesn’t disrupt the whole system because each worker runs in the context of its own OS process.

This process model raises the issue of ==multiple workers on separate processes making numerous copies of the same page==. A solution to maximize memory usage is to use ==shared-memory== for global data structures so that they can be shared by workers running in different processes.

## Process Pool

A worker uses any free process from the pool.

* Still relies on OS scheduler and shared memory.
* Bad for CPU cache locality.

**Examples**: IBM DB2, Postgres (2015)

![image-20220306222452327](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220306222452327.png)

Like process per worker, the process pool also relies on the OS scheduler and shared memory.

A drawback to this approach is ==poor CPU cache locality== as the same processes are not guaranteed to be used between queries.

## Thread per Worker

Single process with ==multiple worker **threads**==.

* DBMS manages its own scheduling.
* May or may not use a dispatcher thread.
* Thread crash (may) kill the entire system.

Examples: IBM DB2, MSSQL, MySQL, Oracle (2014)

![image-20220306222639064](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220306222639064.png)

Using multi-threaded architecture provides certain advantages. 

* For one, there is ==less overhead per context switch==. 
* Additionally, a shared model does not have to be maintained. 

However, the thread per worker model does not necessarily imply that the DBMS supports intra-query parallelism.

## Scheduling
In conclusion, for each query plan, the DBMS has to decide where, when, and how to execute. Relevant questions include:

* How many tasks should it use?
* How many CPU cores should it use?
* What CPU core should the tasks execute on?
* Where should a task store its output?

When making decisions regarding query plans, the DBMS always knows more than the OS and should be prioritized as such.

#  Inter-Query Parallelism (多个 query 并行)

In inter-query parallelism, the DBMS ==executes **different** queries are concurrently==. Because multiple workers are running requests simultaneously, overall performance is improved. This ==increases throughput== and ==reduces latency==.

If the queries are read-only, then little coordination is required between queries. However, if multiple queries are updating the database concurrently, more complicated conflicts arise. These issues are discussed further in lecture 15.

#  Intra-Query parallelism (单个 query 内并行)

In intra-query parallelism, the DBMS ==executes the operations of a **single** query in parallel==. This decreases latency for long-running queries.

The organization of intra-query parallelism can be thought of in terms of a ==*producer/consumer* paradigm==. Each operator is a producer of data as well as a consumer of data from some operator running below it.

Parallel algorithms exist for every relational operator. The DBMS can either have multiple threads access centralized data structures or use partitioning to divide work up.

Within intra-query parallelism, there are three types of parallelism: ==intra-operator==, ==inter-operator==, and ==bushy==. These approaches are not mutually exclusive. It is the DBMS’ responsibility to combine these techniques in a way that optimizes performance on a given workload.

![image-20220306223349731](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220306223349731.png)

## Intra-Operator Parallelism (Horizontal)

In *intra-operator parallelism*, the query plan’s operators are decomposed into independent ==*fragments*== that perform the same function on different (disjoint) subsets of data.

The DBMS inserts an ==*exchange*== operator into the query plan to coalesce results from child operators. The exchange operator prevents the DBMS from executing operators above it in the plan until it receives all of the data from the children. An example of this is shown in Figure 4.

![image-20220306223956626](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220306223956626.png)

In general, there are three types of exchange operators:

* **Gather**: Combine the results from multiple workers into a single output stream. This is the most common type used in parallel DBMSs.
* **Repartition**: Reorganize multiple input streams across multiple output streams. This allows the DBMS take inputs that are partitioned one way and then redistribute them in another way.
* **Distribute**: Split a single input stream into multiple output streams.

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220306223852059.png" alt="image-20220306223852059" style="zoom:33%;" />

![image-20220306224045637](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220306224045637.png)

## Inter-Operator Parallelism (Vertical)

In *inter-operator parallelism*, the DBMS overlaps operators in order to pipeline data from one stage to the next without materialization. This is sometimes called ==*pipelined parallelism*==. See example in Figure 5.

This approach is widely used in *stream processing systems*, which are systems that continually execute a query over a stream of input tuples.

![image-20220306224309728](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220306224309728.png)

## Bushy Parallelism

Bushy parallelism is a hybrid of intra-operator and inter-operator parallelism where workers execute multiple operators from different segments of the query plan at the same time.

The DBMS still uses exchange operators to combine intermediate results from these segments. An example is shown in Figure 6.

![image-20220306224734146](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220306224734146.png)

#  I/O Parallelism

Using additional processes/threads to execute queries in parallel will not improve performance if the disk is always the main bottleneck. Therefore, it is important to be able to split a database across multiple storage devices.

To get around this, DBMSs use I/O parallelism to *split installation across multiple devices*. Two approaches to I/O parallelism are multi-disk parallelism and database partitioning.

## Multi-Disk Parallelism

In multi-disk parallelism, the OS/hardware is configured to store the DBMS’s files across multiple storage devices. This can be done through storage appliances or RAID configuration. All of the storage setup is transparent to the DBMS so workers cannot operate on different devices because the DBMS is unaware of the underlying parallelism.

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220306225046510.png" alt="image-20220306225046510" style="zoom:25%;" />

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220306225106274.png" alt="image-20220306225106274" style="zoom:25%;" />

## Database Partitioning

In database partitioning, the database is split up into disjoint subsets that can be assigned to discrete disks. Some DBMSs allow for specification of the disk location of each individual database. This is easy to do at the file-system level if the DBMS stores each database in a separate directory. The log file of changes made is usually shared.

The idea of logical partitioning is to split single logical table into disjoint physical segments that are stored/managed separately. Such partitioning is ideally transparent to the application. That is, the application should be able to access logical tables without caring how things are stored.

The two approaches to partitioning are vertical and horizontal partitioning.

In ==*vertical partitioning*==, a table’s attributes are stored in a separate location (like a column store). The tuple information must be stored in order to reconstruct the original record.

![image-20220306225332788](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220306225332788.png)

In ==*horizontal partitioning*==, the tuples of a table are divided into disjoint segments based on some partitioning keys. There are different ways to decide how to partition (e.g., hash, range, or predicate partitioning). The efficacy of each approach depends on the queries.

![image-20220306225350080](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220306225350080.png)