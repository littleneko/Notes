# OVERVIEW
========

Group Replication parallel applier implementation is based on
[WL#7165](https://dev.mysql.com/worklog/task/?id=7165): "MTS: Optimizing MTS scheduling by increasing the
parallelization window on master". In that feature, two transactions
are parallelize if we can tell that they have not blocked each
other during their execution.

The parallelization is expressed using two counters that are added
to every transaction header (Gtid_log_event): last_committed and
sequence_number.

On this worklog we will take advantage of the certifier component to
populate the parallelization indexes mentioned above in order to
speed up the apply time of remote transactions.
# DEFINITIONS
===========
Before going into details lets first present the terms that will be
used on this design.

  transaction.sequence_number: is the monotonically increasing
transaction number counter, incremented by each transaction. It is
set on the Gtid_log_event that starts each transaction. From now on
We will refer to it as trx.SN. Please see High-Level
Specification of [WL#7165](https://dev.mysql.com/worklog/task/?id=7165) for further details.
This should not be confused with certification sequence number that
is described below.

  transaction.last_committed: is the version (transaction number) on
which the transaction was executed relative to trx.SN, that is, the
trx.SN (transaction number) before the current transaction commits.
It is set on the Gtid_log_event that starts each transaction. From
now on we will refer to it as trx.LC. Please see High-Level
Specification of [WL#7165](https://dev.mysql.com/worklog/task/?id=7165) for further details.

  certification info: memory structure used by Group Replication
certification component to detect conflicting transactions. It maps
transaction write sets to snapshot versions. Please see High-Level
Specification of [WL#6833](https://dev.mysql.com/worklog/task/?id=6833) for more details.

  write set: set of hashes that identify unequivocally the updated
rows by the transaction.

  snapshot version: is the version on which the transaction was
executed. It is the value of GTID_EXECUTED before transaction
commits. Example: UUID1:1-5, UUID2:1.

  certification info sequence_number: is the increasing remote
transaction number counter in the certifier.

# REPLICATION PATH
================
On [WL#7165](https://dev.mysql.com/worklog/task/?id=7165) the parallelization indexes are saved to Gtid_log_event
on master binary log, then events are replicated to slave and slave
parallel applier will use those indexes to schedule the events.

On this worklog the path is slightly different, when a transaction
is committed it is captured and sent to all group members for
certification. At certification point, transactions can be
considered as:
 local:  that was started and broadcast from this server;
 remote: committed on another server.

This worklog will only handle the remotes transactions. Local ones,
after certification, are committed and logged like on a regular
master. On local transactions, the parallelization indexes stored on
binary log are the ones computed by [WL#7165](https://dev.mysql.com/worklog/task/?id=7165).

For remote transactions, after certification we do the computation
described below, being the parallelization indexes stored on
group_replication_applier channel relay log and then read by
parallel applier to schedule the events.

# PARALLELIZATION INDEXES
=======================

Note: These indexes are referred as logical timestamps on [WL#7165](https://dev.mysql.com/worklog/task/?id=7165):
"MTS: Optimizing MTS scheduling by increasing the parallelization
window on master".

## trx.SN (transaction sequence_number)
------------------------------------

Like presented above, trx.SN is the monotonically increasing
transaction number counter, which is assigned to each transaction on
commit. On Group Replication we have the same monotonic behaviour on
certifier component, that is, all transactions go through
certification process sequentially, so we can maintain and assign a
transaction counter here.

We will have a counter:
  parallel_applier_sequence_number
that will be monotonically incremented after each positively
certified remote transaction.

We will map this parallel_applier_sequence_number in a counter at
Group Replication Certifier class. Its value will be
assigned to each current remote transaction, trx.SN, set on
Gtid_log_event, after positively certified.

parallel_applier_sequence_number will be tracked by write set, that
is, each write set will be recorded on the certification not only
with the snapshot version but also the transaction sequence_number.
This will allow to compute the dependency graph of each transaction
and with that information compute the correct last_committed value,
as explained on Example 3.

This counter, parallel_applier_sequence_number, will be initialized
to 2 whenever the group starts or members join.

Summary of parallel_applier_sequence_number initialization:
  group member join:
    parallel_applier_sequence_number= 2

Why 2?
View_change_log_event sequence number is always 0, so the first
transaction will have:
  last_committed:  1
  sequence_number: 2
This way indexes of transactions never intersect with view change.

## trx.LC (transaction last_committed)
-----------------------------------

The MySQL Group Replication certification ensures that two parallel
conflicting transactions, which update one or more common rows, are
not allowed to commit. The rule is that the first one to reach
certification will be accepted and the other will be rejected
(rollback).

Certification info contains the already committed but not yet
applied transactions on all members, that is, transactions that are
known to be positively certified but are still waiting on remote
queues to be applied. Or if already applied all group members are
not aware of that. Please see garbage collection procedure on
[WL#6833](https://dev.mysql.com/worklog/task/?id=6833) for further details. Certification info, except on a clean
group start, is never empty.

On parallel applier we need a more fine filter than the above one,
because two non-conflicting transactions may not be allowed to be
applied in parallel. Despite when they were executed there was no
certification conflict, there may be a parallelization conflict.
One example can be seen below (EX2) through a look
into the certification info content after two transactions are
executed:
  -----------------------------------------------------------
  Trx  | WS       | SV        | Update
  -----------------------------------------------------------
  T1   | ws1      | UUID1:1   | INSERT INTO t1 VALUES (1)
  T2   | ws1, ws2 | UUID1:1-2 | UPDATE t1 SET c1=2 WHERE c1=1
  -----------------------------------------------------------

Transaction T2 does not conflict (intersecting write sets) with T1,
since T2 snapshot version includes T1 one. But these two
transactions cannot be applied in parallel, T2 may be started before
T1. This will make it to silently fail since 1 is not on the table
yet.

So we need to increase the criteria for conflict detection in
order to correctly specify which transactions can be applied in
parallel.

We already mentioned that certification info contains all ongoing or
not yet applied on all members transactions. So after the current
transaction is certified we need to check if the write sets of the
current transaction are present on certification info, before
updating it if they are it means that we need to mark this
transaction as non parallel with the previous ones.

Lets see the outcome of a given execution on a group to analyze how
should trx.LC be set on transactions depending on its write sets.
On Example 3 (EX3) we see the write sets of a sequence of
transactions as they arrive certification and how the trx.LC and
trx.SN progress
  -----------------------------------------------------------------
  Trx  | WS       | trx.LC  | trx.SN
  -----------------------------------------------------------------
       |          |         | 0      (group boot)
  T1   | ws1      | 1       | 2  ---| T1 and T2 can be applied in
  T2   | ws2      | 1       | 3  ---| parallel
  T3   | ws1, ws3 | 2       | 4  ---| T3 can not be applied in
                                      parallel with T1, so trx.LC is
                                      set to T1 trx.SN
  T4   | ws4      | 1       | 5     |
  T5   | ws5      | 1       | 6     |
  T6   | ws5, ws6 | 6       | 7  ---| T6 can not be applied in
                                      parallel with T5, so trx.LC is
                                      set to T5 trx.SN
  T7   | ws7      | 1       | 8     |
  T8   | ws8      | 1       | 9  ---|
  -----------------------------------------------------------------

We can see on example EX3, that we have the following dependency
graph:
  T3 does depend on T1;
  T6 does depend on T5;
  all others do not depend on any transaction.


## No write set case
-----------------
On Group Replication some transactions may not have write set, like
empty transactions with GTID_NEXT specified or DDL. For those we
cannot check conflicts, and consequently, we do not know if them can
be applied in parallel. So we need to follow the pessimistic
approach and run them sequentially.

Example (EX4):
  -----------------------------------------------------------------
  Trx  | WS       | trx.LC  | trx.SN
  -----------------------------------------------------------------
       |          |         | 0      (group boot)
  T1   |          | 1       | 2     |
  T2   | ws1      | 2       | 3     |
  T3   | ws2      | 2       | 4     |
  T4   |          | 4       | 5     |
  T5   | ws1      | 5       | 6     |


Algorithm (AL1) to determine if a given remote transaction can be
applied in parallel:
  1) Transaction is certified positively
       trx.LC= parallel_applier_last_committed_global
  2) Assign parallel_applier_sequence_number to trx.SN
       trx.SN= parallel_applier_sequence_number
  3) Transaction have write set?
     a) Yes: Check if any of the transaction write set exists on
             the certification info.
             If write sets sequence number is greater than
             trx.LC then update trx.LC
     b) No:  parallel_applier_last_committed_global=
               parallel_applier_sequence_number
  4) Insert/update current transaction write set and snapshot
     version on certification info.
  5) Increment parallel_applier_sequence_number

-------------
Special cases
-------------

## Certification info garbage collection
-------------------------------------

Since the procedure to find
parallel_applier_last_committed_global value, as explained in
algorithm AL1, depends on certification info content, every update
to certification info should be reflected on
parallel_applier_last_committed_global (and on trx.LC).

Lets see a example (EX5) to visualize the problem. Incorrect output
of a given execution including a certification garbage collection
run:
  -----------------------------------------------------------------
  Trx  | WS       | trx.LC  | trx.SN
  -----------------------------------------------------------------
       |          |         | 0  (group boot)
  T1   | ws1      | 1       | 2
  T2   | ws2      | 1       | 3
       |          |         |    (garbage collection procedure
                                  T1 is purged)

So we will end up with the following content on certification info
  -----------------------------------------------------------------
  Trx  | WS       | trx.LC  | trx.SN
  -----------------------------------------------------------------
  T2   | ws2      | 1       | 3

If a new transaction that touches ws1 is executed we will end up
with:
  -----------------------------------------------------------------
  Trx  | WS       | trx.LC  | trx.SN
  -----------------------------------------------------------------
  T2   | ws2      | 1       | 3
  T3   | ws1      | 1       | 4
  T4   | ws4      | 1       | 5

That is, T1 and T3 can be executed in parallel, which is incorrect
since both update ws1.
To prevent this incorrect behaviour, every time a certification
garbage collection run happens, a new parallelization window is open
stating that all transactions executed after this point will need to
wait for the previous transactions to be complete to be applied.
This is done by updating the
parallel_applier_last_committed_global variable to current
parallel_applier_sequence_number.

Correct output of trx.LC and trx.SN when garbage collection
procedure is considered, example (EX6):
  -----------------------------------------------------------------
  Trx  | WS       | trx.LC  | trx.SN
  -----------------------------------------------------------------
       |          |         | 0  (group boot)
  T1   | ws1      | 1       | 2
  T2   | ws2      | 1       | 3
       |          |         |    (garbage collection procedure
                                  T1 is purge)

The certification info and transaction counters will now be
reflected by
  -----------------------------------------------------------------
  Trx  | WS       | trx.LC  | trx.SN
  -----------------------------------------------------------------
  T2   | ws2      | 1       | 3

If a new transaction that touches ws1 is executed we will end up
with:
  -----------------------------------------------------------------
  Trx  | WS       | trx.LC  | trx.SN
  -----------------------------------------------------------------
  T2   | ws2      | 1       | 3
  T3   | ws1      | 3       | 4
  T4   | ws4      | 3       | 5

Now, T1 and T2 can not be applied in parallel, which is correct
since both update the same row.


## View_change_log_event
---------------------

View_change_log_event transaction needs to be applied sequentially
because it is the termination condition for distributed recovery
procedure, and applier must not be executing any other transaction
in parallel to avoid termination errors or data after the
View_change_log_event transaction is applied.

To fulfil this requirement, when a View_change_log_event
transaction is queued to applier, the following will happen:
  1) View_change_log_event trx.LC= 0
     View_change_log_event trx.SN= 0

The values (0,0) force applier to apply the View_change_log_event
sequentially and resets applier counters.

On a joiner, after View_change_log_event queue, the sequence number
algorithm will have the following defaults for future transactions:
  parallel_applier_last_committed_global= 1
  parallel_applier_sequence_number= 2
which are always disjoint of the 0 values of View_change_log_event.

On existing group members, the group_replication_applier channel
relay log is rotated, the View_change_log_event is logged and the
parallel_applier_last_committed_global and
parallel_applier_sequence_number maintain their values, which are
disjoint of the view ones.

Again, lets see the outcome of a correct execution which includes a
View_change_log_event transaction, example (EX7):
  -----------------------------------------------------------------
  Trx  | WS       | trx.LC  | trx.SN
  -----------------------------------------------------------------
       |          |         | 0  (group boot)
  T1   | ws1      | 1       | 2
  T2   | ws2      | 1       | 3
       |          | 0       | 0  (view change)
  T3   | ws3      | 1       | 4


## Session commit order
--------------------

Yet another special case is the session consistency, that is,
updates made by the same client on the same server must preserve its
order.

This is ensured by server option
  --slave_preserve_commit_order=ON
which is required when we enable parallel applier on Group
Replication.


Summary of parallel_applier_last_committed_global update:
  garbage collection procedure purges data from certification info:
    parallel_applier_last_committed_global=
        parallel_applier_sequence_number

  after transaction is certified positively:
    transaction does not have write set:
      parallel_applier_last_committed_global=
          parallel_applier_sequence_number



# SERVER OPTIONS
==============
Applier on Group Replication will follow server configuration
options slave_parallel_workers and slave-parallel-type, like
asynchronous replication.


# CHALLENGES
==========

## Wait until view change
----------------------

Due to the specificities of [WL#7165](https://dev.mysql.com/worklog/task/?id=7165) implementation, we will need to
change how WAIT_UNTIL_VIEW_CHANGE stops reading and applying relay
logs. MySQL Group Replication view change event transaction is
composed by:
  GTID
  BEGIN
  VIEW_CHANGE
  COMMIT
Parallel applier does not support to be stopped on a ongoing
transaction, it must be stopped on transactions boundaries, so
WAIT_UNTIL_VIEW_CHANGE will be changed to stop after view change
event transaction is committed. Meaning that the executed and logged
view change event on a joiner is the one fetched during recovery and
not the one generated by the joiner itself (the previous behavior).
When WAIT UNTIL finds the view change event, it sets a flag that
will cause the WAIT UNTIL to stop after transaction is applied.
View change transaction is always applied sequentially, that is, its
trx.LC and trx.SN never intersect with any other transaction.

## [WL#7165](https://dev.mysql.com/worklog/task/?id=7165) applier recovery
------------------------
[WL#7165](https://dev.mysql.com/worklog/task/?id=7165) applier recovery is based on master log name and position,
this makes very difficult to enable parallel applier on Group
Replication. The following example (EX7) shows why:

 ------   ------   ------
 | S1 |   | S2 |   | S3 |
 ------   ------   ------
   |________|________|

For simplicity only S1 and S2 do writes:
 * S1 executes T1
 * S2 executes T2
Transactions are sent to all group members, for simplicity again,
lets only observe S3, on which T1 and T2 are remote transactions.
Lets also assume that both T1 and T2 only have one event, which
length is 100 bytes.

So in S3 Group Replication applier (relay log) we would have:
# at 4
#150101 00:00:25 server id 3  end_log_pos 122   Start: binlog v4
# at 126
#150101 00:00:26 server id 1  end_log_pos 100    T1
# at 226
#150101 00:00:26 server id 2  end_log_pos 100    T2

Please note the end_log_pos 100 on both transactions.
Since on Group Replication we have several masters there is not a
single master position to follow.
So we will need to add a exception to [WL#7165](https://dev.mysql.com/worklog/task/?id=7165) applier recovery to
execute a different recovery procedure. This exception will only be
available on Group Replication applier channel.
Since we have always GTID_MODE=ON on Group Replication, the simplest
way to solve this issue it is on [WL#7165](https://dev.mysql.com/worklog/task/?id=7165) applier recovery ignore
the positions completely, seek the current relay log to the
beginning and start from there. Already applied transactions will be
skipped due to GTIDs auto skip feature and applier will resume from
the last applied transaction.
On 5.8 internal [WL#7165](https://dev.mysql.com/worklog/task/?id=7165) applier recovery procedure should ignore
positions and only rely on GTIDs.

This approach works if transactions do not span multiple relay logs,
that can happen on the following scenarios:
 1. flush relay logs in the middle of writing a transaction;
 2. max_relay_log_size exceeded in the middle of writing a
    transaction;
 3. user does CHANGE MASTER TO MASTER_LOG_POS forcing it to start in
    the middle of a transaction;
 4. user kills the receiver thread in the middle of writing a
    transaction, then reconnects using auto_position=0;

#2 only happens in 5.6, so it's not a problem. #3 and #4 are not
possible with Group Replication. However, seems that #1 could
happen: group replication uses queue_event to write the relay log,
and queue_event will acquire and release LOG_lock. Since a
transaction consists of multiple events, group replication will have
a sequence of calls to queue_event for any given transaction. If
FLUSH RELAY LOGS happens between two such calls, the second relay
log will begin with a half transaction.

To prevent that user must be disallowed to execute
  FLUSH RELAY LOGS FOR CHANNEL "group_replication_applier";
while Group Replication is running.

FLUSH RELAY LOGS without FOR CHANNEL does not affect Group
Replication channels, so no problem there.
