5.6 基于schema -> table
5.7.3之前 Commit-Parent-Based Scheme
5.7.3之后 Lock-Based Scheme
5.7.22之后 Write Set

```cpp
Trx1 ------------P----------C-------------------------------->
                            |
Trx2 ----------------P------+---C---------------------------->
                            |   |
Trx3 -------------------P---+---+-----C---------------------->
                            |   |     |
Trx4 -----------------------+-P-+-----+----C----------------->
                            |   |     |    |
Trx5 -----------------------+---+-P---+----+---C------------->
                            |   |     |    |   |
Trx6 -----------------------+---+---P-+----+---+---C---------->
                            |   |     |    |   |   |
Trx7 -----------------------+---+-----+----+---+-P-+--C------->
                            |   |     |    |   |   |  |
```

- 对于C（lock interval的结束点），MySQL会给每个事务分配一个逻辑时间戳（logical timestamp），命名为：transaction.sequence_number。此外，MySQL会获取全局变量global.max_committed_transaction，含义：所有已经结束lock interval的事务的最大的sequence_number。

- 对于L（lock interval的开始点），MySQL会把global.max_committed_timestamp分配给一个变量，并取名叫transaction.last_committed。

- transaction.sequence_number和transaction.last_committed这两个时间戳都会存放在binlog中。

- 根据以上分析，我们可以得出在slave上执行事务的条件：

- 如果所有正在执行的事务的最小的sequence_number大于一个事务的transaction.last_committed，那么这个事务就可以并发执行。换言之：

- slave 的work线程不能开始执行一个事务，直到这个事务的last_committed值小于所有其他正在执行事务的sequence_number。

- 根据以上分析，回过头来看前面的那幅图 


![](https://cdn.nlark.com/yuque/0/2020/webp/385742/1599560421021-6f73b541-3dd7-4d8a-b94f-bd790d7ef9e4.webp#align=left&display=inline&height=239&originHeight=239&originWidth=458&size=0&status=done&style=none&width=458)

- 可以看到Trx3、Trx4、Trx5、Trx6四个事务可以并发执行。因为Trx3的sequence_number大于Trx4、Trx5、Trx6的last_committed，所以可以并发执行。

- 当Trx3、Trx4、Trx5执行完成之后，Trx6和Trx7可以并发执行。因为Trx6的sequence_number大于Trx7的last_committed，即两者的lock interval存在重叠。Trx5和Trx7不能并发执行，因为：Trx5的sequence_number小于Trx7的last_committed，即两者的lock interval不存在重叠。

- 综上所述，可以有三种方法来判断slave上事务是否可以并行执行：

- 假设有两个事务：Trx1、Trx2。Trx1先于Trx2。那么，当且仅当Trx1、Trx2的lock interval有重叠，则可以并行执行。

- 如果所有正在执行的事务的最小的sequence_number大于一个事务的transaction.last_committed，那么这个事务就可以并发执行。

- slave 的work线程不能开始执行一个事务，直到这个事务的last_committed值小于所有其他正在执行事务的sequence_number。

- 由上分析，新模式Lock-Based Scheme机制的并发度比旧模式Commit-Parent-Based Scheme的并发度要好。



WriteSet
WriteSet并行复制的思想是：不同事务的不同记录不重叠，则都可在从机上并行回放，可以看到并行的力度从组提交细化为记录级。
所谓不同的记录，在MySQL中用WriteSet对象来记录每行记录，从源码来看WriteSet就是每条记录hash后的值（必须开启ROW格式的二进制日志），具体算法如下：
> _**WriteSet=hash(index_name | db_name | db_name_length | table_name | table_name_length | value | value_length)**_


当事务每次提交时，会计算修改的每个行记录的WriteSet值，然后查找哈希表中是否已经存在有同样的WriteSet，若无，WriteSet插入到哈希表，写入二进制日志的last_committed值不变。若有，则last_committed值更新为sequnce_number。

writeset主库单线程执行时在从库也可以并行回放，Commit_Order需要有足够的并发度


1. MySQL · 功能分析 · 5.6 并行复制实现分析: [http://mysql.taobao.org/monthly/2015/08/09/](http://mysql.taobao.org/monthly/2015/08/09/)
2. MySQL · 特性分析 · LOGICAL_CLOCK 并行复制原理及实现分析: [http://mysql.taobao.org/monthly/2017/12/03/](http://mysql.taobao.org/monthly/2017/12/03/)
3. MySQL · 特性分析 · MySQL 5.7新特性系列四: [http://mysql.taobao.org/monthly/2016/08/01/](http://mysql.taobao.org/monthly/2016/08/01/)
4. MySQL · 特性分析 · 8.0 WriteSet 并行复制: [http://mysql.taobao.org/monthly/2018/06/04/](http://mysql.taobao.org/monthly/2018/06/04/)
5. WL#4648: Prototype for multi-threaded slave for row-based replication: [https://dev.mysql.com/worklog/task/?id=4648](https://dev.mysql.com/worklog/task/?id=4648)
6. WL#6314: MTS: Prepared transactions slave parallel applier: [https://dev.mysql.com/worklog/task/?id=6314](https://dev.mysql.com/worklog/task/?id=6314)
7. WL#7165: MTS: Optimizing MTS scheduling by increasing the parallelization window on master: [https://dev.mysql.com/worklog/task/?id=7165](https://dev.mysql.com/worklog/task/?id=7165)
8. MySQL 5.7新特性：并行复制原理（MTS）: [https://blog.csdn.net/andong154564667/article/details/82117727](https://blog.csdn.net/andong154564667/article/details/82117727)
9. MySQL实战45讲 - 备库为什么会延迟好几个小时？: [https://time.geekbang.org/column/article/77083](https://time.geekbang.org/column/article/77083)
10. MySQL并行复制的深入浅出: [https://keithlan.github.io/2018/07/31/mysql_mts_detail/](https://keithlan.github.io/2018/07/31/mysql_mts_detail/)
11. [图解MySQL]MySQL组提交(group commit): [https://mp.weixin.qq.com/s/rcPkrutiLc93aTblEZ7sFg](https://mp.weixin.qq.com/s/rcPkrutiLc93aTblEZ7sFg)
12. MySQL5.7 核心技术揭秘：MySQL Group commit: [http://keithlan.github.io/2018/07/24/mysql_group_commit/](http://keithlan.github.io/2018/07/24/mysql_group_commit/)
13. 速度提升5~10倍，基于WRITESET的MySQL并行复制 #M1013#: [https://mp.weixin.qq.com/s/oj-DzpR-hZRMMziq2_0rYg](https://mp.weixin.qq.com/s/oj-DzpR-hZRMMziq2_0rYg)
14. MySQL层事务提交流程简析: [https://mp.weixin.qq.com/s/ev78uQxao-Ihw9yMS6tFlg](https://mp.weixin.qq.com/s/ev78uQxao-Ihw9yMS6tFlg)
15. MySQL5.7并行复制中并行的真正含义: [https://mp.weixin.qq.com/s/XbWMdVTl9qz1nSwL3l56XQ](https://mp.weixin.qq.com/s/XbWMdVTl9qz1nSwL3l56XQ)
16. WL#9556: Writeset-based MTS dependency tracking on master: [https://dev.mysql.com/worklog/task/?id=9556](https://dev.mysql.com/worklog/task/?id=9556)
