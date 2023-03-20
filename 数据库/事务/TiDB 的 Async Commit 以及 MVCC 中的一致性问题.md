# Overview

在 TiDB 的官方博客《[事务前沿研究丨事务并发控制](https://cn.pingcap.com/blog/transaction-frontiers-research-article-talk4)》中，有一个关于 MVCC 中不可重复读的问题，具体问题描述如下：

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/8_e2dd7c0dbe.png" alt="8.png" style="zoom: 50%;" />

<center>图8 - MVCC 中的一致性问题</center>

MVCC 通过一个快照去读取相同的数据是一个很理想的想法，但是图 8 描述了 MVCC 中的一致性问题，如果一个事务在 Commit 过程中另一个事务用更新的 ts 进行读，那么对于尚未存在的数据，MVCC 无法正确处理，导致出现**不可重复读**的现象。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/9_b2df1938b4.png" alt="9.png" style="zoom:50%;" />

<center>图9 - MVCC min_commit_ts 实现一致读</center>

为了解决这个图 8 的问题，MVCC 有两种办法，图 9 在系统中加入了一个约束，也是 TiDB 所使用的方法，==写事务的 ts 必须大于所有与之相交的读事务==，在实现中会让读事务推高 key 上的 `min_commit_ts = read_ts + 1`，在提交时候需要计算 `commit_ts = max{commit_ts, min_commit_ts}`，图 9 中，`ts=2` 的第一次读取将 `min_commit_ts` 推高到 3，进而让写事务写入的版本不影响 `ts=2` 的重复读取。

# TiDB 事务的实现

上面问题的本质是因为事务 T1 进入提交流程后，==有一个比当前事务时间戳更高的读事务 T2 进来了==，T2 第一次读的时候因为 T1 还没写 x，因此读的是老版本的 x 值；但是当 T1 成功提交后，T2 再次读就可以读到 x 的新值了，造成了不可重复读。

## TiDB 4.0 前的实现

我们来看看 TiDB 的事务实现，TiDB 的事务实现类似于 Percolator，其总体流程分为 Prewrite 和 Commit 两个阶段：

1. **Prewrite**：检查锁和数据冲突，并对需要写入的数据上锁
2. **Commit**：从 TSO 获取一个 `commit_ts` 作为本次事务的时间戳，提交事务并释放锁

对于读操作：

1. ==检查该行是否有 Lock 标记==，如果有，表示目前有其他事务正占用此行，如果这个锁已经超时则尝试清除，否则等待超时或者其他事务主动解锁。==注意此时不能直接返回老版本的数据，否则会发生幻读的问题==。
2. 读取至 startTs 时该行最新的数据，方法是：读取 meta，找出时间戳为 `[0, startTs]`，获取最大的时间戳 t，然后读取为于 t 版本的数据内容。



如果图 8 中的情况发生，那读事务 T2 的时间戳一定是在 Commit 阶段拿到 commit_ts 后，读操作也在拿到 commit_ts 后，事务 T1 提交完成之前，也就是说 T2 读的时候 x 上一定还有 T1 加的锁没释放，此时读事务 T2 会等锁，并不会直接读老版本的数据，因此不会有图 8 中的情况发生。

既然如此，TiDB 的博客为什么还说 TiDB 为了解决这个问题使用读事务推高 min_commit_ts 的方法呢？实际上，上面所说的 TiDB 事务提交的流程是在 TiDB 5.0 之前的实现。在 TiDB 5.0 中实现了 Async Commit，与之前的方案最大的区别是：事务的 commit_ts 不再是从 TSO 获取，而是在 Prewrite 阶段就确定了。

##  Async Commit

引入 Async Commit 之前，事务的 primary key 被提交才意味着这个事务被提交。Async Commit 力图实现的，就是把确定事务状态的时间提前到完成 prewrite 的时候，==让整个提交的第二阶段都异步化进行==。也就是说，==对于 Async Commit 事务，只要事务所有的 keys 都被成功 prewrite，就意味着事务提交成功==。

下图是 Async Commit 事务的提交流程（你可能发现==原来获取 Commit TS 的环节没有了，在 prewrite 前多了从 PD 获取时间戳作为 Min Commit TS 的操作==）：

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/2_bf4c3e920b.png" alt="2" style="zoom:50%;" />

### 如何确定事务的 Commit TS

Async Commit 事务的状态在 prewrite 完成时就必须确定了，Commit TS 作为事务状态的一部分也不例外。

默认情况下，TiDB 事务满足快照隔离的隔离级别和线性一致性。我们希望这些性质对于 Async Commit 事务同样能够成立，那么确定合适的 Commit TS 非常关键。

==对于 Async Commit 事务的每一个 key，prewrite 时会计算并在 TiKV 记录这个 key 的 Min Commit TS，事务所有 keys 的 Min Commit TS 的最大值即为这个事务的 Commit TS==。

下文会介绍 Min Commit TS 的计算方式，以及它们是如何使 Async Commit 事务满足快照隔离和线性一致性的。

#### 保证快照隔离

TiDB 通过 MVCC 实现快照隔离，事务在开始时会向 TSO 获取 Start TS，为实现快照隔离，我们要保证以 Start TS 作为快照时间戳始终能读取到一个一致的快照。

为此，==TiDB 的每一次快照读都会更新 TiKV 上的 Max TS==。Prewrite 时，Min Commit TS 会被要求至少比当前的 Max TS 大，也就是比所有先前的快照读的时间戳大，所以可以==取 Max TS + 1 作为 Min Commit TS==。在这个 Async Commit 事务提交成功后，由于==其 Commit TS 比之前的快照读的时间戳大，所以不会破坏快照隔离==。

下面的例子中，事务 T1 要写 x 和 y 两个 keys。T2 读取 y 将 Max TS 更新到 5，所以接下来 T1 prewrite y 时，Min Commit TS 至少为 6。T1 prewrite y 成功即意味着 T1 提交成功，而 T1 的 Commit TS 至少为 6。所以之后 T2 再读取 y 时，不会读取到 T1 更新的值，事务 T2 的快照保持了一致。

| **T1: Begin (Start TS = 1)**             |                               |
| ---------------------------------------- | ----------------------------- |
| **T1: Prewrite(x)**                      | **T2: Begin (Start TS = 5)**  |
|                                          | **T2: Read(y) => Max TS = 5** |
| **T1: Prewrite(y) => Min Commit TS = 6** |                               |
|                                          | **T2: Read(y)**               |

> **TIPS**:
>
> 如果读不推高 Max TS 会发生什么？假设事务 T1 进入提交流程，从 TSO 上获取了一个时间戳作为其 Min Commit TS，然后读事务 T2 从 TSO 获取了一个新的时间戳作为其 Read TS（Resd TS 一定比 Min Commit TS 大），T2 开始读 x，T1 对 x 加锁。因为在 T1 从 TSO 拿时间戳和对 x 加锁之间有个 GAP，这个时间段内的读是可以读到旧版本的数据的。
>
> 假设读不推高 min_commit_ts：
>
> | T1                                      | T2                   |
> | --------------------------------------- | -------------------- |
> | Write(x, 2)                             |                      |
> | Prewrite: (min_commit_ts = 10)          |                      |
> |                                         | Begin (read_ts = 15) |
> |                                         | Read(x, read_ts) = 1 |
> | Prewrite: Lock Row                      |                      |
> | Prewrite END: commit_ts = min_commit_ts |                      |
> | Commit Txn and Unlock Row               |                      |
> |                                         | Read(x, read_ts) = 2 |
>
> 可以看到，T2 出现了不可重复读，如果 T2 的 Read 在 T1 Lock Row 之后发生，就会等锁，不会出现不可重复读的情况。

#### 保证线性一致性

线性一致性实际上有两方面的要求：

- **循序性**（sequential）
- **实时性**（real-time）

实时性要求在事务提交成功后，事务的修改立刻就能被新事务读取到。==新事务的快照时间戳是向 PD 上的 TSO 获取的，这要求 Commit TS 不能太大，最大不能超过 TSO 分配的最大时间戳 + 1==。

在快照隔离一节提到，Min Commit TS 的一个可能的取值是 Max TS + 1。用于更新 Max TS 的时间戳都来自于 TSO，==所以 Max TS + 1 必然小于等于 TSO 上未分配的最小时间戳==。除了 TiKV 上的 Max TS 之外，协调者 TiDB 也会提供 Min Commit TS 的约束，但也不会使其超过 TSO 上未分配的最小时间戳。



循序性要求逻辑上发生的顺序不能违反物理上的先后顺序。具体地说，有两个事务 T1 和 T2，如果在 T1 提交后，T2 才开始提交，那么逻辑上 T1 的提交就应该发生在 T2 之前，也就是说 T1 的 Commit TS 应该小于 T2 的 Commit TS。

==为了保证这个特性，TiDB 会在 prewrite 之前向 PD TSO 获取一个时间戳作为 Min Commit TS 的最小约束。由于前面实时性的保证，T2 在 prewrite 前获取的这个时间戳必定大于等于 T1 的 Commit TS==，而这个时间戳也不会用于更新 Max TS，所以也不可能发生等于的情况。综上我们可以保证 T2 的 Commit TS 大于 T1 的 Commit TS，即满足了循序性的要求。

综上所述，每个 key 的 Min Commit TS 取 prewrite 时的 Max TS + 1 和 prewrite 前从 PD 获取的时间戳的最大值，事务的 Commit TS 取所有 key 的 Min Commit TS 的最大值，就能够同时保证快照隔离和线性一致性。

# HLC 实现

在基于 HLC 的实现中，因为没有 TSO 可以保证获取全局最大的 commit_ts 作为事务时间戳，一般生成 commit_ts 的方法类似于 TiDB 的 Async Commit 中的流程。区别在于 Min Commit TS 不是从中心节点获取的，而是直接使用 HLC 获取。在 prewrite 时会记录并计算所有 key 的 Min Commit TS，取其最大值作为事务的 Commit TS。

可以看到 HLC 的实现中，事务的 Commit TS 也是在 prewrite 阶段就确定的，因此也必须要读推高节点的 Max TS，prewrite 时取 Max TS + 1 作为 Min Commit TS，这样才能保证快照隔离级别（防止不可重复读发生）。

> **TIPS**:
>
> 1. 可以看到，HLC 的实现天然就支持了将整个提交的第二阶段异步化进行，因为其在 prewrite 结束后就可以得到事务的 Commit TS 了。
> 2. HLC 的实现无法满足线性一致性，这是由 HLC 本身的特性决定的。

# Summary

可以看到不可重复的的本质是因为在生成 commit_ts 和 Lock Row 之间有一个 GAP，如果读操作在这个 GAP 之间进来，读到旧版本的数据，当写事务提交后，重新读到的就是新版本的数据了。如果写操作是在 Lock Row 之后进来的，第一次读会一直阻塞到写事务提交，不会出现不可重复读的情况。

另外，如果是先 Lock Row，然后才获取的 commit_ts，就像 TiDB 没有实现 Async Commit 之前的做法，那么就不会有这个问题。

# Links

1. 事务前沿研究丨事务并发控制：https://cn.pingcap.com/blog/transaction-frontiers-research-article-talk4
1. TiKV 事务模型概览，Google Spanner 开源实现: https://pingcap.com/zh/blog/tidb-transaction-model
1. TiDB 最佳实践系列（三）乐观锁事务: https://cn.pingcap.com/blog/best-practice-optimistic-transaction
1. TiDB 新特性漫谈：悲观事务: https://cn.pingcap.com/blog/pessimistic-transaction-the-new-features-of-tidb
1. TiDB 悲观锁实现原理： https://tidb.net/blog/7730ed79
1. Async Commit 原理介绍丨 TiDB 5.0 新特性：https://cn.pingcap.com/blog/async-commit-principle

