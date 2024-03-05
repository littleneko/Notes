# About

This document describes the architecture and implementation details for Instant `ADD COLUMN` , which is a new MySQL server feature that allows adding new columns to InnoDB tables in constant time without examining or modifying existing rows.

# Goals

Before this feature was implemented, only `VIRTUAL` columns could be added in constant time. Adding stored columns always required rebuilding the table and its indexes, no matter if `ALTER TABLE ... ALGORITHM=COPY` or `ALTER TABLE ... ALGORITHM=INPLACE` was used.

The goal of this feature is to introduce necessary changes to InnoDB on-disk format, metadata and SQL syntax to be able to add columns to InnoDB tables without rebuilding tables and even without touching existing data at all.

This work is based on the following implementations:

- the original Instant `ADD COLUMNS` patch, which was implemented by Tencent and contributed to both MySQL and Oracle [ [1]](https://bugs.mysql.com/bug.php?id=88528). It did not include regression tests and did not cover many use cases such as partitioning, tablespace import/export, `TRUNCATE TABLE`, etc. It also had the new algorithm hard-coded, i.e. there was no way to choose between instant and non-instant ADD COLUMN implementations.
- MySQL 8.0 implementation based on the Tencent patch [ [2]](https://dev.mysql.com/worklog/task/?id=11250). It is more polished with more corner cases handled, has extensive MTR tests, but all metadata storage is implemented via the global Data Dictionary, which is available only in 8.0.
- MariaDB 10.3 implementation, also based on the Tencent patch [ [3]](https://github.com/MariaDB/server/commit/a4948dafcd7eee65f16d848bdc6562fc49ef8916). This implementation is also quite complete, but differs significantly in many aspects from other implementations. For example, metadata is stored as hidden records in the clustered index of a table without using any Data Dictionary or system tables, partitioning-related code is different, because MariaDB does not support native partitioning introduced in MySQL 5.7, and so on.

Since for us at DiDi it is important to maintain as much compatibility with upstream MySQL as possible, this feature is mostly based on the MySQL 8.0 implementation. However, due to architectural differences between MySQL 5.7 and 8.0, some things had to be implemented from scratch. There are also some user-visible differences in behavior between instant `ADD COLUMN` functionality in DiDi MySQL 5.7 and upstream MySQL 8.0, see [Differences with MySQL 8.0](#1459b8eb).

# High Level Architecture

The following diagram gives an overview of how the feature works:

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1594714630916-bd280a7e-f8b1-478a-9abe-f1ac8603c85f.svg" alt="instant_add_column.svg"  />

The basic idea in all implementations can be summarized as follows. When an `ALTER TABLE ... ADD COLUMN` is executed, instead of copying all table rows to include values for the new column, just update metadata to mark the new column as "instantly added", and remember its `DEFAULT` value, if it has one. When more rows are added after adding an "instant" column, we just store column values for instantly added columns as usual. When processing "old" rows (i.e. those added before instantly adding a column), we rebuild the full row image by combining values of "core" and "instant" columns.

Which means implementing this feature requires changes to the following functionality:

- InnoDB on-disk format (to differentiate the "old" and "new" rows)
- table metadata (to keep track of the number of instantly added columns for each table and their default values)
- SQL syntax for `ALTER TABLE` to be able to control how `ADD COLUMN` is executed

## Changes to the InnoDB on-disk format

Since data rows in InnoDB are stored in leaf nodes of the clustered index, only changes to the records format of the clustered index are necessary.

To differentiate between "old" and "new" rows, a new row flag is introduced. The new flag (`REC_INFO_INSTANT_FLAG`) is stored in the previously unused bit of the **Info Flags** field of index records. When the bit is set, it means the row (actually, the clustered index record) was inserted/updated after an instant `ADD COLUMN`. See [ [4]](https://blog.jcole.us/2013/01/10/the-physical-structure-of-records-in-innodb/) for the description of the index record format.

Since there may be multiple "instant" columns added at different points in time, we may have records with different number of stored values varying from the number of "core" columns (i.e. columns existing before the first instant `ADD COLUMN`) and the current total number of columns. Which means another meta field in the row format specifying the actual number of stored column values is necessary.

Rows in the `REDUNDANT` format already have such a field, so no changes to that format are necessary.

For rows in the `COMPACT`/`DYNAMIC` format, a new field is introduced. The field stores the number of fields 'inlined' in the record, i.e. the number of columns the table had at the time the row was inserted. It occupies 1 or 2 extra bytes, depending on the number of columns. In the most common case, when the number of columns is less than 128, it is 1 byte. Otherwise, the field is stored in 2 bytes.

## Changes to table metadata

It is also important to store the number of columns the table had before the first instant `ADD COLUMN` (that is, the number of _core_ columns). This is required to know how many fields are in the "old" clustered index records which do not have the `REC_INFO_INSTANT_FLAG` flag set and thus, do not have the extra field with the number of fields.

That value is stored in per-table metadata in the `SYS_TABLES` InnoDB system table. It is encoded into unused 16 bits of the existing `MIX_LEN` column of the `SYS_TABLES` table, so no extra storage space is occupied by this field.

Default values of instantly added columns is another thing to keep track of in the per-table metadata. To that end, a new InnoDB system table was introduced. The table has the following name and structure (in the syntax used by InnoDB internal SQL parser):

```sql
CREATE TABLE SYS_INSTANT(
  TABLE_ID BIGINT UNSIGNED NOT NULL,
  POS INT NOT NULL,
  DEFAULT_VALUE CHAR);
CREATE UNIQUE CLUSTERED INDEX INSTANT_IDX
 ON SYS_INSTANT(TABLE_ID, POS);
```

where `TABLE_ID` is the numeric ID of the table, `POS` is a zero-based position of the column and `DEFAULT_VALUE` is a hexadecimal representation of the default value provided by the SQL layer.

Note that _table_ here means either a regular table, or a partition of a partitioned table, which is a set of tables from the InnoDB perspective.

The contents of the `SYS_INSTANT` table can be examined by a user via the `INFORMATION_SCHEMA.INNODB_SYS_INSTANT` table, see [Metadata visibility in `INFORMATION_SCHEMA`](#7435a799).

## Changes to the `ALTER TABLE` syntax

Since adding columns instantly has a cost (extra storage overhead for all subsequently inserted records + extra processing overhead to fetch default values for old rows), it is important to be able to control whether a column is added instantly or by rebuilding the table as before.

To that end, a new value in the `ALGORITHM` clause of the `ALTER TABLE` statement can be used:

- when `ALGORITHM=INSTANT` is used, adding a column will be performed instantly, if possible. Otherwise, `ALTER TABLE` will fail with an error describing why instant `ADD COLUMN` is impossible (see Limitations below);
- when `ALGORITHM=INPLACE/COPY` is used, adding a column will be performed the "old way" by rebuilding the able;
- when no `ALGORITHM` clause is used, or with `ALGORITHM=DEFAULT`, `ALTER TABLE` will pick the most efficient way to add a column, i.e. `INSTANT` if possible, or `INPLACE` otherwise.

Note that some operations other than `ADD COLUMN` are also compatible with `ALGORITHM=INSTANT`. They have always supported constant-time execution, but there has been no way to request it explicitly.

## Supported operations

`ALGORITHM=INSTANT` is currently supported for:

- `ADD COLUMN` (for base columns);
- `ADD COLUMN` (for virtual columns);
- `ALTER COLUMN ... SET DEFAULT`;
- `ALTER COLUMN ... DROP DEFAULT`;
- changing `ENUM` values with `ALTER TABLE ... MODIFY COLUMN ... ENUM(...)`;
- renaming columns with `ALTER TABLE ... CHANGE COLUMN`;
- renaming indexes with `ALTER TABLE ... RENAME INDEX`;
- renaming tables with `ALTER TABLE ... RENAME TO`;
- for MyISAM tables: all operations above except adding a base column.

`ALGORITHM=INSTANT` is currently not supported for:

- adding both virtual and base columns in a single `ALTER TABLE`;
- combining an action that supports `ALGORITHM=INSTANT` (e.g. adding a base column) with  another action that does not support `ALGORITHM=INSTANT` (e.g. adding an index on existing column).

## Metadata visibility in `INFORMATION_SCHEMA`

All extra data in the InnoDB internal data dictionary (the `SYS_*`) tables can be examined through `INFORMATION_SCHEMA`:

- the number of core columns can be viewed in the new `INSTANT_COLS` column of `INFORMATION_SCHEMA.INNODB_SYS_TABLES`. The value of 0 corresponds to a regular table without instantly added columns. The name is misleading (it's not actually the number of _instant_ columns, but the number of columns before the first instant `ADD COLUMN`), but that's how it is called in MySQL 8.0, so the same name was kept for compatibility.
- default values for instantly added columns can be viewed in the new `DEFAULT_VALUE` column of `INFORMATION_SCHEMA.INNODB_SYS_COLUMNS`;
- for debugging and troubleshooting purposes, the contents of the internal `SYS_INSTANT` table (which is used by InnoDB internally and to expose `DEFAULT_VALUE` in the `INNODB_SYS_COLUMNS` Information Schema table) can be viewed directly through `INFORMATION_SCHEMA.SYS_INSTANT`.

## Examples

```sql
mysql> CREATE TABLE t1(id SERIAL);
Query OK, 0 rows affected (0.03 sec)

mysql> INSERT INTO t1 VALUES();
Query OK, 1 row affected (0.01 sec)

mysql> SELECT * FROM t1;
+----+
| id |
+----+
|  1 |
+----+
1 row in set (0.00 sec)

mysql> ALTER TABLE t1 ADD COLUMN a INT DEFAULT 100;
Query OK, 0 rows affected (0.05 sec)
Records: 0  Duplicates: 0  Warnings: 0

mysql> SELECT * FROM t1;
+----+------+
| id | a    |
+----+------+
|  1 |  100 |
+----+------+
1 row in set (0.00 sec)

mysql> INSERT INTO t1(a) VALUES(200);
Query OK, 1 row affected (0.00 sec)

mysql> SELECT * FROM t1;
+----+------+
| id | a    |
+----+------+
|  1 |  100 |
|  2 |  200 |
+----+------+
2 rows in set (0.00 sec)

mysql> ALTER TABLE t1 ADD COLUMN b CHAR(4) DEFAULT 'test';
Query OK, 0 rows affected (0.03 sec)
Records: 0  Duplicates: 0  Warnings: 0

mysql> SELECT * FROM t1;
+----+------+------+
| id | a    | b    |
+----+------+------+
|  1 |  100 | test |
|  2 |  200 | test |
+----+------+------+
2 rows in set (0.00 sec)

mysql> ALTER TABLE t1 ALTER COLUMN b SET DEFAULT 'new'; -- This will only modify .FRM file, but not SYS_INSTANT
Query OK, 0 rows affected (0.02 sec)
Records: 0  Duplicates: 0  Warnings: 0

mysql> INSERT INTO t1 VALUES();
Query OK, 1 row affected (0.00 sec)

mysql> SELECT * FROM t1;
+----+------+------+
| id | a    | b    |
+----+------+------+
|  1 |  100 | test |
|  2 |  200 | test |
|  3 |  100 | new  |
+----+------+------+
3 rows in set (0.00 sec)

mysql> SELECT * FROM INFORMATION_SCHEMA.INNODB_SYS_TABLES WHERE NAME LIKE '%t1%';
+----------+---------+------+--------+-------+-------------+------------+---------------+------------+--------------+
| TABLE_ID | NAME    | FLAG | N_COLS | SPACE | FILE_FORMAT | ROW_FORMAT | ZIP_PAGE_SIZE | SPACE_TYPE | INSTANT_COLS |
+----------+---------+------+--------+-------+-------------+------------+---------------+------------+--------------+
|       74 | test/t1 |   33 |      6 |    61 | Barracuda   | Dynamic    |             0 | Single     |            1 |
+----------+---------+------+--------+-------+-------------+------------+---------------+------------+--------------+
1 row in set (0.01 sec)

-- the default value for column 'b' is 'test', not 'new', because it is only used for old rows
mysql> SELECT * FROM INFORMATION_SCHEMA.INNODB_SYS_COLUMNS WHERE TABLE_ID=74; 
+----------+------+-----+-------+--------+-----+-------------+---------------+
| TABLE_ID | NAME | POS | MTYPE | PRTYPE | LEN | HAS_DEFAULT | DEFAULT_VALUE |
+----------+------+-----+-------+--------+-----+-------------+---------------+
|       74 | id   |   0 |     6 |   1800 |   8 |           0 | NULL          |
|       74 | a    |   1 |     6 |   1027 |   4 |           1 | 80000064      |
|       74 | b    |   2 |     2 | 524542 |   4 |           1 | 74657374      |
+----------+------+-----+-------+--------+-----+-------------+---------------+
3 rows in set (0.01 sec)

-- the default value for column 'b' is 'test', not 'new', because it is only used for old rows
mysql> SELECT * FROM INFORMATION_SCHEMA.INNODB_SYS_INSTANT WHERE TABLE_ID=74;
+----------+-----+---------------+
| TABLE_ID | POS | DEFAULT_VALUE |
+----------+-----+---------------+
|       74 |   1 | 80000064      |
|       74 |   2 | 74657374      |
+----------+-----+---------------+
2 rows in set (0.00 sec)
```

## Compatibility with MySQL 8.0

- tablespaces (`.ibd` files) containing tables with instantly added columns are compatible with MySQL 8.0 on the binary level. For example, it is possible to export a tablespace with `FLUSH TABLES FOR EXPORT` and import it to MySQL 8.0 with `ALTER TABLE IMPORT TABLESPACE`;
- likewise for individual partitions imported with `ALTER TABLE ... IMPORT PARTITION ... TABLESPACE`;
- however, in-place upgrade of the entire MySQL instance to MySQL 8.0 will require extra coding work to a different metadata storage mechanism. To ensure the upgrade path to MySQL 8.0, we will have to implement support in DiDi MySQL 8.0 that will go through instant-related metadata in InnoDB `SYS_*` tables and convert it to the global data dictionary used by MySQL 8.0. This part will be addressed separately in issue #45.
- the format of `INNODB_SYS_TABLES` and `INNODB_SYS_COLUMNS` tables in the Information Schema was deliberately made compatible with MySQL 8.0, but the table names used in MySQL 8.0 are `INNODB_TABLES` and `INNODB_COLUMNS`.

## Differences with MySQL 8.0

- unlike MySQL 8.0, adding regular (base) columns together with virtual generated columns is incompatible with `ALGORITHM=INSTANT`. It can only be done with the `COPY` or `INPLACE` algorithms, i.e. with a table rebuild. This limitation exists due to the Online DDL design in MySQL 5.7 and can be lifted in the future.
- unlike MySQL 8.0, `TRUNCATE TABLE` does not clear the instant metadata from the table. It will still be considered as a table having instant column(s), which means all new rows will be inserted in the extended format. To clear the instant status of a table, it has to be rebuilt by `ALTER TABLE ... FORCE` or any DDL operation with the `COPY`/`INPLACE` algorithm.
- unlike MySQL 8.0, `INFORMATION_SCHEMA.INNODB_SYS_COLUMNS` will have one row per each instant column in each partition. MySQL 8.0 only has one row per table, i.e. it does not contain same instant column records for each partition in a partitioned table.
- unlike MySQL 8.0, it is possible to instantly add a column to a
system table (`mysql.*`)
- unlike MySQL 8.0, `ALTER TABLE ... EXCHANGE PARTITION` works, but should fail, if the partition or the table have instant columns. Fixing it is complicated due to some limitations in the partitioning code in MySQL 5.7

# Table export/import

It is possible to export `innodb_file_per_table` tablespaces containing tables with instantly added columns with `FLUSH TABLES FOR EXPORT` and then import them to another instance, either DiDi MySQL 5.7 with the instant `ADD COLUMN` feature, or MySQL 8.0. That functionality works for both regular tables and partitions. All instant-related metadata is written into the `.cfg` file. To support extra information, the format version of `.cfg` files has been bumped from `V1` to `V3` as it was done in MySQL 8.0. Since format version 3 also includes information used by format version 2 (introduced earlier in the MySQL 8.0 development cycle), the corresponding code has also been backported from MySQL 8.0.

# Physical backups

Since this feature changes the on-disk format for tables with instantly added columns, and introduces one extension to the REDO log format (index definition in a REDO record may now have information about "core" columns in the index), XtraBackup will fail when used to prepare a backup with such tables. Modifying XtraBackup to support tables with instant columns will be addressed separately in xtrabackup#3.

# Limitations and caveats

- encrypted and `ROW_FORMAT=COMPRESSED` tables are not supported. Tables with page compression (`CREATE TABLE ... COMPRESSION`) can be used to instantly add columns;
- temporary InnoDB tables are not supported;
- instantly adding columns between two columns is not supported;
- instantly adding spatial type columns with `NOT NULL` is not supported
- `INFORMATION_SCHEMA.INNODB_SYS_COLUMNS` now uses the `internal_tmp_disk_storage_engine` instead of `MEMORY` due to the new `DEFAULT_VALUE` column which has the `MEDIUMBLOB` type; Likewise for the `INNODB_SYS_INSTANT` table;
- `ALTER TABLE ... EXCHANGE PARTITION` works, but should fail, if the
partition or the table have instant columns. Fixing it is complicated due to some limitations in the partitioning code in MySQL 5.7
- it is impossible to downgrade a MySQL instance containing tables with instantly added columns to a version that does not support the feature. Doing so will result in crashes and assertion failures as soon as the "instant" tables are accessed.

# QA plan

All regression tests related to the instant `ADD COLUMN` feature and `ALGORITH=INSTANT` have been ported from MySQL 8.0, but have been adjusted to take MySQL 5.7-specific behavior into account.

Besides functional QA testing, it is important to test the following aspects on the QA stage:

- general performance of tables in the `COMPACT`/`DYNAMIC` row formats;
- performance of `INFORMATION_SCHEMA.INNODB_SYS_COLUMNS` table on servers with large numbers of tables and columns.

# Links

- [The original contribution by Tencent](https://bugs.mysql.com/bug.php?id=88528)
- [MySQL WL#11250: Support Instant Add Column](https://dev.mysql.com/worklog/task/?id=11250)
- [MDEV-11369 Instant ADD COLUMN for InnoDB](https://github.com/MariaDB/server/commit/a4948dafcd7eee65f16d848bdc6562fc49ef8916)
- [The physical structure of records in InnoDB](https://blog.jcole.us/2013/01/10/the-physical-structure-of-records-in-innodb/)
