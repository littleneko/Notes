# 1. In-memory table objects
To remember the instant status of a table, new member variables were introduced:
```
In dict_table_t:
+       /** Number of non-virtual columns before first instant ADD COLUMN,
+       including the system columns like n_cols. */
+       unsigned                                n_instant_cols:10;
```

```
In dict_index_t:
+       unsigned        n_instant_nullable:10;
+                               /*!< number of nullable fields before first
+                               instant ADD COLUMN applied to this table.
+                               This is valid only when is_instant() is true */
```

A new structure to remember the default value in memory:
```
+/** Data structure for default value of a column in a table */
+struct dict_col_default_t {
+       /** Pointer to the column itself */
+       dict_col_t*     col;
+       /** Default value in bytes */
+       byte*           value;
+       /** Length of default value */
+       size_t          len;
+};
```

Also a default value pointer in dict_col_t, if this column was instantly added.
```
+       /** Default value when this column was added instantly.
+       If this is not a instantly added column then this is nullptr. */
+       dict_col_default_t*             instant_default;
```

There are also some related functions to get instant information etc. from 
table, indexes and columns.


# 2. Records related
Remember that only the record on clustered index could be affected by this 
worklog, secondary index records don't.

## 2.1 Instant bit and default value
---------------------------------

To set a bit in info bits to indicate this is a record after instant ADD COLUMN, 
this bit is introduced:
```
+/* The 0x40UL can also be used in the future */
+/* The instant ADD COLUMN flag. When it is set to 1, it means this record
+was inserted/updated after an instant ADD COLUMN. */
+#define REC_INFO_INSTANT_FLAG  0x80UL
```

To indicate a field has a default value rather than an inlined value in the 
record, this bit is introduced for the offsets array:
```
+/* Default value flag in offsets returned by rec_get_offsets() */
+#define REC_OFFS_DEFAULT       ((ulint) 1 << 29)
```
All instantly add columns will have this bit set in offsets array.

If a record resides on a clustered index whose table has undergone an instant 
ADD COLUMN, then it should be parsed specially. So there should be a check to 
see if this index/table is instant affected, if so, those instantly added 
columns set with REC_OFFS_DEFAULT will ask for default values remembered in 
dict_col_t::instant_default.

## 2.2 Parse
---------

Since the physical record may have less fields than the ones defined on 
clustered index, if the offsets array is initialized according to the physical 
record only, then the offsets fields will also mismatch with fields on clustered 
index. To make logic and coding simple, the offsets array is always created 
according to the real number of fields on index.

There would be two different physical record format with three meanings, please 
refer to rec_init_null_and_len_comp() to know how to handle all these cases. In 
a word, the checking looks like:
if the index is not instant
    /* This is a complete record without instant ADD COLUMN, parse it as is */
else if the record has instant bit set
    /* This is a record inserted after an instant ADD COLUMN, so it should be 
able to know the number of fields by parsing the length info in the record */
else
    /* This is a record inserted before one instant ADD COLUMN, the number of 
fields is remembered in the table metadata */


# 3. Identify an instant ADD COLUMN
Since the keyword INSTANT would be introduced for current instant ADD COLUMN, in 
ha_innodb::check_if_supported_inplace_alter() and 
ha_innopart::check_if_supported_inplace_alter(), if we know the ALGORITHM is 
INSTANT, all relevant tables would be checked if instant ADD COLUMN is 
applicable, like it's not a table with fulltext index, it's not in COMPRESSED 
format etc. Once all are fine, a flag would be set in above variable, to 
indicate this is instant ADD COLUMN, and no rebuild later.


# 4. Metadata in DD
Basically there are four new SE private data introduced:
a) dd::Table::se_private_data::instant_col, to indicate how many columns exist 
before first instant ADD COLUMN in table level
b) dd::Partition::se_private_data::instant_col, to indicate similarly to a), 
however, different partitions may have different numbers, as long as all are 
bigger than or equal to the one in table level
c) dd::Column::se_private_data::default_null, to indicate the default value is 
NULL
d) dd::Column::se_private_data::default, to indicate the default value if it's 
not NULL

All are easy to understand, except b).

Let's say there is a partitioned table with two partitions, and also an instant 
ADD COLUMN has happened just now. ==If partition two is truncated, the new 
partition doesn't have to keep the instant ADD COLUMN information and make the 
records in it more complicated==. It should only works like a fresh new 
table/partition with all complete new records in the table. This is same to 
other partition related operations which will create new partitions. So a) and 
b) are both remembered, b) is per partition. And b) should be either nothing, or 
always bigger than a)

Since b) should be always bigger than a) if exists, so to open a partition 
table, it can only load default values for last b) columns, instead of a) 
columns.

When the whole table is not instant, all a), b), c) and d) would be cleared. If 
only some partitions are not instant, relevant b) would be cleared with others 
left.


# 5. I_S display
There would be one more columns in I_S.innodb_tables called INSTANT_COLS, to 
remember the number of columns when the first instant ADD COLUMN happened on 
this table. For partitioned table, this number may differ for each partition.

There would be two more columns in I_S.innodb_columns called HAS_DEFAULT and 
DEFAULT_VALUE. HAS_DEFAULT = 1 means that this is a instant column with default 
value. DEFAULT_VALUE is only valid when HAS_DEFAULT is 1. It shows the internal 
binary for the default value. If necessary, we may also try to display the 
original default value, but this requires more work in translating the values.


# 6. EXPORT/IMPORT
For non-partitioned table, basically the tablespace can be imported to replace 
the existing one.

For partitioned table, every partition may have different instant columns 
recorded, so before one partition tablespace can be imported, it's a must to 
check if the default values remembered in the .cfg file match the default values 
in the table existing in the running server. If not match, saying different 
default values for one instant column, the tablespace can't be imported. Once a 
tablespace gets imported, its default values should be imported too.
