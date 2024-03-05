row模块是所有与外部接口的实现，handler最终都会调用该模块的一些接口，包括DML、undo、redo等；该模块调用dict、rec、btr、page等模块的接口实现其功能。

# Update/Delete
这里的delete指delete mark，真正物理记录的删除即purge操作不在此流程。

调用入口：
`row_update_for_mysql()` -> `row_update_for_mysql_using_upd_graph()` -> `row_upd_step()` -> `row_upd()` 

**upd_node**:
```cpp
/* Update node structure which also implements the delete operation
of a row */

struct upd_node_t{
	que_common_t	common;	/*!< node type: QUE_NODE_UPDATE */
	ibool		is_delete;/* TRUE if delete, FALSE if update */
	ibool		searched_update;
				/* TRUE if searched update, FALSE if
				positioned */
	ibool		in_mysql_interface;
				/* TRUE if the update node was created
				for the MySQL interface */
	dict_foreign_t*	foreign;/* NULL or pointer to a foreign key
				constraint if this update node is used in
				doing an ON DELETE or ON UPDATE operation */
    upd_node_t*     cascade_node;/* NULL or an update node template which
                                is used to implement ON DELETE/UPDATE CASCADE
                                or ... SET NULL for foreign keys */
	mem_heap_t*	cascade_heap;
				/*!< NULL or a mem heap where cascade
				node is created.*/
	sel_node_t*	select;	/*!< query graph subtree implementing a base
				table cursor: the rows returned will be
				updated */
	btr_pcur_t*	pcur;	/*!< persistent cursor placed on the clustered
				index record which should be updated or
				deleted; the cursor is stored in the graph
				of 'select' field above, except in the case
				of the MySQL interface */
	dict_table_t*	table;	/*!< table where updated */
	upd_t*		update;	/*!< update vector for the row */
	ulint		update_n_fields;
				/* when this struct is used to implement
				a cascade operation for foreign keys, we store
				here the size of the buffer allocated for use
				as the update vector */
	sym_node_list_t	columns;/* symbol table nodes for the columns
				to retrieve from the table */
	ibool		has_clust_rec_x_lock;
				/* TRUE if the select which retrieves the
				records to update already sets an x-lock on
				the clustered record; note that it must always
				set at least an s-lock */
	ulint		cmpl_info;/* information extracted during query
				compilation; speeds up execution:
				UPD_NODE_NO_ORD_CHANGE and
				UPD_NODE_NO_SIZE_CHANGE, ORed */
	/*----------------------*/
	/* Local storage for this graph node */
	ulint		state;	/*!< node execution state */
	dict_index_t*	index;	/*!< NULL, or the next index whose record should
				be updated */
    // 老记录，field和table对应
	dtuple_t*	row;	/*!< NULL, or a copy (also fields copied to
				heap) of the row to update; this must be reset
				to NULL after a successful update */
    // 老记录中ext field prefix (A: NULL; B: 3072)
	row_ext_t*	ext;	/*!< NULL, or prefixes of the externally
				stored columns in the old row */
    // 全量新rec的记录，field和table对应
	dtuple_t*	upd_row;/* NULL, or a copy of the updated row */
    // 新记录中作为ord_part的ext field prefix (A: 767; B: 3072)
	row_ext_t*	upd_ext;/* NULL, or prefixes of the externally
				stored columns in upd_row */
	mem_heap_t*	heap;	/*!< memory heap used as auxiliary storage;
				this must be emptied after a successful
				update */
	/*----------------------*/
	sym_node_t*	table_sym;/* table node in symbol table */
	que_node_t*	col_assign_list;
				/* column assignment list */
	ulint		magic_n;

};
```

**update vector**:
```cpp
/* Update vector structure */
struct upd_t{
	mem_heap_t*	heap;		/*!< heap from which memory allocated */
	ulint		info_bits;	/*!< new value of info bits to record;
					default is 0 */
	dtuple_t*	old_vrow;	/*!< pointer to old row, used for
					virtual column update now */
	ulint		n_fields;	/*!< number of update fields */
	upd_field_t*	fields;		/*!< array of update fields */
};

/* Update vector field */
struct upd_field_t{
	unsigned	field_no:16;	/*!< field number in an index, usually
					the clustered index, but in updating
					a secondary index record in btr0cur.cc
					this is the position in the secondary
					index. If this field is a virtual
					column, then field_no represents
					the nth virtual	column in the table */
#ifndef UNIV_HOTBACKUP
	unsigned	orig_len:16;	/*!< original length of the locally
					stored part of an externally stored
					column, or 0 */
	que_node_t*	exp;		/*!< expression for calculating a new
					value: it refers to column values and
					constants in the symbol table of the
					query graph */
#endif /* !UNIV_HOTBACKUP */
	dfield_t	new_val;	/*!< new value for the column */
	dfield_t*	old_v_val;	/*!< old value for the virtual column */
};
```

**node_state**：
```cpp
/* Node execution states */
#define UPD_NODE_SET_IX_LOCK	   1	/* execution came to the node from
					a node above and if the field
					has_clust_rec_x_lock is FALSE, we
					should set an intention x-lock on
					the table */
#define UPD_NODE_UPDATE_CLUSTERED  2	/* clustered index record should be
					updated */
#define UPD_NODE_INSERT_CLUSTERED  3	/* clustered index record should be
					inserted, old record is already delete
					marked */
#define UPD_NODE_UPDATE_ALL_SEC	   5	/* an ordering field of the clustered
					index record was changed, or this is
					a delete operation: should update
					all the secondary index records */
#define UPD_NODE_UPDATE_SOME_SEC   6	/* secondary index entries should be
					looked at and updated if an ordering
					field changed */
```
upd_node的初始state是 `UPD_NODE_UPDATE_CLUSTERED` 。


**row_upd_clust_step()**

- 如果是delete `SYS_INDEXES` 表的数据，需要删除对应index的b-tree ( `dict_drop_index_tree()` )
- **if delete** ( `node->is_delete` ): delete mark ( `row_upd_del_mark_clust_rec()` ), state = `UPD_NODE_UPDATE_ALL_SEC` , index = dict_table_get_next_index(index)
- 初始化新老记录信息（ `node->row` / `node->ext` / `node->upd_row` / `node->upd_ext` ） ( `row_upd_store_row()` )
- **if change ordering field **( `row_upd_changes_ord_field_binary()` )**:** delete-mark and insert ( `row_upd_clust_rec_by_insert()` ), state = `UPD_NODE_UPDATE_ALL_SEC` 
- **else**: update ( `row_upd_clust_rec()` ), state = `UPD_NODE_UPDATE_SOME_SEC` 

> Q: 对于change ordering field的update，为什么需要delete-mark而不是直接delete？
> A: delete-mark可以在MVCC时搜索到这条记录，直接delete后就不能通过b-tree搜索到这条记录了


**row_upd_del_mark_clust_rec()**

1. Store row because we have to build also the secondary index entries ( `row_upd_store_row()` )
2. Mark the clustered index record deleted; we do not have to check locks, because we assume that we have an x-lock on the record ( `btr_cur_del_mark_set_clust_rec()` )
   1. undo ( `trx_undo_report_row_operation()` )
   2. set delete flag: `btr_rec_set_deleted_flag()` -> `rec_set_deleted_flag_new()` / `rec_set_deleted_flag_old()` 
   3. if online ddl: row log, `row_log_table_delete()` 
   4. update system field: trx_id and roll_ptr, `row_upd_rec_sys_fields()` 
   5. redo: `btr_cur_del_mark_set_clust_rec_log()` 


**row_upd_clust_rec_by_insert()**

1. 根据 `node->upd_row` 和 `node->upd_ext` 生成index entry(dtuple_t) ( `row_build_index_entry_low()` )
2. 第1次进该函数时， `state == UPD_NODE_UPDATE_CLUSTERED` 
   1. 执行`btr_cur_del_mark_set_clust_rec()` 
   2. If the the new row inherits externally stored fields (off-page columns a.k.a. BLOBs) from the delete-marked old record, mark them disowned by the old record and owned by the new entry. `row_upd_clust_rec_by_insert_inherit()` , `btr_cur_disown_inherited_fields()` （防止offpage被purge）
3. 第2次进该函数时， `state == UPD_NODE_INSERT_CLUSTERED` ，因此执行 `row_upd_clust_rec_by_insert_inherit()`
4. insert: `row_ins_clust_index_entry()` 
5. set `node->state = UPD_NODE_INSERT_CLUSTERED` 


**row_upd_clust_rec()**
// todo


**row_upd_store_row()**

1. 初始化老记录Local storage： `node->row` 和 `node->ext` ( `row_build()` )
   1. rec非溢出数据部分数据保存到 `node->row` 中；
   2. ext field的prefix（所有ext字段，包括ord_part和非ord_part）
      1. Antelope格式，`node->ext = NULL` (REDUNDANT and COMPACT formats store a local 768-byte prefix of each externally stored column. No cache is needed.)
      2. Barracuda格式，copy前到3072字节数据到 `node->ext` 中 ( `row_ext_create()` )
2. 初始化新记录Local storage：`node->upd_row` 和 `node->upd_ext` 
   1. delete: `node->upd_row = NULL`  , `node->upd_ext = NULL`
   2. else: 
      1. 根据 `node->update` 信息更新 `node->upd_row` ，并记录更新后的新记录中作为某个index的ord_part且是ext的clumn的ind到ext_cols( `row_upd_replace()` )
      2. 根据上一步记录的ext_cols信息生成 `node->upd_ext` ，注意 `node->upd_ext` 只有作为ord_part的columns ( `row_ext_create()`)
         1. Antelope格式，copy前767字节数据
         2. Barracuda格式，copy前3072字节数据
> **TIPS**
> 新记录中是ord_part且是ext的col可能是这次update引入的也可能本来就是ext field，innodb保证了在该index中作为ord的field不会有溢出数据，但是可能该column在其他index中是ord field，在clust index中不是ord field是ext field


Q: 为什么是767和3072字节？
A: InnoDB限制了所有索引字段的最大长度之和为767和3072字节
> If innodb_large_prefix is enabled (the default), the index key prefix limit is 3072 bytes for InnoDB tables that use the DYNAMIC or COMPRESSED row format. If innodb_large_prefix is disabled, the index key prefix limit is 767 bytes for tables of any row format.
> 
> innodb_large_prefix is deprecated and will be removed in a future release. innodb_large_prefix was introduced in MySQL 5.5 to disable large index key prefixes for compatibility with earlier versions of InnoDB that do not support large index key prefixes.

> 

> The index key prefix length limit is 767 bytes for InnoDB tables that use the REDUNDANT or COMPACT row format. For example, you might hit this limit with a column prefix index of more than 255 characters on a TEXT or VARCHAR column, assuming a utf8mb3 character set and the maximum of 3 bytes for each character.

> 

> Attempting to use an index key prefix length that exceeds the limit returns an error. To avoid such errors in replication configurations, avoid enabling innodb_large_prefix on the source if it cannot also be enabled on replicas.

> 

> If you reduce the InnoDB page size to 8KB or 4KB by specifying the innodb_page_size option when creating the MySQL instance, the maximum length of the index key is lowered proportionally, based on the limit of 3072 bytes for a 16KB page size. That is, the maximum index key length is 1536 bytes when the page size is 8KB, and 768 bytes when the page size is 4KB.

> 

> The limits that apply to index key prefixes also apply to full-column index keys.
> 
> ref: [https://dev.mysql.com/doc/refman/5.7/en/innodb-limits.html](https://dev.mysql.com/doc/refman/5.7/en/innodb-limits.html)


**row_build()**** : ****cl****ustered index rec => table dtuple + ext**

1. 读取 clustered index rec ( `rec_t` )生成 row ( `dtuple_t` )，生成row的field与table columns 对应；同时记录ext字段在index中的的ind到 `ext_cols` 中
2. 根据上一步返回的ext_cols ind信息，取出所有对应ext字段 `row_ext_t::max_len` 长度的数据到 `row_ext_t::buf` 中并返回 (`row_ext_create()` -> `row_ext_cache_fill()` -> `btr_copy_externally_stored_field_prefix()` )

其中max_len的长度由 `DICT_MAX_FIELD_LEN_BY_FORMAT_FLAG(flags)` 计算:

   1. For ROW_FORMAT=REDUNDANT and ROW_FORMAT=COMPACT, the maximum field length is `REC_ANTELOPE_MAX_INDEX_COL_LEN - 1`  (767). 
   2. For Barracuda row formats COMPRESSED and DYNAMIC, the length could be `REC_VERSION_56_MAX_INDEX_COL_LEN`  (3072) bytes


**row_build_index_entry()**** : ****table dtuple + ext => index(clust or sec) dtuple**

1. 根据index->n_fields和table->n_v_cols创建对应的entry (dtuple_t)
2. 遍历每个entry，得到对应的node->upd_row中的field
3. copy数据

> The dfield_copy() above suffices for columns that are stored in-page, or for
> clustered index record columns that are not part of a column prefix in the PRIMARY KEY, or > for virtaul columns in cluster index record.> 

> 

If the column is stored externally (off-page) in the clustered index, it must be an ordering field in the secondary index.  > In the Antelope format, only prefix-indexed columns may be stored off-page in the clustered index record. > In the Barracuda format, also fully indexed long CHAR or VARCHAR columns may be stored off-page.


**upd_node_t Local storage**

- `upd_node_t::row` ：老记录的逻辑记录(dtuple_t)，field与 `dict_table_t::cols` 对应
- `upd_node_t::ext` ：老记录的ext field的prefix，A: NULL; B: 3072 bytes
- `upd_node_t::upd_row` ：新记录的全量逻辑记录（dtuple_t）
- `upd_node_t::upd_ext` ：新记录中是某个index的ord_part且是ext的field的prefix，A: 767; B: 3072 bytes


> **TIPS：**
> **根据clust index的field找到table的column信息流程：**
> 1. `dict_field_t*   ind_field = dict_index_get_nth_field(index, i);` 
> 2. `dict_col_t*     col       = dict_field_get_col(ind_field);` 
> 3. `ulint           col_no    = dict_col_get_no(col);`  // 该index field对应的col在table定义中的idx
> 4. `dict_col_t*     col       = dict_table_get_nth_col(col_table, col_no);` 
> ****
根据table的column ind找到clust index field信息流程：**> 1. `dict_col_t*	col       = dict_table_get_nth_col(table, col_no)` 
> 2. `ulint         clust_pos = dict_col_get_clust_pos(col, index)` // 遍历clust index的field，直到找到field->col == col的field为止
> 3. 略



**BTR_EXTERN_FIELD**
```c
/** The reference in a field for which data is stored on a different page.
The reference is at the end of the 'locally' stored part of the field.
'Locally' means storage in the index record.
We store locally a long enough prefix of each column so that we can determine
the ordering parts of each index record without looking into the externally
stored part. */
/*-------------------------------------- @{ */
#define BTR_EXTERN_SPACE_ID		0	/*!< space id where stored */
#define BTR_EXTERN_PAGE_NO		4	/*!< page no where stored */
#define BTR_EXTERN_OFFSET		8	/*!< offset of BLOB header
						on that page */
#define BTR_EXTERN_LEN			12	/*!< 8 bytes containing the
						length of the externally
						stored part of the BLOB.
						The 2 highest bits are
						reserved to the flags below. */
/*-------------------------------------- @} */
/* #define BTR_EXTERN_FIELD_REF_SIZE	20 // moved to btr0types.h */

/** The most significant bit of BTR_EXTERN_LEN (i.e., the most
significant bit of the byte at smallest address) is set to 1 if this
field does not 'own' the externally stored field; only the owner field
is allowed to free the field in purge! */
#define BTR_EXTERN_OWNER_FLAG		128
/** If the second most significant bit of BTR_EXTERN_LEN (i.e., the
second most significant bit of the byte at smallest address) is 1 then
it means that the externally stored field was inherited from an
earlier version of the row.  In rollback we are not allowed to free an
inherited external field. */
#define BTR_EXTERN_INHERITED_FLAG	64
```

**row_ext_t**
```cpp
/** Prefixes of externally stored columns */
struct row_ext_t{
	ulint		n_ext;	/*!< number of externally stored columns */
	const ulint*	ext;	/*!< col_no's of externally stored columns */
	byte*		buf;	/*!< backing store of the column prefix cache */
	ulint		max_len;/*!< maximum prefix length, it could be
				REC_ANTELOPE_MAX_INDEX_COL_LEN or
				REC_VERSION_56_MAX_INDEX_COL_LEN depending
				on row format */
	page_size_t	page_size;
				/*!< page size of the externally stored
				columns */
	ulint		len[1];	/*!< prefix lengths; 0 if not cached */
};
```


# Insert

# Lock

# DML与Online DDL
