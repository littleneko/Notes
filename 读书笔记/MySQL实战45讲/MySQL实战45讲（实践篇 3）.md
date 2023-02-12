# 31 | 误删数据后除了跑路，还能怎么办？
**关键词**：**Flashback**，**mysqlbinlog**，**延迟复制备库**


1. 使用 delete 删除数据：利用 binlog Flashback
1. truncate/drop：全量备份，加增量日志
   1. 为了加速数据恢复，如果这个临时库上有多个数据库，你可以在使用 mysqlbinlog 命令时，加上一个 -database 参数，用来指定误删表所在的库
   1. 在应用日志的时候，==**需要跳过误操作的那个语句的 binlog**==
      1. 无 GTID：-stop-position -start-position 跳过
      1. 开启 GTID：set gtid_next=gtid1;begin;commit;
   3. 使用 mysqlbinlog 方法恢复数据还是不够快，主要原因有两个
      1. 如果是误删表，最好就是只恢复出这张表，也就是只重放这张表的操作，但是 mysqlbinlog 工具并不能指定只解析一个表的日志
      1. 用 mysqlbinlog 解析出日志应用，应用日志的过程就只能是单线程
   4. 一种加速的方法是，在用备份恢复出临时实例之后，将这个临时实例设置成线上备库的从库
      1. 在 start slave 之前，先通过执行 ﻿﻿change replication filter replicate_do_table = (tbl_name) 命令，就可以让临时库只同步误操作的表
      1. 这样做也可以用上并行复制技术，来加速整个数据恢复过程
3. 延迟复制备库：延迟复制的备库是一种特殊的备库，通过 CHANGE MASTER TO MASTER_DELAY = N 命令，可以指定这个备库持续保持跟主库有 N 秒的延迟。
3. rm 删除数据：有高可用集群，不怕



# ⭐️32 | 为什么还有 kill 不掉的语句？
**关键词**：**kill query**，**kill connection**，==**mysql_store_result**==，==**mysql_use_result**==


1. 在 MySQL 中有两个 kill 命令：
   1. 一个是 kill query + 线程 id，表示==终止这个线程中正在执行的**语句**==；
   1. 一个是 kill connection + 线程 id，这里 connection 可缺省，表示==**断开这个线程的连接**==，当然如果这个线程有语句正在执行，也是要先停止正在执行的语句的
2. 当用户执行 kill query thread_id_B 时，MySQL 里处理 kill 命令的线程做了两件事：
   1. 把 session B 的运行状态改成 ==THD::KILL_QUERY== (将变量 killed 赋值为 THD::KILL_QUERY)；
   1. 给 ==session B 的执行线程发一个信号==，发一个信号的目的，就是让 session B 退出等待，来处理这个 THD::KILL_QUERY 状态（MDL 锁等释放）。
3. Session B 不是“说停就停的”
   1. 一个语句执行过程中有多处“埋点”，==**在这些“埋点”的地方判断线程状态，如果发现线程状态是 THD::KILL_QUERY，才开始进入语句终止逻辑**==；
   1. 如果处于等待状态，必须是一个==**可以被唤醒的等待**==，否则根本不会执行到“埋点”处；
   1. 语句从开始进入终止逻辑，到终止逻辑完全完成，是有一个过程的。
4. kill 无效的情况
   1. ==**线程没有执行到判断线程状态的逻辑**==。跟这种情况相同的，还有由于 IO 压力过大，读写 IO 的函数一直无法返回，导致不能及时判断线程的状态。
   1. ==**终止逻辑耗时较长**==
      1. ==超大事务==执行期间被 kill。这时候，回滚操作需要对事务执行期间生成的所有新数据版本做回收操作，耗时很长。
      1. ==大查询回滚==。如果查询过程中生成了比较大的临时文件，加上此时文件系统压力大，删除临时文件可能需要等待 IO 资源，导致耗时较长。
      1. ==DDL 命令执行到最后阶段==，如果被 kill，需要删除中间过程的临时文件，也可能受 IO 资源影响耗时较久。
5. ==**客户端通过 Ctrl+C 命令，并不是直接终止线程**==。而由于 MySQL 是停等协议，所以这个线程执行的语句还没有返回的时候，再往这个连接里面继续发命令也是没有用的。实际上，执行 Ctrl+C 的时候，是 MySQL 客户端另外启动一个连接，然后发送一个 kill query 命令。
5. mysql 客户端的 -A 参数，表示关掉自动补全的功能，对于表很多的库，加快返回速度（不需要 show databases; show tables 建立本地索引）
5. MySQL 客户端发送请求后，接收服务端返回结果的方式有两种：
   1. 一种是==**本地缓存**==，也就是在本地开一片内存，先把结果存起来。如果你用 API 开发，对应的就是 ==**mysql_store_result**==方法。
   1. 另一种是==**不缓存**==，读一个处理一个。如果你用 API 开发，对应的就是 ==**mysql_use_result**== 方法。
8. mysql 客户端加上 -quick 参数，就会使用第二种不缓存的方式。==采用不缓存的方式时，如果本地处理得慢，就会导致服务端发送结果被阻塞，因此会让服务端变慢==



# ⭐️33 | 我查这么多数据，会不会把数据库内存打爆？
**关键词**：**net_buffer_length**，**Sending to client**，**Sending data**，**LRU**，**Buffer Pool**


1. MySQL 是“边读边发的”，这个概念很重要。这就意味着，如果客户端接收得慢，会导致 MySQL 服务端由于结果发不出去，这个事务的执行时间变长。一个查询在发送过程中，占用的 MySQL 内部的内存最大就是 net_buffer_length 这么大。

1. 如果你看到 State 的值一直处于 ==“**Sending to client**”==，就表示==**服务器端的网络栈写满了**==

1. ==**Sending data**== 并不一定是指“正在发送数据”，而==**可能是处于执行器过程中的任意阶段**==。比如，你可以构造一个锁等待的场景，就能看到 Sending data 状态

1. ==**InnoDB 对 LRU 的改进：全表扫描不会把 buffer pool 都刷掉**== ⭐️

   <img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/21f64a6799645b1410ed40d016139828.png" alt="img" style="zoom:50%;" />

   <center>图 7 改进的 LRU 算法</center>

   在 InnoDB 实现上，按照 5:3 的比例把整个 LRU 链表分成了 young 区域和 old 区域。图中 LRU_old 指向的就是 old 区域的第一个位置，是整个链表的 5/8 处。也就是说，靠近链表头部的 5/8 是 young 区域，靠近链表尾部的 3/8 是 old 区域。

   改进后的 LRU 算法执行流程变成了下面这样。

   1. 图 7 中状态 1，要访问数据页 P3，由于 P3 在 young 区域，因此和优化前的 LRU 算法一样，将其移到链表头部，变成状态 2。
   2. 之后要访问一个新的不存在于当前链表的数据页，这时候依然是淘汰掉数据页 Pm，但是新插入的数据页 Px，是放在 LRU_old 处。
   3. 处于 old 区域的数据页，每次被访问的时候都要做下面这个判断：
      1. 若这个数据页在 LRU 链表中存在的时间超过了 1 秒，就把它移动到链表头部；
      2. 如果这个数据页在 LRU 链表中存在的时间短于 1 秒，位置保持不变。1 秒这个时间，是由参数 innodb_old_blocks_time 控制的。其默认值是 1000，单位毫秒。

1. ==**长事务**==的影响，就要结合我们前面文章中提到的锁、MVCC 的知识点了。

   1. 如果前面的语句有更新，意味着它们在占用着==**行锁**==，会导致别的语句更新被锁住；
   1. 当然读的事务也有问题，就是会导致 ==**undo log 不能被回收**==，导致回滚段空间膨胀。


# ⭐️34 | 到底可不可以使用join？
**关键词**：==**Index Nested-Loop Join（NLJ）**==，**Simple Nested-Loop Join**，==**Block Nested-Loop Join（BNL）**==，**驱动表**，**被驱动表**，==**join_buffer_size**==


1. ==**Index Nested-Loop Join（可以使用被驱动表的索引）**==

   <img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1599326363767-9c42769b-3678-4fbc-931a-e6fafcff1647.png" alt="image.png" style="zoom:50%;" />

   这个过程是先遍历表 t1，然后根据从表 t1 中取出的每行数据中的 a 值，去表 t2 中查找满足条件的记录。在这个流程里：

      1. ==对**驱动表** t1 做了全表扫描==，这个过程需要扫描 100 行；
      1. 而对于每一行 R，==根据 a 字段去表 t2 查找，走的是树搜索过程==。由于我们构造的数据都是一一对应的，因此每次的搜索过程都只扫描一行，也是总共扫描 100 行；
      1. 所以，整个执行流程，总扫描行数是 200。

   通过上面的分析我们得到了两个结论：


   1. 使用 join 语句，性能比强行拆成多个单表执行 SQL 语句的性能要好；
   2. 如果使用 join 语句的话，==**需要让小表做驱动表**==。

   但是，你需要注意，这个结论的==**前提是“可以使用被驱动表的索引**”==。

2. ==**Simple Nested-Loop Join（不能使用被驱动表的索引**）==：因为对于驱动表的每一条数据，需要在被驱动表中全表扫描，MySQL 实际没有使用这种方法

3. ==**Block Nested-Loop Join（不能使用被驱动表的索引）**==

   被驱动表上没有可用的索引，算法的流程是这样的：

   * ==把表 t1 的数据读入线程内存 join_buffer 中==，由于我们这个语句中写的是 select *，因此是把整个表 t1 放入了内存；

   * ==扫描表 t2，把表 t2 中的每一行取出来，跟 join_buffer 中的数据做对比==，满足 join 条件的，作为结果集的一部分返回。

     >  注意：**join_buffer 是无序的**，每次需要全部扫描一遍

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1599326831821-cff99b83-c84c-484d-984c-f47038c354ef.png" alt="image.png" style="zoom:50%;" />

5. ⭐️join_buffer 的大小是由参数 join_buffer_size 设定的，默认值是 256k。==如果放不下表 t1 的所有数据话，策略很简单，就是分段放==。

   执行过程就变成了：

   1. 扫描表 t1，顺序读取数据行放入 join_buffer 中，放完第 88 行 join_buffer 满了，继续第 2 步；
   2. 扫描表 t2，把 t2 中的每一行取出来，跟 join_buffer 中的数据做对比，满足 join 条件的，作为结果集的一部分返回；
   3. 清空 join_buffer；继续扫描表 t1，顺序读取最后的 12 行数据放入 join_buffer 中，继续执行第 2 步。

   执行流程图也就变成这样：

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1599327006479-e24476cb-5b68-4411-acca-e96c29ac331d.png" alt="image.png" style="zoom: 50%;" />

6. 如果要使用 join，应该选择大表做驱动表还是选择小表做驱动表？
   1. 如果是 Index Nested-Loop Join 算法，应该选择小表做驱动表；
   1. 如果是 Block Nested-Loop Join 算法：
      1. 在 join_buffer_size 足够大的时候，是一样的；
      1. 在 join_buffer_size 不够大的时候（这种情况更常见），应该选择小表做驱动表。



# ⭐️35 | join语句怎么优化？
**关键词**：==**Multi-Range Read（MRR）**==，==**Batched Key Access（BKA）**==


1. Multi-Range Read 优化

   <img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1599327500658-27aea8e7-c300-4d3f-bd77-a0d1ebedc5fd.png" alt="image.png" style="zoom: 50%;" />

2. **Batched Key Access**（对 NLJ 的优化）：每次从驱动表中取一批排序，再去被驱动表中查找

   <img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1599327587873-f419f2d9-37bb-43b1-b021-f69295233114.png" alt="image.png" style="zoom: 50%;" />

3. ⭐️使用 Block Nested-Loop Join(BNL) 算法时，可能会==对被驱动表做多次扫描==。如果这个被驱动表是一个大的冷数据表，除了会导致 IO 压力大以外，==**多次扫描一个冷表，而且这个语句执行时间超过 1 秒，就会在再次扫描冷表的时候，把冷表的数据页移到 LRU 链表头部，**==影响 Buffer Pool 的正常运作。
3. BNL 转 BKA：不论是在原表上加索引，还是用有索引的临时表，我们的思路都是让 join 语句能够用上被驱动表上的索引，来触发 BKA 算法，提升查询性能
3. hash join



# 36 | 为什么临时表可以重名？


1. 临时表只能被创建它的 session 访问，所以在这个 session 结束的时候，会自动删除临时表。也正是由于这个特性，临时表就特别适合我们文章开头的 join 优化这种场景
1. 对于临时表，table_def_key 在“库名 + 表名”基础上，又加入了“server_id+thread_id”，也就是说，session A 和 sessionB 创建的两个临时表 t1，它们的 table_def_key 不同，磁盘文件名也不同，因此可以并存。
1. 如果当前的 binlog_format=row，那么跟临时表有关的语句，就不会记录到 binlog 里。也就是说，只在 binlog_format=statment/mixed 的时候，binlog 中才会记录临时表的操作。
1. MySQL 在记录 binlog 的时候，会把主库执行这个语句的线程 id 写到 binlog 中。这样，在备库的应用线程就能够知道执行每个语句的主库线程 id，并利用这个线程 id 来构造临时表的 table_def_key



# 37 | 什么时候会使用内部临时表？


1. MySQL 什么时候会使用内部临时表？
   1. 如果语句执行过程可以一边读数据，一边直接得到结果，是不需要额外内存的，否则就需要额外的内存，来保存中间结果；
   1. join_buffer 是无序数组，sort_buffer 是有序数组，临时表是二维表结构；
   1. 如果执行逻辑需要用到二维表特性，就会优先考虑使用临时表。比如我们的例子中，union 需要用到唯一索引约束， group by 还需要用到另外一个字段来存累积计数。
2. 通过今天这篇文章，我重点和你讲了 group by 的几种实现算法，从中可以总结一些使用的指导原则：
   1. 如果对 group by 语句的结果没有排序要求，要在语句后面加 order by null；
   1. 尽量让 group by 过程用上表的索引，确认方法是 explain 结果里没有 Using temporary 和 Using filesort；
   1. 如果 group by 需要统计的数据量不大，尽量只使用内存临时表；也可以通过适当调大 tmp_table_size 参数，来避免用到磁盘临时表；
   1. 如果数据量实在太大，使用 SQL_BIG_RESULT 这个提示，来告诉优化器直接使用排序算法得到 group by 的结果。



# 38 | 都说 InnoDB 好，那还要不要使用 Memory 引擎？
**关键词**：**Index Organizied Table**，**Heap Organizied Table**，**hash 索引**，**B-Tree 索引**


1. InnoDB 和 Memory 引擎的数据组织方式是不同的：
   1. InnoDB 引擎把数据放在主键索引上，其他索引上保存的是主键 id。这种方式，我们称之为索引组织表（**Index Organizied Table**）。
   1. 而 Memory 引擎采用的是把数据单独存放，索引上保存数据位置的数据组织形式，我们称之为堆组织表（**Heap Organizied Table**）。
2. 内存表也是支 B-Tree 索引的。在 id 列上创建一个 B-Tree 索引，SQL 语句可以这么写：alter table t1 add index a_btree_index using btree (id);
2. 内存表不支持行锁，只支持表锁。因此，一张表只要有更新，就会堵住其他所有在这个表上的读写操作



# ⭐️39 | 自增主键为什么不是连续的？
**关键词**：**auto_increment_offset**，**auto_increment_increment**，**innodb_autoinc_lock_mode**


1. ==**InnoDB 引擎的自增值，其实是保存在了内存里**==，并且到了 MySQL 8.0 版本后，才有了“自增值持久化”的能力，也就是才实现了“如果发生重启，表的自增值可以恢复为 MySQL 重启前的值”
   1. 在 MySQL 5.7 及之前的版本，自增值保存在内存里，并没有持久化。每次重启后，第一次打开表的时候，都会去找自增值的最大值 max(id)，然后将 max(id)+1 作为这个表当前的自增值
   1. 在 MySQL 8.0 版本，将自增值的变更记录在了 redo log 中，重启的时候依靠 redo log 恢复重启之前的值。
2. 根据要插入的值和当前自增值的大小关系，自增值的变更结果也会有所不同。假设，某次要插入的值是 X，当前的自增值是 Y。
   1. 如果 X < Y，那么这个表的自增值不变；
   1. 如果 X >= Y，就需要把当前自增值修改为新的自增值
3. ==**唯一键冲突是导致自增主键 id 不连续的第一种原因**==：这个表的自增值改成 3，是在真正执行插入数据的操作之前。这个语句真正执行的时候，因为碰到唯一键 c 冲突，==所以 id=2 这一行并没有插入成功，但也没有将自增值再改回去==。
3. ==**回滚也会产生类似的现象，这就是第二种原因**==
3. ==**自增值为什么不能回退？**==并行执行事务先申请自增值 2，3，然后如果事务 2 回滚的同时把自增值改成 2，会造成下次插入时主键冲突
3. MySQL 5.1.22 版本引入了一个新策略，新增参数 _innodb_autoinc_lock_mode_，默认值是 1。
   1. 这个参数的值被设置为 0 时，表示采用之前 MySQL 5.0 版本的策略，即==语句执行结束后才释放锁==；
   1. 这个参数的值被设置为 1 时：==普通 insert 语句，自增锁在申请之后就马上释放==；==类似 insert … select 这样的批量插入数据的语句，自增锁还是要等语句结束后才被释放==；
   1. 这个参数的值被设置为 2 时，所有的申请自增主键的动作都是申请后就释放锁
7. 为什么默认设置下，insert … select 要使用语句级的锁？为什么这个参数的默认值不是 2？binlog_format=statement下会造成主从不一致的问题（略）
7. 有 insert … select 这种批量插入数据的场景时，从并发插入数据性能的角度考虑，我建议你这样设置：innodb_autoinc_lock_mode=2 ，并且 binlog_format=row。批量插入数据，包含的语句类型是 insert … select、replace … select 和 load data 语句。
7. 对于==批量插入==数据的语句，MySQL 有一个==批量申请自增 id== 的策略：按 1，2，4，8 的个数申请，**这是主键 id 出现自增 id 不连续的第三种原因**



# 40 | insert语句的锁为什么这么多？
