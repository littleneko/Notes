一些问题以及困惑

1. buffer pool中脏页如何管理
2. 什么情况下会刷脏
3. 刷脏和redolog checkpoint之间有什么关系
4. 一个修改过的页怎么才算脏页，事物结束后？即脏页什么时候加入到flush_list中？MTR结束
5. flush脏页时，如果该页对应的redo log还没有写回磁盘，怎么处理？分为两种情况，事物已提交( `innodb_flush_log_at_trx_commit` 参数影响)和事物未提交。日志先行，一定要先刷redo
6. 未提交事物的脏页能不能刷盘？可以
7. 刷邻居脏页的时候相当与会把flush_list中间某些页刷掉？
8. ... ...


![buf_pool_t.svg](https://cdn.nlark.com/yuque/0/2019/svg/385742/1562864969227-fb084fcf-5eb9-4593-9ab7-90eea8bb5a84.svg#align=left&display=inline&height=1134&originHeight=1134&originWidth=718&size=90152&status=done&width=718)

**mysql flush dirty page的演进**
5.6版本以前，脏页的清理工作交由master线程的；Page cleaner thread是5.6.2引入的一个新线程，它实现从master线程中卸下缓冲池刷脏页的工作；为了进一步提升扩展性和刷脏效率，在5.7.4版本里引入了多个page cleaner线程，从而达到并行刷脏的效果。目前Page cleaner并未和缓冲池绑定，有一个协调线程 和 多个工作线程，协调线程本身也是工作线程。工作队列长度为缓冲池实例的个数，使用一个全局slot数组表示。

**刷脏的总流程**

1. 协调线程计算需要刷脏的数量n_min和lsn_limit(oldest_modification)
2. 协调县城唤醒工作线程开始刷脏（同时协调线程也参与刷脏）
3. 工作线程遍历slots找到一个处于PAGE_CLEANER_STATE_REQUESTED状态的slot，并修改成PAGE_CLEANER_STATE_FLUSHING。如果没有找到跳转到6
4. 工作线程对该slot刷脏
   1. 刷LRU
   2. 刷FLU
      1. 从尾部开始遍历flush_list找到一个page，并找到该page的邻居（innodb_flush_neighbors控制）
      2. 开始刷脏，直到刷脏数量大于等于n_min或lsn_limit不符合
5. 跳转到3
6. 工作线程判断自己是不是最后一个刷脏完成的线程
   1. 不是，结束
   2. 是，唤醒协调线程
7. 协调线程做一些后续的工作

**什么时候会刷脏**

1. 每秒一次的刷脏
2. buf_pool没有足够的free页，并且也没有LRU可以淘汰
3. redolog没有足够的空间需要checkpoint
4. mysql关闭的时候

**刷脏数量没n_min和lsn_limit如何计算**
实际上这两个值用来控制刷脏页的速度，考虑到两个因素，redolog写盘速度和脏页生成速度。
**
函数 `page_cleaner_flush_pages_recommendation` 用于计算这两个值，其中两个重要的函数是 `af_get_pct_for_dirty` 和 `af_get_pct_for_lsn` ，这两个函数分别用于计算这两个值。

相关的参数

- innodb_io_capacity
- innodb_max_dirty_pages_pct

```c
F1(M)
{
  if M>=innodb_max_dirty_pages_pct then
      return 100;
  return 100*M/innodb_max_dirty_pages_pct;
}
```

InnoDB 每次写入的日志都有一个序号，当前写入的序号跟 checkpoint 对应的序号之间的差值，我们假设为 N。InnoDB 会根据这个 N 算出一个范围在 0 到 100 之间的数字，这个计算公式可以记为 F2(N)。F2(N) 算法比较复杂，你只要知道 N 越大，算出来的值越大就好了。

然后，根据上述算得的 F1(M) 和 F2(N) 两个值，取其中较大的值记为 R，之后引擎就可以按照 innodb_io_capacity 定义的能力乘以 R% 来控制刷脏页的速度。
**
**为什么buf_pool_t中的flush_list是以oldest_modification排序的**
一个数据页可能会在不同的时刻被修改多次，在数据页上记录了最老(也就是第一次)的一次修改的lsn，即oldest_modification。不同数据页有不同的oldest_modification，FLU List中的节点按照oldest_modification排序，链表尾是最小的，也就是最早被修改的数据页，当需要从FLU List中淘汰页面时候，从链表尾部开始淘汰。

checkpoint是取所有flush_list中最后一个节点的oldest_modification最小值。

如果不以oldest_modification排序，而是以newest_modification排序可能造成崩溃恢复出错。
比如 A B C 三个页，以newest_modification排序:
C[new: 150, old: 150] <-> B[new: 140, old: 100] <-> A[new: 130, old: 120]
如果数据页A被刷入磁盘，然后checkpoint被更新为120，但是数据页B和C都还没被刷入磁盘，这个时候，数据库crash，重启后，从checkpoint为120开始扫描日志，然后恢复数据，我们会发现，数据页C的修改被恢复了，但是数据页B的修改丢失了。
为什么不以newest_modification作为checkpoint点？

**协调线程3种刷脏策略**

1. 同步：1s sleep被打断，尽可能多刷脏，lsn_limit由唤醒线程设定
2. 活跃：正常计算刷脏数
3. 空闲：尽可能多刷脏，n_min和lsn_limit都不限制

**未提交事物能否刷盘**
看起来应该是可以

先介绍一下buf_page_t中buf_fix_count和io_fix两个变量，这两个变量主要用来做并发控制，减少mutex加锁的范围。当从buffer pool读取一个数据页时候，会其加读锁，然后递增buf_page_t::buf_fix_count，同时设置buf_page_t::io_fix为BUF_IO_READ，然后即可以释放读锁。后续如果其他线程在驱逐数据页(或者刷脏)的时候，需要先检查一下这两个变量，如果buf_page_t::buf_fix_count不为零且buf_page_t::io_fix不为BUF_IO_NONE，则不允许驱逐(buf_page_can_relocate)。这里的技巧主要是为了减少数据页控制体上mutex的争抢，而对数据页的内容，读取的时候依然要加读锁，修改时加写锁。
该值以MTR为单位修改

**改进**
**MySQL空闲页面的获取依赖于page cleaner的刷新能力，如果page cleaner不能即时的刷新足够的空闲页面，那么系统就会使用上面的逻辑来为用户线程申请空闲页面。但如果让page cleaner加快刷新，又会导致频繁刷新脏数据，引发性能问题。 为了改善系统负载太高的情况下，page cleaner刷脏能力不足，进而用户线程调用LRU刷脏导致锁竞争加剧影响数据库性能，Percona对此进行了改善，引入独立的线程负责LRU list的刷脏。目的是为了让独立线程根据系统负载动态调整LRU的刷脏能力。由于LRU list的刷脏从page cleaner线程中脱离出来，调整LRU list的刷脏能力不再会影响到page cleaner。
