# Transaction Locks

A DBMS uses *locks* to dynamically generate an execution schedule for transactions that is serializable ==without knowing each transaction’s read/write set ahead of time==. These locks protect database objects during concurrent access when there are multiple readers and writes. The DBMS contains a ==**centralized** *lock manager*== that decides whether a transaction can acquire a lock or not. It also provides a global view of whats going on inside the system. 

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220312231516029.png" alt="image-20220312231516029" style="zoom:25%;" />

## Lock Types

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220312231631387.png" alt="image-20220312231631387" style="zoom:25%;" />

There are two basic types of locks:

* **Shared Lock (S-LOCK)**: A shared lock that allows multiple transactions to read the same object at the same time. If one transaction holds a shared lock, then another transaction can also acquire that same shared lock.
* **Exclusive Lock (X-LOCK)**: An exclusive lock allows a transaction to modify an object. This lock prevents other transactions from taking any other lock (S-LOCK or X-LOCK) on the object. Only one transaction can hold an exclusive lock at a time.

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220312231651132.png" alt="image-20220312231651132" style="zoom:25%;" />

Transactions must request locks (or upgrades) from the lock manager. The lock manager grants or blocks requests based on what locks are currently held by other transactions. Transactions must release locks when they no longer need them to free up the object. The lock manager updates its internal lock-table with information about which transactions hold which locks and which transactions are waiting to acquire locks.

The DBMS’s lock-table does not need to be durable since any transaction that is active (i.e., still running) when the DBMS crashes is automatically aborted.

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220312231815535.png" alt="image-20220312231815535" style="zoom:25%;" />

> **Tips**:
>
> 上图的例子表示了虽然每个操作都有 Lock 保护，但是仍然有 W-A 冲突，所以需要 2PL。

# Two-Phase Locking

Two-Phase locking (2PL) is a pessimistic concurrency control protocol that uses locks to determine whether a transaction is allowed to access an object in the database on the fly. The protocol does not need to know all of the queries that a transaction will execute ahead of time.

* **Phase #1– Growing**: In the growing phase, each transaction requests the locks that it needs from the DBMS’s lock manager. The lock manager grants/denies these lock requests.

* **Phase #2– Shrinking**: Transactions enter the shrinking phase immediately after it releases its first lock. In the shrinking phase, transactions are only allowed to release locks. They are not allowed to acquire new ones.

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220312232147831.png" alt="image-20220312232147831" style="zoom:25%;" />

## Cascading Aborts

On its own, ==2PL is sufficient to **guarantee conflict serializability**==. ==It generates schedules whose precedence graph is acyclic==. But it is susceptible to ==*cascading aborts*==, which is when a transaction aborts and now another transaction must be rolled back, which results in wasted work.

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220312232422523.png" alt="image-20220312232422523" style="zoom:25%;" />

> **Tips**:
>
> 实际上这是一种脏读。

There are also potential schedules that are serializable but would not be allowed by 2PL (locking can limit concurrency).

## Strong Strict Two-Phase Locking

A schedule is *strict* if any value written by a transaction is never read or overwritten by another transaction until the first transaction commits. Strong Strict 2PL (also known as Rigorous 2PL) is a variant of 2PL where the transactions only release locks when they commit.

The advantage of this approach is that the DBMS does not incur cascading aborts. The DBMS can also reverse the changes of an aborted transaction by restoring the original values of modified tuples. However, ==Strict 2PL generates more cautious/pessimistic schedules that limit concurrency==.

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220312232818561.png" alt="image-20220312232818561" style="zoom:25%;" />

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220312232918310.png" alt="image-20220312232918310" style="zoom:25%;" />

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220312233008191.png" alt="image-20220312233008191" style="zoom:25%;" />

# Deadlock Handling

A *deadlock* is a cycle of transactions waiting for locks to be released by each other. There are two approaches to handling deadlocks in 2PL: **detection** and **prevention**.

## Approach #1: Deadlock Detection

To detect deadlocks, the DBMS creates a ==*waits-for* graph== where transactions are nodes, and there exists a directed edge from T~i~ to T~j~ if transaction T~i~ is waiting for transaction T~j~ to release a lock. The system will periodically check for cycles in the waits-for graph (usually with a background thread) and then make a decision on how to break it. Latches are not needed when constructing the graph since if the DBMS misses a deadlock in one pass, it will find it in the subsequent passes.

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220312233456028.png" alt="image-20220312233456028" style="zoom:25%;" />

When the DBMS detects a deadlock, it will select a “victim” transaction to abort to break the cycle. The victim transaction will either restart or abort depending on how the application invoked it. 

The DBMS can consider multiple transaction properties when selecting a victim to break the deadlock:

1. By age (newest or oldest timestamp).
2. By progress (least/most queries executed).
3. By the # of items already locked.
4. By the # of transactions needed to rollback with it.
5. \# of times a transaction has been restarted in the past (to avoid starvation).

There is no one choice that is better than others. Many systems use a combination of these factors.

After selecting a victim transaction to abort, the DBMS can also decide on how far to rollback the transaction’s changes. It can either rollback the entire transaction or just enough queries to break the deadlock.

## Approach #2: Deadlock Prevention

Instead of letting transactions try to acquire any lock they need and then deal with deadlocks afterwards, deadlock prevention 2PL stops transactions from causing deadlocks before they occur. When a transaction tries to acquire a lock held by another transaction (which could cause a deadlock), the DBMS kills one of them. To implement this, transactions are assigned priorities based on timestamps (==older transactions have higher priority==). ==These schemes guarantee no deadlocks because only one type of direction is allowed when waiting for a lock==. When a transaction restarts, the DBMS ==reuses the same timestamp==.

There are two ways to kill transactions under deadlock prevention:

* **Wait-Die (“Old Waits for Young”)**: If the requesting transaction has a higher priority than the holding transaction, it waits. Otherwise, it aborts.
* **Wound-Wait (“Young Waits for Old”)**: If the requesting transaction has a higher priority than the holding transaction, the holding transaction aborts and releases the lock. Otherwise, the requesting transaction waits.

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220312234052583.png" alt="image-20220312234052583" style="zoom:25%;" />

# Lock Granularities

If a transaction wants to update one billion tuples, it has to ask the DBMS’s lock manager for a billion locks. ==This will be slow because the transaction has to take latches in the lock manager’s internal lock table data structure as it acquires/releases locks==.

To avoid this overhead, the DBMS can use to use a ==**lock hierarchy**== that allows a transaction to take more coarse-grained locks in the system. For example, it could acquire a single lock on the table with one billion tuples instead of one billion separate locks. When a transaction acquires a lock for an object in this hierarchy, it implicitly acquires the locks for all its children objects.

## Intention Lock

==**Intention locks**== allow a higher level node to be locked in shared mode or exclusive mode without having to check all descendant nodes. ==If a node is in an intention mode, then explicit locking is being done at a lower level in the tree.==

* **Intention-Shared (IS)**: Indicates explicit locking at a lower level with shared locks.
* **Intention-Exclusive (IX)**: Indicates explicit locking at a lower level with exclusive or shared locks.
* **Shared+Intention-Exclusive (SIX)**: The sub-tree rooted at that node is locked explicitly in shared mode and explicit locking is being done at a lower level with exclusive-mode locks.

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220312234508769.png" alt="image-20220312234508769" style="zoom:25%;" />

Each txn obtains appropriate lock at highest level of the database hierarchy.

* To get **S** or **IS** lock on a node, the txn must hold at least **IS** on parent node.
* To get **X**, **IX**, or **SIX** on a node, must hold at least **IX** on parent node.

## Example #1

* T1 – Get the balance of Lin's shady off-shore bank account.
* T2 – Increase Andrew's bank account balance by 1%.

What locks should these txns obtain?

* Exclusive + Shared for leaf nodes of lock tree.
* Special Intention locks for higher levels.

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220312234846490.png" alt="image-20220312234846490" style="zoom:25%;" />

## Example #2

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220312234943733.png" alt="image-20220312234943733" style="zoom: 25%;" />

T1 需要读 table R 的所有 tuple，但是只更新 tuple n，因此 T1 需要对 table R 整体加 S Lock 和 IX Lock，同时需要对更新的 tuple 加 X Lock；由于已经对 table R   整体加了 S Lock，就不再需要对每一个需要读取的 tuple 加 S Lock 了。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220312235115471.png" alt="image-20220312235115471" style="zoom: 25%;" />

T2 只需要读 table R 的一个 tuple，因此不需要对 table R 加 S Lock，只需要 IS Lock 就够了，而 ==IS Lock 和 T1 加在 table R 上的 SIX Lock 是相容的==，可以加锁成功。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220312235239522.png" alt="image-20220312235239522" style="zoom: 25%;" />

T3 只需要读 table R 的所有 tuple，不需要修改，因此只需要对 table R 加 S Lock 就行了，但是 ==S Lock 和 T1 在 table R 上加的 SIX Lock 冲突==，因此需要等待 T1 释放 table R 上的 SIX Lock。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220312235318901.png" alt="image-20220312235318901" style="zoom: 25%;" />

T1 释放加在 table R 上的 SIX Lock 后 T3 就可以对 table R 加锁成功，而==不必等到 T1 释放 tuple n 上的 X Lock==。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313000043193.png" alt="image-20220313000043193" style="zoom: 25%;" />

# Locking in Practice

You typically don't set locks manually in txns. Sometimes you will need to provide the DBMS with hints to help it to improve concurrency. Explicit locks are also useful when doing major changes to the database.

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313000502174.png" alt="image-20220313000502174" style="zoom:25%;" />

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313000517245.png" alt="image-20220313000517245" style="zoom:25%;" />