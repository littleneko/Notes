# 物理存储（fsp、fil）
![image.png](https://cdn.nlark.com/yuque/0/2020/png/385742/1593969263153-613b3925-a532-4395-9350-f99119729b90.png#align=left&display=inline&height=704&originHeight=1408&originWidth=2082&size=866719&status=done&style=none&width=1041)

## 页（FIL）
页是InnoDB存储引擎访问的最小I/O单元，页的默认大小是16KiB（如不特别说明，下面所有的描述都是基于16KiB页大小的），一个表空间被划分成一个个的页管理，只需要知道页偏移（page_no）就可以定位到一个页。

### FIL HEADER
| **NAME** | **LEN**
**(byte)** | **DESC** |
| --- | --- | --- |
| FIL_PAGE_SPACE_OR_CHKSUM | 4 | in < MySQL-4.0.14 space id the page belongs to (== 0) but in later versions the 'new' checksum of the page |
| FIL_PAGE_OFFSET | 4 | page_no |
| FIL_PAGE_PREV | 4 | if there is a 'natural' successor of the page, its offset. Otherwise FIL_NULL.
B-tree index pages (FIL_PAGE_TYPE contains FIL_PAGE_INDEX) on the same PAGE_LEVEL are maintained as a doubly linked list via FIL_PAGE_PREV and FIL_PAGE_NEXT in the collation order of the smallest user record on each page.
This field is not set on BLOB pages, which are stored as a singly-linked list.  See also FIL_PAGE_NEXT.

使用页偏移量即page_no表示 |
| FIL_PAGE_NEXT | 4 |  |
| FIL_PAGE_LSN | 8 | lsn of the end of the newest modification log record to the page |
| FIL_PAGE_TYPE | 2 | 页类型，下面介绍 |
| FIL_PAGE_FILE_FLUSH_LSN | 8 |  |
| FIL_PAGE_ARCH_LOG_NO_OR_SPACE_ID | 4 | starting from 4.1.x this contains the space id of the page |
| (FIL_PAGE_DATA) | 38 |  |


### FIL_PAGE_TYPE
InnoDB中一共定义了下面这些PAGE TYPE，这部分内容中我们需要重点关注以下几种类型：

- FIL_PAGE_TYPE_FSP_HDR：space header页，page_no=0
- FIL_PAGE_TYPE_XDES：用来保存extent的xdes信息的页，page_no=16384*N
- FIL_PAGE_IBUF_BITMAP：page_no=16384*N+1
- FIL_PAGE_INODE：专门用来保存segment inode的页，第一次分配的页为page_no=2
- FIL_PAGE_TYPE_SYS：Insert buffer header，dictionary header等页都是该类型
- FIL_PAGE_INDEX：B-tree的leaf和non-leaf节点
- FIL_PAGE_TYPE_ALLOCATED
- FIL_PAGE_IBUF_FREE_LIST
- FIL_PAGE_UNDO_LOG
```cpp
/** File page types (values of FIL_PAGE_TYPE) @{ */
#define FIL_PAGE_INDEX		17855	/*!< B-tree node */
#define FIL_PAGE_RTREE		17854	/*!< B-tree node */
#define FIL_PAGE_UNDO_LOG	2	/*!< Undo log page */
#define FIL_PAGE_INODE		3	/*!< Index node */
#define FIL_PAGE_IBUF_FREE_LIST	4	/*!< Insert buffer free list */
/* File page types introduced in MySQL/InnoDB 5.1.7 */
#define FIL_PAGE_TYPE_ALLOCATED	0	/*!< Freshly allocated page */
#define FIL_PAGE_IBUF_BITMAP	5	/*!< Insert buffer bitmap */
#define FIL_PAGE_TYPE_SYS	6	/*!< System page */
#define FIL_PAGE_TYPE_TRX_SYS	7	/*!< Transaction system data */
#define FIL_PAGE_TYPE_FSP_HDR	8	/*!< File space header */
#define FIL_PAGE_TYPE_XDES	9	/*!< Extent descriptor page */
#define FIL_PAGE_TYPE_BLOB	10	/*!< Uncompressed BLOB page */
#define FIL_PAGE_TYPE_ZBLOB	11	/*!< First compressed BLOB page */
#define FIL_PAGE_TYPE_ZBLOB2	12	/*!< Subsequent compressed BLOB page */
#define FIL_PAGE_TYPE_UNKNOWN	13	/*!< In old tablespaces, garbage
					in FIL_PAGE_TYPE is replaced with this
					value when flushing pages. */
#define FIL_PAGE_COMPRESSED	14	/*!< Compressed page */
#define FIL_PAGE_ENCRYPTED	15	/*!< Encrypted page */
#define FIL_PAGE_COMPRESSED_AND_ENCRYPTED 16
					/*!< Compressed and Encrypted page */
#define FIL_PAGE_ENCRYPTED_RTREE 17	/*!< Encrypted R-tree page */

/** Used by i_s.cc to index into the text description. */
#define FIL_PAGE_TYPE_LAST	FIL_PAGE_TYPE_UNKNOWN
					/*!< Last page type */
```

## 区（XDES）
页是InnoDB存储引擎访问的最小单位，区是InnoDB空间申请的最小单位，一个区由连续的64个页组成，大小1MB。

### EXTENT DESCRIPTOR
File extent descriptor data structure: contains bits to tell which pages in the extent are free and which contain old tuple version to clean.

| **NAME** | **LEN**
**(byte)** | **DESC** |
| --- | --- | --- |
| XDES_ID | 8 | The identifier of the segment to which this extent belongs |
| XDES_FLST_NODE | 12 |  |
| XDES_STATE | 4 | 
- XDES_FREE：该extent在FSP_FREE链表中，不属于任何一个段
- XDES_FREE_FRAG：该区是碎片区，在FSP_FREE_FRAG链表中
- XDES_FULL_FRAG：该区是碎片区，在FSP_FULL_FRAG链表中
- XDES_FSEG：该区属于某个段
 |
| XDES_BITMAP | (2*64)/8 = 16 | 该区管理的所有页的状态，每个状态使用2 bit（ `XDES_BITS_PER_PAGE` ）描述，一共管理 `FSP_EXTENT_SIZE` （在16KiB页下是64）个页

两个bit分别表示：
- XDES_FREE_BIT：Index of the bit which tells if the page is free
- XDES_CLEAN_BIT：urrently not used!
 |
| (XDES_SIZE) | 40 | (XDES_BITMAP + UT_BITS_IN_BYTES(FSP_EXTENT_SIZE * XDES_BITS_PER_PAGE)) |


一个区管理的页数量，根据page size的不同，计算方法如下（对于常见的16KiB页，一个区管理64个页）：
```cpp
/** File space extent size in pages
page size | file space extent size
----------+-----------------------
   4 KiB  | 256 pages = 1 MiB
   8 KiB  | 128 pages = 1 MiB
  16 KiB  |  64 pages = 1 MiB
  32 KiB  |  64 pages = 2 MiB
  64 KiB  |  64 pages = 4 MiB
*/
#define FSP_EXTENT_SIZE         ((UNIV_PAGE_SIZE <= (16384) ?	\
				(1048576 / UNIV_PAGE_SIZE) :	\
				((UNIV_PAGE_SIZE <= (32768)) ?	\
				(2097152 / UNIV_PAGE_SIZE) :	\
				(4194304 / UNIV_PAGE_SIZE))))
```

extent desriptor并不是在每个extent中单独存储，而是每256个extent descriptor保存在1个page中，即每隔16384（256×64）个页，需要有一个页用来保存extent desriptor。（后面我们对于这256个extent称为一个extent group）
![image.png](https://cdn.nlark.com/yuque/0/2020/png/385742/1593966619034-5a29c7aa-548c-4fb9-a8bb-c17b8f0a5dcb.png#align=left&display=inline&height=842&originHeight=842&originWidth=2352&size=120183&status=done&style=none&width=2352)
如上图所示，space的第0个页中，保存有SPACE HEADER，接着是256个xdes信息，每个xdes管理64个页，每间隔16384个页就有一个页用于保存xdes信息。除了第0个页的 `FIL_PAGE_TYPE` 是 `FIL_PAGE_TYPE_FSP_HDR` 以外，其他保存xdes的页的 `FIL_PAGE_TYPE` 都是 `FIL_PAGE_TYPE_XDES` 

### Get Extent Descripter by Page（ `xdes_get_descriptor()` -> `xdes_get_descriptor_with_space_hdr()` ）


## 段（FSEG）
与page和extent不同，segment是一个逻辑的概念，是一些extent和page的集合。

### File segment header
The file segment header points to the inode describing the file segment.
```cpp
// file: fsp0types.h
//
/** Data type for file segment header */
typedef	byte	fseg_header_t;

#define FSEG_HDR_SPACE		0	/*!< space id of the inode */
#define FSEG_HDR_PAGE_NO	4	/*!< page number of the inode */
#define FSEG_HDR_OFFSET		8	/*!< byte offset of the inode */

#define FSEG_HEADER_SIZE	10	/*!< Length of the file system header, in bytes */
```
### FILE SEGMENT INODE
| **NAME** | **LEN**
**(byte)** | **DESC** |
| --- | --- | --- |
| FSEG_INODE_PAGE_NODE | 12 | the list node for linking
    	segment inode pages |
| FSEG_ID | 8 | 8 bytes of segment id: if this is 0, it means that the header is unused |
| FSEG_NOT_FULL_N_USED | 4 | number of used segment pages in the FSEG_NOT_FULL list |
| FSEG_FREE | 16 | list of free extents of this segment |
| FSEG_NOT_FULL | 16 | list of partially free extents |
| FSEG_FULL | 16 | list of full extents |
| FSEG_MAGIC_N | 4 |  |
| FSEG_FRAG_ARR | 128 | array of individual pages belonging to this segment in fsp fragment extent lists.
碎片页数组，保存从FSP的碎片区申请的page的page_no，每个page_no大小4byte，一共保存FSP_EXTENT_SIZE / 2（在16KiB页大小时该值为32）个page |
| (FSEG_INODE_SIZE) | 192 | (16 + 3 * FLST_BASE_NODE_SIZE + FSEG_FRAG_ARR_N_SLOTS * FSEG_FRAG_SLOT_SIZE) |

segment inode保存在单独的inode page中，一个inode page可以保存的inode个数为 `((page_size.physical() - FSEG_ARR_OFFSET - 10) / FSEG_INODE_SIZE)` ，在16KiB页大小时该值为85。


### 创建segment（ `fseg_create(space_id, page, byte_offset, ...)` -> `fseg_create_general()` ）

1. 从fsp的inode page中新申请一个inode（ `fsp_alloc_seg_inode()` ）
2. 初始化inode
   1. 分配新的seg_id（从fsp hdr中独出FSP_SEG_ID并递增），写入inode中
   2. 其他字段填充NULL（FSEG_FRAG_ARR_N_SLOTS等）
3. 如果传入的page_no为0，在新seg中分配一个page（ `fseg_alloc_free_page_low()` ）作为seg hdr page（这里首先是从 `FSEG_FRAG_ARR` 中分配碎片页）
4. 向page_no所在page的byte_offset偏移处写入seg hdr（ `FSEG_HDR_OFFSET` ， `FSEG_HDR_PAGE_NO` ， `FSEG_HDR_SPACE` ，指向新分配的inode）


### 分配区（ `fseg_alloc_free_extent()` ）


### 分配碎片页（ `fseg_alloc_free_page()` -> `fseg_alloc_free_page_low()` ）

1. 根据seg hdr信息得到inode（ `fseg_inode_get()` ）
2. `fseg_alloc_free_page_low()` // todo

### 申请新的区（ `fseg_fill_free_list()` -> `fsp_alloc_free_extent()` ）

## 表空间（FSP）


### SPACE HEADER
File space header data structure: this data structure is contained in the first page of a space. The space for this header is reserved in every extent descriptor page, but used only in the first.

| **NAME** | **LEN**
**(byte)** | **DESC** |
| --- | --- | --- |
| FSP_SPACE_ID | 4 |  |
| FSP_NOT_USED | 4 |  |
| FSP_SIZE | 4 | Current size of the space in pages. space的物理文件的大小 |
| FSP_FREE_LIMIT | 4 | 指向表空间中最后一个初始化的page位置（page_no），这之前的page已经初始化过了（挂在某一个LIST上），从该位置到FSP_SIZE位置的是未初始化的（未挂到人金额一个LIST上），使用时需要先初始化 |
| FSP_SPACE_FLAGS | 4 | FLAG里面保存了page size等信息 |
| FSP_FRAG_N_USED | 4 | number of used pages in the FSP_FREE_FRAG list |
| FSP_FREE | 16 | 空闲extent链表，segment申请extent时可以从这里取 |
| FSP_FREE_FRAG | 16 | 碎片extent链表，这些extent不属于任何一个segment |
| FSP_FULL_FRAG | 16 |  |
| FSP_SEG_ID | 8 | 8 bytes which give the first unused segment id |
| FSP_SEG_INODES_FULL | 16 | list of pages containing segment headers (segment inode节点页的链表) |
| FSP_SEG_INODES_FREE | 16 |  |
| (FSP_HEADER_SIZE) | 112 | (32 + 5 * FLST_BASE_NODE_SIZE) |


碎片区不属于任何一个segent，每个segment用碎片页数组保存了32个碎片页的信息，该碎片页就是从表空间的碎片区中申请的。这样做的目的是为了节省空间，一个segment可能最终只会用到几个页，当创建一个新的segment时，并不是立即申请一个完整的extent，而是先在表空间中申请32个碎片页，当页的数量超过32个时再申请一个extent。


### 表空间初始化（ `fsp_header_init(space_id, size, mtr)` ）

1. 使用表空间page_no=0的页作为fsp hdr page，设置其page类型为 `FIL_PAGE_TYPE_FSP_HDR` 
2. 初始化fsp hdr（FSP_SIZE=size, FSP_FREE_LIMIT=0）
3. 填充 `FSP_FREE` 链表（ `fsp_fill_free_list(init_space=!is_system_tablespace(space_id), ...)` ）
   1. 对于free limit之后未使用的页进行初始化
   2. 每个extent group的第0页作为xdes page（page_no=16384*N + 0，特例page_no=0时的页是fsp hdr页），类型为 `FIL_PAGE_TYPE_XDES` 
   3. 每个extent group的第1页（ `FSP_IBUF_BITMAP_OFFSET` ，starting from 0，page_no=16384*N + 1）作为ibuf bitmap page，初始化ibuf bitmap页，设置其page类型为 `FIL_PAGE_IBUF_BITMAP` （ `ibuf_bitmap_page_init(block, mtr)` ）
   4. 初始化该extent group的每个xdes结构
      1. 标记该extent group的第0和1页已经被使用（ `xdes_set_bit()` ）
      2. **标记该extent group的第0个extent为碎片区（ `xdes_set_state(descr, ``XDES_FREE_FRAG``, mtr)` ），并挂到 `FSP_FREE_FRAG` 链表中**
4. 对于系统表空间，创建ibuf btr（ `btr_create(type=DICT_CLUSTERED | DICT_IBUF, apace=0, ...)` ）
   1. 创建seg（ `fseg_create()` ），该步骤会调用 `fsp_alloc_seg_inode()` 分配inode，但是因为是第一次分配，需要分配inode page，此时分配的page_no=2（0和1页已经用于fsp hdr/xdes和ibuf bitmap）
   2. 指定分配page_no=4（ `FSP_IBUF_TREE_ROOT_PAGE_NO` ）的页作为 ibuf root page（block），page类型为 `FIL_PAGE_INDEX` （ `fseg_alloc_free_page(seg_header, ``hint=IBUF_TREE_ROOT_PAGE_NO``)` ）
   3. 初始化上一步分配的page，设置其类型为 `FIL_PAGE_INDEX` （ `page_create(block=block, ...)` ）

> TIPS：
> 1. fsp_header_init()之后，系统表空间的page_no=0、1、2、4页都已经分配作为固定用途了；实际上对于用户表空间，也会调用btr_create()函数进行页btr的创建，page_no=0、1、2页也会分配作为固定用途
> 2. 第3页（page_no=3）是ibuf header page，参考函数 `ibuf_add_free_page()` 
> 3. 其他固定用途的页参考下面的图



### 分配inode（ `fsp_alloc_seg_inode(space_header, ...)` ）

1. 如果 `FSP_SEG_INODES_FREE` 链表为空，分配一个新的inode page（ `fsp_alloc_seg_inode_page``(space_header)` ）
   1. 从表空间中分配一个碎片页（block）（ `fsp_alloc_free_page(hint=0)` ）作为inode page（ `FIL_PAGE_INODE` ），如果是第一次分配inode page，那么一定是分配的第2页（page_no=2）
   2. 初始化每个inode（ `fsp_seg_inode_page_get_nth_inode()` ）
   3. 把page加到 `FSP_SEG_INODES_FREE` 链表中
2. 从 `FSP_SEG_INODES_FREE` 中取出一个page
3. 从上一步取出的page中找到一个空闲的inode（ `fsp_seg_inode_page_find_free()` , `fsp_seg_inode_page_get_nth_inode()` ）
4. 如果该page已经没有空闲的inode了，从 `FSP_SEG_INODES_FREE` 链表中移动到 `FSP_SEG_INODES_FULL` 中


### 分配区（ `fsp_alloc_free_extent()` ）

### 分配碎片页（ `fsp_alloc_free_page()` -> `fsp_alloc_from_free_frag()` ）

### 申请新的区（ `fsp_fill_free_list()` ）

## File Overview
![image.png](https://cdn.nlark.com/yuque/0/2020/png/385742/1595672846129-8a7cea06-5db6-40b4-b080-06bffa2c6b20.png#align=left&display=inline&height=1551&originHeight=3102&originWidth=3562&size=680408&status=done&style=none&width=1781)

fsp的固定page定义：
```cpp
/** @name The space low address page map
The pages at FSP_XDES_OFFSET and FSP_IBUF_BITMAP_OFFSET are repeated
every XDES_DESCRIBED_PER_PAGE pages in every tablespace. */
/* @{ */
/*--------------------------------------*/
#define FSP_XDES_OFFSET			0	/* !< extent descriptor */
#define FSP_IBUF_BITMAP_OFFSET		1	/* !< insert buffer bitmap */
				/* The ibuf bitmap pages are the ones whose
				page number is the number above plus a
				multiple of XDES_DESCRIBED_PER_PAGE */

#define FSP_FIRST_INODE_PAGE_NO		2	/*!< in every tablespace */
				/* The following pages exist
				in the system tablespace (space 0). */
#define FSP_IBUF_HEADER_PAGE_NO		3	/*!< insert buffer
						header page, in
						tablespace 0 */
#define FSP_IBUF_TREE_ROOT_PAGE_NO	4	/*!< insert buffer
						B-tree root page in
						tablespace 0 */
				/* The ibuf tree root page number in
				tablespace 0; its fseg inode is on the page
				number FSP_FIRST_INODE_PAGE_NO */
#define FSP_TRX_SYS_PAGE_NO		5	/*!< transaction
						system header, in
						tablespace 0 */
#define	FSP_FIRST_RSEG_PAGE_NO		6	/*!< first rollback segment
						page, in tablespace 0 */
#define FSP_DICT_HDR_PAGE_NO		7	/*!< data dictionary header
						page, in tablespace 0 */
/*--------------------------------------*/
/* @} */
```

![image.png](https://cdn.nlark.com/yuque/0/2020/png/385742/1595583371018-2a9edbd3-f7a2-40b9-9f45-452bff3a87af.png#align=left&display=inline&height=2062&originHeight=2062&originWidth=2774&size=362831&status=done&style=none&width=2774)
**（fsp overview）**
![image.png](https://cdn.nlark.com/yuque/0/2020/png/385742/1595584180831-28dcfb51-6c18-4287-a79a-00a5f31f8f45.png#align=left&display=inline&height=2099&originHeight=2099&originWidth=2858&size=404873&status=done&style=none&width=2858)
**（系统表空间页分配）**
![image.png](https://cdn.nlark.com/yuque/0/2020/png/385742/1595584196163-ccb80ee7-282e-4992-8fc7-35c9e490e648.png#align=left&display=inline&height=1574&originHeight=1574&originWidth=2858&size=289822&status=done&style=none&width=2858)
**（用户表空间页分配）**
![image.png](https://cdn.nlark.com/yuque/0/2020/png/385742/1595611075492-6a64ba3e-4218-4c2a-af10-04823a96adb8.png#align=left&display=inline&height=2474&originHeight=2474&originWidth=2774&size=372372&status=done&style=none&width=2774)
**(Index Page)**

# 文件管理

