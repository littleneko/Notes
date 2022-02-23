## **3. 实现**

本小节将详细的分析 raft 层的实现，包括核心的模块接口、数据结构、模块交互和 coroutine 模型等。

## **3.1. 状态转换**

既然是 StateMachine，那么首先看看 raft StateMachine 的状态转换，实际上就是 raft 算法中各种角色的转换，etcd-raft StateMachine 封装在 raft struct 中，其状态转换如下图：

![img](https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-d6309d4293ff5e49e85723cef8dad1dc_1440w.jpg)

- raft state 转换的调用接口是：

  ```golang
  func (r *raft) becomeFollower(term uint64, lead uint64)
  func (r *raft) becomePreCandidate()
  func (r *raft) becomeCandidate() 
  func (r *raft) becomeLeader() 
  ```

- raft 在各个 state 下，如何驱动 raft StateMachine 状态机运转 ？

etcd 将 raft 相关的所以处理都抽象为了 Msg，通过 Step 接口处理

```golang
func (r *raft) Step(m pb.Message) error {
    r.step(r, m)
}
```

其中 step 是一个回调函数，在不同的 state 会设置不同的回调函数来驱动 raft，这个回调函数 stepFunc 就是在 become… 函数完成的设置

```golang
type raft struct {
    .......
    step stepFunc
}
```

step 回调函数有如下几个值，其中 stepCandidate 会处理 PreCandidate 和 Candidate 两种状态

```golang
func stepFollower(r *raft, m pb.Message) error 
func stepCandidate(r *raft, m pb.Message) error
func stepLeader(r *raft, m pb.Message) error 
```

这里以 stepCandidate 为例说明：

```golang
 func stepCandidate(r *raft, m pb.Message) error {
    ......
    switch m.Type {
    case pb.MsgProp:
        r.logger.Infof("%x no leader at term %d; dropping proposal", r.id, r.Term)
        return ErrProposalDropped
    case pb.MsgApp:
        r.becomeFollower(m.Term, m.From) // always m.Term == r.Term
        r.handleAppendEntries(m)
    case pb.MsgHeartbeat:
        r.becomeFollower(m.Term, m.From) // always m.Term == r.Term
        r.handleHeartbeat(m)
    case pb.MsgSnap:
        r.becomeFollower(m.Term, m.From) // always m.Term == r.Term
        r.handleSnapshot(m)
    case myVoteRespType:
        ......
    case pb.MsgTimeoutNow:
        r.logger.Debugf("%x [term %d state %v] ignored MsgTimeoutNow from %x", r.id, r.Term, r.state, m.From)
    }
    return nil
}
```

即对各种 Msg 进行处理，这里就不展开详细展开。

## **3.2. 输入（Msg）**

所有的外部处理请求经过 raft StateMachine 处理都会首先被转换成**统一抽象的输入 Message（Msg）**，Msg 会通过 raft.Step(m) 接口完成 raft StateMachine 的处理，Msg 分两类：

1. 本地 Msg：term = 0，这种 Msg 并不会经过网络发送给 Peer，只是将 Node 接口的一些请求转换成 raft StateMachine 统一处理的抽象 Msg，这里以 Propose 接口为例，向 raft 提交一个 Op 操作，其会被转换成 MsgProp，通过 raft.Step() 传递给 raft StateMachine，最后可能被转换成给 Peer 复制 Op log 的 MsgApp Msg；（即发送给本地peer的消息）
2. 非本地 Msg：term 非 0，这种 Msg 会经过网络发送给 Peer；这里以 Msgheartbeat 为例子，就是 Leader 给 Follower 发送的心跳包。但是这个 MsgHeartbeat Msg 是通过 Tick 接口传入的，这个接口会向 raft StateMachine 传递一个 MsgBeat Msg，raft StateMachine 处理这个 MsgBeat 就是向复制组其它 Peer 分别发送一个 MsgHeartbeat Msg

所有的 Msg 在 bp.Message 中详细定义，下面给出所有的 message 类型并且依次介绍：

```golang
const (
    MsgHup            MessageType = 0   // 本地消息：选举，可能会触发 pre-vote 或者 vote
    MsgBeat           MessageType = 1   // 本地消息：心跳，触发放给 peers 的 Msgheartbeat
    MsgProp           MessageType = 2   // 本地消息：Propose，触发 MsgApp
    MsgApp            MessageType = 3   // 非本地：Op log 复制/配置变更 request
    MsgAppResp        MessageType = 4   // 非本地：Op log 复制 response
    MsgVote           MessageType = 5   // 非本地：vote request
    MsgVoteResp       MessageType = 6   // 非本地：vote response
    MsgSnap           MessageType = 7   // 非本地：Leader 向 Follower 拷贝 Snapshot，response Message 就是 MsgAppResp，通过这个值告诉 Leader 继续复制后面的日志
    MsgHeartbeat      MessageType = 8   // 非本地：心跳 request
    MsgHeartbeatResp  MessageType = 9   // 非本地：心跳 response
    MsgUnreachable    MessageType = 10  // 本地消息：EtcdServer 通过这个消息告诉 raft 状态某个 Follower 不可达，让其发送 message方式由 pipeline 切成 ping-pong 模式
    MsgSnapStatus     MessageType = 11  // 本地消息：EtcdServer 通过这个消息告诉 raft 状态机 snapshot 发送成功还是失败
    MsgCheckQuorum    MessageType = 12  // 本地消息：CheckQuorum，用于 Lease read，Leader lease
    MsgTransferLeader MessageType = 13  // 本地消息：可能会触发一个空的 MsgApp 尽快完成日志复制，也有可能是 MsgTimeoutNow 出 Transferee 立即进入选举
    MsgTimeoutNow     MessageType = 14  // 非本地：触发 Transferee 立即进行选举
    MsgReadIndex      MessageType = 15  // 非本地：Read only ReadIndex
    MsgReadIndexResp  MessageType = 16  // 非本地：Read only ReadIndex response
    MsgPreVote        MessageType = 17  // 非本地：pre vote request
    MsgPreVoteResp    MessageType = 18  // 非本地：pre vote response
)
```

需要注意的是并没有单独的配置变更的 Msg，而是 MsgApp 不同的 entry

```golang
type EntryType int32

const (
    EntryNormal     EntryType = 0
    EntryConfChange EntryType = 1
)
```

## **3.3. 输出（Ready）**

由于 etcd 的网络、持久化模块和 raft 核心是分离的，所以当 raft 处理到某一些阶段的时候，需要输出一些东西，给外部处理，例如 Op log entries 持久化，Op log entries 复制的 Msg 等；以 heartbeat 为例，输入是 MsgBeat Msg，经过状态机状态化之后，就变成了给复制组所有的 Peer 发送心跳的 MsgHeartbeat Msg；在 ectd 中就是通过一个 Ready 的数据结构来封装当前 Raft state machine 已经准备好的数据和 Msg 供外部处理。下面是 Ready 的数据结构

```golang
// Ready encapsulates the entries and messages that are ready to read,
// be saved to stable storage, committed or sent to other peers.
// All fields in Ready are read-only.
type Ready struct {
    // The current volatile state of a Node.
    // SoftState will be nil if there is no update.
    // It is not required to consume or store SoftState.
    *SoftState

    // The current state of a Node to be saved to stable storage BEFORE
    // Messages are sent.
    // HardState will be equal to empty state if there is no update.
    pb.HardState

    // ReadStates can be used for node to serve linearizable read requests locally
    // when its applied index is greater than the index in ReadState.
    // Note that the readState will be returned when raft receives msgReadIndex.
    // The returned is only valid for the request that requested to read.
    ReadStates []ReadState

    // Entries specifies entries to be saved to stable storage BEFORE
    // Messages are sent.
    // 写入 WAL
    Entries []pb.Entry

    // Snapshot specifies the snapshot to be saved to stable storage.
    Snapshot pb.Snapshot

    // CommittedEntries specifies entries to be committed to a
    // store/state-machine. These have previously been committed to stable
    // store.
    CommittedEntries []pb.Entry

    // Messages specifies outbound messages to be sent AFTER Entries are
    // committed to stable storage.
    // If it contains a MsgSnap message, the application MUST report back to raft
    // when the snapshot has been received or has failed by calling ReportSnapshot.
    Messages []pb.Message

    // MustSync indicates whether the HardState and Entries must be synchronously
    // written to disk or if an asynchronous write is permissible.
    MustSync bool
}
```

Ready 是 raft 状态机和外面交互传递的核心数据结构，其包含了一批更新操作

* SoftState：当前 node 的状态信息，主要记录了 Leader 是谁 ？当前 node 处于什么状态，是 Leader，还是 Follower，用于更新 etcd server 的状态

```golang
// SoftState provides state that is useful for logging and debugging.
// The state is volatile and does not need to be persisted to the WAL.
type SoftState struct {
    Lead      uint64 // must use atomic operations to access; keep 64-bit aligned.
    RaftState StateType
}

type StateType uint64

var stmap = [...]string{
    "StateFollower",
    "StateCandidate",
    "StateLeader",
    "StatePreCandidate",
}
```

* pb.HardState：包含当前节点见过的最大的 term，以及在这个 term 给谁投过票，以及当前节点知道的commit index，这部分数据会持久化

```text
type HardState struct {
    Term             uint64 protobuf:"varint,1,opt,name=term" json:"term"
    Vote             uint64 protobuf:"varint,2,opt,name=vote" json:"vote"
    Commit           uint64 protobuf:"varint,3,opt,name=commit" json:"commit"
    XXX_unrecognized []byte json:"-"
}
```

* ReadStates：用于返回已经确认 Leader 身份的 read 请求的 commit index

- Messages：需要广播给所有peers的消息
- CommittedEntrie：已经commit了，还没有apply到状态机的日志
- Snapshot：需要持久化的快照

## **3.4. 交互接口**

也就是上面和图中的 node 模块，其中实现了 Node interface 定义的所有接口，其主要用于raftNode 、外部和 raft StateMachine 状态机交互，其核心接口分类描述如下：

1. **提供输入接口**：向 raft StateMachine 提交 msg

   - Tick：滴答时钟，最终会触发发起选举或者心跳

   - Campaign：向 raft StateMachine 提交本地选举 MsgHup

   - Propose：通过 Channel 向 raft StateMachine 提交一个 Op，提交的是本地 MsgProp Msg

   - ProposeConfChange：通过 propc Channel 向 raft StateMachine 提交一个配置变更的请求，提交的也是本地 MsgProp Msg

   - Step：节点收到 Peer 节点发送的 Msg 的时候会通过这个接口提交给 raft StateMachine，Step 接口通过 recvc Channel 向 raft StateMachine 传递这个 Msg

   - TransferLeadership：提交 Transfer Leader 的 Msg

   - ReadIndex：提交 read only Msg

2. **驱动状态机运转接口**：

   - 上述的所有输入接口都会驱动 raft StateMachine 运转处理 Msg

   - Advance：应用层 raftNode 处理完一个 Ready 之后，就会通过 Advance 接口通知 raft StateMachine 向 raftNode 发送下一个准备好的 Ready 给其处理

3. **获取输出接口**：

​	返回准备好的待处理的状态和数据： Ready，接口 Ready() <-chan Ready，raftNode 模块会监听这个 Channel 来获取 raft StateMachine 的输出结构 Ready

node struct 实现了 Node interface 的所有接口，详细的接口定义如下：

```golang
 type Node interface {
    // Tick increments the internal logical clock for the Node by a single tick. Election
    // timeouts and heartbeat timeouts are in units of ticks.
    Tick()
    // Campaign causes the Node to transition to candidate state and start campaigning to become leader.
    Campaign(ctx context.Context) error
    // 向 raft leader node propse 一个 key-value Op，提交 MsgProp，Entry type:EntryNormal
    Propose(ctx context.Context, data []byte) error
    // 向 raft leader node propse 一个 conf change Op，提交 MsgProp Entry type:EntryConfChange，负责和正常 Op 的 log 复制相同
    ProposeConfChange(ctx context.Context, cc pb.ConfChange) error
    // Step advances the state machine using the given message. ctx.Err() will be returned, if any.
    // 当节点收到其他节点发过来的 message，主动调用驱动 Raft
    Step(ctx context.Context, msg pb.Message) error

    // Ready returns a channel that returns the current point-in-time state.
    // Users of the Node must call Advance after retrieving the state returned by Ready.
    //
    // NOTE: No committed entries from the next Ready may be applied until all committed entries
    // and snapshots from the previous one have finished.
    // 得到当前节点的 ready 状态，我们会在之前用 has_ready 来判断一个 RawNode 是否 ready
    Ready() <-chan Ready

    // 告诉 Raft 已经处理完 ready，开始后续的迭代
    Advance()
    // ApplyConfChange applies config change to the local node.
    // Returns an opaque ConfState protobuf which must be recorded
    // in snapshots. Will never return nil; it returns a pointer only
    // to match MemoryStorage.Compact.
    ApplyConfChange(cc pb.ConfChange) *pb.ConfState

    // TransferLeadership attempts to transfer leadership to the given transferee.
    TransferLeadership(ctx context.Context, lead, transferee uint64)

    // ReadIndex request a read state. The read state will be set in the ready.
    // Read state has a read index. Once the application advances further than the read
    // index, any linearizable read requests issued before the read request can be
    // processed safely. The read state will have the same rctx attached.
    ReadIndex(ctx context.Context, rctx []byte) error

    // Status returns the current status of the raft state machine.
    Status() Status
    // ReportUnreachable reports the given node is not reachable for the last send.
    ReportUnreachable(id uint64)
    // ReportSnapshot reports the status of the sent snapshot. The id is the raft ID of the follower
    // who is meant to receive the snapshot, and the status is SnapshotFinish or SnapshotFailure.
    // Calling ReportSnapshot with SnapshotFinish is a no-op. But, any failure in applying a
    // snapshot (for e.g., while streaming it from leader to follower), should be reported to the
    // leader with SnapshotFailure. When leader sends a snapshot to a follower, it pauses any raft
    // log probes until the follower can apply the snapshot and advance its state. If the follower
    // can't do that, for e.g., due to a crash, it could end up in a limbo, never getting any
    // updates from the leader. Therefore, it is crucial that the application ensures that any
    // failure in snapshot sending is caught and reported back to the leader; so it can resume raft
    // log probing in the follower.
    ReportSnapshot(id uint64, status SnapshotStatus)
    // Stop performs any necessary termination of the Node.
    Stop()
}
```

除此之外 node 模块还会有一个 coroutine 负责接收外部的各种 Msg，然后驱动 raft StateMachine 运转，在 go 中 coroutine 之间的通信都是通过 Channel 来进行的，所以 node 模块也通过监听相应的 Channel 发现输入 Msg ，并且驱动 raft StateMachine 运转，或者通过往 Channel 中写入数据来传递输出。

```golang
 type node struct {
    // 向 raft StateMachine 提交一个 Op Propose（normal op/ conf change）
    propc      chan msgWithResult
    // 向 raft StateMachine 提交 Peer 发送过来的一些 Message，例如一些 Response，或者对 Follower 来说各种 request message
    recvc      chan pb.Message
    confc      chan pb.ConfChange
    confstatec chan pb.ConfState
    // 向上层应用 raftNode 输出 Ready 好的数据和状态
    readyc     chan Ready
    // 用于 raftNode 通知 raft StateMachine 当前 Ready 处理完了，准备下一个
    advancec   chan struct{}    
    // 用于 raftNode 通知 raft StateMachine，滴答逻辑时钟推进
    tickc      chan struct{}    
    done       chan struct{}
    stop       chan struct{}
    // 向上层应用输出 raft state machine 状态
    status     chan chan Status
    .....
}
```

如上是 node 模块的 node struct 的定义，这里以 Node interface 的 Propose 接口为例，其会生成一个本地的 MsgProp Msg 并通过 node.propc Channel 写入，而这个时候 node 模块的 coroutine 已经监听在这个 node.proc Channel 上了，当收到 MsgProp Msg，就会提交 raft StateMachine，并运转 raft StateMachine，一旦产生输出，就会 new 一个 Ready struct 来包含这次输出，然后写入 node.readyc Channel，这个时候 raftNode 模块的 coroutine 监听到 node.readyc 有输入，然后其就会读取处理处理，处理完了，就会通过 node.advance Channel 通知 node 模块 coroutine，已经处理完了当前 raft StateMachine Ready 输出，可以发送下一个准备好的待处理数据 Ready

## **3.5. 运转**

运转指的是整个 etcd-raft 的运转，其核心是由两个 coroutine 驱动，分别上文和图中提到的 raft 层中的 raftNode 模块和 node 模块各一个 coroutine：

**（1）node 模块**，对应一个 coroutine，其对应的处理逻辑代码框架如下。主要负责监听几个 Channel 接收输入，然后运行 raft StateMachine 处理输出，并打包成 Ready 给 raftNode 模块处理。：

```golang
func (n *node) run(r *raft) {

    for {
        if advancec != nil {
            readyc = nil
        } else {
            // 生成 Ready
            rd = newReady(r, prevSoftSt, prevHardSt)
            ......
        }
        .......
        select {
        // TODO: maybe buffer the config propose if there exists one (the way
        // described in raft dissertation)
        // Currently it is dropped in Step silently.
        // 从 propc 拿 client 发过来的 Propose 交给  
        case pm := <-propc:
            .......
            err := r.Step(m)
            .......
        case m := <-n.recvc:
            // filter out response message from unknown From.
            // (1) 如果是 Leader，那么收到的 Msg 必须有对应的 Progress
            // (2) 如果是 Follower，那么收到的 Msg 必定不是 ResponseMsg
            .......
        case <-n.tickc:
            r.tick()
        case readyc <- rd:
            .......
        case <-advancec:
            ......
        }
    }
}
```

**（2）raftNode 模块**：也会有一个 coroutine 对应，其核心的代码逻辑如下，主要完成的工作是把 raft StateMachine 处理的阶段性输出 Ready 拿来处理，该持久化的通过持久化接口写入盘中，该发送给 Peer 的通过网络层发送给 Peers 等。

```golang
 func (r *raftNode) start(rh *raftReadyHandler) {
    go func() {
        defer r.onStop()
        islead := false

        for {
            select {
            // 监听 Ticker 事件，并通知 raft StateMachine    
            case <-r.ticker.C:
                r.tick()
            // 监听待处理的 Ready，并处理    
            case rd := <-r.Ready():
                ......
                  // 这部分处理 Ready 的逻辑下面单独文字描述
                ......
                // 通知 raft StateMachine 运转，返回新的待处理的 Ready
                r.Advance()
            case <-r.stopped:
                return
            }
        }
    }()
}
```

raftNode 模块的 cortoutine 核心就是处理 raft StateMachine 的 Ready，下面将用文字单独描述，这里仅考虑Leader 分支，Follower 分支省略：

1. 取出 Ready.SoftState 更新 EtcdServer 的当前节点身份信息（leader、follower....）等
2. 取出 Ready.ReadStates（保存了 commit index），通过 raftNode.readStateC 通道传递给 EtcdServer 处理 read 的 coroutine
3. 取出 Ready.CommittedEntires 封装成 apply 结构，通过 raftnode.applyc 通道传递给 EtcdServer 异步 Apply 的 coroutine，并更新 EtcdServer 的 commit index
4. 取出 Ready.Messages，通过网络模块 raftNode.transport 发送给 Peers
5. 取出 Ready.HardState 和 Entries，通过 raftNode.storage 持久化到 WAL 中
6. （Follower分支）取出 Ready.snapshot（Leader 发送过来的），（1）通过 raftNode.storage 持久化 Snapshot 到盘中的 Snapshot，（2）通知异步 Apply coroutine apply snapshot 到 KV 存储中，（3）Apply snapshot 到 raftNode.raftStorage 中（all raftLog in memory）
7. 取出 Ready.entries，append 到 raftLog 中
8. 调用 raftNode.Advance 通知 raft StateMachine coroutine，当前 Ready 已经处理完，可以投递下一个准备好的 Ready 给 raftNode cortouine 处理了（raft StateMachine 中会删除 raftLog 中 unstable 中 log entries 拷贝到 raftLog 的 Memory storage 中）

## **3.6. 线程模型**

因为是 go 实现的，所以实际上是 coroutine 模型，如下图，注意因为是 coroutine，所以 coroutine 间的通信都是通过 Channel 完成的，这点注意和多线程模型区别开来，下图将给出整个 etcd server 和 raft 相关的所有 coroutine 和相关交互的 Channel 之间的关系图，这里不会详细介绍所有的交互流程和细节，感兴趣的读者可以结合代码来看。

![img](https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-e7d6302ccc335078d1c57b72479f69af_1440w.jpg)

其中红色虚线框起来的代表一个 coroutine，下面将对各个协程的作用基本的描述

- **Ticker**：golang 的 Ticker struct 会定期触发 Tick 滴答时钟，etcd raft 的都是通过滴答时钟往前推进，从而触发相应的 heartbeat timeout 和 election timeout，从而触发发送心跳和选举。
- **ReadLoop**：这个 coroutine 主要负责处理 Read request，负责将 Read 请求通过 node 模块的 Propose 提交给 raft StateMachine，然后监听 raft StateMachine，一旦 raft StateMachine 完成 read 请求的处理，会通过 readStateC 通知 ReadLoop coroutine 此 read 的commit index，然后 ReadLoop coroutine 就可以根据当前 applied index 的推进情况，一旦 applied index >= commit index，ReadLoop coroutine 就会 Read 数据并通过网络返回 client read response
- **raftNode**：raftNode 模块会有一个 coroutine 负责处理 raft StateMachine 的输出 Ready，上文已经描述了，这里不在赘述
- **node**：node 模块也会有一个 coroutine 负责接收输入，运行状态机和准备输出，上文已经描述，这里不在赘述
- **apply**：raftNode 模块在 raft StateMachine 输出 Ready 中已经 committed entries 的时候，会将 apply 逻辑放在单独的 coroutine 处理，这就是 Async apply。
- **GC**：WAL 和 snapshot 的 GC 回收也都是分别在两个单独的 coroutine 中完成的。etcd 会在配置文中分别设置 WAL 和 snapshot 文件最大数量，然后两个 GC 后台异步 GC

通过上面的线程模型分析以及 3.5 小节关于 raftNode 对于 raft StateMachine 输出 Ready 的处理，可以总结 etcd-raft 在性能上做了如下的优化：

- **Batch**：batch 的发送和持久化 Op log entries，raftNode 处理 Ready 和 node 模块处理 request 分别在两个单独的 coroutine 处理，这样 raftNode 在处理一个 Ready 的时候，node 模块的就会积累用户输入产生的输出，从而形成 batch。
- **Pipeline**：
  1. 一个完整的 raft 流程被拆，本身就是一种 pipeline
  2. Leader 向 Follower 发送 Message 是 pipeline 发送的

- Append Log Parallelly：Leader 发送 Op log entries message 给 Follower和 Leader 持久化 Op log entries 是并行的
- Asynchronous Apply：由单独的 coroutine 负责异步的 Apply
- Asynchronous Gc：WAL 和 snapshot 文件会分别开启单独的 coroutine 进行 GC

## **4. 示例**

为了更好的将整个 etcd-raft 流程串起来，下面将以一个 put kv 请求为例，描述各个模块是如何协作来完成 request 的处理。如下图给出了 etcd server 收到一个 put kv 请求的详细流程步骤图。

![img](https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-3156b634c9e8911f0f05c73e56cd135a_1440w.jpg)

1. client 通过 grpc 发送一个 Put kv request，etcd server 的 rpc server 收到这个请求，通过 node 模块的 Propose 接口提交，node 模块将这个 Put kv request 转换成 raft StateMachine 认识的 MsgProp Msg 并通过 propc Channel 传递给 node 模块的 coroutine；
2. node 模块 coroutine 监听在 propc Channel 中，收到 MsgProp Msg 之后，通过 raft.Step(Msg) 接口将其提交给 raft StateMachine 处理；
3. raft StateMachine 处理完这个 MsgProp Msg 会产生 1 个 Op log entry 和 2 个发送给另外两个副本的 Append entries 的 MsgApp messages，node 模块会将这两个输出打包成 Ready，然后通过 readyc Channel 传递给 raftNode 模块的 coroutine；
4. raftNode 模块的 coroutine 通过 readyc 读取到 Ready，首先通过网络层将 2 个 append entries 的 messages 发送给两个副本(PS:这里是异步发送的)；
5. raftNode 模块的 coroutine 自己将 Op log entry 通过持久化层的 WAL 接口同步的写入 WAL 文件中
6. raftNode 模块的 coroutine 通过 advancec Channel 通知当前 Ready 已经处理完，请给我准备下一个 带出的 raft StateMachine 输出Ready；
7. 其他副本的返回 Append entries 的 response： MsgAppResp message，会通过 node 模块的接口经过 recevc Channel 提交给 node 模块的 coroutine；
8. node 模块 coroutine 从 recev Channel 读取到 MsgAppResp，然后提交给 raft StateMachine 处理。node 模块 coroutine 会驱动 raft StateMachine 得到关于这个 committedEntires，也就是一旦大多数副本返回了就可以 commit 了，node 模块 new 一个新的 Ready其包含了 committedEntries，通过 readyc Channel 传递给 raftNode 模块 coroutine 处理；
9. raftNode 模块 coroutine 从 readyc Channel 中读取 Ready结构，然后取出已经 commit 的 committedEntries 通过 applyc 传递给另外一个 etcd server coroutine 处理，其会将每个 apply 任务提交给 FIFOScheduler 调度异步处理，这个调度器可以保证 apply 任务按照顺序被执行，因为 apply 的执行是不能乱的；
10. raftNode 模块的 coroutine 通过 advancec Channel 通知当前 Ready 已经处理完，请给我准备下一个待处理的 raft StateMachine 输出Ready；
11. FIFOScheduler 调度执行 apply 已经提交的 committedEntries
12. AppliedIndex 推进，通知 ReadLoop coroutine，满足 applied index>= commit index 的 read request 可以返回；
13. 调用网络层接口返回 client 成功。

OK，整个 Put kv request 的处理请求流程大致介绍完。需要注意的是，上面尽管每个步骤都有严格的序号，但是很多操作是异步，并发甚至并行的发生的，序号并不是严格的发生先后顺序，例如上面的 11 步 和 12，分别在不同 coroutine 并行处理，严格的发生时间序列并没有。

## **5. 总结**

etcd-raft 最大设计亮点就是抽离了网络、持久化、协程等逻辑，用一个纯粹的 raft StateMachine 来实现 raft 算法逻辑，充分的解耦，有助于 raft 算法本身的正确实现和，而且更容易纯粹的去测试 raft 算法最本质的逻辑，而不需要考虑引入其他因素（各种异常），这一点在 raft StateMachine 的单元测试中就能够体现。希望通过本文能让大家从整体上快速的了解 etcd-raft 设计和实现思路，限于篇幅未能涉及，很多 etcd-raft 的实现细节未能详细描述，例如 Ticker 驱动逻辑时钟推进，Read 的详细交互流程，Pipeline 复制等，感兴趣的可以阅读相关源代码，时间仓促，难免有理解疏漏或者错误的地方，欢迎指出。

**Notes**

如有理解和描述上有疏漏或者错误的地方，欢迎共同交流；参考已经在参考文献中注明，但仍有可能有疏漏的地方，有任何侵权或者不明确的地方，欢迎指出，必定及时更正或者删除；文章供于学习交流，转载注明出处。

**参考文献**

[1]. Ongaro D, Ousterhout J. In search of an understandable consensus algorithm[J]. Draft of October, 2014.

[2]. ONGARO, D. Consensus: Bridging theory and practice. Tech. Rep. Ph.D. thesis, Stanford University, August 2014.

[3]. etcd. [https://github.com/etcd-io/etcd](https://github.com/etcd-io/etcd)

[4]. raft home. [https://raft.github.io/](https://raft.github.io/)



---

作者：[tom-sun](https://www.zhihu.com/people/sun-jian-liang)
链接：https://zhuanlan.zhihu.com/p/51065416
来源：知乎