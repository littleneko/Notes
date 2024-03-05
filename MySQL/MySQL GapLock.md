READ COMMITTED
Gap locking is only used for foreign-key constraint checking and duplicate-key checking.

[`INSERT`](https://dev.mysql.com/doc/refman/8.0/en/insert.html) sets an exclusive lock on the inserted row. This lock is an index-record lock, not a next-key lock (that is, there is no gap lock) and does not prevent other sessions from inserting into the gap before the inserted row.
Prior to inserting the row, a type of gap lock called an insert intention gap lock is set. This lock signals the intent to insert in such a way that multiple transactions inserting into the same index gap need not wait for each other if they are not inserting at the same position within the gap. Suppose that there are index records with values of 4 and 7. Separate transactions that attempt to insert values of 5 and 6 each lock the gap between 4 and 7 with insert intention locks prior to obtaining the exclusive lock on the inserted row, but do not block each other because the rows are nonconflicting.
If a duplicate-key error occurs, a shared lock on the duplicate index record is set. This use of a shared lock can result in deadlock should there be multiple sessions trying to insert the same row if another session already has an exclusive lock. This can occur if another session deletes the row. Suppose that an `InnoDB` table `t1` has the following structure:
```sql
CREATE TABLE t1 (i INT, PRIMARY KEY (i)) ENGINE = InnoDB;
```
Now suppose that three sessions perform the following operations in order:
Session 1:
```sql
START TRANSACTION;
INSERT INTO t1 VALUES(1);
```

Session 2:
```sql
START TRANSACTION;
INSERT INTO t1 VALUES(1);
```

Session 3:
```sql
START TRANSACTION;
INSERT INTO t1 VALUES(1);
```

Session 1:
```sql
ROLLBACK;
```
The first operation by session 1 acquires an exclusive lock for the row. The operations by sessions 2 and 3 both result in a duplicate-key error and they both request a shared lock for the row. When session 1 rolls back, it releases its exclusive lock on the row and the queued shared lock requests for sessions 2 and 3 are granted. At this point, sessions 2 and 3 deadlock: Neither can acquire an exclusive lock for the row because of the shared lock held by the other.


[1] [https://dev.mysql.com/doc/refman/8.0/en/innodb-locks-set.html](https://dev.mysql.com/doc/refman/8.0/en/innodb-locks-set.html)
[2] [https://dev.mysql.com/doc/refman/5.7/en/innodb-transaction-isolation-levels.html](https://dev.mysql.com/doc/refman/5.7/en/innodb-transaction-isolation-levels.html)
