# 01 | 基础架构：一条 SQL 查询语句是如何执行的
**关键词**：**连接器**、**查询缓存**、**分析器**、**优化器**、**执行器**

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1584286222295-cb000d72-1b9a-47dc-a34a-4b6bc8c4d2f7.png" alt="image.png" style="zoom:50%;" />

Server 层包括==连接器==、==查询缓存==、==分析器==、==优化器==、==执行器==等，涵盖 MySQL 的大多数核心服务功能，以及==所有的内置函数（如日期、时间、数学和加密函数等)，所有跨存储引擎的功能都在这一层实现，比如存储过程、触发器、视图等==。

1. **权限确定**：在**连接器**里处理完登录请求后就查询出来确定，之后这个连接里面的权限判断逻辑，都将依赖于此时读到的权限。

   这就意味着，==一个用户成功建立连接后，即使你用管理员账号对这个用户的权限做了修改，也不会影响已经存在连接的权限==。修改完成后，只有再新建的连接才会使用新的权限设置。

1. **长连接**：长连接使用临时内存直到连接断开时才释放，MySQL 5.7 以后可以通过 `mysql_reset_connection` 初始化连接资源。

1. **权限验证**：执行器在执行之前会判断



Q1: 为什么对权限的检查不在优化器之前做？
A1: 有些时候，SQL 语句要操作的表不只是 SQL 字面上那些。比如如果有个触发器，得在执行器阶段（过程中）才能确定，优化器阶段前是无能为力的。

Q2: Unknown column 'k' in 'where clause' 这个错误是在我们上面提到的哪个阶段报出来的呢？
A2: 分析器

Q3: 创建一个没有 select 权限的用户，执行 `select * from T where k=1`，报错 "select command denied"，并没有报错 "unknown column"，是不是可以说明是在打开表之后才判断读取的列不存在？
A3: 这个是一个安全方面的考虑。你想想一个用户如果没有查看这个表的权限，你是会告诉他字段不对还是没权限？如果告诉他字段不对，其实给的信息太多了，因为没权限的意思还包含了：没权限知道字段是否存在

# 02 | 日志系统：一条 SQL 更新语句是如何执行的？
**关键词**: **WAL**、**redo log**、**binlog**、**两阶段提交**、**双1设置**、**crash-safe**

**WAL**：WAL 的全称是 ==Write-Ahead Logging==，它的关键点就是先写日志，再写磁盘。redo 将写数据数据页的随机 IO 变成写日志的顺序 IO

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1584288534049-262d25e8-4663-4f54-8d58-acad70498b3c.png" alt="image.png" style="zoom: 67%;" />

**两阶段提交**

为什么需要两阶段提交？反证：

1. 先写 redo log 后写 binlog：假设在 redo log 写完，binlog 还没有写完的时候，MySQL 进程异常重启，恢复后主库有该条数据，从库没有
1. 先写 binlog 后写 redo log：如果在 binlog 写完之后 crash，从库有数据，主库没有数据



**crash-safe**

1. `innodb_flush_log_at_trx_commit` 这个参数设置成 1 的时候，表示每次事务的 redo log 都直接持久化到磁盘。
1. `sync_binlog` 这个参数设置成 1 的时候，表示每次事务的 binlog 都持久化到磁盘。



# ⭐️03 | 事务隔离：为什么你改了我还看不见？
**关键词**：**ACID**、**隔离级别**、**undo**、**MVCC**

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1584544507160-98e784b7-ef2c-43ab-acaa-560f6840cc68.png" alt="image.png" style="zoom:50%;" />

- 读未提交：`V1=2,     V2=2,   V3=2` 

- 读已提交：`V1=1,     V2=2,   V3=2` 

- 可重复读：`V1=1,     V2=1,   V3=2` 

- 串行化：    `V1=1,     V2=2,   V3=2` （事务 A 在第一次执行查询的时候会对改行加读锁，事务 B 执行 “将 1 改成 2” 的时候，会被锁住，直到事务 A 提交后，事务 B 才可以继续执行）

  > **Tips**: 
  >
  > 上面这个图画得具有误导性，实际上有 3 个事务，最后查询得到 V3 是一个新的事务。因此，可串行化隔离级别下，相当于 A1 -> B -> A2 三个事务串行执行的结果。



1. **事务隔离的实现**：可重复读 -> MVCC，undo
1. **undo 删除的时机**：当系统里没有比这个回滚日志更早的 read-view 的时候
1. **不要使用长事务**：在这个事务提交之前，回滚记录都要保留，这会导致大量占用存储空间。除此之外，长事务还占用锁资源，可能会拖垮库。
1. MySQL RR 隔离级别中如何解决幻读：==快照读 -> MVCC==；==当前读 -> Next-Key Lock==。



# 04 | 深入浅出索引（上）
**关键词**：**主键索引（聚簇索引）**、**非主键索引（二级索引）**、**回表**、**页分裂**、**页合并**、**自增主键**

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1584546148412-a21abd08-4c1f-4070-92f9-fc45981fa348.png" alt="image.png" style="zoom:50%;" />

1. **Hash索引**：等值查询快，不适用于区间查询
1. **有序数组索引**：等值查询和范围查询场景中的性能就都非常优秀，只适用于静态存储引擎
1. **二叉（N叉）搜索树**：等值和范围查询效率都很高，N 叉树可以使树高更矮，减少磁盘访问次数
1. **InnoDB 索引模型**：主键索引 B+ 树，每一个索引 B+ 树
1. **基于主键索引和普通索引的查询的区别**：非主键索引需要回表，多扫描一次索引树，因此要尽量使用主键索引（覆盖索引的情况除外）
1. 页分裂和页合并过程中会造成性能下降
1. **自增主键的好处**：减少页节点分裂
1. 主键长度越小，普通索引的叶子节点就越小，普通索引占用的空间也就越小
1. **为什么要重建索引**：索引可能因为删除，或者页分裂等原因，导致数据页有空洞，重建索引的过程会创建一个新的索引，把数据按顺序插入，这样页面的利用率最高，也就是索引更紧凑、更省空间。
1. 重建主键索引的方法：`alter table T engine=InnoDB`
1. "N叉树" 的N值在 MySQL 中是可以被人工调整的么：调整 key 的大小；5.6 以后可以通过 page 大小来间接控制



# ⭐️==05 | 深入浅出索引（下）==
**关键词**：==**覆盖索引**==、==**索引下推（ICP）**==、==**Multi-Range Read (MRR)**==

1. **覆盖索引**：由于覆盖索引可以减少树的搜索次数，显著提升查询性能，所以使用覆盖索引是一个常用的性能优化手段。

2. **最左前缀原则**：B+ 树这种索引结构，可以利用索引的“最左前缀”，来定位记录。

    <img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1584546639627-eef36114-dfcd-4b2e-ab8c-8f2a2dc41813.png" alt="image.png" style="zoom: 67%;" />

3. ==**索引下推**==：MySQL 5.6 引入的索引下推优化（index condition pushdown)， 可以在索引遍历过程中，对索引中包含的字段先做判断，直接过滤掉不满足条件的记录，减少回表次数。

​	**Example**:

​		`select * from tuser where name like '张%' and age=10 and ismale=1;` 

​		联合索引（name, age），根据前缀索引规则，所以这个语句在搜索索引树的时候，只能用“张”，找到第一个满足条件的记录 ID3，在 MySQL 5.6 之前，只能	从 ID3 开始一个个回表。到主键索引上找出数据行，再对比字段值。

​	<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1584546755665-7d62ac07-bf84-4982-ae18-8be9f7edacf3.png" alt="image.png" style="zoom: 80%;" /><img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1584546761691-9659ed35-2525-4fc2-8f71-feb5dd2ad794.png" alt="image.png" style="zoom: 80%;" />

4. ==**Multi-Range Read (MRR)**== ：在不影响排序结果的情况下，在取出主键后，回表之前，会在对所有获取到的主键排序。



# 06 | 全局锁和表锁 ：给表加个字段怎么有这么多阻碍？
**关键词**：**全局锁**、**FTWRL**、**表锁**、**MDL**


1. **全局锁（FTWRL）**的典型使用场景是，做全库逻辑备份

1. `mysqldump` 的 `single-transaction` 方法只适用于所有的表使用事务引擎的库

1. MySQL 里面表级别的锁有两种：一种是**表锁**（lock tables … read/write），一种是**元数据锁**（meta data lock，MDL)

1. 当对一个表做增删改查操作的时候，加 MDL 读锁；当要对表做结构变更操作的时候，加 MDL 写锁

1. 即使是小表，DDL操作不慎也会出问题

   <img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1585064637978-29dc8d63-3d3d-43bf-af83-d758869f13bb.png" alt="image.png" style="zoom: 80%;" />

6. 如何安全地给小表加字段：解决长事务；在 alter table 语句里面设定等待时间



Q1: mysql 5.6 不是支持 online ddl 了吗？也就是对表操作增加字段等功能，实际上不会阻塞读写
A1: Online DDL 的过程是这样的：

1. 拿 MDL 写锁
1. 降级成 MDL 读锁
1. 真正做 DDL
1. 升级成 MDL 写锁
1. 释放 MDL 锁

1、2、4、5 如果没有锁冲突，执行时间非常短。第 3 步占用了 DDL 绝大部分时间，这期间这个表可以正常读写数据，是因此称为 “online ”。我们文中的例子，是在第一步就堵住了

Q2: 当备库用 `–single-transaction` 做逻辑备份的时候，如果从主库的 binlog 传来一个 DDL 语句会怎么样
A2: 假设这个 DDL 是针对表 t1 的， 这里我把备份过程中几个关键的语句列出来：

```sql

Q1:SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
Q2:START TRANSACTION  WITH CONSISTENT SNAPSHOT；
/* other tables */
Q3:SAVEPOINT sp;
/* 时刻 1 */
Q4:show create table `t1`;
/* 时刻 2 */
Q5:SELECT * FROM `t1`;
/* 时刻 3 */
Q6:ROLLBACK TO SAVEPOINT sp;
/* 时刻 4 */
/* other tables */
```


参考答案如下：

1. 如果在 Q4 语句执行之前到达，现象：没有影响，备份拿到的是 DDL 后的表结构。
1. 如果在“时刻 2”到达，则表结构被改过，Q5 执行的时候，报 Table definition has changed, please retry transaction，现象：mysqldump 终止；
1. ==如果在“时刻 2”和“时刻 3”之间到达，mysqldump 占着 t1 的 MDL 读锁，binlog 被阻塞，现象：主从延迟，直到 Q6 执行完成==。
1. 从“时刻 4”开始，mysqldump 释放了 MDL 读锁，现象：没有影响，备份拿到的是 DDL 前的表结构。



# 07 | 行锁功过：怎么减少行锁对性能的影响？
**关键词：两阶段锁，死锁，死锁检测**

1. 在 InnoDB 事务中，行锁是在需要的时候才加上的，但并不是不需要了就立刻释放，而是要等到事务结束时才释放。这个就是两阶段锁协议
1. ==如果你的事务中需要锁多个行，要把最可能造成锁冲突、最可能影响并发度的锁尽量往后放==
1. 出现死锁以后，有两种策略：
   - 一种策略是，直接进入等待，直到超时。这个超时时间可以通过参数 `innodb_lock_wait_timeout`  来设置。
   - 另一种策略是，发起死锁检测，发现死锁后，主动回滚死锁链条中的某一个事务，让其他事务得以继续执行。将参数 `innodb_deadlock_detect`  设置为 on，表示开启这个逻辑。
4. ==怎么解决由这种热点行更新导致的性能问题呢==
   1. 如果你能确保这个业务一定不会出现死锁，可以临时把死锁检测关掉
   1. 控制并发度
   1. ...



# ⭐️08 | 事务到底是隔离的还是不隔离的？
**关键词**：**快照**，**MVCC**，**快照读**，**当前读**


1. **transaction id**：InnoDB 里面每个事务有一个唯一的事务 ID，叫作 transaction id。它是在事务开始的时候向 InnoDB 的事务系统申请的，是按申请顺序严格递增的
> **TIPS**：
> 	只读事务不分配 id，是 5.6 以后的优化；其实也不是不分配 id，只是不分配自增的 id，随机分配的那个也是事务 id 的。

2. 每行数据也都是有多个版本的。每次事务更新数据的时候，都会生成一个新的数据版本，并且把 transaction id 赋值给这个数据版本的事务 ID，记为 row trx_id

   <img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1585993677745-417e690e-7d26-4363-90b2-adb23cf68956.png" alt="image.png" style="zoom: 80%;" />

3. **MySQL如何定义快照** 

​	使用一个数组保存事务启动的瞬间当前“活跃”事务的ID，最小值记为低水位，最大值加1记为高水位。

   1. 事务ID小于低水位：可见

   1. 事务ID大于高水位：不可见

   1. 其他情况
      1. 若 row `trx_id` 在数组中，表示这个事务版本是由还没提交的事务生成的，不可见
      
      1. 若 row `trx_id` 不在数组中，表示这个版本是已经提交了的事务生成的，可见
      
         <img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1585993717288-025bb79e-e499-4531-a61d-b7c80bd82e83.png" alt="image.png" style="zoom: 33%;" />
      
      查询逻辑
      
      <img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1586003901853-72de5685-2abb-4c21-bc16-ef3f93d50bfc.png" alt="image.png" style="zoom:50%;" />

> **TIPS**：
> 	同一行数据，最新版本的 row trx_id 是可能会小于旧版本的 row trx_id 的

4. 更新逻辑：更新数据都是先读后写的，而这个读，只能读当前的值，称为“当前读”（current read）。 `select xxx from xxx lock in share mode/for update`  也是当前读。
4. 在可重复读隔离级别下，只需要在事务开始的时候创建一致性视图，之后事务里的其他查询都共用这个一致性视图；在读提交隔离级别下，每一个语句执行前都会重新算出一个新的视图。
