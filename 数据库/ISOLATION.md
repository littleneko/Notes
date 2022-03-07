# 相关概念
## 可串行化相关

- **well-formed**: 事务中所有的 READ、WRITE、UNLOCK 操作都由锁覆盖，并且锁最终会 UNLOCK
- **two-phase**: 一个事务所有的 LOCK 操作都在 UNLOCK 操作之前
- **串行调度 (Serial History)**: 一次一个事物
- **合法调度**: 同一时间没有发生两个不同事务的锁冲突
- **冲突 (conflict)**: 不同事物操作同一份数据 (a row, a page, ..., a set of data items covered by predicate lock)，其中至少一个操作是 Write
- **等价调度 (equivalent)**: 调度具有相同的依赖图 (dependency graph)
- **可串行化调度 (serializable，或者称之为隔离调度)**: 调度等价于某个串行调度。
## Phenomena
下面的定义中，A 和 P 分别表示:
**P: broad interpretation**
**A: strict interpretation**
按正常的逻辑来理解，只需要 A 就已经够了，实际上 ANSI 的定义中使用的是 P，具体原因见下一节。

### P0 脏写 (Dirty Write)
T1 修改了某一份数据，T2 在 T1 COMMIT 或 ROLLBACK 之前也修改了这份数据。
```
P0: w1[x]...w2[x]...((c1 or a1) [and (c2 or a2) in any order)]
```
### P1 脏读 (Dirty Read)
T2 读了 T1 未 COMMIT 或 ROLLBACK 的数据，如果这时候 T1 ROLLBACK 了，那么 T2 读到的数据就是脏的。
**WRITE → READ依赖**

```
P1: w1[x]...r2[x]...((c1 or a1) [and (c2 or a2) in any order)]
A1: w1[x]...r2[x]...(a1 and c2 in any order)
```
### P2 不可重复读 (Non-RepeatableRead)
在事物中 T1 读了数据，然后 T2 修改或删除了这份数据，等到 T1 再次读取时发现数据已经被更改了。
```
P2: r1[x]...w2[x]...((c1 or a1) [and (c2 or a2) in any order)]
A2: r1[x]...w2[x]...c2...r1[x]...c1
```
### P3 幻读 (Phantom)
在事物中 T1 读取了满足某个条件的数据，然后 T2 插入了满足该条件的数据，T1 再次读取时发现多了数据。
```
P3: r1[P]...w2[y in P]...((c1 or a1) [and (c2 or a2) any order)]
A3: r1[P]...w2[y in P]...c2...r1[P]...c1
```
> **Tips**:
>
> 不可重复读和幻读的区别在于前者是读一条特定的行发现不一致，后者是读到新插入或删除的数据发现不一致

### P4 丢失更新 (Lost Update)

**WRITE -> WRITE 依赖**

```
P4: r1[x]...w2[x]...w1[x]...c1
```
### P4C 游标丢失更新 (Cursor Lost Update)
```
P4C: rc1[x]...w2[x]...w1[x]...c1
```
### A5A 读偏序 (Read Skew)
假设 x 和 y 之间满足一致性约束 C，T1 读了 x，然后 T2 写了 x 和 y，然后 T1 读了 y，此时 T1 会发现 x 和 y 不满足 c。
```
A5A: r1[x]...w2[x]...w2[y]...c2...r1[y]...(c1 or a1)
```
> **Tips**:
>
> e.g. 假设 a 和 b 必须满足一致性约束 a + b == 100，初始值 a = b = 50.
>
>事务 T1 首先读取 x = 50，同时事务 T2 写入了 x = 25 和 y = 75。然后事务 T1 继续读取了 x = 75。这时 T1 发现 x + y = 125，违背了一致性约束。
> 

### A5B 写偏序 (Write Skew)

事务都提交后可能导致 x 和 y 不满足一致性约束 C。假设 x 和 y 之间满足一致性约束 C，T1 读了 x 和 y，T2 也读了 x 和 y；然后 T2 写了 x 使 C 满足，T1 写了 y 使 C 满足；两个事务都提交后可能导致 x 和 y 不满足一致性约束 C。
```
A5B: r1[x]...r2[y]...w1[y]...w2[x]...(c1 and c2 occur)
```
> **Tips**:
>
> e.g. 假设我们的约束是 x + y ≤ 100
>
> 事务 T1 读取了 x = 30，并将 y = 60 写入了数据库，事务 T2 读取了 y = 10，并将 x = 50 写回了数据库。此时数据库中 x + y = 110，违背了一致性约束。

### Broad Interpretation and Strict Interpretation

**结论：ANSI Isolation 的定义应该基于 Broad Interpretation**
下面的 H1、H2、H3 三个反例证明了这一点。

- H1 虽然不违背 A1、A2、A3，但是会导致读到的数据不满足一致性 (x+y=100)
```
H1: r1[x=50]w1[x=10]r2[x=10]r2[y=50]c2 r1[y=50]w1[y=90]c1
```

- H2 不违背 A2，但是 T1 读到的数据同样会发现不满足一致性 (x+y=100)
```
H2: r1[x=50]r2[x=50]w2[x=10]r2[y=50]w2[y=90]c2 r1[y=90]c1
```

- H2不 违背 A2，但是 T1 读到的数据同样会发现不满足一致性 (x+y=100)
```
H3: r1[P] w2[insert y to P] r2[z] w2[z] c2 r1[z] c1
```
# 隔离级别的定义
## Jim Gray 关于 Isolation Degree 的定义

| Degree  | user's definition  | lock protocols  |
| --- | --- | --- |
| Degree 0  | 不会重写高级别事务的脏数据 | well-formed with write  |
| Degree 1  | 没有**丢失更新 ** | well-formed with write, two-phase with exclusive lock  |
| Degree 2  | 没有**丢失更新**，没有**脏读 ** | well-formed, two-phase with exclusive lock  |
| Degree 3  | 没有**丢失更新**，**可重复读**(没有**脏读**)  | well-formed, two-phase  |

* 0 级忽略了所有依赖，1 级对 WRITE -> WRITE 依赖敏感
* 2 级对 WRITE -> WRITE 和 READ –> READ 依赖敏感
* 3 级实际上是真正的串行化隔离级别。

## 基于 Phenomena 定义的隔离级别

**Table 3. ANSI SQL Isolation Levels Defined in terms of the four phenomena**

| Isolation Level  | P0 Dirty Write  | P1 Dirty Read  | P2 Fuzzy Read  | P3 Phantom  |
| --- | --- | --- | --- | --- |
| READ UNCOMMITTED  | Not Possible  | Possible  | Possible  | Possible  |
| READ COMMITTED  | Not Possible  | Not Possible  | Possible  | Possible  |
| REPEATABLE READ  | Not Possible  | Not Possible  | Not Possible  | Possible  |
| SERIALIZABLE  | Not Possible  | Not Possible  | Not Possible  | Not Possible  |


## 基于 Lock 定义的隔离级别

**Table 2. Degrees of Consistency and Locking Isolation Levels defined in terms of locks.**

| Consistency Level = Locking Isolation Level  | Read Locks on Data Items and Predicates (the same unless noted)  | Write Locks on Data Items and Predicates (always the same)  |
| --- | --- | --- |
| Degree 0  | none required  | Well-formed Writes  |
| Degree 1 = Locking READ UNCOMMITTED  | none required  | Well-formed Writes Long duration Write locks  |
| Degree 2 = Locking READ COMMITTED  | Well-formed Reads Short duration Read locks (both)  | Well-formed Writes, Long duration Write locks  |
| Cursor Stability (see Section 4.1)  | Well-formed Reads Read locks held on current of cursor Short duration Read Predicate locks  | Well-formed Writes, Long duration Write locks  |
| Locking REPEATABLE READ  | Well-formed Reads Long duration data-item Read locks Short duration Read Predicate locks  | Well-formed Writes, Long duration Write locks  |
| Degree 3 = Locking SERIALIZABLE  | Well-formed Reads Long duration Read locks (both)  | Well-formed Writes, Long duration Write locks  |


## 其他隔离级别
### Cursor Stability

- **游标稳定性消除了丢失更新 (Lost Update)。**

一个基于游标更新的 FECTH，跟着一个独立的更新或一个基于游标的更新。为了防止丢失修改，大多数 SQL 系统对当前游标指向的记录始终保持一个共享锁。
#### CursorStability 和其他隔离级别的关系

-  READ COMMITTED « Cursor Stability « REPEATABLE READ
### Snapshot Isolation

Snapshot Isolation 实际上是一种 MVCC 的策略。
Each transaction reads reads data from a snapshot of the (committed) data as of the time the transaction started, called its Start-Timestamp.
**First-committer-wins**: The transaction successfully commits only if no other transaction T2 with a Commit- Timestamp in T1’s execution interval [Start- Timestamp, Commit-Timestamp] wrote data that T1 also wrote.

- **First-committer-wins 策略防止了丢失更新(P4)**
#### Snapshot isolation 和其他隔离级别的关系
Snapshot Isolation 是一种特殊的隔离级别，无法准确的说到底处于 ANSI 定义的隔离级别中的哪一个位置。

- **READ COMMITTED « Snapshot Isolation**

**证明**:

1. first-committer-wins 保证了不会有脏写(P0);
2. timestamp read 保证了不会有脏读 (P1);
3. 读偏序(A5A)在 READ COMMIT 下会发生，但是在 Snapshot Isolation下不会发生(r1[y]是 timestamp读)
- **REPEATABLE READ »« Snapshot Isolation**

**证明**:

1. A5B在Snapshot Isolation下会发生，解决P2就不会发生A5B(P2: r1[x]...w2[x])。因此可以 认为REPEATABLE READ > Snapshot Isolation;
2. Snapshot Isolation下不会发生A3，但是RR隔离级 别下会发生A3。因此可以认为Snapshot Isolation > REPEATABLE READ

**注: Snapshot Isolation下虽然不会发生 A3，但是会出现 P3**

# 最终结论

**Table 4. Isolation Types Characterized by Possible Anomalies Allowed.**

| Isolation level  | P0 Dirty Write  | P1 Dirty Read  | P4C Cursor Lost Update  | P4 Lost Update  | P2 Fuzzy Read  | P3 Phantom  | A5A Read Skew  | A5B Write Skew  |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| READ UNCOMMITTED == Degree 1  | Not Possible  | Possible  | Possible  | Possible  | Possible  | Possible  | Possible | Possible  |
| READ COMMITTED == Degree 2  | Not Possible  | Not Possible  | Possible  | Possible  | Possible  | Possible  | Possible  | Possible  |
| Cursor Stability  | Not Possible  | Not Possible  | Not Possible  | Sometimes Possible  | Sometimes Possible  | Possible  | Possible  | Sometimes Possible  |
| REPEATABLE READ  | Not Possible  | Not Possible  | Not Possible  | Not Possible  | Not Possible  | Possible  | Not Possible  | Not Possible  |
| Snapshot  | Not Possible  | Not Possible  | Not Possible  | Not Possible  | Not Possible  | Sometime s Possible  | Not Possible  | Possible  |
| ANSI SQL SERIALIZABLE == Degree 3 == Repeatable Read Date, IBM, Tandem, ...  | Not Possible  | Not Possible  | Not Possible  | Not Possible  | Not Possible  | NotPossible  | Not Possible  | Not Possible  |


## Q&A
**Q1**: RR 为什么不会有 A5A 和 A5B?
**A1**: P2: r1[x]...w2[x]...((c1 or a1) 已经保证了不会发生 A5A 和 A5B; 

**Q2**: Snapshot 下为什么不会新出现 A5A 但会出现 A5B? 
**A2**: 不会出现 A5A 是因为 Snapshot 读的都是事务开始时的快照，会出现 A5B 是因为修改仍然是基于最开始读取的值。 

**Q3**: Snapshot 下为什么会出现 P3 
**A3**: However, Snapshot Isolation does not preclude P3. Consider a constraint that says a set of job tasks deter- mined by a predicate cannot have a sum of hours greater than 8. T1 reads this predicate, determines the sum is only 7 hours and adds a new task of 1 hour duration, while a concurrent transaction T2 does the same thing. Since the two transactions are inserting different data items (and different index entries as well, if any), this scenario is not precluded by First-Committer-Wins and can occur in Snapshot Isolation. But in any equivalent serial history, the phenomenon P3 would arise under this scenario.

## 几个疑问

1.  RU == Degree 1，写锁两阶段，为什么会有 Lost Update
2. 完全基于锁实现的隔离级别，怎么保证高级别的隔离级别的正确性。比如说 RC 虽然对读加锁，但是另一个 Degree 0 的事务并没有对写加两阶段锁
# Reference

1. Berenson H, Bernstein P, Gray J, et al. A critique of ANSI SQL isolation levels[C]//ACM SIGMOD Record. ACM, 1995, 24(2): 1-10. 
2. Gray J, Reuter A. Transaction processing: concepts and techniques[M]. Elsevier, 1992. 
3. Innodb 中的事务隔离级别和锁的关系: [https://tech.meituan.com/2014/08/20/innodb-lock.html](https://tech.meituan.com/2014/08/20/innodb-lock.html) 
