（如未做特殊说明，下面所有分析基于MySQL 5.7.x版本）
# Introduction
**数据字典**（Data Dictionary）即表的元数据（表的基本信息、列信息、索引信息等），当对表进行读写时需要先获取表的数据字典信息，对表做DDL时也需要修改这些信息。

数据字典保存在系统表空间的 `SYS_TABLES` , `SYS_COLUMNS` , `SYS_INDEXES` , `SYS_FIELDS` 等表中（上面4个表在代码中被称为 basic system tables），当打开一个用户表时就从磁盘中加载对应表的数据字典到内存缓存中(以 `dict_table_t` , `dict_col_t` , `dict_index_t` , `dict_field_t` , `dict_foreign_t` 等对象保存在 `sys_dict_t` 的 `LRU` 中)。数据字典加载到内存中以后，并不是一直保存在内存中，需要通过 `sys_table_t` 中的 `LRU` 进行淘汰策略。
**
> **TIPS:**
> 读取上述4个系统表时同样需要先获取其元数据，不过这些元数据并不保存在某个表中，而是直接在初始化时生成( `dict_boot()` )。


除了上述4个基本系统表外，还有 `SYS_DATAFILES` , `SYS_FOREIGN` , `SYS_FOREIGN_COLS` , `SYS_TABLESPACES` , `SYS_VIRTUAL` 等表也用来存储一些元信息，这些表是通过CREATE TABLE语句创建的表，其元数据保存在上述4个基本系统表中，读取这些表的数据时需要从上面4个基本系统表中获取元数据信息。

**数据字典相关模块**

| **Module** | **Description** | **Detail** |
| --- | --- | --- |
| dict0boot | Data dictionary creation and booting | 
1. 创建数据字典表物理结构（ `dict_hdr_create()` ）
2. 初始化系统表的数据字典缓存对象（ `dict_boot()` ）
3. 分配table_id, index_id（ `dict_hdr_get_new_id()` ）
 |
| dict0crea | Database object creation | 
1. 建表时数据字典信息的创建
 |
| dict0load | Loads to the memory cache database object definitions from dictionary tables | 
1. 加载系统表的元数据到内存缓存中
2. information_schema库中相关系统表的处理
 |
| dict0dict | Data dictionary system | 所有对dict操作的接口 |
| dict0mem | Data dictionary memory object creation | 
1. 数据字典内存对象的定义和操作：`dict_table_t` , `dict_col_t` , `dict_index_t` , `dict_foergin_t` 
2. 数据字典内存对象的创建接口
 |


# 数据字典内存对象(dict0mem, dict0dict)
## sys_dict_t
`sys_dict_t` 是数据字典的核心struct，数据字典所有信息都由该struct管理，从该结构出发可以找到所有数据字典相关的信息。
```c
// file: dict0dict.h
//
/* Dictionary system struct */
struct dict_sys_t{
	DictSysMutex	mutex;		/*!< mutex protecting the data
					dictionary; protects also the
					disk-based dictionary system tables;
					this mutex serializes CREATE TABLE
					and DROP TABLE, as well as reading
					the dictionary data for a table from
					system tables */
	row_id_t	row_id;		/*!< the next row id to assign;
					NOTE that at a checkpoint this
					must be written to the dict system
					header and flushed to a file; in
					recovery this must be derived from
					the log records */
	hash_table_t*	table_hash;	/*!< hash table of the tables, based
					on name */
	hash_table_t*	table_id_hash;	/*!< hash table of the tables, based
					on id */
	lint		size;		/*!< varying space in bytes occupied
					by the data dictionary table and
					index objects */
	dict_table_t*	sys_tables;	/*!< SYS_TABLES table */
	dict_table_t*	sys_columns;	/*!< SYS_COLUMNS table */
	dict_table_t*	sys_indexes;	/*!< SYS_INDEXES table */
	dict_table_t*	sys_fields;	/*!< SYS_FIELDS table */
	dict_table_t*	sys_virtual;	/*!< SYS_VIRTUAL table */

	/*=============================*/
	UT_LIST_BASE_NODE_T(dict_table_t)
			table_LRU;	/*!< List of tables that can be evicted
					from the cache */
	UT_LIST_BASE_NODE_T(dict_table_t)
			table_non_LRU;	/*!< List of tables that can't be
					evicted from the cache */
	autoinc_map_t*	autoinc_map;	/*!< Map to store table id and autoinc
					when table is evicted */
};
```
## 表定义(dict_table_t，dict_col_t)
**dict_table_t**

| **name** | **type** | **desc** |
| --- | --- | --- |
| flags | unsigned:8 | 
1. 从高位到低位的标志位和长度:

&#124; SHARED_SPACE:1 &#124; DATA_DIR:1 &#124; ATOMIC_BLOBS:1  &#124; ZIP_SSIZE:4 &#124; COMPACT:1 &#124;

2. Use `DICT_TF_GET_COMPACT()` , `DICT_TF_GET_ZIP_SSIZE()` , `DICT_TF_HAS_ATOMIC_BLOBS()`  and `DICT_TF_HAS_DATA_DIR()`  to parse this flag


3. 最低位COMPACT标志从 `SYS_TABLES.``N_COLS` 中取得，高7位从 `SYS_TABLES.``TYPE` 中取得( `dict_sys_tables_type_to_tf()` )
 |
| flags2 | unsigned:9 | 
1. 从高位到低位的标志位和长度:

&#124; ENCRYPTION:1 &#124; INTRINSIC:1 &#124; FTS_AUX_HEX_NAME:1 &#124; DISCARDED:1 &#124; USE_FILE_PER_TABLE:1 &#124; FTS_ADD_DOC_ID:1 &#124; FTS:1 &#124; FTS_HAS_DOC_ID:1 &#124; TEMPORARY:1 &#124; 

2. 使用 `DICT_TF2_FLAG_SET()` , `DICT_TF2_FLAG_IS_SET()` , `DICT_TF2_FLAG_UNSET()` 处理该flag


3. flags2 = `SYS_TABLES.``MIX_LEN` 
 |
| **n_def** | unsigned:10 | cols数组当前实际使用数量，初始值为0，每次调用 `dict_mem_table_add_col()` 都会使该值++ |
| **n_cols** | unsigned:10 | **non-virtual columns + ****system columns**

- 在 `dict_mem_table_create()` 时初始化，会添加2或3个系统列
- `SYS_TABLES.N_COLS`  中保存的 `n_cols` 并不包括3个系统列，参考 `dict_load_table_low()`  函数中对读取的 `SYS_TABLES.N_COLS` 值的处理


**number of system columns**
- intrinsic tabale: 2( `DATA_ITT_N_SYS_COLS` )，没有roll_ptr
- 非 intrinsic table: 3( `DATA_N_SYS_COLS` )
 |
| n_v_def | unsigned:10 | 当前已经向v_cols中添加了多少列的信息，每次调用 `dict_mem_table_add_v_col()` 都会使该值++ |
| n_v_cols | unsigned:10 | Number of virtual columns. |
| n_t_def | unsigned:10 | n_def + n_v_def |
| n_t_cols | unsigned:10 | non-virtual columns + virtual columns + system columns |
| **cols** | dict_col_t*(array) | 大小为 `n_cols` ，在 `dict_mem_table_create()` 时就分配好了空间，实际使用的大小由 `n_def` 定义 |
| v_cols | dict_v_col_t* (array) | 大小为 `n_v_cols`  |
| col_names | char* | 
1. Column names packed in a character string "name1\\0name2\\0...nameN\\0"


2. 使用 `dict_table_get_col_name()` 函数取得第 _i _列的列名


**TIPS**:
因为 `col_names` 是一个连续的内存空间，实际上 `dict_table_get_col_name()` 函数只是把指针移动到了第 _i _列列名的起始地址，拿到该指针后就可以通过移动指针拿到 _i ~ n_def _列所有的列名，参考 `innobase_get_col_names()` 函数中的使用方法。 |
| autoinc | ib_uint64_t | Autoinc counter value to give to the next inserted row. |
|  |  |  |


**dict_col_t**

| **NAME** | **TYPE** | **DESC** |
| --- | --- | --- |
| prtype | unsigned:32 | precise type; MySQL data type, charset code, flags to indicate nullability, signedness, whether this is a binary string, whether this is a true VARCHAR where MySQL uses 2 bytes to store the length |
| mtype | unsigned:8 | main data type. ref: [dtype_t](https://www.yuque.com/littleneko/ubavq5/gw2r53#Ry6xI) |
| len | unsigned:16 | length; for MySQL data this is field->pack_length(), except that for a >= 5.0.3 type true VARCHAR this is the maximum byte length of the string data (in addition to the string, MySQL uses 1 or bytes to store the string length)

pack_length() returns size (in bytes) used to store field data in memory (i.e. it returns the **maximum size of the field in a row of the table**, which is located in RAM) |
| mbminmaxlen | unsigned:5 | 在prtype中描述的编码下的的最大最小长度 |
| ind | unsigned:10 | table column position (starting from 0)  |
| ord_part | unsigned:1 | nonzero if this column appears in the ordering fields of an index |
| max_prefix | unsigned:12 | maximum index prefix length on this column. Our current max limit is 3072 for Barracuda table
该col出现的所有index中的prefix的最大值 |


### create
```cpp
/**********************************************************************//**
Creates a table memory object.
@return own: table object */
dict_table_t*
dict_mem_table_create(
/*==================*/
	const char*	name,	/*!< in: table name */
	ulint		space,	/*!< in: space where the clustered index of
				the table is placed */
	ulint		n_cols,	/*!< in: total number of columns including
				virtual and non-virtual columns */
	ulint		n_v_cols,/*!< in: number of virtual columns */
	ulint		flags,	/*!< in: table flags */
	ulint		flags2)	/*!< in: table flags2 */
{
    // ... ...
    
    table->flags = (unsigned int) flags;
	table->flags2 = (unsigned int) flags2;
	table->name.m_name = mem_strdup(name);
	table->space = (unsigned int) space;
	table->n_t_cols = (unsigned int) (n_cols + dict_table_get_n_sys_cols(table));
	table->n_v_cols = (unsigned int) (n_v_cols);
	table->n_cols = table->n_t_cols - table->n_v_cols;
	table->n_instant_cols = table->n_cols;

	table->cols = static_cast<dict_col_t*>(
		mem_heap_alloc(heap, table->n_cols * sizeof(dict_col_t)));
	table->v_cols = static_cast<dict_v_col_t*>(
		mem_heap_alloc(heap, n_v_cols * sizeof(*table->v_cols)));
    
    // ... ...
}
```

### dict_table_t::flags
**COMPACT**
COMPACT标志位用来表示是否是REDUNDANT格式，其他相关flag的最低位在不同行格式下的值如下：
```
==================== Low order flags bit =========================
                    | REDUNDANT | COMPACT | COMPRESSED and DYNAMIC
SYS_TABLES.TYPE     |     1     |    1    |     1
dict_table_t::flags |     0     |    1    |     1
FSP_SPACE_FLAGS     |     0     |    0    |     1
fil_space_t::flags  |     0     |    0    |     1
```

**ATOMIC_BLOBS**
该字段用来标识两种file format ( `UNIV_FORMAT_A` , `UNIV_FORMAT_B` )：Antelope file format (包括REDUNDANT, COMPACT行格式)把 `BLOB` 和 `TEXT` 类型的前768字节存储在clustered index中，剩下的存储在溢出页中；Barracuda file format (COMPRESS, DYNAMIC)则把所有数据存储在溢出页中。

### dict_table_t::flags2
```
/** TEMPORARY; TRUE for tables from CREATE TEMPORARY TABLE. */
#define DICT_TF2_TEMPORARY		1

/** The table has an internal defined DOC ID column */
#define DICT_TF2_FTS_HAS_DOC_ID		2

/** The table has an FTS index */
#define DICT_TF2_FTS			4

/** Need to add Doc ID column for FTS index build.
This is a transient bit for index build */
#define DICT_TF2_FTS_ADD_DOC_ID		8

/** This bit is used during table creation to indicate that it will
use its own tablespace instead of the system tablespace. */
#define DICT_TF2_USE_FILE_PER_TABLE	16

/** Set when we discard/detach the tablespace */
#define DICT_TF2_DISCARDED		32

/** This bit is set if all aux table names (both common tables and
index tables) of a FTS table are in HEX format. */
#define DICT_TF2_FTS_AUX_HEX_NAME	64

/** Intrinsic table bit
Intrinsic table is table created internally by MySQL modules viz. Optimizer,
FTS, etc.... Intrinsic table has all the properties of the normal table except
it is not created by user and so not visible to end-user. */
#define DICT_TF2_INTRINSIC		128

/** Encryption table bit. */
#define DICT_TF2_ENCRYPTION		256
```

### system columns
对于非intrinsic table来说，table的system columns个数是3( `DATA_N_SYS_COLS` )，三个system columns的mtype都是 `DATA_SYS` ，参考函数 `dict_table_add_system_columns()` 。

`dict_table_t` 的初始化流程是 `dict_mem_table_create()`  -> `dict_mem_table_add_col()` -> `dict_table_add_to_cache()` -> `dict_table_add_system_columns()` ，因此三个系统列定义一般是添加在 `dict_table_t::cols` 的末尾的，且一定是按上面的顺序添加。

需要注意的是 `dict_table_t::cols` 中的col顺序并不代表物理记录的列顺序，InnoDB是索引组织表，数据即聚簇索引，因此实际存储的数据列定义和顺序应该由**clustered index**的 `dict_index_t::fields` 定义。
```cpp
/**********************************************************************//**
Adds system columns to a table object. */
void
dict_table_add_system_columns(
/*==========================*/
	dict_table_t*	table,	/*!< in/out: table */
	mem_heap_t*	heap)	/*!< in: temporary heap */
{
    // ... ...
	dict_mem_table_add_col(table, heap, "DB_ROW_ID", DATA_SYS, // mtype
			       DATA_ROW_ID | DATA_NOT_NULL,				   // prtype
			       DATA_ROW_ID_LEN);
	dict_mem_table_add_col(table, heap, "DB_TRX_ID", DATA_SYS,
			       DATA_TRX_ID | DATA_NOT_NULL,
			       DATA_TRX_ID_LEN);
	if (!dict_table_is_intrinsic(table)) {
		dict_mem_table_add_col(table, heap, "DB_ROLL_PTR", DATA_SYS,
				       DATA_ROLL_PTR | DATA_NOT_NULL,
				       DATA_ROLL_PTR_LEN);
    }
}
```

## 索引定义(dict_index_t, dict_field_t)
**dict_index_t**

| **NAME** | **TYPE** | **DESC** |
| --- | --- | --- |
| **n_uniq** | unsigned | 能决定一个索引记录唯一性的fields数，
- **cluster index : **
   - 定义的fields满足唯一性：index_key 
   - 定义的fields不满足唯一性：index_key + row_id
- **secondary unique index : **index_key 
- **secondary index : **index_key + clust_key (去除重复field) 


在 `dict_index_build_internal_clust()` / `dict_index_build_internal_non_clust()` 中初始化

注意与下面提到的 n_unique_in_tree 区分 |
| **n_fields** | unsigned | 该index包含的fields的数量 ：
- **cluster index : **index_key + system_columns + other_user_cols  (去除重复field)
- **secondary index :** index_key + clust_key (去除重复field)


在 `dict_index_add_to_cache_w_new_col()` -> `dict_index_build_internal_clust()` / `dict_index_build_internal_non_clust()` 最后赋值为 `n_def` 

_user representation index_中用来表示创建该索引定义的列数，即 index_key，比如创建一个index(a, b) 2列的索引，该值就是2 |
| n_def | unsigned | fields数组中实际使用的field数量（分配的n_fields个field可能不会完全用上），每次调用`dict_mem_index_add_field()` 时该值++ |
| n_user_defined_cols | unsigned | 创建该索引定义的列数，比如index(a, b)，该值就是2，即_user representation index_中的n_fields值 |
| **fields** | dict_field_t*
(array) | 
- **clustered index:** _[index_key,__ [row_id], trx_id, roll_ptr, other_user_cols, [NULL]...]_
- **secondary index：**_[ind__ex_key, clust_key, [NULL]...]__ _(去除重复field)

（参考[Record Format](https://www.yuque.com/littleneko/ubavq5/gw2r53#UaHeM)相关内容）

user representation index中：n_fields个大小，保存用户定义的索引列 |
| **n_nullable** | unsigned | 索引中nullable列的数量，在 `dict_index_build_internal_clust()` / `dict_index_build_internal_non_clust()` -> `dict_index_add_col()` 中初始化 |
| to_be_dropped | unsigned | 
1. TRUE if the index is to be dropped; protected by dict_operation_lock
2. 在 `ha_innobase::prepare_inplace_alter_table()` 流程中对所有需要drop的非主键索引该flag置为TRUE
 |
| search_info | btr_search_t* |  |
| uncommitted | unsigned:1 | a flag that is set for secondary indexes that have not been committed to the data dictionary yet.
用于在add index DDL中（ `row_merge_create_index()` ）判断是否需要设置index_name以 `TEMP_INDEX_PREFIX_STR` 开头表示是不可见的表 |


**dict_field_t**

| **NAME** | **TYPE** | **DESC** |
| --- | --- | --- |
| col | dict_col_t* | pointer to the table column
 |
| name | id_name_t | name of the column |
| prefix_len | unsigned | 0 (0 表示没有使用前缀索引) or the length of the column prefix **in bytes** in a MySQL index of type, e.g., INDEX (textcol(25)); must be smaller than DICT_MAX_FIELD_LEN_BY_FORMAT; NOTE that in the UTF-8 charset, MySQL sets this to (mbmaxlen * the prefix len) in UTF-8 chars
一个index中，可能有多个field指向table的同一个col，但是field的prefix_len不同 |
| fixed_len | unsigned | 0 or the fixed length of the column (**in bytes**) if smaller than DICT_ANTELOPE_MAX_INDEX_COL_LEN |


**注意**：
在使用过程中，对该struct有 _user representation index_ 的表述，即 `dict_index_add_to_cache()` 时传入的 `dict_index_t` 对象只是作为临时对象使用，最终加入到cache中的对象是在该函数中另外创建的。

参考 `dict_boot()` 函数中生成系统表的 `dict_index_t` 的流程，生成一个 `dict_index_t` cache的过程如下：

- 调用 `dict_mem_index_create()` 创建一个 `dict_index_t` 对象，其 `n_fields` 为需要建索引的列的数量（只是一个临时用的对象，即_user representation index，_最终加到cache中的并不是这个对象）
- 调用 `dict_mem_index_add_field()` 把所有用户建索引的列名加进去，调用次数应该和上一步中的 `n_fields` 相等
- 调用 `dict_index_add_to_cache()` 把“该对象”加入到 `sys_dict_t`  cache中
   - clustered index： `dict_index_build_internal_clust()` 
   - non clustered index： `dict_index_build_internal_non_clust()` 

在上面两个函数中，会根据情况另外生成新的 `dict_index_t` 对象，其字段值和传入的 `dict_index_t` 对象并不一样，比如该函数会加入一些system fields，因此 `n_fields` 的值也有不同。

### 索引类型
索引类型由 `dict_index_t::type` 字段标识，一共有以下几种类型。
```cpp
/** Type flags of an index: OR'ing of the flags is allowed to define a
combination of types */
/* @{ */
#define DICT_CLUSTERED	1	/*!< clustered index; for other than
				auto-generated clustered indexes,
				also DICT_UNIQUE will be set */
#define DICT_UNIQUE	2	/*!< unique index */
#define	DICT_IBUF	8	/*!< insert buffer tree */
#define	DICT_CORRUPT	16	/*!< bit to store the corrupted flag
				in SYS_INDEXES.TYPE */
#define	DICT_FTS	32	/* FTS index; can't be combined with the
				other flags */
#define	DICT_SPATIAL	64	/* SPATIAL index; can't be combined with the
				other flags */
#define	DICT_VIRTUAL	128	/* Index on Virtual column */

#define	DICT_IT_BITS	8	/*!< number of bits used for
				SYS_INDEXES.TYPE */
/* @} */
```
### ⭐dict_field_t::fixed_len（区分定常和变长字段）
dict_field_t::fixd_len表示需要in-page存储的数据长度，在 `dict_index_add_col()` 流程中初始化。

**REDUNDANT**

- Internally, fixed-length character columns such as CHAR(10) are stored in fixed-length format. Trailing spaces are not truncated from VARCHAR columns.
- Fixed-length columns greater than or equal to 768 bytes are encoded as variable-length columns, which can be stored off-page. For example, a CHAR(255) column can exceed 768 bytes if the maximum byte length of the character set is greater than 3, as it is with utf8mb4.

**COMPACT**

- Internally, for **nonvariable-length character sets**, fixed-length character columns such as CHAR(10) are stored in a fixed-length format.
- Internally, for **variable-length character sets** such as utf8mb3 and utf8mb4, InnoDB attempts to store CHAR(N) in N bytes by trimming trailing spaces. If the byte length of a CHAR(N) column value exceeds N bytes, trailing spaces are trimmed to a minimum of the column value byte length. The maximum length of a CHAR(N) column is the maximum character byte length × N.

A minimum of N bytes is reserved for CHAR(N). Reserving the minimum space N in many cases enables column updates to be done in place without causing index page fragmentation. By comparison, CHAR(N) columns occupy the maximum character byte length × N when using the REDUNDANT row format.
Fixed-length columns greater than or equal to 768 bytes are encoded as variable-length fields, which can be stored off-page. For example, a CHAR(255) column can exceed 768 bytes if the maximum byte length of the character set is greater than 3, as it is with utf8mb4.
(ref: [14.11 InnoDB Row Formats](https://dev.mysql.com/doc/refman/5.7/en/innodb-row-format.html))

> **TIPS：**
> 1. **CHAR(x)在COMPACT格式下latn-1等定长编码下是定长类型（fixed length type）(fixed_len = x * 3)；在utf-8等变长编码下，是变长类型（fixed_len = 0）**
> 2. **CHAR(x)在REDUNDANT格式下是定长编码类型（fixed_len = x * mbmaxlen）**
> 3. 长度超过**DICT_MAX_FIXED_COL_LEN的字段也被认为是变长字段**


```cpp
/*******************************************************************//**
Adds a column to index. */
void
dict_index_add_col(
/*===============*/
	dict_index_t*		index,		/*!< in/out: index */
	const dict_table_t*	table,		/*!< in: table */
	dict_col_t*		col,		/*!< in: column */
	ulint			prefix_len)	/*!< in: column prefix length */
{
    // ... ...
    
    /* DATA_POINT is a special type, whose fixed_len should be:
	1) DATA_MBR_LEN, when it's indexed in R-TREE. In this case,
	it must be the first col to be added.
	2) DATA_POINT_LEN(be equal to fixed size of column), when it's
	indexed in B-TREE,
	3) DATA_POINT_LEN, if a POINT col is the PRIMARY KEY, and we are
	adding the PK col to other B-TREE/R-TREE. */
	/* TODO: We suppose the dimension is 2 now. */
	if (dict_index_is_spatial(index) && DATA_POINT_MTYPE(col->mtype)
	    && index->n_def == 1) {
		field->fixed_len = DATA_MBR_LEN;
	} else {
		field->fixed_len = static_cast<unsigned int>(
					dict_col_get_fixed_size( // 调用dtype_get_fixed_size_low()
					col, dict_table_is_comp(table)));
	}

    // 作为索引的field，只需要要存储prefix_len长度的数据在in-page
	if (prefix_len && field->fixed_len > prefix_len) {
		field->fixed_len = (unsigned int) prefix_len;
	}

	/* Long fixed-length fields that need external storage are treated as
	variable-length fields, so that the extern flag can be embedded in
	the length word. */

	if (field->fixed_len > DICT_MAX_FIXED_COL_LEN) {
		field->fixed_len = 0;
	}
#if DICT_MAX_FIXED_COL_LEN != 768
	/* The comparison limit above must be constant.  If it were
	changed, the disk format of some fixed-length columns would
	change, which would be a disaster. */
# error "DICT_MAX_FIXED_COL_LEN != 768"
#endif
    
    // ... ...
}
```

### build internal clustered index
Builds the internal dictionary cache representation for a clustered index, containing also system fields not defined by the user.

1. 创建一个新的 `dict_index_t` 对象new_index（ `dict_mem_index_create()` ）
   1. _初始值 new_index->n_fields = index->n_fields + table->n_cols_（最多需要那么多fields）
   2. new_index->n_user_defined_cols = index->n_fields;
2. 拷贝user representation index 中的所有field到new_index中，一共需要拷贝index->n_fields个，拷贝完成后new_index->n_def的值刚好等于index->n_fields（ `dict_index_copy()` ）
3. 初始化new_index->n_uniq
   1. index是unique的：_new_index->n_uniq = new_index->n_def_
   2. 否则：_new_index->n_uniq = 1 + new_index->n_def_
4. 添加 `DATA_ROW_ID` (index不是uniq时需要添加该列)、 `DATA_TRX_ID` 、`DATA_ROLL_PTR` 3个system columns
5. Add to new_index non-system columns of table not yet included there。把 table->cols 中不在 new_index->fields 中的所有col添加到new_index中（ `dict_index_add_col()` ）
6. 设置 new_index->n_fields = new_index->n_def

注意：

1. 添加table->cols中的列到new_index->fields中时，需要排除掉已经在new_index->fields中的列（pk定义列、system columns）
2. **If there is only a prefix of the column in the index field, do not mark the column as contained in the index****。**即如果定义的是前缀索引，那么仍需要把原本的列加到index的fields中。

e.g. 1. table->cols = [a, b, c, d, _row_id, trx_id, roll_ptr_]，定义 index->fields = [a, b(10)] 为clustered index且满足唯一性（index->type = DICT_UNIQUE | DICT_CLUSTERED），那么初始值new_index->n_fields = 9 (2 + 7)，第5步中需要把table->cols中的 _[b, c, d]_ 3个cols添加到new_index->fields中。最终new_index中相关的值如下：

- n_user_defined_cols = 2
- n_fields = 7 = n_def
- fields = [_a, b(10)_, trx_id, roll_ptr, **b, c, d**, NULL, NULL]
- n_uniq = 2 (表示fields的前2个列 [a, b(10)] 能确定索引的唯一性])
- n_def = 7

e.g. 2. table->cols = [a, b, c, d, _row_id_, _trx_id_, _roll_ptr_]，定义 index->fields = [a, b] 为clustered index且满足唯一性（index->type = DICT_UNIQUE | DICT_CLUSTERED），那么new_index->n_fields = 9 (2 + 7)，第5步中只需要把table->cols中的 _[c, d]_ 2个cols添加到new_index->fields中。最终new_index中相关的值如下：

- n_user_defined_cols = 2
- n_field = 6 = n_def
- fields = [_a, b_, trx_id, roll_ptr, **c, d**, NULL, NULL, NULL]
- n_uniq = 2 (表示fields的前2个列 [a, b] 能确定索引的唯一性])
- n_def = 6

传入的index->type没有设置DICT_UNIQUE的情况：如果建表语句没定义primary key，mysql会使用第一个定义的not null 的 unique index作为clustered index；如果mysql找不到任何一个not null的unique index作为clusterd index，就会使用innodb生成的row_id，这时传入的index应该是空的

e.g. 3. table->cols = [a, b, c, d, _row_id, trx_id, roll_ptr_]，传入 index = [] 为clustered index且不满足唯一性（index->type = DICT_CLUSTERED），那么初始值new_index->n_fields = 7 (0 + 7)，第5步中需要把table->cols中的 _[a, b, c, d]_ 3个cols添加到new_index->fields中。最终new_index中相关的值如下：

- n_user_defined_cols = 0
- n_fields = 7 = n_def
- fields = [**_row_id_**, trx_id, roll_ptr, **a, b, c, d**]
- n_uniq = 1 (表示fields的前1个列 [row_id] 能确定索引的唯一性])
- n_def = 7

```cpp
/*******************************************************************//**
Builds the internal dictionary cache representation for a clustered
index, containing also system fields not defined by the user.
@return own: the internal representation of the clustered index */
static
dict_index_t*
dict_index_build_internal_clust(
/*============================*/
	const dict_table_t*	table,	/*!< in: table */
	dict_index_t*		index)	/*!< in: user representation of
					a clustered index */
{
    dict_index_t*	new_index;
	dict_field_t*	field;
	ulint		trx_id_pos;
	ulint		i;
	ibool*		indexed;
    
    /* Create a new index object with certainly enough fields */
    // 注意这里传入的n_fields参数为index->n_fields + table->n_cols,
    // 即表的列数（包含系统列）+ 用户索引定义的列数
    // 这里是考虑到index的fields并不是table的cols的情况，
    // 比如前缀索引，因此分配了足够的空间存放index的fields，
	new_index = dict_mem_index_create(table->name.m_name,
					  index->name, table->space,
					  index->type,
					  index->n_fields + table->n_cols);

	/* Copy other relevant data from the old index struct to the new
	struct: it inherits the values */
	new_index->n_user_defined_cols = index->n_fields;
	new_index->id = index->id;

	/* Copy the fields of index */
    // 该步骤完成后new_index->n_def == index->n_fields
	dict_index_copy(new_index, index, table, 0, index->n_fields);

    // 用户定义聚簇索引所用的列可能并不能满足唯一性要求，这时候需要把row_id列加到索引中
	if (dict_index_is_unique(index)) {
		/* Only the fields defined so far are needed to identify
		the index entry uniquely */
		new_index->n_uniq = new_index->n_def;
	} else {
		/* Also the row id is needed to identify the entry */
		new_index->n_uniq = 1 + new_index->n_def;
	}
    
    new_index->trx_id_offset = 0;

	/* Add system columns, trx id first */
	trx_id_pos = new_index->n_def;
    
    if (!dict_index_is_unique(index)) {
		dict_index_add_col(new_index, table,
				   dict_table_get_sys_col(table, DATA_ROW_ID), 0);
		trx_id_pos++;
	}

	dict_index_add_col(
		new_index, table,
		dict_table_get_sys_col(table, DATA_TRX_ID), 0);
    
    // ... ...
    
    /* UNDO logging is turned-off for intrinsic table and so
	DATA_ROLL_PTR system columns are not added as default system
	columns to such tables. */
	if (!dict_table_is_intrinsic(table)) {
		dict_index_add_col(
			new_index, table,
			dict_table_get_sys_col(table, DATA_ROLL_PTR),
			0);
	}
    
    // 标记table->cols中所有已经在new_index->fields中的列
    /* Remember the table columns already contained in new_index */
	indexed = static_cast<ibool*>(ut_zalloc_nokey(table->n_cols * sizeof *indexed));

	/* Mark the table columns already contained in new_index */
	for (i = 0; i < new_index->n_def; i++) {
		field = dict_index_get_nth_field(new_index, i);

		/* If there is only a prefix of the column in the index
		field, do not mark the column as contained in the index */
		if (field->prefix_len == 0) {
			indexed[field->col->ind] = TRUE;
		}
	}
    
    /* Add to new_index non-system columns of table not yet included there */
	ulint n_sys_cols = dict_table_get_n_sys_cols(table);
	for (i = 0; i + n_sys_cols < (ulint) table->n_cols; i++) {
		dict_col_t*	col = dict_table_get_nth_col(table, i);
		ut_ad(col->mtype != DATA_SYS);

		if (!indexed[col->ind]) {
			dict_index_add_col(new_index, table, col, 0);
		}
	}
    // ... ...
}
```

### build internal non-clustered index
Builds the internal dictionary cache representation for a non-clustered index, containing also system fields not defined by the user.

1. 创建一个新的 `dict_index_t` 对象new_index（ `dict_mem_index_create()` ）
   1. _初始值 new_index->n_fields = index->n_fields + 1 + clust_index->n_uniq_
   2. new_index->n_user_defined_cols = index->n_fields;
2. 拷贝_user representation index _中的field到new_index中
3. Add to new_index the columns necessary to determine the clustered index entry uniquely. 把在 clust_index->fields 中且不在 new_index->fields 中的field添加到new_index中（ `dict_index_add_col()` ）
4. 初始化new_index->n_uniq
   1. 唯一索引：_new_index->n_uniq = index->n_fields (唯一索引的n_uniq就是用户定义的列数量)_
   2. 非唯一索引：_new_index->n_uniq = new_index->n_def （用户定义的列数量+cluster_index uniq）_
5. Set the n_fields value in new_index to the actual defined number of fields. (new_index->n_fields = new_index->n_def)

注意：secondray index与clustered index相比，没有system columns

e.g. 1. cluster_index->n_uniq = 2，cluster_index->fields = [a, b, trx_id. roll_ptr, c, d, ...]，用户定义的唯一索引 index = (c, d)，那么初始值new_index->n_fields = 5 (2 + 1 + 2)，第3步中需要把cluster_index->fields中的 _[a, b]_ 2个field加到new_index中。
最终new_index中相关的值如下：

- (c, d) 是唯一索引
   - n_fields = 4 = n_def (这里最后更新了n_fields为fields中实际保存的field数量)
   - field = [c, d, **a, b**, NULL]
   - n_uniq = 2 (field中 [c, d] 2个fields能确定索引的唯一性)
   - n_def = 4
- (c, d) 是普通索引
   - n_fields = 4 = n_def
   - field = [c, d, **a, b**, NULL]
   - n_uniq = 4 (field中 [c, d, a, b] 4个fields能确定索引的唯一性)
   - n_def = 4

e.g. 1. cluster_index->n_uniq = 2，cluster_index->fields = [a, b, trx_id. roll_ptr, c, d, ...]，用户定义的唯一索引 index = (c, a)，那么_初始值_new_index->n_fields = 4 (2 + 1 + 2)，第3步中只需要把cluster_index->fields中的 _[b]_ 1个field加到new_index中。
最终new_index中相关的值如下：

- (c, a) 是唯一索引
   - n_fields = 3 = n_def
   - field = [c, a, **b**, NULL, NULL]
   - n_uniq = 2 (field中 [c, a] 2个fields能确定索引的唯一性)
   - n_def = 3
- (c, a) 是普通索引
   - n_fields = 3 = n_def
   - field = [c, a, **b**, NULL, NULL]
   - n_uniq = 3 (field中 [c, a, b] 2个fields能确定索引的唯一性)
   - n_def = 3
```cpp
/*******************************************************************//**
Builds the internal dictionary cache representation for a non-clustered
index, containing also system fields not defined by the user.
@return own: the internal representation of the non-clustered index */
static
dict_index_t*
dict_index_build_internal_non_clust(
/*================================*/
	const dict_table_t*	table,	/*!< in: table */
	dict_index_t*		index)	/*!< in: user representation of
					a non-clustered index */
{
	dict_field_t*	field;
	dict_index_t*	new_index;
	dict_index_t*	clust_index;
	ulint		i;
	ibool*		indexed;
    
    /* The clustered index should be the first in the list of indexes */
	clust_index = UT_LIST_GET_FIRST(table->indexes);

	/* Create a new index */
	new_index = dict_mem_index_create(
		table->name.m_name, index->name, index->space, index->type,
		index->n_fields + 1 + clust_index->n_uniq); // key + node_pointer + pk

	/* Copy other relevant data from the old index
	struct to the new struct: it inherits the values */

	new_index->n_user_defined_cols = index->n_fields;

	new_index->id = index->id;

	/* Copy fields from index to new_index */
	dict_index_copy(new_index, index, table, 0, index->n_fields);
    
    /* Remember the table columns already contained in new_index */
	indexed = static_cast<ibool*>(ut_zalloc_nokey(table->n_cols * sizeof *indexed));

	/* Mark the table columns already contained in new_index */
	for (i = 0; i < new_index->n_def; i++) {
		field = dict_index_get_nth_field(new_index, i);
		if (dict_col_is_virtual(field->col)) {
			continue;
		}

		/* If there is only a prefix of the column in the index
		field, do not mark the column as contained in the index */
		if (field->prefix_len == 0) {
			indexed[field->col->ind] = TRUE;
		}
	}

	/* Add to new_index the columns necessary to determine the clustered
	index entry uniquely */
	for (i = 0; i < clust_index->n_uniq; i++) {
		field = dict_index_get_nth_field(clust_index, i);

		if (!indexed[field->col->ind]) {
			dict_index_add_col(new_index, table, field->col, field->prefix_len);
		} else if (dict_index_is_spatial(index)) {
			/*For spatial index, we still need to add the field to index. */
			dict_index_add_col(new_index, table, field->col, field->prefix_len);
		}
	}

	ut_free(indexed);
    
	if (dict_index_is_unique(index)) {
		new_index->n_uniq = index->n_fields;
	} else {
		new_index->n_uniq = new_index->n_def;
	}

	/* Set the n_fields value in new_index to the actual defined
	number of fields */
	new_index->n_fields = new_index->n_def;
    
	new_index->cached = TRUE;
	return(new_index);
}
```

### node ptr
dict_index_build_node_ptr()

### n_unique_in_tree
`dict_index_get_n_unique_in_tree_nonleaf()` -> `dict_index_get_n_unique_in_tree()` 函数用于获取在b-tree中该索引需要多少个fields才能确定其唯一性（暂不考虑spatial index）。

其语义和 `dict_index_t::n_uniq` 并不相同，可以看到对于secondary index来说，是整行索引数据。

- clustered index : `dict_index_t::n_uniq` 
- secondary index : `dict_index_t::n_fields` 

secondary index中的non-leaf node存储的是 index_key + clust_key，虽然unique index只需要index_key就可以确定其唯一性了，但是在non-leaf node也会存储其clust_key的值。

```cpp
/********************************************************************//**
Gets the number of fields in the internal representation of an index
which uniquely determine the position of an index entry in the index, if
we also take multiversioning into account.
@return number of fields */
UNIV_INLINE
ulint
dict_index_get_n_unique_in_tree(
/*============================*/
	const dict_index_t*	index)	/*!< in: an internal representation
					of index (in the dictionary cache) */
{
	ut_ad(index);
	ut_ad(index->magic_n == DICT_INDEX_MAGIC_N);
	ut_ad(index->cached);

	if (dict_index_is_clust(index)) {
		// index->n_uniq
		return(dict_index_get_n_unique(index));
	}

    // index->n_fields
	return(dict_index_get_n_fields(index));
}
```

## 外键定义(dict_foreign_t)
### create foreign constraints
dict_create_foreign_constraints()

### foreign/table/index的关联

## 内存对象的组织
![image.png](https://cdn.nlark.com/yuque/0/2020/png/385742/1595143120567-bdaa1496-5159-45d1-b365-77b90aa4b0da.png#align=left&display=inline&height=1662&originHeight=1662&originWidth=1718&size=235590&status=done&style=none&width=1718)
> **TIPS**:
> 1. `SYS_TABLES` 、 `SYS_COLUMNS` 、 `SYS_INDEXS` 、 `SYS_FIELDS` 、 `SYS_VIRTUAL` 单独挂在 `sys_dict_t` 上，且不会被换出cache
> 2. `dict_index_t::fields` 中的col指向 `dict_index_t::table->cols` （system columns除外），前缀索引的 `dict_field_t::col` 也指向 `dict_table_t::cols` 中的某一个col，只是在 `dict_field_t::prefix_len` 中定义了前缀的长度，因此当定义了前缀索引时index中有多个field指向table的同一个col


## 内存对象管理
dict_make_room_in_cache()
dict_table_can_be_evicted()
dict_table_remove_from_cache_low()
dict_index_remove_from_cache_low()

> Function object


# 数据字典系统表
4个基本系统表并不是通过CREATE TABLE创建的，其表结构固定不可修改，在代码中直接定义，参考 `dict_boot()` 函数中 `dict_table_t` 相关对象的创建。

## SYS_TABLES
| **COL_NAME** | **TYPE** | **LEN(byte)** | **DESC** |
| --- | --- | --- | --- |
| NAME | DATA_BINARY | MAX_FULL_NAME_LEN | clustered index |
| ID | DATA_BINARY | 8 | unique index |
| N_COLS | DATA_INT | 4 |  |
| TYPE | DATA_INT | 4 |  |
| MIX_ID | DATA_BINARY | 0 |  |
| MIX_LEN | DATA_INT | 4 |  |
| CLUSTER_NAME | DATA_BINARY | 0 |  |
| SPACE | DATA_INT | 4 |  |


参考函数 `dict_sys_tables_rec_read()` 和 `dict_boot()` 中的定义

- **`TYPE`** ： The low order bit of TYPE is always set to 1.  If the format is `UNIV_FORMAT_B`  or higher, this field matches `table->flags` . But in `dict_table_t::flags`  the low order bit is used to determine if the row format is Redundant (0) or Compact (1) when the format is Antelope
- **`N_COLS`** ：
   1. 最高位表示是否是COMPACT格式， `ROW_FORMAT = (N_COLS >> 31) ? COMPACT : REDUNDANT`
   2. 高16位（COMPACT标志抹掉后）表示 `n_vcols` ，低16位表示 `n_cols` (非虚拟列数量，**不包括系统列**)
> TIPS:
> 1. `dict_table_t::``flag` 字段由 `N_COLS` 最高位的COMPACT标志和 `TYPE` 的1-8位生成，ref: `dict_sys_tables_type_to_tf()`
> 2. 从rec中读出来的原始n_cols字段在生成flag后会把COMPACT标志位置0: `*n_cols &= ~DICT_N_COLS_COMPACT;` 
> 3. **`SYS_TABLES.N_COLS`**** 中存储的 ****`n_cols`**** 不包含系统列，  ****`dict_table_t::n_cols`**** 包含系统列**

- **`MIX_LEN`** ：对应 `dict_table_t::``flags2` 。
> **TIPS**:
> 1. MIX_LEN长度为4字节，flag2只占9位，因此高23位都是空闲状态：
> 
/** Total number of bits in table->flags2. */
> #define DICT_TF2_BITS  	9
> #define DICT_TF2_UNUSED_BIT_MASK	(~0U << DICT_TF2_BITS)
> 高16位在 feature instant add column 中用来存储n_instant_cols值
> 2. We don't trust the table->flags2(retrieved from SYS_TABLES.MIX_LEN field) if the datafiles are from 3.23.52 version. To identify this version, we do the below check and reset the flags.
> 3. 如果编译了debug， `test/t1` 作为一个特殊的表，会把 `flags` 和 `flags2` 都设置为 `255`


## SYS_COLUMNS
| **COL_NAME** | **TYPE** | **LEN(byte)** | **DESC** |
| --- | --- | --- | --- |
| TABLE_ID | DATA_BINARY | 8 | clustered index |
| POS | DATA_INT | 4 |  |
| NAME | DATA_BINARY | 0 |  |
| MTYPE | DATA_INT | 4 |  |
| PRTYPE | DATA_INT | 4 |  |
| LEN | DATA_INT | 4 |  |
| PREC | DATA_INT | 4 |  |


参考 `dict_load_column_low()`

- **`POS`** ：
   - 普通列：表示nth (starting from 0)，对应 `dict_col_t::ind` ；由于在 `dict_table_t::cols` 中，system columns是添加在最后的，因此这里也不需要考虑系统列
   - 虚拟列（ `prtype & DATA_VIRTUAL` ），存储了两个信息：
      1. `pos & 0xFFFF` : the column position in the original table（意义和普通列的pos相同）， ref: `dict_get_v_col_mysql_pos()`
      2. `(pos >> 16) - 1` : the "nth" virtual column (starting from 1)，ref: `dict_get_v_col_pos()`
- **`MTYPE`** and **`PRTYPE`** ：ref `data0type`

## SYS_INDEXES
| **COL_NAME** | **TYPE** | **LEN(byte)** | **DESC** |
| --- | --- | --- | --- |
| TABLE_ID | DATA_BINARY | 8 | clustered index |
| ID | DATA_BINARY | 8 |  |
| NAME | DATA_BINARY | 0 |  |
| N_FIELDS | DATA_INT | 4 |  |
| TYPE | DATA_INT | 4 |  |
| SPACE | DATA_INT | 4 |  |
| PAGE_NO | DATA_INT | 4 |  |
| MERGE_THRESHOLD | DATA_INT | 4 |  |


- `MERGE_THRESHOLD` : 对于older SYS_INDEXES table，没有该字段，读取rec的时候根据 `rec_get_n_fields_old_raw(rec) ` 判断，默认值为 `50` ( `DICT_INDEX_MERGE_THRESHOLD_DEFAULT` )
- **`TYPE`** : 这里的type在表中存储的值是4字节，但只用到了低 `8` ( `DICT_IT_BITS` )位。
- **`NAME`** : 以 `TEMP_INDEX_PREFIX` （\377）开头的index name表示将要被drop的index，load时会忽略（ `dict_load_indexes()` ），该特性主要用于online DDL：
   - **online DDL create sec index prepare**: 对于 `!index->is_committed()` （在 `row_merge_create_index()` 中设置）的index，在name前添加 `TEMP_INDEX_PREFIX` 前缀（ `dict_create_index_step()` -> `dict_build_index_def_step()` -> `dict_create_sys_indexes_tuple()` ）
   - **online DDL create sec index commit**: 在commit阶段rename index name，去除`TEMP_INDEX_PREFIX` 前缀（ `ha_innobase::commit_inplace_alter_table()` -> `commit_try_norebuild()` -> `row_merge_rename_index_to_add()` ）
   - **online DDL drop sec index commit**: 在commit阶段rename index name，添加 `TEMP_INDEX_PREFIX` 前缀（ `ha_innobase::commit_inplace_alter_table()` -> `commit_try_norebuild()` -> `row_merge_rename_index_to_drop()` ）

## SYS_FIELDS
| **COL_NAME** | **TYPE** | **LEN(byte)** | **DESC** |
| --- | --- | --- | --- |
| INDEX_ID | DATA_BINARY | 8 | clustered index |
| POS | DATA_INT | 4 |  |
| COL_NAME | DATA_BINARY | 0 |  |


参考 `dict_load_field_low()`

- **POS**：
   - if there is at least one prefix field in the index, then the HIGH 2 bytes contain the field number (index->n_def) and the low 2 bytes the prefix length for the field. 
   - Otherwise the field number (index->n_def) is contained in the 2 LOW bytes.
```cpp
	if (first_field || pos_and_prefix_len > 0xFFFFUL) {
		prefix_len = pos_and_prefix_len & 0xFFFFUL;
		position = (pos_and_prefix_len & 0xFFFF0000UL)  >> 16;
	} else {
		prefix_len = 0;
		position = pos_and_prefix_len & 0xFFFFUL;
	}
```

## 其他系统表(dict0crea)
`dict_create_or_check_foreign_constraint_tables()`
`dict_create_or_check_sys_tablespace()`
`dict_create_or_check_sys_virtual()`

```
mysql> select * from INNODB_SYS_TABLES;
+----------+---------------------------------+------+--------+-------+-------------+------------+---------------+------------+
| TABLE_ID | NAME                            | FLAG | N_COLS | SPACE | FILE_FORMAT | ROW_FORMAT | ZIP_PAGE_SIZE | SPACE_TYPE |
+----------+---------------------------------+------+--------+-------+-------------+------------+---------------+------------+
|       14 | SYS_DATAFILES                   |    0 |      5 |     0 | Antelope    | Redundant  |             0 | System     |
|       11 | SYS_FOREIGN                     |    0 |      7 |     0 | Antelope    | Redundant  |             0 | System     |
|       12 | SYS_FOREIGN_COLS                |    0 |      7 |     0 | Antelope    | Redundant  |             0 | System     |
|       13 | SYS_TABLESPACES                 |    0 |      6 |     0 | Antelope    | Redundant  |             0 | System     |
|       15 | SYS_VIRTUAL                     |    0 |      6 |     0 | Antelope    | Redundant  |             0 | System     |
// 此处省略一万行... ...
|       36 | test/t1                         |   33 |      5 |    25 | Barracuda   | Dynamic    |             0 | Single     |
|       37 | test/t2                         |    0 |      5 |    26 | Antelope    | Redundant  |             0 | Single     |
+----------+---------------------------------+------+--------+-------+-------------+------------+---------------+------------+
27 rows in set (0.00 sec)

mysql> select * from INNODB_SYS_COLUMNS where table_id = 11;
+----------+----------+-----+-------+---------+-----+
| TABLE_ID | NAME     | POS | MTYPE | PRTYPE  | LEN |
+----------+----------+-----+-------+---------+-----+
|       11 | ID       |   0 |     1 | 5439492 |   0 |
|       11 | FOR_NAME |   1 |     1 | 5439492 |   0 |
|       11 | REF_NAME |   2 |     1 | 5439492 |   0 |
|       11 | N_COLS   |   3 |     6 |       0 |   4 |
+----------+----------+-----+-------+---------+-----+
4 rows in set (0.00 sec)
```

# 数据字典创建(dict0boot)
### 物理结构创建(dict_hdr_create())
在mysql第一次初始化时，需要在系统表空间中创建4个基本系统表，其主要实现在 `dict_hdr_create()` :

1. 在系统表空间（ `system tablespace` ）分配一页用于存放dictionary hdr信息（ `fseg_create(DICT_HDR_SPACE, 0, DICT_HDR + DICT_HDR_FSEG_HEADER, mtr)` ）
2. 写入hdr相关字段的初始值
3. Create the B-tree roots for the clustered indexes of the basic system tables( `btr_create()` )，并把 `root_page_no` 记录到hdr中

dictionery header在系统表空间的第 `7` （ `DICT_HDR_PAGE_NO` ）页上，所有字段如下：
```c
/*-------------------------------------------------------------*/
/* Dictionary header offsets */
#define DICT_HDR_ROW_ID		0	/* The latest assigned row id */
#define DICT_HDR_TABLE_ID	8	/* The latest assigned table id */
#define DICT_HDR_INDEX_ID	16	/* The latest assigned index id */
#define DICT_HDR_MAX_SPACE_ID	24	/* The latest assigned space id,or 0*/
#define DICT_HDR_MIX_ID_LOW	28	/* Obsolete,always DICT_HDR_FIRST_ID*/
#define DICT_HDR_TABLES		32	/* Root of SYS_TABLES clust index SYS_TABLES聚簇索引root节点所在的page*/
#define DICT_HDR_TABLE_IDS	36	/* Root of SYS_TABLE_IDS sec index */
#define DICT_HDR_COLUMNS	40	/* Root of SYS_COLUMNS clust index */
#define DICT_HDR_INDEXES	44	/* Root of SYS_INDEXES clust index */
#define DICT_HDR_FIELDS		48	/* Root of SYS_FIELDS clust index */
```
**4个基本系统表的ID**
```c
/* The ids for the basic system tables and their indexes */
#define DICT_TABLES_ID		1
#define DICT_COLUMNS_ID		2
#define DICT_INDEXES_ID		3
#define DICT_FIELDS_ID		4
/* The following is a secondary index on SYS_TABLES */
#define DICT_TABLE_IDS_ID	5
```
> **TIPS**:
> 基本系统表（base system tables）不需要使用CREATE TABLE创建，因为不需要在其他地方记录表的元数据信息，直接创建所需的page就行


![image.png](https://cdn.nlark.com/yuque/0/2020/png/385742/1593452171144-1cfcc41c-f8e7-4bc8-a798-c56f4528f0b1.png#align=left&display=inline&height=1224&originHeight=1224&originWidth=1502&size=191832&status=done&style=none&width=1502)
创建完成后的表空间如图所示，系统表空间的第7页上是dictionary hdr page，38~56字节是写入的hdr信息，紧跟着是10字节的inode位置信息，记录了inode（segment的元信息）所在的位置(space_id, page_no, offset)，使用该信息就可以找到该segment的所有区和页等信息。

**写入hdr的关键代码片段**
```c
/*****************************************************************//**
Creates the file page for the dictionary header. This function is
called only at the database creation.
@return TRUE if succeed */
static
ibool
dict_hdr_create(
/*============*/
	mtr_t*	mtr)	/*!< in: mtr */
{
	buf_block_t*	block;
	dict_hdr_t*	dict_header;
	ulint		root_page_no;

	ut_ad(mtr);

	/* Create the dictionary header file block in a new, allocated file
	segment in the system tablespace */
	block = fseg_create(DICT_HDR_SPACE, 0, DICT_HDR + DICT_HDR_FSEG_HEADER, mtr);
	ut_a(DICT_HDR_PAGE_NO == block->page.id.page_no());
	dict_header = dict_hdr_get(mtr);

	/* Start counting row, table, index, and tree ids from
	DICT_HDR_FIRST_ID */
	mlog_write_ull(dict_header + DICT_HDR_ROW_ID, DICT_HDR_FIRST_ID, mtr);
	mlog_write_ull(dict_header + DICT_HDR_TABLE_ID, DICT_HDR_FIRST_ID, mtr);
    // ... ...
    
    /* Create the B-tree roots for the clustered indexes of the basic
	system tables */

	/*--------------------------*/
	root_page_no = btr_create(DICT_CLUSTERED | DICT_UNIQUE, DICT_HDR_SPACE,
				  univ_page_size, DICT_TABLES_ID,
				  dict_ind_redundant, NULL, mtr);
	if (root_page_no == FIL_NULL) {
		return(FALSE);
	}
	mlog_write_ulint(dict_header + DICT_HDR_TABLES, root_page_no, MLOG_4BYTES, mtr);
    
    // ... ...
}
```

### 数据字典初始化(dict_boot())
在mysql启动时会调用该函数，用于初始化数据字典以及系统表的元信息

1. 初始化 `sys_dict_t` ( `dict0dict::dict_init()` )
2. 处理hdr中保存的 `row_id` 值：`dict_hdr_get()` 得到hdr的rec指针，然后从hdr中读出持久化的 `row_id` 值
3. 生成系统表 `SYS_TABLES` 、`SYS_COLUMNS` 、`SYS_INDEXES` 、`SYS_FIELDS` 的元数据，添加到 `sys_table_t` 中，并生成其他index信息（ `dict_load_sys_table()` ）

> **hdr中保存的 **`**row_id**` **值:**
> Because we only write new row ids to disk-based data structure (dictionary header) when it is divisible by DICT_HDR_ROW_ID_WRITE_MARGIN, in recovery we will not recover the latest value of the row id counter. Therefore we advance the counter at the database startup to avoid overlapping values. Note that when a user after database startup first time asks for a new row id, then because the counter is now divisible by ..._MARGIN, it will immediately be updated to the disk-based header.
> 

> 参考`dict_sys_get_new_row_id()` 函数分配 `row_id` 的流程：每次递增变量 `dict_sys->row_id` ， `id % DICT_HDR_ROW_ID_WRITE_MARGIN` 时持久化一次该值。


#### 系统表元信息创建
系统表也是在共享表空间中的表，读取这些表时也需要元数据信息，这些信息并不保存在磁盘上的任何地方，而是在mysql启动时生成，主要逻辑在 `dict_boot()` 中。

1. 调用 `dict_mem_table_create()` 和 `dict_mem_table_add_col()` 生成 `dict_table_t` 信息并添加到 `sys_dict_t` 中（ `dict_table_add_to_cache()` ）；
2. 调用 `dict_mem_index_create()` 和 `dict_mem_index_add_field()` 生成 `dict_index_t` 信息并添加到 `sys_dict_t` 中（ `dict_index_add_to_cache()` ）

关于系统表的列类型和名称等信息，都可以在这里找到（以 `SYS_TABLES` 为例）。
```c
/*****************************************************************//**
Initializes the data dictionary memory structures when the database is
started. This function is also called when the data dictionary is created.
@return DB_SUCCESS or error code. */
dberr_t
dict_boot(void)
/*===========*/
{
    // ... ...
    
	/* Insert into the dictionary cache the descriptions of the basic
	system tables */
	/*-------------------------*/
	table = dict_mem_table_create("SYS_TABLES", DICT_HDR_SPACE, 8, 0, 0, 0);

	dict_mem_table_add_col(table, heap, "NAME", DATA_BINARY, 0, MAX_FULL_NAME_LEN);
	dict_mem_table_add_col(table, heap, "ID", DATA_BINARY, 0, 8);
	/* ROW_FORMAT = (N_COLS >> 31) ? COMPACT : REDUNDANT */
	dict_mem_table_add_col(table, heap, "N_COLS", DATA_INT, 0, 4);
	/* The low order bit of TYPE is always set to 1.  If the format
	is UNIV_FORMAT_B or higher, this field matches table->flags. */
	dict_mem_table_add_col(table, heap, "TYPE", DATA_INT, 0, 4);
	dict_mem_table_add_col(table, heap, "MIX_ID", DATA_BINARY, 0, 0);
	/* MIX_LEN may contain additional table flags when
	ROW_FORMAT!=REDUNDANT.  Currently, these flags include
	DICT_TF2_TEMPORARY. */
	dict_mem_table_add_col(table, heap, "MIX_LEN", DATA_INT, 0, 4);
	dict_mem_table_add_col(table, heap, "CLUSTER_NAME", DATA_BINARY, 0, 0);
	dict_mem_table_add_col(table, heap, "SPACE", DATA_INT, 0, 4);

	table->id = DICT_TABLES_ID;

	dict_table_add_to_cache(table, FALSE, heap);
	dict_sys->sys_tables = table;
	mem_heap_empty(heap);

    // 以NAME列建cluster index
	index = dict_mem_index_create("SYS_TABLES", "CLUST_IND",
				      DICT_HDR_SPACE,
				      DICT_UNIQUE | DICT_CLUSTERED, 1);

	dict_mem_index_add_field(index, "NAME", 0);

	index->id = DICT_TABLES_ID;

	error = dict_index_add_to_cache(table, index,
					mtr_read_ulint(dict_hdr + DICT_HDR_TABLES, MLOG_4BYTES, &mtr),
					FALSE);
	ut_a(error == DB_SUCCESS);
    
    // ... ...
}
```

#### 系统表的列顺序
相关系统表的列顺序在 `dict0boot.h` 中定义，分别定义了逻辑上的列顺序（读到 `dtuple_t::dfield_t` 中时使用）和物理结构（clustered index）上存储的顺序（以 `SYS_TABLES` 为例，实际上物理存储上多了事物ID和回滚指针）：
```c
/* The columns in SYS_TABLES */
enum dict_col_sys_tables_enum {
	DICT_COL__SYS_TABLES__NAME		= 0,
	DICT_COL__SYS_TABLES__ID		= 1,
	DICT_COL__SYS_TABLES__N_COLS		= 2,
	DICT_COL__SYS_TABLES__TYPE		= 3,
	DICT_COL__SYS_TABLES__MIX_ID		= 4,
	DICT_COL__SYS_TABLES__MIX_LEN		= 5,
	DICT_COL__SYS_TABLES__CLUSTER_ID	= 6,
	DICT_COL__SYS_TABLES__SPACE		= 7,
	DICT_NUM_COLS__SYS_TABLES		= 8
};
/* The field numbers in the SYS_TABLES clustered index */
enum dict_fld_sys_tables_enum {
	DICT_FLD__SYS_TABLES__NAME		= 0,
	DICT_FLD__SYS_TABLES__DB_TRX_ID		= 1,
	DICT_FLD__SYS_TABLES__DB_ROLL_PTR	= 2,
	DICT_FLD__SYS_TABLES__ID		= 3,
	DICT_FLD__SYS_TABLES__N_COLS		= 4,
	DICT_FLD__SYS_TABLES__TYPE		= 5,
	DICT_FLD__SYS_TABLES__MIX_ID		= 6,
	DICT_FLD__SYS_TABLES__MIX_LEN		= 7,
	DICT_FLD__SYS_TABLES__CLUSTER_ID	= 8,
	DICT_FLD__SYS_TABLES__SPACE		= 9,
	DICT_NUM_FIELDS__SYS_TABLES		= 10
};

// ... ... 此处省略一万行
```
其中，物理结构上的列顺序主要在 `dict0load` 中使用，当打开一个表需要读取其元数据时，根据这里定义的列顺序从表中读取数据初始化 `dict_xxx_t` 相关的结构，不过这些列数据可能经过的特殊的编码，关于其每一列的类型、大小、意义等需要参考 `dict0load` 中对这些列读取的相关函数。

# 数据字典对象加载(dict0load)
### 用户表元数据加载(dict_load_table())
在打开一个表时，需要先通过`dict_load_table()` /** **`dict_load_table_on_id()` 读取一个表的 table define, index, foreign信息到内存中。
**
**主要步骤：**

1. 检查表对应的元数据是否已经在cache中（ `dict_table_check_if_in_cache_low()` ），即是否在 `sys_dict_t` 的 `LRU` 中，如果在就直接返回cache中的值
2. 加载表定义和索引定义到cache中（ `dict_load_table_one()` ）
   1. 打开 `SYS_TABLES` 表，获取表的基本信息
      1. 获取 `SYS_TABLES` 的元数据（ `dict_table_get_low()` ）
      2. 根据表名在cluster index中找到对应的rec记录（ `btr_pcur_open_on_user_rec()` ）
      3. 读取 `SYS_TABLES` 表中的数据并生成 `dict_table_t` 结构(`dict_mem_table_create()` ): `dict_load_table_low()`  -> `dict_sys_tables_rec_read()` 
   2. 打开 `SYS_TABLESPACES` 表，根据上一步得到的 `dict_table_t::space` 找到表空间文件名，打开表空间文件: `dict_load_tablespace()` -> `dict_space_get_name()` -> `fil_ibd_open()` 
   3. 根据 `dict_table_t::id` 在 `SYS_COLUMNS` 表中找到对应表的列的元数据，步骤与上面读取 `SYS_TABLES` 的步骤类似: `dict_load_columns()` -> `dict_load_column_low()` 
   4. `dict_load_virtual()`  `SYS_VIRTUAL` 
   5. 根据 `dict_table::id` 在 `SYS_INDEXES` 表中找到该表的所有索引信息记录，对于已经删除的索引（标记为delete的记录 `rec_get_deleted_flag(rec, 0)` ）直接跳过: `dict_load_indexes()` -> `dict_load_index_low()` 
      1. 根据 `dict_index_t::id` 在 `SYS_FIELDS` 表中找到该索引的field定义: `dict_load_fields()` -> `dict_load_field_low()` 
   6. 根据 `dict_table_t::name` 在 `SYS_FOREIGN` 表中找到对应的记录: `dict_load_foreigns()` -> `dict_load_foreign()` 
      1. `SYS_FOREIGN_COLS` 

> Tips：
> 系统表也是存储在共享表空间的表，读取这些表时也需要元信息，不过这些元信息已经在boot阶段在内存中生成了（参考 `dict_table_get_low()` 函数的实现，该函数第一步就是调用`dict_table_check_if_in_cache_low()` 从 `sys_dict_t` 中取元数据，否则才会调用`dict_load_table()` ）

**
**打开系统表的关键代码**
```c
static
dict_table_t*
dict_load_table_one(
	table_name_t&		name,
	bool			cached,
	dict_err_ignore_t	ignore_err,
	dict_names_t&		fk_tables)
{
    dberr_t		err;
	dict_table_t*	table;
	dict_table_t*	sys_tables;
	btr_pcur_t	pcur;
	dict_index_t*	sys_index;
	dtuple_t*	tuple;
	mem_heap_t*	heap;
	dfield_t*	dfield;
	const rec_t*	rec;
	const byte*	field;
	ulint		len;
	const char*	err_msg;
	mtr_t		mtr;
    
    ut_ad(mutex_own(&dict_sys->mutex));

	heap = mem_heap_create(32000);

	mtr_start(&mtr);
    
    // SYS_TABLES的元数据信息，直接从sys_dict_t的sys_tables中取得
	sys_tables = dict_table_get_low("SYS_TABLES");
	sys_index = UT_LIST_GET_FIRST(sys_tables->indexes);

    // 生成b-tree搜索条件
	tuple = dtuple_create(heap, 1);
	dfield = dtuple_get_nth_field(tuple, 0);

	dfield_set_data(dfield, name.m_name, ut_strlen(name.m_name));
	dict_index_copy_types(tuple, sys_index, 1);

    // b-tree搜索找到符合条件的记录指针rec
	btr_pcur_open_on_user_rec(sys_index, tuple, PAGE_CUR_GE, BTR_SEARCH_LEAF, &pcur, &mtr);
	rec = btr_pcur_get_rec(&pcur);
    
    // ... ...
    // 调用rec_get_nth_field_old()一系列函数读取SYS_TABLES表里的行记录信息
}
```

### 系统表与information_schema的关系
`dict_process_sys_xxx_rec()` ： 主要是 `i_s` 使用
`dict_startscan_system()` / `dict_getnext_system()` ：全表扫描系统表时使用

# 数据字典修改(DDL)
### create table/create index（dict0crea）
入口函数分别为 `dict_create_table_step()` / `dict_create_index_step()` ，下面以建表为例。

#### Query Graph
Query graph相关的实现在 `que0que.cc` 中，其实现了任务执行状态转换图。简单来说就是不断调用对应 `que_node_t` 的step函数，step函数根据任务的status执行不同的分支代码，然后根据情况将任务状态置为下一个要执行的status或执行其他 `que_node_t` ，任务会一直执行并进行状态转换，直到到达特定的状态。

对于table create来说，其 `que_node_t` 定义如下，通过 `tab_create_graph_create()` 函数创建，类型为 `QUE_NODE_CREATE_TABLE` ：
```c
/* Table create node structure */
struct tab_node_t{
	que_common_t	common;		/*!< node type: QUE_NODE_TABLE_CREATE */
	dict_table_t*	table;		/*!< table to create, built as a
					memory data structure with
					dict_mem_... functions */
	ins_node_t*	tab_def;	/*!< child node which does the insert of
					the table definition; the row to be
					inserted is built by the parent node  */
	ins_node_t*	col_def;	/*!< child node which does the inserts
					of the column definitions; the row to
					be inserted is built by the parent
					node  */
	ins_node_t*	v_col_def;	/*!< child node which does the inserts
					of the sys_virtual row definitions;
					the row to be inserted is built by
					the parent node  */
	/*----------------------*/
	/* Local storage for this graph node */
	ulint		state;		/*!< node execution state */
	ulint		col_no;		/*!< next column definition to insert */
	ulint		base_col_no;	/*!< next base column to insert */
	mem_heap_t*	heap;		/*!< memory heap used as auxiliary
					storage */
};
```
可以看到  `tab_node_t` 又引用了三个 `ins_node_t` （ `QUE_NODE_INSERT` ），分别执行insert到系统表中的任务。

```c
/*********************************************************************//**
Creates a table create graph.
@return own: table create node */
tab_node_t*
tab_create_graph_create(
/*====================*/
	dict_table_t*	table,	/*!< in: table to create, built as a memory data structure */
	mem_heap_t*	heap)	/*!< in: heap where created */
{
	tab_node_t*	node;
	node = static_cast<tab_node_t*>(mem_heap_alloc(heap, sizeof(tab_node_t)));

	node->common.type = QUE_NODE_CREATE_TABLE;
	node->table = table;
	node->state = TABLE_BUILD_TABLE_DEF;
	node->heap = mem_heap_create(256);

	node->tab_def = ins_node_create(INS_DIRECT, dict_sys->sys_tables, heap);
	node->tab_def->common.parent = node; // 设置parent为了执行完ins_node的step后可以回到tab_node

	node->col_def = ins_node_create(INS_DIRECT, dict_sys->sys_columns, heap);
	node->col_def->common.parent = node;

	node->v_col_def = ins_node_create(INS_DIRECT, dict_sys->sys_virtual, heap);
	node->v_col_def->common.parent = node;

	return(node);
}
```
**
**create table的query graph调用**
```c
/*********************************************************************//**
Creates a table for MySQL. On failure the transaction will be rolled back
and the 'table' object will be freed.
@return error code or DB_SUCCESS */
dberr_t
row_create_table_for_mysql(
/*=======================*/
	dict_table_t*	table,	/*!< in, own: table definition
				(will be freed, or on DB_SUCCESS
				added to the data dictionary cache) */
	const char*	compression,
				/*!< in: compression algorithm to use,
				can be NULL */
	trx_t*		trx,	/*!< in/out: transaction */
	bool		commit)	/*!< in: if true, commit the transaction */
{
	tab_node_t*	node;
    
    // ... ...
    node = tab_create_graph_create(table, heap);
	thr = pars_complete_graph_for_exec(node, trx, heap, NULL);
	ut_a(thr == que_fork_start_command(static_cast<que_fork_t*>(que_node_get_parent(thr))));

    // 该函数会调用que_run_threads_low()->que_thr_step()
    // que_thr_step()函数中根据不同的node type，执行不同的函数
    // QUE_NODE_CREATE_TABLE: dict_create_table_step()
    // QUE_NODE_CREATE_INDEX: dict_create_index_step()
	que_run_threads(thr);
    
    // ... ...
}
```

#### Step（dict_create_table_step()）
其执行过程如下：

1. TABLE_BUILD_TABLE_DEF: `dict_build_table_def_step()` 
   1. `row_ins_step()` ：执行该insert把数据写入到SYS_TABLES的rec中，完成后会返回其parent node即当前node `tab_node_t`  
2. TABLE_BUILD_COL_DEF: `dict_build_col_def_step()` 
   1. `row_ins_step()`
3. TABLE_BUILD_V_COL_DEF: `dict_build_v_col_def_step()` 
   1. `row_ins_step()`
4. TABLE_ADD_TO_CACHE: `dict_table_add_to_cache()` 
```c
/***********************************************************//**
Creates a table. This is a high-level function used in SQL execution graphs.
@return query thread to run next or NULL */
que_thr_t*
dict_create_table_step(
/*===================*/
	que_thr_t*	thr)	/*!< in: query thread */
{
	tab_node_t*	node;
    
    // ... ...
	if (node->state == TABLE_BUILD_TABLE_DEF) {
		err = dict_build_table_def_step(thr, node);
		node->state = TABLE_BUILD_COL_DEF;
		node->col_no = 0;
        // 设置下一个执行的node
        // 在que_run_threads_low循环中的下一次调用就会执行该node的step函数row_ins_step()
        // 执行完成后需要通过设置thr->run_node = que_node_get_parent(node)返回上层
		thr->run_node = node->tab_def;
		return(thr);
	}

	if (node->state == TABLE_BUILD_COL_DEF) {
        // ... ...
        dict_build_col_def_step(node);
        node->state = TABLE_BUILD_V_COL_DEF;
        thr->run_node = node->col_def;
        // ... ...
        return(thr);
    }
    
    if (node->state == TABLE_BUILD_V_COL_DEF) {
        // ... ...
        dict_build_v_col_def_step(node);
        node->state = TABLE_ADD_TO_CACHE;
        thr->run_node = node->v_col_def;
        // ... ...
        return(thr);
    }
    
    if (node->state == TABLE_ADD_TO_CACHE) {
		dict_table_add_to_cache(node->table, TRUE, node->heap);
		err = DB_SUCCESS;
	}
    
    // 执行完后返回上层parent
    thr->run_node = que_node_get_parent(node);
    return(thr);
}
```

### tablespace
`mysql_execute_command()` ->
`mysql_alter_tablespace()` ->
`hton->alter_tablespace()` ( `innobase_alter_tablespace()` ) ->
`innobase_create_tablespace()` / `innobase_drop_tablespace()` ->
`dict_build_tablespace()` / `dict_delete_tablespace_and_datafiles()` 

### handler0alter

# 数据字典读取(DML)

