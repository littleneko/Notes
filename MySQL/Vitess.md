# Architecture
![image.png](https://cdn.nlark.com/yuque/0/2020/png/385742/1603984207030-915c8605-3f2c-42eb-ab23-49599cbad815.png#align=left&display=inline&height=956&originHeight=1912&originWidth=3510&size=373251&status=done&style=none&width=1755)
![image.png](https://cdn.nlark.com/yuque/0/2020/png/385742/1603957907916-477e1631-3c8e-45e6-997c-a0a7796704ec.png#align=left&display=inline&height=1072&originHeight=1072&originWidth=2102&size=1948712&status=done&style=none&width=2102)

1. **VTGate：**相当于proxy，所有的SQL请求都通过VTGate转发，在VTGate上进行路由
2. **Topology：**管理一些元数据信息，包含服务器信息、**分片方案**和**主从信息**的元数据信息存储服务
3. **VTTablet：**管理一个MySQL实例，可能是master、replicas...
# Concepts

1. **_**__Keyspace Graph__**_**：Vitess 使用keyspace graph 记录Cell下有多少keyspaces，每个keyspace下有多少shard，每个shard下有多少个tablet，每个tablet的类型是什么。
2. **_Cell_**：数据中心, 可用区域或计算资源组
3. **_keyspace_**： 逻辑上的数据库，在单片场景下，一个keyspace对应一个MYSQL集群；当一个keySpace被sharding成多分片database。在这种情况下一个查询会被路由到一个或者多个shard上，这取决于请求的数据所在的位置
4. _**Shard**_：表示keyspace中的一个分片，一个shard通常包含一个master和读个slave
5. **_Tablet_**：mysqld进程和vttablet的组合。
6. **Tablet Type**：每个tablet都有一个状态，我们称之为Tablet Type，包括**master、****replica、****rdonly、****backup、****restore、****drained**。
   1. **drained**：A tablet that has been reserved by a Vitess background process (such as rdonly tablets for resharding)
7. _**Keyspace ID：**_keyspace ID是用于确定给定行所在的分片的值
## Key Ranges and Partitions
Vitess uses key ranges to determine which shards should handle any particular query.

- A **key range** is a series of consecutive keyspace ID values. It has starting and ending values. A key falls inside the range if it is equal to or greater than the start value and strictly less than the end value.
- A **partition** represents a set of key ranges that covers the entire space.



Several sample key ranges are shown below:
```
Start=[], End=[]: Full Key Range
Start=[], End=[0x80]: Lower half of the Key Range.
Start=[0x80], End=[]: Upper half of the Key Range.
Start=[0x40], End=[0x80]: Second quarter of the Key Range.
Start=[0xFF00], End=[0xFF80]: Second to last 1/512th of the Key Range.
```
# Horizontal Sharding
这里假设已经按官方文档（[https://vitess.io/docs/get-started/local/](https://vitess.io/docs/get-started/local/)）将vitess run起来了，并且已经做了Vertical Split（即已经执行完了local里的101-206的shell脚本），这时集群的现状如下：

- **_keyspace：_**commerce 和 customer
- _**shard：**_commerce和customer都只有一个shard，即没有分片
- _**tablet**_：每个keyspace 3个，type分别为master, replica, replica，commerce下的3个tablet的id分别为100，101，102



集群topo如下：
![image.png](https://cdn.nlark.com/yuque/0/2020/png/385742/1603957960886-ada334b8-ddba-4706-b712-9e2f7e3dbf85.png#align=left&display=inline&height=397&originHeight=397&originWidth=753&size=76291&status=done&style=none&width=753)
commerce下的table和初始数据如下：
```
mysql> use commerce/0
Reading table information for completion of table and column names
You can turn off this feature to get a quicker startup with -A

Database changed
mysql> show tables;
+-----------------------+
| Tables_in_vt_commerce |
+-----------------------+
| customer_seq          |
| order_seq             |
| product               |
+-----------------------+
3 rows in set (0.01 sec)


mysql> desc product;
+-------------+----------------+------+-----+---------+-------+
| Field       | Type           | Null | Key | Default | Extra |
+-------------+----------------+------+-----+---------+-------+
| sku         | varbinary(128) | NO   | PRI | NULL    |       |
| description | varbinary(128) | YES  |     | NULL    |       |
| price       | bigint(20)     | YES  |     | NULL    |       |
+-------------+----------------+------+-----+---------+-------+
3 rows in set (0.00 sec)

mysql> select * from product;
+----------+-------------+-------+
| sku      | description | price |
+----------+-------------+-------+
| SKU-1001 | Monitor     |   100 |
| SKU-1002 | Keyboard    |    30 |
+----------+-------------+-------+
2 rows in set (0.00 sec)
```
其中customer_seq和order_seq表用生成全局id的，暂时忽略。

customer中的table和初始数据如下：
```
mysql> use customer/0;
Reading table information for completion of table and column names
You can turn off this feature to get a quicker startup with -A

Database changed
mysql> show tables;
+-----------------------+
| Tables_in_vt_customer |
+-----------------------+
| corder                |
| customer              |
+-----------------------+
2 rows in set (0.00 sec)

mysql> desc corder;
+-------------+----------------+------+-----+---------+-------+
| Field       | Type           | Null | Key | Default | Extra |
+-------------+----------------+------+-----+---------+-------+
| order_id    | bigint(20)     | NO   | PRI | NULL    |       |
| customer_id | bigint(20)     | YES  |     | NULL    |       |
| sku         | varbinary(128) | YES  |     | NULL    |       |
| price       | bigint(20)     | YES  |     | NULL    |       |
+-------------+----------------+------+-----+---------+-------+
4 rows in set (0.01 sec)


mysql> desc customer;
+-------------+----------------+------+-----+---------+-------+
| Field       | Type           | Null | Key | Default | Extra |
+-------------+----------------+------+-----+---------+-------+
| customer_id | bigint(20)     | NO   | PRI | NULL    |       |
| email       | varbinary(128) | YES  |     | NULL    |       |
+-------------+----------------+------+-----+---------+-------+
2 rows in set (0.00 sec)

mysql> select * from corder;
+----------+-------------+----------+-------+
| order_id | customer_id | sku      | price |
+----------+-------------+----------+-------+
|        1 |           1 | SKU-1001 |   100 |
|        2 |           2 | SKU-1002 |    30 |
|        3 |           3 | SKU-1002 |    30 |
|        4 |           4 | SKU-1002 |    30 |
|        5 |           5 | SKU-1002 |    30 |
+----------+-------------+----------+-------+
5 rows in set (0.00 sec)

mysql> select * from customer;
+-------------+--------------------+
| customer_id | email              |
+-------------+--------------------+
|           1 | alice@domain.com   |
|           2 | bob@domain.com     |
|           3 | charlie@domain.com |
|           4 | dan@domain.com     |
|           5 | eve@domain.com     |
+-------------+--------------------+
5 rows in set (0.00 sec)
```
> **Tips**
这里我们是使用的 > _use commerce/0 _切换到> _commerce_的，实际上因为只有一个> _shard_，使用> _use commerce_和> _use commerce/0_是同样的效果

Putting it all together, we have the following VSchema for `customer`:
```
{
  "sharded": true,
  "vindexes": {
    "hash": {
      "type": "hash"
    }
  },
  "tables": {
    "customer": {
      "column_vindexes": [
        {
          "column": "customer_id",
          "name": "hash"
        }
      ],
      "auto_increment": {
        "column": "customer_id",
        "sequence": "customer_seq"
      }
    },
    "corder": {
      "column_vindexes": [
        {
          "column": "customer_id",
          "name": "hash"
        }
      ],
      "auto_increment": {
        "column": "order_id",
        "sequence": "order_seq"
      }
    }
  }
}
```
上述配置表示customer表的vindexes为customer_id列，使用hash方式做分片
## Create new shards
该步骤创建两个新的tablet用于customer的resharding，其中id为300、301、302的3个table的SHARD=-80；id为400、401、402的3个table的SHARD=80-：
```
source ./env.sh
 
for i in 300 301 302; do
 CELL=zone1 TABLET_UID=$i ./scripts/mysqlctl-up.sh
 SHARD=-80 CELL=zone1 KEYSPACE=customer TABLET_UID=$i ./scripts/vttablet-up.sh
done
 
for i in 400 401 402; do
 CELL=zone1 TABLET_UID=$i ./scripts/mysqlctl-up.sh
 SHARD=80- CELL=zone1 KEYSPACE=customer TABLET_UID=$i ./scripts/vttablet-up.sh
done
```
然后将300、400设置为master，并copy schema：
```
vtctlclient -server localhost:15999 InitShardMaster -force customer/-80 zone1-300
vtctlclient -server localhost:15999 InitShardMaster -force customer/80- zone1-400
vtctlclient -server localhost:15999 CopySchemaShard customer/0 customer/-80
vtctlclient -server localhost:15999 CopySchemaShard customer/0 customer/80-
```
现在，使用use customer/-80和use customer/80-就可以看到新建的两个tablet中的表，现在两个新的tablet中没有数据。
## SplitClone
```
vtworker \
 $TOPOLOGY_FLAGS \
 -cell zone1 \
 -log_dir "$VTDATAROOT"/tmp \
 -alsologtostderr \
 -use_v3_resharding_mode \
 SplitClone -min_healthy_rdonly_tablets=1 customer/0
```
For large tables, this job could potentially run for many days, and can be restarted if failed. This job performs the following tasks:

- Dirty copy data from customer/0 into the two new shards. But rows are split based on their target shards.
- Stop replication on customer/0 rdonly tablet and perform a final sync.
- Start a filtered replication process from customer/0 into the two shards by sending changes to one or the other shard depending on which shard the rows belong to.

**详细步骤：**
代码位置：SplitCloneWorker.run()
### Phase 1: read what we need to do
SplitCloneWorker.init()

**初始化Source Shard、Destination Shard信息**
SplitClone 命令只是指定了Source Shard的信息，但是Vitess会自动去寻找所有的Shard并且根据KeyRange将所有Shard分成Range没有重合两份，两份分别标记为left、right，然后通过查询Shard是否在服务中(Serving/NotServing)来区分Source Shard和Destination Shard，一般而言，处于Serving状态的是Source Shard，而处于NotServing状态的是Destination Shard。

主要实现：_SplitCloneWorker.__initShardsForHorizontalResharding()_
从日志中看到，left和right划分后的结果如下：
```
/**
// OverlappingShards contains sets of shards that overlap which each-other.
// With this library, there is no guarantee of which set will be left or right.
type OverlappingShards struct {
   Left  []*topo.ShardInfo
   Right []*topo.ShardInfo
}


// ShardInfo is a meta struct that contains metadata to give the data
// more context and convenience. This is the main way we interact with a shard.
type ShardInfo struct {
   keyspace  string
   shardName string
   version   Version
   *topodatapb.Shard
}
*/

{
	Left:[
		master_alias:<cell:"zone1" uid:300 > master_term_start_time:<seconds:1585398160 nanoseconds:448016788 > key_range:<end:"\200" >
		master_alias:<cell:"zone1" uid:400 > master_term_start_time:<seconds:1585398160 nanoseconds:610385313 > key_range:<start:"\200" > 
	]


	Right:[
		master_alias:<cell:"zone1" uid:200 > master_term_start_time:<seconds:1585323731 nanoseconds:448148085 > is_master_serving:true 
	]
}
```
最终确定的Source应该是Right，Target应该是Left。
**
**sanityCheck**
_SplitCloneWorker.sanityCheckShardInfos()_
在正式clone之前，会做一些检查：

1. source shard 有MASTER、REPLICA、RDONLY三种状态的tablet
2. target shard 没有处于任何Serving状态的tablet

**
**healthcheck**
### Phase 2: Find destination master tablets
该步骤主要是找出target shard的master tablet，从日志中看到，这一步找到的master tablet如下：
```
I0328 20:43:24.178913   39992 split_clone.go:862] Using tablet zone1-0000000300 as destination master for customer/-80
I0328 20:43:24.178964   39992 split_clone.go:862] Using tablet zone1-0000000400 as destination master for customer/80-
```
### Phase 3: (optional) online clone
该流程实际上是存量数据拷贝的过程，直接从原shard select数据然后insert到新shard。

1. 一些检查和信息获取（_SplitCloneWorker.waitForTablets()_）
   1. 找到一个RDONLY状态的tablet作为source（默认为RDONLY，可以使用参数_tablet_type_设置为REPLICA）（_SplitCloneWorker.findFirstSourceTablet()）_
   2. _初始化限流模块（SplitCloneWorker.createThrottlers()）_
   3. 获取原tablet下需要copy的table信息（_SplitCloneWorker.getSourceSchema()）_
2. 拷贝数据（_SplitCloneWorker_.clone()）
   1. 为每个destination tablet创建一个insertChannel
   2. 为每个insertChannel创建_destinationWriterCount（受参数destination_writer_count_控制，默认20）个goroutine，每个goroutine的工作是读取insertChannel中的SQL语句，并写到target tablet（_SplitCloneWorker_._startExecutor() → executor.fetchLoop() → Client.ExecuteFetchAsApp() _），同时对每个goroutine启动限流模块。
   3. 开启goroutine从workPipeline中取chunck信息，然后去原表取数据，并按照新的shard方式生成SQL语句分发到不同的insertChannel中。goroutine数目由参数_source_reader_count_控制，默认10（_SplitCloneWorker_._startCloningData()_）
   4. 根据原表的数据量，把原表的数据根据主键划分成多个chunck，放到workPipeline中


克隆数据过程中Source Tablet的数据库可能会有更新，所以克隆到Destination Tablet的数据可能和Source Tablet不一致。

clone的关键代码：
```go
// copy phase:
// - copy the data from source tablets to destination masters (with replication on)
// Assumes that the schema has already been created on each destination tablet
// (probably from vtctl's CopySchemaShard)
func (scw *SplitCloneWorker) clone(ctx context.Context, state StatusWorkerState) error {
   // ... ...
   //
   // 对应destination的goroutine
   // In parallel, setup the channels to send SQL data chunks to for each destination tablet:
   insertChannels := make([]chan string, len(scw.destinationShards))
   destinationWaitGroup := sync.WaitGroup{}
   for shardIndex, si := range scw.destinationShards {
      // We create one channel per destination tablet. It is sized to have a
      // buffer of a maximum of destinationWriterCount * 2 items, to hopefully
      // always have data. We then have destinationWriterCount go routines reading
      // from it.
      insertChannels[shardIndex] = make(chan string, scw.destinationWriterCount*2)
 
      for j := 0; j < scw.destinationWriterCount; j++ {
         destinationWaitGroup.Add(1)
         go scw.startExecutor(ctx, &destinationWaitGroup, si.Keyspace(), si.ShardName(), insertChannels[shardIndex], j, processError)
      }
   }
 
   // Now for each table, read data chunks and send them to all
   // insertChannels
   readers := sync.WaitGroup{}
 
   err = scw.startCloningData(ctx, state, sourceSchemaDefinition, processError, firstSourceTablet, tableStatusList, start, statsCounters, insertChannels, &readers)
   // ... ...
}
```
startCloningData 的关键代码：
```go
func (scw *SplitCloneWorker) startCloningData(...) {
    workPipeline := make(chan workUnit, 10) // We'll use a small buffer so producers do not run too far ahead of consumers
 
    // Let's start the work consumers
    for i := 0; i < scw.sourceReaderCount; i++ {
        wg.Add(1)
        // 该goroutine不停从workPipeline中取chunck信息，并调用cloneAChunk处理
        go func() {
            defer wg.Done()
            for work := range workPipeline {
                scw.cloneAChunk(ctx, work.td, work.threadID, work.chunk, processError, state, tableStatusList, work.resolver, start, insertChannels, txID,                      statsCounters)
            }
        }()
    }
 
 
    // And now let's start producing work units
    for tableIndex, td := range sourceSchemaDefinition.TableDefinitions {
        td = reorderColumnsPrimaryKeyFirst(td)
 
        keyResolver, err := scw.createKeyResolver(td)
        if err != nil {
            return vterrors.Wrapf(err, "cannot resolve sharding keys for keyspace %v", scw.destinationKeyspace)
        }
 
        // 该函数使用 SELECT MIN(pek), MAX(pek) FROM schema.table 查询出原表的最大最小值，并根据原表总数据行数，进行chunck的划分
        //
        // TODO(mberlin): We're going to chunk *all* source shards based on the MIN
        // and MAX values of the *first* source shard. Is this going to be a problem?
        chunks, err := generateChunks(ctx, scw.wr, firstSourceTablet, td, scw.chunkCount, scw.minRowsPerChunk)
        if err != nil {
                return vterrors.Wrap(err, "failed to split table into chunks")
        }
        tableStatusList.setThreadCount(tableIndex, len(chunks))
 
        for _, c := range chunks {
            workPipeline <- workUnit{td: td, chunk: c, threadID: tableIndex, resolver: keyResolver}
        }
    }
}
```
chunk的定义，可以看到有主键的起始和终止值和数据行数：
```go
// chunk holds the information which subset of the table should be worked on.
// The subset is the range of rows in the range [start, end) where start and end
// both refer to the first column of the primary key.
// If the column is not numeric, both start and end will be sqltypes.NULL.
type chunk struct {
   start sqltypes.Value
   end   sqltypes.Value
   // number records the position of this chunk among all "total" chunks.
   // The lowest value is 1.
   number int
   // total is the total number of chunks this chunk belongs to.
   total int
}
```
### Phase 4: offline clone

1. Make sure the sources are producing a stable view of the data。对于每个source shard，选中一个RDONLY tablet将其状态改为DRAINED，并**停止主从复制**。这时候，该DRAINED tablet实际上就有了一份当前时间的完整快照（_SplitCloneWorker.__findOfflineSourceTablets()_）

wrangler.RecordStartSlaveAction(scw.cleaner, scw.sourceTablets[i])

2. 重复上面的clone步骤。该步骤是为了让新shard的数据和原shard 被摘下来的tablet的数据保持完全一致，因为大部分数据已经在online clone的流程中copy过了，这一步实际上很快，只是把在online clone过程中改变的数据更新的新shard。(如果有delete如何处理？如果与sharding key更改了如何处理？)

![image.png](https://cdn.nlark.com/yuque/0/2020/png/385742/1603963464436-bd93531b-01ef-447a-aa76-f00decc14ac9.png#align=left&display=inline&height=386&originHeight=386&originWidth=600&size=71422&status=done&style=none&width=600)

3. setUpVReplication（增量数据拷贝）
   1. 记录第一步中选中的每个tablet的GTID位点，实际上该位点就是该tablet从master上摘下来时候的位点

   2. 对于每个destination teblet，开启复制goroutine(_SplitCloneWorker._setUpVReplication())，该流程实际上是向__vt.vreplication_表中插入了一下replication的信息，然后RPC调用vreplication流程


vt_0000000300的_vt.vreplication信息：
```sql
mysql> select * from vreplication\G
*************************** 1. row ***************************
                   id: 1
             workflow: SplitClone
               source: keyspace:"customer" shard:"0" key_range:<end:"\200" >
                  pos: MySQL56/9a6cbb10-74c3-11ea-a04f-b255221d7376:1-20
             stop_pos: NULL
              max_tps: 9223372036854775807
  max_replication_lag: 9223372036854775807
                 cell: NULL
         tablet_types: NULL
         time_updated: 1585819522
transaction_timestamp: 0
                state: Running
              message:
              db_name: vt_customer
1 row in set (0.00 sec)
```
**VReplication**
VReplication 使用BinlogPlayer模拟一个mysql replica，从原tablet上中拉取binlog，并在新shard上回放。[https://vitess.io/docs/reference/vreplication/](https://vitess.io/docs/reference/vreplication/)

- 主要代码位置：vt/vttablet/tabletmanager/vreplication/*
- 流程入口：Engine.Exec() → Controller.run()

> TIPS
VReplication会一直保持binlog play，直到cutover（在该流程之前应该需要把source drained tablet从新挂到master上的，没找到相关代码）

相关日志：
```
I0328 20:43:25.202685   39992 topo_utils.go:124] Changing tablet zone1-0000000202 to 'DRAINED'
I0328 20:43:25.212253   39992 healthcheck.go:470] HealthCheckUpdate(Type Change): zone1-0000000202, tablet: zone1-202 (localhost), target customer/0 (RDONLY) => customer/0 (DRAINED), reparent time: 0
I0328 20:43:25.215070   39992 topo_utils.go:133] Adding tag[worker]=http://localhost:0/ to tablet zone1-0000000202
I0328 20:43:25.227605   39992 split_clone.go:770] Using tablet zone1-0000000202 as source for customer/0


I0328 20:43:25.289748   39992 split_clone.go:1271] Making and populating vreplication table
I0328 20:43:25.289799   39992 split_clone.go:1271] Making and populating vreplication table
I0328 20:43:25.335984   39992 split_clone.go:1298] Created replication for tablet customer/-80: keyspace:"customer" shard:"0" key_range:<end:"\200" > , db: vt_customer, pos: MySQL56/7bea3315-7041-11ea-921f-627fab508c36:1-20, uid: 1
I0328 20:43:25.336059   39992 locks.go:218] Locking keyspace customer for action SourceShardAdd(1)
I0328 20:43:25.335984   39992 split_clone.go:1298] Created replication for tablet customer/80-: keyspace:"customer" shard:"0" key_range:<start:"\200" > , db: vt_customer, pos: MySQL56/7bea3315-7041-11ea-921f-627fab508c36:1-20, uid: 1
I0328 20:43:25.336150   39992 locks.go:218] Locking keyspace customer for action SourceShardAdd(1)
```
## 数据一致性校验
通过以下命令进行数据校验：
```bash
SplitDiff -min_healthy_rdonly_tablets = 1 customer / -80
```
获取源分片的rdonly节点。状态重置为drained，同时停止该节点的数据复制，从而保证数据没有复制延迟。做完一系列操作后，开始校验源分片与目标分片的数据一致性。需要为每个目标分片都运行数据校验任务。 
## Cut over
CutOver通过以下命令进行，分为rdonly、replica、master三个type：
```
vtctlclient -server localhost:15999 MigrateServedTypes customer/0 rdonly
vtctlclient -server localhost:15999 MigrateServedTypes customer/0 replica
 
 
vtctlclient -server localhost:15999 MigrateServedTypes customer/0 master
```
相关代码：_Wrangler.MigrateServedTypes()_

CutOver首先要做rdonly和replica的切换，最后才是master（即写入点）的切换，如果先进行了master的切换，读取的还是老数据的一份快照。这里migrate master时会做检查，如果还有其他type没migrate，会报错。
下面以master为例，说明步骤：

1. 停止原master上的写
2. 获取master 的binlog position
3. 等待VReplication到上步记录的position
4. Stop VReplication streams.
5. 修改target shard为serrving状态并更新路由信息（Server.MigrateServedType()）
6. 确认服务正常，停止所有的source shard



migrate rdonly和replica的日志：
```
I0406 21:18:36.683268    1691 locks.go:218] Locking keyspace customer for action MigrateServedTypes(RDONLY)
I0406 21:18:36.686850    1691 keyspace.go:404] Finding the overlapping shards in keyspace customer
I0406 21:18:36.692330    1691 keyspace.go:1369] RefreshTabletsByShard called on shard customer/-80
I0406 21:18:36.693734    1691 keyspace.go:1395] Calling RefreshState on tablet zone1-0000000302
I0406 21:18:36.701557    1691 keyspace.go:1369] RefreshTabletsByShard called on shard customer/80-
I0406 21:18:36.703550    1691 keyspace.go:1395] Calling RefreshState on tablet zone1-0000000402
I0406 21:18:36.712531    1691 keyspace.go:445] WaitForDrain: Sleeping for 5 seconds before shutting down query service on old tablets...
I0406 21:18:41.712678    1691 keyspace.go:447] WaitForDrain: Sleeping finished. Shutting down queryservice on old tablets now.
I0406 21:18:41.712703    1691 keyspace.go:1369] RefreshTabletsByShard called on shard customer/0
I0406 21:18:41.714742    1691 keyspace.go:1395] Calling RefreshState on tablet zone1-0000000202
I0406 21:18:41.726815    1691 locks.go:257] Unlocking keyspace customer for successful action MigrateServedTypes(RDONLY)
 
I0406 21:18:41.745266    1691 locks.go:218] Locking keyspace customer for action MigrateServedTypes(REPLICA)
I0406 21:18:41.747463    1691 keyspace.go:404] Finding the overlapping shards in keyspace customer
I0406 21:18:41.753021    1691 keyspace.go:1369] RefreshTabletsByShard called on shard customer/-80
I0406 21:18:41.754481    1691 keyspace.go:1395] Calling RefreshState on tablet zone1-0000000301
I0406 21:18:41.762415    1691 keyspace.go:1369] RefreshTabletsByShard called on shard customer/80-
I0406 21:18:41.763811    1691 keyspace.go:1395] Calling RefreshState on tablet zone1-0000000401
I0406 21:18:56.771658    1691 keyspace.go:447] WaitForDrain: Sleeping finished. Shutting down queryservice on old tablets now.
I0406 21:18:56.771681    1691 keyspace.go:1369] RefreshTabletsByShard called on shard customer/0
I0406 21:18:56.773597    1691 keyspace.go:1395] Calling RefreshState on tablet zone1-0000000201
I0406 21:18:56.780686    1691 locks.go:257] Unlocking keyspace customer for successful action MigrateServedTypes(REPLICA)
 
 
 
I0406 21:56:11.148143    1691 locks.go:218] Locking keyspace customer for action MigrateServedTypes(MASTER)
I0406 21:56:11.150448    1691 keyspace.go:404] Finding the overlapping shards in keyspace customer
I0406 21:56:11.152773    1691 keyspace.go:583] RefreshState master zone1-0000000200
I0406 21:56:11.159941    1691 keyspace.go:593] zone1-0000000200 responded
I0406 21:56:11.159971    1691 keyspace.go:583] RefreshState master zone1-0000000400
I0406 21:56:11.160017    1691 keyspace.go:583] RefreshState master zone1-0000000300
I0406 21:56:11.166275    1691 keyspace.go:593] zone1-0000000300 responded
I0406 21:56:11.166474    1691 keyspace.go:593] zone1-0000000400 responded
I0406 21:56:11.168260    1691 keyspace.go:583] RefreshState master zone1-0000000200
I0406 21:56:11.173774    1691 keyspace.go:593] zone1-0000000200 responded
I0406 21:56:11.173882    1691 keyspace.go:508] Gathering master position for zone1-0000000200
I0406 21:56:11.176512    1691 keyspace.go:521] Got master position for zone1-0000000200
I0406 21:56:11.176619    1691 keyspace.go:552] Waiting for zone1-0000000300 to catch up
I0406 21:56:11.176684    1691 keyspace.go:552] Waiting for zone1-0000000400 to catch up
I0406 21:56:11.179705    1691 keyspace.go:566] zone1-0000000300 caught up
I0406 21:56:11.179763    1691 keyspace.go:566] zone1-0000000400 caught up
I0406 21:56:11.180871    1691 keyspace.go:828] Gathering master position for zone1-0000000300
I0406 21:56:11.183301    1691 keyspace.go:828] Gathering master position for zone1-0000000400
I0406 21:56:11.190520    1691 keyspace.go:863] Created reverse replication for tablet customer/0: keyspace:"customer" shard:"-80" key_range:<> , db: vt_customer, pos: MySQL56/c5fa5bf6-74c3-11ea-80f6-b255221d7376:1-17, uid: 2
I0406 21:56:11.194604    1691 keyspace.go:863] Created reverse replication for tablet customer/0: keyspace:"customer" shard:"80-" key_range:<> , db: vt_customer, pos: MySQL56/d0b1e396-74c3-11ea-9175-b255221d7376:1-17, uid: 3
I0406 21:56:11.209291    1691 keyspace.go:583] RefreshState master zone1-0000000400
I0406 21:56:11.209375    1691 keyspace.go:583] RefreshState master zone1-0000000300
I0406 21:56:11.215525    1691 keyspace.go:593] zone1-0000000300 responded
I0406 21:56:11.215546    1691 keyspace.go:593] zone1-0000000400 responded
I0406 21:56:11.217222    1691 locks.go:257] Unlocking keyspace customer for successful action MigrateServedTypes(MASTER)
```
[https://vitess.io/docs/user-guides/horizontal-sharding/](https://vitess.io/docs/user-guides/horizontal-sharding/)

1. 如何管理路由：topology统一管理，如何保证每个vtgate一致？
2. 如何copy数据：全量 select -> insert ，增量 过滤复制

# Reference
vitess：[https://vitess.io/docs](https://vitess.io/zh/docs/concepts/shard/)
RadonDB: [https://github.com/radondb/radon](https://github.com/radondb/radon)
[https://chuansongme.com/n/1747905853923](https://chuansongme.com/n/1747905853923)
