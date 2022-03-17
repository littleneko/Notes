# Crash Recovery

The DBMS relies on its recovery algorithms to ensure database consistency, transaction atomicity, and durability despite failures. Each recovery algorithm is comprised of two parts:

* Actions during normal transaction processing to ensure ha the DBMS can recover from a failure
* Actions after a failure to recover the database to a state that ensures the atomicity, consistency, and durability of transactions.

**A**lgorithms for **R**ecovery and **I**solation **E**xploiting **S**emantics (==**ARIES**==) is a recovery algorithm developed at IBM research in early 1990s for the DB2 system.

There are three key concepts in the ARIES recovery protocol:

* **Write Ahead Logging**: Any change is recorded in log on stable storage before the database change is written to disk (==STEAL + NO-FORCE==).
* **Repeating History During Redo**: On restart, retrace actions and restore database to exact state before crash.
* **Logging Changes During Undo**: Record undo actions to log to ensure action is not repeated in the event of repeated failures.

# WAL Records

Write-ahead log records extend the DBMS’s log record format to include a globally unique *log sequence number* (==**LSN**==). A high level diagram of how log records with LSN’s are written is shown in Figure 1.

![image-20220316230013409](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220316230013409.png)

All log records have an LSN. The ==**pageLSN**== is updated every time a transaction modifies a record in the page. The ==**flushedLSN**== in memory is updated every time the DBMS writes out the WAL buffer to disk.

Various components in the system keep track of **LSNs** that pertain to them. A table of these LSNs is shown in Figure 2.

![image-20220316230029739](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220316230029739.png)

Each data page contains a **pageLSN**, which is the LSN of the most recent update to that page. The DBMS also keeps track of the max LSN flushed so far (**flushedLSN**). ==Before the DBMS can write page $i$ to disk, it must flush log at least to the point where $pageLSN_i ≤ flushedLSN$==. (即==如果要把某一页刷到磁盘，需要该页最近更新的 LSN(pageLSN) 对应的 WAL 已经写盘==)

# Normal Execution

Every transaction invokes a sequence of reads and writes, followed by a commit or abort. It is this sequence of events that recovery algorithms must have.

## Transaction Commit

When a transaction goes to commit, the DBMS first writes COMMIT record to log buffer in memory. Then the DBMS flushes all log records up to and including the transaction’s COMMIT record to disk. Note that these log flushes are sequential, synchronous writes to disk. There can be multiple log records per log page. A diagram of a transaction commit is shown in Figure 3.

![image-20220316231144133](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220316231144133.png)

> **Tips**:
>
> * We can trim the in-memory WAL (Tail) log up to flushedLSN.

Once the COMMIT record is safely stored on disk, the DBMS returns an acknowledgment back to the application that the transaction has committed. At some later point, the DBMS will write a special TXN-END record to log. This indicates that the transaction is completely finished in the system and there will not be anymore log records for it. These TXN-END records are used for internal bookkeeping and do not need to be flushed immediately.

## Transaction Abort

Aborting a transaction is a special case of the ARIES undo operation applied to only one transaction.

An additional field is added to the log records called the ==**prevLSN**==. This corresponds to the previous LSN for the transaction. The DBMS uses these prevLSN values to maintain a linked-list for each transaction that makes it easier to walk through the log to find its records.

A new type of record called the ==*compensation log record*== (==**CLR**==) is also introduced. A CLR describes the actions taken to undo the actions of a previous update record. It has all the fields of an update log record plus the ==*undoNext* pointer== (i.e., the next-to-be-undone LSN). The DBMS adds CLRs to the log like any other record but they never need to be undone.

To abort a transaction, the DBMS first appends a ABORT record to the log buffer in memory. ==It then undoes the transaction’s updates in reverse order to remove their effec==

==ts from the database==. For each undone update, the DBMS creates **CLR** entry in the log and restore old value. After all of the aborted transaction’s updates are reversed, the DBMS then writes a TXN-END log record. A diagram of this is shown in Figure 4.

![image-20220316231806501](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220316231806501.png)

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220316233215794.png" alt="image-20220316233215794" style="zoom:25%;" />

#  Checkpointing

The DBMS periodically takes *checkpoints* where it writes the dirty pages in its buffer pool out to disk. This is used to minimize how much of the log it has to replay upon recovery.

The first two blocking checkpoint methods discussed below pause transactions during the checkpoint process. This pausing is necessary to ensure that the DBMS does not miss updates to pages during the checkpoint. Then, a better approach that allows transactions to continue to execute during the checkpoint but requires the DBMS to record additional information to determine what updates it may have missed is presented.

## Blocking Checkpoints

The DBMS halts the execution of transactions and queries when it takes a checkpoint to ensure that it writes a consistent snapshot of the database to disk. The is the same approach discussed in previous lecture:

* ==Halt== the start of any new transactions.
* ==Wait== until all active transactions finish executing.
* ==Flush dirty pages== to disk.

## Slightly Better Blocking Checkpoints

Like previous checkpoint scheme except that you the DBMS does not have to wait for active transactions to finish executing. The DBMS now records the internal system state as of the beginning of the checkpoint.

* ==Halt== the start of any new transactions.
* ==Pause== transactions while the DBMS takes the checkpoint.
  * ==Prevent== queries from ==acquiring **write** latch on table/index pages==. (**read-only** transaction can still run)
  * Don't have to wait until all txns finish before taking the checkpoint.


<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220317002432466.png" alt="image-20220317002432466" style="zoom:25%;" />

<center>(1) Transaction update Page #3 和 Page #1，当 update Page #3 结束，准备 update Page #1 的时候，Checkpoint 开始了，这时 Transaction 必须 stall。</center>

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220316233748790.png" alt="image-20220316233748790" style="zoom:25%;" />

<center>(2) Checkpoint 依次进行 Page #1 #2 #3 的 Checkpoint</center>

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220317002728113.png" alt="image-20220317002728113" style="zoom:25%;" />

<center>(3) Checkpoint 结束，Transaction 可以继续运行。</center>

==上面的问题是 Checkpoint 写入了 Transaction 的部分数据（Page #3），因此 Checkpoint 或者说数据库状态处于不一致的状态。==

---

We must record internal state as of the beginning of the checkpoint.

==**Active Transaction Table (ATT)**==: The ATT represents the state of transactions that are actively running in the DBMS. A transaction’s entry is removed after the DBMS completes the commit/abort process for that transaction. For each transaction entry, the ATT contains the following information:

* **transactionId**: Unique transaction identifier
* **status**: The current “mode” of the transaction (**R**unning, **C**ommitting, **U**ndo Candidate).
* **lastLSN**: Most recent LSN written by transaction

Note that the ATT contains every transcation without the TXN-END log record. This includes both transactions that are either committing or aborting.

==**Dirty Page Table (DPT)**==: The DPT contains information about the pages in the buffer pool that ==were modified by **uncommitted** transactions==. There is one entry per dirty page containing the **recLSN** (i.e., the LSN of the log record that first caused the page to be dirty).

The DPT contains all pages that are dirty in the buffer pool. It doesn’t matter if the changes were caused by a transaction that is running, committed, or aborted.

Overall, the ATT and the DPT serve to help the DBMS recover the state of the database before the crash via the ARIES recovery protocol.

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220316234206090.png" alt="image-20220316234206090" style="zoom:25%;" />

## Fuzzy Checkpoints

A *fuzzy* checkpoint is where the DBMS allows other transactions to continue to run. This is what ARIES uses in its protocol.

The DBMS uses additional log records to track checkpoint boundaries:

* **\<CHECKPOINT-BEGIN\>**: Indicates the start of the checkpoint. ==At this point, the DBMS takes a snapshot of the current ATT and DPT==, which are referenced in the \<CHECKPOINT-END\> record.
* **\<CHECKPOINT-END\>**: When the checkpoint has completed. It contains the ATT + DPT, captured just as the \<CHECKPOINT-BEGIN\> log record is written.

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220316234522342.png" alt="image-20220316234522342" style="zoom:25%;" />

> **Tips**:
>
> * CHECKPOINT-END 中的 ATT 和 DPT 在 CHECKPOINT-BEGIN 的时候生成
> * 对于第一个 CHECKPOINT-END 中的 ATT 和 DPT：
>   * T~2~ 在 CHECKPOINT-BEGIN 之前处于活跃状态，需要计入 ATT
>   * T~1~ 在 CHECKPOINT-BEGIN 之前已经提交，不需要计入 ATT (必须要 TXN-END)
>   * T~3~ 在 CHECKPOINT-BEGIN 之后 START，不需要计入 ATT；
>   * ==P~11~ 在 CHECKPOINT-BEGIN 之前被已提交的事务 T~1~ 修改，不需要计入到 DPT==
>   * ==P~22~ 在 CHECKPOINT-BEGIN 之前被未提交的事务 T~2~ 修改，需要计入 DPT==
>   * P~11~ 在 CHECKPOINT-BEGIN 之后被 T~2~，不需要计入 DPT；
> * 对于第二个 CHECKPOINT-END 中的  ATT 和 DPT:
>   * T~2~ 在 CHECKPOINT-BEGIN 之前执行了 COMMIT 命令，但是没有 TXN-END，处于 COMMITTING 状态，需要计入 ATT；
>   * T~3~ 在 CHECKPOINT-BEGIN 之前处于活跃状态，需要计入 ATT
>   * ==P~11~ 在 CHECKPOINT-BEGIN 之前被未提交的事务 T~2~ 修改，需要计入 DPT== (注意：虽然这个修改发生在上一个 CHECKPOINT-END 之前，但所有上一个 CHECKPOINT-BEGIN 之后的变更都应该算在本次 CHECKPOINT 之中)
>   * P~33~ 在 CHECKPOINT-BEGIN 之前被未提交的事务 T~3~ 修改，需要计入 DPT

# ARIES Recovery

The ARIES protocol is comprised of three phases. Upon start-up after a crash, the DBMS will execute the following phases as shown in Figure 5:

1. **Analysis**: Read the WAL to identify dirty pages in the buffer pool and active transactions at the time of the crash. At the end of the analysis phase the **ATT** tells the DBMS which transactions were active at the time of the crash. The **DPT** tells the DBMS which dirty pages might not have made it to disk.
2. **Redo**: Repeat all actions starting from an appropriate point in the log.
3. **Undo**: Reverse the actions of transactions that did not commit before the crash.

![image-20220316234814924](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220316234814924.png)

## Analysis Phase

Start from last checkpoint found via the database’s **MasterRecord** LSN.

1.  Scan log forward from the checkpoint.
2.  ==If the DBMS finds a TXN-END record, remove its transaction from ATT==.
3. All other records, add transaction to **ATT** with status **UNDO**, and on commit, change transaction status to **COMMIT**.
4. For UPDATE log records, if page *P* is not in the **DPT**, then add *P* to **DPT** and set *P* ’s ***recLSN*** to the log record’s LSN.

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220316235501563.png" alt="image-20220316235501563" style="zoom:25%;" />

## Redo Phase

The goal of this phase is for the DBMS to repeat history to reconstruct its state up to the moment of the crash. It will reapply all updates (even aborted transactions) and redo **CLRs**.

==The DBMS scans forward from log record containing *smallest* **recLSN** in the **DPT**==. For each update log record or **CLR** with a given LSN, the DBMS ==re-applies== the update <u>unless</u>:

* Affected page is not in the DPT, or
* Affected page is in DPT but that record’s LSN is less than the **recLSN** of the page in **DPT**, or
* Affected pageLSN (on disk) ≥ LSN.

To redo an action, the DBMS re-applies the change in the log record and then sets the affected page’s *pageLSN* to that log record’s LSN.

At the end of the redo phase, write TXN-END log records for all transactions with status COMMIT and remove them from the ATT.

## Undo Phase

In the last phase, the DBMS reverses all transactions that were active at the time of crash. These are all transactions with UNDO status in the ATT after the Analysis phase.

The DBMS processes transactions in reverse LSN order using the lastLSN to speed up traversal. As it reverses the updates of a transaction, the DBMS writes a CLR entry to the log for each modification.

Once the last transaction has been successfully aborted, the DBMS flushes out the log and then is ready to start processing new transactions.

## Example

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220317000521503.png" alt="image-20220317000521503" style="zoom:25%;" />

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220317000619586.png" alt="image-20220317000619586" style="zoom:25%;" />