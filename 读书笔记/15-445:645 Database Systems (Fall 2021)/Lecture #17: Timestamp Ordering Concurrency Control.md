# Timestamp Ordering Concurrency Control

Timestamp ordering (T/O) is an **optimistic** class of concurrency control protocols where the DBMS assumes that transaction conflicts are rare. Instead of requiring transactions to acquire locks before they are allowed to read/write to a database object, ==the DBMS instead uses timestamps to determine the serializability order of transactions.==

Each transaction T~i~ is assigned a **unique** fixed timestamp TS(T~i~ ) that is ==monotonically increasing==. Different schemes assign timestamps at different times during the transaction. Some advanced schemes even assign multiple timestamps per transaction.

If TS(T~i~ ) < TS(T~j~ ), then the DBMS must ensure that the execution schedule is equivalent to a serial schedule where T~i~ appears before T~j~ .

There are multiple timestamp allocation implementation strategies. 

* **System Clock**: The DBMS can use the system clock as a timestamp, but issues arise with edge cases like daylight savings.
* **Logical Counter**: Another option is to use a logical counter. However, this has issues with overflow and with maintaining the counter across a distributed system with multiple machines.
* **Hybrid**: There are also hybrid approaches that use a combination of both methods.

#  Basic Timestamp Ordering (BASIC T/O)

The basic timestamp ordering protocol (BASIC T/O) allows reads and writes on database objects without using locks. Instead, ==every database object X is tagged with timestamp of the last transaction that successfully performed a read (denoted as R-TS(X)) or write (denoted as W-TS(X)) on that object.== The DBMS then checks these timestamps for every operation. ==If a transaction tries to access an object in a way which violates the timestamp ordering, the transaction is aborted and restarted.== The underlying assumption is that violations will be rare and thus these restarts will also be rare.

* W-TS(X) – Write timestamp on X
* R-TS(X) – Read timestamp on X

## Read Operations

If ==*TS(T~i~) < W-TS(X)*==, this violates timestamp order of Ti with regard to the writer of X.

* Abort Ti and restart it with a new TS.

Else:

* Allow Ti to read X.
* Update *R-TS(X)* to ==*max(R-TS(X), TS(T~i~))*==
* ==Make a local copy of X== to ensure repeatable reads for T~i~.

> **Tips**:
>
> 为什么不允许 TS(T~i~) < W-TS(X)？因为 DBMS 使用 timestamps 作为串行化的依据，我们假设 T~j~ > T~i~，且写了 X 的事务就是 T~j~，那么 T~i~ 在串行化调度中是在 T~j~ 前执行的，T~i~ 当然不可能读到 T~j~ 写的 X。

## Write Operations

If ==*TS(T~i~) < R-TS(X)*== or ==*TS(T~i~) < W-TS(X)*==

* Abort and restart T~i~.

Else:

* Allow T~i~ to write X and ==update W-TS(X)==

* Also ==make a local copy of X== to ensure repeatable reads.

> **Tips**:
>
> 1. 为什么不允许 TS(T~i~) < R-TS(X)？我们假设 T~j~ > T~i~，且读了 X 的事务就是 T~j~，那么 T~i~ 在串行化调度中是在 T~j~ 前执行的，T~i~ 写 X 在 T~j~ 读 X 之前，T~j~ 应该读到 T~i~ 写的 X，而不是老的 X。
> 2. 为什么不允许 TS(T~i~) < W-TS(X)？我们假设 T~j~ > T~i~，且写了 X 的事务就是 T~j~，那么 T~i~ 在串行化调度中是在 T~j~ 前执行的，T~i~ 先写了 X，T~j~ 在 T~i~ 之后覆盖写了 X，最后执行的结果是 X 的值应该是 T~j~ 写的值。（因为这里 T~i~ 写 X 的结果最终会被 T~j~ 写 X 的结果覆盖，所以可以优化，见 Thomas Write Rule）

## Example #1

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313003720034.png" alt="image-20220313003720034" style="zoom:25%;" />

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313003736766.png" alt="image-20220313003736766" style="zoom:25%;" />

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313003809174.png" alt="image-20220313003809174" style="zoom:25%;" />

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313003838194.png" alt="image-20220313003838194" style="zoom:25%;" />

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313003901266.png" alt="image-20220313003901266" style="zoom:25%;" />

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313003923028.png" alt="image-20220313003923028" style="zoom:25%;" />

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313003948462.png" alt="image-20220313003948462" style="zoom:25%;" />

> **Tips**:
>
> 对于读操作来说 TS(T~1~) < R-TS(A) 并没有问题，所以 T~1~ 可以正常读取 A，并且因为 TS(T~1~) < R-TS(A)，所以不需要更新 R-TS(A)。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313004222825.png" alt="image-20220313004222825" style="zoom:25%;" />

## Example #2

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313004257197.png" alt="image-20220313004257197" style="zoom:25%;" />

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313004318156.png" alt="image-20220313004318156" style="zoom:25%;" />

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313004344858.png" alt="image-20220313004344858" style="zoom:25%;" />

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313004409696.png" alt="image-20220313004409696" style="zoom:25%;" />

## Optimization: Thomas Write Rule⭐️

If ==*TS(T~i~) < R-TS(X)*==:

* Abort and restart T~i~.

If ==*TS(T~i~) < W-TS(X)*==:

* **Thomas Write Rule**: ==Ignore the write== to allow the txn to continue executing without aborting.
* This violates timestamp order of T~i~.

Else:

* Allow Ti to write X and update *W-TS(X)*

> **Tips**:
>
> TS(T~i~) < W-TS(X) 表示 X 已经被一个 timestamp 比 T~i~ 大的事务（我们设为 T~j~）写了，因为 DBMS 以 timestamp 作为串行化调度的依据，因此最终结果必须跟  T~i~ 先执行，T~j~ 后执行等价，即 X 最终的结果是  T~j~ 写的值，我们忽略 T~i~ 写的 X 最终的结果也与 T~i~ -> T~j~ 这个调度等价。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313010216220.png" alt="image-20220313010216220" style="zoom:25%;" />

* ==The Basic T/O protocol generates a schedule that is **conflict serializable** if it does not use Thomas Write Rule.==

* It ==cannot have deadlocks== because no transaction ever waits. 
* However, there is a possibility of ==starvation== for long transactions if short transactions keep causing conflicts.

It also permits schedules that are ==not *recoverable=*=. A schedule is recoverable if transactions commit only after all transactions whose changes they read, commit. Otherwise, the DBMS cannot guarantee that transactions read data that will be restored after recovering from a crash.

## Recoverable Schedules

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313010541617.png" alt="image-20220313010541617" style="zoom:25%;" />

## Potential Issues

* High overhead from copying data to transaction’s workspace and from updating timestamps.
* Long running transactions can get starved. The likelihood that a transaction will read something from a newer transaction increases.
* Suffers from the timestamp allocation bottleneck on highly concurrent systems.

# Optimistic Concurrency Control (OCC)

Optimistic concurrency control (OCC) is another *optimistic* concurrency control protocol which also uses timestamps to validate transactions. ==OCC works best when the number of conflicts is low.== This is when either all of the transactions are ==read-only== or when transactions ==access disjoint subsets of data==. If the database is large and the workload is not skewed, then there is a low probability of conflict, making OCC a good choice.

==In OCC, the DBMS creates a ***private workspace*** for each transaction==. ==All modifications of the transaction are applied to this workspace==. Any object read is copied into workspace and any object written is copied to the workspace and modified there. No other transaction can read the changes made by another transaction in its private workspace.

When a transaction commits, the DBMS compares the transaction’s workspace ==***write set***== to see whether it conflicts with other transactions. If there are no conflicts, the write set is installed into the “global” database.

OCC consists of three phases:

1. **Read Phase**: Here, the DBMS tracks the read/write sets of transactions and ==stores their writes in a private workspace==.
2. **Validation Phase**: When a transaction commits, the DBMS checks whether it conflicts with other transactions.
3. **Write Phase**: If validation succeeds, the DBMS applies the private workspace changes to the database. Otherwise, it aborts and restarts the transaction.

## Example #1⭐️

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313011341986.png" alt="image-20220313011341986" style="zoom:25%;" />

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313011410274.png" alt="image-20220313011410274" style="zoom:25%;" />

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313011516329.png" alt="image-20220313011516329" style="zoom:25%;" />

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313011613470.png" alt="image-20220313011613470" style="zoom:25%;" />

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313011654444.png" alt="image-20220313011654444" style="zoom:25%;" />

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313011712348.png" alt="image-20220313011712348" style="zoom:25%;" />

## Validation Phase⭐️

==The DBMS assigns transactions timestamps when they enter the **validation phase**==. To ensure only serializable schedules are permitted, the DBMS checks T~i~ against other transactions for RW and WW conflicts and makes sure that all conflicts go one way (from older transactions to younger transactions). The DBMS checks the timestamp ordering of the committing transaction with all other running transactions. ==Transactions that have not yet entered the validation phase are assigned a timestamp of **∞**==.

> **Tips**:
>
> transactions timestamp 是在进入 validation phase 之后才分配，之前都是无穷大。

Two methods for this phase:

* Backward Validation
* Forward Validation

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313012147770.png" alt="image-20220313012147770" style="zoom:25%;" />

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313012233649.png" alt="image-20220313012233649" style="zoom:25%;" />

If *TS(T~i~ ) < TS(T~j~ )*, then one of the following three conditions must hold:
1. T~i~ completes all three phases before T~j~ begins

   <img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313012639461.png" alt="image-20220313012639461" style="zoom:25%;" />

2. ==T~i~ completes before T~j~ starts its Write phase==, and ==T~i~ does not write to any object read by T~j~== . (WriteSet(T~i~ ) ∩ ReadSet(T~j~) = Ø)

   <img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313012850247.png" alt="image-20220313012850247" style="zoom:25%;" />

   <img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313012914814.png" alt="image-20220313012914814" style="zoom:25%;" />

   > **Tips**:
   >
   > 注意：T~1~ 的 W(A) 操作是在本地 workspace 执行的，在提交之前其他事务是看不到的，因此尽管 T~1~ W(A) 在 T~2~ R(A) 之前发生，T~2~ 读到的 A 仍然是老的值 123。
   >
   > 
   >
   > 上面这两个例子的 R W 顺序都一样，唯一的区别是 Validate 的先后顺序：
   >
   > * 第 1 个例子中 T~1~ 先进入 Validate，因此 T~1~ < T~2~。因为 T~2~ Read 了 A，因此 WriteSet(T~1~ ) ∩ ReadSet(T~2~) 不是空集，不满足上述条件，不能提交。
   >   * T~1~ < T~2~ 表示在串行化调度中 T~1~ 在 T~2~ 之前执行，那么 T~2~ 的 R(A) 一定能看到 T~1~ W(A)，但实际情况是 T~2~ R(A) 仍然是旧值 123，不符合串行化调度
   > * 第 2 个例子中 T~2~ 先进入 Validate，因此 T~2~ < T~1~。尽管 T~2~ Read 了 A，但是 WriteSet(T~2~ ) ∩ ReadSet(T~1~) 是空集，满足上述条件，可以提交。 
   >   * T~2~ < T~1~ 表示在串行化调度中 T~2~ 在 T~1~ 之前执行，那么 T~2~ 的 R(A) 是看不到 T~1~ 的 W(A) 的，显然这个例子是符合这个要求的

3. ==T~i~ completes its Read phase before T~j~ completes its Read phase==, and ==T~i~ does not write to any object that is either read or written by T~j~== .

    (WriteSet(Ti ) ∩ ReadSet(T j) = Ø and WriteSet(Ti ) ∩ WriteSet(Tj ) = Ø)

   <img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313014335756.png" alt="image-20220313014335756" style="zoom:25%;" />

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313014418942.png" alt="image-20220313014418942" style="zoom:25%;" />

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313014459523.png" alt="image-20220313014459523" style="zoom:25%;" />

> **Tips**:
>
> 1. T~1~ 先进入 Validate，因此 T~1~ < T~2~，虽然 T~1~ 写了 A，而且 T~2~ 在后面会读 A，但是在 Validate 的时候 T~2~ 并没有开始写 A，因此 T~1~ 与 T~2~ 之间并没有写冲突，可以提交
> 2. T~2~ R(A) 在 T~1~ COMMIT 之后，读到的是 T~1~ 写的新值
> 3. T~2~ 进入 Validate 的时候 T~1~ 已经完成 COMMIT，系统中没有其他活跃事务了，即第 1 中情况，直接通过
> 4. 整个调度等价于 T~1~ -> T~2~

## Potential Issues

* High overhead for copying data locally into the transaction’s private workspace.
* Validation/Write phase bottlenecks.
* Aborts are potentially more wasteful than in other protocols because they only occur after a transaction has already executed.
* Suffers from timestamp allocation bottleneck.

# Isolation Levels

Serializability is useful because it allows programmers to ignore concurrency issues but enforcing it may allow too little parallelism and limit performance. We may want to use a weaker level of consistency to improve scalability.

Isolation levels control the extent that a transaction is exposed to the actions of other concurrent transactions.

**Anomalies**:

* **Dirty Read**: Reading uncommitted data.
* **Unrepeatable Reads**: Redoing a read results in a different result.
* **Phantom Reads**: Insertion or deletions result in different results for the same range scan queries.

## The Phantom Problem⭐️

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313015645853.png" alt="image-20220313015645853" style="zoom:25%;" />

How did this happen? ==Because T1 locked only existing records and not ones under way!== ==Conflict serializability on reads and writes of
individual items guarantees serializability **only** if the set of objects is fixed==.

### Approach #1: Re-Execute Scans

The DBMS tracks the WHERE clause for all queries that the txn executes. Have to retain the scan set for every range query in a txn.

Upon commit, re-execute just the scan portion of each query and check whether it generates the same result.

Example: Run the scan for an UPDATE query but do not modify matching tuples.

### Approach #2: Predicate Locking

Proposed locking scheme from System R. Shared lock on the predicate in a WHERE clause of a SELECT query.

Exclusive lock on the predicate in a WHERE clause of any UPDATE, INSERT, or DELETE query.

Never implemented in any system except for HyPer (precision locking).

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313020253942.png" alt="image-20220313020253942" style="zoom:25%;" />

### Approach #3: Index Locking

If there is an index on the status attribute then the txn can lock index page containing the data with status='lit'.

If there are no records with status='lit', the txn must lock the index page where such a data entry would be, if it existed.

If there is no suitable index, then the txn must obtain: 

1. A lock on every page in the table to prevent a record’s status='lit' from being changed to lit.
2. The lock for the table itself to prevent records with status='lit' from being added or deleted.

> **Tips**: MySQL 的 Next-Key-Lock

## Isolation Levels

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313020544691.png" alt="image-20220313020544691" style="zoom:25%;" />

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313020650526.png" alt="image-20220313020650526" style="zoom:25%;" />

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220313020718682.png" alt="image-20220313020718682" style="zoom:25%;" />

The isolation levels defined as part of SQL-92 standard only focused on anomalies that can occur in a 2PL-based DBMS. There are two additional isolation levels:

1. **CURSOR STABILITY**
   * Between repeatable reads and read committed
   * Prevents Lost Update Anomaly.
   * Default isolation level in IBM DB2.
2. ==**SNAPSHOT ISOLATION**==
   * Guarantees that all reads made in a transaction see a consistent snapshot of the database that existed at the time the transaction started.
   * A transaction will commit only if its writes do not conflict with any concurrent updates made since that snapshot.
   * Susceptible to ==write skew== anomaly.