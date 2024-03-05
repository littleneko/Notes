# Old, Commit-Parent-Based Scheme
===============================

The old scheme for multi-threaded slave implemented in [WL#6314](https://dev.mysql.com/worklog/task/?id=6314) works
as follows.

- On master, there is a global counter. The counter is incremented
  before each storage engine commit.

- On master, before a transaction enters the prepare phase, the
  current value of the global counter is stored in the
  transaction. This number is called the commit-parent for the
  transaction.

- On master, the commit-parent is stored in the binary log in the
  header of the transaction.

- On slave, two transactions are allowed to execute in parallel if
  they have the same commit-parent.

# Problem With Commit-Parent-Based Scheme
=======================================

The old scheme allows less parallelism than would be possible.

The old scheme partitions the time line into intervals.  When a
transaction commits, the current time interval ends and a new begins.
Two transactions can execute in parallel if they were prepared within
the same time interval. The following picture illustrates the scheme:
```
Trx1 ------------P----------C-------------------------------->
                            |
Trx2 ----------------P------+---C---------------------------->
                            |   |
Trx3 -------------------P---+---+-----C---------------------->
                            |   |     |
Trx4 -----------------------+-P-+-----+----C----------------->
                            |   |     |    |
Trx5 -----------------------+---+-P---+----+---C------------->
                            |   |     |    |   |
Trx6 -----------------------+---+---P-+----+---+---C---------->
                            |   |     |    |   |   |
Trx7 -----------------------+---+-----+----+---+-P-+--C------->
                            |   |     |    |   |   |  |
```

Each horizontal line represents a transaction. Time progresses to the
right. P denotes the point in time when the commit-parent is read
before the prepare phase.  C denotes the point in time when the
transaction increases the global counter and thus begins a new
interval.  The vertical lines extending down from each commit show the
interval boundaries.

Trx5 and Trx6 are allowed to execute in parallel because they have the
same commit-parent (namely, the counter value set by Trx2).  However,
Trx4 and Trx5 are not allowed to execute in parallel, and Trx6 and
Trx7 are not allowed to execute in parallel.

But note that two transactions that hold all their respective locks at
the same point in time on the master are necessarily non-conflicting.
Thus, it would not be problematic to allow them to execute in parallel
on the slave.  In the above example, this has two implications:

- Trx4, Trx5, and Trx6 hold all their locks at the same time but Trx4
  will be executed in isolation.

- Trx6 and Trx7 hold all their locks at the same time but Trx7 will be
  executed in isolation.

It would be better if Trx4 could execute in parallel with Trx5 and
Trx6, and Trx6 could execute in parallel with Trx7.

# New, Lock-Based Scheme
======================

In the present worklog we implement a scheme that allows two
transactions to execute in parallel if they hold all their locks at
the same time.

We define the lock interval as the interval of time when a transaction
holds all its locks:

- The lock interval ends when the first lock(最开始申请的lock) is released in the
  storage engine commit.  For simplicity, we do not analyze the lock
  releases inside the storage engine; instead, we assume that locks
  are released just before the storage engine commit.

- The lock interval begins when the last lock is acquired. This may
  happen in the storage engine or in the server.  For simplicity, we
  do not analyze lock acquisition in the storage engine or in the
  server; instead, we assume that the last lock is acquired at the end
  of the last DML statement, in binlog_prepare. This works correctly
  both for normal transactions and for autocommitted transactions.

If Trx1, Trx2 are transactions, and Trx1 appears before Trx2, the
criterion for parallel execution is this:

**C1. Trx1, Trx2 can execute in parallel if and only if their locking**
**    intervals overlap.**

The following is an equivalent formulation:

**C2. Trx1, Trx2 can NOT execute in parallel, if and only if Trx1 has**
**    ended its locking interval before Trx2 has started its locking**
**    interval.**

The following illustrates the criteria (L denotes the beginning of the
locking interval and C denotes the end of the locking interval).

  - Can execute in parallel:
    Trx1 -----L---------C------------>
    Trx2 ----------L---------C------->

  - Can not execute in parallel:
    Trx1 -----L----C----------------->
    Trx2 ---------------L----C------->

To evaluate the locking criteria, we need to keep track of which
transactions have ended their locking intervals. To this end, we
assign a logical timestamp to each transaction:
transaction.sequence_number. We will need to store
transaction.sequence_number in the binary log.  Therefore, we step it
and assign it to the transaction just before the transaction enters
the flush stage.

In addition, we maintain the global variable
global.max_committed_transaction, which holds the maximal
sequence_number of all transactions that have ended their locking
intervals. The variable plays a role of the system commit logical clock.
Thus, before a transaction performs storage engine commit,
it sets global.max_committed_transaction to
max(global.max_committed_timestamp, transaction.sequence_number).

Each transaction needs to know which transactions it cannot execute in
parallel with. We define the *commit parent* of a transaction to be the
*newest* transaction that cannot execute in parallel with the transaction.
Thus, when the transaction begins its locking
interval, we store **global.max_committed_timestamp** into the variable
transaction.last_committed. Recall that the locking interval for
multi-statement transactions begins at the end of the last statement
before commit. Since we do not know a priori which is the last
statement, we store global.max_committed_timestamp into
transaction.last_committed at the end of *every* DML statement,
overwriting the old value. Then we will have the correct value when
the transaction is written to the binary log.

We store both timestamps in the binary log.

The condition for executing a transaction on the slave is as follows:

**C3. Slave can execute a transaction if the smallest sequence_number**
**    among all executing transactions is greater than**
**    transaction.last_committed.**

In order to check this condition, the slave scheduler maintains an
ordered sequence of currently executing transactions.  The first
transaction in the sequence is the one that appeared first in the
master binary log. In other words, it is the one with the smallest
value for transaction.sequence_number. The last transaction in
the sequence is the one that appeared last in the master binary log,
i.e., has the greatest value for transaction.transaction_counter

Before a transaction is taken for scheduling, the following condition is
checked:

 (*)  transaction_sequence[0].sequence_number > this.last_committed

Scheduling holds up until this condition becomes true. At successful
scheduling, the transaction is appended at the end of
transaction_sequence.

After a transaction has committed, it is effectively removed from the
sequence. (In the implementation, it is merely marked as done, which
tells the scheduler to ignore the transaction when it evaluates
condition (*)).


# Pseudo-code
===========

Master variables:
- int64 global.transaction_counter
- int64 global.max_committed_transaction
- int64 transaction.sequence_number
- int64 transaction.last_committed

Master logic in order of events of execution:

- in binlog_prepare:

    if this is not a transaction commit:
      transaction.last_committed = global.max_committed_transaction

- after it has been determined that the transaction is the next one to
  be flushed, and before transaction is flushed, the global transaction
  counter is stepped and copied to the transaction's sequence number:

    transaction.sequence_number = ++global.transaction_counter

- write transaction.sequence_number and transaction.last_committed to
  the binary log, in the transaction header;

- before transaction does storage engine commit:

    global.max_committed_transaction = max(global.max_committed_transaction,
                                           transaction.sequence_number)

  
  When @@global.binlog_order_commits is true, in principle we could reduce
  the max to an assignment:

    global.max_committed_transaction = transaction.sequence_number

  However, since binlog_order_commits is dynamic, if we do this, there will
  be a short time interval just after user change binlog_order_commits from
  0 to 1, during which the committing transactions' timestamps are not
  monotonically increasing, but binlog_order_commits == 1. If we used the
  assignment algorithm during this time period, transactions could have the
  wrong timestamps in the binary log, which could lead to conflicting
  transactions executing in parallel on the slave.

  To handle both cases using atomic operations we use the following algorithm:

  int64 old_value = transaction.sequence_number - 1;
  while (!my_atomic_cas64(&global.max_committed_transaction,
                          &old_value, transaction.sequence_number) &&
         transaction.sequence_number > old_value)
     ; // do nothing

Slave variables:

- transaction_sequence: ordered sequence containing all executing
  transactions in order of increasing sequence_number.

  (In the code, this is implemented using the existing Relay_log_info::GAQ.
  This is a circular queue of large, fixed size.)

Slave logic:

- before scheduler pushes the transaction for execution:

    wait until transaction_sequence[0].sequence_number >
               transaction.last_committed

  (The actual implementation will step through the list in the following
  manner:

    // The Low Water Mark is the newest transaction for which the scheduler
    // knows the following facts:
    // - the transaction has been committed;
    // - all older transactions have been committed.
    // LWM_plus_1 is the next transaction, i.e., the one that was the oldest
    // executing transaction last time that the schedule looked.

    global int LWM_plus_1;  // the same as transaction_sequence[0]

    function wait_until_transaction_can_be_scheduled(transaction):
      while true:
        while rli.GAQ[LWM_plus_1].is_committed:
          LWM_plus_1++
        if rli.GAQ[LWM_plus_1].sequence_number > transaction.last_committed:
          return
        wait until rli.GQA[LWM_plus_1] commits

- after transaction commits:
  GAQ[transaction.index].is_committed = true;

# Corner cases
============

 1. Handle exhaustion of the counters. (Note, this will never happen,
    because it takes 500 years to wrap a 64 bit counter if you have
    1,000,000,000 transactions per second, but we should handle it
    because people usually worry about such things.)

    If the counter wraps, we should rotate the binary log. The slave
    coordinator should make a checkpoint and wait for all currently
    running threads when it sees a rotate. This mechanism is already
    implemented for the current scheme, so all we need is a test case.

 2. Fall back to sequential execution.
    In certain cases a transaction is not scheduled in parallel to require
    all prior to have been finished (a similar policy exists in [WL#5569](https://dev.mysql.com/worklog/task/?id=5569)).
    Transaction header event is tagged with last_committed value of zero,
    and possibly with last_committed of zero.
    Those rare cases include:

    - "old" WL7165 unaware master transaction, incl wl6134-aware ones
    - DROP of multiple tables is logged such way with a second Query event
    - CREATE table ... SELECT ... from @user-var, or rand function, or
      INTVAR is generated for the query.

  3. Mixed engine transaction is logged as multiple (two) groups, where
     the 2nd is tagged to have the 1st as its commit parent.

# Optimizations
=============

 1. Access to global.transaction_counter does not need a lock because
    flushes are serialized on the master.

 2. The two numbers stored in the binary log will normally have a very
    small difference.  So instead of storing two 64-bit integers, we
    can store transaction.sequence_number as a 64-bit integer, and
    then store the difference as a 16-bit integer.  This will save 6
    bytes of space.  In the case that the difference is greater than
    65535, we store the number 65535.  This is safe, but may give less
    parallelism (in the case of 65536 or more concurrent
    transactions on the master).


==== Notes for future work ====

    The ideas of this section are *not* to be included in this worklog;
    they are merely mentioned here to prevent possible concerns and
    motivate the current design choice.

 1. Logical timestamp compressing in the binlog event
   
    If binlog_order_commits=OFF, the current policy of storing just
    two numbers in the binary log may give sub-optimal scheduling on
    the slave. This could in theory be fixed by replacing
    transaction.last_committed by a more complex data structure. However,
    this would be both more conceptually complex and require a more
    complex implementation, as well as more data in the binary log.
    It also only addresses a corner case (the default is
    binlog_order_commits=ON and there is no known reason to turn it
    off). Therefore, we do not intend to fix that in this worklog.

    Just for the record, we here outline the problem and a possible
    solution; this may be considered future work in case it is
    determined to be useful.

    The precise problem is that when binlog_order_commits=OFF, it is
    possible for two transactions to be committed in a different order
    than the order in which they were flushed. Thus, even if trx1 is
    written before trx2 to the binary log and thus
    trx1.sequence_number < trx2.sequence_number, it is possible that
    trx2 is committed before trx1. This gives the following possible
    scenario of sub-optimal scheduling on the slave:

     1. T1 flushes and is assigned transaction.sequence_number := 1
     2. T2 flushes and is assigned transaction.sequence_number := 2
     3. T2 commits and sets global.max_committed_transaction := 2
     4. T3 reads transaction.last_committed :=
        global.max_committed_transaction = 2
     5. T1 commits

    Then, the slave will not schedule T3 at the same time as T1 or T2.
    However, it would have been ok for T3 to execute in parallel with
    T1, since T1 held all locks at the same time as T3.

    To fix this, we would need to replace transaction.last_committed
    by the set of all sequence numbers that have not yet been committed.
    Currently, we know that this set only contains consecutive values,
    so it is conveniently stored as a single integer, but when commits
    may happen in a different order from the assignment of
    transaction.sequence_number, the set may be more complex. The set of
    sequence numbers that have not been committed can then be represented
    as a list of intervals, or as an offset plus a bitmap (if bit number
    N is set in the bitmap, it means that sequence number offset+N has
    been generated but not committed).

 2. Transaction distribution policies

    Among substantial factors to consider there's
    the style of the jobs assigning (feeding) to Workers.
    There are two being considered for the immediate evaluation, yet only
    the first one (A) implemented and is present in this section to contrast
    with the 2nd (B).

    A. At-Most-One (which had been designed yet by [WL#6314](https://dev.mysql.com/worklog/task/?id=6314)) Any worker
       can have only at most one transaction in its private queue.  In
       case all workers are occupied, which is actually expected 'cos
       the read time is about 1% of execution time, the Coordinator
       gets to waiting for release of any first of them.  Potential
       disadvantage is apparent, in the worst case all but one Worker
       can be without any assignment for duration of scheduling of few
       transactions.  And it actually scales up: the last of the
       idling workers would experience hungry time for duration of N-1
       scheduling times.

    B. The First Available (arguably ideal, not to be implemented in
       this WL) The idea is use a shared queue to hold the transaction
       events that Coordinator pushes into, and Worker pick up from
       the (other) end.  Such queue design had been done ago at the
       DB-type "classing" MTS.  The queue features concurrent access
       (push and pop) by multiple threads.[High Level Architecture](https://dev.mysql.com/worklog/task/?id=7165#tabs-7165-4)
