关于Instant Add Column的High Level Architecture，可以参考[WL#11250: Support Instant Add Column](https://dev.mysql.com/worklog/task/?id=11250)。
# Record
Instant Add Column对于行格式的更改，有以下两点：

1. **使用info bits中未使用的1位来表示是否是Instant Add Column后写入的行数据，即是否是新格式的数据**
2. **Compact格式，在hdr前增加一个n_fields字段用于记录Instant Add Column后写入的每行数据的field数（即inline的数据）；Redundant本来就有n_fields字段，不需要更改；同时对于new-style temporary record格式也需要做相应的更改**



> | 1 or 2 bytes to indicate number of fields in the record if the table
> where the record resides has undergone an instant ADD COLUMN
> before this record gets inserted; If no instant ADD COLUMN ever
> happened, here should be no byte; So parsing this optional number
> requires the index or table information |


> **TIPS：**
> Q1: 为什么要增加n_fields信息？
> A1: 如果有多次Instant Add Column，那么dict中的n_fields信息是最新的，在第一次Instant Add Column和最新的Instant Add Column之间写入的数据，需要通过该n_fields得到有多少列数据是inline的。
> 
> Q2: 第一次Instant Add Column之前写入的数据如何得到inline的信息？
> A2: 在SYS_TABLES表中存储了INSTANT_COLS信息



**代码涉及到修改的地方有**：

1. instant flag： `rec_get_instant_flag_new()` / `rec_set_instant_flag_new()`
2. n_fields（new-style）： `rec_set_n_fields()` /`rec_get_n_fields_instant()` / `rec_get_n_fields_length()`
3. get_n_fields（在当前的表定义下，需要读取多少个field，逻辑的field数量）
   1. old-style
      1. in an old-style record. Have to consider the case that after instant ADD COLUMN, this record may have less fields thancurrent index. 如果是Instant Add Column的表，不能直接从 n_fields 字段得到该行的列数，需要结合数据字典判断（ `rec_get_n_fields_old()`  ，该函数实际为新增，原函数改名为xxx_raw()）
      2. 原函数改成了 rec_get_n_fields_old_raw() （The following function is used to get the number of fields in an old-style record, which is stored in the rec），raw函数在dict中仍然会使用
   2. new-style：逻辑没有变化，仍然从dict中获取最新的表信息（`rec_get_n_fields()` ）
4. get_nth_field
   1. old-style
      1. inline数据（ `n < rec_get_n_fields_old_raw()` ），直接从rec中取第n列的值( `rec_get_nth_field_old()` )；
      2. 非inline数据：取default值（ `rec_get_nth_field_old_instant()` ，Gets the value of the specified field in the record. This is only used when there is possibility that the record comes from the clustered index, which has some instantly added columns.）
      3. 原函数rec_get_nth_field_old() 仍然保留，在dict中仍然会使用
   2. new-style
      1. 逻辑和old-style一样，不过有了offsets数组后，根据该列是否设置了offset DEFAULT FLAG可以直接知道该列是否需要取default值（ `rec_get_nth_field_instant()` ）
      2. 原rec_get_nth_field() 函数仍然保留，在row、btr、page等多处用到（Gets the value of the specified field in the record. This is used for normal cases, i.e. secondary index or clustered index which must have no instantly added columns. Also note, if it's non-leaf page records, it's OK to always use this functioni.）
5. offsets数组
   1. Note that after instant ADD COLUMN, if this is a record from clustered index, fields in the record may be less than the fields defined in the clustered index. So the offsets size is allocated according to the clustered index fields. 
      1. old-style，需要调用新函数 `rec_get_n_fields_old()`  获取n_field信息（ `rec_get_offsets_func()` ）。
      2. new-style的n_fields逻辑没有变化
   2. compact格式读取null flag和var-len field length时需要考虑是否有n_fileds字段，即是否是Instant Add Column之后写入的数据（ `rec_init_null_and_len_comp()` ）
   3. default值的表示：在初始化offsets数组时编码到每个offset中了，使用第3高位(`REC_OFFS_DEFAULT` )表示（前两高位分别用于表示NULL值和Extern字段了）
      1. 初始化offsets数组时，对于非inline的数据，需要设置offset的DEFAULT FLAG或者NULL FLAG（ `rec_init_offsets()` / `rec_init_offsets_comp_ordinary()` / `rec_get_instant_offset()` ）
   4. 读取nth length时需要判断是否是Default值然后返回对应的FLAG（`rec_get_nth_field_offs()` ）
6. convert（ `rec_convert_dtuple_to_rec()` ）
   1. new-style计算extra size的时候需要考虑 n_fields 和 null flag 的长度（ `rec_get_converted_size_comp_prefix_low()` ）
   2. new-style转换成rec时需要考虑 null flag 和 n_fields 的值（ `rec_convert_dtuple_to_rec_comp()`  ）
   3. 如果是instant add column表需要设置instant flag

convert相关函数调用关系：
```cpp
rec_convert_dtuple_to_rec()
	rec_convert_dtuple_to_rec_new()
		rec_get_converted_size_comp() // 计算转换成物理记录后的总大小 extra + data
			rec_get_converted_size_comp_prefix_low()
		rec_convert_dtuple_to_rec_comp() // 实际生成rec的函数
		rec_set_instant_flag_new()
	rec_convert_dtuple_to_rec_old()
```
## Overview
### n_fields
n_fields表示对于该行记录，需要取到多少个field，即逻辑field数量。因为同一个index的non-leaf node和leaf node存储的数据不一样，需要单独判断

- **old-style**：结合数据字典判断 `rec_get_n_fields_old()`
   - no instant：rec中的n_fields， `rec_get_n_fields_old_raw()` 
   - has instant：表执行过instant add column
      - **non-leaf node**：不会有instant field， `rec_get_n_fields_old_raw()` 
      - **leaf node**： `dict_index_get_n_fields()` 
- **new-style**：无论是否有instant add column，逻辑都不变， `rec_get_n_fields()`
   - leaf node: `dict_index_get_n_fields()` 
   - non-leaf node: `dict_index_get_n_unique_in_tree() + 1` 

参考函数： `rec_get_offsets_func()` 

### inline fields
在有instant add column特性之前，数据字典和行记录信息一致，n_fields个field都能从rec中得到；在有了instant add column特性之后，可能会出现有些field需要从数据字典中取default值的情况，inline fields即表示可以从rec中取到的field

- **old-rec：rec的n_fields** `rec_get_n_fields_old_raw()`
- **new-style：**
   - no instant： `dict_index_t::n_fields` 
   - **rec write before instant：** `dict_index_t::``get_instant_fields()` (fields before first instant fields)
   - **rec write after instant：**rec的n_fields， `rec_get_n_fields_instant()` 

参考下面的函数： `rec_get_nth_field_old_instant()` / `rec_get_nth_field_instant()` / `rec_init_offsets_comp_ordinary()` / `rec_init_null_and_len_comp()` 

> **TIPS**:
> 1. 关于 `dict_index_t::n_instant_nullable` 和 `get_instant_fields()` 的逻辑可以参考[dict](#9yIIu)
> 2. 是否has instant通过 `dict_index_t::instant_cols` 判断
> 3. write before/after instant通过rec的instant_flag标志位判断（ `rec_get_instant_flag_new(rec)` ）


### nullable fields (new-style only)
Compact格式中的null flag字段需要根据nullable列的数量计算得到，有了instant add column特性之后， `dict_index_t::n_nullable` 表示的是最新的表结构中的信息，并不是实际物理记录rec中的n_nullable值

- leaf node
   - **no instant**： `dict_index_t::n_nullable` 
   - **rec write after instant**： `get_n_nullable_before(inline_fields)` ( dict_index_t::n_nullable - nullable fields after inline_fields) 
   - **rec write before instant**： `dict_index_t::n_instant_nullable` 
- non-leaf node
   - `dict_index_t::n_instant_nullable` ，不受instant add column影响，仍然是instant add column前nullable列的数量（在没有instant add column特性之前，该值是 `dict_index_t::n_nullable` ，在第一次instant add column的时候，会把n_nullable赋值给n_instan_nullable）

参考下面的函数： `rec_init_null_and_len_comp()` / `rec_init_offsets_comp_ordinary()` 

### instant fields about leaf and non-leaf node
instant fields只能存在于cluster index的leaf node；cluster index的non-leaf node和secondary index，都不会有instant fields，因此只有cluster index的leaf node会有instant flag和n_fields(compact)字段。

参考函数： `rec_get_converted_size_comp_prefix_low()` / `rec_convert_dtuple_to_rec_comp()` / `rec_init_offsets()`

cluster index的instant fields数量参考函数 `dict_index_t::get_instant_fields()` 
注意：dict中的n_instant_col表示first instant add column之前表中列的数量

### ⭐update and rollback
结论是只要不是inplace update，一定会更新成新的行格式（set instant flag and n_fields）

- inplace update：只更新对应field的值（btr_cur_optimistic_update() -> btr_cur_update_in_place() -> row_upd_rec_in_place() -> rec_set_nth_field()）
- **non inplace update**：更新成新的行格式，instant field部分写入（ `rec_convert_dtuple_to_rec_comp()` ）
- **update for rollback**：更新成新的行格式，field还原成update之前的field，不会写入新增的instant field

optimistic update的主要逻辑（ `btr_cur_optimistic_update()` ）

1. 根据要更新的cursor得到block、page、rec、index
2. 根据rec和index得到offsets数组（ `rec_get_offsets()` ）
3. 从rec中读出逻辑记录new_entry（ `row_rec_to_index_entry()` ）
   1. 创建 `rec_offs_n_fields()` 大小的dtuple
   2. 依次填充dtuple的每个field（ `rec_get_nth_field_instant()` ）
4. 更新逻辑记录（ `row_upd_index_replace_new_col_vals_index_pos()` ）
5. ignore new_entry结尾instant field且是default值的field（ `ignore_trailing_default()` ）
6. 写undo，delete原记录，insert新纪录（ `btr_cur_insert_if_possible()` -> `rec_convert_dtuple_to_rec()` ）

第3步中，创建的dtuple的dfield个数为从offsets数组里取到的n_fields，该值是根据index得到的逻辑的值，与当前表结构的信息一致（dict_index_t::n_fields）；但是在第5步中，把instant fields且是default值的dfield都去掉了，因此写入的field数量比当前表定义的field数量要小。

这也是在 `rec_convert_dtuple_to_rec()` 函数中，对于有instant add columns特性的表， `n_null = index->get_n_nullable_before(n_fields)`  的原因。

对于rollback的数据，在第3步中对于当前表结构多出来的field，一定都会被填上default值；在第5步中，这些值都会被ignore掉；最终逻辑记录的field和原物理记录中field一致，但是在调用convert函数转换成rec的过程中，会set instant flag和n_fields字段。

### functions about n_fields and nth_field**
```
+----------------------------+----------------------+-----+-------+--------------+------------------+
| function                   | source file          | git | style | record-type  | target           |
+----------------------------+----------------------+-----+-------+--------------+------------------+
| rec_get_n_fields           | include/rem0rec.ic   | Mod | Both  | all          | logical n_fields |
+----------------------------+----------------------+-----+-------+--------------+------------------+
| rec_get_n_fields_old       | include/rem0rec.ic   | Mod | Old   | instant*     | logical n_fields |
+----------------------------+----------------------+-----+-------+--------------+------------------+
| rec_get_n_fields_old_raw   | include/rem0rec.ic   | Add | Old   | inline-only  | header n_fields  |
+----------------------------+----------------------+-----+-------+--------------+------------------+
| rec_get_n_fields_instant   | include/rem0rec.ic   | Add | New   | instant-only | header n_fields  |
+----------------------------+----------------------+-----+-------+--------------+------------------+	
| rec_set_n_fields           | include/rem0rec.ic   | Add | New   | instant-only | header n_fields  |
+----------------------------+----------------------+-----+-------+--------------+------------------+
| rec_set_n_fields_old       | include/rem0rec.ic   | OK. | Old   | all          | header n_fields  |
+----------------------------+----------------------+-----+-------+--------------+------------------+
```

```
+-------------------------------+----------------------+-----+-------+--------------+------------------+
| function                      | source file          | git | style | record-type  | target           |
+-------------------------------+----------------------+-----+-------+--------------+------------------+
| rec_get_nth_field_offs        | include/rem0rec.ic   | Mod | Both  | all          | offsets to field |
+-------------------------------+----------------------+-----+-------+--------------+------------------+
| rec_get_nth_field_offs_old    | rem/rem0rec.cc       | Mod | Old   | inline-only  | record to field  |
+-------------------------------+----------------------+-----+-------+--------------+------------------+
| rec_get_nth_field             | include/rem0rec.h    | Mod | Both  | inline-only  | offsets to field |
+-------------------------------+----------------------+-----+-------+--------------+------------------+
| rec_get_nth_field_instant     | include/rem0rec.ic   | Add | New   | all          | header n_fields  |
+-------------------------------+----------------------+-----+-------+--------------+------------------+
| rec_get_nth_field_old         | include/rem0rec.h    | OK. | Old   | inline-only  | header n_fields  |
+-------------------------------+----------------------+-----+-------+--------------+------------------+
| rec_get_nth_field_old_instant | include/rem0rec.ic   | Add | Old   | all          | header n_fields  |
+-------------------------------+----------------------+-----+-------+--------------+------------------+
| rec_get_nth_field_size        | include/rem0rec.ic   | OK. | Old   | all          | header n_fields  |
+-------------------------------+----------------------+-----+-------+--------------+------------------+
```

## code diff
### n_fields in new-style
n_fields字段在null flag和hdr之间，使用1字节或2字节表示。当n_field小于等于127时，使用1字节表示，否则使用2字节表示，逆序第一个字节的最高位用于表示2bit flag。
```cpp
/** Set the number of fields for one new style leaf page record.
This is only needed for table after instant ADD COLUMN.
@param[in,out]	rec		leaf page record
@param[in]	n_fields	number of fields in the record
@return	the length of the n_fields occupies */
UNIV_INLINE
uint8_t rec_set_n_fields(rec_t *rec, ulint n_fields) {
  byte *ptr = rec - (REC_N_NEW_EXTRA_BYTES + 1);

  ut_ad(n_fields < REC_MAX_N_FIELDS);

  if (n_fields <= REC_N_FIELDS_ONE_BYTE_MAX) {
    *ptr = static_cast<byte>(n_fields);
    return (1);
  }

  --ptr;
  *ptr++ = static_cast<byte>(n_fields & 0xFF); // 低字节
  *ptr = static_cast<byte>(n_fields >> 8); // 高字节
  ut_ad((*ptr & 0x80) == 0);
  *ptr |= REC_N_FIELDS_TWO_BYTES_FLAG; // 逆序第1个字节的最高位用于表示2bit flag

  return (2);
}
```

```cpp
/** Get the number of fields for one new style leaf page record.
This is only needed for table after instant ADD COLUMN.
@param[in]	rec		leaf page record
@param[in]	extra_bytes	extra bytes of this record
@param[in,out]	length		length of number of fields
@return	number of fields */
UNIV_INLINE
uint32_t
rec_get_n_fields_instant(
/*=====================*/
	const rec_t*	rec,
	const ulint	extra_bytes,
	uint16_t*	length)
{
	uint16_t	n_fields;
	const byte*	ptr;

	ptr = rec - (extra_bytes + 1);

	if ((*ptr & REC_N_FIELDS_TWO_BYTES_FLAG) == 0) {
		*length = 1;
		return (*ptr);
	}

	*length = 2;
	n_fields = ((*ptr-- & REC_N_FIELDS_ONE_BYTE_MAX) << 8);
	n_fields |= *ptr;
	ut_ad(n_fields < REC_MAX_N_FIELDS);
	ut_ad(n_fields != 0);

	return (n_fields);
}
```

### offsets
生成offsets数组涉及到解析rec信息，因为行格式做了修改，这里的逻辑也有一些变化。

**Compact格式****ordinary****节点offsets生成**（ `rec_init_offsets_comp_ordinary()` ）：

1. null flag和n_fields信息解析： `rec_init_null_and_len_comp()`
2. var-len col length解析
   1. start pointer计算方法有所不同（在上面的函数中已经处理）
   2. 对于不在var-len col legth中的列，需要取default值的length（ `rec_get_instant_offset()` ）

**Compact格式node_ptr节点offsets生成：**non-leaf节点不可能有instant add column，不需要考虑这种情况

**Redundant格式offsets生成：**与Compact相比，简单很多，主要是处理不在col offset list中的列的offset信息，方法与处理Compact格式的相同

```cpp
/** Determines the information about null bytes and variable length bytes
for a new style record
@param[in]	rec		physical record
@param[in]	index		index where the record resides
@param[out]	nulls		the start of null bytes
@param[out]	lens		the start of variable length bytes
@param[out]	n_null		number of null fields
@return	the number of fields which are inlined of the record */
UNIV_INLINE
uint16_t
rec_init_null_and_len_comp(
/*=======================*/
	const rec_t*		rec,
	const dict_index_t*	index,
	const byte**		nulls,
	const byte**		lens,
	uint16_t*		n_null)
{
	uint16_t	non_default_fields = dict_index_get_n_fields(index);

	*nulls = rec - (REC_N_NEW_EXTRA_BYTES + 1);

	if (!index->has_instant_cols()) {
        // 没有instant add column，dict_index_t::n_nullable就表示
        // 物理记录中nullable列的数量，逻辑不变
		*n_null = index->n_nullable;
	} else if (rec_get_instant_flag_new(rec)) {
		/* Row inserted after first instant ADD COLUMN */
        // 该行数据有n_fields字段，n_fields字段表示该行rec的实际列数
		uint16_t length;
		non_default_fields = rec_get_n_fields_instant(rec, REC_N_NEW_EXTRA_BYTES, &length);
		ut_ad(length == 1 || length == 2);

        // null flag指针需要再向前移动1或2字节
		*nulls -= length;
        // nullable列的数量不包含写入该行数据后的nullable列
		*n_null = index->get_n_nullable_before(non_default_fields);
	} else {
		/* Row inserted before first instant ADD COLUMN */
        // 该行数据没有n_fields字段，null flag指针再不需要移动
        
        // 有了Instant Add Column，dict_index_t::nullable和物理记录中实际的nullable不一样
        // 使用dict_index_t::n_instant_nullable表示Instant Add Column之前
        // 表中nullable列的数量
		*n_null = index->n_instant_nullable;
        // 实际列数从数据字典中取
		non_default_fields = index->get_instant_fields();
	}

	*lens = *nulls - UT_BITS_IN_BYTES(*n_null);

	return (non_default_fields);
}
```

**Compact ordinary节点的解析代码diff：**
```cpp
/******************************************************//**
Determine the offset to each field in a leaf-page record
in ROW_FORMAT=COMPACT.  This is a special case of
rec_init_offsets() and rec_get_offsets_func(). */
UNIV_INLINE MY_ATTRIBUTE((nonnull))
void
rec_init_offsets_comp_ordinary(
/*===========================*/
	const rec_t*		rec,	/*!< in: physical record in
					ROW_FORMAT=COMPACT */
	bool			temp,	/*!< in: whether to use the
					format for temporary files in
					index creation */
	const dict_index_t*	index,	/*!< in: record descriptor */
	ulint*			offsets)/*!< in/out: array of offsets;
					in: n=rec_offs_n_fields(offsets) */
{
    // ... ...
    
    // 通过该函数计算nulls指针, lens指针, n_null, inline fields的数量
    if (temp) {
		non_default_fields =
			rec_init_null_and_len_temp(rec, index, &nulls, &lens, &n_null);
	} else {
		non_default_fields =
			rec_init_null_and_len_comp(rec, index, &nulls, &lens, &n_null);
	}
    
    /* read the lengths of fields 0..n */
	do {
        // ... ...
        
        // 对于非inline的列，取
        if (i >= non_default_fields) {
			ut_ad(index->has_instant_cols());
			len = rec_get_instant_offset(index, i, offs);
			goto resolved;
		}
        // ... ...
	} while (++i < rec_offs_n_fields(offsets));
    // ... ...
}


/** Determine the offset of a specified field in the record, when this
field is a field added after an instant ADD COLUMN
@param[in]	index	Clustered index where the record resides
@param[in]	n	Nth field to get offset
@param[in]	offs	Last offset before current field
@return The offset of the specified field */
UNIV_INLINE
uint64_t
rec_get_instant_offset(
/*===================*/
	const dict_index_t*	index,
	uint16_t		n,
	uint64_t		offs)
{
	ut_ad(index->has_instant_cols());

    // 从数据字典中取default值和len
	ulint length;
	index->get_nth_default(n, &length);

	if (length == UNIV_SQL_NULL) {
		return (offs | REC_OFFS_SQL_NULL);
	} else {
		return (offs | REC_OFFS_DEFAULT);
	}
}
```

**Compact node_ptr节点解析代码diff：**
即node pointer节点的null flag的长度与instant add column之前相同，不会有变化（instant add column不可能在non-leaf node中出现）
```cpp
static
void
rec_init_offsets(
/*=============*/
	const rec_t*		rec,	/*!< in: physical record */
	const dict_index_t*	index,	/*!< in: record descriptor */
	ulint*			offsets)/*!< in/out: array of offsets;
					in: n=rec_offs_n_fields(offsets) */
{
    // ... ...
    if (dict_table_is_comp(index->table)) {
        // ... ...
        // 读取NODE_PTR类型rec
        nulls = rec - (REC_N_NEW_EXTRA_BYTES + 1);
        
        // before
        // lens = nulls - UT_BITS_IN_BYTES(index->n_nullable);
        // after
        lens = nulls - UT_BITS_IN_BYTES(index->n_instant_nullable);
        offs = 0;
        null_mask = 1;

        /* read the lengths of fields 0..n */
    }
    // ... ...
}
```

**Redundant 格式的解析代码diff：**
```cpp
static
void
rec_init_offsets(
/*=============*/
	const rec_t*		rec,	/*!< in: physical record */
	const dict_index_t*	index,	/*!< in: record descriptor */
	ulint*			offsets)/*!< in/out: array of offsets;
					in: n=rec_offs_n_fields(offsets) */
{
	ulint	i	= 0;
	ulint	offs;

	if (dict_table_is_comp(index->table)) {	
        // ... ...
	} else {
		/* Old-style record: determine extra size and end offsets */
		offs = REC_N_OLD_EXTRA_BYTES;
		if (rec_get_1byte_offs_flag(rec)) {
			offs += rec_get_n_fields_old_raw(rec);
			*rec_offs_base(offsets) = offs;
			/* Determine offsets to fields */
			do {
                // 对于非inline的数据，从数据字典中取
				if (index->has_instant_cols() &&
				    i >= rec_get_n_fields_old_raw(rec)) {
					offs &= ~REC_OFFS_SQL_NULL;
					offs = rec_get_instant_offset(index, i, offs);
				} else {
					offs = rec_1_get_field_end_info(rec, i);
				}

				if (offs & REC_1BYTE_SQL_NULL_MASK) {
					offs &= ~REC_1BYTE_SQL_NULL_MASK;
					offs |= REC_OFFS_SQL_NULL;
				}

				ut_ad(i < rec_get_n_fields_old_raw(rec) ||
				      (offs & REC_OFFS_SQL_NULL) ||
				      (offs & REC_OFFS_DEFAULT));
				rec_offs_base(offsets)[1 + i] = offs;
			} while (++i < rec_offs_n_fields(offsets));
		} else {
            // ... ...
        }
    }
}
```

### get_n_fields
**old-style**主要逻辑在于判断是否是页节点的行（即是数据还是索引），对于页节点，直接从数据字典中获取最新的列数即可；对于非页节点，应当返回rec中实际的列数。
**
```cpp
/******************************************************//**
The following function is used to get the number of fields
in an old-style record. Have to consider the case that after
instant ADD COLUMN, this record may have less fields than
current index.
@param[in]	rec	physical record
@param[in]	index	index where the record resides
@return number of data fields */
UNIV_INLINE
MY_ATTRIBUTE((warn_unused_result)) uint16_t
rec_get_n_fields_old(
	const rec_t *rec,
	const dict_index_t *index)
{
    // 该rec中实际存储的列的数量
	uint16_t n = rec_get_n_fields_old_raw(rec);

    // 对于有instant cols的表需要从dict中获取列数
	if (index->has_instant_cols()) {
        // 对于clustered index来说，返回的是dict_index_t::n_uniq的值，
        // 即primary key的列数
		uint16_t n_uniq = dict_index_get_n_unique_in_tree_nonleaf(index);

        // instant add column只能出现在clustered index上，
        // 如果要对instant add column添加index，那么必须要rebuild table，
        // 也就没有instant cols了
		ut_ad(index->is_clustered());
        
        // 
		ut_ad(n <= dict_index_get_n_fields(index));
		ut_ad(n_uniq > 0);
		/* Only when it's infimum or supremum, n is 1.
		If n is exact n_uniq, this should be a record copied with prefix
		during search.
        
        // clustered index
        // 对于non-leaf node来说 n = n_uniq(primary_key) + 1(node pointer)
        // 对于leaf node来说，n >= n_uniq(primary_key) + 2(trx_id and roll_ptr)
        
		And if it's node pointer, n is n_uniq + 1, which should be
		always less than the number of fields in any leaf page, even if
		the record in leaf page is before instant ADD COLUMN. This is
		because any record in leaf page must have at least n_uniq + 2
		(system columns) fields */
		ut_ad(n == 1 || n >= n_uniq);
		ut_ad(static_cast<uint16_t>(dict_index_get_n_fields(index)) > n_uniq + 1);
		if (n > n_uniq + 1) { // is leaf node
#ifdef UNIV_DEBUG
            // 非inline的fields
			uint16_t rec_diff = dict_index_get_n_fields(index) - n;
            // instant cols
			uint16_t col_diff = index->table->n_cols - index->table->n_instant_cols;
			// 可能有一些instant fields写到了rec中
            ut_ad(rec_diff <= col_diff);
			if (n != dict_index_get_n_fields(index)) {
				ut_ad(index->has_instant_cols());
			}
#endif /* UNIV_DEBUG */
			n = dict_index_get_n_fields(index);
		}
        // 对于non-leaf node，不可能有instant add column的列
	}

	return (n);
}
```

对于**new-style**，其status字段已经记录了是否是leaf node的信息，可以根据status和dict共同计算得到n_fields信息，计算逻辑与之前没有变化。

### get_nth_field
**old-style**
```cpp
/** Gets the value of the specified field in the record in old style.
This is only used for record from instant index, which is clustered
index and has some instantly added columns.
@param[in]	rec	physical record
@param[in]	n	index of the field
@param[in]	index   clustered index where the record resides
@param[out]	len	length of the field, UNIV_SQL if SQL null
@return value of the field, could be either pointer to rec or default value */
UNIV_INLINE
const byte *
rec_get_nth_field_old_instant(
	const rec_t *rec,
	uint16_t n,
	const dict_index_t *index,
	ulint *len)
{
	ut_a(index != NULL);

	if (n < rec_get_n_fields_old_raw(rec)) {
		return (rec_get_nth_field_old(rec, n, len));
	}

	const byte *field;

	ut_ad(index->has_instant_cols());

	field = index->get_nth_default(n, len);
	return (field);
}
```

**new_style**
```cpp
/** Gets the value of the specified field in the record.
This is only used when there is possibility that the record comes from the
clustered index, which has some instantly add columns
@param[in]	rec	record
@param[in]	offsets	array returned by rec_get_offsets()
@param[in]	n	index of the field
@param[in]	index	clustered index where the record resides
@param[in,out]	len	length of the field, UNIV_SQL_NULL if SQL null
@return	value of the field, could be either pointer to rec or default value */
UNIV_INLINE
const byte *
rec_get_nth_field_instant(
	const rec_t *rec,
	const ulint *offsets,
	ulint n,
	const dict_index_t *index,
	ulint *len)
{
    // offsets数组中已经处理好了是否是inline列的信息
	ulint off = rec_get_nth_field_offs(offsets, n, len);

	if (*len != UNIV_SQL_ADD_COL_DEFAULT) {
		return (rec + off);
	}

	ut_a(index != NULL);
	ut_ad(index->has_instant_cols());

	return (index->get_nth_default(n, len));
}
```

### rec_convert
**converted size**

Q: 此处对于n_null的计算逻辑，对于instant add column的表，为什么是 `index->get_n_nullable_before(n_fields)` ，而不是直接取 `index->n_nullable` ?
A: 可能要转换的数据（dtuple_t）的列已经和现在的dict信息不一致了，参考[rollback](#My8Ry)一节

```cpp
/**********************************************************//**
Determines the size of a data tuple prefix in ROW_FORMAT=COMPACT.
@return total size */
UNIV_INLINE MY_ATTRIBUTE((warn_unused_result, nonnull(1,2)))
ulint
rec_get_converted_size_comp_prefix_low(
/*===================================*/
	const dict_index_t*	index,	/*!< in: record descriptor;
					dict_table_is_comp() is
					assumed to hold, even if
					it does not */
	const dfield_t*		fields,	/*!< in: array of data fields */
	ulint			n_fields,/*!< in: number of data fields */
	const dtuple_t*		v_entry,/*!< in: dtuple contains virtual column
					data */
	ulint*			extra,	/*!< out: extra size */
	ulint*			status,	/*!< in: status bits of the record,
					can be NULL if unnecessary */ // ADD for instant add column
	bool			temp)	/*!< in: whether this is a
					temporary file record */
{
	ulint	extra_size = 0;
	ulint	data_size;
	ulint	i;
	ulint	n_null	= 0;
	ulint	n_v_fields;
    
    // before:
    // ulint	n_null	= (n_fields > 0) ? index->n_nullable : 0;
    // 对于在instant add column之前的数据，需要得到正确的n_nullable值
    if (n_fields > 0) {
		n_null = index->has_instant_cols() ?
			index->get_n_nullable_before(n_fields)
			: index->n_nullable;
	}

	if (index->has_instant_cols() && status != NULL) {
		switch (UNIV_EXPECT(*status, REC_STATUS_ORDINARY)) {
		case REC_STATUS_ORDINARY:
			ut_ad(!temp && n_fields > 0);
            // extra_size加上n_fields的长度
			extra_size += rec_get_n_fields_length(n_fields);
			break;
		case REC_STATUS_NODE_PTR:
			ut_ad(!temp && n_fields > 0);
			n_null = index->n_instant_nullable;
			break;
		case REC_STATUS_INFIMUM:
		case REC_STATUS_SUPREMUM:
			break;
		}
	}

	extra_size += temp
		? UT_BITS_IN_BYTES(n_null)
		: REC_N_NEW_EXTRA_BYTES
		+ UT_BITS_IN_BYTES(n_null);
    
    data_size = 0;
    /* read the lengths of fields 0..n */
    // ... ...
    
	return(extra_size + data_size);
}
```

**convert**
如果有instant add column，对于leaf node和non-leaf node，需要单独处理:

- leaf node才会有instant add column，需要考虑n_fields和null flag长度的变化；
- non-leaf node不会有instant add column，行格式仍然是老得compact格式，不存在n_fields字段。
```cpp
/*********************************************************//**
Builds a ROW_FORMAT=COMPACT record out of a data tuple.*/
UNIV_INLINE
bool
rec_convert_dtuple_to_rec_comp(
/*===========================*/
	rec_t*			rec,	/*!< in: origin of record */
	const dict_index_t*	index,	/*!< in: record descriptor */
	const dfield_t*		fields,	/*!< in: array of data fields */
	ulint			n_fields,/*!< in: number of data fields */
	const dtuple_t*		v_entry,/*!< in: dtuple contains
					virtual column data */
	ulint			status,	/*!< in: status bits of the record */
	bool			temp)	/*!< in: whether to use the
					format for temporary files in
					index creation */
{
    // ... ...
    
    bool		instant = false;

    // 新增
    // n_nullable需要经过计算得到
	if (n_fields != 0) {
		n_null = index->has_instant_cols() ?
			index->get_n_nullable_before(n_fields)
			: index->n_nullable;
	}

    if (temp) {
         // ... ...
	} else {
		ut_ad(v_entry == NULL);
		ut_ad(num_v == 0);
		nulls = rec - (REC_N_NEW_EXTRA_BYTES + 1);

		switch (UNIV_EXPECT(status, REC_STATUS_ORDINARY)) {
		case REC_STATUS_ORDINARY:
			ut_ad(n_fields <= dict_index_get_n_fields(index));
			n_node_ptr_field = ULINT_UNDEFINED;

            // 新增
            // leaf-node 需要写入n_fields信息
            // 并把nulls指针向前移动
			if (index->has_instant_cols()) {
				uint32_t n_fields_len;
				n_fields_len = rec_set_n_fields(rec, n_fields);
				nulls -= n_fields_len;
				instant = true;
			}
			break;
		case REC_STATUS_NODE_PTR:
            // leaf node 格式不更改
			ut_ad(n_fields == dict_index_get_n_unique_in_tree_nonleaf(index) + 1);
			n_node_ptr_field = n_fields - 1;
			n_null = index->n_instant_nullable;
			break;
		case REC_STATUS_INFIMUM:
		case REC_STATUS_SUPREMUM:
			ut_ad(n_fields == 1);
			n_node_ptr_field = ULINT_UNDEFINED;
			break;
		default:
			ut_error;
			return (instant);
		}
	}
    
    // ... ...
}
```

### ignore_trailing_default
```cpp
/** Ignore trailing default fields if this is a tuple from instant index
@param[in]	index		clustered index object for this tuple */
void dtuple_t::ignore_trailing_default(const dict_index_t *index) {
  if (!index->has_instant_cols()) {
    return;
  }

  /* It's necessary to check all the fields that could be default.
  If it's from normal update, it should be OK to keep original
  default values in the physical record as is, however,
  if it's from rollback, it may rollback an update from default
  value to non-default. To make the rolled back record as is,
  it has to check all possible default values. */
  for (; n_fields > index->get_instant_fields(); --n_fields) {
    const dict_col_t *col = index->get_field(n_fields - 1)->col;
    const dfield_t *dfield = dtuple_get_nth_field(this, n_fields - 1);
    ulint len = dfield_get_len(dfield);

    ut_ad(col->instant_default != NULL);

    // 非default值
    if (len != col->instant_default->len ||
        (len != UNIV_SQL_NULL &&
         memcmp(dfield_get_data(dfield), col->instant_default->value, len) != 0)) {
      break;
    }
  }
}
```

# Data Dictionary
Instant Add Column对于数据字典的更改，有以下几点：

1. **使用 **`**SYS_TABLES**` **表记录第一次INSTANT ADD COLUMN前该表的列数，用于读取INSTANT ADD COLUMN 前写入的行数据时判断应该读多少列**
2. **增加一个新的系统表 **`**SYS_INSTANT**` 记录**INSTANT ADD COLUMN列的DEFAULT值，用于读取非inline列时使用（非inline的数据可能是instant Add Column之前写入的，也可能是多次Instant Add Column后非最新写入的数据）**

**
从information_schema中可以看到相关信息如下：

- INNODB_SYS_TABLES.INSTANT_COLS字段记录第一次Instant Add Column时表所有的列数
- INNODB_SYS_COLUMNS.DEFAULT_VALUE和INNODB_SYS_INSTANT.DEFAULT_VALUE中记录Instant Add Column列的Default值（DDL更改了Default值后不会更新这里的值，原因可以参考[https://www.yuque.com/littleneko/note/gtptal#Examples](https://www.yuque.com/littleneko/note/gtptal#Examples)）

**![image.png](https://cdn.nlark.com/yuque/0/2020/png/385742/1594713573392-b862939c-e4ce-4c55-b03d-7fb4e4eac8b1.png#align=left&display=inline&height=587&originHeight=587&originWidth=1208&size=210459&status=done&style=none&width=1208)**
> 注意：information_schema中的表的列与SYS_TABLES、SYS_COLUMNS、SYS_INSTANT等表的实际表结构并不一致，实际上information_schema类似于一个视图



**代码涉及到需要修改的地方有**：

1. 系统表更改
   1. 增加 `SYS_INSTANT` 表存储Instant Add Column的default值 ( `dict_create_or_check_sys_instant()` )
   2. 存储 `n_instasnt_cols` 值到 `SYS_TABLES` 表中（ `dict_update_n_instant()` ）
      1. 编码到 `SYS_TABLES.MIX_LEN` 未使用的高16位中
      2. 存储到表中的值不包括system columns
2. dict cache更改
   1. `dict_table_t` ：增加 `n_instant_cols` 字段
   2. `dict_col_t` : 保存default值
   3. `dict_index_t` 
   4. `dict_field_t` 
3. **DDL**
   1. Instant Add Column : 
      1. 更改 `SYS_TABLES.MIX_LEN` 的值（ `dict_update_n_instant()` ）
      2. 更改 `SYS_INSTANT` 表的数据
   2. Create Table（包括rebuild table），需要设置 `SYS_TABLES.MIX_LEN` 的 `n_instant_cols` 字段为0（ `dict_create_table_step()` -> ... -> `dict_create_sys_tables_tuple()` ）
4. **dict load**
   1. 读取 `SYS_TABLES` 表中存储的 `n_instalt_cols` 值（ `dict_load_table_low()` ）
   2. 读取 `SYS_INSTANT` 表中的Instant Add Column的default值（ `dict_load_instant()` ）

## Overview
### support instant add
```cpp
/** Determine if the table can support instant ADD COLUMN */
inline bool dict_table_t::support_instant_add() const {
  return (!DICT_TF_GET_ZIP_SSIZE(flags) && space != TRX_SYS_SPACE &&
          !DICT_TF2_FLAG_IS_SET(this, DICT_TF2_FTS_HAS_DOC_ID) &&
          !dict_table_is_temporary(this));
}
```
### dict_table_t::n_instant_cols (new)
Number of non-virtual columns before first instant ADD COLUMN, including the system columns like n_cols

存储在  `SYS_TABLES.MIX_LEN` 的高16位，其值不包括系统列（原本只使用了低9位存储flags2），ref： `dict_update_n_instant()` / `dict_table_encode_mix_len()` / `dict_table_decode_mix_len()`

### dict_index_t::n_instant_nullable (new)
该值表示在第一次Instant Add Column之前索引中nullable列的数量，不需要持久化，在load table的时候可以通过instant fields的数量计算出来：
`new_index->get_n_nullable_before(new_index->get_instant_fields())` 

e.g.
clust-index: [not_null, nullable, not_null, nullable, nullable |instant|, nullable, not_null, nullable]
index->n_instant_nullable == 3;  // before the 1st instant add column.

| **NAME** | **TYPE** | **DESC** |
| --- | --- | --- |
| n_instant_nullable | unsigned:10 | number of nullable fields before first instant ADD COLUMN applied to this table.  This is valid only when has_instant_cols() is true |
| instant_cols | unsigned:1 | TRUE if the index is clustered index and it has some instant columns |


### fields before first instant ADD COLUMN (get_instant_fields())
该值表示在clustered index中，第一次instant add column之前的fields数量，也是rec write before instant add column的inline field数量。
```sql
/** Returns the number of fields before first instant ADD COLUMN */
inline uint32_t dict_index_t::get_instant_fields() const {
  ut_ad(has_instant_cols());
  return (n_fields - (table->n_cols - table->n_instant_cols));
}
```
![image.png](https://cdn.nlark.com/yuque/0/2020/png/385742/1595169865062-b9e08461-96d3-4330-b1e3-d60e189b76d3.png#align=left&display=inline&height=1166&originHeight=1166&originWidth=1980&size=120365&status=done&style=none&width=1980)
> **TIPS:**
> table->n_cols和clust_index->n_fields并不相等，一是可能有前缀索引，前缀索引列和原完整列在index->n_fields会占用2个位置；二是table->n_cols包括了一个ROW_ID，而index->n_fields可能没有ROW_ID.


### default value
default值存储在 `SYS_INSTANT` 表中，按如下方式存储：
```
+-----------+-----------------+--------------+-------------------------+
| case      |  param: length  | param: value | instant_default->value  |
+-----------+-----------------+--------------+-------------------------+
| NULL      |   UNIV_SQL_NULL |         NULL |                    NULL |
+-----------+-----------------+--------------+-------------------------+
| empty     |               0 |         NULL |                    "\0" |
+-----------+-----------------+--------------+-------------------------+
| non-empty | (0, 0xFFFFFFFF) |    non-empty |    copy of param: value |
+-----------+-----------------+--------------+-------------------------+
```

## code diff
### system tables
** `SYS_INSTANT` 表**
新增函数 `dict_create_or_check_sys_instant()` 用于创建表
```cpp
/** Creates the instantly added columns system table (SYS_INSTANT) inside InnoDB
at server bootstrap or server start if the table is not found or is
not of the right form.
@return DB_SUCCESS or error code */
dberr_t
dict_create_or_check_sys_instant()
{
    // ... ...
    
	err = que_eval_sql(
		NULL,
		"PROCEDURE CREATE_SYS_INSTANT_PROC () IS\n"
		"BEGIN\n"
		"CREATE TABLE\n"
		"SYS_INSTANT(TABLE_ID BIGINT UNSIGNED NOT NULL,"
		" POS INT NOT NULL,"
		" DEFAULT_VALUE CHAR);\n"
		"CREATE UNIQUE CLUSTERED INDEX INSTANT_IDX"
		" ON SYS_INSTANT(TABLE_ID, POS);\n"
		"END;\n",
		FALSE, trx);
    // ... ...
}
```
```cpp
/* The columns in SYS_INSTANT */
enum dict_col_sys_instant_enum {
	DICT_COL__SYS_INSTANT__TABLE_ID = 0,
	DICT_COL__SYS_INSTANT__POS = 1,
	DICT_COL__SYS_INSTANT__DEFAULT_VALUE = 2,
	DICT_NUM_COLS__SYS_INSTANT = 3
};
/* The field numbers in the SYS_INSTANT clustered index */
enum dict_fld_sys_instant_enum {
	DICT_FLD__SYS_INSTANT__TABLE_ID = 0,
	DICT_FLD__SYS_INSTANT__POS = 1,
	DICT_FLD__SYS_INSTANT__DB_TRX_ID = 2,
	DICT_FLD__SYS_INSTANT__DB_ROLL_PTR = 3,
	DICT_FLD__SYS_INSTANT__DEFAULT_VALUE = 4,
	DICT_NUM_FIELDS__SYS_INSTANT = 5
};

```

**`SYS_TABLES` 表**
虽然要存储 `n_instant_cols` 到 `SYS_TABLES` 表中，但是表结构不需要更改， `n_instanl_cols` 值保存到了 `MIX_LEN` 未使用的空间中。（实际上4个base system tables的表结构是不能更改的）

### n_instant_cols
#### decode and encode
`n_instant_cols` 值存储在 `SYS_TABLES.MIX_LEN` 的高16位
```cpp
/** encode flags2 and number of core columns in one
4 bytes value.
@param[in]	flags2
@param[in]	n_instant column number before first time instant add column
@return encoded value */
UNIV_INLINE
ulint
dict_table_encode_mix_len(
	ulint	flags2,
	ulint	n_instant)
{
	/* Be sure all non-used bits are zero. */
	ut_a(!(flags2 & DICT_TF2_UNUSED_BIT_MASK));
	ut_a(!(flags2 & 0xFFFF0000));

	return (flags2 + (n_instant << 16));
}

/** Decode number of flags2 and number of core columns in one 4 bytes value.
@param[in]	encoded	encoded value
@param[in,out]	flags2
@param[in,out]	n_instant column number before first time instant add column*/
UNIV_INLINE
void
dict_table_decode_mix_len(
	ulint	encoded,
	ulint*	flags2,
	ulint*	n_instant)
{
	*flags2 = encoded & 0xFFFF;

	*n_instant = encoded >> 16;
}
```

#### write
**Instant Add Column**
使用 `dict_update_n_instant()` 函数对 `SYS_TABLES` 表的 `MIX_LEN` 字段进行更新（ 在DDL的过程中调用`handler0alter::innobase_add_instant_try()` ）

需要注意的地方：

1. 需要同时更新 `N_COLS` ，并且 `N_COLS` 中编码的 `n_cols` 是不包含系统列的
2. 保存到 `SYS_TABLES.MIX_LEN` 中的instant_cols不包括系统列（使用 `table->get_instant_cols()` 取的值）
```cpp
/** Update INNODB SYS_TABLES on number of instantly added columns
@param[in] user_table   InnoDB table
@param[in] added_cols   number of new instantly added columns
@param[in] trx      transaction
@return DB_SUCCESS if successful, otherwise error code */
dberr_t
dict_update_n_instant(
    const dict_table_t* table,
    ulint           added_cols,
    trx_t*          trx)
{
    dberr_t     err = DB_SUCCESS;
    pars_info_t*    info = pars_info_create();
    /* Encode the new number of stored user columns, the number of virtual
    columns and table->flags into the N_COLS field */
    const ulint n_cols = dict_table_encode_n_col(
        dict_table_get_n_user_cols(table) + added_cols,
        dict_table_get_n_v_cols(table))
        | ((table->flags & DICT_TF_COMPACT) << 31);
    /* Encode the number of 'core' columns (i.e. those existing before the
    first instantly added column) and table->flags2 into the MIX_LEN
    field. This value changes only once on the first instantly added column,
    but for simplicity we update it along with N_COLS on every instantly
    added column. */
    const ulint mix_len = dict_table_encode_mix_len(
        table->flags2, table->get_instant_cols());
    pars_info_add_int4_literal(info, "num_col", n_cols);
    pars_info_add_int4_literal(info, "mix_len", mix_len);
    pars_info_add_ull_literal(info, "id", table->id);
    err = que_eval_sql(
        info,
        "PROCEDURE P () IS\n"
        "BEGIN\n"
        "UPDATE SYS_TABLES"
        " SET N_COLS = :num_col,\n"
        " MIX_LEN = :mix_len\n"
        " WHERE ID = :id;\n"
        "END;\n", FALSE, trx);
    return(err);
}
```

**Create Table**
在create table的流程中（ `dict_create_table_step()` -> `dict_build_table_def_step()` -> `dict_create_sys_tables_tuple()` ）写入 `MIX_LEN` 字段时，需要把高16位的n_instant_cols置0。

> 此处的create table应该包括了用户建表和rebuild table过程中的建表

```cpp
/*****************************************************************//**
Based on a table object, this function builds the entry to be inserted
in the SYS_TABLES system table.
@return the tuple which should be inserted */
static
dtuple_t*
dict_create_sys_tables_tuple(
/*=========================*/
	const dict_table_t*	table,	/*!< in: table */
	mem_heap_t*		heap)	/*!< in: memory heap from
					which the memory for the built
					tuple is allocated */
{
    // ... ...
    /* 7: MIX_LEN (additional flags) --------------------------*/
	dfield = dtuple_get_nth_field(entry, DICT_COL__SYS_TABLES__MIX_LEN);

	ptr = static_cast<byte*>(mem_heap_alloc(heap, 4));
	/* No instantly added columns in a newly created table. */
	mach_write_to_4(ptr, dict_table_encode_mix_len(table->flags2, 0));

	dfield_set_data(dfield, ptr, 4);
    
    // ... ...
}
```

#### read
参考 [dict load](https://www.yuque.com/littleneko/ubavq5/xs126o/edit) 一节

### dict_index_t::n_instant_nullable
#### init
```sql
dberr_t
dict_index_add_to_cache_w_new_col(
	dict_table_t*		table,
	dict_index_t*		index,
	const dict_add_v_col_t* add_v,
	const dict_add_i_col_t* add_i,
	ulint			page_no,
	ibool			strict)
{
	// ... ...
  
	if (new_index->table->has_instant_cols() && new_index->is_clustered()) {
		new_index->instant_cols = true;
		new_index->n_instant_nullable =
			new_index->get_n_nullable_before(new_index->get_instant_fields());
	} else {
		new_index->instant_cols = false;
		new_index->n_instant_nullable = new_index->n_nullable;
	}
  // ... ...
}
```
#### get_n_nullable_before
```cpp
struct dict_index_t{
    // ... ...
    
	/** Returns the number of nullable fields before specified
	nth field
	@param[in]	nth	nth field to check */
	uint32_t get_n_nullable_before(uint32_t nth) const {
		ulint nullable = n_nullable;

		ut_ad(nth <= n_fields);

		for (uint32_t i = nth; i < n_fields; ++i) {
			if (get_field(i)->col->is_nullable()) {
				--nullable;
			}
		}

		return (nullable);
	}
    // ... ...
}
```

使用到该值的地方：

- `rec_init_null_and_len_comp()`  时计算null flag的长度
- `rec_get_converted_size_comp_prefix_low()` 和 `rec_convert_dtuple_to_rec_comp()` 时计算null flag的长度
- mtrlog

### default value
default值在dict cache中保存在 `dict_cols_t` 中：
```cpp
/** Data structure for default value of a column in a table */
struct dict_col_default_t {
  /** Pointer to the column itself */
  dict_col_t *col;
  /** Default value in bytes */
  const byte *value;
  /** Length of default value */
  size_t len;
};


/** Data structure for a column in a table */
struct dict_col_t{
	/*----------------------*/
	/** The following are copied from dtype_t,
	so that all bit-fields can be packed tightly. */
	/* @{ */

	/** Default value when this column was added instantly.
	If this is not a instantly added column then this is NULL. */
	dict_col_default_t *instant_default;
    
    /** Set default value
	@param[in]	value	Default value
	@param[in]	length	Default value length
	@param[in,out]	heap	Heap to allocate memory */
	void set_default(const byte *value, size_t length, mem_heap_t *heap);
    
    // ... ...
}
```

使用函数 `get_nth_default()` 取该值
```cpp
struct dict_index_t{
    // ... ...
    
	/** Get the default value of nth field and its length if exists.
	If not exists, both the return value is NULL and length is 0.
	@param[in]	nth	nth field to get
	@param[in,out]	length	length of the default value
	@return	the default value data of nth field */
	const byte *get_nth_default(uint16_t nth, ulint *length) const {
		ut_ad(nth < n_fields);
		ut_ad(get_instant_fields() <= nth);
		const dict_col_t *col = get_col(nth);
		if (col->instant_default == NULL) {
			*length = 0;
			return (NULL);
		}

		*length = col->instant_default->len;
		ut_ad(*length == 0 || *length == UNIV_SQL_NULL ||
		      col->instant_default->value != NULL);
		return (col->instant_default->value);
	}
}
```
**场景:**
一方面可以得到 立即列的默认值，以便提供给上层来读取数据.
比如: 用到立即列的二级索引字段的值的确定，主键行返回给Server层时，应当返回的值.
一方面可以通过该函数判断 nth fields in an index 是否是立即列，从而决定该字段的值从rec还是从col->instant_default中获取。

使用到该函数的地方：

1. `rec_get_nth_field_old_instant()` 
2. `rec_get_nth_field_instant()` 
3. `rec_get_instant_offset()` ：主要是取length值


使用函数 `set_default()` 设置该值：
```cpp
/** Set default value
@param[in]	value	Default value
@param[in]	length	Default value length
@param[in,out]	heap	Heap to allocate memory */
void dict_col_t::set_default(
	const byte *value,
	size_t length,
	mem_heap_t *heap)
{
	ut_ad(instant_default == NULL);
	ut_ad(length == 0 || length == UNIV_SQL_NULL || value != NULL);

	instant_default = static_cast<dict_col_default_t *>(
		mem_heap_alloc(heap, sizeof(dict_col_default_t)));

	instant_default->col = this;

	if (length != UNIV_SQL_NULL) {
		const char *val =
			(value == NULL ? "\0" :
			 reinterpret_cast<const char *>(value));

		instant_default->value =
			reinterpret_cast<byte *>(
				mem_heap_strdupl(heap, val, length));
	} else {
		ut_ad(!(prtype & DATA_NOT_NULL));
		instant_default->value = NULL;
	}

	instant_default->len = length;
}
```

### dict load
**load instant**
`dict_process_sys_instant_rec_low()` / `dict_load_instant()` 

**load table**
```cpp
/** Loads a table definition from a SYS_TABLES record to dict_table_t.
Does not load any columns or indexes.
@param[in]	name	Table name
@param[in]	rec	SYS_TABLES record
@param[out,own]	table	table, or NULL
@return error message, or NULL on success */
static
const char*
dict_load_table_low(
	table_name_t&	name,
	const rec_t*	rec,
	dict_table_t**	table)
{
    table_id_t	table_id;
	ulint		space_id;
	ulint		mix_len;
	ulint		n_cols;
	ulint		n_instant;
	ulint		t_num;
	ulint		flags;
	ulint		flags2;
	ulint		n_v_col;
    
    // ... ...
    
    dict_sys_tables_rec_read(rec, name, &table_id, &space_id,
				 &t_num, &flags, &mix_len);

	if (flags == ULINT_UNDEFINED) {
		return("incorrect flags in SYS_TABLES");
	}
    
    dict_table_decode_n_col(t_num, &n_cols, &n_v_col);

    // 需要注意mix_len读出来后要decode成flag2和n_instatl_cols
	dict_table_decode_mix_len(mix_len, &flags2, &n_instant);

	*table = dict_mem_table_create(
		name.m_name, space_id, n_cols + n_v_col, n_v_col, flags, flags2);

    // ... ...
}
```

