crash recovery的起点，checkpoint_lsn存于何处？
redo过程是batch redo，还是single redo？如果是batch redo，那么是如何实现的？
redo过程中是否需要读取所有数据文件？
undo操作的起点是什么？
如何找到每个rollback segment中的undo信息？
事务与undo是如何关联起来的？
同一事务的undo，是如何链接起来的？

怎么判断是否需要recovery
需要恢复什么？恢复要达到什么目的？
redo、undo和data page怎么对应起来？
如何恢复事务表？
怎么判断哪些事物需要commit哪些事物需要rollback？
DDL过程中crash怎么办？

在恢复的过程中又crash了怎么办？

1、为什么redo文件要有两个checkpoint
2、为什么回滚事物可以后台进行
3、未知后台线程？
4.  binlog和redolog两阶段提交是怎么做的？


# 预备知识
## redo log
### redo log buffer/redolog block
![image.png](https://cdn.nlark.com/yuque/0/2019/png/385742/1573647940899-d895ba2d-bc11-4a8c-9b5d-6aa7f08b2b34.png#align=left&display=inline&height=526&originHeight=1052&originWidth=2078&size=403771&status=done&style=none&width=1039)

### redo log file
![image.png](https://cdn.nlark.com/yuque/0/2019/png/385742/1573647972206-b42548c3-d550-459c-8b03-d94e73fc9b19.png#align=left&display=inline&height=273&originHeight=546&originWidth=1994&size=202308&status=done&style=none&width=997)
redo log 以log block为单位组织，每个block 512字节，格式如上节所示，一个mlog可能跨越多个block。

### redo log file header and checkpoint
![image.png](https://cdn.nlark.com/yuque/0/2019/png/385742/1573578590609-fe0909ea-5462-44f8-88d6-b20a5b3f2937.png#align=left&display=inline&height=203&originHeight=574&originWidth=1482&size=270417&status=done&style=none&width=524)
![image.png](https://cdn.nlark.com/yuque/0/2019/png/385742/1573578615406-74f17c2a-de8e-4af7-b41d-23199d03e03f.png#align=left&display=inline&height=371&originHeight=742&originWidth=2432&size=510770&status=done&style=none&width=1216)
![image.png](https://cdn.nlark.com/yuque/0/2019/png/385742/1573578628951-6c1427ff-72d3-4337-a55f-3b9876c5a38b.png#align=left&display=inline&height=633&originHeight=1266&originWidth=2406&size=1118492&status=done&style=none&width=1203)
两个checkpoint轮流写

### redo log 格式
![image.png](https://cdn.nlark.com/yuque/0/2019/png/385742/1573647995088-e30eed32-fa33-4839-9123-3abb73e00105.png#align=left&display=inline&height=276&originHeight=552&originWidth=2128&size=177508&status=done&style=none&width=1064)

## undo
undo 以回滚段的方式组织，每个回滚段又包含多个page。每个回滚段维护了一个段头页，在该page中又划分了1024个slot(TRX_RSEG_N_SLOTS)，每个slot又对应到一个undo log对象，因此理论上InnoDB最多支持 96 * 1024个普通事务。

- 事务开启时，会专门给他指定一个回滚段，以后该事务用到的undo log页，就从该回滚段上分配;
- 事务提交后，需要purge的回滚段会被放到purge队列上(purge_sys->purge_queue)。
### undo header page
![image.png](https://cdn.nlark.com/yuque/0/2019/png/385742/1573661617864-00f9f17b-bf7a-4ffa-8602-25b64a0577c6.png#align=left&display=inline&height=486&originHeight=632&originWidth=893&size=68281&status=done&style=none&width=686)

### undo 格式
![image.png](https://cdn.nlark.com/yuque/0/2019/png/385742/1574083854581-7b7abcc1-ec51-4357-9765-f634e3929183.png#align=left&display=inline&height=385&originHeight=383&originWidth=312&size=20143&status=done&style=none&width=314)
![image.png](https://cdn.nlark.com/yuque/0/2019/png/385742/1574083864052-208204f7-8c6d-4d35-9007-6ee2dd3e23a4.png#align=left&display=inline&height=464&originHeight=673&originWidth=716&size=97221&status=done&style=none&width=494)


**事物prepare**
为了在崩溃重启时知道事务状态，需要将事务设置为Prepare。分别设置insert undo 和 update undo的状态为prepare，调用函数trx_undo_set_state_at_prepare，过程也比较简单，找到undo log slot对应的头页面(trx_undo_t::hdr_page_no)，将页面段头的TRX_UNDO_STATE设置为TRX_UNDO_PREPARED。

```cpp
// trx0undo.h
//
/* States of an undo log segment */
#define TRX_UNDO_ACTIVE		1	/* contains an undo log of an active
					transaction */
#define	TRX_UNDO_CACHED		2	/* cached for quick reuse */
#define	TRX_UNDO_TO_FREE	3	/* insert undo segment can be freed */
#define	TRX_UNDO_TO_PURGE	4	/* update undo segment will not be
					reused: it can be freed in purge when
					all undo data in it is removed */
#define	TRX_UNDO_PREPARED	5	/* contains an undo log of an
					prepared transaction */
```

> InnoDB层的XID是如何获取的呢？ 当Innodb的参数innodb_support_xa打开时，在执行事务的第一条SQL时，就会去注册XA，根据第一条SQL的query id拼凑XID数据，然后存储在事务对象中。参考函数`trans_register_ha`。


**事物commit**

- 如果当前的undo log只占一个page，且占用的header page大小使用不足其3/4时(TRX_UNDO_PAGE_REUSE_LIMIT)，则状态设置为_TRX_UNDO_CACHED_，该undo对象会随后加入到undo cache list上；
- 如果是_Insert_undo_（undo类型为TRX_UNDO_INSERT），则状态设置为_TRX_UNDO_TO_FREE_；
- 如果不满足a和b，则表明该undo可能需要Purge线程去执行清理操作，状态设置为_TRX_UNDO_TO_PURGE_。

# crash recovery
当正常shutdown实例时，会将所有的脏页都刷到磁盘，并做一次完全同步的checkpoint；同时将最后的lsn写到系统表ibdata的第一个page中（函数fil_write_flushed_lsn）。在重启时，可以根据该lsn来判断这是不是一次正常的shutdown，如果不是就需要去做崩溃恢复逻辑。

checkpoint信息被写入到了第一个iblogfile的头部，但写入的文件偏移位置比较有意思，当log_sys->next_checkpoint_no为奇数时，写入到LOG_CHECKPOINT_2（3 *512字节）位置，为偶数时，写入到LOG_CHECKPOINT_1（512字节）位置。

```cpp
#define LOG_CHECKPOINT_1	OS_FILE_LOG_BLOCK_SIZE
					/* first checkpoint field in the log
					header; we write alternately to the
					checkpoint fields when we make new
					checkpoints; this field is only defined
					in the first log file of a log group */
#define LOG_CHECKPOINT_2	(3 * OS_FILE_LOG_BLOCK_SIZE)
					/* second checkpoint field in the log
					header */
```


当实例从崩溃中恢复时，需要将活跃的事务从undo中提取出来，对于ACTIVE状态的事务直接回滚，对于Prepare状态的事务，如果该事务对应的binlog已经记录，则提交，否则回滚事务。


源码位置:
srv/srv0start.cc
log/log0log.cc
log/log0recv.cc
fsp/fsp0sysspace.cc


重要函数：

1. `innobase_start_or_create_for_mysql` ：入口，不只是恢复逻辑

首先初始化崩溃恢复所需要的内存对象
`recv_sys_create()` ;
`recv_sys_init(buf_pool_get_curr_size())` ;

打开系统表空间ibdata，并读取存储在其中的LSN，保存到flushed_lsn中
 `err = srv_sys_space.open_or_create(false, create_new_db, &sum_of_new_sizes, &flushed_lsn);` 

```cpp
	if (!create_new_db && flush_lsn) {
		/* Validate the header page in the first datafile
		and read LSNs fom the others. */
		err = read_lsn_and_check_flags(flush_lsn);
		if (err != DB_SUCCESS) {
			return(err);
		}
	}
```

另外这里也会将double write buffer内存储的page载入到内存中(`buf_dblwr_init_or_load_pages`)，如果ibdata的第一个page损坏了，就从dblwr中恢复出来。
`buf_dblwr_init_or_load_pages(it->handle(), it->filepath());` 


 	/* We always try to do a recovery, even if the database had
 been shut down normally: this is the normal startup path */

 `err = recv_recovery_from_checkpoint_start(flushed_lsn);` 

```cpp
// log0log.h
/* Offsets inside the checkpoint pages (redo log format version 1) */
#define LOG_CHECKPOINT_NO		0
#define LOG_CHECKPOINT_LSN		8
#define LOG_CHECKPOINT_OFFSET		16
#define LOG_CHECKPOINT_LOG_BUF_SIZE	24


// log0recv.cc
/** Start recovering from a redo log checkpoint.
@see recv_recovery_from_checkpoint_finish
@param[in]	flush_lsn	FIL_PAGE_FILE_FLUSH_LSN
of first system tablespace page
@return error code or DB_SUCCESS */
dberr_t
recv_recovery_from_checkpoint_start(
	lsn_t	flush_lsn)
{
    // ... ...
    // 在第一个redo log的头中找到最新的checkpoint（有两个checkpoint轮流写）
    // 找最新的checkpoint的方法是比较checkpoint_no，找到大的那一个
	/* Look for the latest checkpoint from any of the log groups */
	err = recv_find_max_checkpoint(&max_cp_group, &max_cp_field);

	if (err != DB_SUCCESS) {
		log_mutex_exit();
		return(err);
	}

    // 把checkpoint读到log_sys->checkpoint_buf中，读OS_FILE_LOG_BLOCK_SIZE(512)字节
    // 实际上在recv_find_max_checkpoint中已经多次把数据读到了log_sys->checkpoint_buf, 
    // 但是函数返回时log_sys->checkpoint_buf钟保存的是最后一次读取的数据，并不是最大的checkpoint
	log_group_header_read(max_cp_group, max_cp_field);

	buf = log_sys->checkpoint_buf;

    // 读出checkpoint_no和checkpoint_lsn
	checkpoint_lsn = mach_read_from_8(buf + LOG_CHECKPOINT_LSN);
	checkpoint_no = mach_read_from_8(buf + LOG_CHECKPOINT_NO);
    
    // ... ...
    /** Scan the redo log from checkpoint lsn and redo log to
	the hash table. */
	rescan = recv_group_scan_log_recs(group, &contiguous_lsn, false);
}
```

1. 为每个buffer pool instance创建一棵红黑树，指向buffer_pool_t::flush_rbt，主要用于加速插入flush list ( `buf_flush_init_flush_rbt` )；
2. 读取存储在第一个redo log文件头的CHECKPOINT LSN，并根据该LSN定位到redo日志文件中对应的位置，从该checkpoint点开始扫描。

`recv_group_scan_log_recs` 扫描redo log的函数

`recv_group_scan_log_recs` -> `recv_scan_log_recs` 

```cpp
	do {
		if (last_phase && store_to_hash == STORE_NO) {
			store_to_hash = STORE_IF_EXISTS;
			/* We must not allow change buffer
			merge here, because it would generate
			redo log records before we have
			finished the redo log scan. */
			recv_apply_hashed_log_recs(FALSE);
		}

		start_lsn = end_lsn;
		end_lsn += RECV_SCAN_SIZE;

		log_group_read_log_seg(
			log_sys->buf, group, start_lsn, end_lsn);
	} while (!recv_scan_log_recs(
			 available_mem, &store_to_hash, log_sys->buf,
			 RECV_SCAN_SIZE,
			 checkpoint_lsn,
			 start_lsn, contiguous_lsn, &group->scanned_lsn));
```

`trx_sys_init_at_db_start` 初始化事物子系统

`trx_lists_init_at_db_start` 


流程
`innobase_start_or_create_for_mysql` 恢复入口函数

1. 初始化一些内存对象
2. 打开系统表空间 `ibdata` ，并读取存储在其中的LSN
> 当正常shutdown实例时，会将所有的脏页都刷到磁盘，并做一次完全同步的checkpoint；同时将最后的lsn写到系统表ibdata的第一个page中（函数fil_write_flushed_lsn）。在重启时，可以根据该lsn来判断这是不是一次正常的shutdown，如果不是就需要去做崩溃恢复逻辑。

3. 进入崩溃恢复逻辑（ `recv_recovery_from_checkpoint_start` ）
   - **扫描redo并解析**（ `recv_group_scan_log_recs` ）：从checkpoint_lsn开始扫描redo，按照数据页的 `space_id` 和 `page_no` 分发redo日志到 `hash_table` 中，保证同一个数据页的日志被分发到同一个哈希桶中，且按照lsn大小从小到大排序。
> checkpoint_lsn之前的数据页都已经落盘，不需要前滚，之后的数据页可能还没落盘，需要重新恢复出来，即使已经落盘也没关系，因为redo日志是幂等的，应用一次和应用两次都一样(底层实现: 如果数据页上的lsn大于等于当前redo日志的lsn，就不应用，否则应用。

扫描的过程中，会基于MLOG_FILE_NAME 和MLOG_FILE_DELETE 这样的redo日志记录来构建recv_spaces，存储space id到文件信息的映射（fil_name_parse –> fil_name_process），这些文件可能需要进行崩溃恢复。
> 在5.7之前，需要打开所有表空间，数据库之所以要打开所有的表，是因为在分发日志的时候，需要确定space_id对应哪个ibd文件，通过打开所有的表，读取space_id信息来确定。
> 针对这个表数量过多导致恢复过慢的问题，MySQL 5.7做了优化，WL#7142，。在一次checkpoint后第一次修改某个表的数据时，总是先写一条MLOG_FILE_NAME 日志记录（包括space_id和filename的映射）；通过该类型的日志可以跟踪一次CHECKPOINT后修改过的表空间，避免打开全部表。


对不同redo的处理（ `recv_parse_or_apply_log_rec_body` ）：
例如如果解析到的日志类型为MLOG_UNDO_HDR_CREATE，就会从日志中解析出事务ID，为其重建undo log头（trx_undo_parse_page_header）；如果是一条插入操作标识（MLOG_REC_INSERT 或者 MLOG_COMP_REC_INSERT），就需要从中解析出索引信息（mlog_parse_index）和记录信息（page_cur_parse_insert_rec）；或者解析一条IN-PLACE UPDATE (MLOG_REC_UPDATE_IN_PLACE)日志，则调用函数btr_cur_parse_update_in_place。

   - **应用日志**（ `recv_apply_hashed_log_recs` ）

遍历hash_table，从磁盘读取对每个数据页，依次应用哈希桶中的日志。应用完所有的日志后，如果需要则把buffer_pool的页面都刷盘，毕竟空间有限。
只应用redo日志lsn大于page_lsn的日志，只有这些日志需要重做，其余的忽略。应用完日志后，把脏页加入脏页列表，由于脏页列表是按照最老修改lsn(oldest_modification)来排序的，这里通过引入一颗红黑树来加速查找插入的位置，时间复杂度从之前的线性查找降为对数级别。
执行完了redo前滚数据库，数据库的所有数据页已经处于一致的状态，undo回滚数据库就可以安全的执行了。数据库崩溃的时候可能有一些没有提交的事务或者已经提交的事务，这个时候就需要决定是否提交。主要分为三步，首先是扫描undo日志，重新建立起undo日志链表，接着是，依据上一步建立起的链表，重建崩溃前的事务，即恢复当时事务的状态。最后，就是依据事务的不同状态，进行回滚或者提交。
> _在恢复数据页的过程中不产生新的redo 日志_；


   - **初始化事物子系统**（ `trx_sys_init_at_db_start` ）

在初始化回滚段的时候，我们通过读入回滚段页并进行redo log apply，就可以将回滚段信息恢复到一致的状态，从而能够 “复活”在系统崩溃时活跃的事务，维护到读写事务链表中。对于处于prepare状态的事务，我们后续需要做额外处理

   1. 在内存中建立起了undo_insert_list和undo_update_list(链表每个undo segment独立)
   2. 遍历所有链表，重建起事务的状态(trx_resurrect_insert和trx_resurrect_update)
   3. 回滚所有active状态的事物（这一步是后台线程处理的）
> _因此我们常常在会发现数据库已经启动起来了，然后错误日志中还在不断的打印回滚事务的信息。事务回滚的核心函数是_`_trx_rollback_or_clean_recovered_`_，逻辑很简单，只需要遍历trx_sys->trx_list，按照事务不同的状态回滚或者提交即可(_`_trx_rollback_resurrected_`_)。_


   - 处理prepare状态的事物

如果事务是TRX_STATE_PREPARED状态，那么在InnoDB层，不做处理，需要在Server层依据binlog的情况来决定是否回滚事务，如果binlog已经写了，事务就提交，因为binlog写了就可能被传到备库，如果主库回滚会导致主备数据不一致，如果binlog没有写，就回滚事务。
首先扫描最后一个binlog文件，找到其中所有的XID事件，并将其中的XID记录到一个hash结构中（MYSQL_BIN_LOG::recover）；然后对每个引擎调用接口函数xarecover_handlerton, 拿到每个事务引擎中处于prepare状态的事务xid，如果这个xid存在于binlog中，则提交；否则回滚事务。

Links:

1. InnoDB Crash Recovery: [http://hedengcheng.com/?p=183](http://hedengcheng.com/?p=183)
2. MySQL InnoDB Update和Crash Recovery流程: [https://cloud.tencent.com/developer/article/1072722](https://cloud.tencent.com/developer/article/1072722)
3. MySQL · 引擎特性 · InnoDB 崩溃恢复过程： [http://mysql.taobao.org/monthly/2015/06/01/](http://mysql.taobao.org/monthly/2015/06/01/)
4. MySQL · 引擎特性 · InnoDB崩溃恢复： [http://mysql.taobao.org/monthly/2017/07/01/](http://mysql.taobao.org/monthly/2017/07/01/)
5. InnoDB 崩溃恢复机制: [https://www.jiqizhixin.com/articles/2018-12-06-19](https://www.jiqizhixin.com/articles/2018-12-06-19)
6. MySQL崩溃恢复功臣—Redo Log: [https://cloud.tencent.com/developer/article/1417482](https://cloud.tencent.com/developer/article/1417482)
7. MySQL · 引擎特性 · InnoDB 事务子系统介绍: [http://mysql.taobao.org/monthly/2015/12/01/](http://mysql.taobao.org/monthly/2015/12/01/)

