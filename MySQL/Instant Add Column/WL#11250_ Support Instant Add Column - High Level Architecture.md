# 0. Definitions
COLUMN: This is used when we say ADD COLUMN in SQL.

FIELD: This is used when we say a column in a row. That is for every single row, 
there is a physical record in clustered index, and a column in the row maps to a 
field in the record in our code.

instant ADD COLUMN: This means all kinds of ADD COLUMN operations supported by 
this worklog which can be done instantly.


# 1. General
## 1.1. Problems of current ADD COLUMN

Currently, InnoDB supports two types of ALTER TABLE ADD COLUMN, no matter what 
kind of columns and how many columns are added in one clause. There are 
ALGORITHM = INPLACE and ALGORITHM = COPY. Although it's called INPLACE algorithm 
which is online DDL indeed, however, a table rebuild is required to finish it. 
The reason is that the internal record format is not flexible enough for new 
fields(columns). For example, if it's a new style record, length of variable-
length field and SQL-null flags would be stored in the record header. So to add 
every new column, the record header may change too, which applies to all exiting 
rows. So it looks like a simplest way is not reorganize every single record of 
the table, but read the old records and add the new fields, then insert them 
into a new table.

Users have a strong request that some DDL like current ADD COLUMN should be done 
in a very short duration since it looks like only a metadata change. In this 
way, they don't need to wait a long time for the table coming to a final shape 
and lots of IO can be saved.

## 1.2. Tencent's contribution

To fix this issue, a team from Tencent company figured out a solution to add 
columns instantly, without modifying records of the table. The rough idea has 
been already mentioned in the HLD section.

The benefits of their contribution are:
a) ALTER TABLE .. ADD COLUMN can be done instantly, without too much IO and 
waiting time
b) Row format is compatible with existing data files


# 2. Operations which can be instant

As mentioned in FR2, this worklog mainly supports the instant ADD COLUMN 
operations. Multiple columns, either regular columns or virtual columns, with or 
without default values are all supported.

Refer to FR2 to see which kind of SQL is supported and which is not.

## 2.1 ALGORITHM and LOCK

Basically, there are INPLACE and COPY algorithm, both of which would be kept as 
is. Only when user specifies the INSTANT algorithm, current ADD COLUMN could be 
done  instantly with only some metadata changes, rather than an internal table 
rebuilding. So after this worklog, as long as the algorithm is ignored, or 
specified as DEFAULT/INSTANT, InnoDB will try an instant ADD COLUMN is possible.

If users want to still do original online ADD COLUMN with table rebuilding, they 
can use the INPLACE algorithm or FORCE keyword, like described in FR2.

There is no any change to the LOCK for this worklog. We can always specify 
NONE/SHARED/EXCLUSIVE for the LOCK.

## 2.2 Row format supported

The row formats of DYNAMIC/COMPACT/REDUNDANT would be supported in this worklog. 
COMPRESSED is no need to supported.


# 3. Algorithm

To make an ADD COLUMN metadata change only, it is necessary to mark the record 
accordingly, so that later scan can know which record is fit to which table 
definition. One solution is to give every record or page a version number, 
meaning that the record or records in a page are defined by table structure 
version X, so to parse a record, a proper table structure can be picked 
accordingly. But this is more complex and lots of work need to be done.

A simpler solution is how this worklog works. Instead of giving record/page a 
version, ==a bit in record would be set if there was any instant ADD COLUMN 
happened before==. With this bit set, it's possible to distinguish a record is 
inserted before any instant ADD COLUMN or not. At the meantime, it's necessary 
to ==remember the existing column number when first instant ADD COLUMN happens.==

Let's suppose there is a table with one row:
```sql
CREATE TABLE t1 (a INT NOT NULL AUTO_INCREMENT PRIMARY KEY, b INT);
INSERT INTO t1 VALUES(0, 1); -- Row 1
```

When executing an instant ADD COLUMN:
```sql
ALTER TABLE t1 ADD COLUMN c INT DEFAULT 10;
```
**The column numbers in old table t1 would be remembered, so the number is 2, **
**which is invariable**.

Then another INSERT:
```sql
INSERT INTO t1 VALUES(0, 2, 20); -- Row 2
```
When inserting row two, one bit should be set to identify that it's a row after 
any instant ADD COLUMN. The bit in row one is not set. So when parsing row 1, 
only the first 2(as remembered) columns would be used. If row 2, all columns 
would be used.

==To make it possible to parse a row after another new instant ADD COLUMN, a 
variable-length number of columns information should be added to the physical 
record if the record has the instant mark set.== ==**So in row 2, it's also necessary **
**to remember current fields number, it's 3 now**.== Let's say there is another ALTER 

```sql
TABLE and a new INSERT:
ALTER TABLE t1 ADD COLUMN d INT;
INSERT INTO t1 VALUES(0, 3, 20, 10); -- Row 3
```
==**In row 3, the number of current fields would be remembered, it's 4 now**.== So to 
parse row 2, 3 columns are used, while to parse row 3, 4 columns are used.

==Default value of the instantly added columns should be remembered too==. So in 
above case, for row 1, default values of column c and d would be filled in for 
it; for row 2, default value of column d would be filled in; finally, for row 3, 
no need for default values.

Since there is only one bit to indicate the column change, so the order of 
columns are assumed to be not changed after instant ADD COLUMN. For short, the 
newly instantly added columns can only appended at last of the table.

Also, because there is no version concept here, there is no strong requirement 
to convert the old record format to the new one either in background or by some 
manual command. So physical records would always be left as is.

Only when there is a table rebuild operation, the old table would be destroyed 
and new table would be created, then all records in the new table are according 
to the latest table structure. And in this way, the number of current fields 
information don't need to be stored in record.

So, in a word, instant ADD COLUMN can be applied to a table repeatedly, and 
records in the table may have different number of fields stored. Once there is a 
table rebuild, all the record format would be in a unified and latest format.


# 4. Row format compatibility

There are both old style row format and new style row format in use.

## 4.1 New style row format

New style row format includes DYNAMIC and COMPACT format. Different rows can be 
of different length, depending on the nullable fields and variable-length 
fields. Current physical record consists of a record header and record data 
fields.

The detailed record header which is in variable-length looks like:
```
+--------------------------------+----------------+---------------+
| Non-null variable-length array | SQL-null flags | Extra 5 bytes |
+--------------------------------+----------------+---------------+
```
Then the detailed 5 extra bytes look like:
```
+-----------+---------------+----------+-------------+-----------------+
| Info bits | Records owned | Heap No. | Record type | Next record ptr |
+-----------+---------------+----------+-------------+-----------------+
```

The lengths of above information are:
a) Info bits: 4 bits
b) Record owned: 4 bits
c) Heap No. : 13 bits
d) Record type: 3 bits
e) Next record ptr: 2 bytes

So the total length is 5 bytes.

## 4.2 How to mark instant bit?

Let's first consider the new style row format.

As it is known, there are un-used bits in both 'Info bits' and 'Record type'. 
Two bits in 'Info bits' can be used further while 4 kinds of values can be used 
in 'Record type'. So one bit in 'Info bits' would be used to indicate the 
instant mark. Also, to remember current field numbers, a variable-length number 
of fields would be added between the SQL-null flags and Extra 5 bytes. So the 
record header now becomes

```
+--------------------------+----------------+---------------+---------------+
| Non-null variable-length |                |               |               |
| array                    | SQL-null flags | fields number | Extra 5 bytes |
+--------------------------+----------------+---------------+---------------+
```
## 4.3 Old style row format

Only REDUNDANT row format needs to be considered here. And since there is 
already firlds number in the physical record, there should be no physical format 
change for redundant row format. It's possible to parse the record according to 
the fields number.


# 5. Integration with DD
What should be remembered in DD are:
==**a) Column numbers before first instant ADD COLUMN**==
==**b) Default values for instant added columns**==

**Please note that if the default value gets changed later, it's still a must to **
**remember the original default value, because records without this field should **
**be filled in with the original default value.**

**注：alter table 更改 instant add column 添加的列的 default 值时，不更新 INNODB_SYS_COLUMN 表
和 INNODB_SYS_INSTANT 表的 DEFAULT_VALUE 列**

It's obviously that a) should be stored in dd::Table::se_private_data, as an 
integer. Furthermore, if this is a partitioned table, a) for different 
partitions may differ, so this should be also stored in 
dd::Partition::se_private_data.

About b), considering the new DD, the best place to store it is 
dd::Column::se_private_data. The benefit is that the default value becomes an 
attribute of the dd::Table, also every dd::Column can manage its default value 
separately.

These values would be remembered during ALTER TABLE, and loaded into memory 
during opening table.


# 6. DMLs

## 6.1 INSERT
As mentioned above, INSERT after one instant ADD COLUMN would affect the record 
format, the number of fields currently would be remembered in the record. If no 
instant ADD COLUMN, insert doesn't care about the number of current fields.

## 6.2 DELETE
There is no any change.

## 6.3 UPDATE
As long as the instantly added column gets changed, it must not use the inplace 
update, instead, it should delete and re-insert the new record.

Furthermore, to handle a rollback problem easily(see next section), it has to 
check if the trailing fields of the updated record can be ignored or not. If the 
updated record has the same default values at last, the default values won't be 
stored in the row.

## 6.4 SELECT
Default values of instantly added columns should be read and filled into the 
result whenever a record is read


# 7. Rollback

Because some fields could be not stored in the physical record, update to this 
record may result in the row too big problem if update is done in the old way, 
expanding all default fields in the new record.

One example is:

a) create table t2( id int primary key, c1 varchar(4000), c2 varchar(4000), c3 
varchar(1000)) engine=innodb row_format=compact;
b) insert into t2 values(1, repeat('a', 4000), repeat('b', 4000), repeat('c', 
1));
c) alter table t2 add column d1 varchar(500) not null default repeat('d', 500);
d) begin;
e1) update t2 set c1 = repeat('x', 200) where id = 1;
or e2) update t2 set c4 = 'x' where id = 1;
f) rollback;

In this example, original row doesn't have any field stored externally, if it's 
instant ADD COLUMN, the row would not be changed at all, that is the default 
value of 500 chars are not in the record.

Case e1): The update new row fit in the page too. However, when rollback, the 
original row now has to include the default value of 500 chars. Then the record 
is too long to fit in one page, some fields have to be stored externally. The 
worse is if it's REDUNDANT format with 4K page size, the expanded record would 
become too big to be inserted into the page, thus a rollback failure with crash.

Case e2): The update new row also fit in the page. However, the rollback will 
now have to expand the record with 500 chars, which makes the row too big to be 
rolled back.

So it needs to keep the default values as not stored in record when possible. 
That is in both cases, new record would not include 500 chars for c4 column, 
just mark it as default value in the record.

Shall it just keep the default values as original record? No. In e2) case, the 
updated record doesn't have c4 as default value, if we don't check c4 when 
rollback, it's impossible to roll back it too. So all possible default 
values(after first INSTANT ADD COLUMN) should be checked.

Why this doesn't happen before instant ADD COLUMN? Because the fields of the row 
have already stored externally after the ADD COLUMN. During rollback, the 
existing externally stored value can be used to represent the old value before 
update, thus, no new external fields are necessary.



# 8. Recovery

For redo recovery, InnoDB will parse the record logged, so it's a must to know 
the instant ADD COLUMN information. The only needed information is that if the 
table is after one instant ADD COLUMN and the column number before its first 
instant ADD COLUMN.

So basically when logging the index information, the number of columns before 
first instant ADD COLUMN would be logged to indicate both above information for 
new style records. If it's old style, no extra logs are necessary.


# 9. Replication

As long as the DMLs can work correctly, there should be no impact on replication 
at all.


# 10. IMPORT/EXPORT

Since the related information as mentioned in 5. are already all stored in 
dd::Table, dd::Partition and dd::Column(mysql.tables, mysql.partition_tables and  
mysql.columns), so it would be out of box for the table to work after 
exporting/importing with SDI. However, this has to wait for WL#9761 for SDI 
EXPORT/IMPORT to work. So in this worklog, it's necessary to write the DD 
related information into the .cfg file, and read it during IMPORT.

The serialization can be done straightly by writing the metadata out along with 
other table/column metadata.

If the .cfg file is missing, there is no way to know the number of fields on 
first instant add column, so in most cases, it's impossible to use the IBD file. 
To handle the .cfg missing problem, after IMPORT, a check would be done on 
clustered index, to verify all the physical records. A table with instant 
columns would be always reported having corrupted records in clustered index. So 
in this case, the IMPORT would fail. This applies to generic IMPORT too, it's no 
need to import a corrupted table. Once WL#9761 comes in, .cfg missing problem 
would not happen so there would be no this issue.


# 11. Displayed in I_S.innodb*

It would be nice to provide the instant ADD COLUMN information to users through 
I_S views. Since there are two types of DD metadata related, one is in 
dd::Table::se_private_data and dd::Partition::se_private_data, others are in 
dd::Column::se_private_data, it's naturally to show these metadata in 
I_S.innodb_tables and I_S.innodb_columns accordingly. So the number of columns 
before first instant ADD COLUMN would be displayed in I_S.innodb_tables for 
every table, and every default value of columns would be displayed in 
I_S.innodb_columns. The default value would only be displayed in a binary format 
which is used in InnoDB internally.


# 12. Side effects

a) Since ADD COLUMN may be done instantly, so we may not expect an instant ADD 
COLUMN will fix a corrupted index

b) Since the INSTANT ADD COLUMN would not copy a new table from old one row by 
row, there is no chance for it to check if the rows from old table along with 
new added columns would become too big or not. So after INSTANT ADD COLUMN, some 
rows may in fact too big for the table, especially for REDUNDANT format, it 
would be detected when the record gets updated.

---

# 总结
**需要额外记录的信息（参考5.7实现）：**

1. **该行数据是否是 INSTANT ADD COLUMN 后写入的，即是否是新格式的数据（INSTANT ADD COLUMN 后 INSERT 的数据和 UPDATE 的数据都是新格式的数据）（使用未使用的 info bits 字段中的一位）**
2. **第一次 INSTANT ADD COLUMN 前该表的列数（**_**INSTANT_COLS**_**），用于读取 INSTANT ADD COLUMN 前写入的行数据时判断应该读多少列（INNODB_SYS_TABLES.INSTANT_COLS 字段用来记录该信息）**
3. **INSTANT ADD COLUMN 后写入的每行数据的列数（ **_**n_fields**_**），由于允许多次 INSTANT ADD COLUMN，写入每行数据时需要记录该行数据的总列数，才能从物理记录中正确读出该行数据（COMPACT 和 DYNAMIC 格式新增一个字段用于记录该信息，REDUNDANT 本来就有列数信息，不需要更改行格式）**
4. **Instant Add Column 的 DEFAULT 值（5.7 中的实现是 INNODB_SYS_COLUMNS.DEFAULT_VALUE 和 INNODB_SYS_INSTANT.DEFAULT_VALUE 中记录；8.0 存储在 dd 中）**

![image.png](https://littleneko.oss-cn-beijing.aliyuncs.com/img/1591624355179-0e6128ff-c63a-4a84-ab4c-fc0bf287f753.png)

读取的 Instant 列不在物理记录中时需要取 Default 值，有 2 种情况会使用：

1. 数据行是 Instant Add Column 之前写入的，读取所有 Instant Add Column（即列编号大于 INSTANT_COLS 的列）时都需要从这里读取 Default 值
2. 在多次 Instant Add Column 的情况下，读取在该行数据写入后的 Instant Add Column （即列编号大于 n_fields 的列，非 inline 数据），都需要从这里读取 Default 值

**Q**: 为什么 alter table 更改 instant add column 添加的列的 default 值时，不能更新 INNODB_SYS_INSTANT 表的 DEFAULT_VALUE 列？
**A**: ALTER TABLE xxx SET DEFAULT 语义是不会更改已经写入的数据的值的，即使当时该行数据是写入的 Default 值，只会影响后写入的数据的 Default 值。因此对于非 inline 的列，在读取时也应该读取的是第一次 Instant Add Column 时的 Default 值，参考 [Feature instant add column.Examples](https://www.yuque.com/littleneko/note/gtptal#Examples) 。
既然没有更改 SYS_INSTANT 表的 Default 值，那么新写入的数据就不是从字典表取的 Default 值了，而是从其他地方取得的。

# Links

- [WL#11250: Support Instant Add Column](https://dev.mysql.com/worklog/task/?id=11250)
