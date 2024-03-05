对于解析MySQL的binlog用来更新其他数据存储的应用来说，binlog的顺序标识是很重要的。比如根据时间戳得到binlog位点作为解析起点，所以需要能够确定binlog顺序的一个标志。
# binlog格式
一个完整的binlog event格式如下：
![](https://cdn.nlark.com/yuque/0/2019/png/385742/1564035717974-3319f421-85b5-4068-ba68-d10c6839f1fc.png#height=362&id=jvWvE&originHeight=723&originWidth=635&originalType=binary&ratio=1&status=done&style=none&width=318)
一个典型的事务在binlog中的内容如下(使用mysqlbinlog解析得到，设置`binlog_format=ROW`, `binlog_row_image=full`)：
```
# at 1975
#180921 18:33:43 server id 1  end_log_pos 2040 CRC32 0xd0d984ad     GTID    last_committed=5    sequence_number=6    rbr_only=yes
/*!50718 SET TRANSACTION ISOLATION LEVEL READ COMMITTED*//*!*/;
SET @@SESSION.GTID_NEXT= '9a54a748-bd4f-11e8-9469-e2ee2de8debb:11'/*!*/;
# at 2040
#180921 18:31:57 server id 1  end_log_pos 2112 CRC32 0xe92adeca     Query    thread_id=3    exec_time=0    error_code=0
SET TIMESTAMP=1537525917/*!*/;
BEGIN
/*!*/;
# at 2112
#180921 18:31:57 server id 1  end_log_pos 2168 CRC32 0x903bad28     Table_map: `test`.`table1` mapped to number 119
# at 2168
#180921 18:31:57 server id 1  end_log_pos 2255 CRC32 0x38de19eb     Update_rows: table id 119 flags: STMT_END_F

BINLOG '
ncikWxMBAAAAOAAAAHgIAAAAAHcAAAAAAAEABHRlc3QABnRhYmxlMQAECA8PAwTwAPAAACitO5A=
ncikWx8BAAAAVwAAAM8IAAAAAHcAAAAAAAEAAgAE///wAQAAAAAAAAAHbGl0YW8xMARtYXJzZAAA
APABAAAAAAAAAAZsaXRhbzEEbWFyc2QAAADrGd44
'/*!*/;
### UPDATE `test`.`table1`
### WHERE
###   @1=1 /* LONGINT meta=0 nullable=0 is_null=0 */
###   @2='litao10' /* VARSTRING(240) meta=240 nullable=0 is_null=0 */
###   @3='mars' /* VARSTRING(240) meta=240 nullable=0 is_null=0 */
###   @4=100 /* INT meta=0 nullable=0 is_null=0 */
### SET
###   @1=1 /* LONGINT meta=0 nullable=0 is_null=0 */
###   @2='litao1' /* VARSTRING(240) meta=240 nullable=0 is_null=0 */
###   @3='mars' /* VARSTRING(240) meta=240 nullable=0 is_null=0 */
###   @4=100 /* INT meta=0 nullable=0 is_null=0 */
# at 2255
#180921 18:33:41 server id 1  end_log_pos 2311 CRC32 0x3cc14438     Table_map: `test`.`table1` mapped to number 119
# at 2311
#180921 18:33:41 server id 1  end_log_pos 2374 CRC32 0x5083fa6d     Write_rows: table id 119 flags: STMT_END_F

BINLOG '
BcmkWxMBAAAAOAAAAAcJAAAAAHcAAAAAAAEABHRlc3QABnRhYmxlMQAECA8PAwTwAPAAADhEwTw=
BcmkWx4BAAAAPwAAAEYJAAAAAHcAAAAAAAEAAgAE//AGAAAAAAAAAAZsaXRhbzYHYmVpamluZ5AB
AABt+oNQ
'/*!*/;
### INSERT INTO `test`.`table1`
### SET
###   @1=6 /* LONGINT meta=0 nullable=0 is_null=0 */
###   @2='litao6' /* VARSTRING(240) meta=240 nullable=0 is_null=0 */
###   @3='beijing' /* VARSTRING(240) meta=240 nullable=0 is_null=0 */
###   @4=400 /* INT meta=0 nullable=0 is_null=0 */
# at 2374
#180921 18:33:43 server id 1  end_log_pos 2405 CRC32 0xa56469b8     Xid = 122
COMMIT/*!*/;
```
可以看到binlog中一个事务以GTID Event开始已XID Event结束。每个Event都有一个时间戳，对于GTID Event还有GTID、last_committed、sequence_number等信息。
# binlog中和时序有关的字段
从上图中可以看到，binlog中和时序有关的字段可能有时间戳、xid、gtid、sequence_number这几个。
其中时间戳从event header的timestamp中读取；gtid和sequence_number从gtid event中获取；xid从xid event中获取。
这四个值中，哪个是真正有序的，能够作为寻找binlog位置的依据呢。
## 时间戳
首先来看一个binlog片段：
```
#180921 15:19:23 server id 1  end_log_pos 574 CRC32 0x94fcf43e  GTID  last_committed=1  sequence_number=2 rbr_only=yes
SET @@SESSION.GTID_NEXT= '9a54a748-bd4f-11e8-9469-e2ee2de8debb:7'/*!*/;
#180921 15:18:36 server id 1  end_log_pos 646 CRC32 0x4503f3f5  Query thread_id=4 exec_time=0 error_code=0
SET TIMESTAMP=1537514316/*!*/;
#180921 15:18:36 server id 1  end_log_pos 702 CRC32 0xb68fe4e3  Table_map: `test`.`table1` mapped to number 119
#180921 15:18:36 server id 1  end_log_pos 765 CRC32 0x60cb13bd  Write_rows: table id 119 flags: STMT_END_F
#180921 15:19:03 server id 1  end_log_pos 821 CRC32 0xa1a67b57  Table_map: `test`.`table1` mapped to number 119
#180921 15:19:03 server id 1  end_log_pos 910 CRC32 0xb7a21637  Update_rows: table id 119 flags: STMT_END_F
#180921 15:19:23 server id 1  end_log_pos 941 CRC32 0xc2ccaae5  Xid = 111

#180921 15:19:19 server id 1  end_log_pos 1006 CRC32 0x560ab776   GTID  last_committed=2  sequence_number=3 rbr_only=yes
SET @@SESSION.GTID_NEXT= '9a54a748-bd4f-11e8-9469-e2ee2de8debb:8'/*!*/;
#180921 15:19:19 server id 1  end_log_pos 1078 CRC32 0xabd930cd   Query thread_id=3 exec_time=4 error_code=0
SET TIMESTAMP=1537514359/*!*/;
#180921 15:19:19 server id 1  end_log_pos 1134 CRC32 0xaaa801d0   Table_map: `test`.`table1` mapped to number 119
#180921 15:19:19 server id 1  end_log_pos 1221 CRC32 0xeabf23ab   Update_rows: table id 119 flags: STMT_END_F
#180921 15:19:19 server id 1  end_log_pos 1252 CRC32 0xd24234be   Xid = 116

#180921 15:20:10 server id 1  end_log_pos 1317 CRC32 0xa7f16789   GTID  last_committed=3  sequence_number=4 rbr_only=yes
SET @@SESSION.GTID_NEXT= '9a54a748-bd4f-11e8-9469-e2ee2de8debb:9'/*!*/;
#180921 15:20:10 server id 1  end_log_pos 1389 CRC32 0x6be44f2a   Query thread_id=4 exec_time=0 error_code=0
SET TIMESTAMP=1537514410/*!*/;
#180921 15:20:10 server id 1  end_log_pos 1445 CRC32 0x8343c851   Table_map: `test`.`table1` mapped to number 119
#180921 15:20:10 server id 1  end_log_pos 1508 CRC32 0x1bd75475   Write_rows: table id 119 flags: STMT_END_F
#180921 15:20:10 server id 1  end_log_pos 1539 CRC32 0x207ca814   Xid = 120
```
从上面的binlog片段中可以看到，一共有三个事务，每个事务有多个event，每个event的第一行是时间戳(如180921 15:19:23)。可以看到这个三个事务的XID Event的时间戳分别为xid=111: “180921 15:19:23”、xid=116: “180921 15:19:19”、xid=120: “180921 15:20:10”。在binlog中XID event表示一个事务commit了，MySQL是在事务commit前才刷盘的，按理说xid evnet的时间戳可以表示事务结束的时间，然而可以看到第二个xid=116的event的时间戳比第一个xid=111的时间戳还小，难道是binlog的时间戳出问题了？
为了解释这个问题，先看看上面的binlog是如何生成的：

| T1(111) | T2(116) | T3(120) |
| --- | --- | --- |
| BEGIN | 

 | 

 |
| INSERT | 

 | 

 |
| UPDATE ... WHERE id = 1 | 

 | 

 |
| 

 | UPDATE ... WHERE id = 1 (wait) | 

 |
| COMMIT | 

 | 

 |
| 

 | (AUTO COMMIT) | 

 |
| 

 | 

 | INSERT (AUTO COMMIT) |

可以看到T2的COMMIT时间实际上是在T1 COMMIT之后的，但是从binlog中看到的时间戳却在T1之前。导致这个情况的原因是因为binlog中的时间戳并不是这个event真正生成时的时间，而是语句被执行时的时间。

- MySQL官方文档中对timestamp的描述：
> 4 bytes. This is the time at which the statement began executing. It is represented as the number of seconds since 1970 (UTC), like the TIMESTAMP SQL data type.

因为T2只有一条UPDATE语句，而且是AUTO CIMMIT的，AUTO COMMIT的事务最后实际的COMMIT操作并不会计入时间戳，而该UPDATE被执行的时间是在T1 COMMIT之前，UPDATE之后，所以时间戳符合预期。
可以看到T1最后xid的时间实际上是COMMIT语句执行时的时间戳。
## xid
首先来看一个binlog片段：
```
#180921 18:33:27 server id 1  end_log_pos 1604 CRC32 0x7066ad97     GTID    last_committed=4    sequence_number=5    rbr_only=yes
SET @@SESSION.GTID_NEXT= '9a54a748-bd4f-11e8-9469-e2ee2de8debb:10'/*!*/;
#180921 18:32:52 server id 1  end_log_pos 1676 CRC32 0x8cb2e484     Query    thread_id=4    exec_time=0    error_code=0
#180921 18:32:52 server id 1  end_log_pos 1732 CRC32 0x6eb9c966     Table_map: `test`.`table1` mapped to number 119
#180921 18:32:52 server id 1  end_log_pos 1825 CRC32 0xbbeb0398     Update_rows: table id 119 flags: STMT_END_F
#180921 18:33:25 server id 1  end_log_pos 1881 CRC32 0x1d7dd283     Table_map: `test`.`table1` mapped to number 119
#180921 18:33:25 server id 1  end_log_pos 1944 CRC32 0x7c469d2e     Write_rows: table id 119 flags: STMT_END_F
#180921 18:33:27 server id 1  end_log_pos 1975 CRC32 0x29442cd5     Xid = 125

#180921 18:33:43 server id 1  end_log_pos 2040 CRC32 0xd0d984ad     GTID    last_committed=5    sequence_number=6    rbr_only=yes
SET @@SESSION.GTID_NEXT= '9a54a748-bd4f-11e8-9469-e2ee2de8debb:11'/*!*/;
#180921 18:31:57 server id 1  end_log_pos 2112 CRC32 0xe92adeca     Query    thread_id=3    exec_time=0    error_code=0
#180921 18:31:57 server id 1  end_log_pos 2168 CRC32 0x903bad28     Table_map: `test`.`table1` mapped to number 119
#180921 18:31:57 server id 1  end_log_pos 2255 CRC32 0x38de19eb     Update_rows: table id 119 flags: STMT_END_F
#180921 18:33:41 server id 1  end_log_pos 2311 CRC32 0x3cc14438     Table_map: `test`.`table1` mapped to number 119
#180921 18:33:41 server id 1  end_log_pos 2374 CRC32 0x5083fa6d     Write_rows: table id 119 flags: STMT_END_F
#180921 18:33:43 server id 1  end_log_pos 2405 CRC32 0xa56469b8     Xid = 122
```
binlog中每个事务都会分配一个全局唯一的ID，从上图中可以看到有两个事务，XID分别为125何122。因为binlog一定是按事务COMMIT的顺序记录的，所以XID为125的事务一定在XID为122的事务之前COMMIT。所以binlog中XID也并不能代表事务COMMIT的顺序。
上面的binlog是通过如下的两个事务生成的:

| T1(122) | T2(125) |
| --- | --- |
| BEGIN | 

 |
| UPDATE ... WHERE id = 3 | 

 |
| 

 | BEGIN |
| 

 | UPDATE ... WHERE id = 2 |
| 

 | INSERT |
| 

 | COMMIT |
| INSERT | 

 |
| COMMIT | 

 |

每个事务的Xid来源于事务第一条语句的query_id，上面可以看到T1事务先开始，后于T2结束。因此T1的xid要小于T2的XID，但是T2先结束，所以先写到binlog中。
## gtid
GTID和XID一样，是一个全局递增的ID，与XID不同的是，GTID是在事务COMMIT binlog写盘的时候生成，因此GTID能够表示事务真正COMMIT的时序。
源码中对GTID的解释，这里默认的是`AUTOMATIC_GROUP`
```cpp
/**
    Specifies that the GTID has not been generated yet; it will be
    generated on commit.  It will depend on the GTID_MODE: if
    GTID_MODE<=OFF_PERMISSIVE, then the transaction will be anonymous;
    if GTID_MODE>=ON_PERMISSIVE, then the transaction will be assigned
    a new GTID.

    This is the default value: thd->variables.gtid_next has this state
    when GTID_NEXT="AUTOMATIC".

    It is important that AUTOMATIC_GROUP==0 so that the default value
    for thd->variables->gtid_next.type is AUTOMATIC_GROUP.
  */
  AUTOMATIC_GROUP= 0,
  /**
    Specifies that the transaction has been assigned a GTID (UUID:NUMBER).

    thd->variables.gtid_next has this state when GTID_NEXT="UUID:NUMBER".

    This is the state of GTID-transactions replicated to the slave.
  */
  GTID_GROUP,
  /**
    Specifies that the transaction is anonymous, i.e., it does not
    have a GTID and will never be assigned one.

    thd->variables.gtid_next has this state when GTID_NEXT="ANONYMOUS".

    This is the state of any transaction generated on a pre-GTID
    server, or on a server with GTID_MODE==OFF.
  */
ANONYMOUS_GROUP
```
## last_committed and sequence_number
从上面两个binlog片段中可以看到，在GTID Event中，还有last_committed 和 sequence_number两个字段，这两个字段看起来和GTID的增长一致。在每个binlog产生时从1开始然后递增,每增加一个事务则sequencenumber就加1,你可能好奇有了gtid何必多此一举再加个sequencenumber来标识事务呢。
实际上这两个值是用于group commit，在binlog中用来标识组提交,同一个组提交里多个事务gtid不同,但lastcommitted确是一致的,MySQL正是依据各个事务的lastcommitted来判断它们在不在一个组里;一个组里的lastcommitted与上一个组提交事务的sequencenumber相同,这样sequencenumber就必须存在了:
```
...... 
xxxxxxxxxxxx   GTID    last_committed=3        sequence_number=8   
xxxxxxxxxxxx   GTID    last_committed=3        sequence_number=9   
xxxxxxxxxxxx   GTID    last_committed=9        sequence_number=10   
...... 
xxxxxxxxxxxx   GTID    last_committed=9        sequence_number=24   
xxxxxxxxxxxx   GTID    last_committed=24        sequence_number=25   
......
```

这代表sequencenumber=10到sequencenumber=24的事务在同一个组里(因为lastcommitted都相同,是9)
note:
> 组提交只与lastcommitted有关,这也是MySQL基于组提交(logic clock)的并行复制方式即使在gtid关闭情形下也能生效的原因。

有关group commit更详细的信息，可以参考资料[6][7]
# 总结：
通过上面的分析，知道binlog中的时间戳、xid都不一定和事务实际COMMIT的顺序一致，只有GTID和sequence_number是和事务COMMIT顺序一致的。
本文只是对binlog中这几个和时序相关的字段做了简单的分析，很多问题都没有深入研究，比如超大事务时binlog何时刷盘、GTID具体的生成逻辑、last_committed是如何计算的、group commit是怎么判断多个事务是可以并行复制的等等问题还有待深入研究。
# 参考资料
[1] [https://dev.mysql.com/doc/internals/en/event-header-fields.html](https://dev.mysql.com/doc/internals/en/event-header-fields.html)
[2] Binlog中的时间戳: [http://www.broadview.com.cn/article/310](http://www.broadview.com.cn/article/310)
[3] MySQL · 答疑释惑 · binlog event有序性: [http://mysql.taobao.org/monthly/2014/12/05/](http://mysql.taobao.org/monthly/2014/12/05/)
[4] 深入理解MySQL 5.7 GTID系列（三）：GTID的生成时机:[https://yq.aliyun.com/articles/364921](https://yq.aliyun.com/articles/364921)
[5] MySQL · 特性分析 ·MySQL 5.7新特性系列四: [http://mysql.taobao.org/monthly/2016/08/01/](http://mysql.taobao.org/monthly/2016/08/01/)
[6] 【腾讯云CDB】源码分析 · MySQL binlog组提交和Multi-Threaded-Slave: [https://cloud.tencent.com/developer/article/1008565](https://cloud.tencent.com/developer/article/1008565)
[7] [https://www.jianshu.com/p/e051000e0cce](https://www.jianshu.com/p/e051000e0cce)

## Attachments:
![](https://cdn.nlark.com/yuque/0/2019/gif/385742/1564035719116-7d1d28d6-9b56-49d1-a74f-c90d954c2275.gif#height=8&id=GL3ZK&originHeight=8&originWidth=8&originalType=binary&ratio=1&status=done&style=none&width=8)[image2019-5-23_0-28-41.png](https://cdn.nlark.com/yuque/0/2019/png/385742/1564035717974-3319f421-85b5-4068-ba68-d10c6839f1fc.png)
