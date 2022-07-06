https://github.com/pingcap/awesome-database-learning

How do we build TiDB: https://pingcap.com/zh/blog/how-do-we-build-tidb

# 事务

TiDB 事务隔离级别: https://docs.pingcap.com/zh/tidb/dev/transaction-isolation-levels#tidb-%E4%BA%8B%E5%8A%A1%E9%9A%94%E7%A6%BB%E7%BA%A7%E5%88%AB

事务前沿研究 | 隔离级别的追溯与究明，带你读懂 TiDB 的隔离级别（上篇）: https://pingcap.com/zh/blog/take-you-through-the-isolation-level-of-tidb-1

事务前沿研究 | 隔离级别的追溯与究明，带你读懂 TiDB 的隔离级别（下篇）: https://pingcap.com/zh/blog/take-you-through-the-isolation-level-of-tidb-2


**事务前沿研究丨事务并发控制**: https://pingcap.com/zh/blog/transaction-frontiers-research-article-talk4

TiKV 的 MVCC（Multi-Version Concurrency Control）机制: https://pingcap.com/zh/blog/mvcc-in-tikv


**TiKV 事务模型概览，Google Spanner 开源实现**: https://pingcap.com/zh/blog/tidb-transaction-model

Percolator 和 TiDB 事务算法: https://pingcap.com/zh/blog/percolator-and-txn

Async Commit 原理介绍丨 TiDB 5.0 新特性： https://pingcap.com/zh/blog/async-commit-principle




TiDB 乐观事务模型: https://docs.pingcap.com/zh/tidb/dev/optimistic-transaction

**TiDB 最佳实践系列（三）乐观锁事务**: https://pingcap.com/zh/blog/best-practice-optimistic-transaction

TiDB 悲观事务模式: https://docs.pingcap.com/zh/tidb/dev/pessimistic-transaction

TiDB 新特性漫谈：悲观事务: https://pingcap.com/zh/blog/pessimistic-transaction-the-new-features-of-tidb

TiDB 4.0 新特性前瞻（二）白话“悲观锁”: https://pingcap.com/zh/blog/tidb-4.0-pessimistic-lock

**TiDB 悲观锁实现原理**: https://tidb.net/blog/7730ed79


TiKV 源码解析系列文章（十一）Storage - 事务控制层: https://pingcap.com/zh/blog/tikv-source-code-reading-11
TiKV 源码解析系列文章（十二）分布式事务: https://pingcap.com/zh/blog/tikv-source-code-reading-12

# 分布式

Spanner - CAP, TrueTime and Transaction: https://pingcap.com/zh/blog/Spanner-cap-truetime-transaction

**一致性模型**: https://segmentfault.com/a/1190000016785044

**线性一致性和 Raft**: https://pingcap.com/zh/blog/linearizability-and-raft

TiKV 功能介绍 - Raft 的优化: https://pingcap.com/zh/blog/optimizing-raft-in-tikv

TiKV 功能介绍 - Lease Read: https://pingcap.com/zh/blog/lease-read

基于 Raft 构建弹性伸缩的存储系统的一些实践: https://pingcap.com/zh/blog/building-distributed-db-with-raft

**TiDB 新特性漫谈：从 Follower Read 说起**: https://pingcap.com/zh/blog/follower-read-the-new-features-of-tidb


# 存储

B-Tree/LSM-Tree

LevelDB/RocksDB

行存/列存

TiKV 是如何存取数据的: https://pingcap.com/zh/blog/how-tikv-store-get-data


# SQL 层


# DDL

理解 Google F1: Schema 变更算法: https://disksing.com/understanding-f1-schema-change/