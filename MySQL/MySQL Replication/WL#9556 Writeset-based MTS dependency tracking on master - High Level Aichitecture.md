APPROACH

The approach to take is to track in a map/hash the last transaction that used
each row hash (which represents a row in the database), up to a maximum history
log. Whenever a new transaction is processed, the writesets it uses are searched
in the history and the most recent transaction that used any of the writesets in
this transaction becomes the commit parent of the new transaction.

If the search returns no commit_parent, a variable that represents the oldest
transaction that can be a commit_parent is used. This variable also allows the
history to be cleared regularly and introduces support for transaction that
have DDL and need to be executed sequentially, while also supporting the switch
between commit order and writesets as source for the logical clock.

The following diagram provides an overview:

trx1 ---------- B, R(a), W(a), C ----------------------------------->
trx2 ---------------------B, R(b), W(b) C -------------------------->
trx3 ----------------------------- B, R(a), W(a), R(b), W(b) C ----->

* hashes:
  - trx1 commits => { a=trx1 }
  - trx2 commits => { a=trx1, b=trx2 }
  - trx3 commits => { a=trx3, b=trx3 }

* writesets:
  - trx1 = { a }
  - trx2 = { b }
  - trx3 = { a, b }

* Clocks/timestamps:
  - trx1 LC= { Nil , trx1 }
  - trx2 LC= { Nil , trx2 }
  - trx3 LC= { trx2, trx3 }

* Notes
  - trx3 depends on trx2 and trx1, but only trx2 is captured as dependency.
  - trx3 takes the most recently committed transaction that touched one of
    its items in the writeset

* The lower timestamp is calculated similarly to what is
  depicted on the oversimplified routine below

  on_commit(trx, ws):
     max=0
     foreach i in ws:
       if hash[i] > max or max == 0:
         max= hash[i]
       hash[i]= trx.commit_seq
     return max

DETAILS

* New system variable to control which method to capture dependencies
  between transactions:

- Name: binlog-transaction-dependency-tracking
  - Input Values: { COMMIT_ORDER | WRITESET | WRITESET_SESSION}
  - Default: COMMIT_ORDER
  - Description: This option controls whether transaction dependencies are
    established using write sets or commit timestamps. A server applying
    binary logs uses this information to determine which transactions can
    be applied in parallel.
    If this variable is equal to WRITESET_SESSION the master will store the
    last transaction issues by each client and will not allow reordering
    of transactions issued by the same client.
  - Dynamic: yes.
  - Scope: Global
  - Type: Enumeration

- Name: binlog-transaction-dependency-history-size
  - Input Values: [1, 1000000]
  - Default: 25000
  - Description: This option controls the maximum size of the row hash
    history that is kept to track transaction dependencies.
  - Dynamic: yes.
  - Scope: Global
  - Type: Enumeration

* Observability
  - It relies on the infrastructure that we have in place already and the
    results are observable with the tools that mine the binary log.

* Cross-version replication
  - Current MySQL 5.7 servers can automatically take advantage of the new
    commit_parents generated, even if they are not aware of how they were
    generated. There is no extra requirements other than support for the
    LOGICAL_CLOCK scheduler in MTS (so MySQL 5.6 will not use it).

* Rolling-upgrades
  - The upgrade procedures do not change as a results of this worklog.
    The slaves of masters which are configured with the variable
    binlog-transaction-dependency-tracking != COMMIT_ORDER
    may see a different history from the master, but that already happens
    between sessions if slave-preserve-commit-order is not ON.

* Group Replication
  - Servers in GR fulfill all the requirements for this worklod and can use
    the WRITE_SET option without new restrictions.
    If the members are configured with COMMIT_ORDER the recovery that happens
    when new members join the group will not take advantage of the WRITE_SET
    source to improve the parallelism on the node. Also, the asynchronous
    replication slaves that connect to it will also not be able to take
    advantage of the performance improvements.

* DDL
  DDL must be handle sequentialy on the slaves, so all transactions that don't
  have writeset (such as DDLs) are configured to run sequentially on the slave.

CAVEATS

* Using the WRITESET to generate the commit_parent makes it possible that the
  slaves see a state in the database that was never seen in the master.
  To reduce this effect the WRITESET_SESSION value can be used at the cost of
  significantly reducing the parallelism that can be achieved, in particular
  when for transactions ran be the same client.

* This worklog deals with DDLs, FK, filters and savepoints by reverting to
  commit order, which is sub-optimal way. Later we will deal specifically with
  optimizing the commit_parent generation for such cases.
