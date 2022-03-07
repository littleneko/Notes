# Bigtable overview

Percolator 建立在 Bigtable 分布式存储系统之上，Bigtable 为用户呈现一个多维排序的映射：==key 是 (row, column, timestamp) 元组（tuples）==。 Bigtable 在每一行上提供查找和更新操作，而 Bigtable ==行事务==可以对单个行进行原子 read-modify-write 操作。 Bigtable 可处理 PB 级数据，并可在大量（不可靠）机器上可靠运行。

一个运行中的 Bigtable 包含一批 tablet 服务器，每个负责服务多个 tablet（key 空间内连续的域）。一个 master 负责协调控制各 tablet 服务器的操作，比如指示它们装载或卸载 tablet。一个 tablet 在 Google SSTable 上被存储为一系列只读的文件。SSTable 被存储在 GFS；Bigtable 依靠 GFS 来保护数据以防磁盘故障。Bigtable 允许用户控制 table 的执行特征，比如将一批列分配为一个 locality group。locality group 中的列被存储在独立隔离的 SSTable 集合中，在其他列不需要被扫描时可以有效降低扫描成本。

基于 Bigtable 来构建 Percolator，也就大概确定了 Percolator 的架构样式。Percolator 充分利用了 Bigtable 的接口：数据被组织到 Bigtable 行和列中，==Percolator 会将元数据存储在旁边特殊的列中==（见图 5）。Percolator 的 API 和 Bigtable 的 API 也很相似：Percolator 中大量 API 就是在特定的计算中封装了对Bigtable 的操作。实现 Percolator 的挑战就是提供 Bigtable 没有的功能：==**多行事务**==和==**观察者框架**==。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220306234911087.png" alt="image-20220306234911087" style="zoom:50%;" />

# 事务

Percolator 使用 ACID ==快照隔离==语义提供跨行跨表事务。Percolator 的用户可使用必要的语言（当前是 C++）编写它们的事务代码，然后加上对 Percolator API 的调用。

==Percolator 使用 Bigtable 中的时间戳维度，对每个数据项都存储多版本，以实现快照隔离==。在一个事务中，按照某个时间戳读取出来的某个版本的数据就是一个隔离的快照，然后再用一个较迟的时间戳写入新的数据。快照隔离可以有效的解决 “写-写” 冲突：如果事务 A 和 B 并行运行，往同一个 cell 执行写操作，最多只有一个能提交成功。快照隔离级别不保证串行化；特别地，在快照隔离级别下运行的事物会有写倾斜（write skew）的问题。快照隔离级别相对于串行化最大的好处是更高效地读。因为任何时间戳都代表了一个一致的快照，读取一个 cell 仅需要用给出的时间戳执行一个 Bigtable 查询；获取锁不是必要的。图 3 说明了快照隔离下事务之间的关系。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220307000157392.png" alt="image-20220307000157392" style="zoom:50%;" />

传统 PDBMS 为了实现分布式事务，可以集成基于磁盘访问管理的锁机制：PDBMS 中每个节点都会间接访问磁盘上的数据，控制磁盘访问的锁机制就可以控制生杀大权，拒绝那些违反锁要求的访问请求。而 Percolator 是基于 Bigtable 的，它不会亲自控制对存储介质的访问，所以在实现分布式事务上，与传统的 PDBMS 相比，Percolator 面对的是一系列不同的挑战。

相比之下，Percolator 中的任何节点都可以发出请求，直接修改 Bigtable 中的状态：没有太好的办法来拦截并分配锁。所以，==Percolator 一定要明确的维护锁==。==锁必须持久化以防机器故障==；如果一个锁在两阶段提交之间消失，系统可能错误的提交两个会冲突的事务。==锁服务一定要高吞吐量==，因为几千台机器将会并行的请求锁。锁服务应该也是低延迟的；每个 Get() 操作都需要申请“读取锁”，我们倾向于最小化延迟。给出这些需求，锁服务器需要冗余备份（以防异常故障）、分布式和负载均衡（以解决负载），并需要持久化存储。Bigtable 作为存储介质，可以满足所有我们的需求，所以 ==Percolator 将锁和数据存储在同一行，用特殊的内存列，访问某行数据时 Percolator 将在一个 Bigtable 行事务中对同行的锁执行读取和修改==。

我们现在考虑事务协议的更多细节。图 6 展现了 Percolator 事务的伪代码，图 4 展现了在执行事务期间 Percolator 数据和元数据的布局。图 5 中描述了系统如何使用这些不同的元数据列。事务构造器向 oracle 请求一个开始的时间戳（第六行），它决定了 Get() 将会看到的一致性快照。Set() 操作将被缓冲（第七行），直到 Commit() 被调用。提交被缓冲的 Set 操作的基本途径是两阶段提交，被客户端协调控制。不同机器上基于 Bigtable 行事务执行各自的操作，并相互影响，最终实现整体的分布式事务。

```cpp
class Transaction {
    struct Write{ Row row; Column: col; string value;};
    vector<Write> writes_;
    int start_ts_;

    Transaction():start_ts_(orcle.GetTimestamp()) {}
    void Set(Write w) {writes_.push_back(w);}
    bool Get(Row row, Column c, string* value) {
        while(true) {
            bigtable::Txn = bigtable::StartRowTransaction(row);
            // Check for locks that signal concurrent writes.
            if (T.Read(row, c+"locks", [0, start_ts_])) {
                // There is a pending lock; try to clean it and wait
                BackoffAndMaybeCleanupLock(row, c);
                continue;
            }
        }

        // Find the latest write below our start_timestamp.
        latest_write = T.Read(row, c+"write", [0, start_ts_]);
        if(!latest_write.found()) return false; // no data
        int data_ts = latest_write.start_timestamp();
        *value = T.Read(row, c+"data", [data_ts, data_ts]);
        return true;
    }
    // prewrite tries to lock cell w, returning false in case of conflict.
    bool Prewrite(Write w, Write primary) {
        Column c = w.col;
        bigtable::Txn T = bigtable::StartRowTransaction(w.row);

        // abort on writes after our start stimestamp ...
        if (T.Read(w.row, c+"write", [start_ts_, max])) return false;
        // ... or locks at any timestamp.
        if (T.Read(w.row, c+"lock", [0, max])) return false;

        T.Write(w.row, c+"data", start_ts_, w.value);
        T.Write(w.row, c+"lock", start_ts_, 
            {primary.row, primary.col});  // The primary's location.
        return T.Commit();
    }
    bool Commit() {
        Write primary = write_[0];
        vector<Write> secondaries(write_.begin() + 1, write_.end());
        if (!Prewrite(primary, primary)) return false;
        for (Write w : secondaries)
            if (!Prewrite(w, primary)) return false;

        int commit_ts = orcle.GetTimestamp();

        // Commit primary first.
        Write p = primary;
        bigtable::Txn T = bigtable::StartRowTransaction(p.row);
        if (!T.Read(p.row, p.col+"lock", [start_ts_, start_ts_]))
            return false; // aborted while working
        T.Write(p.row, p.col+"write", commit_ts,
            start_ts_); // Pointer to data written at start_ts_
        T.Erase(p.row, p.col+"lock", commit_ts);
        if(!T.Commit()) return false;  // commit point

        // Second phase: write our write records for secondary cells.
        for (Write w:secondaries) {
            bigtable::write(w.row, w.col+"write", commit_ts, start_ts_);
            bigtable::Erase(w.row, w.col+"lock", commit_ts);
        }
        return true;
    }
}; // class Transaction
```

Figure 6: Pseudocode for Percolator transaction protocol.

> **Tips**:
>
> T.Write(w.row, c+"data", start\_ts\_, w.value); 表示写 data 列，时间戳为 start_ts_，值为 w.value。

**Write**：

在 Commit 的第一阶段(“预写”，prewrite)，我们尝试锁住所有被写的 cell。（为了处理客户端失败的情况，我们指派一个任意锁为 “primary”；后续会讨论此机制）事务在每个被写的 cell 上读取元数据来检查冲突。

* 有两种冲突场景：如果事务在它的开始时间戳之后看见另一个写记录，它会取消（32 行）；这是“写-写”冲突，也就是快照隔离机制所重点保护的情况。
* 如果事务在任意时间戳看见另一个锁，它也取消（34 行）：如果看到的锁在我们的开始时间戳之前，可能提交的事务已经提交了却因为某种原因推迟了锁的释放，但是这种情况可能性不大，保险起见所以取消。

如果没有冲突，我们将锁（lock 列）和数据（data 列）写到各自 cell 的开始时间戳（start_ts_）下（36-38 行）。

如果没有 cell 发生冲突，事务可以提交并执行到第二阶段。在第二阶段的开始，客户端从 oracle 获取提交时间戳（48 行）。然后，在每个 cell（从“primary”开始），==客户端释放它的锁，替换锁为一个写记录（write 列）以让其他读事务知晓==。==读过程中看到写记录就可以确定它所在时间戳下的新数据已经完成了提交==，并可以用它的时间戳作为“指针”找到提交的真实数据。一旦 “primary” 的写记录可见了（58 行），其他读事务就会知晓新数据已写入，所以事务必须提交。

**Read**：

一个 Get() 操作第一步是在时间戳范围 [0, start timestamp]（是右开区间） 内检查有没有锁，这个范围是在此次事务快照所有可见的时间戳（12 行）。如果看到一个锁，表示另一个事务在并发的写这个 cell，所以读事务必须等待直到此锁释放。如果没有锁出现，Get() 操作在时间戳范围内读取最近的写记录（19 行）然后返回它的时间戳对应的数据项（22 行）。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220307002835839.png" alt="image-20220307002835839" style="zoom:50%;" />

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220307002926782.png" alt="image-20220307002926782" style="zoom:50%;" />

由于客户端随时可能故障，导致了事务处理的复杂度（Bigtable 可保证 tablet 服务器故障不影响系统，因为 Bigtable 确保写锁持久存在）。如果一个客户端在一个事务被提交时发生故障，锁将被遗弃。Percolator 必须清理这些锁，否则他们将导致将来的事务被非预期的挂起。Percolator 用一个懒惰的途径来实现清理：当一个事务 A 遭遇一个被事务 B 遗弃的锁，A 可以确定 B 遭遇故障，并清除它的锁。

然而希望 A 很准确的判断出 B 失败是十分困难的；可能发生这样的情况，A 准备清理 B 的事务，而事实上 B 并未故障还在尝试提交事务，我们必须想办法避免。现在就要详细介绍一下上面已经提到过的 “primary” 概念。Percolator 在每个事务中会对任意的提交或者清理操作指定一个 cell 作为同步点。这个 cell 的锁被称之为 “primary锁”。A 和 B 在哪个锁是 primary 上达成一致（primary锁 的位置被写入所有 cell 的锁中）。执行一个清理或提交操作都需要修改 primary 锁；这个修改操作会在一个 Bigtable 行事务之下执行，所以只有一个操作可以成功。特别的，在 B 提交之前，它必须检查它依然拥有 primary 锁，提交时会将它替换为一个写记录。在 A 删除 B 的锁之前，A 也必须检查 primary 锁来保证 B 没有提交；如果 primary 锁依然存在它就能安全的删除 B 的锁。

如果一个客户端在第二阶段提交时崩溃，一个事务将错过提交点（它已经写过至少一个写记录），而且出现未解决的锁。我们必须对这种事务执行 roll-forward。当其他事务遭遇了这个因为故障而被遗弃的锁时，它可以通过检查 primary 锁来区分这两种情况：如果 primary 锁已被替换为一个写记录，写入此锁的事务则必须提交，此锁必须被 roll forward；否则它应该被回滚（因为我们总是先提交 primary，所以如果 primary 没有提交我们能肯定回滚是安全的）。执行 roll forward 时，执行清理的事务也是将搁浅的锁替换为一个写记录。

清理操作在 primary 锁上是同步的，所以清理活跃客户端持有的锁是安全的；然而回滚会强迫事务取消，这会严重影响性能。所以，一个事务将不会清理一个锁除非它猜测这个锁属于一个僵死的 worker。Percolator 使用简单的机制来确定另一个事务的活跃度。运行中的 worker 会写一个 token 到 Chubby 锁服务来指示他们属于本系统，token 会被其他 worker 视为一个代表活跃度的信号（当处理退出时 token 会被自动删除）。有些 worker 是活跃的，但不在运行中，为了处理这种情况，我们附加的写入一个 wall time 到锁中；一个锁的 wall time 如果太老，即使 token 有效也会被清理。有些操作运行很长时间才会提交，针对这种情况，在整个提交过程中 worker 会周期的更新 wall time。

# 时间戳

时间戳 oracle 是一个用严格的单调增序给外界分配时间戳的服务器。因为每个事务都需要调用 oracle 两次，这个服务必须有很好的可伸缩性。oracle 会定期分配出一个时间戳范围，通过将范围中的最大值写入稳定的存储；范围确定后，oracle 能在内存中原子递增来快速分配时间戳，查询时也不涉及磁盘 I/O。如果 oracle重启，将以稳定存储中的上次范围的最大值作为开始值（此值之前可能有已经分配的和未分配的，但是之后的值肯定是未分配的，所以即使故障或重启也不会导致分配重复的时间戳，保证单调递增 ）。为了节省 RPC 消耗（会增加事务延迟）Percolator 的 worker 会维持一个长连接 RPC 到 oracle，低频率的、批量的获取时间戳。随着 oracle 负载的增加，worker 可通过增加每次批处理返回的量来缓解。批处理有效的增强了时间戳 oracle 的可伸缩性而不影响其功能。我们 oracle 中单台机器每秒向外分配接近两百万的时间戳。

==事务协议使用严格增长的时间戳来保证 Get() 能够返回所有在 “开始时间戳” 之前已提交的写操作==。举个例子，考虑一个事务 R 在时间戳 T(R) 执行读取操作，一个写事务 W 在时间戳 T(W)<T(R) 执行了提交；如何保证 R 能看到 W 提交的写操作？由于 T(W)<T(R)，我们知道 oracle 肯定是在 T(R) 之前或相同的批处理中给出 T(W)；==因此，W 是在 R 收到 T(R) 之前请求了 T(W) 作为提交时间戳==。我们知道 R 在收到 T(R) 之前不能执行读取操作，==而 W 在它的提交时间戳 T(W) 之前必定完成了锁的写入==；因此，上面的推理保证了 W 在 R 做任何读之前就写入了它所有的锁；==R 的 Get() 要么看到已经完全提交的写记录，要么看到锁==，在看到锁时 R 将阻塞直到锁被释放（锁被替换为写记录）。所以在任何情况下，W 的写对 R 的 Get() 都是可见的。

# 通知

为了实现通知机制，Percolator 需要高效找到被观察的脏 cell。这个搜索是复杂的因为通知往往是稀疏的：我们表有万亿的 cell，但是可能只会有百万个通知。而且，观察者的代码运行在一大批分布式的跨大量机器的客户端进程上，这意味着脏 cell 搜索也必须是分布式的。

为确定 cell 是否脏，Percolator 还是老办法，在 Bigtable 真实数据列旁边维护一个特殊的 “notify” 列，表示此 cell 是否为脏。当一个事务对被监测 cell 执行写操作时，它同时设置对应的 notify cell。worker 对 notify 列执行一个分布式扫描来找到脏 cell。在观察者被触发并且事务提交成功后，我们会删除对应的 notify  cell。因为 notify 列只是一个 Bigtable 列，不是个 Percolator 列，它没有事务型属性，只是作为一个暗示，配合 acknowledgment 列来帮助扫描器确定是否运行观察者。

为了使扫描高效，Percolator 存储 notify 列为一个独立的 Bigtable locality group，所以扫描时仅需读取百万个脏 cell，而不是万亿行个 cell。每个 Percolator 的 worker 指定几个线程负责扫描。对每个线程，worker 为其分配 table 的一部分作为扫描范围，首先挑选一个随机的 tablet，然后挑选一个随机的 key，然后从那个位置开始扫描。因为每个 worker 都在扫描 table 中的一个随机范围，我们担心两个 worker 会扫描到同一行、并发的运行观察者。虽然由于通知的事务本性，这种行为不会导致数据准确性问题，但这是不高效的。为了避免这样，每个 worker 在扫描某行之前需要从一个轻量级锁服务中申请锁。这个锁服务只是咨询性质、并不严格，所以不需要持久化，因此非常可伸缩。

# 讨论

相对于 MR，Percolator 一个不高效的点就是每个 work 单元发送的 RPC 数量。MR 通常只对 GFS 执行一个大型的 read 操作以获取所有需要的数据，而Percolator 处理一个文档就需要执行大约 50 个单独的 Bigtable 操作。导致 RPC 太多的其中一个因素发生在 commit 期间。当写入一个锁时就需要两个 Bigtable的 RPC：一个为查询冲突锁或写记录，另一个来写入新锁。为减少负载，我们修改了 Bigtable 的 API 将两个 RPC 合并（读者可以联想一下 Map 中的 createIfAbsent）。按这个方法，我们会尽量将可以打包批处理的 RPC 调用都合并以减少 RPC 总数。比如将锁操作延缓几秒钟，使它们尽可能的聚集以被批处理。因为锁是并行获取的，所以每个事务仅仅增加了几秒的延迟；这附加的延迟可以用更强的并行来弥补。批处理增大了事务时窗，导致冲突可能性提高，但是通过有效的事务、通知机制，我们的环境中竞争并不强烈，所以不成问题。

从 table 读取时我们也利用了批处理：每个读取操作都被延缓，从而有一定几率让相同 tablet 的读取操作打包成批处理（类似 buffer 的原理）。这样会延缓每次读取，也可能增加不少的事务延迟。为了解决这个问题，我们采用了预取机制。实验证明从同一行里读取一个数据和读取多个数据所产生的消耗相差不大，因为Bigtable 都要从文件系统读取一整个 SSTable 块并解压缩。Percolator 尝试在每次读取某一行的某一列时都做预测，在本事务中，会不会稍后就要读取该行的其他列。预测是根据过去的行为记录而做出的。通过此方法，降低了几乎 10 倍的 read 次数。

在之前的 Percolator 的实现中，所有 API 调用都会阻塞，然后通过调高每台机器的线程数量来支持高并发、提升 CPU 利用率。相比异步、事件驱动等方案，这种 thread-per-request 的同步模型的代码更易编写。异步方案需要花费大量精力维护上下文状态，导致应用开发更加困难。根据我们的实际经验，thread-per-request 的同步模型还是可圈可点的，它的应用代码简单，多核机器 CPU 利用率也不错，同步调用下的堆栈跟踪也很方便调试，所遭遇的资源竞争也没有想象中那么恐怖。不过它的最大缺点是可伸缩性问题，linux 内核、Google 的各种基础设施在遭遇很高的线程数时往往导致瓶颈。不过我们有 in-house 内核开发小组来帮助解决内核问题。

# Links

1. Peng, Daniel, and Frank Dabek. "Large-scale incremental processing using distributed transactions and notifications." *9th USENIX Symposium on Operating Systems Design and Implementation (OSDI 10)*. 2010.

