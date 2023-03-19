# 事务模型

Percolator 是 Google 的上一代分布式事务解决方案，构建在 BigTable 之上，在 Google 内部用于网页索引更新的业务，原始的论文 [在此 ](http://research.google.com/pubs/pub36726.html)。原理比较简单，总体来说就是一个经过优化的二阶段提交的实现，进行了一个二级锁的优化，TiDB 的事务模型沿用了 Percolator 的事务模型。 

总体来说，TiKV 的读写事务分为两个阶段：1、Prewrite 阶段；2、Commit 阶段。

客户端会缓存本地的写操作，在客户端调用 `client.Commit()` 时，开始进入分布式事务 Prewrite 和 Commit 流程。



**Prewrite 对应传统 2PC 的第一阶段**：

1. 首先在所有行的写操作中选出一个作为 PrimaryRow，其他的为 SecondaryRows

2. Prewrite Primary：对 PrimaryRow ==写入锁==（修改 meta key 加入一个标记），==锁中记录本次事务的开始时间戳==。上锁前会检查：

   - 该行是否已经有别的客户端已经上锁 (Locking)
   - 是否在本次事务开始时间之后，有更新 `[startTs, +Inf)` 的写操作已经提交 (Conflict)

   在这两种种情况下会返回事务冲突，否则就成功上锁，将行的内容写入 row 中，版本设置为 `startTs`

3. 将 PrimaryRow 的锁上好了以后，进行 SecondaryRows 的 Prewrite 流程：

   - 类似 PrimaryRow 的上锁流程，只不过锁的内容为事务开始时间 `startTs` 及 PrimaryRow 的信息
   - 检查的事项同 PrimaryRow 的一致
   - 当锁成功写入后，写入 row，时间戳设置为 `startTs`

以上 Prewrite 流程任何一步发生错误，都会进行回滚：删除 meta 中的 Lock 标记 , 删除版本为 startTs 的数据。



**Commit 对应传统 2PC 的第二阶段**：

当 Prewrite 阶段完成以后，进入 Commit 阶段，当前时间戳为 `commitTs`，TSO 会保证 commitTs > startTs

1. Commit Primary：写入 meta 添加一个新版本，时间戳为 `commitTs`，内容为 `startTs`，表明数据的最新版本是 startTs 对应的数据
2. 删除 Lock 标记

值得注意的是，如果 Primary Row 提交失败的话，全事务回滚，回滚逻辑同 Prewrite 失败的回滚逻辑。

如果 Commit Primary 成功，则可以异步的 Commit SecondaryRows，流程和 Commit Primary 一致， 失败了也无所谓，PrimaryRow 提交的成功与否标志着整个事务是否提交成功。



**事务中的读操作**：

1. 检查该行是否有 Lock 标记，如果有，表示目前有其他事务正占用此行，如果这个锁已经超时则尝试清除，否则等待超时或者其他事务主动解锁。==注意此时不能直接返回老版本的数据，否则会发生幻读的问题==。
2. 读取至 startTs 时该行最新的数据，方法是：读取 meta，找出时间戳为 `[0, startTs]`，获取最大的时间戳 t，然后读取为于 t 版本的数据内容。

由于锁是分两级的，Primary 和 Seconary Row，只要 Primary Row 的锁去掉，就表示该事务已经成功提交，这样的好处是 Secondary 的 Commit 是可以异步进行的，只是在异步提交进行的过程中，如果此时有读请求，可能会需要做一下锁的清理工作。因为即使 Secondary Row 提交失败，也可以通过 Secondary Row 中的锁，找到 Primary Row，根据检查 Primary Row 的 meta，确定这个事务到底是被客户端回滚还是已经成功提交。



通过 MVCC， TiKV 的事务默认隔离级别是 Repeatable Read (SI), 也对外暴露显式的加锁的 API，用于为客户端实现 SELECT … FOR UPDATE 等隔离级别为 SSI 的语句。

大家可以看到， 本质上 TiKV 的事务模型是基于 Percolator 的思想，但是对比原论文，做了很多工程上的优化，我们将原来论文中的 L 列和 W 列去掉，通过和MVCC 的 Meta 来存储相关的事务信息。

# 乐观事务

## 实现

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1_b7759a4dac.png" alt="img" style="zoom: 67%;" />

**TiDB 在处理一个事务时，处理流程如下**：

1. 客户端 begin 了一个事务。

   a. TiDB 从 PD 获取一个全局唯一递增的版本号作为当前事务的开始版本号，这里我们定义为该事务的 `start_ts`。

2. 客户端发起读请求。

   a. TiDB 从 PD 获取数据路由信息，数据具体存在哪个 TiKV 上。

   b. TiDB 向 TiKV 获取 `start_ts` 版本下对应的数据信息。

3. 客户端发起写请求。

   a. ==TiDB 对写入数据进行校验，如数据类型是否正确、是否符合唯一索引约束等，确保新写入数据事务符合一致性约束==，**将检查通过的数据存放在内存里**。

4. 客户端发起 commit。

5. TiDB 开始两阶段提交将事务原子地提交，数据真正落盘。

   a. TiDB 从当前要写入的数据中选择一个 Key 作为当前事务的 Primary Row。

   b. TiDB 从 PD 获取所有数据的写入路由信息，并将所有的 Key 按照所有的路由进行分类。

   c. TiDB 并发向所有涉及的 TiKV 发起 prewrite 请求，TiKV 收到 prewrite 数据后，==检查数据版本信息是否存在冲突、过期，符合条件给数据加锁==。

   d. TiDB 收到所有的 prewrite 成功。

   e. ==TiDB 向 PD 获取第二个全局唯一递增版本，作为本次事务的 `commit_ts`。==

   f. TiDB 向 Primary Key 所在 TiKV 发起第二阶段提交 commit 操作，TiKV 收到 commit 操作后，检查数据合法性，清理 prewrite 阶段留下的锁。

   g. TiDB 收到 f 成功信息。

6. TiDB 向客户端返回事务提交成功。

7. TiDB 异步清理本次事务遗留的锁信息。



**缺点如下**：

* 两阶段提交，网络交互多。
* 需要一个中心化的版本管理服务。
* 事务在 commit 之前，数据写在内存里，数据过大内存就会暴涨。



> **TIPS**:
>
> 关于唯一性约束检查：在上面的描述中，TiDB 是在客户端写入数据的时候在 TiDB 层检查的，在 OCC 事物模型中，这里的检查只是对 snapshot 版本进行检查并且不会加锁。如果检查的时候没有违反唯一性约束，但是等到事物提交的时候，如果这个 Key 已经被其他事物写入了，那么因为这行数据的在 [start_ts, commit_ts] 之间已经被修改过了，因此在 prewrite 阶段会检测出版本冲突。



## 事务大小

为了降低网络交互对于小事务的影响，我们建议小事务打包来做。



既然小事务有问题，我们的事务是不是越大越好呢？当事务过大时，会有以下问题：

* 客户端 commit 之前写入数据都在内存里面，TiDB 内存暴涨，一不小心就会 OOM。
* ==第一阶段写入与其他事务出现冲突的概率就会指数级上升，事务之间相互阻塞影响。==
* 事务的提交完成会变得很长很长



## 事务冲突

### 默认冲突行为

我们这边来分析一下乐观事务下，TiDB 的行为。默认配置下，以下并发事务存在冲突时，结果如下：

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/table_1_d5df660172.png" alt="img" style="zoom:50%;" />

在这个 case 中，现象分析如下：

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/2_e5374da6f3.png" alt="img" style="zoom:67%;" />

- 如上图，事务 A 在时间点 `t1` 开始事务，事务 B 在事务 `t1` 之后的 `t2` 开始。
- 事务 A、事务 B 会同时去更新同一行数据。
- 时间点 `t4` 时，事务 A 想要更新 `id = 1` 的这一行数据，虽然此时这行数据在 `t3` 这个时间点被事务 B 已经更新了，但是因为 TiDB 乐观事务只有在事务 commit 时才检测冲突，所以时间点 `t4` 的执行成功了。
- 时间点 `t5`，事务 B 成功提交，数据落盘。
- 时间点 `t6`，事务 A 尝试提交，检测冲突时发现 `t1` 之后有新的数据写入，返回冲突，事务 A 提交失败，提示客户端进行重试。

根据乐观锁的定义，这样做完全符合逻辑。

### 重试机制

那么重试是不是万能的呢？这要从重试的原理出发，重试的步骤：

1. 重新获取 start_ts。
2. 对带写入的 SQL 进行重放。
3. 两阶段提交。

细心如你可能会发现，我们这边==只对写入的 SQL 进行回放，并没有提及读取 SQL==。这个行为看似很合理，但是这个会引发其他问题：

1. start_ts 发生了变更，当前这个事务中，读到的数据与事务真正开始的那个时间发生了变化，写入的版本也是同理变成了重试时获取的 start_ts 而不是事务一开始时的那个。
2. ==如果当前事务中存在更新依赖于读到的数据，结果变得不可控==。

打开了重试后，我们来看下面的例子：

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/table_2_edd7ad784f.png" alt="img" style="zoom:50%;" />

我们来详细分析以下这个 case：

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/3_ff034321bb.png" alt="img" style="zoom: 67%;" />

* 如图，在 session B 在 t2 开始事务 2，t5 提交成功。session A 的事务 1 在事务 2 之前开始，在事务 n2 提交完成后提交。

* 事务 1、事务 2 会同时去更新同一行数据。

* session A 提交事务 1 时，发现冲突，tidb 内部重试事务 1。

  * 重试时，重新取得新的 start_ts 为 t8’。

  * 回放更新语句 update tidb set name='pd' where id =1 and status=1。 i. 发现当前版本 t8’ 下并不存在符合条件的语句，不需要更新。 ii. 没有数据更新，返回上层成功。

* tidb 认为事务 1 重试成功，返回客户端成功。

* session A 认为事务执行成功，查询结果，在不存在其他更新的情况下，发现数据与预想的不一致。

这里我们可以看到，==对于重试事务，如果本身事务中更新语句需要依赖查询结果时，因为重试时会重新取版本号作为 start_ts，因而无法保证事务原本的 ReadRepeatable 隔离型，结果与预测可能出现不一致==。

# 悲观事务

## 为什么需要悲观事务

对于很多普通的互联网场景，虽然并发量和数据量都很大，但是冲突率其实并不高。举个简单的例子，比如电商的或者社交网络，刨除掉一些比较极端的 case 例如「秒杀」或者「大V」，访问模式基本可以认为还是比较随机的，而且在互联网公司中很多这些极端高冲突率的场景都不会直接在数据库层面处理，大多通过异步队列或者缓存在来解决，这里不做过多展开。

但是对于一些传统金融场景，由于种种原因，==会有一些高冲突率但是又需要保证严格的事务性的业务场景==。举个简单的例子：发工资，对于一个用人单位来说，发工资的过程其实就是从企业账户给多个员工的个人账户转账的过程，一般来说都是批量操作，在一个大的转账事务中可能涉及到成千上万的更新，想象一下如果这个大事务执行的这段时间内，某个个人账户发生了消费（变更），如果这个大事务是乐观事务模型，提交的时候肯定要回滚，涉及上万个个人账户发生消费是大概率事件，如果不做任何处理，最坏的情况是这个大事务永远没办法执行，一直在重试和回滚（饥饿）。

另外一个更重要的理由是，有些业务场景，悲观事务模型写起来要更加简单。此话怎讲？

因为 TiDB 支持 MySQL 协议，在 MySQL 中是支持可交互事务的，例如一段程序这么写（伪代码）：

```
mysql.SetAutoCommit(False);
txn = mysql.Begin();
affected_rows = txn.Execute(“UPDATE t SET v = v + 1 WHERE k = 100”);
if affected_rows > 0 {
    A();
} else {
    B();
}
txn.Commit();
```

大家注意下，第四行那个判断语句是直接通过上面的 UPDATE 语句返回的 affected_rows 来决定到底是执行 A 路径还是 B 路径，但是聪明的朋友肯定看出问题了，==在一个乐观事务模型的数据库上，在 COMMIT 执行之前，其实是并不知道最终 affected_rows 到底是多少的，所以这里的值是没有意义的==，程序有可能进入错误的处理流程。这个问题在只有乐观事务支持的数据库上几乎是无解的，需要在业务侧重试。

这里的问题的本质是 MySQL 的协议支持可交互事务，但是 MySQL 并没有原生的乐观事务支持（MySQL InnoDB 的行锁可以认为是悲观锁），所以原生的 MySQL 在执行上面这条 UPDATE 的时候会先上锁，确认自己的 Update 能够完成才会继续，所以返回的 affected_rows 是正确的。

## 实现

TiDB 悲观锁复用了乐观锁的两阶段提交逻辑，重点在 DML 执行时做了改造。在两阶段提交之前增加了 Acquire Pessimistic Lock 阶段，简要步骤如下：

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/0f9d1887996012ca6591cb85cd77939fd1fc609e_2_1380x628.jpeg" alt="image" style="zoom: 33%;" />

- 【与乐观锁共用】TiDB 收到来自客户端的 begin 请求，获取当前版本号作为本事务的 StartTS
- ==TiDB 收到来自客户端的更新数据的请求: TiDB 向 TiKV 发起加悲观锁请求，该锁持久化到 TiKV==。
- 【与乐观锁共用】client 发起 commit ，TiDB 开始执行与乐观锁一样的两阶段提交。

有了以上大致的印象后，我们具体来看看悲观锁事务的执行流程细节：

![image](https://littleneko.oss-cn-beijing.aliyuncs.com/img/922136bc7d53c260cfcabb5e9dd5f69aeb9a60bf.jpeg)

悲观锁只有一个地方有区别，即如上图红色框内，在 TiDB 收到写入请求后，TiDB 按照如下方式开始加锁：

1. 从 PD 获取当前 tso 作为当前锁的 `for_update_ts`
2. TiDB 将写入信息写入 TiDB 的内存中（与乐观锁相同）
3. 使用 `for_update_ts` 并发地对所有涉及到的 Key 发起加悲观锁（acquire pessimistic lock）请求
4. 如果加锁成功，TiDB 向客户端返回写成功的请求
5. 如果加锁失败
6. 如果遇到 Write Conflict， 重新回到步骤 1 直到加锁成功。
7. 如果超时或其他异常，返回客户端异常信息



TiDB 的悲观锁实现的原理确实如此，在一个事务执行 DML (UPDATE/DELETE) 的过程中，TiDB 不仅会将需要修改的行在本地缓存，同时还会对这些行直接上悲观锁，==这里的悲观锁的格式和乐观事务中的锁几乎一致，但是锁的内容是空的，只是一个占位符，待到 Commit 的时候，直接将这些悲观锁改写成标准的 Percolator 模型的锁，后续流程和原来保持一致即可==，唯一的改动是：

==**对于读请求，遇到这类悲观锁的时候，不用像乐观事务那样等待解锁，可以直接返回最新的数据即可**==（至于为什么，读者可以仔细想想）。

至于写请求，遇到悲观锁时，只需要和原本一样，正常的等锁就好。

这个方案很大程度上兼容了原有的事务实现，扩展性、高可用和灵活性都有保证（基本复用原来的 Percolator 自然没有问题）。

## 对谁加悲观锁

在实现悲观锁的时候，我们根据不同的 DML 类型，制定了不同的加锁规则，旨在实现悲观锁逻辑的基础上，加更少的锁，实现更高的性能。目前加锁规则如下：

- 插入（ Insert）
  - 如果存在唯一索引，对应唯一索引所在 Key 加锁
  - 如果表的主键不是自增 ID，跟索引一样处理，加锁。
- 删除（Delete）
  - RowID 加锁
- 更新（update）
  - 对旧数据的 RowID 加锁
  - 如果用户更新了 RowID，加锁新的 RowID
  - 对更新后数据的唯一索引都加锁

## 如何加悲观锁

本章我们来仔细了解一下，TiKV 中 acquire pessimistic lock 接口的具体处理逻辑，具体步骤如下：

- 检查 TiKV 中锁情况，如果发现有锁
  - 不是当前同一事务的锁，返回 KeyIsLocked Error
  - 锁的类型不是悲观锁，返回锁类型不匹配（意味该请求已经超时）
  - 如果发现 TiKV 里锁的 `for_update_ts` 小于当前请求的 `for_update_ts` (同一个事务重复更新)， 使用当前请求的 `for_update_ts` 更新该锁
  - 其他情况，为重复请求，直接返回成功
- 检查是否存在更新的写入版本，如果有写入记录
  - 若已提交的 `commit_ts` 比当前的 `for_update_ts` 更新，说明存在冲突，返回 WriteConflict Error
  - 如果已提交的数据是当前事务的 Rollback 记录，返回 PessimisticLockRollbacked 错误
  - 若已提交的 `commit_ts` 比当前事务的 `start_ts` 更新，说明在当前事务 begin 后有其他事务提交过
    - 检查历史版本，如果发现当前请求的事务有没有被 Rollback 过，返回 PessimisticLockRollbacked 错误
- 给当前请求 key 加上悲观锁，并返回成功

以上便是悲观锁请求加锁的一个全过程。

## 死锁

但是引入悲观锁和可交互式事务，就可能引入另外一个问题：死锁。这个问题其实在乐观事务模型下是不存在的，因为已知所有需要加锁的行，所以可以按照顺序加锁，就自然避免了死锁（实际 TiKV 的实现里，乐观锁不是顺序加的锁，是并发加的锁，只是锁超时时间很短，死锁也可以很快重试）。但是悲观事务的上锁顺序是不确定的，因为是可交互事务，举个例子：

* 事务 1 操作顺序：UPDATE A，UPDATE B
* 事务 2 操作顺序：UPDATE B，UPDATE A

这俩事务如果并发执行，就可能会出现死锁的情况。

所以为了避免死锁，TiDB 需要引入一个死锁检测机制，而且这个死锁检测的性能还必须好。其实死锁检测算法也比较简单，只要保证正在进行的悲观事务之间的依赖关系中不能出现环即可。

# Links

1. TiKV 事务模型概览，Google Spanner 开源实现: https://pingcap.com/zh/blog/tidb-transaction-model
2. TiDB 最佳实践系列（三）乐观锁事务: https://cn.pingcap.com/blog/best-practice-optimistic-transaction
3. TiDB 新特性漫谈：悲观事务: https://cn.pingcap.com/blog/pessimistic-transaction-the-new-features-of-tidb
4. TiDB 悲观锁实现原理： https://tidb.net/blog/7730ed79