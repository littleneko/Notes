## **1. 前言**

etcd 是一个被广泛应用于共享配置和服务发现的分布式、一致性的 kv 存储系统。作为分布式 kv，其底层使用的 是 raft 算法来实现多副本数据的强一致复制，etcd-raft 作为 raft 开源实现的杰出代表，在设计上，将 raft 算法逻辑和持久化、网络、线程等完全抽离出来单独实现，充分解耦，在工程上，实现了诸多性能优化，是 raft 开源实践中较早的工业级的实现，很多后来的 raft 实践者都直接或者间接的参考了 ectd-raft 的设计和实现 [5]，算是 raft 实现的一个典范。尽管当前市面上有一些 etcd 的源码解读和分析，但是大都比较零碎，缺乏一个整体的 high-level 的分析，刚好最近研究了下，特意写了这篇文章，尝试向大家展示 etcd-raft 设计和实现，文章不会过多描述 raft 算法本身和代码细节，如果不了解 raft 算法本身，建议先阅读文献 [1、2]。

首先从整体上来看看 etcd-raft 功能和性能，看看其是否符合你的期待。

![img](https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-3523e034f88cc8acead654e4e4f5f1c8_1440w.jpg)

**功能支持**：

1. Election（vote）：选举
2. Pre-vote：在发起 election vote 之前，先进行 pre-vote，可以避免在网络分区的情况避免反复的 election 打断当前 leader，触发新的选举造成可用性降低的问题
3. Config changes：配置变更，增加，删除节点等
4. Leaner：leaner 角色，仅参与 log replication，不参与投票和提交的 Op log entry，增加节点时，复制追赶 使用 leader 角色
5. Transfer leader：主动变更 Leader，用于关机维护，leader 负载等
6. ReadIndex：优化 raft read 走 Op log 性能问题，每次 read Op，仅记录 commit index，然后发送所有 peers heartbeat 确认 leader 身份，如果 leader 身份确认成功，等到 applied index >= commit index，就可以返回 client read 了
7. Lease read：通过 lease 保证 leader 的身份，从而省去了 ReadIndex 每次 heartbeat 确认 leader 身份，性能更好，但是通过时钟维护 lease 本身并不是绝对的安全
8. snapshot：raft 主动生成 snapshot，实现 log compact 和加速启动恢复，install snapshot 实现给 follower 拷贝数据等

从功能上，etcd-raft 完备的实现了 raft 几乎所需的功能。

**性能优化**：

1. Batch：网络batch发送、batch持久化 Op log entries到WAL
2. Pipeline：Leader 向 Follower 发送 Message 可以 pipeline 发送的（相对的 ping-pong 模式发送和接收）（pipeline 是grpc的一重要特性）
3. Append Log Parallelly：Leader 发送 Op log entries message 给 Followers 和 Leader 持久化 Op log entries 是并行的
4. Asynchronous Apply：由单独的 coroutine（协程） 负责异步的 Apply
5. Asynchronous GC：WAL 和 snapshot 文件会分别开启单独的 coroutine 进行 GC

etcd-raft 几乎实现了 raft 大论文 [2] 和工程上该有的性能优化，实际上 ReadIndex 和 Lease Read 本身也算是性能优化。

通过上面的介绍，可见 etcd-raft 无论在功能完备性还是性能优化上，都是我们学习和参考的不可或缺的经典。

## **2. 设计**

![img](https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-ef297c4a45c3d20daff24e49b79b5e41_1440w.jpg)

如上图，整个 etcd-server 的整体架构，其主要分为三层：

- **网络层**

图中最上面一层是网络层，负责使用 grpc 收发 etcd-raft 和 client 的各种 messages，etcd-raft 会通过网络层收发各种 message，包括 raft append entries、vote、client 发送过来的 request，以及 response 等等，其都是由 rpc 的 coroutine 完成（PS：可以简单理解所有 messages 都是通过网络模块异步收发的）。

- **持久化层**

图中最下面一层是持久化层，其提供了对 raft 各种数据的持久化存储，**WAL** - 持久化 raft Op log entries；**Snapshot** - 持久化 raft snapshot；**KV** - raft apply 的数据就是写入 kv 存储中，因为 etcd 是一个分布式的 kv 存储，所以，对 raft 来说，applied 的数据自然也就是写入到 kv 中。

- **Raft 层**

中间这一层就是 raft 层，也是 etcd-raft 的核心实现。在前言部分提到 etcd 设计上将 raft 算法的逻辑和持久化、网络、线程（实际上是 coroutine）等完全解耦成一个单独的模块，拍脑袋思考下，将网络、持久化层抽离出来，并不难，但是如何将 raft 算法逻辑和网络、持久化、coroutine 完成解耦呢 ？这小节将详细描述 etcd 是如何在设计上做到。

其核心的思路就是将 **raft 所有算法逻辑实现封装成一个 StateMachine**，也就是图中的 **raft StateMachine**，注意和 raft 复制状态机区别，这里 raft StateMachine 只是对 raft 算法的多个状态 （Leader、Follower、Candidate 等），多个阶段的一种代码实现，类似网络处理实现中也会通过一个 StateMachine 来实现网络 message 异步不同阶段的处理。回忆数据结构或者算法课学习的，**算法的五个方面**：有穷性、确切性、**输入**、**输出**、可行性。raft 算法的实现就封装在了一个 raft StateMachine，一段静静的 **躺在** 那里的代码，不包含任何的网络、持久化、coroutine 等，给其指定的**输入**，外部通过线程/coroutine 驱动 raft StateMachine 算法**运转**就能得到指定的**输出**。

为了更加形象，这里以 client 发起 一个 put kv request 为例子，来看看 raft StateMachine 的输入、运转和输出，这里以 Leader 为例，分为如下阶段：

1. **第一阶段**：client 发送一个 put kv request 给 etcd server，grpc server 解析后，生成一个 **Propose Message**（Msg，后面 Message 和 Msg 表示相同的意思，后面可能会出现混用，在 etcd-raft 将所有的输入抽象成了 msg 了，后面实现章节会详细描述）作为 raft StateMachine **输入**，如果你驱动 raft StateMachine 运转，就会生成两个**输出**，一个需要写入 WAL 的 Op log entry，2 条发送给另外两个副本的 Append entries Msg，输出会封装在 `Ready` 结构中
2. **第二阶段**：如果把第一阶段的输出 WAL 写到了盘上，并且把 Append entries Msg 发送给了其他两个副本，那么两个副本会收到 Append entries Msg，持久化之后就会给 Leader 返回 Append entries Response Msg，etcd server 收到 Msg 之后，依然作为**输入**交给 raft StateMachine 处理，驱动 StateMachine 运转，如果超过大多数 response，那么就会产生**输出**：已经 commit 的 committed entries
3. **第三阶段**：外部将上面 raft StateMachine 输出 committed entries 拿到后，apply，然后就可以返回 client put kv success 的 response 了

通过上面的例子展示了 raft StateMachine 输入，输出，运转的情况，尽管已经有了网络层和持久化层，但是，显然还缺少很多其的模块，例如：coroutine 驱动状态机运转，coroutine 将驱动网络发 message 和 持久化写盘等，下面介绍的 **raft 层**的三个小模块就是完成这些事情的：

**（1）raft StateMachine**

就是一个 raft 算法的逻辑实现，其输入统一被抽象成了 **Msg**，输出则统一封装在 **Ready** 结构中。

**（2）node（raft StateMachine 接口 - 输入+运转）**

node 模块提供了如下功能：

**（a）**raft StateMachine 和外界交互的接口，就是提供 ectd 使用一致性协议算法的接口，供上层向 raft StateMachine 提交 request，也就是输入，已上面例子的 put kv request 为例，就是通过 `func (n *node) Propose(ctx context.Context, data []byte)` 接口向 raft StateMachine 提交一个 Propose，这个接口将用户请求转换成 raft StateMachine 认识的 `MsgProp` Msg，并通过 Channel 传递给驱动 raft StateMachine 运转的 coroutine；

**（b）**提供驱动 raft 运转的 coroutine，其负责监听在各个 Msg 输入 Channel 中，一旦收到 Msg 就会调用 raft StateMachine 处理 Msg 接口 `func (r *raft) Step(m pb.Message)` 得到输出 `Ready` 结构，并将 Channel 传递给其他 coroutine 处理

**（3）raftNode（处理 raft StateMachine 输出 `Ready`）**

raftNode 模块会有一个 coroutine，负责从处理 raft StateMachine 的输出 `Ready` 结构，该持久化的调用持久化的接口持久化，该发送其他副本的，通过网络接口发送给其他副本，该 apply 的提交给其他 coroutine apply。

本小节主要讨论了整体 etcd 的分层设计和核心模块的功能，详细的实现细节，将在下一小节 [etcd raft 设计与实现《二》](https://zhuanlan.zhihu.com/p/51065416)中描述。



---

作者：[tom-sun](https://www.zhihu.com/people/sun-jian-liang)
链接：https://zhuanlan.zhihu.com/p/51063866
来源：知乎