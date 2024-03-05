# 物理记录（rem0rec）
## Redundant行记录格式 (old-style)
Redundant是MySQL 5.0版本之前的InnoDB行记录格式，在代码中被称为 _"old-style"_，由**字段偏移列表**、**头信息**、**列数据 **3部分组成，与该行格式相关的函数大都以 _"_old"_ 结尾。

```cpp
// file: rem/rem0rec.cc

/*			PHYSICAL RECORD (OLD STYLE)
			===========================

The physical record, which is the data type of all the records
found in index pages of the database, has the following format
(lower addresses and more significant bits inside a byte are below
represented on a higher text line):

| offset of the end of the last field of data, the most significant
  bit is set to 1 if and only if the field is SQL-null,
  if the offset is 2-byte, then the second most significant
  bit is set to 1 if the field is stored on another page:
  mostly this will occur in the case of big BLOB fields |
...
| offset of the end of the first field of data + the SQL-null bit |
| 4 bits used to delete mark a record, and mark a predefined
  minimum record in alphabetical order |
| 4 bits giving the number of records owned by this record
  (this term is explained in page0page.h) |
| 13 bits giving the order number of this record in the
  heap of the index page |
| 10 bits giving the number of fields in this record |
| 1 bit which is set to 1 if the offsets above are given in
  one byte format, 0 if in two byte format |
| two bytes giving an absolute pointer to the next record in the page |
ORIGIN of the record
| first field of data |
...
| last field of data |

The origin of the record is the start address of the first field
of data. The offsets are given relative to the origin.
The offsets of the data fields are stored in an inverted
order because then the offset of the first fields are near the
origin, giving maybe a better processor cache hit rate in searches.

The offsets of the data fields are given as one-byte
(if there are less than 127 bytes of data in the record)
or two-byte unsigned integers. The most significant bit
is not part of the offset, instead it indicates the SQL-null
if the bit is set to 1. */
```
![image.png](https://cdn.nlark.com/yuque/0/2020/png/385742/1594998990327-59f2c1e1-35f0-40a3-92eb-62e53a7d1d1b.png#align=left&display=inline&height=1144&originHeight=1144&originWidth=1836&size=131049&status=done&style=none&width=1836)
> **TIPS**:
> 1. 解析行记录时拿到的rec指针（类型byte*）指向数据的起始位置
> 2. field offset list逆序存放，逆序第N（start from 0）个offset起始位置计算方法为 _rec - (6 + (N+1)*X)_，其中6是hdr长度，X是1或2


### 头信息（hdr）
#### 定义
头信息共 `6`  ( `REC_N_OLD_EXTRA_BYTES` ) 字节，定义如下：
```
//file: rem0rec.ic
//
/* Offsets of the bit-fields in an old-style record. NOTE! In the table the
most significant bytes and bits are written below less significant.

	(1) byte offset		(2) bit usage within byte
	downward from (逆序)
	origin ->	1	8 bits pointer to next record
						2	8 bits pointer to next record
						3	1 bit short flag
							7 bits number of fields
						4	3 bits number of fields
							5 bits heap number
						5	8 bits heap number
						6	4 bits n_owned
							4 bits info bits
*/
```
| **NAME** |  | **LEN(bit)** | **DESC** |
| --- | --- | --- | --- |
| info_bits |  | 1 | not use |
|  |  | 1 | not use |
|  | deleted_flag | 1 | when bit is set to 1, it means the record has been delete marked.
`#define REC_INFO_DELETED_FLAG	0x20UL`  |
|  | min_rec_flag | 1 | this bit is set if and only if the record is the first user record on a non-leaf B-tree page that is the leftmost page on its level (PAGE_LEVEL is nonzero and FIL_PAGE_PREV is FIL_NULL).
`#define REC_INFO_MIN_REC_FLAG	0x10UL`  |
| n_owned |  | 4 | 页内排序使用，稀疏索引中该行所包含的记录数 |
| heap_no |  | 13 |  |
| n_fields |  | 10 | rec中field数量（包括系统列），10位最多可以表示1023个field

对于_Clustered Index_的_Leaf Node_来说，rec的fields依次是：
_[Cluster Key(ROW_ID), Transaction ID, Rollback Pointer, Other Cols]_
关于其他情况下rec中fields的详细信息，参考[Record Format](#UaHeM)一节 |
| short_flag |  | 1 | 标识field end offset list每个元素是1字节还是2字节 |
| next_record |  | 16 | 下一条记录的页内偏移（绝对地址） |
| Total |  | 48 |  |

#### GET/SET
物理记录以 page 为单位加载到 buffer pool 中，所有的读写流程都是对已经在 buffer pool 中的数据做处理，其中 `rec` 是一个 `byte*` 指针，指向数据列起始位置。

**相关函数：**

- next_record: `rec_get_next_ptr_const()` / `rec_get_next_ptr()` / `rec_get_next_offs()` , `rec_set_next_offs_old()` 
- short_flag: `rec_get_1byte_offs_flag()` , `rec_set_1byte_offs_flag()` 
- n_fields: `rec_get_n_fields_old()` 
- heap_no: `rec_get_heap_no_old()` , `rec_set_heap_no_old()` 
- n_owned: `rec_get_n_owned_old()` , `rec_set_n_owned_old()` 
- info_bits: `rec_get_info_bits()` , `rec_get_deleted_flag()` , `rec_set_info_bits_old()` 

头信息中的数据以**MSB** (most significant bytes and bits are written below less significant，即数据的最高有效位存放在最低位) 的方式存储。
![image.png](https://cdn.nlark.com/yuque/0/2020/png/385742/1592751385521-e4a8f703-5466-43cd-a838-21559093fbcc.png#align=left&display=inline&height=346&originHeight=346&originWidth=2002&size=43528&status=done&style=none&width=2002)

以读取 n_fields 的函数（ `rec_get_n_fields_old()` ）为例:
```cpp
// file: rem0rec.ic
//
#define REC_OLD_N_FIELDS	4	// 该字段起始位置在(rec - 4)字节内
#define REC_OLD_N_FIELDS_MASK	0x7FEUL // 二进制：0000 0111 1111 1110
#define REC_OLD_N_FIELDS_SHIFT	1 // 表示字节对齐后需要右移1位才是该字段的最低位（最右1位为1 bit short flag）

/******************************************************//**
The following function is used to get the number of fields
in an old-style record.
@return number of data fields */
UNIV_INLINE
ulint
rec_get_n_fields_old(
/*=================*/
	const rec_t*	rec)	/*!< in: physical record */
{
	ulint	ret;
	ret = rec_get_bit_field_2(rec, REC_OLD_N_FIELDS,
				  REC_OLD_N_FIELDS_MASK,
				  REC_OLD_N_FIELDS_SHIFT);
	return(ret);
}

/******************************************************//**
Gets a bit field from within 2 bytes. */
UNIV_INLINE
ulint
rec_get_bit_field_2(
/*================*/
	const rec_t*	rec,	/*!< in: pointer to record origin */
	ulint		offs,	/*!< in: offset from the origin down */
	ulint		mask,	/*!< in: mask used to filter bits */
	ulint		shift)	/*!< in: shift right applied after masking */
{
	return((mach_read_from_2(rec - offs) & mask) >> shift);
}

/********************************************************//**
The following function is used to fetch data from 2 consecutive
bytes. The most significant byte is at the lowest address.
@return ulint integer */
UNIV_INLINE
ulint
mach_read_from_2(
/*=============*/
	const byte*	b)	/*!< in: pointer to 2 bytes */
{
	return(((ulint)(b[0]) << 8) | (ulint)(b[1]));
}
```

#### Next Record Pointer
Redundant头信息中的 next record pointer表示的是下一条记录相对页起始地址的偏移（页内绝对地址，指向列数据起始位置）。
buffer中的 page 在内存中是按 `UNIV_PAGE_SIZE` 对齐的，通过当前记录的内存地址（rec）取整就可以得到该 page 起始的内存地址，然后再加上 next record 就可以得到下一条记录的指针了，简化后的代码如下：
```cpp
/******************************************************//**
The following function is used to get the pointer of the next chained record
on the same page.
@return pointer to the next chained record, or NULL if none */
UNIV_INLINE
const rec_t*
rec_get_next_ptr_const(
/*===================*/
	const rec_t*	rec,	/*!< in: physical record */
	ulint		comp)	/*!< in: nonzero=compact page format */
{
	ulint	field_value;
  	field_value = mach_read_from_2(rec - REC_NEXT);
    
  	if (comp) {
        // Compact的next record表示的是相对当前记录的偏移
    	return((byte*) ut_align_down(rec, UNIV_PAGE_SIZE)
		       + ut_align_offset(rec + field_value, UNIV_PAGE_SIZE));
	} else {
        // 根据rec得到page的起始地址，再加上field_value就可以得到下一条记录的指针了
		return((byte*) ut_align_down(rec, UNIV_PAGE_SIZE) + field_value);
	}
}
```
> 16bit的 next record 最大能表示2^16=64K的偏移，是否代表页大小最大是个64KB


---

**两个align函数**

- `ut_align_offset()` : **取余** (align_no为2^N时)，page读到内存中后地址按照 `UNIV_PAGE_SIZE` 对齐，对一个页内的指针(rec)，取余后就得到了页内偏移
- `ut_align_down()` : **取整** (align_no为2^N时)，同上，取整即的到page首地址
```cpp
/*********************************************************//**
The following function rounds down a pointer to the nearest
aligned address.
@return aligned pointer */
UNIV_INLINE
void*
ut_align_down(
/*==========*/
	const void*	ptr,		/*!< in: pointer */
	ulint		align_no)	/*!< in: align by this number */
{
	return((void*)((((ulint) ptr)) & ~(align_no - 1)));
}

/*********************************************************//**
The following function computes the offset of a pointer from the nearest
aligned address.
@return distance from aligned pointer */
UNIV_INLINE
ulint
ut_align_offset(
/*============*/
	const void*	ptr,		/*!< in: pointer */
	ulint		align_no)	/*!< in: align by this number */
{
	return(((ulint) ptr) & (align_no - 1));
}
```

### 字段偏移列表（field end offset list）
字段偏移列表存储的是字段长度的累加值（[_len(0), len(0)+len(1), ..., len(0)+len(1)+...+len(N-1)]），即_每列数据的结束位置相对于rec指针的偏移），逆序存放，每个offset占用 1 个字节（所有字段长度总和小于等于127，short flag值为1）或 2 个字节。

> **TIPS：**
> 这里判断使用1字节还是2字节表示每个offset的依据是所有字段长度总和小于等于127
> 参考函数： `rec_get_converted_extra_size()` 


> **逆序存放的原因，代码中这样描述**：
> The offsets of the data fields are stored in an inverted order because then the offset of the first fields are near the origin, giving maybe a better processor cache hit rate in searches.


**Example**：
假设4列的数据长度分别为 _[6, 6, 7, 10]_，由于所有字段总和29（6+6+7+10）小于127，因此每个offset使用 1 字节表示，col offset list 的十进制数据逆序为 _[29, 19, 12, 6]_，从中可以的到以下信息：

- 4列数据的长度分别为 [6, 12 - 6 = 6, 19 - 12 = 7, 29 - 19 = 10]
- 4列数据相对于rec的偏移（start offs）分别是 [0, 6, 12, 19]，通过该信息就可以得到4列数据的起始地址分别为 [rec + 0, rec + 6, rec + 12, rec + 19]

详细实现参考[逻辑记录转换成物理记录](#KWOvg)一节，其主要实现在 `rec_convert_dtuple_to_rec_old()` 函数中。

**GET/SET**
以每个offset为 1 字节长度为例，2 字节同理

1. `rec_1_get_prev_field_end_info()` ：取第n列（从0开始计数）的前一列（即第n-1列，n=0除外）数据的结束offset信息，即col offset list中第n-1个元素。

`mach_read_from_1(``rec - (REC_N_OLD_EXTRA_BYTES + n)``)` （注意这里以info结尾的函数读出的是原始的offset值，包括了NULL和External flag）

2. `rec_1_get_field_end_info()` ：取第n列数据的结束offset信息，即col offset list中第n个元素。

 `mach_read_from_1(``rec - (REC_N_OLD_EXTRA_BYTES + n + 1)``)` 

3. `rec_1_get_field_start_offs()` ：取第n列数据的起始offset，即第n-1列数据的结束offset（     即 `rec_1_get_prev_field_end_info(n)` 的值）
4. `rec_get_nth_field_size()` ：取第n列数据的长度，即第n+1列数据的起始位置 - 第n列数据的起始位置（`rec_1_get_field_start_offs(n+1) - rec_1_get_field_start_offs(n)`）
5. `rec_1_set_field_end_info()` ：写入第n列数据的结束offset信息，即col offset list中第n个元素。

`mach_write_to_1(``rec - (REC_N_OLD_EXTRA_BYTES + n + 1``), info)` 

> **TIPS**:
> col offset list中第N个元素指针计算方法为 **_rec - (__REC_N_OLD_EXTRA_BYTES__ + (N+1)*X)_**，X表示每个offset的长度（1或2）


### NULL值和External字段标识
字段偏移列表中，使用每个offset值的最高位和次高位表示该列是否是 `NULL` 值以及是否有溢出数据，使用下面的宏进行该信息的提取：
```cpp
/** SQL null flag in a 1-byte offset of ROW_FORMAT=REDUNDANT records */
#define REC_1BYTE_SQL_NULL_MASK	0x80UL
/** SQL null flag in a 2-byte offset of ROW_FORMAT=REDUNDANT records */
#define REC_2BYTE_SQL_NULL_MASK	0x8000UL
/** In a 2-byte offset of ROW_FORMAT=REDUNDANT records, the second most
significant bit denotes that the tail of a field is stored off-page. */
#define REC_2BYTE_EXTERN_MASK	0x4000UL
```
> **TIPS**:
> 1. 1BYTE时没有溢出数据MASK，因为如果有溢出数据，那么前768字节是保存在数据列中的，offset一定需要用2字节表示


**Example**：
假设一共有5列（VARCHAR类型），长度分别为 [6, 6, 7, NULL, 10]，那么长度偏移列表字段的数据为 [157, 147, 19, 12, 6]，因为第4列的长度偏移为 0x93 = 1001 0011，最高位是1，表示是 `NULL` 值，最终得到的实际字段长度分别为 [6, 6, 7, 0, 10]

> **TIPS**:
> `NULL` 值在数据列是否占用空间需要根据情况区分，比如 `VARCHAR(16)` 不占空间， `CHAR(16)` 需要占用16字节的空间（对于latin1字符集），上面的例子中 `VARCHAR` 的 `NULL` 值不占空间，计算出来该列的长度为 0


### field读取 (get_nth_field_old())
根据上一节我们知道，从字段偏移列表中可以得到每个field的起始和结束偏移，根据rec指针就可以得到数据列实际的起始和结束位置，还可以计算出每列的长度。

**读取第n列数据的流程：**

1. 取第n列数据的起始offset和结束offset(`rec_get_nth_field_offs_old()` )，并计算数据长度
2. 把rec指针指向列数据的起始位置( `rec_get_nth_field_old()` )

> **TIPS:**
> 使用返回的长度len为 `UNIV_SQL_NULL` 表示 `NULL` 值

```cpp
// =====================
//
#define rec_get_nth_field_old(rec, n, len) \
((rec) + rec_get_nth_field_offs_old(rec, n, len))

/************************************************************//**
The following function is used to get the offset to the nth
data field in an old-style record.
@return offset to the field */
ulint
rec_get_nth_field_offs_old(
/*=======================*/
	const rec_t*	rec,	/*!< in: record */
	ulint		n,	/*!< in: index of the field */
	ulint*		len)	/*!< out: length of the field;
				UNIV_SQL_NULL if SQL null */
{
	ulint	os;
	ulint	next_os;

	if (rec_get_1byte_offs_flag(rec)) {
        // 第n列数据的起始offset，即第n-1列数据的结束offset，col offset list 中第n-1个元素
        // n==0时直接返回0
		os = rec_1_get_field_start_offs(rec, n);
        // 第n列的结束offset信息，即col offset list中第n个元素
		next_os = rec_1_get_field_end_info(rec, n);

        // 对于NULL值直接返回长度为UNIV_SQL_NULL
		if (next_os & REC_1BYTE_SQL_NULL_MASK) {
			*len = UNIV_SQL_NULL;
			return(os);
		}

        // 去除NULL FLAG，实际上走到这里的话，next_os中不会有NULL FLAG存在
		next_os = next_os & ~REC_1BYTE_SQL_NULL_MASK;
	} else {
		os = rec_2_get_field_start_offs(rec, n);
		next_os = rec_2_get_field_end_info(rec, n);

		if (next_os & REC_2BYTE_SQL_NULL_MASK) {
			*len = UNIV_SQL_NULL;
			return(os);
		}

		next_os = next_os & ~(REC_2BYTE_SQL_NULL_MASK | REC_2BYTE_EXTERN_MASK);
	}

	*len = next_os - os;
	return(os);
}
```
列数据的写在后面介绍Compact格式的列数据写时一起介绍。

## Compact行记录格式 (new-style)
Compact是MySQL 5.0引入的，与Redundant格式相比，更省空间，存储效率更高。后来的Dynamic和Comparess格式，与Compact相比差别比较小，主要是对于溢出数据的处理有一些区别，在代码中都被成为 _"new-style"_，与之相关的函数不带后缀或带"__cmp_"后缀。

> 在代码中，comp标识实际上指Compact、Dynamic、Compress三种格式。因此后面如不特别说明，Compact行格式指广义上的Compact行格式，即包含Compact，Dynamic，Compress三种行格式。``其中Redundant与Compact（狭义）称为_Antelope_（ `UNIV_FORMAT_A` ），Dynamic和Compress被称为_Barracuda_（ `UNIV_FORMAT_B` ）


```cpp
/*			PHYSICAL RECORD (NEW STYLE)
			===========================

The physical record, which is the data type of all the records
found in index pages of the database, has the following format
(lower addresses and more significant bits inside a byte are below
represented on a higher text line):

| length of the last non-null variable-length field of data:
  if the maximum length is 255, one byte; otherwise,
  0xxxxxxx (one byte, length=0..127), or 1exxxxxxxxxxxxxx (two bytes,
  length=128..16383, extern storage flag) |
...
| length of first variable-length field of data |
| SQL-null flags (1 bit per nullable field), padded to full bytes |
| 4 bits used to delete mark a record, and mark a predefined
  minimum record in alphabetical order |
| 4 bits giving the number of records owned by this record
  (this term is explained in page0page.h) |
| 13 bits giving the order number of this record in the
  heap of the index page |
| 3 bits record type: 000=conventional, 001=node pointer (inside B-tree),
  010=infimum, 011=supremum, 1xx=reserved |
| two bytes giving a relative pointer to the next record in the page |
ORIGIN of the record
| first field of data |
...
| last field of data |

The origin of the record is the start address of the first field
of data. The offsets are given relative to the origin.
The offsets of the data fields are stored in an inverted
order because then the offset of the first fields are near the
origin, giving maybe a better processor cache hit rate in searches.

The offsets of the data fields are given as one-byte
(if there are less than 127 bytes of data in the record)
or two-byte unsigned integers. The most significant bit
is not part of the offset, instead it indicates the SQL-null
if the bit is set to 1. */
```
![image.png](https://cdn.nlark.com/yuque/0/2020/png/385742/1595001261640-0932dca9-a7be-46f0-805c-6881404a5b9b.png#align=left&display=inline&height=1106&originHeight=1106&originWidth=1726&size=139880&status=done&style=none&width=1726)

> **TIPS**:
> 1. Compact格式与Redundant格式相比多了null flag字段，用于标识nullable field的值是否是NULL，每个nullable field占用1bit，其总长度以1字节为单位向上取整（ `UT_BITS_IN_BYTES(index->n_nullable)` ）
> 2. Leaf Node和Non-Leaf Node的null flag字段长度一样，都是通过index->n_nullable计算的
> 3. non-null var-len field length list只存储了非NULL（注意不是nullable）变长字段的长度，且每个length占用字节数可能不相同（1字节或2字节）
> 4. 变长编码（variable-length character sets）的CHAR(x)也被认为是变长类型，比如说utf8的CHAR(128)是变长类型

### 头信息（hdr）
#### 定义
Compact格式的头信息共 `5` （ `REC_N_NEW_EXTRA_BYTES` ）字节，定义如下：
```
//file: rem0rec.ic
//
/* Offsets of the bit-fields in a new-style record. NOTE! In the table the
most significant bytes and bits are written below less significant.

	(1) byte offset		(2) bit usage within byte
	downward from (逆序)
	origin ->	1	8 bits relative offset of next record
						2	8 bits relative offset of next record // 下一条记录的相对偏移
				  				the relative offset is an unsigned 16-bit
				  				integer:
				  				(offset_of_next_record
				   				- offset_of_this_record) mod 64Ki,
				  				where mod is the modulo as a non-negative
				  				number;
				  				we can calculate the offset of the next
				  				record with the formula:
				  				relative_offset + offset_of_this_record
				  				mod UNIV_PAGE_SIZE
						3	3 bits status:
								000=conventional record
								001=node pointer record (inside B-tree)
								010=infimum record
								011=supremum record
								1xx=reserved
							5 bits heap number
						4	8 bits heap number
						5	4 bits n_owned
							4 bits info bits
*/
```
| **NAME** |  | **LEN(bit)** | **DESC** |
| --- | --- | --- | --- |
| info_bits |  | 1 |  |
|  |  | 1 |  |
|  | delete_flag | 1 |  |
|  | min_rec_flag | 1 |  |
| n_owned |  | 4 |  |
| heap_no |  | 13 |  |
| status |  | 3 | /* Record status values */
#define REC_STATUS_ORDINARY	0    // 叶节点(数据节点)
#define REC_STATUS_NODE_PTR	1    // 非叶节点(索引节点)
#define REC_STATUS_INFIMUM	2
#define REC_STATUS_SUPREMUM	3 |
| next_record |  | 16 | 下一条记录的相对偏移 |
| Total |  | 40 |  |


> **TIPS**:
> 对于Comapct格式，rec中没有存储该行数据的field数，由于rec可能是non-leaf或leaf节点，因此需要根据节点类型（status）和数据字典综合判断该行数据的列数，参考[offsets数组初始化](#055he)一节


#### GET/SET
略（同Redundant）
![image.png](https://cdn.nlark.com/yuque/0/2020/png/385742/1593065978522-bd8541f9-59bf-467d-98a3-c83f3bca8674.png#align=left&display=inline&height=346&originHeight=346&originWidth=1722&size=33923&status=done&style=none&width=1722)

#### Next Record Pointer
Comapct格式的next record pointer表示下一条记录相对于当前记录的偏移，而不是页内绝对偏移，其get/set在函数 `rec_get_next_ptr_const()` 和 `rec_set_next_offs_new()` 中实现。

set函数实现如下：
```cpp
/******************************************************//**
The following function is used to set the next record offset field
of a new-style record. */
UNIV_INLINE
void
rec_set_next_offs_new(
/*==================*/
	rec_t*	rec,	/*!< in/out: new-style physical record */
	ulint	next)	/*!< in: offset of the next record */ // 页内偏移
{
	ulint	field_value;

	ut_ad(rec);
	ut_ad(UNIV_PAGE_SIZE > next);

	if (!next) {
		field_value = 0;
	} else {
		/* The following two statements calculate
		next - offset_of_rec mod 64Ki, where mod is the modulo
		as a non-negative number */

        // 算出相对rec的偏移
		field_value = (ulint)
            ((lint) next - (lint) ut_align_offset(rec, UNIV_PAGE_SIZE));
		field_value &= REC_NEXT_MASK; // 只保留低16位
	}

	mach_write_to_2(rec - REC_NEXT, field_value);
}
```

### NULL值标识（null flag）
null flag记录了所有 nullable field( `!(col->prtype & DATA_NOT_NULL)` )是否是 `NULL` 值，逆序存放，每1个nullable field的信息使用1 bit表示。

该字段占用的字节数使用宏 `UT_BITS_IN_BYTES(n_nullable)` 计算，其中`n_nullable` 表示当前索引数据中nullable列的数量( `dict_index_t::n_nullable` )，因此对于Leaf Node和Non-Leaf Node null flag的长度相同（Instant Add Column特性之后两者不相等了）。

关于该字段的读取可以参考[offsets数组](#055he)一节，写入可以参考[逻辑记录转换成物理](#BS6va)记录一节。

> **TIPS**:
> #define UT_BITS_IN_BYTES(b) (((b) + 7) / 8)


### 变长字段长度列表（non-null var-len field length）
与Redundant不同的是，Compact行数据中只存储了非 NULL 变长字段的长度（Compact的NULL值不占用任何空间，只是在null flag中通过1bit表示是NULL值），并没有包括所有字段的长度，并且这个长度不是累加值，而是每个字段的实际长度。

> **TIPS**:
> 变长编码（e.g. utf8）下的CHAR(x)也认为是变长类型字段


#### 写入
每个变长字段长度占用使用 `1`  字节或 `2`  字节(变长字段最大长度是65535字节)存储该字段的长度，关于如何确定需要使用1字节还是2字节，注释中这样描述：
> If the maximum length of a variable-length field is up to 255 bytes, the actual length is always stored in one byte. 
> If the maximum length is more than 255 bytes, the actual length is stored in one byte for 
0..127.  The length will be encoded in two bytes when it is 128 or more, or when the field is stored externally.

**var-len field length字节数计算：**

- 有External字段：使用 `2` 字节存储（有external字段的field一定是大字段 `DATA_BIG_COL()` ）
- 变长列**数据实际长度小于128** 或 **非大字段**( `!DATA_BIG_LEN_MTYPE()` ，定义长度小于等于255且不是BLOB和GEO类型)：使用 `1`  字节存储
- 其他情况用 `2` 字节存储（其他情况包括实际数据长度大于等于128且是大字段）

**var-len field length使用1字节存储时，表示的数据长度范围：**

- 非大字段：0 - 255 bytes
- 大字段：0 -127 bytes

对于大字段，如果其实际数据长度小于128，仍然用1个字节存储length；如果其实际数据长度大于等于128，需要用2个字节存储length。以128（二进制1000 0000）为阈值的原因是，读取一列的length时，如果该列是大字段，为了区分length是用1个字节还是2个字节表示的，把第1个字节的最高位用于该flag（下面称之为_2字节length flag位_）。

使用2字节存储长度时，2字节分别表示：

- 逆序第1个字节：16位长度字段的高8位（最高两位用于表示_2字节length标识位_和_external标识位_）， `*lens-- = (byte) (len >> 8) | 0x80;` 
- 逆序第2个字节：16位长度字段的低8位， `*lens-- = (byte) len;` 

以上逻辑参考函数 `rec_convert_dtuple_to_rec_comp()` 和`rec_get_converted_size_comp_prefix_low()`，详细流程参考[逻辑记录转换成物理](#BS6va)一节

---

**关于 `DATA_BIG_COL()` **
变长字段的定义长度大于 `255` (即VARCHAR(x)定义的长度，该值取自逻辑记录的 `dtype_t::len` ) 或者是 `BLOB` / `VAR_POINT` / `GEOMETRY` 类型
```cpp
/* For checking if mtype is BLOB or GEOMETRY, since we use BLOB as
the underling datatype of GEOMETRY(not DATA_POINT) data. */
#define DATA_LARGE_MTYPE(mtype) ((mtype) == DATA_BLOB			\
				 || (mtype) == DATA_VAR_POINT		\
				 || (mtype) == DATA_GEOMETRY)

/* For checking if data type is big length data type. */
#define DATA_BIG_LEN_MTYPE(len, mtype) ((len) > 255 || DATA_LARGE_MTYPE(mtype))

/* For checking if the column is a big length column. */
#define DATA_BIG_COL(col) DATA_BIG_LEN_MTYPE((col)->len, (col)->mtype)
```

#### 读取
读取non-null var-len field length数据时，对于非NULL变长字段，如果是 `DATA_BIG_COL()` 可能是1字节或2字节存储的，需要进一步区分，总体读取流程如下：

1. 如果是nullable且根据null flag判断出来是NULL值，不读var-len field length，否则继续
2. 如果是fix_length的类型，不读var-len field length，否则继续
3. **非 `DATA_BIG_COL()` ：只读取 1 字节，表示范围****0 - 255**
4. **`DATA_BIG_COL()` ：先读取第 1 个字节 len**
   1. **len的2字节length flag位是1（len & 0x80）：继续读取下一个字节**
   2. **否则结束读取，1字节表示，能表示范围****0 - 127**

**
关于变长字段长度列表和null flag的详细读取流程，可以参考下面的[offsets数组初始化](#9jk4G)流程一节。

#### External字段标识
溢出数据只有在大字段，并且用2字节表示长度的时候才出现，flag存储在第1个字节（转换成off后在从低到高第2个字节）的次高位，使用 `0x4000` 提取。

### field读取 (rec_get_nth_field())
有了offsets数组之后，其读写逻辑和Redundant的读写逻辑基本一样了：
```cpp
/************************************************************//**
The following function is used to get an offset to the nth
data field in a record.
@return offset from the origin of rec */
UNIV_INLINE
ulint
rec_get_nth_field_offs(
/*===================*/
	const ulint*	offsets,/*!< in: array returned by rec_get_offsets() */
	ulint		n,	/*!< in: index of the field */
	ulint*		len);	/*!< out: length of the field; UNIV_SQL_NULL
				if SQL null */
#define rec_get_nth_field(rec, offsets, n, len) \
((rec) + rec_get_nth_field_offs(offsets, n, len))
```

### 伪记录
INFIMUM
SUPREMUM

### temp record
temp record 格式和compact格式基本一样，只是没有hdr信息。

## offsets数组（通用逻辑偏移）
为了统一Redundant和Compact格式的field元数据信息，InnoDB生成了一个offsets数组用来存储每列的长度偏移，offsets使用一个 `ulint*` 数组表示，其结构如下：
![image.png](https://cdn.nlark.com/yuque/0/2020/png/385742/1595002101244-2daf64fe-9eb7-4cf8-b92d-a61fc0cb441f.png#align=left&display=inline&height=470&originHeight=470&originWidth=1384&size=45760&status=done&style=none&width=1384)
可以发现，实际上该数组存的数据和Redundant格式的字段长度偏移列表的数据一致，并且每个长度的最高位和次高位也是用于表示NULL值和是否有溢出字段（分别用 `REC_OFFS_SQL_NULL` 和 `REC_OFFS_EXTERNAL` 提取）。

其大小( `n_alloc` )为 `size = n + (1 + REC_OFFS_HEADER_SIZE)` ，其中 `n` 是列的数量，对于不同类型（status）的行，其取值如下：

- **leaf-node** : `dict_index_get_n_fields(index)` 
- **non-leaf node** : `dict_index_get_n_unique_in_tree_nonleaf(index) + 1` (参考[n_fields](#YECiP)一节)
- **infimum/supremum** : 1
```cpp
/******************************************************//**
The following function determines the offsets to each field
in the record.	It can reuse a previously returned array.
@return the new offsets */
ulint*
rec_get_offsets_func(
/*=================*/
	const rec_t*		rec,	/*!< in: physical record */
	const dict_index_t*	index,	/*!< in: record descriptor */
	ulint*			offsets,/*!< in/out: array consisting of
					offsets[0] allocated elements,
					or an array from rec_get_offsets(),
					or NULL */
	ulint			n_fields,/*!< in: maximum number of
					initialized fields
                    (ULINT_UNDEFINED if all fields) */
	mem_heap_t**	heap)	/*!< in/out: memory heap */
{
	ulint	n;
	ulint	size;
    
    if (dict_table_is_comp(index->table)) {
		switch (UNIV_EXPECT(rec_get_status(rec), REC_STATUS_ORDINARY)) {
		case REC_STATUS_ORDINARY:
            // ref: dict
			n = dict_index_get_n_fields(index);
			break;
		case REC_STATUS_NODE_PTR:
			/* Node pointer records consist of the
			uniquely identifying fields of the record
			followed by a child page number field. */
			n = dict_index_get_n_unique_in_tree_nonleaf(index) + 1;
			break;
		case REC_STATUS_INFIMUM:
		case REC_STATUS_SUPREMUM:
			/* infimum or supremum record */
			n = 1;
			break;
		default:
			ut_error;
			return(NULL);
		}
	} else {
        // Redundant格式直接取hdr中的信息，不需要从dict中获取
		n = rec_get_n_fields_old(rec);
	}

	if (UNIV_UNLIKELY(n_fields < n)) {
		n = n_fields;
	}

	/* The offsets header consists of the allocation size at
	offsets[0] and the REC_OFFS_HEADER_SIZE bytes. */
	size = n + (1 + REC_OFFS_HEADER_SIZE);
    
    // ... ...
}
```

### Compact (null flag和non-null var-len col length读取)
#### 普通节点（rec_init_offsets_comp_ordinary()）
Compact行格式数据节点（status == ORDINARY）offsets数组初始化逻辑：依次遍 [0, `rec_offs_n_fields(offsets)` ] 个field，取出其var-len length字段。
```cpp
/******************************************************//**
Determine the offset to each field in a leaf-page record
in ROW_FORMAT=COMPACT.  This is a special case of
rec_init_offsets() and rec_get_offsets_func(). */
UNIV_INLINE MY_ATTRIBUTE((nonnull))
void
rec_init_offsets_comp_ordinary(
/*===========================*/
    const rec_t*    rec,    /*!< in: physical record in
                    ROW_FORMAT=COMPACT */
    bool            temp,   /*!< in: whether to use the
                    format for temporary files in
                    index creation */
    const dict_index_t* index,  /*!< in: record descriptor */
    ulint*          offsets)/*!< in/out: array of offsets;
                    in: n=rec_offs_n_fields(offsets) */
{
    ulint       n_null      = index->n_nullable;
    // nulls指针指向null flag第一个字节开始的位置
    const byte* nulls       = temp
        ? rec - 1
        : rec - (1 + REC_N_NEW_EXTRA_BYTES);
    // lens指针指向第一个len的第一个字节位置
    // 这里使用UT_BITS_IN_BYTES(n_null)计算出来了null flag占用的字节数
    const byte* lens        = nulls - UT_BITS_IN_BYTES(n_null);
    ulint       null_mask   = 1;
    
    if (temp && dict_table_is_comp(index->table)) {
        /* No need to do adjust fixed_len=0. We only need to
        adjust it for ROW_FORMAT=REDUNDANT. */
        temp = false;
    }
    /* read the lengths of fields 0..n */
    do {
        const dict_field_t* field = dict_index_get_nth_field(index, i);
        const dict_col_t*   col   = dict_field_get_col(field);
        ulint           len;
        
        // 只对于nullable的列存了null flag，对于这些列才需要判断是否是NULL
        if (!(col->prtype & DATA_NOT_NULL)) {
            /* nullable field => read the null flag */
            ut_ad(n_null--);
            // !(byte) null_mask 即表示已经左移了超过7位
            // 遍历完了1字节，需要重置mask，接着遍历下1字节
            if (UNIV_UNLIKELY(!(byte) null_mask)) {
                nulls--;
                null_mask = 1;
            }
            if (*nulls & null_mask) { // 该列是NULL值
                null_mask <<= 1;
                /* No length is stored for NULL fields.
                We do not advance offs, and we set
                the length to zero and enable the
                SQL NULL flag in offsets[]. */
                len = offs | REC_OFFS_SQL_NULL;
                // 因为是NULL值，也不需要存len列表了，读lens的流程不需要了
                goto resolved;
            }
            // 不是NULL值，移动numm_mask到下一位，并且需要走到后面的lens读取流程
            null_mask <<= 1;
        }
        
        // 流程走到这里说明该列：
        // 1. 不是一个nullable的列
        // 2. 或者是nullable的列，但是值并不是NULL
        if (!field->fixed_len
            || (temp && !dict_col_get_fixed_size(col, temp))) {
            ut_ad(col->mtype != DATA_POINT);
            // 读取变长字段长度的第一个字节
            /* Variable-length field: read the length */
            len = *lens--;
            /* If the maximum length of the field is up
            to 255 bytes, the actual length is always
            stored in one byte. If the maximum length is
            more than 255 bytes, the actual length is
            stored in one byte for 0..127.  The length
            will be encoded in two bytes when it is 128 or
            more, or when the field is stored externally. */
            if (DATA_BIG_COL(col)) {
                // 第1个字节的最高位是1表示长度是使用2个字节表示的
                if (len & 0x80) {
                    // 继续读第2个字节的数据
                    // 注意: 第1个字节的数据在len的高位，第2个字节在低位
                    /* 1exxxxxxx xxxxxxxx */
                    len <<= 8;
                    len |= *lens--;
                    
                    // len是4字节，实际上长度只用最多2字节表示
                    // 4字节的最高位和次高位用于表示NULL和External
                    offs += len & 0x3fff;
                    if (UNIV_UNLIKELY(len & 0x4000)) {
                        // 第1个字节（len的高位）的次高位表示是否有external数据
                        ut_ad(dict_index_is_clust(index));
                        any_ext = REC_OFFS_EXTERNAL;
                        len = offs | REC_OFFS_EXTERNAL;
                    } else {
                        len = offs;
                    }
                    goto resolved;
                }
            }
            len = offs += len;
        } else {
            len = offs += field->fixed_len;
        }
resolved:
        rec_offs_base(offsets)[i + 1] = len;
    } while (++i < rec_offs_n_fields(offsets));
    
    *rec_offs_base(offsets) = (rec - (lens + 1)) | REC_OFFS_COMPACT | any_ext;
}
```

#### Note Pointer节点（rec_init_offsets()）
Compact格式的索引节点（NODE_PTR）的读取方式类似，区别有两点：

   1. 读取的fields数量不一样，最后一个field固定是4字节的node pointer
   2. 索引节点不会有溢出字段

> **TIPS:**
> node pointer节点的null flag字段长度和ordinary节点的该字段长度相同


```cpp
/******************************************************//**
The following function determines the offsets to each field in the
record.	 The offsets are written to a previously allocated array of
ulint, where rec_offs_n_fields(offsets) has been initialized to the
number of fields in the record.	 The rest of the array will be
initialized by this function.  rec_offs_base(offsets)[0] will be set
to the extra size (if REC_OFFS_COMPACT is set, the record is in the
new format; if REC_OFFS_EXTERNAL is set, the record contains externally
stored columns), and rec_offs_base(offsets)[1..n_fields] will be set to
offsets past the end of fields 0..n_fields, or to the beginning of
fields 1..n_fields+1.  When the high-order bit of the offset at [i+1]
is set (REC_OFFS_SQL_NULL), the field i is NULL.  When the second
high-order bit of the offset at [i+1] is set (REC_OFFS_EXTERNAL), the
field i is being stored externally. */
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

	rec_offs_make_valid(rec, index, offsets);

	if (dict_table_is_comp(index->table)) {
		const byte*	nulls;
		const byte*	lens;
		dict_field_t*	field;
		ulint		null_mask;
		ulint		status = rec_get_status(rec);
		ulint		n_node_ptr_field = ULINT_UNDEFINED;

		switch (UNIV_EXPECT(status, REC_STATUS_ORDINARY)) {
		case REC_STATUS_INFIMUM:
		case REC_STATUS_SUPREMUM:
			/* the field is 8 bytes long */
			rec_offs_base(offsets)[0] = REC_N_NEW_EXTRA_BYTES | REC_OFFS_COMPACT;
			rec_offs_base(offsets)[1] = 8;
			return;
		case REC_STATUS_NODE_PTR:
			n_node_ptr_field = dict_index_get_n_unique_in_tree_nonleaf(index);
			break;
		case REC_STATUS_ORDINARY:
			rec_init_offsets_comp_ordinary(rec, false, index, offsets);
			return;
		}
        
        // 读取NODE_PTR类型rec
        nulls = rec - (REC_N_NEW_EXTRA_BYTES + 1);
        // node pointer节点的null flag字段长度和数据节点一样
		lens = nulls - UT_BITS_IN_BYTES(index->n_nullable);
		offs = 0;
		null_mask = 1;

		/* read the lengths of fields 0..n */
		do {
			ulint	len;
            // 读到最后一个node pointer了
			if (UNIV_UNLIKELY(i == n_node_ptr_field)) {
				len = offs += REC_NODE_PTR_SIZE;
				goto resolved;
			}
            
            // 处理null flag
            // ... ...
            // 读取var-len field length
            // ... ...
        } while (++i < rec_offs_n_fields(offsets));
        // ... ...
    } else {
		/* Old-style record: determine extra size and end offsets */
        // ... ...
    }
}
```

#### 伪记录
Compact格式的INFIMUM和SUPREMUM节点是需要特殊处理的，见上一节的代码。

### Redundant（rec_init_offsets()）
Redundant格式因为在字段长度偏移列表中本来就存储了每一个字段的累加偏移，所以直接全部读出来按顺序放到offsets中即可。

> **TIPS:**
> `UNIV_UNLIKELY(cond)`  即 `__builtin_expect(cond, (0))` 是gcc的一个编译优化的宏，用于告诉编译器大多数情况下该条件都是 `FALSE` ，因此编译时 `FALSE` 条件需要执行的指令会紧随cmp指令，避免了jmp的消耗。
> reference: [https://kernelnewbies.org/FAQ/LikelyUnlikely](https://kernelnewbies.org/FAQ/LikelyUnlikely)


### NULL值和External字段标识
与Redundant的字段长度偏移列表格式一样，也使用字段长度的最高位（`REC_OFFS_SQL_NULL`）表示是否是NULL值，使用次高位（`REC_OFFS_EXTERNAL`）表示是否有溢出数据。
```cpp
/* SQL NULL flag in offsets returned by rec_get_offsets() */
#define REC_OFFS_SQL_NULL	((ulint) 1 << 31)
/* External flag in offsets returned by rec_get_offsets() */
#define REC_OFFS_EXTERNAL	((ulint) 1 << 30)
```

## inplace update (rec_set_nth_field()）
inplace update 要求新数据长度和老数据长度一样，对于该种类型的update，不需要在页内分配新的空间用于插入新记录，直接在原记录上更新，该函数在普通的update、rollback、redo apply等流程上都会使用。
```cpp
/***********************************************************//**
This is used to modify the value of an already existing field in a record.
The previous value must have exactly the same size as the new value. If len
is UNIV_SQL_NULL then the field is treated as an SQL null.
For records in ROW_FORMAT=COMPACT (new-style records), len must not be
UNIV_SQL_NULL unless the field already is SQL null. */
UNIV_INLINE
void
rec_set_nth_field(
/*==============*/
	rec_t*		rec,	/*!< in: record */
	const ulint*	offsets,/*!< in: array returned by rec_get_offsets() */
	ulint		n,		/*!< in: index number of the field */
	const void*	data,	/*!< in: pointer to the data if not SQL null */
	ulint		len)	/*!< in: length of the data or UNIV_SQL_NULL */
{
	byte*	data2;
	ulint	len2;

	ut_ad(rec);
	ut_ad(rec_offs_validate(rec, NULL, offsets));

	if (len == UNIV_SQL_NULL) {
		if (!rec_offs_nth_sql_null(offsets, n)) {
            // 只有Redundant格式允许 新数据是NULL，老数据不是NULL
			ut_a(!rec_offs_comp(offsets));
			rec_set_nth_field_sql_null(rec, n);
		}
		return;
	}
    // len不是NULL

	data2 = rec_get_nth_field(rec, offsets, n, &len2);
	if (len2 == UNIV_SQL_NULL) {
		ut_ad(!rec_offs_comp(offsets));
		rec_set_nth_field_null_bit(rec, n, FALSE);
		ut_ad(len == rec_get_nth_field_size(rec, n));
	} else {
		ut_ad(len2 == len);
	}

	ut_memcpy(data2, data, len);
}
```

### NULL值的处理
| **old_val** | **new_val** | **style** | **length** | **result** | **desc** |
| --- | --- | --- | --- | --- | --- |
| 


NO NULL | NO NULL |  |  | old_len == new_len |  |
|  | 

NULL | old-style | var | not allowed |  |
|  |  |  | fixed | ok | 
1. set offset NULL FALG
2. data set 0
 |
|  |  | new-style |  | not allowed |  |
| 


NULL | 

NO NULL | old-style | var | not allowed |  |
|  |  |  | fixed | ok | 
1. unset offset NULL FLAG
2. copy data
 |
|  |  | new-style |  | not allowed |  |
|  | NULL |  |  | no change |  |


> TIPS:
> 关于新数据不是NULL值，老数据是NULL值的情况（2.a），由于Redundant格式对于fixed length类型的NULL值是会填0占位的（比如说CHAR、INT类型），因此可以直接把新数据copy到原占位的空间；对于其他类型（比如VARCHAR）没有占位存储，新老数据的长度是不一样的，这种情况不会调用该函数处理。


## Record Format
![image.png](https://cdn.nlark.com/yuque/0/2020/png/385742/1593517878000-4d5918cd-a2f0-4500-80ee-b0c0cda17d45.png#align=left&display=inline&height=270&originHeight=540&originWidth=1964&size=84094&status=done&style=none&width=982)
![image.png](https://cdn.nlark.com/yuque/0/2020/png/385742/1593517922492-d971acf9-6938-4e84-9628-5a90dc38f398.png#align=left&display=inline&height=193&originHeight=386&originWidth=1970&size=66313&status=done&style=none&width=985)
![image.png](https://cdn.nlark.com/yuque/0/2020/png/385742/1593517937059-d230a337-a5e3-4b0a-8fd0-6b6d70a6bfee.png#align=left&display=inline&height=198&originHeight=396&originWidth=1972&size=62056&status=done&style=none&width=986)
![image.png](https://cdn.nlark.com/yuque/0/2020/png/385742/1593517946850-c1b8860d-e0ce-4f63-b892-ec5f6f9ecad7.png#align=left&display=inline&height=236&originHeight=472&originWidth=1972&size=83372&status=done&style=none&width=986)（图片来源：[https://github.com/jeremycole/innodb_diagrams](https://github.com/jeremycole/innodb_diagrams)）

## n_fields
根据上节我们知道对于同一个表的index，leaf node的non-leaf node存储的field内容和数量不一样。
> get_n_fileds相关函数的语义实际上是对于该行记录，需要取多少个field，目前n_fields个field都能从rec中取到，包括null值；不过有了instant add column特性之后，n_fields个field不一定都能从rec中取到，可能需要从数据字典中拿default值。


- Redundant格式在rec中已经使用n_fields字段存储了实际的field数量，因此可以直接取得（ `rec_get_n_fields_old``()` ）
- Compact格式没有在rec中记录该信息，需要结合数据字典（dict_index_t）和rec类型（status）判断（ 参考 `rec_get_n_fields``()`  ）
   - `REC_STATUS_ORDINARY` ： `dict_index_t::n_fields` 
   - `REC_STATUS_NODE_PTR` ： `dict_index_get_n_unique_in_tree_nonleaf(index) + 1` ，其中 1 表示1个node pointer，`dict_index_get_n_unique_in_tree_nonleaf()`的取值如下：
      - **cluster index**：primary_key 数量
      - **secondary index**：sendory_key + primary_key 数量
   - `REC_STATUS_INFIMUM` / `REC_STATUS_SUPREMUM` ：1


`rec_get_n_fields()` 函数的主要逻辑
```cpp
/** The following function is used to get the number of fields
in a record. 
@return number of data fields */
UNIV_INLINE
ulint
rec_get_n_fields(
/*=============*/
	const rec_t*		rec,	/*!< in: physical record */
	const dict_index_t*	index)	/*!< in: record descriptor */
{
	ut_ad(rec);
	ut_ad(index);

	if (!dict_table_is_comp(index->table)) {
		return(rec_get_n_fields_old(rec));
	}

	switch (rec_get_status(rec)) {
	case REC_STATUS_ORDINARY:
		return(dict_index_get_n_fields(index));
	case REC_STATUS_NODE_PTR:
		return(dict_index_get_n_unique_in_tree(index) + 1);
	case REC_STATUS_INFIMUM:
	case REC_STATUS_SUPREMUM:
		return(1);
	default:
		ut_error;
		return(ULINT_UNDEFINED);
	}
}
```

# 逻辑记录 (data0data)
## 定义 (dtuple_t)
InnoDB中使用 `dtuple_t` 和 `dfield_t` 表示在内存中的逻辑记录，其定义如下：
```cpp
// file: data0data.h
//
/** Structure for an SQL data tuple of fields (logical record) */
struct dtuple_t {
	ulint		info_bits;	/*!< info bits of an index record:
					the default is 0; this field is used
					if an index record is built from
					a data tuple */
	ulint		n_fields;	/*!< number of fields in dtuple */
	ulint		n_fields_cmp;	/*!< number of fields which should
					be used in comparison services
					of rem0cmp.*; the index search
					is performed by comparing only these
					fields, others are ignored; the
					default value in dtuple creation is
					the same value as n_fields */
	dfield_t*	fields;		/*!< fields */
	ulint		n_v_fields;	/*!< number of virtual fields */
	dfield_t*	v_fields;	/*!< fields on virtual column */
	UT_LIST_NODE_T(dtuple_t) tuple_list;
					/*!< data tuples can be linked into a
					list using this field */
};

/** Structure for an SQL data field */
struct dfield_t {
	void*		data;	/*!< pointer to data */
	unsigned	ext:1;	/*!< TRUE=externally stored, FALSE=local */
	unsigned	spatial_status:2;
				/*!< spatial status of externally stored field
				in undo log for purge */
	unsigned	len;	/*!< data length, 实际数据长度; UNIV_SQL_NULL if SQL null */
	dtype_t		type;	/*!< type of data */
};
```

## dtype_t (main type/charset ...)
```cpp
struct dtype_t{
	unsigned	prtype:32;	/*!< precise type; MySQL data
					type, charset code, flags to
					indicate nullability,
					signedness, whether this is a
					binary string, whether this is
					a true VARCHAR where MySQL
					uses 2 bytes to store the length */
	unsigned	mtype:8;	/*!< main data type */

	/* the remaining fields do not affect alphabetical ordering: */

	unsigned	len:16;		/*!< length; for MySQL data this
					is field->pack_length(),
					except that for a >= 5.0.3
					type true VARCHAR this is the
					maximum byte length of the
					string data (in addition to
					the string, MySQL uses 1 or 2
					bytes to store the string length) */ // 数据的定义长度最大值(bytes)
#ifndef UNIV_HOTBACKUP
	unsigned	mbminmaxlen:5;	/*!< minimum and maximum length of a
					character, in bytes;
					DATA_MBMINMAXLEN(mbminlen,mbmaxlen);
					mbminlen=DATA_MBMINLEN(mbminmaxlen);
					mbmaxlen=DATA_MBMINLEN(mbminmaxlen) */
#endif /* !UNIV_HOTBACKUP */
};
```
### main data type
```cpp
/*-------------------------------------------*/
/* The 'MAIN TYPE' of a column */
#define DATA_MISSING	0	/* missing column */
#define	DATA_VARCHAR	1	/* character varying of the
				latin1_swedish_ci charset-collation; note
				that the MySQL format for this, DATA_BINARY,
				DATA_VARMYSQL, is also affected by whether the
				'precise type' contains
				DATA_MYSQL_TRUE_VARCHAR */
#define DATA_CHAR	2	/* fixed length character of the
				latin1_swedish_ci charset-collation */
#define DATA_FIXBINARY	3	/* binary string of fixed length */
#define DATA_BINARY	4	/* binary string */
#define DATA_BLOB	5	/* binary large object, or a TEXT type;
				if prtype & DATA_BINARY_TYPE == 0, then this is
				actually a TEXT column (or a BLOB created
				with < 4.0.14; since column prefix indexes
				came only in 4.0.14, the missing flag in BLOBs
				created before that does not cause any harm) */
#define	DATA_INT	6	/* integer: can be any size 1 - 8 bytes */
#define	DATA_SYS_CHILD	7	/* address of the child page in node pointer */
#define	DATA_SYS	8	/* system column */

/* Data types >= DATA_FLOAT must be compared using the whole field, not as
binary strings */

#define DATA_FLOAT	9
#define DATA_DOUBLE	10
#define DATA_DECIMAL	11	/* decimal number stored as an ASCII string */
#define	DATA_VARMYSQL	12	/* any charset varying length char */
#define	DATA_MYSQL	13	/* any charset fixed length char */
				/* NOTE that 4.1.1 used DATA_MYSQL and
				DATA_VARMYSQL for all character sets, and the
				charset-collation for tables created with it
				can also be latin1_swedish_ci */
// ... ...

#define DATA_MTYPE_MAX	63	/* dtype_store_for_order_and_null_size()
				requires the values are <= 63 */

#define DATA_MTYPE_CURRENT_MIN	DATA_VARCHAR	/* minimum value of mtype */
#define DATA_MTYPE_CURRENT_MAX	DATA_VAR_POINT	/* maximum value of mtype */
```
我们主要关注下面几个类型：

- **DATA_VARCHAR:** character varying of the latin1_swedish_ci charset-collation; note that the MySQL format for this, DATA_BINARY, DATA_VARMYSQL, is also affected by whether the 'precise type' contains DATA_MYSQL_TRUE_VARCHAR.
- **DATA_CHAR**: fixed length character of the latin1_swedish_ci charset-collation.
- **DATA_VARMYSQL**: any **charset** varying length char.
- **DATA_MYSQL**: any **charset** fixed length char. NOTE that 4.1.1 used DATA_MYSQL and DATA_VARMYSQL for all character sets, and the charset-collation for tables created with it can also be latin1_swedish_ci.

因此对于设置了非latin1字符集的VARCHAR(x)和CHAR(x)来说，应该属于DATA_VARMYSQL和DATA_MYSQL类型

### mbminmaxlen
通过下面的宏提取出下面两个信息：

- mbminlen=DATA_MBMINLEN(mbminmaxlen)
- mbmaxlen=DATA_MBMINLEN(mbminmaxlen)

在utf-8等变长编码的情况下，mbminlen和mbmaxlen分别表示该类型的最小长度和最大长度；对于定常编码，两个值应该相等。

e.g.
对于utf-8字符集下的VARCHAR(128)来说，mbminlen = 128，mbmaxlen = 128*3 = 384

### ⭐dtype size (min/max/fixed/null)
三个相关函数：

- min: dtype_get_min_size_low()
- max: dtype_get_max_size_low()
- fixed: dtype_get_fixed_size_low
- null: dtype_get_sql_null_size()

COMPACT 格式下CHAR(xxx)在latn-1等定长编码下是定长类型（fixed length type）；在utf-8等变长编码下，是变长字段。
```cpp
/***********************************************************************//**
Returns the size of a fixed size data type, 0 if not a fixed size type.
@return fixed size, or 0 */
UNIV_INLINE
ulint
dtype_get_fixed_size_low(
/*=====================*/
	ulint	mtype,		/*!< in: main type */
	ulint	prtype,		/*!< in: precise type */
	ulint	len,		/*!< in: length */
	ulint	mbminmaxlen,	/*!< i	n: minimum and maximum length of
				a multibyte character, in bytes */
	ulint	comp)		/*!< in: nonzero=ROW_FORMAT=COMPACT  */
{
	switch (mtype) {
	case DATA_SYS:
	// Fall through.
	case DATA_CHAR: // latin1字符集下的CHAR(X)是定常字段
	case DATA_FIXBINARY:
	case DATA_INT:
	case DATA_FLOAT:
	case DATA_DOUBLE:
	case DATA_POINT:
		return(len);
	case DATA_MYSQL: // any charset fixed length char, e.g. CHAR(x) charset utf8
		if (prtype & DATA_BINARY_TYPE) {
			return(len);
		} else if (!comp) { // REDUNDANT格式认为CHAR(x) charset utf8是定常字段
			return(len);
		} else {
            // 对于COMPACT格式来说
            // 定长编码才算fixed length type，可变长度编码不算fixed length type
			if (DATA_MBMINLEN(mbminmaxlen) == DATA_MBMAXLEN(mbminmaxlen)) {
				return(len);
			}
		}
	case DATA_VARCHAR: // latin1字符集下的VARCHAR(x)是变长字段 
	case DATA_BINARY:
	case DATA_DECIMAL:
	case DATA_VARMYSQL: // 非latin1字符集下的VARCHAR(x)是变长字段
	case DATA_VAR_POINT:
	case DATA_GEOMETRY:
	case DATA_BLOB:
		return(0);
	default:
		ut_error;
	}

	return(0);
}
```

## 大记录 (big_rec_t)
big_rec_t用来存储rec的溢出字段。
```cpp
/** A slot for a field in a big rec vector */
struct big_rec_field_t {
    // 表示该overflow数据对应的是哪一列
	ulint		field_no;	/*!< field number in record */
    // 溢出数据的长度
	ulint		len;		/*!< stored data length, in bytes */
	const void*	data;		/*!< stored data */
};

/** Storage format for overflow data in a big record, that is, a
clustered index record which needs external storage of data fields */
struct big_rec_t {
	mem_heap_t*	heap;		/*!< memory heap from which allocated */
	const ulint	capacity;	/*!< fields array size */
	ulint		n_fields;	/*!< number of stored fields */
	big_rec_field_t*fields;		/*!< stored fields */
};
```

## 行溢出数据处理 (dtuple_convert_big_rec())
InnoDB对于满足一定条件的大记录，会存储某些列的部分或全部数据到溢出页中，原数据列中增加指向溢出页的指针。该函数只是把原记录 `dfield::data` 中的off-page数据copy到 `big_rec_t` 中，把原记录 `dfield::data` 增加20( `BTR_EXTERN_FIELD_REF_SIZE` )字节溢出指针并填零，关于off-page数据的存储以及溢出指针的赋值逻辑在btr模块中实现，这里不再深究。

**行数据需要存储到溢出页的情况**（ `page_zip_rec_needs_ext()` ）：

- compressd page：todo
- 其他类型：行数据总长度（包括extra）大于等于空页大小（除去page头等信息）的一半

`rec_size >= page_get_free_space_of_empty(comp) / 2` 

> **TIPS**:
> 溢出页只在clust index的非unique列存在（循环从 `dict_index_get_n_unique_in_tree(index)` 开始寻找可可以存储到溢出页的field）


对于第二个条件，实际上是要让每个page里至少能存储下2行数据，否则b-tree就退化成链表没有意义了。如果找不到可以存储到溢出字段的列了，但是行大小仍然很大，不能在一行存下2条这样的记录，就会直接报错。

```sql
mysql> CREATE TABLE `t1` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `A` varchar(512) COLLATE utf8_bin DEFAULT NULL,
  `B` varchar(512) COLLATE utf8_bin DEFAULT NULL,
  `C` varchar(512) COLLATE utf8_bin DEFAULT NULL,
  `D` varchar(512) COLLATE utf8_bin DEFAULT NULL,
  `E` varchar(512) COLLATE utf8_bin DEFAULT NULL,
  `F` varchar(512) COLLATE utf8_bin DEFAULT NULL,
  `G` varchar(512) COLLATE utf8_bin DEFAULT NULL,
  `H` varchar(512) COLLATE utf8_bin DEFAULT NULL,
  `I` varchar(512) COLLATE utf8_bin DEFAULT NULL,
  `J` varchar(512) COLLATE utf8_bin DEFAULT NULL,
  `K` varchar(512) COLLATE utf8_bin DEFAULT NULL,
  `L` varchar(512) COLLATE utf8_bin DEFAULT NULL,
  `M` varchar(512) COLLATE utf8_bin DEFAULT NULL,
  `N` varchar(512) COLLATE utf8_bin DEFAULT NULL,
  `O` varchar(512) COLLATE utf8_bin DEFAULT NULL,
  `P` varchar(512) COLLATE utf8_bin DEFAULT NULL,
  `Q` varchar(512) COLLATE utf8_bin DEFAULT NULL,
  `R` varchar(512) COLLATE utf8_bin DEFAULT NULL,
  `S` varchar(512) COLLATE utf8_bin DEFAULT NULL,
  `T` varchar(512) COLLATE utf8_bin DEFAULT NULL,
  `U` varchar(512) COLLATE utf8_bin DEFAULT NULL,
  `V` varchar(512) COLLATE utf8_bin DEFAULT NULL,
  `W` varchar(512) COLLATE utf8_bin DEFAULT NULL,
  `X` varchar(512) COLLATE utf8_bin DEFAULT NULL,
  `Y` varchar(512) COLLATE utf8_bin DEFAULT NULL,
  `Z` varchar(512) COLLATE utf8_bin DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB ROW_FORMAT=COMPACT

mysql> insert into t1 values(3, repeat('a', 512), repeat('a', 512), repeat('a', 512), repeat('a', 512), repeat('a', 512), repeat('a', 512), repeat('a', 512), repeat('a', 512), repeat('a', 512), repeat('a', 512), repeat('a', 512), repeat('a', 512), repeat('a', 512), repeat('a', 512), repeat('a', 512), repeat('a', 512), repeat('a', 512), repeat('a', 512), repeat('a', 512), repeat('a', 512), repeat('a', 512), repeat('a', 512), repeat('a', 512), repeat('a', 512), repeat('a', 512), repeat('a', 512));
ERROR 1118 (42000): Row size too large (> 8126). Changing some columns to TEXT or BLOB or using ROW_FORMAT=DYNAMIC or ROW_FORMAT=COMPRESSED may help. In current row format, BLOB prefix of 768 bytes is stored inline.
```

`page_get_free_space_of_empty()` 的计算方法：
```cpp
/*************************************************************//**
Calculates free space if a page is emptied.
@return free space */
UNIV_INLINE
ulint
page_get_free_space_of_empty(
/*=========================*/
	ulint	comp)		/*!< in: nonzero=compact page layout */
{
	if (comp) {
		return((ulint)(UNIV_PAGE_SIZE
			       - PAGE_NEW_SUPREMUM_END
			       - PAGE_DIR
			       - 2 * PAGE_DIR_SLOT_SIZE));
	}

	return((ulint)(UNIV_PAGE_SIZE
		       - PAGE_OLD_SUPREMUM_END
		       - PAGE_DIR
		       - 2 * PAGE_DIR_SLOT_SIZE));
}
```

**溢出数据如何存储：**

- Redundant和Compact(狭义)行格式：列数据存储的是数据的前 768 字节 + 20字节溢出页指针
- Dynamic和Compress行格式：列数据只存储20字节溢出页指针
> **TIPS:**
> 在这里只是预留了20字节溢出指针的位置，并全部填0，关于off-page的存储和该溢出指针的初始化，详见btr模块。
>  /* Clear the extern field reference (BLOB pointer). */
>  memset(data + local_prefix_len, 0, BTR_EXTERN_FIELD_REF_SIZE);


**不能（不需要）存储到溢出字段的情况：**

- **定长字段**（field->fixed_len > 0，不包括数据最大定义长度大于768的定长字段，e.g. utfmb4下的CHAR(255)，ref：[dict](https://www.yuque.com/littleneko/ubavq5/sk19n9#VKfRI)）
- NULL值
- 已经是是ext字段了（因为是while循环每次在所有列中找最长的列用来转换为溢出字段，可能多次遍历）
- 实际数据长度小于local_len（768或0）
- 实际数据长度小于BTR_EXTERN_LOCAL_STORED_MAX_SIZE

主要实现在函数 `dtuple_convert_big_rec()` ，该函数对 `dtuple_t` 数据中需要用溢出字段存储的数据列生成 `big_rec_t` 返回，并更新对应的 `dfield_t::data` / `dfield_t::ext` `dfield_t::len` 信息。
```cpp
/**************************************************************//**
Moves parts of long fields in entry to the big record vector so that
the size of tuple drops below the maximum record size allowed in the
database. Moves data only from those fields which are not necessary
to determine uniquely the insertion place of the tuple in the index.
@return own: created big record vector, NULL if we are not able to
shorten the entry enough, i.e., if there are too many fixed-length or
short fields in entry or the index is clustered */
big_rec_t*
dtuple_convert_big_rec(
/*===================*/
	dict_index_t*	index,	/*!< in: index */
	upd_t*		upd,	/*!< in/out: update vector */
	dtuple_t*	entry,	/*!< in/out: index entry */
	ulint*		n_ext)	/*!< in/out: number of
				externally stored columns */
{
    // ... ...
    // 只有Clustered Index能存储溢出页，Secondary Index不能有溢出页
    if (!dict_index_is_clust(index)) {
		return(NULL);
	}
    
    // Redundant和Compact格式存储大数据的前768字节+20字节溢出数据指针
    // dict_table_get_format()从dict_table_t::flags字段取出ATOMIC_BLOBS位
    if (dict_table_get_format(index->table) < UNIV_FORMAT_B) {
		/* up to MySQL 5.1: store a 768-byte prefix locally */
		local_len = BTR_EXTERN_FIELD_REF_SIZE + DICT_ANTELOPE_MAX_INDEX_COL_LEN;
	} else { // Dynamic和Compress，只存储20字节的溢出数据指针
		/* new-format table: do not store any BLOB prefix locally */
		local_len = BTR_EXTERN_FIELD_REF_SIZE;
	}
    
    // 这个size即该行逻辑记录如果直接转换成物理记录后的size
    // 包括(col offset list + [null flag] + hdr + col data) 完整行数据的大小
    size = rec_get_converted_size(index, entry, *n_ext);
    
    // 一直循环，每次处理一个长度最大的列，直到行数据大小满足特定条件为止
    while (page_zip_rec_needs_ext(rec_get_converted_size(index, entry, *n_ext),
				      dict_table_is_comp(index->table),
				      dict_index_get_n_fields(index),
				      dict_table_page_size(index->table))) {
        
        // 找到所有可以存储到溢出字段的列中最长的1列
        // 对于clustered index的leaf page来说，u_unique的列即主键，不能存储到溢出字段
        for (i = dict_index_get_n_unique_in_tree(index);
		     i < dtuple_get_n_fields(entry); i++) {
			ulint	savings;
            
            dfield = dtuple_get_nth_field(entry, i);
			ifield = dict_index_get_nth_field(index, i);

			/* Skip fixed-length, NULL, externally stored,
			or short columns */

			if (ifield->fixed_len
			    || dfield_is_null(dfield)
			    || dfield_is_ext(dfield)
			    || dfield_get_len(dfield) <= local_len
			    || dfield_get_len(dfield)
			    <= BTR_EXTERN_LOCAL_STORED_MAX_SIZE) {
				goto skip_field;
			}

			savings = dfield_get_len(dfield) - local_len;

			/* Check that there would be savings */
			if (longest >= savings) {
				goto skip_field;
			}

			/* In DYNAMIC and COMPRESSED format, store
			locally any non-BLOB columns whose maximum
			length does not exceed 256 bytes.  This is
			because there is no room for the "external
			storage" flag when the maximum length is 255
			bytes or less. This restriction trivially
			holds in REDUNDANT and COMPACT format, because
			there we always store locally columns whose
			length is up to local_len == 788 bytes.
			@see rec_init_offsets_comp_ordinary */
			if (!DATA_BIG_COL(ifield->col)) {
				goto skip_field;
			}

			longest_i = i;
			longest = savings;

skip_field:
			continue;
		}
        
        // 不能再找出1个可以存储到溢出字段的列时，就返回了
        // 注意：从这里返回时，page_zip_rec_needs_ext()条件仍然满足
        // 也就是说，虽然行大小太大仍然不能满足在一行存储至少2条记录的条件，
        // 但是已经找不到可以存储到溢出字段的行是时候，就不管了
        if (!longest) {
			/* Cannot shorten more */
			mem_heap_free(heap);
			return(NULL);
		}
        
        /* Move data from field longest_i to big rec vector.

		We store the first bytes locally to the record. Then
		we can calculate all ordering fields in all indexes
		from locally stored data. */

		dfield = dtuple_get_nth_field(entry, longest_i);
		ifield = dict_index_get_nth_field(index, longest_i);
		local_prefix_len = local_len - BTR_EXTERN_FIELD_REF_SIZE;

		vector->append(
			big_rec_field_t(
				longest_i,
				dfield_get_len(dfield) - local_prefix_len,
				static_cast<char*>(dfield_get_data(dfield))
				+ local_prefix_len));

		/* Allocate the locally stored part of the column. */
		data = static_cast<byte*>(mem_heap_alloc(heap, local_len));

		/* Copy the local prefix. */
		memcpy(data, dfield_get_data(dfield), local_prefix_len);
		/* Clear the extern field reference (BLOB pointer). */
		memset(data + local_prefix_len, 0, BTR_EXTERN_FIELD_REF_SIZE);
        
        // 更新dtuple的data为去除了overflow数据的data
        dfield_set_data(dfield, data, local_len);
        // 设置ext标识
		dfield_set_ext(dfield);

		n_fields++;
		(*n_ext)++;
		ut_ad(n_fields < dtuple_get_n_fields(entry));
        
        // upd 相关
        // ... ...

	ut_ad(n_fields == vector->n_fields);

	return(vector);
}
```

# 逻辑记录和物理记录的转换
## 逻辑记录转换成物理记录（rec_convert_dtuple_to_rec()）
逻辑记录转换成物理记录的过程中，除了需要把列数据按顺序写入rec里以外，还需要把一些元信息也同时写入，入口函数为 `rec_convert_dtuple_to_rec()` ，需要区分Redundant和Compact格式。

> **TIPS**：
> 上层调用该函数时，应该已经调用 `dtuple_convert_big_rec()` 和btr相关的函数处理好大记录的溢出数据了，即溢出页已经存储好并且溢出页指针信息也已经更新到 `dfield_t::data` 中了


### Redundant
入口函数 `rec_convert_dtuple_to_rec_old()` ，主要步骤：

1. 计算extra字段（hdr和字段长度偏移列表）的长度，根据该长度的到列数据起始位置（rec）： `rec_get_converted_extra_size()` 
2. 设置rec的头的n_fields和info_bits字段： `rec_set_n_fields_old()` , `rec_set_info_bits_old()` 
3. Store the data and the offsets
   1. 判断字段长度偏移列表每个元素的字节数( `!n_ext && data_size <= REC_1BYTE_OFFS_LIMIT` )，写入short flag： `rec_set_1byte_offs_flag()` 
   2. 遍历tuple_t的每一个field
   3. 写入数据： `data_write_sql_null()` （NULL值）/ `memcpy()` 
   4. 计算字段偏移列表的数据并写入： `rec_1_set_field_end_info()` / `rec_2_set_field_end_info()` 

**主要流程**
```cpp
/*********************************************************//**
Builds an old-style physical record out of a data tuple and
stores it beginning from the start of the given buffer.
@return pointer to the origin of physical record */
static
rec_t*
rec_convert_dtuple_to_rec_old(
/*==========================*/
	byte*		buf,	/*!< in: start address of the physical record */
	const dtuple_t*	dtuple,	/*!< in: data tuple */
	ulint		n_ext)	/*!< in: number of externally stored columns */
{
	const dfield_t*	field;
	ulint		n_fields;
	ulint		data_size;
	rec_t*		rec;
	ulint		end_offset;
	ulint		ored_offset;
	ulint		len;
	ulint		i;

	n_fields = dtuple_get_n_fields(dtuple);
	data_size = dtuple_get_data_size(dtuple, 0); // 所有数据列的总长度

	/* Calculate the offset of the origin in the physical record */

    // 计算hdr和col offset list的总长度，并把指针移动到数据列起始位置
	rec = buf + rec_get_converted_extra_size(data_size, n_fields, n_ext);
	/* Store the number of fields */
	rec_set_n_fields_old(rec, n_fields);

	/* Set the info bits of the record */
	rec_set_info_bits_old(rec, dtuple_get_info_bits(dtuple) & REC_INFO_BITS_MASK);

	/* Store the data and the offsets */
    
	end_offset = 0;
    
    if (!n_ext && data_size <= REC_1BYTE_OFFS_LIMIT) {
        // ... ...
	} else {
        rec_set_1byte_offs_flag(rec, FALSE);

		for (i = 0; i < n_fields; i++) {
			field = dtuple_get_nth_field(dtuple, i);

			if (dfield_is_null(field)) {
                // Redundant的NULL值占用空间不一样:
                // 1. fixed length type: 定义长度, 写入时全部填0
                // 2. var length type: 0
				len = dtype_get_sql_null_size(dfield_get_type(field), 0);
				data_write_sql_null(rec + end_offset, len);

				end_offset += len;
				ored_offset = end_offset | REC_2BYTE_SQL_NULL_MASK;
			} else {
				/* If the data is not SQL null, store it */
				len = dfield_get_len(field);

				memcpy(rec + end_offset, dfield_get_data(field), len);

				end_offset += len;
				ored_offset = end_offset;

				if (dfield_is_ext(field)) {
					ored_offset |= REC_2BYTE_EXTERN_MASK;
				}
			}

			rec_2_set_field_end_info(rec, i, ored_offset);
		}
    }
    return(rec);
}
```

### Compact
入口函数 `rec_convert_dtuple_to_rec_new()` ，主要步骤：

1. 计算extra字段的长度，根据该长度得到数据列起始位置指针（rec）： `rec_get_converted_size_comp()` ，该函数的计算方法比Redundant要复杂，需要判断字段列表里每个长度是使用1字节还是2字节表示。
2. 写入数据： `rec_convert_dtuple_to_rec_comp()` 
   1. 遍历dtuple的每一个field
   2. 对于nullable且是NULL值的列设置null flag（continue，NULL值不需要写列数据）
   3. 写入变长字段长度列表数据，需要根据数据类型和实际长度计算占用1字节还是2字节
   4. 写入数据： `memcpy()` 
3. 设置头信息

**extra字段长度计算**
核心函数是 `rec_get_converted_size_comp_prefix_low()` ，其主要逻辑为：
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
	bool			temp)	/*!< in: whether this is a
					temporary file record */
{
    ulint	extra_size;
    ulint	data_size;
	ulint	i;
	ulint	n_null	= (n_fields > 0) ? index->n_nullable : 0;
    
    // 计算null flag的长度
    extra_size = temp
		? UT_BITS_IN_BYTES(n_null)
		: REC_N_NEW_EXTRA_BYTES
		+ UT_BITS_IN_BYTES(n_null);
    
    // ... ...
    
    /* read the lengths of fields 0..n */
	for (i = 0; i < n_fields; i++) {
        // ... ...
        
        // 变长字段长度列表中不存储NULL值列的长度
        if (dfield_is_null(&fields[i])) {
			continue;
		}
        
        if (fixed_len) {  // 定长字段不存储在变长字段长度列表中
            // do nothing
        } else if (dfield_is_ext(&fields[i])) {	// extren一定使用2字节表示
			ut_ad(DATA_BIG_COL(col));
			extra_size += 2;
		} else if (len < 128 || !DATA_BIG_COL(col)) {
			extra_size++;
		} else {
			/* For variable-length columns, we look up the
			maximum length from the column itself.  If this
			is a prefix index column shorter than 256 bytes,
			this will waste one byte. */
			extra_size += 2;
		}
		data_size += len;
	}
    
    if (extra) {
		*extra = extra_size;
	}
    
    // ... ...
    return(extra_size + data_size);
}
```

**写入列数据/变长字段长度列表/null flag**
```cpp
/*********************************************************//**
Builds a ROW_FORMAT=COMPACT record out of a data tuple. */
UNIV_INLINE
void
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
	const dfield_t*	field;
	const dtype_t*	type;
	byte*		end;
	byte*		nulls;
	byte*		lens;
	ulint		len;
	ulint		i;
	ulint		n_node_ptr_field;
	ulint		fixed_len;
	ulint		null_mask	= 1;
	ulint		n_null;
	ulint		num_v = v_entry ? dtuple_get_n_v_fields(v_entry) : 0;
    
    if (temp) {
        // ... ...
	} else {
		ut_ad(v_entry == NULL);
		ut_ad(num_v == 0);
        
        // nulls指针指向null flag的第1个字节起始位置(逆序)
		nulls = rec - (REC_N_NEW_EXTRA_BYTES + 1);

		switch (UNIV_EXPECT(status, REC_STATUS_ORDINARY)) {
		case REC_STATUS_ORDINARY:
			ut_ad(n_fields <= dict_index_get_n_fields(index));
			n_node_ptr_field = ULINT_UNDEFINED;
			break;
		case REC_STATUS_NODE_PTR:
			ut_ad(n_fields == dict_index_get_n_unique_in_tree_nonleaf(index) + 1);
			n_node_ptr_field = n_fields - 1;
			break;
		case REC_STATUS_INFIMUM:
		case REC_STATUS_SUPREMUM:
			ut_ad(n_fields == 1);
			n_node_ptr_field = ULINT_UNDEFINED;
			break;
		default:
			ut_error;
			return;
		}
	}
    
    end = rec;

	if (n_fields != 0) {
		n_null = index->n_nullable;
        // lens指向第1个长度字段的第1个字节(逆序)
		lens = nulls - UT_BITS_IN_BYTES(n_null);
		/* clear the SQL-null flags */
		memset(lens + 1, 0, nulls - lens);
	}

	/* Store the data and the offsets */
	for (i = 0; i < n_fields; i++) {
		const dict_field_t*	ifield;
		dict_col_t*		col = NULL;

		field = &fields[i];
		type = dfield_get_type(field);
		len = dfield_get_len(field);

        // NODE_PTR类型的rec
		if (UNIV_UNLIKELY(i == n_node_ptr_field)) {
			ut_ad(dtype_get_prtype(type) & DATA_NOT_NULL);
			ut_ad(len == REC_NODE_PTR_SIZE);
			memcpy(end, dfield_get_data(field), len);
			end += REC_NODE_PTR_SIZE;
			break;
		}

        // 只有nullable的字段才需要设置null flag
		if (!(dtype_get_prtype(type) & DATA_NOT_NULL)) {
			/* nullable field */
			ut_ad(n_null--);

            // null flag 1字节用完，逆序移动到下1个字节
			if (UNIV_UNLIKELY(!(byte) null_mask)) {
				nulls--;
				null_mask = 1;
			}

			ut_ad(*nulls < null_mask);

			/* set the null flag if necessary */
			if (dfield_is_null(field)) {
				*nulls |= null_mask;
				null_mask <<= 1;
                // 对于NULL值只需要设置null flag字段，不再需要写列数据
				continue;
			}

			null_mask <<= 1;
		}
        // 代码走到这里一定是非NULL值
		/* only nullable fields can be null */
		ut_ad(!dfield_is_null(field));

		ifield = dict_index_get_nth_field(index, i);
		fixed_len = ifield->fixed_len;
		col = ifield->col;
		if (temp && fixed_len
		    && !dict_col_get_fixed_size(col, temp)) {
			fixed_len = 0;
		}

		/* If the maximum length of a variable-length field
		is up to 255 bytes, the actual length is always stored
		in one byte. If the maximum length is more than 255
		bytes, the actual length is stored in one byte for
		0..127.  The length will be encoded in two bytes when
		it is 128 or more, or when the field is stored externally. */
		if (fixed_len) {
            // do nothing
		} else if (dfield_is_ext(field)) {	// external时使用2字节存储长度
			ut_ad(DATA_BIG_COL(col));
            // 768字节的数据+20字节的extrenal指针
			ut_ad(len <= REC_ANTELOPE_MAX_INDEX_COL_LEN + BTR_EXTERN_FIELD_REF_SIZE);
			// 逆序第1个字节存储len的第2个字节位（从低到高计算）
            // 并且把external位(次高位)和2字节长度位(最高位)置位
            // 0xc0 = 1100 0000
            *lens-- = (byte) (len >> 8) | 0xc0;
            // 逆序第2个字节存储len的低字节位
			*lens-- = (byte) len;
		} else {
			/* DATA_POINT would have a fixed_len */
			ut_ad(dtype_get_mtype(type) != DATA_POINT);
			ut_ad(len <= dtype_get_len(type)
			      || DATA_LARGE_MTYPE(dtype_get_mtype(type))
			      || !strcmp(index->name,
					 FTS_INDEX_TABLE_IND_NAME));
            // 1字节长度有2种情况：
            // 	1. 列数据实际长度小于128，列类型定义可以是DATA_BIG_COL
            //	2. 列类型定义不是DATA_BIG_COL，即var-len类型的长度小于256且不是BLOB或GEO类型
			if (len < 128 || !DATA_BIG_LEN_MTYPE(
                dtype_get_len(type), dtype_get_mtype(type))) {
				*lens-- = (byte) len;
			} else { // 其他情况包括了列实际数据长度大于等于128且是DATA_BIG_COL类型
				ut_ad(len < 16384);
                // 只置位2字节长度位（0x80 = 1000 0000）
				*lens-- = (byte) (len >> 8) | 0x80;
				*lens-- = (byte) len;
			}
		}

		memcpy(end, dfield_get_data(field), len);
		end += len;
	}
    
    if (!num_v) {
		return;
	}
    
    // ... ...
}
```
### NULL值占用空间大小

- **Redundant**：For fixed length types it is the fixed length of the type, otherwise 0. 对于fixed length type，写入数据时需要全部填0（ `dtype_get_sql_null_size()` ）
- **Compact**：NULL值不占用任何存储空间，只需要在null flag字段把对应的bit位设置为1

对于Redundant格式，NULL值占用的空间大小参考函数 `dtype_get_sql_null_size()` ，该函数实际上调用 `dtype_get_fixed_size_low()` 返回定长数据的长度或者是0。

### var-len field 判断
前面说过COMAPCT格式的var-len field length字段只存储了non-null变长字段的长度，如果在某种编码下其长度超过了768字节，需要存储到溢出页，就需要在var-len field length中记录ext标记。实际上，这种情况下该char被视为variable-length类型，参考[dict_field_t::fixed_len的初始化逻辑](https://www.yuque.com/littleneko/ubavq5/sk19n9#VKfRI)（ `if (field->fixed_len > DICT_MAX_FIXED_COL_LEN) { field->fixed_len = 0; }` ）

### CHAR/VARCHAR类型存储
// todo

# 记录之间的比较（rem0cmp）
