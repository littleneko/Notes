# 1 General logic
=================
Since MySQL is using a lock-based scheduler, **all threads that are in the prepare**
**phase but have not as yet committed can be executed in parallel on the slave**
**without violating the consistency.**

All transactions should be marked with a logical time-stamp, which identifies 
the last transaction that was committed when the current transaction entered the 
prepare stage. Details of this logical time stamp is given in the next section.
On the slave side all the transactions with the same time-stamp can execute in 
parallel. 

# 2 Master Side 
================
On master side the commit parent time-stamping can be done by using a Lamport 
clock

We implement a Logical clock for commit parent timestamp in the SQL engine 
layer.

The logic of the same is given by the following pseudocode.

Global:: Logical_clock commit_clock; 

2.1 in prepare stage:
   >> Fetch the time-stamp from the commit_clock, this will be stored as the 
commit parent of the transaction.
2.2 in commit stage: /* after the transaction is written to the binlog before 
the low-level commit */
   >> step the commit_clock; 

# 3 Slave Side 
===============
On the slave side, the coordinator thread will group the events based on the 
commit parent (i.e. transactions with same commit parent will be in the same 
group). All transaction in a group can be executed in parallel.

3.1  Event scheduling
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The events are scheduled to worker threads by picking a worker from the list of 
idle threads. if none are found the coordinator waits. 

3.2 Problems 
~~~~~~~~~~~~~~~
Since Coordinator waits after each group, in case the groups are small, the 
over-head of scheduling the events and waiting for the workers to finish may 
override the performance improvement  while applying events in parallel.
The best performance can be guaranteed when the number of clients doing writes 
ion master is high.

3.3 Proposed changes 
~~~~~~~~~~~~~~~~~~~~~~~
1. We will use the existing infrastructure of the slave workers and the
   coordinator. The change however will be to ignore the database partitioning
   information.
2. The thread association with a database will no longer be used. We will
   schedule the tasks in a group by assigning the threads in a round-robin
   method.
3. The coordinator will be blocked to make sure that the previous group has been
   applied before the event in the next group is scheduled. During this  time
   coordinator will do periodic check-pointing

3 New Options:
===============
3.1. On slave we should have a system variable 

slave_parallel_type=[logical_clock|database]

The option can only be changed after a stop slave;


REPLICATION CONSISTENCY ANALYSIS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

# BACKGROUND
==========

- Replication Consistency Criteria [1][2]

  1. Linearizabile or Atomic Consistency

     If a single client forwards a transaction Ta to a replica Ri and
     gets the result of Ta , any other transaction Tb sent later by
     this same client to any other replica Rj should be able to read
     the updates caused by Ta , assuming that no other transaction is
     submitted to the system between Ta and Tb .
     
  2. Sequential Consistency

     The result of any execution is the same as if the operations of
     all the processors were executed in some sequential order, and
     the operations of each individual processor appear in this
     sequence in the order specified by its program.

     So, it can be implemented using FIFO total order for applying all
     write operations in system replicas. Note that this does not
     avoid the problem outlined in [24], since sequential consistency
     ensures that all updates will be applied following the same
     sequence in all replicas. However, if replica Rj is overloaded
     and holds a long queue of pending updates (to be applied in the
     database), it might serve the first read accesses of Tb before
     applying the updates of Ta and, of course, before locally
     committing Ta.

  3. Causal consistency (Cache Consistency)

     This model only requires that accesses are sequentially
     consistent on a per-item basis.

     There are some replication protocols [...] that are able to
     comply with the requirements of this model but provide a
     consistency slightly higher, but that does not correspond to any
     already specified model. Such protocols are based on total order
     update propagation, but they allow that writeset application
     breaks such total order when writesets do not conflict (i.e.,
     there are no write-write conflicts) with any of the
     previously-delivered but not-yet-committed transactions.  Note
     that this ensures a per-item sequential consistency (as requested
     in the cache model), but also a per-transaction-writeset
     consistency (i.e., we can not commit half of a writeset WSA
     before writeset WSB and the other half of WSA afterward),
     although not a complete sequential consistency.

# ANALISYS
========

1. MySQL Asynchronous Replication and Single-threaded Applier

   - Details
 
     All backups/slaves execute the same transactions in the same
     order. No two different slaves execute the same two transactions
     in a different order.

   - End user impact
   
     Eventually, the user will see the same execution history on every
     slave. The commit history will match that of the master.

   - Consistency Criterion
     
     Sequential Consistency.
 
2. MySQL 5.6 Asynchronous Replication and Multi-threaded Applier

   - Details

     All backups/slaves executing transactions T1 and T2 on schema S
     will will apply T1 and T2 on the same order. In other words, no
     two different slaves executing the same two transactions on the
     same schema will commit them in a different order. Transactions
     changing different schemas are considered concurrent and can
     commit in a different order at two different slaves.

   - End user impact

     Eventually, and if updates stop on the master, the state on the
     slaves will converge to the same state, which matches that of the
     master.  While updates are ongoing, different execution histories
     can be observed on different slaves, and may be different from the
     execution history on the master. Execution histories differ only
     w.r.t. databases.

     Application invariants and semantics that require sequential
     consistency between all servers in the replication topology may
     be broken, but only if these semantics/invariants cross-reference
     schemas.

   - Consistency Criterion

     Causal Consistency. Causality is determined by the schema on
     which transactions operate.

3. MySQL 5.6 Asynchronous Replication and Multi-threaded Applier 

   - Details

     All backups/slaves executing transactions T1 and T2 marked as
     having prepared on different commit parents will apply T1 and T2
     on the same order among themselves. In other words, no two
     different slaves executing the same two transactions that
     prepared on different commit parents will commit them in a
     different order. Two transactions prepared on the same commit 
     parent can commit in different order at different slaves.

   - End user impact

     Eventually, and if updates stop on the master, the state on the
     slaves will converge to the same state, which matches that of the
     master.  While updates are ongoing, different execution histories
     can be observed on different slaves, and may be different from
     the execution history on the master. Execution histories differ
     w.r.t. transactions that are concurrent and prepared on the same
     commit parent.

     Application invariants and semantics that require sequential
     consistency between all servers in the replication topology may
     be broken.

   - Consistency Criterion

     Causal consistency. Causality is determined by the snapshot on
     which transactions prepare.

4. MySQL 5.6 Asynchronous Replication and Multi-threaded Applier


   - Details

     All backups/slaves executing transactions T1 and T2 marked as
     having prepared on the same or different commit parents will 
     apply T1 and T2 on the same order among themselves. In other words
     no two backups/slaves will externalize commit transactions in a 
     different order.

   - End user impact

     Eventually, the user will see the same execution history on every
     slave. The commit history will match that of the master.

   - Consistency Criterion

     Sequential consistency. 

# REFERENCES
==========

[1] [http://dl.acm.org/citation.cfm?id=1693858](http://dl.acm.org/citation.cfm?id=1693858)
[2] [http://web.iti.upv.es/~fmunyoz/research/pdf/TR-ITI-SIDI-2009003.pdf](http://web.iti.upv.es/~fmunyoz/research/pdf/TR-ITI-SIDI-2009003.pdf)
[24] [http://dl.acm.org/citation.cfm?id=1141442](http://dl.acm.org/citation.cfm?id=1141442)


[https://dev.mysql.com/worklog/task/?id=6314](https://dev.mysql.com/worklog/task/?id=6314)
