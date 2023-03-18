本文解读的是 SIGMOD 2020 的论文 ***CockroachDB: The Resilient Geo-Distributed SQL Database*** ，主要介绍了著名开源分布式数据库 CockroachDB 的整体架构，包括容灾、高可用、强一致性事务和 SQL 引擎的设计。我们将着重谈论其中的事务处理部分。 由于论文本身篇幅限制，为了更好地理解 CockroachDB 的设计，本文会结合 CockroachDB 的源码、文档做一些补充。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-78196f87cf52c6d86061b76e8f7ce546_1440w.webp" alt="img" style="zoom:50%;" />

# 整体介绍

## 基本概念

首先明确几个概念：

**Range：**CockroachDB 使用范围分区的方式，将全局递增有序的 K-V 数据，划分为 64MB 单位大小的 chunk，称为 K-V Range。Range 是路由、存储、复制的基本单位，具备自动分裂与合并的能力。

**Leaseholder：**CockroachDB 中最重要的概念之一，涉及到 lease 机制。简单来说，持有 lease 的副本可以对外提供 KV 的一致性读写。如果一个 raft group 中的某个副本持有 lease，那么该副本所在的节点称为 leaseholder 节点。持有 lease 的副本，一般也是 raft group 中的一个 leader。

**Gateway:** gateway 节点是和 leaseholder 节点相对的概念。gateway 节点负责解析 SQL 请求、充当事务的 coordinator，并将 KV 操作路由到正确的 leaseholder 节点上。

**Raft Leader / Log / Replica：**至少 3 的 range 可以组成一个 raft group，对外保证高可用和一致性的读写。raft 中的 leader、log、replica 用于选举、日志复制等，属于 Raft 算法的范畴，这里不再赘述。

例如，一个三节点的 CockroachDB 集群，有如下的结构：

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-23235ef187c95cf513c18432ba07f8c8_1440w.webp" alt="img" style="zoom:50%;" />

## 一次 SQL 处理流程

我们通过一个简化的模型，举例说明一次写入的过程。现有三个 CockroachDB 节点，数据库包含三张表，每个表只包含一个 Range 的数据，每个 Range 隶属于三副本 raft group：

1. 用户 SQL 发起对 table 1 的写入请求，被最近的节点 3 接收；
2. 由于 table1 所在 range 的 leaseholder，位于节点 1 上，因此需要将请求路由到节点 1 执行；
3. 节点 1 处理写入请求，将相关日志复制到节点 2、3 的副本上；
4. 节点 2、3 返回 ack 消息，节点 1 完成复制并 apply 日志；（实际上，节点 2、3 其中一个返回复制成功消息，就已经满足 Quorum；CockroachDB 的 write pipeline 优化让这一步能够异步执行。）
5. 节点 1 将写入成功的消息传给节点 3；
6. 节点 3 响应用户。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-0f914f9049a7631e05b106a29c166377_1440w.webp" alt="img" style="zoom:50%;" />

## 节点内部结构

CockroachDB 采用了 Share-nothing 的架构，所有节点同时承担着计算、存储能力。从节点内部结构来看，可以分为这么几个层次：

* **SQL 层**：接收客户端 SQL，执行 SQL 的解析、优化，生成执行计划，最终将 SQL 转化为一组 K-V 请求；
* **Transaction 层**：接收 SQL 层的 K-V 请求，保证 K-V 操作的原子性和隔离性；
* **Distribution 层**：抽象了一层全局有序、单调递增的 K-V 存储空间，接收 Transaction 层的 K-V 请求，路由到正确的 K-V Range 上。
* **Replication 层：**每个 Range 至少有三个副本，分布在不同的节点上，共同组成一个高可用的 range group。
* **Storage 层：**基于 RocksDB 构建的本地 KV 存储。

结合之前的 leaseholder/gateway 的定义来看，可以粗略认为 SQL 层、Transaction 层和 Distribution 层的能力在 gateway node 上完成，repliction 和 storage 层的能力在 leaseholder node 上完成。

# 事务整体流程

CockroachDB 利用 MVCC 机制，对外提供隔离级别为 Serializable 的一致性事务。当事务发起时，SQL 首先会被转发到 gateway 节点。gateway 节点 负责与客户端进行直接交互，同时也充当着事务中 transaction coordinator 的角色。应用通常会选择地理上最接近的 gateway 节点来发送 SQL 请求，以保证较低的延迟。

## Transaction Coordinator 执行

下图中的 algorithm 1 介绍了 transaction coordinator 的大致执行模式。当上层的 SQL layer 将用户 SQL 请求处理为一个 KV 操作序列后，transaction coordinator 负责将 KV 操作序列以满足事务语义的形式来执行。

![img](https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-42e7a4e3714b4efbb35235bde56ca282_1440w.webp)

一般地，我们只有等待事务内的上一次 SQL 请求完成，才能处理事务内的下一次 SQL 请求。为了优化这一执行模式，CockroachDB 引入了两种重要的事务处理策略： Write Pipeline 和 Parallel commit 。Write Pipeline 顾名思义，就是让写操作像流水线一样执行。具体来说，Write Pipeline 允许一次写操作可以不等待复制完成，就返回写请求成功，从而达到流水线执行的效果；Paralllel Commit 则进一步地让事务提交（commit）和 Write Pipeline 中的复制操作也并行起来。在理想情况，上述两类事务执行策略，可以让包含多条 SQL 的事务，在一次复制 rt 中快速完成。

## LeaseHolder 执行

当 lease holder 节点接收到从 coordinator 发来的请求，会先检查租约是否有效（来保证一致性读写），并尝试为操作中的 key 获取锁（保证事务内操作执行的串行）。为了避免出现不一致的情况，还需要检查本次操作所依赖的写操作是否已经完成复制；接着，如果此次写操作与其他事务的读操作产生了冲突，则需要拉高本次事务的时间戳。

完成上述准备工作后，lease holder 节点进行 evaluation，把 KV 操作转换成更底层的 command 序列。注意在这一阶段，CockroachDB 会利用并发控制机制，来处理事务间的冲突，保证事务的隔离性。我们将在下文中讲述。

![img](https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-abb46280c10c4d3d6f83ee5f2c3bb4e0_1440w.webp)

## Write Pipeline

对于上层结构传来的一条普通 KV 操作请求（非 commit 操作），只要它不和之前未完成复制的请求产生依赖关系，就有机会利用 Write Pipeline 机制来实现流水线式的写入。 因此，Cockroach 事务中需要检查每条 KV 请求与更早的、未完成复制的写操作（我们称为 in-flight 操作）是否在 key 上有重合，即存在依赖关系。如果检查出有依赖关系，则流水线需要暂停，本次操作需要等待其依赖的 in-flight 操作完成复制。这一流水线中断的现象称为 “pipeline stall”。

在完成依赖检查后，transacntion coordinator 就可以将操作发送给上文提到的 lease holder 节点来执行。关于 lease holder 节点的执行，我们将在下文详述。一旦 lease holder 节点执行完成，就会返回一个包含时间戳的 response。 如果时间戳比事务开始时的时间戳要大，说明有其他事务的读操作对本次事务操作产生了影响（一般是因为产生了 Read-Write 冲突）。此时需要对本次事务内已经完成的读操作，在新的时间戳下逐个检查。如果读操作的结果与旧时间戳下有差异，则事务失败；否则事务可以正常继续执行。

我们可以用下图的形式来描述 Write Pipeline 优化的效果。在优化前，每次写操作需要同步等待两个 follower 节点完成复制；优化后，如果写操作间不存在依赖关系（pipeline stall 现象），则仅需在 commit 时同步等待事务内所有复制完成，而不需要为每个写操作进行等待。绿色部分显示了 write pipeline 对于整个事务的优化效果。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-46036d7a5cb5a18f0d7daed2c86cc346_1440w.webp" alt="img" style="zoom:50%;" />

## Parallel Commit

当上层传来的操作是一条事务 commit 请求，则会利用 parallel commit 机制来处理。直观来说，当事务内所有写操作已经完成了复制，事务的 commit 才能开始执行。这种执行模式一般花费至少两轮复制 rt 的时间。 而在 parallel commit 机制下，事务利用记录 staging 状态信息来避免多等待一个复制 rt 时间。我们用一个例子来解释这一过程：

1. 当客户端发起一个事务，一个 Transaction Coordinator 实例被创建出来用于管理事务过程。



<img src="https://pic2.zhimg.com/80/v2-baafe0af214156e9d4c2984f15526715_1440w.webp" alt="img" style="zoom:50%;" />

2. 客户端分别在事务内写入了 "Apple" 和 "Berry" 两条 Key。由于事务还未提交，CockroachDB 暂时以 write intent 的形式来保存写入的记录。与普通的 key-value 记录相比，write intent 维护一个指向 Transaction record 的指针（此时还是空指针，尚未初始化）。Transaction record 是系统表中的一条记录，用于维护事务的状态。



<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-4fde3fc869ed0f528296187d1e8a665e_1440w.webp" alt="img" style="zoom: 67%;" />



3. 当客户端发出 commit 请求，coordinator 会正式创建出 Transaction Record，并将事务状态记录为 Staging。同时，由于 Write Pipeline 机制的存在，此时尚未完成复制的写操作（in-flight 操作）也会被记录到 Transaction Record 中。

Transaction Record 写入本身也是一次写操作，在 Write Pipeline 机制下，同样会不等复制完成就返回。接着，commit 操作会等待所有的写操作的复制（包括所有 in-flight 写，和 transaction record 写）全部完成。理想情况下，等待时间是在一个复制 rt 时间范围内的。之后，coordinator 立即响应客户端显示提交成功。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-ad51e133ac82e61526f462ba255e4483_1440w.webp" alt="img" style="zoom:67%;" />

综上，parallel commit 将整个事务的理想执行时间，压缩到了一个写复制 rt 时间内，对 CockroackDB 事务吞吐带来了极大的提升：

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-e5f08893669eea9e156a9719ec7771b7_1440w.webp" alt="img" style="zoom: 50%;" />

# 原子性与并发控制

## Atomicity

CockroachDB 通过维护 Write Intent 和 Transaction Record 来保证事务的原子性。关于这两者的定义，上文中已有介绍。Transaction Record 保存在 System Range 中，能够表示当前事务的不同状态，包括 pending staging committed 和 aborted，并确保 Write Intent 的可见性能够被原子性地改变。在长事务中，coordinator 节点还会利用心跳包来维护处于 pending 阶段的 transaction record。

当事务执行过程中遇到另一个事务写入的 write intent 时，就会触发一个 intent resolving 流程，读取并解析 transaction record 中的信息，并根据这些信息使用不同的策略来进行事务处理：

* **committed**：当 write intent 所属事务处于 committed 状态，本事务将此记录视为一个合法的常规记录，并帮助删除 write intent 中的指针，将其恢复为一个普通记录；

* **aborted**: 当 write intent 所属事务处于 aborted 状态，本事务将此记录视为一个非法记录，并进行 cleanup 流程（清理事务记录和 write intent）。
* **pending**：当 write intent 所属事务处于 pending 状态，则可能有两类情况。首先最常见的，是该 write intent 所处事务尚未完成，此时需要阻塞并等待其执行完成；或者是通过检查 transaction record 上的心跳时间是否超时，来判断事务是否处于失效状态（例如 coordinator 节点异常崩溃）。如果已经失效，则进入 abort 流程。
* **staging**：当 write intent 所属事务处于 staging 状态，说明事务已经进入提交流程。此时需要检查该事务所有写操作是否已经完成复制。如果是，则直接当做 committed 状态来处理。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-599d6eaf22cb46d98a1ec0ec8e2b0223_1440w.webp" alt="img" style="zoom:50%;" />

## Concurrency Control

在事务发生冲突时，CockroachDB 基于对时间戳的顺序判断与调整，来进行并发控制。在这一过程中，应当始终保证已发生的读取操作，在时间戳发生调整后，依然是最新的、合法的。

* **Write-Read Conflict:** 如果事务内在未完成提交的 write-intent 上发生了读取，我们称之为”写读冲突“。
  * 如果时间戳 T_write <T_read ，此时需要等待 write-intent 完成正常的事务提交流程。
  * 如果时间戳 T_write> T_read ，则读操作直接忽略 write-intent 内容，读取快照中的数据即可。

* **Read-Write Conflict**：如果在一条 key 上有两个事务 a 和 b 分别进行了写和读操作，且时间戳关系为 T_a <= T_b ，此时 CockroachDB 会强制提升 T_a 的大小，使得 T_a> T_b 。

* **Write-Write Conflict：**当一个事务的写操作，作用于另一个时间戳更小的 write-intent 上时，需要等待 write-intent 完成提交流程；而如果 key 上已经有更大时间戳的事务完成了提交，则写事务需要对时间戳进行 Push.

---

https://zhuanlan.zhihu.com/p/543497168