# Raft 是什么
Raft 是一种用来管理日志复制的一致性算法，Raft 将一致性算法分为了几个部分，例如领导人选举（Leader selection）、日志复制（Log replication）和安全性（safety），同时它使用了更强的一致性来减少了必须需要考虑的状态。

## 复制状态机
一致性算法管理来自客户端状态命令的复制日志，状态机处理的日志中的命令的顺序都是一致的，因此会得到相同的执行结果。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1590167066460-cf7a0695-dc95-4d8f-b615-40cf4a41c032.jpeg" alt="img" style="zoom: 80%;" />

# Raft 基础
## 三种角色

- **Leader**：由选举产生，每个 term 只有一个 Leader，Client 的所有请求都发送到 Leader
- **Follower**：初始状态，他们不会发送任何请求，只是响应来自领导人和候选人的请求，超时之后会自动转变为 Candidate
- **Candidate**：Follower 在一段时间没收到 Leader 的消息后，转变为 Candidate，增加自己的 term，开始新一轮 Leader 的选举


## 角色之间的转换过程

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1590167066601-cf32b9a5-9db3-475f-9188-e9ff8a4b7510.png" alt="img" style="zoom:80%;" />

## Term

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1590167066718-ae9982bf-1baf-4d1e-9cfe-3ef37e7c1621.jpeg" alt="img" style="zoom:80%;" />

Term 是一个个的时间片，每一个任期的开始都是 Leader 选举，在成功选举之后，一个 Leader 会在任期内管理整个集群。如果选举失败，该任期就会因为没有 Leader而结束。

# Leader 选举
## 初始状态
**初始角色都是 Follower**

   1. 收到 Leader 请求，更新 term 和 Leader 信息
   1. 收到 Candidate 请求，根据 term 信息投票
   1. 超时，转变为 Candidate，开始发起投票请求


每个 Follower 都有一个**随机**超时时间，当一个 Follower 超时后，自增自己的 term。并转换状态为Candidate，开始发起投票。

## Candidate 状态转变
**一个 Candidate 会一直处于该状态，直到下列三种情形之一发生**

   1. 它赢得了选举；
   1. 另一台服务器赢得了选举；
   1. 一段时间后没有任何一台服务器赢得了选举

**三种情况具体如下**：

   - 一个 Candidate 如果在一个任期内收到了来自集群中大多数服务器的投票就会赢得选举。在一个任期内，一台服务器最多能给一个候选人投票。
   - 当一个 Candidate 等待别人的选票时，它有可能会收到来自其他服务器发来的声明其为 Leader 的 AppendEntries RPC。如果这个 Leader 的 term **不小于**自己的 term，则自己认为该 Leader 合法，并且转换自己的状态为 Follower。如果在这个 RPC 中的 term 小于自己当前的 term，则会拒绝此次 RPC， 继续保持 Candidate 状态。
   - 最后一种情形是投票分散，没有任何一个候选者获得大多数投票。

## 投票请求 RPC

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1590167066863-bb03c70f-13d8-463f-b3cb-e6ba2585e54d.png" alt="img" style="zoom:80%;" />


**投票请求信息**：

1. **Term**: Candidate 当前所在的 term
1. **LastLogIndex**: 候选人最新日志条目的索引值
1. **LastLogTerm**: 候选人最新日志条目所在的 term


## 其他 Follower 接收到投票请求之后的处理
如果没有投过票：则对比 Candidate 的 log 和当前 server 的 log 哪个更新，如果 Candidate 的 log 比当前节点的新或者和当前节点一样新（up to date），则同意。（==这里比较的是已经正确复制的log，不管该 log 是否已经 commited==。）

Raft 使用投票的方式来阻止没有包含全部日志条目的服务器赢得选举。一个候选人为了赢得选举必须要和集群中的大多数进行通信，这就意味着每一条已经提交的日志条目最少在其中一台服务器上出现。如果候选人的日志至少和大多数服务器上的日志一样新，那么它一定包含有全部的已经提交的日志条目。

Raft 通过比较日志中最后一个条目的索引和任期号来决定两个日志哪一个更新。**如果两个日志的任期号不同，任期号大的更新；如果任期号相同，更长的日志更新。**

** **
## Follower 成功选举为 Leader 之后的处理
**新 Leader 首先会提交自己的所有日志，因为新 Leader 一定是已经包含所有已提交的日志的，所以新 Leader 可以直接把自己的日志提交。**

然后开始把自己的日志复制到 Follower 上并告知 Follower 已提交日志的编号。
# 日志复制
## 日志复制流程
Leader 接收到 Client 发送过来的请求后，首先将该请求转化成 entry，然后添加到自己的 log 中，得到该 entry 的 index 信息。entry 中就包含了当前 Leader 的 term 信息和在 log 中的 index 信息。

然后 Leader 复制上述 entry 到所有 Follower。数据的流向只能从 Leader 节点向 Follower 节点转移。当 Client 向集群 Leader 节点提交数据后，Leader 节点接收到的数据处于未提交状态（Uncommitted），接着 Leader 节点会并发向所有 Follower 节点复制数据并等待接收响应，确保至少集群中超过半数节点已接收到数据后，Leader 会将这个条目应用到它的状态机中并且会向客户端返回执行结果。这时 Leader 节点上该数据处于已提交状态（Commited），在下一次 Heartbeat 消息中，会将该 commit 信息发送给所有 Follower。

Leader 跟踪记录它所知道的被提交条目的最大索引值，并且这个索引值会包含在之后的 AppendEntries RPC 中（包括心跳 Heartbeat 中），为的是让其他服务器都知道这个条目已经提交。一旦一个 Follewer 知道了一个日志条目已经被提交，它会将该条目应用至本地的状态机（按照日志顺序）。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1590167066989-800d0c0a-6f0f-49fb-b645-0dc7e0ce4cd0.png" alt="img" style="zoom:50%;" />

这里有一个问题是当日志写入到磁盘和复制日志到 Follower 是同步进行的，如果 Leader 先收到半数以上的 Follower 日志写成功回复，但自己的日志还没有写到磁盘，这时是否应该 commit？

如果这时 commit 了，返回给 client 成功了。节点崩溃后马上恢复，因为日志还没有写到磁盘，重启后就丢失了。所以需要限定多数派成功一定要包含 Leader 自己。

日志条目示例：

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1590167067115-53d311c4-c17b-4332-ba5b-2d36acd2d61c.jpeg" alt="img" style="zoom:80%;" />

## Log 复制 RPC
<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1590167067245-6617c985-6305-4969-b76a-9db95aa1e90a.png" alt="img" style="zoom:80%;" />

* **prevLogIndex**：之前提交的日志的编号
* **prevLogTerm**：之前提交的日志的 Term
* **LeaderCommit**：Leader 已经提交的日志编号

## AppendEntries RPC 请求的参数生成
对于每个 Follower，Leader 保存 2 个状态：

* **nextIndex**：Leader 要发给该 Follower 的下一个 entry 的 index；

* **matchIndex**：Follower 发给 Leader 的确认 index，即 Follower 已经确认复制到该节点的index。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1590167067375-eb28bb71-05d7-49b5-9881-3210d4c721e0.png" alt="img" style="zoom:80%;" />

Leader 在刚开始的时候会初始化：

* nextIndex = Leader 的 log 的最大 index + 1
* matchIndex = 0
* prevLogIndex = nextIndex - 1
* prevLogTerm = 从 log 中得到上述 prevLogIndex 对应的 term
* leaderCommit = commitIndex

## Follower 收到该消息后的处理
* Reply false if term < currentTerm

* Reply false if log doesn’t contain an entry at prevLogIndex whose term matches prevLogTerm. 检查 prevLogIndex 和 prevLogTerm 和当前 Follower 的对应 index 的 log 是否一致，如果不一致返回 false.

* **Leader 接收到上述 false 之后，会将 nextIndex 递减。**（Raft 论文中提出了另一种减少请求次数的方法：Follower 返回自己冲突日志条目的任期号和自己存储那个任期的最早的索引）

  **然后 Leader 会重新按照上述规则，发送新的 prevLogIndex、prevLogTerm 和 entries 数组。（==用于 Leader 找到 Follower 上的日志比自己落后多少或者从哪个 index 起不一致==）**

* Follower 检查 prevLogIndex 和 prevLogTerm 和对应 index 的 log 是否一致，最终 nextIndex 会达到一个 Leader 和 Flooower 日志一致的地方。

* 如果一致 Follower 就开始**将 entries 中的数据全部覆盖到本地对应的 index 上**，如果没有则算是添加如果有则算是更新，也就是说和 Leader 的保持一致。

* 最后 Follower 将最后复制的 index 发给 Leader，同时返回 ok，Leader 会像上述一样来更新 Follower 的 macthIndex。

==**在 Raft 算法中，领导人通过强制追随者们复制它的日志来处理日志的不一致。这就意味着，在追随者上的冲突日志会被领导者的日志覆盖**==

** **
## Leader 收到 Follower 回复之后的处理
Leader 一旦发现有些 entries 已经被过半的 Follower 复制了，则就将该 entry 提交，将 commitIndex 提升至该 entry 的 index，具体的实现可以通过 Follower 发送过来 macthIndex 来判定是否过半了。

一旦可以提交了，Leader 就将该 entry 应用到状态机中，然后给客户端回复 OK。

然后在下一次 Heartbeat 心跳中，将 commitIndex 就传给了所有的 Follower，对应的 Follower 就可以将 commitIndex 以及之前的 entry 应用到各自的状态机中了。

## Raft 日志保证以下特性
1. 如果在不同日志中的两个条目有着相同的索引和任期号，则它们所存储的命令是相同的。
2. 如果在不同日志中的两个条目有着相同的索引和任期号，则它们之间的所有条目都是完全一样的。

# 安全性保证
Leader 选举的两个安全性约束：

* ==**被选举出来的 Leader 必须要包含所有已经提交的 entries**==
  如 Leader 针对复制过半的 entry 提交了，但是某些 Follower 可能还没有这些 entry，当 Leader 挂了，该 Follower 如果被选举成 Leader 的时候，就可能会覆盖掉了上述的 entry 了，造成不一致的问题，所以新选出来的 Leader 必须要满足上述约束。

	目前对于上述约束的简单实现方法就是：
  
  **如果自己的日志比候选人的日志要新，那么它会拒绝候选人的投票请求**
  
  > 这里的新就是指：**谁的 lastLog 的 term 越大谁越新，如果 term 相同，谁的 lastLog 的 index 越大谁越新**
  
* ==**当前 term 的 Leader 不能“直接”提交之前 term 的 entries**==

经过上述 2 个约束，就能得出 Leader Completeness 结论。

正是由于上述 “不能直接提交之前 term 的 entries” 的约束，所以**任何一个 entry 的提交必然存在当前 term 下的 entry 的提交**。那么此时所有的 server 中有过半的 server 都含有当前 term（也是当前最大的 term）的 entry，假设 serverA 将来会成为 Leader，此时 serverA 的 lastlog 的 term 必然是不大于当前 term 的，它要想成为 Leader，即和其他 server pk 谁的 log 最新，必然是需要满足 log 的 index 比他们大的，所以必然含有已提交的 entry。

==实现中在新 Leader 选出后，直接插入一条新的空日志（idx+1，term+1），把之前的日志和空日志一起同步给 Follower，然后把之前的日志和空日志一起提交。不能一直等到客户端提交下一个请求的时候再提交==。

**案例**：

![img](https://littleneko.oss-cn-beijing.aliyuncs.com/img/1590167067505-de1afe47-9963-4375-bcf6-1b487c52b928.jpeg)

* a 场景：s1 是 leader，此时处于 term2，并且将 index 为 2 的 entry 复制到 s2 上

* b 场景：s1 挂了，s5 当选为 Leader，处于 term3，s5 在 index 为 2 的位置上接收到了新的 entry

* c 场景：s5 挂了，s1 当选为 Leader，处于 term4，s1将 index 为 2，term 为 2 的 entry 复制到了s3 上，此时已经满足过半数了

重点就在这里：**此时处于 term4，但是之前处于 term2 的 entry 达到过半数了，s1 是提交该 entry 呢还是不提交呢？**

假如 s1 提交的话，则 index 为 2，term 为 2 的 entry 就被应用到状态机中了，是不可改变了，**此时 s1 如果挂了，来到 term5，s5 是可以被选为 Leader 的，因为按照之前的 log 比对策略来说，s5 的最后一个 log 的 term 是 3 比 s2 s3 s4 的最后一个 log 的 term 都大。**一旦 s5 被选举为 Leader，即 d 场景，s5 会复制 index 为 2，term 为 3 的 entry 到上述机器上，这时候就会造成之前 s1 已经提交的 index 为 2 的位置被重新覆盖，因此违背了一致性。

假如 s1 不提交，而是等到 term4 中有过半的 entry 了，然后再将之前的 term 的 entry 一起提交（这就是所谓的间接提交，即使满足过半，但是必须要等到当前 term 中有过半的 entry 才能跟着一起提交），即处于 e 场景，s1 此时挂的话，s5 就不能被选为 Leader 了，因为 s2 s3 的最后一个 log的 term 为 4 比 s5 的 3 大，所以 s5 获取不到投票，进而 s5 就不可能去覆盖上述的提交。

# 成员变化
向 raft 系统中添加新机器时，由于配置信息不可能在各个系统上同时达到同步状态，总会有某些 server 先得到新机器的信息，有些 server 后得到新机器的信息

比如下图 raft 系统中新增加了server4 和 server5 这两台机器。只有 server3 率先感知到了这两台机器的添加。这个时候如果进行选举，就有可能出现两个 Leader 选举成功。因为 server3 认为有 3 台 server 给它投了票，它就是Leader，而 server1 认为只要有 2 台 server 给它投票就是 Leader 了。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1590167067668-719f1aaf-9616-424c-ae98-769c1c989af1.png" alt="img" style="zoom:80%;" />

产生这个问题的根本原因是，raft 系统中有一部分机器使用了旧的配置，如 server1 和 server2，有一部分使用新的配置，如 server3。解决这个问题的方法是添加一个中间配置 (Cold, Cnew)，这个中间配置的内容是旧的配置表 Cold 和新的配置 Cnew。还是拿上图中的例子来说明，这个时候server3 收到添加机器的消息后，不是直接使用新的配置 Cnew，而是使用 (Cold, Cnew) 来做决策。比如说 server3 在竞选 Leader 的时候，不仅需要得到 Cold 中的大部分投票，还要得到 Cnew 中的大部分投票才能成为 Leader。这样就保证了 server1 和 server2 在使用 Cold 配置的情况下，还是只可能产生一个 Leader。当所有 server 都获得了添加机器的消息后，再统一切换到 Cnew。

raft 实现中，将 Cold，(Cold, Cnew) 以及 Cnew 都当成一条普通的日志。配置更改信息发送 Leader后，由 Leader 先添加一条 (Cold, Cnew) 日志，并同步给其它 Follower。当这条日志 (Cold, Cnew) 提交后，再添加一条 Cnew 日志同步给其它 Follower，通过 Cnew 日志将所有 Follower 的配置切换到最新。

# 日志压缩
![img](https://littleneko.oss-cn-beijing.aliyuncs.com/img/1590167067814-9a0f8ee7-1e8f-4f1d-b20c-17db26061eaf.jpeg)

每个服务器独立的创建快照，只包括已经被提交的日志。主要的工作包括将状态机的状态写入到快照中。Raft 也将一些少量的元数据包含到快照中：最后被包含的索引（last included index）指的是被快照取代的最后的条目在日志中的索引值（状态机最后应用的日志），最后被包含的任期（last included term）指的是该条目的任期号。保留这些数据是为了支持快照前的第一个条目的附加日志请求时的一致性检查，因为这个条目需要最后的索引值和任期号。为了支持集群成员更新（第 6 章)，快照中也将最后的一次配置作为最后一个条目存下来。一旦服务器完成一次快照，他就可以删除最后索引位置之前的所有日志和快照了。

# 客户端交互
如果 client 发送一个请求，Leader 返回 ok 响应，那么 client 认为这次请求成功执行了，那么这个请求就需要被真实的落地，不能丢。如果 Leader 没有返回 ok，那么 client 可以认为这次请求没有成功执行，之后可以通过重试方式来继续请求。

所以对 Leader 来说，一旦你给客户端回复 OK 的话，然后挂了，那么这个请求对应的 entry 必须要保证被应用到状态机，即需要别的 Leader 来继续完成这个应用到状态机。

一旦 leader 在给客户端答复之前挂了，那么这个请求对应的 entry 就不能被应用到状态机了，如果被应用到状态机就造成客户端认为执行失败，但是服务器端缺持久化了这个请求结果，这就有点不一致了。

Leader 在某个 entry 被过半复制了，认为可以提交了，就应用到状态机了，然后向客户端回复 OK，之后 Leader 挂了，是可以保证该 entry 在之后的 Leader 中是存在的。

Leader 在某个 entry 被过半复制了，然后就挂了，即没有向客户端回复 OK，raft 的机制下，后来的 Leader 是可能会包含该 entry 并提交的，或可能直接就覆盖掉了该 entry。如果是前者，则该 entry是被应用到了状态机中，那么此时就出现一个问题：client 没有收到 OK 回复，但是服务器端竟然可以成功保存了

为了掩盖这种情况，就需要在客户端做一次手脚，即客户端对那么没有回复 OK 的都要进行重试，客户端的请求都带着一个唯一的请求 id，重试的时候也是拿着之前的请求 id 去重试的。

服务器端发现该请求 id 已经存在提交 log 中了，那么直接回复 OK，如果不在的话，那么再执行一次该请求。
# 异常情况处理
1. Follower 崩溃
Follower 挂了，只要 Leader 还满足过半条件就一切正常。他们挂了又恢复之后，Leader 是会不断递减 prevLogIndex 进行重试的，该 Follower 仍然是能恢复所有的日志的，或者可以直接发送快照给 Follower。

2. Leader 崩溃：数据到达 Leader 节点，成功复制到 Follower 所有节点，但还未向 Leader 响应接收

   <img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1590167067950-0b6a42ac-2e5e-4e51-8094-ddeddaeb71f4.png" alt="img" style="zoom:50%;" />

   这个阶段 Leader 挂掉，虽然数据在 Follower 节点处于未提交状态（Uncommitted）但保持一致，重新选出 Leader 后可完成数据提交，此时 Client 由于不知到底提交成功没有，可重试提交。针对这种情况 Raft 要求 RPC 请求实现幂等性，也就是要实现内部去重机制。

3. Leader 崩溃：数据到达 Leader 节点，成功复制到 Follower 部分节点，但还未向 Leader 响应接收

   <img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1590167068087-7435feb8-e409-496f-a826-7c4ca634f04c.png" alt="img" style="zoom:50%;" />

   这个阶段 Leader 挂掉，数据在 Follower 节点处于未提交状态（Uncommitted）且不一致，Raft 协议要求投票只能投给拥有最新数据的节点。所以拥有最新数据的节点会被选为 Leader 再强制同步数据到 Follower，数据不会丢失并最终一致。

4. 网络分区，出现双 Leader

   <img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1590167068216-5e03de10-b5b0-4a53-9bb9-f4c96dbe5e4f.png" alt="img" style="zoom: 80%;" />

   如图所示，原 Leader 是 B ，term 为 1，A、B 和 C、D、E 网络被分开。因为 CDE 接收不到Leader B 的 Heart Beat，超时之后重新选出 Leader D，term 为 2。Client 所有向 B 提交的**写请求**都不能成功，因为 Node B 无法得到多数派的回应。但是向 Node D 提交的**写请求**是可以成功的，因为 Node D 可以得到 CDE 多数派的确认。
   
   对于读请求，如果设计为在 Leader节点直接读，不需要经过多数派投票，则在两个节点都能读成功，可能会导致在 B 节点读到脏数据。解决该问题有两个方法：
   
   1. 读请求前需要确认自己还是 Leader，得到多数派的确认（参考线性一致性读）
   
   2. 实现租约，旧 Leader 会在一定时间后超时。可以在一定程度上避免这个问题，但不能完全杜绝。
   
     如上图所示，向 Node B 提交的 “Set 3” 请求在 Node B 和 Node A 上都处于未提交状态。向 Node D 提交的 “Set 8” 请求因为可以得到 CDE的 确认，处于已提交状态。

​		如果此时网络恢复：

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1590167068339-c6feb746-9098-4f35-868e-9457fe623d35.png" alt="img" style="zoom:80%;" />

​		Node B 和 Node C 的心跳都可以被所有节点收到，当 CDE 收到 Node B 的心跳后，发现 B 的 term=1，自己的 term=2，会返回 false。

​		Node A B 收到 Node D 的心跳后，发现 term 比自己的 term 大，承认 Node D 为新的 Leader，Node B 转变状态为 Follower，并且丢弃未提交的 log “set 		3”，被新的 log “set 8” 覆盖。

# Links

1. 
2. https://github.com/baidu/braft/blob/master/docs/cn/raft_protocol.md
