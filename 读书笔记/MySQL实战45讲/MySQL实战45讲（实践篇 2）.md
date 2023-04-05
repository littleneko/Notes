# 16 | “order by” 是怎么工作的？
**关键词**：**order by**，**sort_buffer**，**全字段排序**，**rowid 排序**，==**Using filesort**==，==**归并排序**==


1. ==**全字段排序**==： `select city,name,age from t where city='杭州' order by name limit 1000;` 

    <img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1586270451159-9e8452ac-abc2-4197-a083-03adafcc6f95.png" alt="image.png" style="zoom: 80%;" />

2. 图中 "按 name 排序" 这个动作，可能在内存中完成，也可能需要使用外部排序，这取决于排序所需的内存和参数 `sort_buffer_size` 。如果要排序的数据量小于 `sort_buffer_size`，排序就在内存中完成。但如果排序数据量太大，内存放不下，则不得不利用磁盘临时文件辅助排序。

3. ⭐️内存放不下时，就需要使用外部排序，外部排序一般使用==**归并排序**==算法

4. 查看是否使用==**临时文件排序**==的方法：使用 OPTIMIZER_TRACE（略）

5. ==**rowid 排序**==： `max_length_for_sort_data` 是 MySQL 中专门控制用于排序的**行数据**的长度的一个参数。它的意思是，如果单行的长度超过这个值，MySQL 就认为单行太大，要换一个算法。

    <img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1586270551663-678dd245-e1ab-4801-b558-c8d210177c80.png" alt="image.png" style="zoom:80%;" />

6. 使用索引排序，添加 (city, name) 联合索引

    <img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1586270857299-05eb74cd-30b4-4fdf-87db-f5fc094a36ae.png" alt="image.png" style="zoom:80%;" />

7. 覆盖索引排序，添加 (city, name, age) 的联合索引

   <img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/df4b8e445a59c53df1f2e0f115f02cd6.jpg" alt="img" style="zoom: 40%;" />


# 17 | 如何正确地显示随机消息？
**关键词**：**临时表**，**Using temporary**，==**优先队列排序**==，**随机排序方法**

(略)

# 18 | 为什么这些 SQL 语句逻辑相同，性能却差异巨大？
**关键词：**


1. ==**对索引字段做函数操作**==，可能会破坏索引值的有序性，因此优化器就决定放弃走树搜索功能，如 `select xxx ... where month(t_modified)=7` 
1. 放弃了树搜索功能，优化器可以选择遍历主键索引，也可以选择遍历索引 t_modified，优化器对比索引大小后发现，索引 t_modified 更小，遍历这个索引比遍历主键索引来得更快。因此最终还是会选择索引 t_modified。explain可以看到 key="t_modified" 和 Using index，但是这条语句==扫描了整个索引的所有值==（这算不算使用了索引呢？可以说使用了，也可以说没使用）
> TIPS:
> - ==using where==：通常来说，意味着全表扫描或者在查找使用索引的情况下，但是还有查询条件不在索引字段当中。具体来说有很多种情况
> - ==using index==：覆盖索引
> - ==using index condition==：索引下推（ICP）

3. ==**对索引字段做隐式类型转换**==，在 MySQL 中，字符串和数字做比较的话，是将字符串转换成数字。比如表定义为 varchar，但是查询条件使用 int。 `select * from tradelog where tradeid=110717;` 等价于 `select * from tradelog where CAST(tradid AS signed int) = 110717;` 相当于对索引字段做了函数操作。
> 注意：只有在需要索引字段做类型转换时才无法使用索引，对查询条件做类型转换是可以使用索引的。比如表定义为 int，但是查询使用字符串则，按照mysql 类型转换规则，string 需要转换为 int，mysql 会首先把查询条件中的 string 转成 int 再查询。即 `select * from xx where id = '123'` 会被转成 `select * from xx where id = 123` 再去查询
> 

> mysql类型转换规则：[https://dev.mysql.com/doc/refman/5.7/en/type-conversion.html](https://dev.mysql.com/doc/refman/5.7/en/type-conversion.html)

4. ==**隐式字符编码转换**==，字符集不同只是条件之一，连接过程中要求在被驱动表的索引字段上加函数操作，是直接导致对被驱动表做全表扫描的原因。



# ⭐️19 | 为什么我只查一行的语句，也执行这么慢？
**关键词**：**MDL锁**，**FTWRL**，**semi-consistent**


1. **等 MDL 锁**。如何查看： `show processlist` 命令查看 Waiting for table metadata lock；解决方法：通过查询 sys.schema_table_lock_waits 这张表，我们就可以直接找出造成阻塞的 process id，把这个连接用 kill 命令断开即可
1. **等 FTWRL**
1. ==**等行锁**==。如何查看： `select * from t sys.innodb_lock_waits where locked_table='test.t'` 
> TIPS:
> - KILL QUERY pid：停止 pid 当前正在执行的语句，锁不会释放
> - KILL pid：断开这个连接，锁会被释放

4. ==**快照读扫描大量 undo log**==。现象：==普通 select 响应时间很长，加上 lock in share mod 后当前读立刻返回==。

4. **对于没有建索引的表如何加锁**
   1. **RR**：全表加 Gap Lock
   
   1. **RC**：只有满足条件的行加 Row Lock（扫描过程中不满足条件的行直接释放行锁）⭐️
   
      对于 `update` ，扫描的过程中如果发现该行已经被加锁了，会使用 semi-consistent 优化，即读取该行的最新值，判断是否满足 where 条件，只有在满足的时候才会锁等待
> **TIPS**:
>
> **REPEATABLE READ**
> For locking reads (SELECT with FOR UPDATE or LOCK IN SHARE MODE), UPDATE, and DELETE statements, locking depends on whether the statement uses a unique index with a unique search condition, or a range-type search condition.
>
> - For a _unique index_ with a unique search condition, `InnoDB` _locks only the index record found_, not the [gap](https://dev.mysql.com/doc/refman/5.7/en/glossary.html#glos_gap) before it.
> - For other search conditions, `InnoDB` _locks the index range scanned_, using [_gap locks_](https://dev.mysql.com/doc/refman/5.7/en/glossary.html#glos_gap_lock) or [_next-key locks_](https://dev.mysql.com/doc/refman/5.7/en/glossary.html#glos_next_key_lock) to block insertions by other sessions into the gaps covered by the range.
>
> **READ COMMITTED**
> For locking reads ([`SELECT`](https://dev.mysql.com/doc/refman/5.7/en/select.html) with `FOR UPDATE` or `LOCK IN SHARE MODE`), [`UPDATE`](https://dev.mysql.com/doc/refman/5.7/en/update.html) statements, and [`DELETE`](https://dev.mysql.com/doc/refman/5.7/en/delete.html) statements, `_InnoDB_`_ locks only index records_, not the gaps before them, and thus permits the free insertion of new records next to locked records. 
>
> Only row-based binary logging is supported with the READ COMMITTED isolation level.
>
> Using > `READ COMMITTED`
>
> has additional effects:
>
> * For [`UPDATE`](https://dev.mysql.com/doc/refman/5.7/en/update.html) or [`DELETE`](https://dev.mysql.com/doc/refman/5.7/en/delete.html) statements, `InnoDB` holds locks only for rows that it updates or deletes. ==*Record locks for nonmatching rows are released after MySQL has evaluated the`WHERE` condition*==. （==可以看到 MySQL 在这里实际上是违背了两阶段加锁协议的==）
>- **For [`UPDATE`](https://dev.mysql.com/doc/refman/5.7/en/update.html) statements, if a row is already locked, `InnoDB` performs a “==_semi-consistent_==” read, returning the latest committed version to MySQL so that MySQL can determine whether the row matches the `WHERE` condition of the [`UPDATE`](https://dev.mysql.com/doc/refman/5.7/en/update.html). If the row matches (must be updated), MySQL reads the row again and this time `InnoDB` either locks it or waits for a lock on it.**
> 
>ref: [https://dev.mysql.com/doc/refman/5.7/en/innodb-transaction-isolation-levels.html#](https://dev.mysql.com/doc/refman/5.7/en/innodb-transaction-isolation-levels.html#)



# ⭐️20 | 幻读是什么，幻读有什么问题？
**关键词**：**幻读**，**Gap Lock**，**Next-Key Lock**


1. **幻读指的是一个事务在前后两次查询同一个范围的时候，后一次查询看到了前一次查询没有看到的行**，==幻读仅专指 "新插入的行=="。

1. 幻读有什么问题：
   1. 首先是语义上的。session A 在 T1 时刻就声明了，“我要把所有 d=5 的行锁住，不准别的事务进行读写操作”。而实际上，这个==语义被破坏了==。
   1. ⭐️其次，是数据一致性的问题。而这个一致性，不止是数据库内部数据状态在此刻的一致性，还包含了==数据和日志在逻辑上的一致性==。

        <img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1586966593595-03a09c85-965d-44e7-b652-e7da3f1d81f2.png" alt="image.png" style="zoom: 80%;" />

        statement格式的binlog在从库重放的情况：
        ```
        update t set d=5 where id=0; /*(0,0,5)*/
        update t set c=5 where id=0; /*(0,5,5)*/
        
        insert into t values(1,1,5); /*(1,1,5)*/
        update t set c=5 where id=1; /*(1,5,5)*/
        
        update t set d=100 where d=5;/*所有d=5的行，d改成100*/
        ```

3. 也就是说，即使把所有的记录都加上锁，还是阻止不了新插入的记录，这也是为什么“幻读”会被单独拿出来解决的原因。

4. 如何解决幻读：间隙锁（Gap Lock）

3. **⭐️==跟间隙锁存在冲突关系的，是“往这个间隙中插入一个记录”这个操作。间隙锁之间都不存在冲突关系==。**如下图所示，因为表里面没有 7 这行记录，两个session 都会加 (5, 10) 的间隙锁，但是不冲突

    <img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1586966849982-b3b8f168-9f22-4d7d-b627-9db7ee9a51cf.png" alt="image.png" style="zoom: 80%;" />

6. Gap Lock 和行锁合称 next-key lock，每个 next-key lock 是前开后闭区间

7. ⭐️==**间隙锁的引入，可能会导致同样的语句锁住更大的范围，这其实是影响了并发度的，还可能造成死锁**==

    <img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1586967035451-71b7f36f-c548-43fd-90d7-401a6617843b.png" alt="image.png" style="zoom:80%;" />

8. ==**所以，你如果把隔离级别设置为读提交的话，就没有间隙锁了。但同时，你要解决可能出现的数据和日志不一致问题，需要把 binlog 格式设置为 row。（ref 2.b）**==

Q1: RC 隔离级别下是否有 Gap Lock
A1: 读提交隔离级别一般没有 gap lock，不过也有例外情况， 比如 insert 出现主键冲突的时候，也可能加间隙锁。


# ⭐️21 | 为什么我只改一行的语句，锁这么多？
**关键词**：**Next-Key Lock**

1. ==**MySQL加锁规则（RR）**==：
   - **原则 1**：加锁的==基本单位是 next-key lock==。希望你还记得，next-key lock 是==前开后闭==区间。
   - **原则 2**：查找过程中==访问到的对象才会加锁==。如果查询只使用覆盖索引，并不需要访问主键索引，那么主键索引上没有加任何锁（ lock in share mode：扫描索引只会锁住索引；for update：即使不访问主键索引也会给主键索引加锁）
   - **优化 1**：索引上的==等值查询==，给==唯一索引==加锁的时候，next-key lock ==退化为行锁==。
   - **优化 2**：索引上的==等值查询==，==向右遍历==时且==最后一个值不满足等值条件==的时候，next-key lock ==退化为间隙锁==。
   - **一个 bug**：唯一索引上的范围查询会访问到不满足条件的第一个值为止。


2. next-key lock 实际上是间隙锁和行锁加起来的结果，即==分析加锁的时候要按两步来，先 Gap Lock 再 Row Lock==。

    <img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1587040765219-3695a126-bfc6-4710-b3b7-009d186c946e.png" alt="image.png" style="zoom: 50%;" />

    session B 的 “加 next-key lock(5,10] ” 操作，实际上分成了两步，先是加 (5,10) 的间隙锁，加锁成功；然后加 c=10 的行锁，这时候才被锁住的。

3. 读提交隔离级别（RC）在外键场景下还是有间隙锁，相对比较复杂。另外，==在读提交隔离级别下还有一个优化，即：语句执行过程中加上的行锁，在语句执行完成后，就要把 "不满足条件的行" 上的行锁直接释放了，不需要等到事务提交==。（ref 19.5）

4. `<=`  到底是间隙锁还是行锁？其实，这个问题，你要跟 "执行过程" 配合起来分析。==在 InnoDB 要去找 "第一个值" 的时候，是按照等值去找的，用的是等值判断的规则；找到第一个值以后，要在索引内找 "下一个值"，对应于我们规则中说的范围查找==。

3. "有行" 才会加行锁。如果查询条件没有命中行，那就加 next-key lock



# 22 | MySQL 有哪些 "饮鸩止渴" 提高性能的方法？
**关键词**：**短连接风暴**，**慢查询**


1. 短连接风暴：不能单纯通过增大 `max_connections` 参数解决问题
   1. 第一种方法：先处理掉那些占着连接但是不工作的线程。通过 `show processlist` 和查询 `information_schema.innodb_trx` 表找到断开后损失较小的线程（比如不在事务中）
   1. 第二种方法：减少连接过程的消耗。跳过权限验证 `–skip-grant-tables` 
2. 慢查询
   1. 索引没有设计好：直接在备库执行 alter（关闭备库 binlog）然后主备交换，紧急情况下效率高，非紧急情况下建议使用 gh-ost
   1. SQL 语句没写好：配置 `query_rewrite` 规则
   1. MySQL 选错了索引：`force_index` 
   1. 提前预防的方法：测试环境打开 `slow_log` 分析是否符合预期
3. QPS 突增：一般是业务上了新功能有 bug，可以让业务把功能先下掉，或者把出现问题的 SQL 干掉


4. 如果一个数据库是被客户端的压力打满导致无法响应的，重启数据库是没用的。因为重启之后，业务请求还会再发。而且==由于是重启，buffer pool 被清空，可能会导致语句执行得更慢==。



# ⭐️23 | MySQL 是怎么保证数据不丢的？
**关键词**：**binlog cache**，**redo log buffer**，**group commit**，**LSN**，**checkpoint**


1. 一个事务的 binlog 是不能被拆开的，因此不论这个事务多大，也要确保一次性写入。系统给 binlog cache 分配了一片内存，每个线程一个，参数 `binlog_cache_size`  用于控制单个线程内 binlog cache 所占内存的大小。如果超过了这个参数规定的大小，就要暂存到磁盘。

    <img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1587046297950-9ac81a0c-9e69-476e-9c81-0e5f50902f52.png" alt="image.png" style="zoom:50%;" />

2. write 和 fsync 的时机，是由参数 `sync_binlog`  控制的：
   1. ==sync_binlog=0 的时候，表示每次提交事务都只 write，不 fsync==；（机器宕机会丢数据）
   1. ==sync_binlog=1 的时候，表示每次提交事务都会执行 fsync==；（不会丢数据）
   1. ==sync_binlog=N(N>1) 的时候，表示每次提交事务都 write，但累积 N 个事务后才 fsync==。（可能丢失 N 个事务的数据）
   
3. rego log 的 3 种状态

    <img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1587046474826-cf205c17-d550-47d8-9301-3fb873ded75b.png" alt="image.png" style="zoom:50%;" />

5. 为了控制 redo log 的写入策略，InnoDB 提供了 `innodb_flush_log_at_trx_commit`  参数，它有三种可能取值：
   1. ==设置为 0 的时候，表示每次事务提交时都只是把 redo log 留在 redo log buffer 中==;（会丢数据，不建议）
   1. ==设置为 1 的时候，表示每次事务提交时都将 redo log 直接持久化到磁盘==；（不会丢数据，性能稍差）
   1. ==**设置为 2 的时候，表示每次事务提交时都只是把 redo log 写到 page cache**==。（MySQL crash 不会丢数据，系统宕机会丢数据，写 page chache 很快，性能和 0 差不多）
   
6. 事务执行中间过程的 redo log 也是直接写在 redo log buffer 中的，这些 redo log 也会被后台线程一起持久化到磁盘。也就是说，==**一个没有提交的事务的 redo log，也是可能已经持久化到磁盘的**==

6. 没有提交的事务的 redo log 写入到磁盘中的场景
   1. InnoDB 有一个后台线程，每隔 1 秒，就会把 redo log buffer 中的日志，调用 write 写到文件系统的 page cache，然后调用 fsync 持久化到磁盘
   1. redo log buffer 占用的空间即将达到 innodb_log_buffer_size 一半的时候，后台线程会主动写盘
   1. 并行的事务提交的时候，顺带将这个事务的 redo log buffer 持久化到磁盘
   
8. **group commit** ⭐️

    <img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1587046856707-bd0e972c-4025-4eaf-8be7-43abd49709e0.png" alt="image.png" style="zoom: 33%;" />

9. ==**在并发更新场景下，第一个事务写完 redo log buffer 以后，接下来这个 fsync 越晚调用，组员可能越多，节约 IOPS 的效果就越好**。为了让一次 fsync 带的组员更多，MySQL 有一个很有趣的优化：拖时间==

    <img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1587046960111-785b3da1-1bc9-4220-8f9d-3a39f86b3907.png" alt="image.png" style="zoom: 33%;" />

10. 如果你想提升 binlog 组提交的效果，可以通过设置 `binlog_group_commit_sync_delay`  和 `binlog_group_commit_sync_no_delay_count`  来实现。
    1. binlog_group_commit_sync_delay 参数，表示延迟多少微秒后才调用 fsync;
    2. binlog_group_commit_sync_no_delay_count 参数，表示累积多少次以后才调用 fsync。
11. WAL 机制主要得益于两个方面：
    1. redo log 和 binlog 都是==**顺序写**==，磁盘的顺序写比随机写速度要快；
    2. ==**组提交机制**==，可以大幅度降低磁盘的 IOPS 消耗。
> **TIPS**:
> `sync_binlog` 和 `binlog_group_commit_sync_no_delay_count` 的最大区别主要在于，数据的丢失与否
>
> - `sync_binlog = N` ：每个事务 write 后就响应客户端了。刷盘是 N 次事务后刷盘。N 次事务之间宕机，数据丢失。
> - `binlog_group_commit_sync_no_delay_count = N` ： 必须等到 N 个后才能提交。换言之，会增加响应客户端的时间。但是一旦响应了，那么数据就一定持久化了。宕机的话，数据是不会丢失
>
> sync_binlog=0 的情况下，sync_delay 和 sync_no_delay_count 的逻辑先走，因此该等还是会等。等到满足了这两个条件之一，就进入 sync_binlog 阶段。这时候如果判断 sync_binlog=0，就直接跳过，还是不调 fsync

12. 临时设置成非双 1 的场景（一般情况下，把生产库改成 “非双 1” 配置，是设置 innodb_flush_logs_at_trx_commit=2、sync_binlog=1000）：
    1. 业务高峰期
    2. 备库延迟
    3. 备份恢复主库的副本，应用 binlog 的过程
    4. 批量导入数据




# 24 | MySQL 是怎么保证主备一致的？
**关键词**：**主备复制**


1. MySQL 主备的基本原理

    <img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1587094917295-bf20e887-0218-4d60-acc3-b452fb8145ce.png" alt="image.png" style="zoom:50%;" />

2. binlog 的三种格式对比
   1. statement 可能不安全，比如带 limit 的语句主备可能选择不同的索引，导致匹配的数据不一致
   1. row 格式没有上述问题
   1. mixed MySQL 自己会判断这条 SQL 语句是否可能引起主备不一致，如果有可能，就用 row 格式，否则就用 statement 格式
   
3. 现在越来越多的场景要求把 MySQL 的 binlog 格式设置成 row。这么做的理由有很多，我来给你举一个可以直接看出来的好处：**恢复数据**。可以方便使用**Flashback **工具恢复数据

3. 用 binlog 来恢复数据的标准做法是，用 mysqlbinlog 工具解析出来，然后把解析结果整个发给 MySQL 执行。类似下面的命令：
```sql
mysqlbinlog master.000001  --start-position=2738 --stop-position=2973 | mysql -h127.0.0.1 -P13000 -u$user -p$pwd;
```
​	如果直接拷贝 SQL 语句会有风险，比如 `NOW()` 函数，binlog 中记录实际上会先执行 `SET TIMESTAMP=xxx` 的，如果只拷贝 SQL 语句取得的时间戳就不正确了。

5. 双主架构下 MySQL 是如何解决循环复制问题的：根据 server id 判断是否是自己生成的 binlog
5. 可能出现循环复制的情况：
   1. 主更改了server id
   1. A -> B <-> C
7. 出现循环复制后的解决办法： `stop slave；CHANGE MASTER TO IGNORE_SERVER_IDS=(server_id_of_B);start slave;` 



**扩展**：异步复制，半同步复制（semi-sync），AFTER-COMMIT，AFTER_SYNC，group replication



Q1: “主库 A 从本地读取 binlog，发给从库 B”，这里的本地是指文件系统的 page cache还是 disk 呢？
A1: 对于 A 的线程来说，就是“读文件”，1. 如果这个文件现在还在 page cache中，那就最好了，直接读走；2. 如果不在 page cache 里，就只好去磁盘读。这个行为是文件系统控制的，MySQL 只是执行“读文件”这个操作

Q2: binlog 设置成 row 的话，update 语句下 server 肯定会把原数据先读出来，这样是不是就用不上 change buffer 了？
A1: 不是，change buffer 是用在普通索引上的，主键索引是唯一索引本来就用不上 change buffer


# 25 | MySQL 是怎么保证高可用的？
**关键词**：**主备延迟**，**主从切换**


1. 主备延迟的原因：
   1. 备库所在机器的性能要比主库所在的机器性能差
   1. 备库的压力大
   1. ==**大事务**==：delete 全表，DDL
   1. 备库的并行复制能力
   
2. 主备切换的两种策略
   1. 可靠性优先策略

      <img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1587119826563-40b27d9d-ae74-402d-91e6-0d901b671407.png" alt="image.png" style="zoom:50%;" />

   1. 可用性优先策略（statement 可能造成数据不一致，row 可能造成主键冲突）
   
3. 在满足数据可靠性的前提下，MySQL 高可用系统的可用性，是依赖于主备延迟的。延迟的时间越小，在主库故障的时候，服务恢复需要的时间就越短，可用性就越高。



# ⭐️26 | 备库为什么会延迟好几个小时？
**关键词**：**并行复制**


1. **并行复制模型**

   coordinator 在分发的时候，需要满足以下这两个基本要求：

   * 不能造成更新覆盖：这就要求==**更新同一行的两个事务，必须被分发到同一个 worker 中**==。
   * ==**同一个事务不能被拆开**，必须放到同一个 worker 中==。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1587121532510-a6aa399f-75f4-431b-a2dd-845d5da4206c.png" alt="image.png" style="zoom:50%;" />

2. **按表分发策略**（MySQL 5.5 ali patch）：如果有跨表的事务，是要把两张表放在一起考虑的。

   可以看到，每个 worker 线程对应一个 hash 表，用于保存当前正在这个 worker 的“执行队列”里的事务所涉及的表。hash 表的 key 是“库名. 表名”，value 是一个数字，表示队列中有多少个事务修改这个表。

   在有事务分配给 worker 时，事务里面涉及的表会被加到对应的 hash 表中。worker 执行完成后，这个表会被从 hash 表中去掉。

   每个事务在分发的时候，跟所有 worker 的冲突关系（更新同一个表）包括以下三种情况：

   * 如果跟所有 worker 都不冲突，coordinator 线程就会把这个事务分配给最空闲的 woker;
   * ==如果跟多于一个 worker 冲突，coordinator 线程就进入等待状态==，直到和这个事务存在冲突关系的 worker 只剩下 1 个；
   * ==如果只跟一个 worker 冲突，coordinator 线程就会把这个事务分配给这个存在冲突关系的 worker==。

   这个按表分发的方案，在多个表负载均匀的场景里应用效果很好。但是，如果碰到==热点表==，比如所有的更新事务都会涉及到某一个表的时候，所有事务都会被分配到同一个 worker 中，就变成单线程复制了。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1587121660781-c3f626dc-7403-45a0-90ff-b391ce73ef54.png" alt="image.png" style="zoom:50%;" />

3. **按行分发策略**（MySQL 5.5 ali patch）

   按行复制和按表复制的数据结构差不多，也是为每个 worker，分配一个 hash 表。只是要实现按行分发，这时候的 key，就必须是“库名 + 表名 + 唯一键的值”。但是，这个“唯一键”只有主键 id 还是不够的，我们还需要考虑唯一索引。

   ```sql
   
   CREATE TABLE `t1` (
     `id` int(11) NOT NULL,
     `a` int(11) DEFAULT NULL,
     `b` int(11) DEFAULT NULL,
     PRIMARY KEY (`id`),
     UNIQUE KEY `a` (`a`)
   ) ENGINE=InnoDB;
   
   insert into t1 values(1,1,1),(2,2,2),(3,3,3),(4,4,4),(5,5,5);
   ```

   <img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/f19916e27b8ff28e87ed3ad9f5473378.png" alt="img" style="zoom:50%;" />

   可以看到，这两个事务要更新的行的主键值不同，但是如果它们被分到不同的 worker，就有可能 session B 的语句先执行。这时候 id=1 的行的 a 的值还是 1，就会报唯一键冲突。

   相比于按表并行分发策略，按行并行策略在决定线程分发的时候，需要消耗更多的计算资源。

4. **按库分发**（MySQL 5.6 社区，不怎么使用）

5. ==**Group Commit（MariaDB）**==⭐️

   在第 23 篇文章中，介绍了 redo log 组提交 (group commit) 优化， 而 MariaDB 的并行复制策略利用的就是这个特性：

   * 能够在同一组里提交的事务，一定不会修改同一行；（写一定有锁，进入组提交了表示没有锁冲突）
   * 主库上可以并行执行的事务，备库上也一定是可以并行执行的。

   在实现上，MariaDB 是这么做的：

   * 在一组里面一起提交的事务，有一个相同的 commit_id，下一组就是 commit_id+1；
   * commit_id 直接写到 binlog 里面；
   * 传到备库应用的时候，相同 commit_id 的事务分发到多个 worker 执行；
   * 这一组全部执行完成后，coordinator 再去取下一批。

   这个策略有一个问题，==它并没有实现“真正的模拟主库并发度”这个目标。在主库上，一组事务在 commit 的时候，下一组事务是同时处于“执行中”状态的==。

   <img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1587122145200-4d65937a-24a9-4bed-97e0-953dbaeda2dc.png" alt="image.png" style="zoom:50%;" />

   <center>图 5 主库并行事务</center>

   而按照 MariaDB 的并行复制策略，备库上的执行效果如图 6 所示。可以看到，==在备库上执行的时候，要等第一组事务完全执行完成后，第二组事务才能开始执行==，这样系统的吞吐量就不够。

   <img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/8ac3799c1ff2f9833619a1624ca3e622.png" alt="img" style="zoom: 50%;" />

   <center>图 6 MariaDB 并行复制，备库并行效果</center>

   ==这个方案很容易被大事务拖后腿==。假设 trx2 是一个超大事务，那么在备库应用的时候，trx1 和 trx3 执行完成后，就只能等 trx2 完全执行完成，下一组才能开始执行。这段时间，只有一个 worker 线程在工作，是对资源的浪费。

6. ==**LOGICAL_CLOCK（MySQL 5.7）**==⭐️

   1. 可以先考虑这样一个问题，同时处于“执行状态”的所有事务，是不是可以并行？

      不能。因为，这里面可能有由于锁冲突而处于锁等待状态的事务。如果这些事务在备库上被分配到不同的 worker，就会出现备库跟主库不一致的情况。

   1. 而上面提到的 MariaDB 这个策略的核心，是==所有处于 commit 状态的事务可以并行。事务处于 commit 状态，表示已经通过了锁冲突的检验了。==

   **其实，==不用等到 commit 阶段，只要能够到达 redo log prepare 阶段，就表示事务已经通过锁冲突的检验了==**。因此，MySQL 5.7 并行复制策略的思想是：

   * ==**同时处于 prepare 状态的事务，在备库执行时是可以并行的；（表示没有锁冲突，即没有更新到同一行）**==

   * ==**处于 prepare 状态的事务，与处于 commit 状态的事务之间，在备库执行时也是可以并行的。（即已经进入 commit 状态的事务和刚进入 prepare 状态的事务也可以并行）**==


7. ==**WRITESET（MySQL 5.7.22）**==⭐️

   新增了一个参数 binlog-transaction-dependency-tracking，用来控制是否启用这个新策略。这个参数的可选值有以下三种。

      - **COMMIT_ORDER**，表示的就是前面介绍的，根据同时进入 prepare 和 commit 来判断是否可以并行的策略。
      - ==**WRITESET，表示的是对于事务涉及更新的每一行，计算出这一行的 hash 值，组成集合 writeset。如果两个事务没有操作相同的行，也就是说它们的 writeset 没有交集，就可以并行。**==
      - **WRITESET_SESSION**，是在 WRITESET 的基础上多了一个约束，即在主库上同一个线程先后执行的两个事务，在备库执行的时候，要保证相同的先后顺序。


​        


⭐️扩展阅读：[https://mp.weixin.qq.com/s/oj-DzpR-hZRMMziq2_0rYg](https://mp.weixin.qq.com/s/oj-DzpR-hZRMMziq2_0rYg)

1. **Group Commit**

   在代码实现中，同一组的事务拥有同一个 parent_commit（父亲），在二进制日志中可以看到类似如下的内容：

   ![img](https://littleneko.oss-cn-beijing.aliyuncs.com/img/1587123434098-f8154276-bd77-482a-bfc0-52cc2b33277b.webp)

   **last_commit 相同可视为具有相同的 parent_commit**，事务在同一组内提交，因此在从机回放时，可以并行回放。例如 last_committed = 0 的有 7 个事务，sequence_number 1 ~ 7，则这 7 个可以并行执行。last_committed = 7 有 6 个事务，sequence_number 9 ~ 14，可以并行回放执行。

2. **Logical Clock**

   在上面的并行执行中，last_committed = 1 的事务需要等待 last_committed = 0 的 7 个事务完成，同理，last_committed = 7 的 6 个事务需要等待last_committed = 1 的事务完成。但是 MySQL 5.7 还做了额外的优化，可进一步增大回放的并行度。思想是 LOCK-BASED，即==如果两个事务有**重叠**，则两个事务的锁依然是没有冲突的，依然可以并行回放==。

   ![](https://cdn.nlark.com/yuque/0/2020/webp/385742/1587123512641-6a533ef0-233e-4bcf-8e16-ef6d3f8035d8.webp#align=left&display=inline&height=143&margin=[object Object]&originHeight=286&originWidth=853&size=0&status=done&style=none&width=427)

   在上面的例子中，last_committed = 1的事务可以和 last_committed = 0 的事务同时并行执行，因为事务有重叠。具体来说，这表示 last_committed = 0 的事务进入到 COMMIT 阶段时，last_committed 的事务进入到了 PREPARE 阶段，即事务间依然没有冲突。具体实现思想可见官方的 Worklog： [**WL#7165: MTS: Optimizing MTS scheduling by increasing the parallelization window on master**](https://dev.mysql.com/worklog/task/?id=7165)

   ==**实际上经过这个优化后，binlog 中的 last_commited 不再是记录的上一组的 leader 的 id，而是该事务进入 prepare 阶段时系统中已经 commmit 事务的最大 sequence，在从库上回放时，last_commited 事务 commit 后本事务就可以开始回放了。**==

   > **TIPS**:
   >
   > * 小于等于 last_commited 的事务与本事务没有重叠，不能确定是否有冲突，不能并行回放；而 last_commited + 1 的事务与本事务是有重叠的，因为本事务进入到 Prepare 阶段的时候这个事务还没有 Commit，一定不会有冲突。
   > * 注意 last_commited 是 sequence_number，不是事务 id，因此一定是按提交顺序编号的。上面的图画得有误导性，事务 id 与 sequence_number 一样递增了，实际上事务提交顺序和事务 id 大小没有任何关系。
   
   
   
   **WL#7165: MTS: Optimizing MTS scheduling by increasing the parallelization window on master**
   
   ```
       Trx1 ------------P----------C-------------------------------->
                                   |
       Trx2 ----------------P------+---C---------------------------->
                                   |   |
       Trx3 -------------------P---+---+-----C---------------------->
                                   |   |     |
       Trx4 -----------------------+-P-+-----+----C----------------->
                                   |   |     |    |
       Trx5 -----------------------+---+-P---+----+---C------------->
                                   |   |     |    |   |
       Trx6 -----------------------+---+---P-+----+---+---C---------->
                                   |   |     |    |   |   |
       Trx7 -----------------------+---+-----+----+---+-P-+--C------->
                                   |   |     |    |   |   |  |
   ```
   
   如果按照组提交并行：
   
   * Trx5 and Trx6 are allowed to execute in parallel because they have the same commit-parent (namely, the counter value set by Trx2). 
   * Trx4 and Trx5 are not allowed to execute in parallel
   * Trx6 and Trx7 are not allowed to execute in parallel.
   
   但是：
   
   * Trx4, Trx5, and Trx6 hold all their locks at the same time but Trx4 will be executed in isolation.
   * Trx6 and Trx7 hold all their locks at the same time but Trx7 will be executed in isolation.

# 27 | 主库出问题了，从库怎么办？
**关键字**：**GTID**


1. 大多数的互联网应用场景都是读多写少，因此你负责的业务，在发展过程中很可能先会遇到读性能的问题。而在数据库层==解决读性能问题==，就要涉及到接下来两篇文章要讨论的架构：一主多从。
1. 没有 GTID 的情况下做故障切换：通过故障时间在新主上找位点，可能会有重复 binlog 被应用，可以把 slave_skip_errors 设置为“1032（插入数据时唯一键冲突）,1062（删除数据时找不到行）”，这样中间碰到这两个错误时就直接跳过。
1. GTID 格式：GTID=server_uuid:gno。在 MySQL 里面我们说 transaction_id 就是指事务 id，事务 id 是在事务执行过程中分配的，如果这个事务回滚了，事务 id 也会递增，而 gno 是在事务提交的时候才会分配。从效果上看，GTID 往往是连续的，因此我们用 gno 来表示更容易理解。
1. 可以通过 `set gtid_next='aaaaaaaa-cccc-dddd-eeee-ffffffffffff:10';begin;commit;` 这样的命令来跳过某些事务。
1. GTID 和在线 DDL
1. 在 GTID 模式下，如果一个新的从库接上主库，但是需要的 binlog 已经没了，要怎么做？
   1. 如果业务允许主从不一致的情况，那么可以在主库上先执行 `show global variables like 'gtid_purged'`，得到主库已经删除的 GTID 集合，假设是 gtid_purged1；然后先在从库上执行 reset master，再执行 `set global gtid_purged ='gtid_purged1'`；最后执行 start slave，就会从主库现存的 binlog 开始同步。binlog 缺失的那一部分，数据在从库上就可能会有丢失，造成主从不一致。
   1. 如果需要主从数据一致的话，最好还是通过重新搭建从库来做。
   1. 如果有其他的从库保留有全量的 binlog 的话，可以把新的从库先接到这个保留了全量 binlog 的从库，追上日志以后，如果有需要，再接回主库。
   1. 如果 binlog 有备份的情况，可以先在从库上应用缺失的 binlog，然后再执行 start slave。
7. MySQL 是怎么快速定位 binlog 里面的某一个 GTID 位置的？答案是，在 binlog 文件头部的 Previous_gtids 可以解决这个问题。



# 28 | 读写分离有哪些坑？
**关键词**：**过期读**，**semi-sync**


1. 过期读问题处理方法：
   1. 强制走主库方案；
   1. sleep 方案（前端/客户端缓存用户输入内容，而不是真的去查询数据库）；
   1. 判断主备无延迟方案；
   1. 配合 semi-sync 方案；
   1. 等主库位点方案；
   1. 等 GTID 方案。

2. ==判断主备无延迟方案==

   1. seconds_behind_master == 0（只能精确到秒）
   1. 如果 Master_Log_File 和 Relay_Master_Log_File、Read_Master_Log_Pos 和 Exec_Master_Log_Pos 这两组值完全相同，就表示接收到的日志已经同步完成。
   1. Retrieved_Gtid_Set 和 Executed_Gtid_Set 相同

3. 上面三种判断主备无延迟的方案都不精确：我们上面判断主备无延迟的逻辑，是==“备库收到的日志都执行完成了”。但是，**从 binlog 在主备之间状态的分析中，不难看出还有一部分日志，处于客户端已经收到提交确认，而备库还没收到日志的状态**==。

    <img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1599152760459-34dcc172-9edd-485e-a239-05edc94537d8.png" alt="image.png" style="zoom: 80%;" />

4. 解决上面问题的方法：**semi-sync replication**

5. ⭐实际上，回到我们最初的业务逻辑里，当发起一个查询请求以后，我们要得到准确的结果，其实并==**不需要等到“主备完全同步”**==。

    其实客户端是在发完 trx1 更新后发起的 select 语句，我们只需要确保 trx1 已经执行完成就可以执行 select 语句了。也就是说，如果在状态 3 执行查询请求，得到的就是预期结果了。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1599153043842-1a16305b-2b94-43e5-b97a-bd6f09517a4e.png" alt="image.png" style="zoom:50%;" />

6. semi-sync 配合判断主备无延迟的方案，存在两个问题：
   1. 一主多从的时候，在某些从库执行查询请求会存在过期读的现象；
   1. ==**在持续延迟的情况下，可能出现过度等待的问题**==。
   
7. ⭐==**等主库位点方案**==
   1. trx1 事务更新完成后，==**马上执行 show master status**== 得到当前主库执行到的 File 和 Position；
   
   1. 选定一个从库执行查询语句；
   
   1. 在从库上执行 ==**select master_pos_wait(File, Position, 1)**==；
   
   1. 如果返回值是大于等于 0 的正整数，则在这个从库执行查询语句；
   
   1. 否则，到主库执行查询语句。
   
      <img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1599153197174-4b833da2-ebd5-4d75-a4b2-567169f46bc7.png" alt="image.png" style="zoom:50%;" />

8. ⭐==**GTID 方案**==
   1. trx1 事务更新完成后，==**从返回包直接获取这个事务的 GTID**==，记为 gtid1；
   
   1. 选定一个从库执行查询语句；
   
   1. 在从库上执行 ==**select wait_for_executed_gtid_set(gtid1, 1)**==；
   
   1. 如果返回值是 0，则在这个从库执行查询语句；
   
   1. 否则，到主库执行查询语句。
   
      <img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1599153262014-cc04b014-2020-4283-895c-6bc8b8c4a114.png" alt="image.png" style="zoom:50%;" />

# ⭐29 | 如何判断一个数据库是不是出问题了？
**关键词**：**并发连接**，**并发查询**


1. ==**select 1 判断**==：==**不准确**==，同时在执行的语句超过了设置的 ==innodb_thread_concurrency== 的值，这时候系统其实已经不行了，但是通过 select 1 来检测系统，会认为系统还是正常的。

1. 在 show processlist 的结果里，看到的几千个连接，指的就是==**并发连接 **==（max_connection）。而“当前正在执行”的语句，才是我们所说的==**并发查询**==。==**innodb_thread_concurrency 设置的是并发查询数**==。

1. ==**在线程进入锁等待以后，并发线程的计数会减一**==，也就是说等行锁（也包括间隙锁）的线程是不算在 innodb_thread_concurrency 里面的。

1. 这么设计的原因是==**进入锁等待的线程已经不吃 CPU 了；更重要的是，必须这么设计，才能避免整个系统锁死。**==

   <img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1599154002109-44b31ecf-2f61-4bec-86bc-c41fe03a21be.png" alt="image.png" style="zoom:50%;" />

   这时候 InnoDB 不能响应任何请求，整个系统被锁死。而且，由于所有线程都处于等待状态，此时占用的 CPU 却是 0，而这明显不合理。所以，我们说 InnoDB 在设计时，遇到进程进入锁等待的情况时，将并发线程的计数减 1 的设计，是合理而且是必要的。

5. ==**查表判断**==：使用这个方法，我们==可以检测出由于并发线程过多导致的数据库不可用的情况==。但是，我们马上还会碰到下一个问题：==空间满了以后，这种方法又会变得不好使==。
5. ==**更新判断**==
   1. 需要注意需要主备上更新不同的行
   1. 更新判断是一个相对比较常用的方案了，不过依然存在一些问题。其中，“判定慢”一直是让 DBA 头疼的问题
7. 更新判断的问题：IO 利用率 100% 表示系统的 IO 是在工作的，每个请求都有机会获得 IO 资源，执行自己的任务。==而我们的检测使用的 update 命令，需要的资源很少，所以可能在拿到 IO 资源的时候就可以提交成功，并且在超时时间 N 秒未到达之前就返回给了检测系统==。
7. ⭐**内部统计**：MySQL 5.6 版本以后提供的 performance_schema 库，就在 file_summary_by_event_name 表里统计了每次 IO 请求的时间



# ⭐30 | 答疑文章（二）：用动态的观点看加锁
