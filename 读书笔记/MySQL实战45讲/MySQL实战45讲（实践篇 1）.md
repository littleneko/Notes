# ⭐️09 | 普通索引和唯一索引，应该怎么选择？
**关键词**：**普通索引**、**唯一索引**、**Change Bufer**


1. **查询过程**：等值查询普通索引找到第一条记录后还需要继续查找下一条；唯一索引找到第一条满足条件的记录后就会停止。性能影响可以忽略不计，因为MySQL 以页为单位读写，下一条记录大部分情况在同一页，已经读到内存中了。
1. **Change Buffer**：当需要更新（INSERT、UPDATE、DELETE）一个数据页时，如果数据页在内存中就直接更新，==而如果这个**数据页还没有在内存中**的话，在不影响数据一致性的前提下，InnoDB 会将这些更新操作缓存在 change buffer 中，这样就不需要从磁盘中读入这个数据页了==。
1. ==**change buffer 在内存中有拷贝，也会被写入到磁盘上**==。change Buffer 和数据页一样，也是物理页的一个组成部分，数据结构也是一颗 **B+ 树**，这棵B+树放在共享表空间中，默认 ibdata1 中
1. 将 change buffer 中的操作应用到原数据页，得到最新结果的过程称为 merge。除了访问这个数据页会触发 merge 外，系统有后台线程会定期 merge
1. Change Buffer 的好处：减少读磁盘（随机IO），语句的执行速度会得到明显的提升；避免占用过多 Buffer Pool 内存，提高内存利用率。使用`innodb_change_buffer_max_size` 设置大小，表示占用 Buffer Pool 的比例
1. ==**唯一索引的更新就不能使用 change buffer，实际上也只有普通索引可以使用**==
1. **Change Buffer 优化起作用的场景**
   1. 对于==**写多读少**==的业务来说，页面在写完以后马上被访问到的概率比较小，此时 change buffer 的使用效果最好。这种业务模型常见的就是账单类、日志类的系统
   1. 设一个业务的更新模式是写入之后马上会做查询，那么即使满足了条件，将更新先记录在 change buffer，但之后由于马上要访问这个数据页，会立即触发 merge 过程。这样随机访问 IO 的次数不会减少，反而增加了 change buffer 的维护代价。所以，对于这种业务模式来说，change buffer 反而起到了副作用。
8. ==redo log 主要节省的是**随机写磁盘**的 IO 消耗（转成顺序写），而 change buffer 主要节省的则是**随机读磁盘**的 IO 消耗==。



change buffer 更新过程（假设 k1 在内存中，k2 不在内存中）

![image.png](https://littleneko.oss-cn-beijing.aliyuncs.com/img/1586006564026-d2745e7a-9f1b-495c-8e2c-7d4d6c029bf4.png)

change buffer 读取过程

![image.png](https://littleneko.oss-cn-beijing.aliyuncs.com/img/1586006654239-400eee74-9232-4ed5-8442-9dedebba49bc.png)

9. Change Buffer merge 的过程
   1. 从磁盘读入数据页到内存（老版本的数据页）；
   1. 从 change buffer 里找出这个数据页的 change buffer 记录 (可能有多个），依次应用，得到新版数据页；
   1. 写 redo log。这个 redo log 包含了数据的变更和 change buffer 的变更。



Q1: Change Buffer 与锁
A1: 锁是一个单独的数据结构，如果数据页上有锁，change buffer 在判断“是否能用”的时候，就会认为否

Q2: 主键索引和 Change Buffer
A2: 主键索引肯定是唯一索引，所以用不上 change buffer，change buffer 的优化主要体现在二级索引上。

Q3：如果某次写入使用了 change buffer 机制，之后主机异常重启，是否会丢失 change buffer 和数据。
A3: 不会丢失，虽然是只更新内存，但是在事务提交的时候，我们把 change buffer 的操作也记录到 redo log 里了，所以崩溃恢复的时候，change buffer 也能找回来。

# 10 | MySQL为什么有时候会选错索引？
**关键词**：**优化器**，**索引选择**，**扫描行数**，**区分度（cardinality）**，**执行计划**


1. 优化器选择索引的依据除==扫描行数==外，还要结合==是否使用临时表==、==是否排序==等因素进行综合判断。
1. MySQL 在真正开始执行语句之前，并不能精确地知道满足这个条件的记录有多少条，而只能根据统计信息来估算记录数。这个统计信息就是索引的“区分度”。显然，一个索引上不同的值越多，这个索引的区分度就越好。==**而一个索引上不同的值的个数，我们称之为“基数”（cardinality）**==。也就是说，这个基数越大，索引的区分度越好。我们可以使用 `show index` 方法，看到一个索引的基数。
1. 采样统计的时候，InnoDB 默认会选择 N 个数据页，统计这些页面上的不同值，得到一个平均值，然后乘以这个索引的页面数，就得到了这个索引的基数
1. `analyze table t` 命令，可以用来重新统计索引信息
1. 索引统计只是一个输入，对于一个具体的语句来说，优化器还要判断，执行这个语句本身要扫描多少行，即==**需要统计回表的代价**==。
1. 解决MySQL索引选择错误的问题：
   1. force index
   1. 修改SQL语句，引导MySQL使用我们期望的索引
   1. 新建一个更合适的索引或者删掉误用的索引



# 11 | 怎么给字符串字段加索引？
**关键词**：**前缀索引**，**覆盖索引**、**倒序存储**


1. ==**索引选取的越长，占用的磁盘空间就越大，相同的数据页能放下的索引值就越少，搜索的效率也就会越低。**==
1. 使用前缀索引，定义好长度，就可以做到既节省空间，又不用额外增加太多的查询成本。我们在建立索引时关注的是区分度，区分度越高越好。因为区分度越高，意味着重复的键值越少。因此，我们可以通过统计索引上有多少个不同的值来判断要使用多长的前缀。可以使用如下语句 `select count(distinct left(email,4)) as L from SUser` 
1. ==**前缀索引无法使用覆盖索引**==
1. 对于前缀区分度不大的情况（两种方法都**不支持范围查询**）：
   1. 可以使用**倒序存储**，查询时使用 `reverse` 函数
   1. 添加一个hash字段，在hash值上建索引



# ⭐️12 | 为什么我的MySQL会“抖”一下？
**关键词**：**刷脏**


1. 当内存数据页跟磁盘数据页内容不一致的时候，我们称这个内存页为“脏页”。内存数据写入到磁盘后，内存和磁盘上的数据页的内容就一致了，称为“干净页”。

1. 刷脏的4种场景：
   1. InnoDB 的 ==**redo log 写满了**==。这时候系统会停止所有更新操作，把 checkpoint 往前推进，redo log 留出空间可以继续写。把 checkpoint 位置从 CP 推进到 CP’，就需要将两个点之间的日志，对应的所有脏页都 flush 到磁盘上。
   1. ==**系统内存不足**==。当需要新的内存页，而内存不够用的时候，就要淘汰一些数据页，空出内存给别的数据页使用。如果淘汰的是“脏页”，就要先将脏页写到磁盘。
   1. MySQL 认为系统“空闲”的时候主动刷脏
   1. MySQL 正常关闭的情况。这时候，MySQL 会把内存的脏页都 flush 到磁盘上，这样下次 MySQL 启动的时候，就可以直接从磁盘上读数据，启动速度会很快。
   
3. `innodb_io_capacity`  这个参数，它会告诉 InnoDB 你的磁盘能力

4. InnoDB 的刷盘速度就是要参考这两个因素：一个是==**脏页比例**==，一个是 ==**redo log 写盘速度**==。

5. 参数 `innodb_max_dirty_pages_pct`  是脏页比例上限，默认值是 75%

6. **根据上述算得的 F1(M) 和 F2(N) 两个值，取其中较大的值记为 R，之后引擎就可以按照 innodb_io_capacity 定义的能力乘以 R% 来控制刷脏页的速度**

   <img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1586093102073-980f099b-74ff-45bb-ac52-449ff2ea0fa2.png" alt="image.png" style="zoom:50%;" />

7. 脏页比例查看
```sql
select VARIABLE_VALUE into @a from global_status where VARIABLE_NAME = 'Innodb_buffer_pool_pages_dirty';
select VARIABLE_VALUE into @b from global_status where VARIABLE_NAME = 'Innodb_buffer_pool_pages_total';
select @a/@b;
```

8. 在 InnoDB 中， `innodb_flush_neighbors`  参数就是用来控制刷邻居脏页行为的，值为 1 的时候会有上述的“连坐”机制，值为 0 时表示不找邻居，自己刷自己的。找“邻居”这个优化在机械硬盘时代是很有意义的，可以减少很多随机 IO。**而如果使用的是 SSD 这类 IOPS 比较高的设备的话，我就建议你把 `innodb_flush_neighbors` 的值设置成 0。因为这时候 IOPS 往往不是瓶颈，而“只刷自己”，就能更快地执行完必要的刷脏页操作，减少 SQL 语句响应时间**。



# 13 | 为什么表数据删掉一半，表文件大小不变？
**关键词**：**标记删除**，**空洞**，**重建表**，**OnLine DDL**


1. **数据删除只是标记删除**：假设，我们要删掉 R4 这个记录，InnoDB 引擎只会把 R4 这个记录标记为删除。如果之后要再插入一个 ID 在 300 和 600 之间的记录时，可能会复用这个位置。但是，磁盘文件的大小并不会缩小。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1586094428711-cfbdffc7-a850-4264-92a6-5570de3575cd.png" alt="image.png" style="zoom:33%;" />

2. 如果我们删掉了一个数据页上的所有记录，整个数据页就可以被复用了。

2. 如果我们用 delete 命令把整个表的数据删除呢？结果就是，所有的数据页都会被标记为可复用。但是磁盘上，文件不会变小

2. ==**不止是删除数据会造成空洞，插入数据也会**==。如果数据是按照索引递增顺序插入的，那么索引是紧凑的。但如果数据是随机插入的，就可能造成索引的数据页分裂。

   <img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1586094589993-9e587a34-2ab3-4c54-b2f8-ee5a1985c552.png" alt="image.png" style="zoom:50%;" />

> TIPS:
> 这种情况 mysql 实际上是有优化的，但还是会有空洞

5. 重建表可以收缩空间， `alter table A engine=InnoDB` 在。整个 DDL 过程中，表 A 中不能有更新。也就是说，这个 DDL 不是 Online 的

5. MySQL 5.6 版本开始引入的 Online DDL

   ![image.png](https://littleneko.oss-cn-beijing.aliyuncs.com/img/1586094902987-0030c5f2-f0a3-4724-842b-b0245c20d68d.png)

> TIPS:
> alter 语句在启动的时候需要获取 MDL 写锁，但是这个写锁在真正拷贝数据之前就退化成读锁了



7. ==**Inplace**==：根据表 A 重建出来的数据是放在“tmp_file”里的，这个临时文件是 InnoDB 在内部创建出来的。整个 DDL 过程都在 InnoDB 内部完成。对于 server 层来说，没有把数据挪动到临时表，是一个“原地”操作，这就是 “inplace” 名称的来源



Q1: 什么时候使用 `alter table t engine=InnoDB` 会让一个表占用的空间反而变大。
A1: 1. 这个表，本身就已经没有空洞的了；2. 在 DDL 期间，如果刚好有外部的 DML 在执行，这期间可能会引入一些新的空洞；3. 在重建表的时候，InnoDB 不会把整张表占满，每个页留了 1/16 给后续的更新用。也就是说，其实重建表之后不是“最”紧凑的。

# 14 | count(\*) 这么慢，我该怎么办？
**关键词**： **count**


1. count(\*) 的实现方式
   1. MyISAM 引擎把一个表的总行数存在了磁盘上，因此执行 count(\*) 的时候会直接返回这个数，效率很高
   1. 而 InnoDB 引擎就麻烦了，它执行 count(\*) 的时候，需要把数据一行一行地从引擎里面读出来，然后累积计数。
   
2. ==**为什么 InnoDB 不跟 MyISAM 一样，也把数字存起来呢？因为可重复读，MVCC**==

3. ==**count(\*) 可以不遍历主键索引，遍历最小的普通索引**==

2. 解决 count(\*) 慢的方法
   1. 行数保存到 redis：无法保证一致性
   
   1. 行数保存到 mysql，利用 InnoDB 事务的特性
   
      <img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1586097367608-d05e8c7d-c06a-4ba8-9b04-8a25c2d7e2b7.png" alt="image.png" style="zoom:50%;" />
   
5. count() 的语义：count() 是一个聚合函数，对于返回的结果集，一行行地判断，如果 count 函数的参数不是 **NULL**，累计值就加 1，否则不加。最后返回累计值。

5. ==**count(\*)，count(1)，count(id)，count(column) 的性能差别**==
   
   1. 对于 count(主键 id) 来说，==InnoDB 引擎会遍历整张表，把每一行的 id 值都取出来，返回给 server 层==。server 层拿到 id 后，判断是不可能为空的，就按行累加。
   1. 对于 count(1) 来说，==InnoDB 引擎遍历整张表，但不取值==。server 层对于返回的每一行，放一个数字“1”进去，判断是不可能为空的，按行累加。因此 count(1) > count(id)
   1. 对于 count(字段) 来说：
      1. 如果这个“字段”是定义为 not null 的话，一行行地从记录里面读出这个字段，判断不能为 null，按行累加；
      1. 如果这个“字段”定义允许为 null，那么执行的时候，判断到有可能是 null，还要把值取出来再判断一下，不是 null 才累加。
   4. 但是 count(\*) 是例外，并不会把全部字段取出来，而是专门做了优化，不取值。count(\*) 肯定不是 null，按行累加。

==**count(字段) < count(主键 id) < count(1) ≈ count(\*)**==

# 15 | 答疑文章（一）：日志和索引相关问题
**关键词**：**crash recovery**，**两阶段提交**


1. 在两阶段提交的不同时刻，MySQL 异常重启会出现什么现象

   <img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1586190090676-eb45343d-41c8-49ba-aab7-3183fceec1d8.png" alt="image.png" style="zoom:50%;" />

      1. 时刻A：事务回滚

      1. 时刻B：事务提交，因为 redolog 处于 prepare 且 binlog 完整

2. MySQL 如何判断 binlog 完整：XID event
2. redo log 和 binlog 是怎么关联起来的：XID
2. 时刻B的事务为什么需要提交：为了保证主备一致
2. 为什么需要两阶段：假设先提交redo再写binlog，如果binlog写入失败，主备会不一致
2. ==**为什么不能只用 binlog 来实现 crash recovery**：**binlog 没有能力恢复“数据页”**==
2. 能否只用 redo 来实现 crash recovery：如果只从崩溃恢复的角度来讲是可以的。你可以把 binlog 关掉，这样就没有两阶段提交了，但系统依然是 crash-safe 的
