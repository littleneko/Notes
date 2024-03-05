```cpp
/**
  Type of metadata lock request.

  @sa Comments for MDL_object_lock::can_grant_lock() and
      MDL_scoped_lock::can_grant_lock() for details.
*/

enum enum_mdl_type {
  /*
    An intention exclusive metadata lock. Used only for scoped locks.
    Owner of this type of lock can acquire upgradable exclusive locks on
    individual objects.
    Compatible with other IX locks, but is incompatible with scoped S and
    X locks.
  */
  MDL_INTENTION_EXCLUSIVE= 0,
  /*
    A shared metadata lock.
    To be used in cases when we are interested in object metadata only
    and there is no intention to access object data (e.g. for stored
    routines or during preparing prepared statements).
    We also mis-use this type of lock for open HANDLERs, since lock
    acquired by this statement has to be compatible with lock acquired
    by LOCK TABLES ... WRITE statement, i.e. SNRW (We can't get by by
    acquiring S lock at HANDLER ... OPEN time and upgrading it to SR
    lock for HANDLER ... READ as it doesn't solve problem with need
    to abort DML statements which wait on table level lock while having
    open HANDLER in the same connection).
    To avoid deadlock which may occur when SNRW lock is being upgraded to
    X lock for table on which there is an active S lock which is owned by
    thread which waits in its turn for table-level lock owned by thread
    performing upgrade we have to use thr_abort_locks_for_thread()
    facility in such situation.
    This problem does not arise for locks on stored routines as we don't
    use SNRW locks for them. It also does not arise when S locks are used
    during PREPARE calls as table-level locks are not acquired in this
    case.
  */
  MDL_SHARED,
  /*
    A high priority shared metadata lock.
    Used for cases when there is no intention to access object data (i.e.
    data in the table).
    "High priority" means that, unlike other shared locks, it is granted
    ignoring pending requests for exclusive locks. Intended for use in
    cases when we only need to access metadata and not data, e.g. when
    filling an INFORMATION_SCHEMA table.
    Since SH lock is compatible with SNRW lock, the connection that
    holds SH lock lock should not try to acquire any kind of table-level
    or row-level lock, as this can lead to a deadlock. Moreover, after
    acquiring SH lock, the connection should not wait for any other
    resource, as it might cause starvation for X locks and a potential
    deadlock during upgrade of SNW or SNRW to X lock (e.g. if the
    upgrading connection holds the resource that is being waited for).
  */
  MDL_SHARED_HIGH_PRIO,
  /*
    A shared metadata lock for cases when there is an intention to read data
    from table.
    A connection holding this kind of lock can read table metadata and read
    table data (after acquiring appropriate table and row-level locks).
    This means that one can only acquire TL_READ, TL_READ_NO_INSERT, and
    similar table-level locks on table if one holds SR MDL lock on it.
    To be used for tables in SELECTs, subqueries, and LOCK TABLE ...  READ
    statements.
  */
  MDL_SHARED_READ,
  /*
    A shared metadata lock for cases when there is an intention to modify
    (and not just read) data in the table.
    A connection holding SW lock can read table metadata and modify or read
    table data (after acquiring appropriate table and row-level locks).
    To be used for tables to be modified by INSERT, UPDATE, DELETE
    statements, but not LOCK TABLE ... WRITE or DDL). Also taken by
    SELECT ... FOR UPDATE.
  */
  MDL_SHARED_WRITE,
  /*
    A version of MDL_SHARED_WRITE lock which has lower priority than
    MDL_SHARED_READ_ONLY locks. Used by DML statements modifying
    tables and using the LOW_PRIORITY clause.
  */
  MDL_SHARED_WRITE_LOW_PRIO,
  /*
    An upgradable shared metadata lock which allows concurrent updates and
    reads of table data.
    A connection holding this kind of lock can read table metadata and read
    table data. It should not modify data as this lock is compatible with
    SRO locks.
    Can be upgraded to SNW, SNRW and X locks. Once SU lock is upgraded to X
    or SNRW lock data modification can happen freely.
    To be used for the first phase of ALTER TABLE.
  */
  MDL_SHARED_UPGRADABLE,
  /*
    A shared metadata lock for cases when we need to read data from table
    and block all concurrent modifications to it (for both data and metadata).
    Used by LOCK TABLES READ statement.
  */
  MDL_SHARED_READ_ONLY,
  /*
    An upgradable shared metadata lock which blocks all attempts to update
    table data, allowing reads.
    A connection holding this kind of lock can read table metadata and read
    table data.
    Can be upgraded to X metadata lock.
    Note, that since this type of lock is not compatible with SNRW or SW
    lock types, acquiring appropriate engine-level locks for reading
    (TL_READ* for MyISAM, shared row locks in InnoDB) should be
    contention-free.
    To be used for the first phase of ALTER TABLE, when copying data between
    tables, to allow concurrent SELECTs from the table, but not UPDATEs.
  */
  MDL_SHARED_NO_WRITE,
  /*
    An upgradable shared metadata lock which allows other connections
    to access table metadata, but not data.
    It blocks all attempts to read or update table data, while allowing
    INFORMATION_SCHEMA and SHOW queries.
    A connection holding this kind of lock can read table metadata modify and
    read table data.
    Can be upgraded to X metadata lock.
    To be used for LOCK TABLES WRITE statement.
    Not compatible with any other lock type except S and SH.
  */
  MDL_SHARED_NO_READ_WRITE,
  /*
    An exclusive metadata lock.
    A connection holding this lock can modify both table's metadata and data.
    No other type of metadata lock can be granted while this lock is held.
    To be used for CREATE/DROP/RENAME TABLE statements and for execution of
    certain phases of other DDL statements.
  */
  MDL_EXCLUSIVE,
  /* This should be the last !!! */
  MDL_TYPE_END};
```
