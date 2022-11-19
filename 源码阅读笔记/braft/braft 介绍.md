# Raft 介绍

下表给出了 Multi-Paxos、RAFT、Zab 和 ViewStamped Replication 的对比：

| Multi-Paxos           | **RAFT** | **Zab** | **Viewstamped Replication** |        |
| --------------------- | -------- | ------- | --------------------------- | ------ |
| Leader Election       | Yes      | Yes     | Yes                         | Yes    |
| Log Replication       | Yes      | Yes     | Yes                         | Yes    |
| Log Recovery          | Yes?     | Yes     | Yes                         | Yes    |
| Log Compaction        | Yes?     | Yes     | Yes                         | Yes    |
| Membership Management | Yes?     | Yes     | No                          | Yes    |
| Understandable        | Hard     | Easy    | Medium                      | Medium |
| Protocol Details      | No       | Yes     | Yes                         | Yes    |
| Implements            | Few      | Mass    | Many                        | Few    |

RAFT 中将节点状态分为：

- **Leader**：接收 Client 的请求，并进行复制，任何时刻只有一个 Leader
- **Follower**：被动接收各种 RPC 请求
- **Candidate**：用于选举出一个新的 Leader

RAFT 中 Follower 长时间没有接受到心跳就会转为 Candidate 状态，收到多数投票应答之后可以转为 Leader，Leader 会定期向其他节点发送心跳。当 Leader 和Candidate 接收到更高版本的消息后，转为 Follower。具体节点状态转移图如下：

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/raft_stat.png" alt="img" style="zoom: 50%;" />

RAFT 比较优雅的解决了上面复制状态机中的几个问题，下面对选主、修复和节点变更等方面展开详细描述。

## Leader Election

RAFT 中将时间划分到 term，用于选举，标示某个 Leader 下的 Normal Case，每个 term 最多只有一个 Leader，某些 term 可能会选主失败而没有 Leader（未达到多数投票应答而超时）。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/leader_term.png" alt="img" style="zoom: 67%;" />

RAFT 的选主过程中，每个 Candidate 节点==先将本地的 currentTerm 加 1==，然后向其他节点发送 RequestVote 请求，其他节点根据本地数据版本、长度和之前选主的结果判断应答成功与否。

其他节点收到投票请求后的具体处理规则如下：

1. ==如果 now – lastLeaderUpdateTimestamp < elect_timeout，忽略请求==（注：Leader Lease 未过期，见下面 "**Asymmetric Network Partitioning**" 部分）
2. 如果 req.term < currentTerm，忽略请求（注意：request 中的 term 就是发起投票节点的 currentTerm + 1）
3. 如果 req.term > currentTerm，设置 req.term 到 currentTerm 中，如果是 Leader 或 Candidate 就转为 Follower，然后进入投票流程
4. 如果 req.term == currentTerm，进入投票流程

**投票流程**

* 如果 Candidate 的 Log 至少和本地一样新（`req.lastLogTerm > lastLogTerm || (req.lastLogTerm == lastLogTerm && req.lastLogIndex >= lastLogIndex)`）（注：LogId 的比较是先比较 term 再比较 index）

  * 本地 voteFor 记录为空或者与 vote 请求中的 term 和 CandidateId 都一致，则同意选主请求。

  * 本地 voteFor 记录非空并且与 vote 请求中的 term 一致 CandidateId 不一致，则拒绝选主请求。（一个 term 只能投给一个 Candidate ）

* 如果 Candidate 上数据比本地旧，拒绝选主请求。



上面的选主请求处理，符合 Paxos 的 "少数服从多数，后者认同前者" 的原则。按照上面的规则，选举出来的 Leader，一定是多数节点中 Log 数据最新的节点。

下面来分析一下选主的时间和活锁问题，设定 Follower 检测 Leader Lease 超时为 HeartbeatTimeout，Leader 定期发送心跳的时间间隔将小于 HeartbeatTimeout，避免 Leader Lease 超时，通常设置为小于 HeartbeatTimeout/2。当选举出现冲突，即存在两个或多个节点同时进行选主，且都没有拿到多数节点的应答，就需要重新进行选举，这就是常见的选主活锁问题。==RAFT 中引入随机超时时间机制，有效规避活锁问题==。

==注意上面的 Log 新旧的比较，是基于 lastLogTerm 和 lastLogIndex 进行比较，而不是基于 currentTerm 和 lastLogIndex 进行比较，currentTerm 只是用于忽略老的 term 的 vote 请求，或者提升自己的 currentTerm，并不参与 Log 新旧的决策==。考虑一个非对称网络划分的节点，在一段时间内会不断的进行 vote，并增加 currentTerm，这样会导致网络恢复之后，Leader 会接收到 AppendEntriesResponse 中的 term 比 currentTerm 大，Leader 就会重置 currentTerm 并进行 StepDown，这样 Leader 就对齐自己的 term 到划分节点的 term，重新开始选主，最终会在上一次多数集合中选举出一个 term 大于等于划分节点 term 的 Leader。

### Symmetric Network Partitioning

原始的 RAFT 论文中对于对称网络划分的处理是，一个节点再次上线之后，Leader 接收到高于 currentTerm 的 RequestVote 请求就进行 StepDown。这样即使这个节点已经通过 RemovePeer 删除了，依然会打断当前的 Lease，导致复制组不可用。对于这种 case 可以做些特殊的处理：Leader 不接收 RequestVote 请求，具体情况如下：

- 对于属于 PeerSet 中的节点，Leader 会在重试的 AppendEntries 中因为遇到更高的 term 而 StepDown
- 对于不属于 PeerSet 中的节点，Leader 永远忽略

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/symmetric_partition.png" alt="img" style="zoom: 67%;" />

这样，属于 PeerSet 中的节点最终能够加入，不属于 PeerSet 的节点不会加入也不会破坏。如果网络划分是因为节点故障导致的，那么稳定的多数复制组不会收到更高 term 的 AppendEntries 应答，Leader 不会 StepDown，这样节点可以安静的加入集群。

### Asymmetric Network Partitioning ⭐️

原始的 RAFT 论文中对非对称的网络划分处理不好，比如 S1、S2、S3 分别位于三个 IDC，其中 S1 和 S2 之间网络不通，其他之间可以联通。==这样一旦 S1 或者是 S2 抢到了 Leader，另外一方在超时之后就会触发选主，例如 S1 为 Leader，S2 不断超时触发选主，S3 提升 term 打断当前 Lease，从而拒绝 Leader 的更新==。==这个时候可以增加一个 trick 的检查，每个 Follower 维护一个时间戳记录收到 Leader 上数据更新的时间，只有超过 ElectionTImeout 之后才允许接受 Vote 请求==。这个类似 Zookeeper 中只有 Candidate 才能发起和接受投票，就可以保证 S1 和 S3 能够一直维持稳定的 quorum 集合，S2 不能选主成功。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/asymmetric_partition.png" alt="!img" style="zoom:67%;" />

### StepDown

RAFT 原始协议中 Leader 收到任何 term 高于 currentTerm 的请求都会进行 StepDown，在实际开发中应该在以下几个时刻进行 StepDown：

* Leader 接收到 AppendEntries 的失败应答，term 比 currentTerm 大
* Leader 在 ElectionTimeout 内没有写多数成功，通过 logic clock 检查实现（1 个 ElectionTimeout 内会有 10 个 HeartBeat）
* Leader 在进行 RemovePeer 的 LogEntry 被 Commit 的时候，不在节点列表中，进行 StepDown，通常还会进行 Shutdown

## Log Replication

一旦选举出了一个 Leader，它就开始负责服务客户端的请求。每个客户端的请求都包含一个要被复制状态机执行的指令。==Leader 首先要把这个指令追加到 log 中形成一个新的 entry，然后通过 AppendEntries RPCs **并行**的把该 entry 发给其他 servers==，其他 server 如果发现没问题，复制成功后会给 Leader 一个表示成功的 ACK，Leader 收到大多数 ACK 后应用该日志，返回客户端执行结果。如果 Followers crash 或者丢包，Leader 会不断重试 AppendEntries RPC。

> **Tips**:
>
> Leader 追加 Log 到本地的时候不需要等到本地持久化成功才向 Follower 发送 AppendEntries RPC

Logs 按照下图组织：

![img](https://littleneko.oss-cn-beijing.aliyuncs.com/img/logs.png)

每个 log entry 都存储着一条用于状态机的指令，同时保存从 Leader 收到该 entry 时的 term 号。该 term 号可以用来判断一些 log 之间的不一致状态。每一个entry 还有一个 index 指明自己在 log 中的位置。

Leader 需要决定什么时候将日志应用给状态机是安全的，可以被应用的 entry 叫 committed。RAFT 保证 committed entries 持久化，并且最终被其他状态机应用，一个 Log Entry 一旦复制给了大多数节点就成为 committed。同时要注意一种情况，==如果当前待提交 entry 之前有未提交的 entry，即使是以前过时的 Leader 创建的，只要满足已存储在大多数节点上就一次性按顺序都提交==。Leader 要追踪最新的 committed 的 index，并在每次 AppendEntries RPCs（包括心跳）都要捎带，以使其他 server 知道一个 Log Entry 是已提交的，从而在它们本地的状态机上也应用。具体 Log Entry 的状态转移图如下：

![img](https://littleneko.oss-cn-beijing.aliyuncs.com/img/log_stats.png)

每个节点重启之后，先加载上一个 Snapshot，再加入 RAFT 复制组、选主或者是接收更新。因为 Snapshot 中的数据一定是 Applied，那么肯定是 Committed的，加载是安全的。但是 Log 中的数据，不一定是 Committed 的，因为我们没有持久化 CommittedIndex，所以不确定 Log 是否是 Committed，不能进行加载。这样先加载 Snapshot 虽然延迟了新节点加入集群的时间，但是能够保证一旦一个节点变为 Leader 之后能够比较快的加载完全数据，并提供服务。同理，Follower 接收到 InstallSnapshot 之后，接收并加载完 Snapshot 之后再回复 Leader。

### Log Recovery

Log Recovery 这里分为 current Term 修复和 prev Term 修复，Log Recovery 就是要保证已经 Committed 的数据一定不会丢失，未 Committed 的数据转变为Committed，但不会因为修复过程中断又重启而影响节点之间一致性。

current Term 修复主要是解决某些 Follower 节点重启加入集群，或者是新增 Follower 节点加入集群，Leader 需要向 Follower 节点传输漏掉的 Log Entry，如果Follower 需要的 Log Entry 已经在 Leader 上 Log Compaction 清除掉了，Leader 需要将上一个 Snapshot 和其后的 Log Entry 传输给 Follower 节点。Leader-Alive 模式下，只要 Leader 将某一条 Log Entry 复制到多数节点上，Log Entry 就转变为 Committed。 

prev Term 修复主要是在保证 Leader 切换前后数据的一致性。通过上面 RAFT 的选主可以看出，==每次选举出来的 Leader 一定包含已经 committed 的数据==（抽屉原理，选举出来的 Leader 是多数中数据最新的，一定包含已经在多数节点上 commit 的数据），==新的 Leader 将会覆盖其他节点上不一致的数据==。==**虽然新选举出来的 Leader 一定包括上一个 Term 的 Leader 已经 Committed 的 Log Entry，但是可能也包含上一个 Term 的 Leader 未 Committed 的 Log Entry**==。这部分 Log Entry 需要转变为 Committed，相对比较麻烦，需要考虑 Leader 多次切换且未完成 Log Recovery，需要保证最终提案是一致的，确定的。 RAFT 中增加了一个约束：==**对于之前 Term 的未 Committed 数据，修复到多数节点，且在新的 Term 下至少有一条新的 Log Entry 被复制或修复到多数节点之后，才能认为之前未 Committed 的 Log Entry 转为 Committed**。==下图就是一个 prev Term Recovery 的过程：

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/log_recovery.png" alt="img" style="zoom:50%;" />

1. S1 是 Term2 的 Leader，将 LogEntry 部分复制到 S1 和 S2 的 2 号位置，然后 Crash。
2. S5 被 S3、S4 和 S5 选为 Term3 的 Leader，并只写入一条 LogEntry 到本地，然后 Crash。
3. S1 被 S1、S2 和 S3 选为 Term4 的Leader，并将 2 号位置的数据修复到 S3，达到多数；并在本地写入一条 Log Entry，然后 Crash。
4. **这个时候 2 号位置的 Log Entry 虽然已经被复制到多数节点上，但是并不是 Committed**。
   * S5 被 S3、S4 和 S5 选为 Term5 的 Leader，将 2 号位置 Term3 写入的数据复制到其他节点，覆盖 S1、S2、S3 上 Term2 写入的数据
   * S1 被 S1、S2 和 S3 选为 Term5 的 Leader，将 3 号位置 Term4 写入的数据复制到 S2、S3，使得 2 号位置 Term2 写入的数据变为 Committed

通过上面的流程可以看出，在 prev Term Recovery 的情况下，只要 Log Entry 还未被 Committed，即使被修复到多数节点上，依然可能不是 Committed，必须依赖新的 Term 下再有新的 Log Entry 被复制或修复到多数节点上之后才能被认为是 Committed。 选出 Leader 之后，Leader 运行过程中会进行副本的修复，这个时候只要多数副本数据完整就可以正常工作。

Leader 为每个 Follower 维护一个 nextId，标示下一个要发送的 logIndex。Follower 接收到 AppendEntries 之后会进行一些一致性检查，检查 AppendEntries 中指定的 LastLogIndex 是否一致，如果不一致就会向 Leader 返回失败。Leader 接收到失败之后，会将 nextId 减 1，重新进行发送，直到成功。这个回溯的过程实际上就是寻找 Follower 上最后一个 CommittedId，然后 Leader 发送其后的 LogEntry。因为 Follower 持久化CommittedId 将会导致更新延迟增大，回溯的窗口也只是 Leader 切换导致的副本间不一致的 LogEntry，这部分数据量一般都很小。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/log_replication.png" alt="img" style="zoom:50%;" />

==Follower a 与 Leader 数据都是一致的，只是有数据缺失，可以优化为直接通知 Leader 从 logIndex=5 开始进行重传，这样只需一次回溯==。==Follower b 与 Leader有不一致性的数据，需要回溯 7 次才能找到需要进行重传的位置==。

重新选取 Leader 之后，新的 Leader 没有之前内存中维护的 nextId，以本地 lastLogIndex+1 作为每个节点的 nextId。这样根据节点的 AppendEntries 应答可以调整 nextId：`local.nextIndex = max(min(local.nextIndex-1, resp.LastLogIndex+1), 1)`

## Log Compaction

更新通过 Leader 写入 Log，复制到多数节点，变为 Committed，再提交业务状态机。在实际系统中，当这个流程长时间跑的时候，Log 就会无限制增长，导致Log 占用太多的磁盘空间，需要更长的启动时间来加载。如果不采取一些措施进行 Log Compaction 最终将会导致系统不可用。

Snapshot 是 Log Compaction 的常用方法，将系统的全部状态写入一个 Snapshot 中，并持久化的一个可靠存储系统中，完成 Snapshot 之后这个点之前的 Log 就可以被删除了。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/log_compaction.png" alt="img" style="zoom: 80%;" />

Snapshot 的时候，除了业务状态机 dump 自己的业务数据之外，还需要一些元信息：

- **last included index**：做 Snapshot 的时候最后 apply 的 log entry 的 index
- **last included term**：做 Snapshot 的时候最后 apply 的 log entry 的 term
- **last included configuration**：做 Snapshot 的时候最后的 Configuration

==因为做完 Snapshot之后，last include index 及其之前的 Log 都会被删除，这样再次重启需要恢复 term、index 和 cofiguration 等信息，考虑 Snapshot 之后没有写入并重启的情况，所以要保存元信息==。

做 Snapshot 的时机选择，对系统也是有影响的。如果过于频繁的 Snapshot，那么将会浪费大量的磁盘带宽；如果过于不频繁的 Snasphot，那么 Log 将会占用大量的磁盘空间，启动速度也很慢。一个简单的方式就是当 Log 达到一定大小之后再进行 Snapshot，或者是达到一定时间之后再进行 Snapshot。这个根据业务场景来判断，如果 Log 加载速度很快，可以采用定量 Snapshot 的方式，并且定量的大小可以远大于 Snapshot 的大小；如果 Log 加载速度很慢，可以采用定期 Snapshot 的方式，避免 Log 太长。

==Snapshot 会花费比较长的时间，如果期望 Snapshot 不影响正常的 Log Entry 同步，需要采用 Copy-On-Write 的技术来实现==。例如，底层的数据结构或者是存储支持 COW，LSM-Tree 类型的数据结构和 KV 库一般都支持 Snapshot；或者是使用系统的 COW 支持，Linux 的 fork，或者是 ZFS 的 Snapshot 等。

### InstallSnapshot

==正常情况下，Leader 和 Follower 独立的做 Snapshot，但是当 Leader 和 Follower 之间 Log 差距比较大的时候，Leader 已经做完了一个 Snapshot，但是 Follower 依然没有同步完 Snapshot 中的 Log，这个时候就需要 Leader 向 Follower 发送 Snapshot。==

Follower 收到 InstallSnapshot 请求之后的处理流程如下：

1. 检查 req.term < currentTerm 直接返回失败
2. 创建 Snapshot，并接受后续的数据
3. 保存 Snapshot 元信息，并删除之前的完成的或者是未完成的 Snapshot
4. ==如果现存的 LogEntry 与 Snapshot 的 last_included_index 和 last_include_term 一致，保留后续的 Log；否则删除全部 Log==（表示数据不一致）
5. Follower 重新加载 Snapshot

> **TIPS**:
>
> raft 保证了如果 term 和 index 一致，那么 log entry 的数据一定是一致的

==由于 InstallSnapshot 请求也可能会重传，或者是 InstallSnapshot 过程中发生了 Leader 切换，新 Leader 的 last_included_index 比较小，可能还有 UnCommitted 的 LogEntry，这个时候就不需要进行 InstallSnapshot。所以 Follower 在收到 InstallSnapshot 的时候，Follower 不是直接删除全部 Log，而是将Snapshot 的 last_include_index 及其之前的 Log Entry 删掉，last_include_index 后续的 Log Entry 继续保留。如果需要保留后面的 Log Entry，这个时候其实不用进行加载 Snapshot 了，如果全部删除的话，就需要重新加载 Snapshot 恢复到最新的状态。==

由于 Snapshot 可能会比较大，RPC 都有消息大小限制，需要采用些手段进行处理：可以拆分数据采用 N 个 RPC，每个 RPC 带上 offset 和 data 的方式；也可以采用 Chunk 的方式，采用一个 RPC，但是拆分成多个 Chunk 进行发送。

## Membership Management

分布式系统运行过程中节点总是会存在故障报修，需要	支持节点的动态增删。节点增删过程不能影响当前数据的复制，并能够自动对新节点进行数据修复，如果删除节点涉及 Leader，还需要触发自动选主。直接增加节点可能会导致出现新老节点结合出现两个多数集合，造成冲突。下图是 3 个节点的集群扩展到 5 个节点的集群，直接扩展可能会造成 Server1 和 Server2 构成老的多数集合，Server3、Server4 和 Server5构成新的多数集合，两者不相交从而可能导致决议冲突。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/membership.png" alt="img" style="zoom: 67%;" />

### Joint-Consensus

RAFT 采用协同一致性的方式来解决节点的变更，先提交一个包含新老节点结合的 Configuration 命令，当这条消息 Commit 之后再提交一条只包含新节点的 Configuration 命令。新老集合中任何一个节点都可以成为 Leader，这样 Leader 宕机之后，如果新的 Leader 没有看到包括新老节点集合的 Configuration 日志（这条 configuration 日志在老节点集合中没有写到多数），继续以老节点集合组建复制组（老节点集合中收到 configuration 日志的节点会截断日志）；如果新的 Leader 看到了包括新老节点集合的 Configuration 日志，将未完成的节点变更流程走完。具体流程如下：

1. 首先对新节点进行 CaughtUp 追数据
2. 全部新节点完成 CaughtUp 之后，向新老集合发送 Cold+new 命令
3. 如果新节点集合多数和老节点集合多数都应答了 Cold+new，就向新老节点集合发送 Cnew 命令
4. 如果新节点集合多数应答了 Cnew，完成节点切换

配置改变示意图如下：

![img](https://littleneko.oss-cn-beijing.aliyuncs.com/img/member_change_procedure.png)

下面是节点变更过程中的状态转移图：

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/member_change_stats.png" alt="img" style="zoom: 67%;" />

节点配置变更过程中需要满足如下规则：

- 新老集合中的任何节点都可能成为 Leader
- 任何决议都需要新老集合的多数通过

结合上面的流程和状态转移图，如果 Cold+new 被 Commit 到新老集合多数的话，即使过程终止，新的 Leader 依然能够看到 Cold+new，并继续完成 Cnew 的流程，最终完成节点变更；如果 Cold+new 没有提交到新老集合多数的话，新的 Leader 可能看到了 Cold+new 也可能没有看到，如果看到了依然可以完成 Cnew 的流程，如果没有看到，说明 Cold+new 在两个集合都没有拿到多数应答，重新按照 Cold 进行集群操作。这里说明一下选主过程，==两阶段过程中选主需要新老两个集合都达到多数同意==。

### Single-Server Change

其实上面的流程可以简化，==每次只增删一个节点，这样就不会出现两个多数集合==，不会造成决议冲突的情况。按照如下规则进行处理：

1. Leader 收到 AddPeer/RemovePeer 的时候就进行处理，而不是等到 committed，这样马上就可以使用新的 peer set 进行复制 AddPeer/RemovePeer 请求。
2. Leader 启动的时候就发送 NO_OP 请求，将上一个 AddPeer/RemovePeer 变为 committed，并使未复制到当前 Leader 的 AddPeer/RemovePeer 失效。直等到 NO_OP 请求 committed 之后, 可以安全地创建一个新的 configuration 并开始复制它。
3. Leader 在删除自身节点的时候，会在 RemovePeer 被 Committed 之后，进行关闭。

按照上面的规则，可以实现安全的动态节点增删，因为节点动态调整跟 Leader 选举是两个并行的过程，节点需要一些宽松的检查来保证选主和 AppendEntries 的多数集合：

1. 节点可以接受不是来自于自己 Leader 的 AppendEntries 请求
2. 节点可以为不属于自己节点列表中的 Candidate 投票

单节点变更有几个问题：

1. 以老节点集还是新节点集作为 Configuration Change 日志的节点集
2. 什么时候修改本地内存中节点集合

Configuration Change 无论基于新节点集还是老节点集都不会破坏“新老节点集的多数至少有一个节点相交”。

1. 基于老节点集的问题是，对于 2 个节点的集群，挂掉 1 台之后没法进行 add_peer 或者是 remove_peer。其实可以推广到偶数节点故障一半，基于老节点集的 add_peer/remove_peer 都无法完成。基于老节点集，可以省掉 leader 启动时候的 NO_OP 日志，同时被删除的节点还可以收到 remove_peer 而自动进行 shutdown。Leader 在同步 Configuration Change 日志过程中宕机，老节点集中重新选出一个 Leader，要么恢复到 old Configuration，要么继续 new Configuration change。
2. 基于新节点集在 Configuration Change 日志之前的日志都 Committed 的话，是可以解决上面的偶数节点挂一半的 case，但实际意义不大。基于新节点集，需要在 Leader 启动的时候写入一条 NO_OP 日志。Leader 在同步 Configuration Change 日志过程中宕机，merge(老节点集,新节点集) 中重新选出一个Leader，要么恢复到 old Configuration，要么继续 new Configuration change。

对于什么时候修改本地节点集合，只需要保证 Configuration Change 下不会导致 Committed 的 Log 不会被覆盖就可以，Configuration Change 之后的 Log 采用新集合还是老集合都不会破坏这个规则。

RAFT 作者论文中是采用新节点集且本地写下 Configuration Change Log 就修改内存 Configuration 的方案，etcd 中采用老节点集且在老节点集中多数达成Committed 后再修改内存 Configuration 的方案。

在偶数节点集群删除一个节点的时候，在 remove_peer 之前的日志的 counting replica 比之后的日志多，可能后面的日志先满足 counting。如果后面的日志变为 committed，前面的日志也是 committed，因为老的 configuration 的多数节点集不会选为 Leader，从而不会发生覆盖。hashicorp 的实现是严格按序进行 committed，即只有前面的日志都满足 counting 之后才能变为 committed。

对于多数节点故障的时候，Leader 应该 step down，通过 set_peer 向新节点集中每个节点设置相同的节点集，触发它们重新选主，新的 Leader 再写入一条add_peer 的 log（以 set_peer 设置的节点集为准进行同步）。

另外 Leader 启动的时候先发送一个 AddPeer 或者是 NO_OP 请求是非常重要的：如果集群数量为偶数，并且上一个 Leader 最后在进行节点变更的时候宕机没有commit 到多数；新的 Leader 如果启动就改变其节点集合，按照新节点集可能判断为 Committed，但是之前老的 Leader 启动之后按照新的节点集合形成另外一个多数集合将之前未 Commit 的节点变更日志变为 Committed，这样就产生了脑裂，可能会造成数据丢失。新的 Leader 启动之后必须 Commit 一条数据非节点变更日志后才能够进行发起节点变更，这条 Committed 的非节点变更日志可以保证至少跟之前 UnCommitted 的日志有一个节点交集，这样就可以保证 UnCommitted 的节点变更日志不会再变为 Committed。详细讨论参见：https://groups.google.com/forum/#!topic/RAFT-dev/t4xj6dJTP6E

### Configuration Store

Configuration 在节点重启之后必须跟节点挂掉之前的 Configuration 保持一致，也就是说 Configuration 是跟 Log 一致的。如果单独找一个地方存 Configuration，需要保证 Configuration 的存储和 Log 的存储是原子的，并且是可重入的。Configuration 的存储发生在 Configuration Change 日志被写入的时候，对于 Leader 来讲开始异步写入就需要存储，对于 Follower 来讲写入成功才需要存储。Configuration Change 之前还没有 Committed 的 LogEntry 原则上只需要 Old 节点集多数应答即可，实际中可以约束到 Old 节点集和 New 节点集都多数应答，这样能简化 Configuration 的管理。

Snapshot 中保存的 Configuration，一定是 Applied 的，肯定是 Committed。但是 Log 中的 Configuration 可能是 UnCommitted 的，因为没有记录 CommittedIndex。启动前需要先扫描一遍 Log 获取其中的 Configuration，这里不仅仅是获取最后一个 Configuration。因为最后的 Configuration Change Log 可能是 UnCommitted 从而被 Overwrite，之后需要查找上一个 Configuration，所以需要拿到 Log 中全部的 Configuration。在完成选主之后，使用最后一个 Configuration 作为节点列表配置。通过定期将全部 Configuration 持久化，可以加快启动前的扫描速度，只扫描记录的最后一个 Configuration 之后的 Log。

## Safety

前面对 RAFT 的一些处理流程进行了一些描述，但是对于 RAFT 的安全性保证并没有进行太多的描述。比如某个 Follower 暂时离线，Leader 又 Commit 了一些 LogEntry，这个 Follower 再次上线之后被选为 Leader，覆盖这部分 LogEntry，这样就会导致不同的状态机执行了不同的命令。 RAFT 保证任意时刻如下属性都为真：

* **Election Safety**：给定 Term 下最多只有一个 Leader 被选举出来。
* **Leader Append-Only**：Leader 不会覆盖或者是删除自己的 Entry，只会进行 Append。
* **Log Matching**：如果两个 Log 拥有相同的 Term 和 Index，那么给定 Index 之前的 LogEntry 都是相同的。
  * ==如果两个 Log 拥有相同的 Term 和 Index，那么他们拥有相同的内容==
  * ==如果两个 Log 拥有相同的 Term 和 Index，那么之前的 Log 也都是一样的==
* **Leader Completeness**：如果一条 LogEntry 在某个 Term 下被 Commit 了，那么这条 LogEntry 必然存在于后面 Term 的 Leader 中。
* **State Machine Safety**：如果一个节点已经 Apply 了一条 LogEntry 到状态机，那么其他节点不会向状态机中 Apply 相同 Index 下的不同的 LogEntry。

RAFT 中有一个 Leader Completeness 属性来保证任意 term 的 Leader 都包含了之前 term 的已经 committed 的 LogEntry，通过 Leader Completeness 约束 RAFT 选出来的 Leader 一定包含全部已经 committed 的数据，具体来讲就是比较最后一条 LogEntry 的 index 和 term。下面我们对 Leader Completeness 进行证明，假定 term T 的 Leader（LeaderT）在其 term 下 commit 了一条 LogEntry，之后几个 Term 的 Leader 都包含这条 LogEntry，但是在 Term U(U > T) 中不包含这条 LogEntry：

1. LeaderU 的 Committed Log 中一定不包含这条 LogEntry，因为 Leader 从不会删除或者是覆盖自己的LogEntry。
2. LeaderT 将这条 LogEntry 复制到多数节点，LeaderU 收到多数节点的投票。这样至少有一个节点 Voter 包含这条 LogEntry，并对 LeaderU 进行了投票。
3. Voter 上包含这条 LogEntry，一定在给 LeaderU 投票前接受了 LeaderT 的这条 LogEntry。否则它的 Term 比 T 大会拒绝 LeaderT 的 AppendEntries 请求。
4. Voter 在投票给 LeaderU 之前依然保存着这条 LogEntry，因为 Term (T, U) 之间的 Leader 都包含这条 LogEntry。因为 Leader 不会删除 LogEntry，Follower 只有在跟 Leader 不一致时才会删除 LogEntry。Voter 跟 Leader 之间数据一致，不会删除那条 LogEntry。
5. Voter 投票给 LeaderU，那么 LeaderU 的 Log 至少跟 Voter 一样新。这样就产生了两个矛盾：
6. 首先，如果 Voter 和 LeaderU 拥有相同的 LastLog，那么 LeaderU 一定包含 Voter 上的 Log，Voter 包含那条 LogEntry，但 LeaderU 之前假定没有那条 LogEntry，得到矛盾。
7. 其次，如果 LeaderU 的 LastLog 比 Voter 大。很明显 LeaderU 的 LastLog 的 Term 一定大于 T，Voter 的 LastLog 的 Term 也至少大于 T。Term (T,U) 之间的 Leader 都包含这条 Committed 的 LogEntry。根据 Log Matching 属性，LeaderU 一定也包含之前 Committed 的 LogEntry，但是 LeaderU 之前假定没有那条 LogEntry，得到矛盾。

通过上面的证明来看，RAFT Safety 的关键在于选主过程中数据新旧程度的判断，具体来讲就是 LastLog 的 Term 和 Index。在 RAFT 中抛开 Log Compaction 中的 LogEntry 删除，只有在 Follower 上数据与 Leader 不一致的时候才会进行删除，而且 RAFT 的 AppendEntries 流程也保证了只删除不一致的部分。这样 LogEntry 一旦被 Committed，就不会被覆盖；没有 Committed 的 LogEntry 处于未决状态，可能变为 Committed 可能被删除。在转变为 Committed 的过程中，不会修改 LogEntry 的 Term 或者是 Content。

# RAFT 完善 ⭐️

## 功能完善

原始的 RAFT 在实际使用中还需要对一些功能进行完善，来避免一些问题。

* **pre-vote**：网络划分会导致某个节点的数据与集群最新数据差距拉大，但是 term 因为不断尝试选主而变得很大。网络恢复之后，Leader 向其进行 replicate 就会导致 Leader 因为 term 较小而 stepdown。这种情况可以引入 pre-vote 来避免，==Follower 在转变为 Candidate 之前，先与集群节点通信，获得集群 Leader 是否存活的信息，如果当前集群有 Leader 存活，Follower 就不会转变为 Candidate，也不会增加 term==。

* **transfer leadership**：在实际一些应用中，需要考虑一些副本局部性放置，来降低网络的延迟和带宽占用。RAFT 在 transfer leadership 的时候，先 block 当前 leader 的写入过程，然后排空 target 节点的复制队列，使得 target 节点日志达到最新状态，然后发送 TimeoutNow 请求，触发 target 节点立即选主。这个过程不能无限制的 block 当前 leader 的写入过程，这样会影响服务，需要为 transfer leadership 设置一个超时时间，超时之后如果发现 term 没有发生变化，说明 target 节点没有追上数据并选主成功，transfer 就失败了。

  在 facebook 的 hydrabase 中跨 IDC 复制方案中，通过设置不同的 election_timeout 来设置不同 IDC 的选主优先级，election_timeout 越小选主成功概率越大。

* **setpeer**：RAFT 只能在多数节点存活的情况下可以正常工作，在实际中可能会存在多数节点故障只存在一个节点的情况，这个时候需要提供服务并及时修复数据。因为已经不能达到多数，不能写入数据，也不能做正常的节点变更。libRAFT 需要提供一个 SetPeer 的接口，设置每个节点看到的复制组节点列表，便于从多数节点故障中恢复。比如只有一个节点 S1 存活的时候，SetPeer 设置节点列表为 {S1}，这样形成一个只有 S1 的节点列表，让 S1 继续提供读写服务，后续再调度其他节点进行 AddPeer。通过强制修改节点列表，可以实现最大可用模式。

* **指定节点进行 Snapshot**：RAFT 中每个节点都可以做 snapshot，但是做 snapshot 和 apply 日志是互斥的，如果 snapshot 耗时很长就会导致 apply 不到最新的数据。一般需要 FSM 的数据支持 COW，这样才能异步完成 Snapshot Save，并不阻塞 apply。实际中很多业务数据不支持 COW，只能通过 lock 等方式来进行互斥访问，这个时候进行 snapshot 就会影响服务的可用性。因此，需要指定某个 follower 节点进行 snapshot，完成之后通知其他节点来拖 Snapshot，并截断日志。

* **静默模式**：RAFT 的 Leader 向 Follower 的心跳间隔一般都较小，在 100ms 粒度，当复制实例数较多的时候，心跳包的数量就呈指数增长。通常复制组不需要频繁的切换 Leader，我们可以将主动 Leader Election 的功能关闭，这样就不需要维护 Leader Lease 的心跳了。复制组依靠业务 Master 进行被动触发 Leader Election，这个可以只在 Leader 节点宕机时触发，整体的心跳数就从复制实例数降为节点数。社区还有一种解决方法是 [MultiRAFT](http://www.cockroachlabs.com/blog/scaling-RAFT/)，将复制组之间的心跳合并到节点之间的心跳。

* **节点分级**：在数据复制和同步的场景中，经常有增加 Follower 来进行分流的需求，比如 bigpipe 的 common broker。对于级联的 broker 并没有强一致性复制的需求，这个时候可以对节点进行分级。将 RAFT 复制组中的节点定为 Level0，其他 Level 不参与 RAFT 复制，但是从上一层节点中进行异步复制 Log。当 K>=0 时，Level K+1 从 Level K 中进行异步复制。每个节点可以指定上一层 Level 的某个节点作为复制源，也可以由 Leader 或者是由外部 Master 进行负载均衡控制。

## 性能优化

原始的 RAFT 设计中依然有些性能不尽如人意的地方，需要在实现 libRAFT 过程进行改进。

* **流水线复制**：Leader 跟其他节点之间的 Log 同步是串行 batch 的方式，每个 batch 发送过程中之后到来的请求需要等待 batch 同步完成之后才能继续发送，这样会导致较长的延迟。这个可以通过 Leader 跟其他节点之间的 PipeLine 复制来改进，有效降低更新的延迟。
* **Leader 慢节点优化**：RAFT 中 Client 的读写都通过 Leader 完成，一旦 Leader 出现 IO 慢节点，将会影响服务质量，需要对读写进行分别优化。 写入的时候Leader 需要先将 Log Entry 写到本地，然后再向其他节点进行复制，这样写入的延迟就是 *IO_Leader + Min(IO_Others)*，IO 延迟较高。其实 RAFT 的模型要求的是一条 LogEntry 在多数节点上写入成功即可认为是 Committed 状态，就可以向状态机进行 Apply，==可以将 Leader 写本地和复制异步进行，只需要在内存中保存未 Committed 的 Log Entry，在多数节点已经应答的情况下，无需等待 Leader 本地 IO 完成，将内存中的 Log Entry 直接 Apply 给状态机即可==。==**即使会造成持久化的 Base 数据比 Log 数据新，因为节点启动都是先加载上一个 Snapshot 再加载其后的 Log，对数据一致性也不会造成影响**==。 ==**对于读取，在 Single Client 的模型下面，可以将最后写入成功的多数节点列表返回给 Client，这样 Client 从这几个节点中就可以进行 Backup Request 了，就可以跳过Leader 进行读取了**==，Client 的读取中带上 CommittedId，这样即使 Follower 节点还没有收到 Leader 的心跳或者是下一个 AppendEntries，也可以将 Log Entry 转换为 Committed，并 Apply 到状态机中，随后将 Read 也发往状态机。
* **本地 IO Batch 写入**：传统的元信息复制需求，需要对每一条更新都进行 fsync，保证刷到磁盘上。如果针对每一条 Log Entry 都进行 fsync 将会比较费，可以采用类似网络 Batch 发送的的方式进行本地磁盘 IO Batch 写入，来提高吞吐。

# Links

1. https://github.com/baidu/braft/blob/master/docs/cn/raft_protocol.md
2. Ongaro, Diego, and John Ousterhout. "In search of an understandable consensus algorithm (extended version)." (2013).