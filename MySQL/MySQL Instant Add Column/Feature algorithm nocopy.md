# About

This document describes the architecture and implementation details for the new `ALTER TABLE` option `ALGORITHM=NOCOPY`, which is based on the previously implemented [Instant ADD COLUMN feature](https://www.yuque.com/littleneko/note/gtptal) and allows more schema change operations to be performed faster without a full table rebuild.

# Goals

The [Instant Add Column feature](https://www.yuque.com/littleneko/note/gtptal) made it possible to add columns without rebuilding tables, i.e. as a metadata only instant operation.

However, combining `ADD COLUMN` with other operations that do not require rebuilding the entire table (such as `ADD/DROP INDEX`) would trigger a full table rebuild.

That is, the following operation would be instant:

```sql
ALTER TABLE t ADD COLUMN c INT;
```

but the following operations would be potentially slow due to a full table rebuild:

```sql
ALTER TABLE t ADD COLUMN d INT, ADD INDEX (c); -- equivalent to ALTER TABLE ... ALGORITHM=INPLACE
ALTER TABLE t ADD COLUMN e INT, ADD INDEX (e), DROP INDEX c; -- equivalent to ALTER TABLE ... ALGORITHM=INPLACE
```

The reason is that even though `ADD INDEX` or `DROP INDEX` do not require a table rebuild, they are also not instant and thus, are incompatible with `ALGORITHM=INSTANT`. In which case MySQL executes `ALTER TABLE` as if `ALGORITHM=INPLACE` was specified, and for a column addition `ALGORITHM=INPLACE` means a table rebuild.

The goal of this work is to combine the best of both worlds and make operations like that faster by executing `ADD COLUMN` instantly, and creating/dropping indexes without a table rebuild at the same time as they would normally be executed without `ADD COLUMN`.

From the internal architecture perspective, that is possible to implement by introducing a new `ALTER TABLE` algorithm `NOCOPY`. `ALGORITHM=NOCOPY` is supposed to resolve the ambiguity of `ALGORITHM=INPLACE`, which means either a table rebuild for some operations (like `ADD COLUMN`) or fast operations like creating or dropping indexes.

Unlike `ALGORITHM=INPLACE`, `ALGORITHM=NOCOPY` would perform the specified operations without a full table rebuild, if possible, or return an error otherwise.

For example, with this feature implemented, the following operations would avoid rebuilding the table:

```sql
ALTER TABLE t ADD COLUMN d INT, ADD INDEX (c); -- equivalent to ALTER TABLE ... ALGORITHM=NOCOPY
ALTER TABLE t ADD COLUMN e INT, ADD INDEX (e), DROP INDEX c; -- equivalent to ALTER TABLE ... ALGORITHM=NOCOPY
```

`ALGORITHM=NOCOPY` allows the above operations to be performed by:

- instantly adding a column;
- scanning the clustered index to create the new index;
- scanning all pages of the index being dropped to mark them as free.

Comparing to `ALGORITHM=INPLACE`, the same operations would require:

- rebuilding the clustered index with a new column included;
- rebuilding all existing secondary indexes (except the index which is being dropped);
- building the new index;

One extra benefit of `ALGORITHM=NOCOPY` is that a DBA can also request it explicitly, in which case `ALTER TABLE` will raise an error if the operation cannot be performed fast without rebuilding the entire table. For example:

```sql
mysql> ALTER TABLE t DROP COLUMN e, ALGORITHM=NOCOPY;
ERROR 1846 (0A000): ALGORITHM=NOCOPY is not supported. Reason: incompatible operation. Try ALGORITHM=COPY/INPLACE.

mysql> ALTER TABLE t DROP PRIMARY KEY, ADD PRIMARY KEY (c), ALGORITHM=NOCOPY;
ERROR 1846 (0A000): ALGORITHM=NOCOPY is not supported. Reason: incompatible operation. Try ALGORITHM=COPY/INPLACE.
```

# High Level Architecture

This work is loosely based on the MariaDB patch for [MDEV-13134](https://jira.mariadb.org/browse/MDEV-13134). However, MariaDB currently does not allow `ADD COLUMN` + `ADD/DROP INDEX` as a `NOCOPY` operation (this is tracked as [MDEV-16291](https://jira.mariadb.org/browse/MDEV-16282) which was not implemented at the moment of this writing).

Even though many `ALTER TABLE` operations are compatible with `ALGORITHM=NOCOPY` (see [Supported Operations](#supported-operations) below), only the following combination required significant work:

```sql
ALTER TABLE t ADD new_col, ADD INDEX (new_col [, ...]);
```

Adding the index requires scanning the table, so it may take time for large tables. On the other hand, we want the table to be accessible while we are building the index, so we can only add the new column at the end of this operation. However, [Sorted Index Builds](https://dev.mysql.com/doc/refman/5.7/en/sorted-index-builds.html) are implemented in InnoDB by scanning the clustered index and producing row tuples used to create index records. In this particular case, since the index is being created on a new column, the clustered index does not yet have a field corresponding to the new column. So the tricky part here is building "fake" row tuples consisting of existing fields and the default value for the new column to build the index.

This is illustrated on the following diagram:

![algorithm_nocopy.svg](https://littleneko.oss-cn-beijing.aliyuncs.com/img/1594715571427-7e562a6e-291b-4499-94cf-498ea1dc44c0.svg)

# Supported Operations

The following operations are compatible with `ALGORITHM=NOCOPY`, so they can be combined in a single `ALTER TABLE`:

- all `ALGORITHM=INSTANT` operations,i.e. those marked as "**Instant: Yes**" in the [Online DDL Operations](https://dev.mysql.com/doc/refman/8.0/en/innodb-online-ddl-operations.html) overview in the MySQL 8.0 Reference Manual:
   - `ADD COLUMN`, with all limitations described in the [Limitations and Caveats section](https://git.xiaojukeji.com/foundation/mysql-server-5.7/wikis/feature-instant-add-column#limitations-and-caveats) of the Instant ADD COLUMN feature.
   - adding / dropping `VIRTUAL` generated columns
   - `MODIFY c ENUM`
   - `MODIFY c SET`
   - `SET DEFAULT`
   - `DROP DEFAULT`
- all operations that do not require a table rebuild, i.e. those marked as "**Rebuilds Table: No**" in the [Online DDL Operations](https://dev.mysql.com/doc/refman/8.0/en/innodb-online-ddl-operations.html) overview in the MySQL 8.0 Reference Manual:
   - `ADD INDEX`
   - `DROP INDEX`
   - `RENAME INDEX`
   - `CHANGE old_name new_name same_type` (renaming a column)
   - `CHANGE c c VARCHAR(M)` (extending a `VARCHAR` size)
   - `AUTO_INCREMENT=next_value`
   - `ADD FOREIGN KEY`
   - `DROP FOREIGN KEY`
   - `STATS_PERSISTENT=..., STATS_SAMPLE_PAGES=..., STATS_AUTO_RECALC=...`
   - `RENAME TO` (renaming a table)

# Limitations And Caveats

- There are incompatible operations. When one of the following operations is present in an `ALTER TABLE` without explicit `ALGORITHM=NOCOPY`, a slower table-rebuilding algorithm will be used. If there is an explicit `ALGORITHM=NOCOPY` specification, an error will be returned:
   - `ADD COLUMN ... FIRST / AFTER`
   - `ADD COLUMN ... STORED`
   - `MODIFY COLUMN ... FIRST / AFTER`
   - `MODIFY COLUMN ... STORED`
   - `DROP COLUMN` (except `VIRTUAL` columns)
   - `CHANGE v v ... AS other_expression VIRTUAL` (changing a `VIRTUAL` column expression)
   - `ADD FULLTEXT INDEX` (if there is no an existing `FTS_DOC_ID` column)
   - `ADD PRIMARY KEY`
   - `DROP PRIMARY KEY`
   - `CHANGE c1 c1 other_data_type`
   - `MODIFY COLUMN c1 ... NULL` (for a `NOT NULL` column)
   - `MODIFY COLUMN c1 ... NOT NULL` (for a `NULL` column)
- Adding a column and creating an index on the same column cannot be done online, i.e. is only possible with read-only access to the table by other connections. This is a limitation of the [InnoDB DDL log](https://dev.mysql.com/doc/refman/5.7/en/innodb-online-ddl-space-requirements.html), and can be fixed later:
```sql
mysql> ALTER TABLE t1 ADD COLUMN c INT, ADD INDEX (c), ALGORITHM=NOCOPY, LOCK=NONE;
ERROR 0A000: LOCK=NONE is not supported. Reason: ADD COLUMN col..., ADD INDEX(col). Try LOCK=SHARED.
```

But this works:
```sql
mysql> ALTER TABLE t1 ADD COLUMN c INT, ADD INDEX (other_col), ALGORITHM=NOCOPY, LOCK=NONE; -- works
```

- It is also impossible to combine `ADD/DROP` of a `VIRTUAL` column with other operations. This limitation has been inherited from `ALGORITHM=INPLACE` and again, can be lifted in the future, if necessary.
- With [InnoDB Adaptive Hash Index](https://dev.mysql.com/doc/refman/5.7/en/innodb-adaptive-hash.html) enabled, `ALGORITHM=INSTANT/NOCOPY` operations involving adding columns or dropping `VIRTUAL` columns require invalidating AHI, which is an expensive operation involving a buffer pool scan. Other connections may get blocked for the duration of the scan.

# Compatibility

There are no changes to the on-disk format in addition to [those introduced by the Instant Add Column feature](https://www.yuque.com/littleneko/note/gtptal#e91ffe51), so data file compatibility remains unchanged.

This feature is currently not available in any MySQL version or fork (MariaDB has implemented [MDEV-13134](https://jira.mariadb.org/browse/MDEV-13134), which is what this work is based on, but [MDEV-16291](https://jira.mariadb.org/browse/MDEV-16282) is currently Open). When they will implement similar features in the future, there will likely be incompatibilities on the syntax level or in functionality.

# Links

- [MDEV-13134](https://jira.mariadb.org/browse/MDEV-13134)
- [MDEV-16291](https://jira.mariadb.org/browse/MDEV-16282)
- [Online DDL Operations](https://dev.mysql.com/doc/refman/8.0/en/innodb-online-ddl-operations.html) in the MySQL 8.0 Reference Manual
- [Instant ADD COLUMN Limitations and Caveats](https://git.xiaojukeji.com/foundation/mysql-server-5.7/wikis/feature-instant-add-column#limitations-and-caveats)
- [The DDL Log](https://dev.mysql.com/doc/refman/5.7/en/innodb-online-ddl-space-requirements.html)
