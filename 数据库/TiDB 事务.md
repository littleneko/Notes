## Percolator

Percolator 是 Google 的上一代分布式事务解决方案，构建在 BigTable 之上，在 Google 内部 用于网页索引更新的业务，原始的论文 [在此 ](http://research.google.com/pubs/pub36726.html)。原理比较简单，总体来说就是一个经过优化的二阶段提交的实现，进行了一个二级锁的优化。TiDB 的事务模型沿用了 Percolator 的事务模型。 

总体来说，TiKV 的读写事务分为两个阶段：1、Prewrite 阶段；2、Commit 阶段。

客户端会缓存本地的写操作，在客户端调用 client.Commit() 时，开始进入分布式事务 prewrite 和 commit 流程。

**Prewrite 对应传统 2PC 的第一阶段**：

1. 首先在所有行的写操作中选出一个作为 primary row，其他的为 secondary rows

2. Prewrite Primary：对 primaryRow 写入锁（修改 meta key 加入一个标记），锁中记录本次事务的开始时间戳。上锁前会检查：

   - 该行是否已经有别的客户端已经上锁 (Locking)
   - 是否在本次事务开始时间之后，检查 versions ，是否有更新 [startTs, +Inf) 的写操作已经提交 (Conflict)

   在这两种种情况下会返回事务冲突。否则，就成功上锁。将行的内容写入 row 中，版本设置为 startTs

3. 将 primaryRow 的锁上好了以后，进行 secondaries 的 prewrite 流程：

   - 类似 primaryRow 的上锁流程，只不过锁的内容为事务开始时间 startTs 及 primaryRow 的信息
   - 检查的事项同 primaryRow 的一致
   - 当锁成功写入后，写入 row，时间戳设置为 startTs

以上 Prewrite 流程任何一步发生错误，都会进行回滚：删除 meta 中的 Lock 标记 , 删除版本为 startTs 的数据。

当 Prewrite 阶段完成以后，进入 Commit 阶段，当前时间戳为 commitTs，TSO 会保证 commitTs > startTs

**Commit 的流程是，对应 2PC 的第二阶段**：

1. commit primary: 写入 meta 添加一个新版本，时间戳为 commitTs，内容为 startTs, 表明数据的最新版本是 startTs 对应的数据
2. 删除 Lock 标记

值得注意的是，如果 primary row 提交失败的话，全事务回滚，回滚逻辑同 prewrite 失败的回滚逻辑。

如果 commit primary 成功，则可以异步的 commit secondaries，流程和 commit primary 一致， 失败了也无所谓。Primary row 提交的成功与否标志着整个事务是否提交成功。

**事务中的读操作**：

1. 检查该行是否有 Lock 标记，如果有，表示目前有其他事务正占用此行，如果这个锁已经超时则尝试清除，否则等待超时或者其他事务主动解锁。注意此时不能直接返回老版本的数据，否则会发生幻读的问题。
2. 读取至 startTs 时该行最新的数据，方法是：读取 meta ，找出时间戳为 [0, startTs], 获取最大的时间戳 t，然后读取为于 t 版本的数据内容。

由于锁是分两级的，Primary 和 Seconary row，只要 Primary row 的锁去掉，就表示该事务已经成功提交，这样的好处是 Secondary 的 commit 是可以异步进行的，只是在异步提交进行的过程中，如果此时有读请求，可能会需要做一下锁的清理工作。因为即使 Secondary row 提交失败，也可以通过 Secondary row 中的锁，找到 Primary row，根据检查 Primary row 的 meta，确定这个事务到底是被客户端回滚还是已经成功提交。



# 乐观锁

# 悲观锁



https://pingcap.com/zh/blog/tidb-transaction-model

https://pingcap.com/zh/blog/percolator-and-txn