CockroachDB 实现了一个无锁的乐观事务模型，事务冲突通过事务重启或者回滚尽快返回客户端，然后由客户端决策下一步如何处理。本文将重点解析 CockroachDB 的乐观事务模型的实现。

# MVCC（多版本并发控制）

在传统的单机数据库中，通常会使用一个单调递增的逻辑 ID 作为事务 ID，同时这个逻辑 ID 也起着 MVCC 实现中数据版本号的作用。我们在[《CockroachDB事务解密(一)》](https://mp.weixin.qq.com/s?__biz=MzI2MjQ5NTc1OQ==&mid=2247483985&idx=1&sn=97815dd6c06c1dd712449a98850cce23&chksm=ea4b0931dd3c8027e425b170f065a53d503df7cb276d29f1877c531c8209bff8f35983bb09ac&scene=21#wechat_redirect)中提到，CockroachDB 使用 HLC 时间追溯事务发生的先后顺序，为了实现 MVCC，CockroachDB 同时使用 HLC 时间戳作为数据的版本号。如下图：

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/640" alt="图片" style="zoom:50%;" />

对于已提交的数据，CockroachDB 把 HLC 时间戳 Encode 到 Key 的尾部作为版本号，降序存储。对于尚未提交或者刚提交的数据，此时 HLC 时间不会直接 Encode 到 Key 尾部，而是把事务相关的信息和数据一起 Encode 到 Value 中，称之为 WRITE INTENT，结构如下：

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20221218215138859.png" alt="image-20221218215138859" style="zoom:50%;" />

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20221218215151672.png" alt="image-20221218215151672" style="zoom:50%;" />

访问数据时，用当前事务的 HLC 时间和多版本数据中的 HLC 时间比较，返回 HLC 时间小于等于当前事务 HLC 时间，且 HLC 时间最大的版本数据。

# 事务原子性

我们知道，分布式事务可能会涉及到多条记录在多个节点上的写，CockroachDB 如何保证写的原子性？

CockroachDB 首先引入了一个全局事务表（全局事务表的数据亦采用分布式存储，使用随机产生的 UUID 作为事务记录的唯一标识；但是事务记录没有多版本信息，也就是每个事务记录只有一个版本，而且记录会定期被清理）记录事务执行状态。每个事务启动后，在事务执行第一次写时，同时往全局事务表中写入一条事务记录，记录当前事务状态。事务记录主要结构如下：

![image-20221218215304396](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20221218215304396.png)

* **UUID**：事务记录唯一标识符
* **Key**：事务记录的 Key，用来定位事务记录的位置
* **Timestamp**：事务提交时间
* **Status**：事务状态，PENDING、COMMITED、ABORTED



其次，事务写入的数据被封装成上文中提到的 WRITE INTENT，WRITE INTENT 中包含了指向当前事务记录的索引。事务初始状态是 PENDING，事务提交或者回滚只要修改事务记录的状态为 COMMITED 或者 ABORTED，然后返回结果给客户端即可。根据事务状态，遗留的 WRITE INTENT 会被异步清理：提交成功的数据则转换成前文中的多版本结构，被回滚则直接把 INTENT 清理掉。



当其他记录遇到 WRITE INTENT 时，根据 WRITE INTENT 中的事务记录索引信息反向查找事务记录：

1. 如果事务处于 PENDING 状态，则陷入写写冲突的场景，具体处理方式下文将详细解释；
2. 如果事务处于 COMMITED 状态，则进一步根据事务中 HLC 时间决定是返回 INTENT 中的数据还是返回上一个版本的数据；
3. 如果事务处于 ABORTED 状态，则返回上一个版本的数据。



同时，当前事务的协调者会为正在执行的事务记录保持心跳（通过定期刷新事务记录的 LastHeartbeat 字段），即使出现事务协调者 down 掉，也不会出现事务残留的情况。

简而言之，CockroachDB 利用 WRITE INTENT 和事务记录二者结合，保证事务写入的数据要么一起提交成功，要么一起回滚，实现事务原子操作。

# 事务隔离性

CockroachDB实现了两种隔离级别：***Snapshot Isolation*** 和 ***Serializable Snapshot*** ***Isolation***。

## Snapshot Isolation

Snapshot 隔离级别解决了脏读、不可重复读、幻读，但是不能解决 Write Skew 的问题。在上一篇文章[《CockroachDB事务解密(一)》](https://mp.weixin.qq.com/s?__biz=MzI2MjQ5NTc1OQ==&mid=2247483985&idx=1&sn=97815dd6c06c1dd712449a98850cce23&chksm=ea4b0931dd3c8027e425b170f065a53d503df7cb276d29f1877c531c8209bff8f35983bb09ac&scene=21#wechat_redirect)中我们阐述了CockroachDB 如何实现对已提交数据的 Snapshot Read。

对于未提交的数据 (WRITE INTENT)，在 Snapshot 隔离级别下，如果写入该 WRITE INTENT 的事务发生在当前读事务之后 (由于 Uncertain Read 和事务隔离级别没有直接关系，这里暂不考虑 Uncertain Read，关于 Uncertain Read 的处理方式可参考[《CockroachDB事务解密(一)》](https://mp.weixin.qq.com/s?__biz=MzI2MjQ5NTc1OQ==&mid=2247483985&idx=1&sn=97815dd6c06c1dd712449a98850cce23&chksm=ea4b0931dd3c8027e425b170f065a53d503df7cb276d29f1877c531c8209bff8f35983bb09ac&scene=21#wechat_redirect))，通过 MVCC 往前读取合适的版本；

==如果写入该 WRITE INTENT 的事务发生在当前读事务之前且尚未提交，那么读事务会把该写事务的时间戳修改为当前读事务之后，保证不会出现不可重复读和幻读。==（TIPS：读操作会推高事务 commit 的时间戳）

对于 Snapshot 隔离级别的写写冲突，如果当前写事务遇到一个尚未提交的 WRITE INTENT，比较当前事物和写入 WRITE INTENT 的事务的优先级，优先级低的事务被终止并重启；如果当前事务遇到一个已提交的 WRITE INTENT，且写入 WRITE INTENT 的事务发生在当前事务之后，则当前事务终止并重启。

## Serializable Snapshot Isolation

Serializable 隔离级别在 Snapshot 隔离级别的基础上进一步解决了 Write Skew 的问题，但是在多数据库系统中都不支持或者不建议使用 Serializable 隔离级别，最重要的原因是性能过于低下。CockroachDB 为了实现 Serializable 隔离级别进行了大量的优化，并且把默认隔离级别设置为 Serializable 隔离级别。CockroachDB 提供了一个高性能的 Serializable 隔离级别。



CockroachDB 基于 Serializability Graph 理论实现 Serializable 隔离级别。该理论定义了三种冲突（**注：三种冲突皆指不同事务操作同一数据引起的冲突**）：

1. **RW**: W 覆盖了 R 读到的值
2. **WR**: R 读到了 W 更新的值
3. **WW**: W 覆盖了第一个 W 更新的值

若事务 T1 对事务 T2 造成上述任意一种冲突，则可认为从 T1 向 T2 存在一条冲突关系的有向边；若事务之间的冲突关系形成回环，则意味着这些事务不可串行化。如下图中事务 T1、T2、T3 则不可串行化：

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20221218215813274.png" alt="image-20221218215813274" style="zoom:67%;" />

CockroachDB 通过如下约束来保证事务之间的冲突不会形成冲突回环，保证事务的可串行化调度:

1. 同一事务的 R/W 统一使用事务启动时的时间戳。

2. ==RW: W 的时间戳只能比 R 的大==：

   CockroachDB 在每个节点会维护一个 Read Timestamp Cache，对当前节点所有数据的读时间戳都会被记录下来。当 W 在 Read Timestamp Cache 发现 R 的时间戳更大时，W 事务被重启。

3. ==WR: R 只读比自身 Timestamp 小的最大的版本==：

   MVCC 机制保证 R 不会去读比自己 Timestamp 大的数据。其次若 R 遇到 Timstamp 比自身小但是未提交的 WRITE INTENT，比较二者之间的事务优先级，优先级低的事务被重启。

4. ==WW:第二个 W 的 Timestamp 比第一个 W 的 Timestamp 大==：

   如果 W 遇到一个比自身 Timestamp 大且已提交的 WRITE INTENT，W 以一个更大的时间戳重启事务。如果遇到 Timestamp 更大但未提交 WRITE INTENT，比较二者之间的事务优先级，优先级低的事务被重启。

5. Strict scheduling：读写操作只能作用在已提交的数据之上。

   也就是说，只要保证事务只与比自身 Timestamp 更小的事务冲突，就能保证无环。

最终上文中的事务冲突被转换成如下图：

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20221218220044277.png" alt="image-20221218220044277" style="zoom:67%;" />

# 两阶段事务

CockroachDB 实现的是一个无锁的两阶段提交事务模型，事务冲突通过事务重启或者回滚尽快返回客户端由客户端决策下一步如何处理。事务重启会以新的 HLC 时间戳和优先级重新执行，可以复用事务 ID，由系统内部自动重新调度。事务回滚则直接废弃当前事务上下文，尽快将控制权返回客户端，客户端重新执行事务时将以新的事务上下文执行。CockroachDB 两阶段事务具体执行过程如下所示：

![image-20221218220127082](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20221218220127082.png)

1. 产生事务记录，事务状态为 PENDING，也就是 BeginTransactoin。
2. 参与节点以 WRITE INTENT 的形式写入数据，并返回候选时间戳。
3. 比较候选时间戳和事务起始时间戳是否相等，以及事务隔离级别，决定事务状态被修改为 COMMITED 还是 ABORTED。
4. 事务提交/回滚之后，残留的 WRITE INTENT 将被异步清理。
5. 通常情况下会选择事务中遇到的第一个写操作的 Key 作为事务记录的 Key，此时才会真正把事务记录持久化到事务记录表中。这样做的好处是，对于只读事务不需要记录事务状态。

# 一阶段事务

从上文可以看到，CockroachDB 的两阶段事务可能需要经过多次的网络交互才能完成事务的提交。为了提升事务处理性能，CockroachDB 针对事务所有的写都落在一个 Range 的场景做了优化，称之为 Fast 1PC。

其主要思路是，一次把所有写操作提交到 Raft Leader，由 Raft 来保证这一批写操作的原子性。这样就不需要产生事务记录和 INTENT，减少 RPC 交互。

# 总结

CockroachDB 实现了一个高效的无锁乐观事务模型，相比经典的两阶段实现，在第二阶段只需要修改事务记录状态即可，不需要同步参与者的执行状态以及锁管理,事务提交和回滚代价小；任一节点挂掉仍然能保证事务的一致性。同时不需要中心节点协调事务，任一节点都可临时充当事务协调者。对于数据竞争比较激烈的场景，事务频繁 restart 的开销会相对较大。



---

https://mp.weixin.qq.com/s/39hPkoFZonWajhFWE41tVA