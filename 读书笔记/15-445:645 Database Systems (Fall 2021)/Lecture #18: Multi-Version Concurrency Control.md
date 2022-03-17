# Multi-Version Concurrency Control

Multi-Version Concurrency Control (MVCC) is a larger concept than just a concurrency control protocol. It involves all aspects of the DBMS’s design and implementation. MVCC is the most widely used scheme in DBMSs. It is now used in almost every new DBMS implemented in last 10 years. Even some systems (e.g., NoSQL) that do not support multi-statement transactions use it.

With MVCC, the DBMS maintains multiple *physical* versions of a single *logical* object in the database. When a transaction writes to an object, the DBMS creates a new version of that object. When a transaction reads an object, it reads the newest version that existed when the transaction started.

The fundamental concept/benefit of MVCC is that ==writers do not block writers== and ==readers do not block readers==. This means that one transaction can modify an object while other transactions read old versions.

One advantage of using MVCC is that ==read-only transactions can read a consistent snapshot of the database without using locks of any kind==. Additionally, multi-versioned DBMSs can easily support ==*time-travel queries*==, which are queries based on the state of the database at some other point in time (e.g. performing a query on the database as it was 3 hours ago).

## Example #1

> **Tips**: 
>
> * Transaction ID (or timestamp) 在事务开始的时候就分配。
> * Tuple 中的 Begin 和 End timestamp 用来判断这条数据可见（visible）的 transaction timestamp 范围。
> * A~0~ 的 Begin 为 0 表示这条数据是由 ID (or timestamp) 为 0 的 Transaction 创建的，==End 为 **NULL** 表示 A~0~ 是这条数据的最新版本==。
> * 下面所有的讨论默认都是基于 ==**Snapshot Isolation**== 的。

T~1~ 的 timestamp 在 A~0~ 的 Begin 和 End 之间，因此 T~1~ 能读 A~0~

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313155542875.png" alt="image-20220313155542875" style="zoom:25%;" />

T~2~ 写了 A 产生一个新版本 A~1~，A~1~ 的 Begin timestamp 是 2，==同时修改 A~0~ 的 End timestamp 为 2，表示 A~0~ 只能被 timestamp 在 [0, 2) 之间的 Transaction 可见；所有 timestamp 大于等于 2 的事务都不能读到 A~0~，只能读到 A~0~ 之后的版本==。（注：还需要判断 T~2~ 是否 Commited）

> Q1：在 T~2~ Commit 之前，其他事务能否读到 A~1~，如果能读到，那不就是 Read Uncommitted 了吗？
>
> A1: Read Uncommitted 隔离级别以上不能读到，使用 Txn Status Table 判断 T~2~ 是否 Committed，如果没有 Committed 就不能读 A~1~ 这个版本。
>
> Q2: 为什么不在 Commit 的时候再修改 A~0~ 的 End timestamp 为 2？
>
> A2: // TODO

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313155618328.png" alt="image-20220313155618328" style="zoom:25%;" />

同时，我们需要有一个地方单独保存当前活跃事务列表，目的是==为了保证其他事务不能读到还未 Commit 的数据 A~1~==。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313184250836.png" alt="image-20220313184250836" style="zoom:25%;" />

T~1~ 在 T~2~ 写了 A 之后仍然只能读到 A~0~ 版本，因为 A~0~ Begin <= T~1~ < A~0~ End。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313155704492.png" alt="image-20220313155704492" style="zoom:25%;" />

## Example #2

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313155922158.png" alt="image-20220313155922158" style="zoom:25%;" />

尽管 T~2~ > T~1~，并且 T~2~ 不在 A~0~ 的 Begin 和 End timestap 之间，T~2~ 仍然只能读到 A~0~，因为 T~1~ 还未 Commit。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313160007018.png" alt="image-20220313160007018" style="zoom:25%;" />

T~2~ 不能写 A，因为 T~1~ 写了 A 并且还未提交，存在 Write-Write 冲突，T~2~ 必须等到 T~1~ Commit 之后才能继续执行。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313160040441.png" alt="image-20220313160040441" style="zoom:25%;" />

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313160102388.png" alt="image-20220313160102388" style="zoom:25%;" />

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313160144592.png" alt="image-20220313160144592" style="zoom:25%;" />

> **Tips**:
>
> * 这个例子中的调度并不是 **serializable** 的，原因是最后结果并不等价于任何一个串行化调度，这个例子是符合 **Snapshot Isolation** 的。
> * 如果是在 **serializable** 隔离级别下，上面的 T~2~ 将不会 Commit 成功。
> * 这个例子实际上是有==**丢失更新**==（**Lost Update**）发生的，实际上很多快照隔离的数据库都会做冲突检测，避免更新丢失的情况，因此一般当人们讲 “快照隔离” 时都是默认避免了更新丢失的情况的。

---

There are four important MVCC design decisions:

1. Concurrency Control Protocol
2. Version Storage
3. Garbage Collection
4. Index Management

The choice of concurrency protocol is between the approaches discussed in previous lectures (two-phase locking, timestamp ordering, optimistic concurrency control).

# Version Storage

This how the DBMS will store the different physical versions of a logical object and how transactions find the newest version visible to them.

The DBMS uses the tuple’s pointer field to create a **version chain** per logical tuple, which is essentially a linked list of versions sorted by timestamp. This allows the DBMS to find the version that is visible to a particular transaction at runtime. Indexes always point to the “head” of the chain, which is either the newest or oldest version depending on implementation. A thread traverses chain until it finds the correct version. Different storage schemes determine where/what to store for each version.

## Approach #1: Append-Only Storage

All physical versions of a logical tuple are stored in the same table space. Versions are mixed together in the table and each update just appends a new version of the tuple into the table and updates the version chain. The chain can either be sorted *oldest-to-newest* (**O2N**) which requires chain traversal on look-ups, or *newest-to-oldest* (**N2O**), which requires updating index pointers for every new version.

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313160809182.png" alt="image-20220313160809182" style="zoom:25%;" />

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313160825532.png" alt="image-20220313160825532" style="zoom:25%;" />

> **Tips**:
>
> 上图展示了 update A 产生一个新的版本 A~2~ 同时修改 pointer 的过程。

---

Version Chain Ordering

**Approach #1: Oldest-to-Newest (O2N)**:

* Append new version to end of the chain.
* Must traverse chain on look-ups.

**Approach #2: Newest-to-Oldest (N2O)**:

* Must update index pointers for every new version.
* Do not have to traverse chain on look-ups.

## Approach #2: Time-Travel Storage

The DBMS maintains a **separate** table called the **time-travel table** which stores older versions of tuples. On every update, the DBMS copies the old version of the tuple to the time-travel table and overwrites the tuple in the main table with the new data. Pointers of tuples in the main table point to past versions in the time-travel table.

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313161248377.png" alt="image-20220313161248377" style="zoom:25%;" />

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313161323180.png" alt="image-20220313161323180" style="zoom:25%;" />

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313161405917.png" alt="image-20220313161405917" style="zoom:25%;" />

## Approach #3: Delta Storage

Like time-travel storage, but instead of the entire past tuples, the DBMS only stores the deltas, or changes between tuples in what is known as the delta storage segment. Transactions can then recreate older versions by iterating through the deltas. This results in faster writes than time-travel storage but slower reads.

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313161449540.png" alt="image-20220313161449540" style="zoom:25%;" />

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313161736092.png" alt="image-20220313161736092" style="zoom:25%;" />

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313161816966.png" alt="image-20220313161816966" style="zoom:25%;" />

#  Garbage Collection

The DBMS needs to remove reclaimable physical versions from the database over time. A version is *reclaimable* if ==no **active** transaction can “see” that version== or if ==it was created by a transaction that was aborted==.

## Approach #1: Tuple-level GC

With tuple-level garbage collection, the DBMS finds old versions by examining tuples directly. There are two approaches to achieve this:

* **Background Vacuuming**: Separate threads periodically scan the table and look for reclaimable versions. This works with any version storage scheme. A simple optimization is to maintain a ==“*dirty page bitmap*”==, ==which keeps track of which pages have been modified since the last scan. This allows the threads to skip pages which have not changed.==
* **Cooperative Cleaning**: Worker threads identify reclaimable versions as they traverse version chain. This only works with O2N chains.

### Example #1

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313162354010.png" alt="image-20220313162354010" style="zoom:25%;" />

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313162427897.png" alt="image-20220313162427897" style="zoom:25%;" />

> **Tips**:
>
> 这个例子中，系统中有两个活跃的事务（12 和 25），A~100~ 和 B~100~ 的 END-TS 为 9 表示事务 ID 为 9 的事务写了 A~100~ 和 B~100~，并产生了一个新的版本 A~101~ 和 B~101~。因为 12 > 9 且 25 > 9，所以 A~100~ 和 B~100~ 这两个版本一定没有事务能看到或正在读了，可以安全清理；而 B~101~ 的 BEGIN-TS 和 END-TS 分别为 10 和 20，可以被事务 12 看到，不能被清理。

### Example #2

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313170429601.png" alt="image-20220313170429601" style="zoom:25%;" />

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313162517447.png" alt="image-20220313162517447" style="zoom:25%;" />

### Example #3

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313162731314.png" alt="image-20220313162731314" style="zoom:25%;" />

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313162755748.png" alt="image-20220313162755748" style="zoom:25%;" />

> **Tips**:
>
> T~12~ 在遍历 A 的历史版本的时候，发现 A~0~、A~1~ 小于任何一个当前活跃的事务 timestamp（DBMS 通过维护一个所有当前活跃事务的最小 ID 或 timestamp 的 Watermark 来判断），因此可以安全删除。

## Approach #2: Transaction-level GC

Under transaction-level garbage collection, each transaction is responsible for keeping track of their own old versions so the DBMS does not have to scan tuples. Each transaction maintains its own read/write set. When a transaction completes, the garbage collector can use that to identify which tuples to reclaim. ==The DBMS determines when all versions created by a finished transaction are no longer visible.==

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313163046950.png" alt="image-20220313163046950" style="zoom:25%;" />

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313163142448.png" alt="image-20220313163142448" style="zoom:25%;" />

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313163305925.png" alt="image-20220313163305925" style="zoom:25%;" />

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313163419545.png" alt="image-20220313163419545" style="zoom:25%;" />

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313163508813.png" alt="image-20220313163508813" style="zoom:25%;" />

> **Tips**：
>
> 注：在 CMU 的课里，最后 A~2~ 和 B~6~ 的 END-TS 为 15，A~3~ 和 B~7~ 的BEGIN-TS 为 15。(which one is correct?)
>
> 在事务结束的时候，会有 Vacuum 线程判断当前所有活跃事务的 ID 是否都大于 15，如果是，A~2~ 和 A~6~ 这两个版本就可以删除了。

# Index Management

All primary key (pkey) indexes always point to version chain head. How often the DBMS has to update the pkey index depends on whether the system creates new versions when a tuple is updated. If a transaction updates a pkey attribute(s), then this is treated as a DELETE followed by an INSERT.

Managing secondary indexes is more complicated. There are two approaches to handling them.

## Approach #1: Logical Pointers

==The DBMS uses a fixed identifier per tuple that does not change==. This requires an extra indirection layer that ==maps the logical id to the physical location of the tuple==. Then, updates to tuples can just update the mapping in the indirection layer.

## Approach #2: Physical Pointers
The DBMS uses the physical address to the version chain head. This requires updating every index when the version chain head is updated.

## Example

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313163932002.png" alt="image-20220313163932002" style="zoom:25%;" />

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313164006853.png" alt="image-20220313164006853" style="zoom:25%;" />

> **Tips**:
>
> 可能会有很多 Secondary Index，使用 Physical Pointers 的话，需要更新所有 Secondary Index 的 Pointer。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313164032869.png" alt="image-20220313164032869" style="zoom:25%;" />

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313164055165.png" alt="image-20220313164055165" style="zoom:25%;" />

## Duplicate Key Problem

MVCC DBMS indexes (usually) do not store version information about tuples with their keys. 

* Exception: Index-organized tables (e.g., MySQL)

Every index must ==support duplicate keys from different snapshots==:

* The same key may point to different logical tuples in different snapshots.

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313175130940.png" alt="image-20220313175130940" style="zoom:25%;" />

T~2~ 更新了 A 产生了一个新版本 A~2~，然后又 DELETE 了 A，因为版本 A~1~ 还有事务在读，所以 A~1~ 不能被立即删除。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313175209822.png" alt="image-20220313175209822" style="zoom:25%;" />

然后 T~3~ 插入了 A，因为 A 已经被 T~2~ 删除了，所以 T~3~ 可以成功插入，此时 Index 中就有两个关于 A 的 Version Chain 了。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313175240204.png" alt="image-20220313175240204" style="zoom:25%;" />

* Each index's underlying data structure must support the storage of non-unique keys.
* Use additional execution logic to perform conditional inserts for pkey / unique indexes: Atomically check whether the key exists and then insert.
* Workers may get back multiple entries for a single fetch. They then must follow the pointers to find the proper physical version.

The DBMS physically deletes a tuple from the database only when all versions of a logically deleted tuple are not visible.

* If a tuple is deleted, then there cannot be a new version of that tuple after the newest version.
* No write-write conflicts / first-writer wins

We need a way to denote that tuple has been logically delete at some point in time.

**Approach #1: Deleted Flag**

* Maintain a flag to indicate that the logical tuple has been deleted after the newest physical version.
* Can either be in tuple header or a separate column.

**Approach #2: Tombstone Tuple**

* Create an empty physical version to indicate that a logical tuple is deleted.
* Use a separate pool for tombstone tuples with only a special bit pattern in version chain pointer to reduce the storage overhead.