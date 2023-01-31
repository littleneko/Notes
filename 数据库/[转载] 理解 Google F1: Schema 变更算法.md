# F1 中的算法实现

## 租约

F1 中 Schema 以特殊的 kv 对存储于 Spanner 中，同时每个 F1 服务器在运行过程中自身也维护一份拷贝。为了保证==同一时刻最多只有 2 份 Schema 生效==，F1 约定了长度为数分钟的 Schema 租约，所有 F1 服务器在租约到期后都要重新加载 Schema。如果节点无法重新完成续租，它将会自动终止服务并等待被集群管理设施重启。

## 中间状态

前面已经提过，F1 在 Schema 变更的过程中，会把一次 Schema 的变更拆解为多个逐步递进的中间状态。实际上我们并不需要针对每种 Schema 变更单独设计中间状态，总共只需要两种就够了： *delete-only* 和 *write-only* 。

==***delete-only* 指的是 Schema 元素的存在性只对删除操作可见。**==

例如当某索引处于 *delete-only* 状态时，F1 服务器中执行对应表的删除一行数据操作时能“看到”该索引，所以会同时删除该行对应的索引，与之相对的，如果是插入一行数据则“看不到”该索引，所以 F1 不会尝试新增该行对应的索引。

具体的，

* 如果 Schema 元素是 *table* 或 *column* ，该 Schema 元素只对 *delete* 语句生效；
* 如果 Schema 元素是 *index* ，则只对 *delete* 和 *update* 语句生效，其中 *update* 语句修改 *index* 的过程可以认为是先 *delete* 后再 *insert* ，在 *delete-only* 状态时只处理其中的 *delete* 而忽略掉 *insert* 。

总之，只要某 Schema 元素处于 *delete-only* 状态，F1 保证该 Schema 元素对应的 kv 对总是能够被正确地删除，并且不会为此 Schema 元素创建任何新的 kv 对。

==***write-only* 指的是 Schema 元素对写操作可见，对读操作不可见**。==

例如当某索引处于 *write-only* 状态时，不论是 *insert* 、 *delete* ，或是 *update* ，F1 都保证正确的更新索引，只是对于查询来说该索引仍是不存在的。

简单的归纳下就是 *write-only* 状态的 Schema 元素可写不可读。

## 示例推演

Google 论文的叙述过程是描述完两种中间状态后就开始了冗长的形式化推导，最后得以证明按照特定的步骤来做 Schema 演化是能保证一致性的。这里我想先拿出一个例子把 Schema 变更的过程推演一遍，这样形成整体印象后更有助于看懂证明：我们以添加索引为例，对应的完整 Schema 演化过程如下：

```
absent --> delete only --> write only --(reorg)--> public
```

其中 *delete-only* 和 *write-only* 是介绍过了的中间状态。*absent* 指该索引完全不存在，也就是 Schema 变更的初始状态。 *public* 自然对应变更完成后就状态，即索引可读可写，对所有操作可见。

*reorg* 指 “database reorganization”，不是一种 Schema 状态，而是发生在 *write-only* 状态之后的一系列操作。这些操作是为了保证在索引变为 *public* 之前所有旧数据的索引都被正确地生成。

根据之前的讨论，==F1 中同时最多只可能有两份 Schema 生效==，我们逐个步骤来分析。

先看 *absent* 到 *delete-only*，很显然这个过程中不会出现与此索引相关的任何数据。

再看 *delete-only* 到 *write-only* 。根据 *write-only* 的定义，一旦某节点进入 *write-only* 状态后，任何数据变更都会同时更新索引。当然，==不可能所有节点同时进入 *write-only* 状态，但我们至少能保证没有节点还停留在 *absent* 状态， *delete-only* 或 *write-only* 状态的节点都能保证索引被正确清除==。于是我们知道：从 *write-only* 状态发布时刻开始，数据库中不会存在多余的索引。

> **TIPS**:
>
> 该状态只保证删除数据的时候如果有索引一定会删除索引，即不会有多余的索引数据残留：如果在一个 write-only 状态的节点插入的数据，写了索引；在其他任何节点 (write-only, delete-only) 上如果有删除数据的操作，索引都能被正确删除。
>
> 但是该状态并不保证新写入的数据一定会写索引，如果一个写入落在 delete-only 节点，那么不会有索引被写入，需要在下一个流程 reorg 中解决这个问题。

接下来是 *reorg* ，我们来考察 *reorg* 开始时数据库的状态。==首先因为 *delete-only* 的存在，我们知道此时数据库中不存在多余的索引==。==另外此时不可能有节点还停留在 *delete-only* 状态，我们又知道从这时起，所有数据的变更都能正确地更新索引。所以 *reorg* 要做的就是取到当前时刻的 snapshot，为每条数据补写对应的索引即可==。当然 *reorg* 开始之后数据可能发生变更，这种情况下底层 Spanner 提供的一致性能保证 *reorg* 的写入操作要么失败（说明新数据已提前写入），要么被新数据覆盖。

> **TIPS**:
>
> 到达该状态起，不可能有节点还在 delete-only 状态，因此此后写入和删除的数据一定能够正确的写入和删除索引。现在要做的就是把之前所有的数据（包括开始 DDL 之前和进入 reorg 之前）的索引都更新一遍（可能有部分数据的索引已经是最新的了）。

基于前面的讨论，到 *reorg* 完成时，我们的数据不少不多也不错乱，可以放心地改为 *public* 状态了。

> **TIPS**:
>
> 1. 状态推进方法：等到所有节点都进入到一个状态后，更新 schema 信息，其他节点会定时或触发 reload schema，这样就能保证所有节点一定只在两个相邻的状态下。
> 2. reorg 阶段开启一个 snapshot 扫描所有数据，需要解决和之后更新的写入冲突。这里有两个方案：
>    1. 依靠 kv 层的冲突检测来解决写入时的冲突，如果有数据在 snapshot 开启之后又被其他事务写入，reorg 写入失败，这时不应该整个事务回滚，可能需要跳过该行的处理（TODO）
>    2. 加锁写入然后释放锁

![img](https://littleneko.oss-cn-beijing.aliyuncs.com/img/schema-change-process.png)

<center>CREATE INDEX 的 Schema 状态转换图</center>

# 其他

本文参考文献主要有：

- F1 简介 [F1: A Distributed SQL Database That Scales](http://research.google.com/pubs/archive/41344.pdf)
- Spanner 简介 [Spanner: Google’s Globally-Distributed Database](http://research.google.com/archive/spanner-osdi2012.pdf)
- Schema 变更算法 [Online, Asynchronous Schema Change in F1](http://research.google.com/pubs/archive/41376.pdf)



---

1. https://disksing.com/understanding-f1-schema-change/
2. https://hhwyt.xyz/2021-03-27-online-async-schema-change-in-f1/