# Crash Recovery

*Recovery algorithms* are techniques to ensure database ==consistency==, transaction ==atomicity==, and ==durability== despite failures. When a crash occurs, all the data in memory that has not been committed to disk is at risk of being lost. Recovery algorithms act to prevent loss of information after a crash.

Every recovery algorithm has two parts:

* Actions during normal transaction processing to ensure that the DBMS can recover from a failure.
* Actions after a failure to recover the database to a state that ensures atomicity, consistency, and durability.

The key primitives that used in recovery algorithms are **UNDO** and **REDO**. Not all algorithms use both primitives.

* **UNDO**: The process of removing the effects of an incomplete or aborted transaction.
* **REDO**: The process of re-instating the effects of a committed transaction for durability.

# Storage Types

* **Volatile Storage**
  * Data does not persist after power is lost or program exits.
  * Examples: DRAM, SRAM,.
* **Non-Volatile Storage**
  * Data persists after losing power or program exists.
  * Examples: HDD, SDD.
* **Stable Storage**
  * A non-existent form of non-volatile storage that survives all possible failures scenarios.
  * Use multiple storage devices to approximate.

# Failure Classification

Because the DBMS is divided into different components based on the underlying storage device, there are a number of different types of failures that the DBMS needs to handle. Some of these failures are recoverable while others are not.

## Type #1: Transaction Failures

*Transactions failures* occur when a transaction reaches an error and must be aborted. Two types of errors that can cause transaction failures are logical errors and internal state errors.

* **Logical Errors**: A transaction cannot complete due to some internal error condition (e.g., integrity, constraint violation).
* **Internal State Errors**: The DBMS must terminate an active transaction due to an error condition (e.g., deadlock)

## Type #2: System Failures

*System failures* are unintented failures in hardware or software that must also be accounted for in crash recovery protocols.

* **Software Failure**: There is a problem with the DBMS implementation (e.g., uncaught divide-by-zero exception) and the system has to halt.
* **Hardware Failure**: The computer hosting the DBMS crashes (e.g., power plug gets pulled). We assume that non-volatile storage contents are not corrupted by system crash.

## Type #3: Storage Media Failure

*Storage media failures* are non-repairable failures that occur when the physical storage machine is damaged. When the storage media fails, the DBMS must be restored from an archived version.

* **Non-Repairable Hardware Failure**: A head crash or similar disk failure destroys all or parts of non-volatile storage. Destruction is assumed to be detectable.

# Buffer Pool Management Policies

The DBMS needs to ensure the following guarantees:

* The changes for any transaction are durable once the DBMS has told somebody that it committed.
* No partial changes are durable if the transaction aborted.

## Steal and Force ⭐️

A *steal policy* dictates whether the DBMS allows an uncommitted transaction to overwrite the most recent committed value of an object in non-volatile storage (==can a transaction write uncommitted changes to disk==).

* ==**STEAL**==: Is allowed (==允许未提交事务刷盘==)
* **NO-STEAL**: Is not allowed. (不允许未提交事务刷盘)

A *force policy* dictates whether the DBMS requires that all updates made by a transaction are reflected on non-volatile storage before the transaction is allowed to commit.

* **FORCE**: Is required (事务提交时脏页必须刷盘)
* ==**NO-FORCE**==: Is not required (==事务提交时脏页不用刷盘==)

Force writes make it easier to recover since all of the changes are preserved but result in poor runtime performance.

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220316002900676.png" alt="image-20220316002900676" style="zoom:25%;" />

## NO-STEAL + FORCE

The easiest buffer pool management policy to implement is called *NO-STEAL + FORCE*. In the NO-STEAL + FORCE policy, the DBMS ==never has to undo== changes of an aborted transaction because the changes were not written to disk. It also ==never has to redo== changes of a committed transaction because all the changes are guaranteed to be written to disk at commit time. An example of NO-STEAL + FORCE is show in Figure 1.

A limitation of NO STEAL + FORCE is that all of the data that ==a transaction needs to modify must fit on memory==. Otherwise, that transaction cannot execute because the DBMS is not allowed to write out dirty pages to disk before the transaction commits.

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220316000216064.png" alt="image-20220316000216064" style="zoom: 33%;" />

#  Shadow Paging

The DBMS maintains two separate copies of the database:

* *master*: Contains only changes from committed txns.
* *shadow*: Temporary database with changes made from uncommitted transactions.

==Updates are only made in the shadow copy==. When a transaction commits, the shadow is atomically switched to become the new master. This is an example of a NO-STEAL + FORCE system. A high-level example of shadow paging is shown in Figure 2.

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220316000431148.png" alt="image-20220316000431148" style="zoom:33%;" />

## Implementation

The DBMS organizes the database pages in a tree structure where the root is a single disk page. There are ==two copies of the tree==, the *master* and *shadow*. The root always points to the current master copy. When a transaction executes, it only makes changes to the shadow copy.

When a transaction wants to commit, the DBMS must install its updates. To do this, it only has overwrite the root to make it points to the shadow copy of the database, thereby swapping the master and shadow. Before overwriting the root, none of the transactions updates are part of the disk-resident database. After overwriting the root, all of the transactions updates are part of the disk resident database.

## Recovery

* **Undo**: Remove the shadow pages. Leave the master and DB root pointer alone.
* **Redo**: Not needed at all.

## Disadvantages

A disadvantage of shadow paging is that ==copying the entire page table is expensive==. ==In reality, only paths in the tree that lead to updated leaf nodes need to be copied, not the entire tree==. In addition, the commit overhead of shadow paging is high. ==Commits require every updated page, page table, and root to be flushed==. This causes ==fragmented data== and also requires ==garbage collection==. Another issue is that this only supports one writer transaction at a time or transactions in a batch.

# Journal File

When a transaction modifies a page, the DBMS copies the original page to a separate journal file before overwriting the master version. After restarting, if a journal file exists, then the DBMS restores it to undo changes from uncommited transactions.

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220316001117511.png" alt="image-20220316001117511" style="zoom:25%;" />

<center>(1) 对 page 的更改写入到 journal file</center>

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220316001158024.png" alt="image-20220316001158024" style="zoom:25%;" />

<center>(2) 写回 page2 时 crash 了</center>

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/021223592303_01.png" alt="img" style="zoom: 25%;" />

<center>(3) recovery 时先从 journal file 中读出所有的 page，然后再写回 disk</center>

# Write-Ahead Logging ⭐️

With *write-ahead logging*, the DBMS records all the changes made to the database in a log file (on stable storage) before the change is made to a disk page. The log contains sufficient information to perform the necessary undo and redo actions to restore the database after a crash. ==The DBMS must write to disk the log file records that correspond to changes made to a database object before it can flush that object to disk==. An example of WAL is shown in Figure 3. WAL is an example of a ==STEAL + NO-FORCE== system.

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220316002124274.png" alt="image-20220316002124274" style="zoom: 33%;" />

In shadow paging, the DBMS was required to perform writes to random non-contiguous pages on disk. Write-ahead logging allows the DBMS to convert random writes into ==sequential writes== to optimize performance. Thus, almost every DBMS uses write-ahead logging (WAL) because it has the fastest runtime performance. But the DBMS’s recovery time with WAL is slower than shadow paging because it has to replay the log.

## Implementation

The DBMS first stages all of a transaction’s log records in volatile storage. All log records pertaining to an updated page are then written to non-volatile storage before the page itself is allowed to be overwritten in non-volatile storage. ==A transaction is **not** considered committed until all its log records have been written to stable storage==.

When the transaction starts, write a \<BEGIN\> record to the log for each transaction to mark its starting point.

When a transaction finishes, write a \<COMMIT\> record to the log and make sure all log records are flushed before it returns an acknowledgment to the application.

Each log entry contains information about the change to a single object:

* Transaction ID.
* Object ID.
* Before Value (used for UNDO).
* After Value (used for REDO).

==**The DBMS must flush all of a transaction’s log entries to disk before it can tell the outside world that a transaction has successfully committed**==. The system can use the “==*group commit*==” optimization to batch multiple log flushes together to amortize overhead. The DBMS can write dirty pages to disk whenever it wants as long as it’s after flushing the corresponding log records.

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220316002647184.png" alt="image-20220316002647184" style="zoom:25%;" />

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220316002758272.png" alt="image-20220316002758272" style="zoom:25%;" />

# Logging Schemes

The contents of a log record can vary based on the implementation.

**Physical Logging**:

* Record the byte-level changes made to a specific location in the database.
* Example: Position of a record in a page

**Logical Logging**:

* Record the high level operations executed by transactions.
* Not necessarily restricted to a single page.
* Requires less data written in each log record than physical logging because each record can update multiple tuples over multiple pages. However, it is difficult to implement recovery with logical logging when there are concurrent transactions in a non-deterministic concurrency control scheme. Additionally recovery takes longer because you must re-execute every transaction.
* Example: The UPDATE, DELETE, and INSERT queries invoked by a transaction.

**Physiological Logging**:

* Hybrid approach where log records target a single page but do not specify data organization of the page. That is, identify tuples based on a slot number in the page without specifying exactly where in the page the change is located. Therefore the DBMS can reorganize pages after a log record has been written to disk.
* Most common approach used in DBMSs.

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220316003152327.png" alt="image-20220316003152327" style="zoom:25%;" />

# Checkpoints

Why?

* The WAL will grow forever.
* ==After a crash, the DBMS must replay the entire log, which will take a long time.==
* The DBMS periodically takes a checkpoint where it flushes all buffers out to disk.

How?

* Output onto stable storage all log records currently residing in main memory.
* Output to the disk all modified blocks.
* Write a \<CHECKPOINT\> entry to the log and flush to stable storage.

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220316003445550.png" alt="image-20220316003445550" style="zoom:25%;" />

Disadvantage:

* The DBMS must stall txns when it takes a checkpoint to ensure a consistent snapshot.
* Scanning the log to find uncommitted txns can take a long time.
* Not obvious how often the DBMS should take a checkpoint...