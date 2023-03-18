# 简介

CockroachDB 是一个支持 SQL 及完整事务 ACID 的分布式数据库，CockroachDB 结合 HLC 时钟算法实现了 Lock-Free 的乐观事务模型，支持 Serializable 和 Snapshot 两种隔离级别（注：社区目前在讨论是否去除 Snapshot 隔离级别，只保留最严格的 Serializable 隔离级别)，默认使用 Serializable 隔离级别。本文将重点解密 CockroachDB 如何做到使用 NTP 时钟同步实现现有的事务模型。

# 从时间说起

在一个单机系统中，要追溯系统发生的事务先后顺序，可通过为每一个事务分配一个顺序递增的 ID（通常称之为事务 ID）来标识事务发生的先后顺序，但是对一个分布式系统来说情况就有点特殊。目前分布式系统中常用的事务 ID 分配方式有两种：==一种是由一个中心节点统一产生事务 ID==；==另一种是使用分布式时钟算法产生事务 ID==。第一种方案实现较为简单，但是==存在单点问题==，==跨地域部署延时较高==；第二种方案各个节点可直接获取本地时间不存在单点问题，但是由于各个节点物理时钟无法保证完全一致，事务顺序保证实现较为复杂。

Google Spanner 和 CockroachDB 都采用了去中心化的设计理念，因此使用了第二种方案，但又有所不同。Google 使用了一个基于硬件 (GPS 原子钟) 的 TrueTime API 提供相对比较精准的时钟，具体细节可参考 Spanner 的论文；而 CockroachDB 使用了一个软件实现的基于 NTP 时钟同步的混合逻辑时钟算法 (Hybrid Logic Clock) —— HLC 追踪系统中事务的的 hb 关系 (happen before)。

> **e hb f 关系 (e happen before f):** 
>
> 1. 如果事件 e 和 f 发生在同一节点，e 发生在 f 之前
> 2. e 是发送事件，f 是相应的接收事件
> 3. 基于上述两者的过渡情况



HLC 由 WallTime 和 LogicTime 两部分组成（WallTime 为节点 n 当前已知的最大的物理时间，通过先判断 WallTime，再判断 LogicTime 确定两个事件的先后顺序），时间获取算法如下所示（其中 WallTime 用 `l.j` 表示，LogicTime 用 `c.j` 表示，物理时间用 `pt.j` 表示）：

```
Initially l.j := 0; c.j := 0

Send or local event
    l'.j := l.j;
    l.j := max(l'.j, pt.j);
    If (l.j = l'.j) then c.j := c.j + 1
    Else c.j := 0;
    Timestamp with l.j, c.j


Receive event of message m
    l'.j := l.j;
    l.j := max (l'.j, l.m, pt.j);
    If (l.j = l'.j = l.m) then c.j := max(c.j, c.m) + 1	// 本地 WallTime == 本地 pt == 对方 WallTime
    Elseif (l.j = l'.j) then c.j := c.j + 1			        // 本地 WallTime > 对方 WallTime && 本地 WallTime > 本地 pt
    Elseif (l.j = l'.m) then c.j := c.m + 1			        // 本地 WallTime < 对方 WallTime && 本地 WallTime > 本地 pt
    Else c.j := 0										                    // 本地 pt > 本地 WallTime && 本地 pt > 对方 WallTime
    Timestamp with l.j, c.j
```

在给本地节点产生的事件分配 HLC 时间时，WallTime 部分取当前 WallTime 和当前物理时间最大值。

* 如果物理时间小于或等于 WallTime，LogicTime 在原有基础上加 1；
* 如果物理时间大于 WallTime，LogicTime 归零。



节点之间的消息交换都会附带上消息产生时获取的 HLC 时间，当任一节点收到其他节点发送过来的消息时，取当前节点的 WallTime、对端 HLC 时间的 WallTime 以及本地物理时间中的最大值。

* 若三者相等，则取当前节点的 LogicTime 和对端 LogicTime 最大值加 1；
* 若对端 WallTime 最大，则取对端 LogicTime 加 1；
* 若本地 WallTime 最大，则取本地 LogicTime 加 1。

新的 HLC 时间更新到本地并作为本地下一个本地事件使用的 HLC 时间。



简而言之，WallTime 表示事件发生时当前节点所能感知到的最大物理时间；==LogicTime 用来追溯 WallTime 相等的事件的 hb 关系==。

HLC 算法保证了 HLC 时间有如下特性：

1. 事件 e 发生在事件 f 之前，那么事件 e 的 HLC 时间一定小于事件 f 的 HLC 时间 (即：(l.e, c.e) < (l.f, c.f))。

   > 这里的 e 发生在 f 之前实际上是指 e hb f，即 e 和 f 之间能确定 hb 关系。

2. WallTime 大于等于本地物理时间 (l.e ≥ pt.e)。即 HLC 时间总是不断递增，不会随着物理时间发生回退。

3. 对事件 e，l.e 是事件 e 能感知的到的最大时间值。也就是说，如果 l.e > pt.e，那么一定存在着一个发生在 e 之前的事件 g，有 pt.g=l.e。简单来说是==如果出现 l.e > pt.e 肯定是因为有一个 HLC 时间更大的的节点把当前节点的 HLC 时间往后推了==。

4. ==WallTime 和物理时钟的偏差是有界的 (ε ≥ |pt.e - l.e| )==。因为节点之间通过 NTP 服务校时，那么节点之间的物理时钟偏差一定小于某个值 ε。那么对于任一事件 b 和 e，==如果 b hb e，那么事件 b 的物理时间 pt.b 一定满足 pt.e + ε ≥ pt.b==。结合特性 3 存在一个事件 g 满足，l.e = pt.g。那么 pt.e + ε ≥ l.e=pt.g > pt.e

   > TIPS:
   >
   > * 节点间的物理时钟偏差一定小于等于 ε，因此系统中 WallTime 的上限是 pt + ε
   > * 证明 b hb e => pt.e + ε ≥ pt.b：因为 pt.e + ε 是 e 的 WallTime 上界，即 l.e <= pt.e + ε，我们还知道 l.b >= pt.b。假设 pt.b > pt.e + ε，可以推断出 l.b >= pt.b > pt.e +  ε >= l.e，即 l.b > l.e，那么一定不满足 b hb e，因此假设 pt.b > pt.e + ε 不成立。

5. HLC 支持 Snapshot Read。如下图所示，==节点 0 将当前发 Snapshot Read 的 HLC 时间 hlc.e 传播到其他节点，和其他节点产生关联关系 (实际上是把其他节点的 HLC 时间往后推移，使其后续产生的事件的 HLC 时间大于 hlc.e，满足 hb 关系)，这样就能拿到一个确定的全局 Snapshot==。但是这种 Snapshot Read ==不能保证完全的线性一致性 (linearizability)==，如下图中的节点 3 的 (2,2,0) 事件。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20221128010237431.png" alt="image-20221128010237431" style="zoom:67%;" />

# CockroachDB and HLC

CockroachDB 在每个事务启动时会在本地获取一个 HLC 时间 hlc.e 作为事务启动时间 (此行为可理解为 HLC 理论中的 Send or Local Event 操作) 并携带一个 MaxOffset (默认 500ms，意思是认为节点之间的物理时间偏差不会超过 500ms，该值可在节点启动时根据运行环境的时钟精度调整)。当事务消息发送到其他参与者节点之后更新参与者节点的本地 HLC 时间 (此行为可理解为 Receive Event 操作)，和参与者节点后续启动的事务产生关联关系 (hb 关联关系)。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20221128010206738.png" alt="image-20221128010206738" style="zoom: 67%;" />

下面我们来看一下 CockroachDB 如何实现一个 Snapshot Read。CockroachDB 启动事务 e，做了一个假设：==认为当前物理时间 pt.e + MaxOffset 一定是当前系统的最大时间，发生在 pt.e + MaxOffset 之后的事务的物理时间一定大于当前事务 (根据 NTP 时间同步特性 ε ≥ |ptnode1 - ptnode2| 得出该假设成立)。==根据 HLC 的特性 ε ≥ |pt.e - l.e| ，可得推论：任意时刻当前集群的整体物理时间不可能超过 hlc.e + MaxOffset。那么当 CockroachDB 执行 Snapshot Read 的时候有（注：其中 e 事务是读事务）：

1. 事务 g 满足 hlc.e + MaxOffset < hlc.g。根据特性 2 (对任一事件 e，一定有 l.e ≥ pt.e)，可得出：pt.e < pt.g，e hb g，事务 e 发生在 g 之前。

2. 事务 g 满足 hlc.e < hlc.g <= hlc.e + MaxOffset，那么此时事务 e 陷入一个叫 Uncertain Read 的状态，意思是不确定事务 g 的物理时间 pt.g 一定大于  pt.e。例如：

   * hlc.e=(10,10,2)，hlc.g=(11,11,0)，假设 MaxOffset=5，此时 hlc.g > hlc.e，pt.g > pt.e。
   * hlc.e=(10,10,2)，hlc.g=(9,11,0)，假设 MaxOffset=5，此时 hlc.g > hlc.e，pt.g < pt.e。

   在这种情况下 CockroachDB 无法拿到一个一致的 Snapshot，因此当前事务 e 必须 restart，等待时间足够长之后，获取一个新的时间戳 hlc.g +1 重新执行

3. ==事务 g 满足 hlc.g < hlc.e， 那么根据特性 5，直接执行 Snapshot Read==。

> **TIPS**:
>
> 1. hlc.e + MaxOffset 是当前系统的 hlc 上界，因此大于 hlc.e + MaxOffset 的事务一定发生在 e 之后，不能读到。
>
> 2. ==CockroachDB 在 Snapshot Read 的时候，会把当前 Read 的 HLC 传播到其他节点，与其他节点建立 hb 关系==。因此如果事务是在读事务 e 之后发生的，那么其 hlc 一定大于 hlc.e；反之一个事务的 hlc 小于 hlc.e，那么它一定是在 e 之前发生的。
>
> 3. 上面的条件是必要不充分条件，即：
>
>    * hlc.g < hlc.e => g hb e，但是 g hb e !=> hlc.g < hlc.e
>    * e hb g => hlc.g > hlc.e，但是 hlc.g > hlc.e !=> e hb g
>
>    因此只有 hlc.g < hlc.e 和 hlc.g > hlc.e + max_offset 两种情况可以确定是否可见，位于 [hlc.e, hlc.e + max_offset] 之间的事务无法确定。

# 如何选择 Maxoffset

HLC 的正确性很大程度上依赖于 NTP 服务的授时精度。当 NTP 服务变得不可靠时，HLC 也做一定程度上的容忍，消除 NTP 服务不可用带来的影响。HLC 算法不修改本地物理时间，本地物理时间通过主板上的晶振仍然能在一定时间内保证授时精度不会出现太大的偏差，能保证有足够时间恢复 NTP 服务。其次任一节点收到一个消息(事务)携带的 HLC 时间和当前节点的偏差超过 Maxoffset，该节点可拒绝此消息(事务)防止该异常的 HLC 时间扩散。CockroachDB 节点同时会定期搜集各个节点的 HLC 时间，如果当前节点和一半以上节点时间偏差超过 Maxoffset，当前节点拒绝外部请求并下线。简而言之，MaxOffset 只是在限制节点时间偏差，在超过这个偏差时对相应节点做出相应的处理。

CockroachDB 要求 Maxoffset ≥ 物理时钟偏差 (即 NTP 时间同步精度偏差)。NTP 服务偏差精度可通过如下命令查看：**ntpq -p**

![image-20221128010706267](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20221128010706267.png)

offset 列代表当前节点物理时间和 NTP 时间源时间偏差(单位毫秒)。可通过观察一段时间之后 offset 字段跳变范围决定 CockroachDB 集群 Maxoffset 取值范围。一般情况下同机房局域网或者同城机房之间的时钟偏差不会超过 200ms，CockroachDB 为了容忍网络环境较为恶劣的情况，默认设置成 500ms。

# 总结

CockroachDB 使用 HLC 追踪事务之间的 hb 关系，使其能用一个确定的 HLC 时间获取一个一致的 Snapshot 来实现事务模型。==CockroachDB 也可以使用和 Spanner 同样的 Commit-Wait 机制来实现事务的 Linearizability，但是由于 NTP 服务的精度问题，这个特性不建议开启。==



----

https://mp.weixin.qq.com/s/ho2McS6yNohEJSqChXmckA