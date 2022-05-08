# Overview

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1584239850162-c8a45a72-1bbe-4d4f-bbfc-a464e383e0d8.png" alt="img" style="zoom: 33%;" />

## 并行复制
MongoShake提供了并行复制的能力，复制的粒度选项（shard_key）可以为：id，collection或者auto，不同的文档或表可能进入不同的哈希队列并发执行。id表示按文档进行哈希；collection表示按表哈希；auto表示自动配置，如果有表存在唯一键，则退化为collection，否则则等价于id。

配置模板中的建议：”如果没有索引建议选择id达到非常高的同步性能，反之请选择collection。“ why?

## HA
MongoShake定期将同步上下文进行存储，存储对象可以为第三方API（注册中心）或者源库。目前的上下文内容为“已经成功同步的oplog时间戳”。在这种情况下，当服务切换或者重启后，通过对接该API或者数据库，新服务能够继续提供服务。
此外，MongoShake还提供了Hypervisor机制用于在服务挂掉的时候，将服务重新拉起。

## 过滤
提供黑名单和白名单机制选择性同步db和collection。

## checkpoint
![img](https://littleneko.oss-cn-beijing.aliyuncs.com/img/1584239966168-ced42de7-2fca-4d5a-959d-e61862f47b93.png)

如上图所示，LSN=16表示已经传输了16条oplog，如果没有重传的话，下次将传输LSN=17；LSN_ACK=13表示前13条都已经收到确认，如果需要重传，最早将从LSN=14开始；LSN_CKPT=8表示已经持久化checkpoint=8。持久化的意义在于，如果此时MongoShake挂掉重启后，源数据库的oplog将从LSN_CKPT位置开始读取而不是从头LSN=1开始读。因为oplog DML的幂等性，同一数据多次传输不会产生问题。但对于DDL，重传可能会导致错误。

## 排障和限速
MongoShake对外提供Restful API，提供实时查看进程内部各队列数据的同步情况，便于问题排查。另外，还提供限速功能，方便用户进行实时控制，减轻数据库压力。

## 架构和数据流

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1584240023263-be69a110-d246-4284-a514-1b7ea589fa5f.png" alt="img" style="zoom: 80%;" />

上图展示了MongoShake内部架构和数据流细节。总体来说，整个MongoShake可以大体分为3大部分：Syncer、Worker和Replayer，其中Replayer只用于tunnel类型为direct的情况。

Syncer负责从源数据库拉取数据，如果源是Mongod或者ReplicaSet，那么Syncer只有1个，如果是Sharding模式，那么需要有多个Syncer与Shard一一对应。在Syncer内部，首先fetcher用mgo.v2库从源库中抓取数据然后batch打包后放入PendingQueue队列，deserializer线程从PendingQueue中抓取数据进行解序列化处理。Batcher将从LogsQueue中抓取的数据进行重新组织，将前往同一个Worker的数据聚集在一起，然后hash发送到对应Worker队列。

Worker主要功能就是从WorkerQueue中抓取数据，然后进行发送，由于采用ack机制，所以会内部维持几个队列，分别为未发送队列和已发送队列，前者存储未发送的数据，后者存储发送但是没有收到ack确认的数据。发送后，未发送队列的数据会转移到已发送队列；收到了对端的ack回复，已发送队列中seq小于ack的数据将会被删除，从而保证了可靠性。

Worker可以对接不同的Tunnel通道，满足用户不同的需求。如果通道类型是direct，那么将会对接Replayer进行直接写入目的MongoDB操作，Worker与Replayer一一对应。首先，Replayer将收到的数据根据冲突检测规则分发到不同的ExecutorQueue，然后executor从队列中抓取进行并发写入。为了保证写入的高效性，MongoShake在写入前还会对相邻的相同Operation和相同Namespace的Oplog进行合并。

# FAQ
## 如果是分片sharding该如何配置？
对于源节点是分片的情况，源mongodb的地址`mongo_urls`需要配置各个分片shard的地址（需要local库的读权限），以分号（;）分隔。`tunnel.address`需要配置目的端的mongos地址。此外，还需要配置`context.storage.url`，这个是用于存储checkpoint的地址。在副本集的情况下，这一项不需要配置，因为默认的checkpoint都会写入源库，默认是`mongoshake.ckpt_default`。对于分片集群，由于不知道源mongos的地址，所以需要额外配置checkpoint地址，此处需要配置config-server的地址（目前需要写admin库的权限）。
另外，需要强调的是，目前sharding模式源端需要关闭balance，暂不支持move chunk的同时进行同步。

## 写完tcp/rpc/kafka后，读取出来发现数据乱码怎么办？
A: 这是因为写入的数据有控制信息在里面，需要用[receiver](https://github.com/alibaba/MongoShake/wiki/FAQ#q-how-to-connect-to-different-tunnel-except-direct)进行接收，剥离控制信息，然后再进行后续的对接。receiver同样需要编译，编译后位于bin目录。
剩下详细的信息请参考配置文件的具体说明。

## If MongoShake encounters an error oplog, will it skips this oplog and continue to write the post oplog?
A: No. This log will always be retried and thrown the error until success.

## Doest MongoShake support sync sharding?
A: Yes. But `balance` must be closed at the source database before syncing to prevent data to transfer between different shards.

## Does mongoshake support strict consistency of oplog?
A: No, when `shard_key` is `auto/collection`, mongoshake supports sequential consistency which means in the same namespace(`ns`), the sequence can be guaranteed. If `shard_key` is `id`, mongoshake supports eventual consistency.

## Where does MongoShake fetch oplog? Master or slave?
A: MongoShake fetches oplog from slave by default, so it's better to add all connection including master and slave into `mongo_urls`.

## Does MongoShake support resuming from breakpoint? For example, if MongoShake exists abnormally, will some data lost after restart?
A: Yes, MongoShake supports resuming from breakpoint bases on checkpoint mechanism, every time it starts, it reads the checkpoint which is a timestamp marks how many data have ready been replayed. After that, it pulls data from the source begin with this timestamp. So it won't lose data when restart.

## How can I configure checkpoint?
A: There have several variables in the configuration file(`collector.conf`) star with `context`:

- `context.storage`: the location type of checkpoint position. We offer two types: `database` and `api`. `database` means MongoShake will store the checkpoint into a database, while `api` means MongoShake will store and fetch the checkpoint from the given http interface which should be offered by users.
- `context.storage.url`: if the source MongoDB type is sharding, the checkpoint will be stored into this MongoDB address. For replicaSet, this variable is useless.
- `context.address`: the collection name of the checkpoint and the database name is `mongoshake` when `context.storage` is `database`.
- `context.start_position`: when starting for the first time, MongoShake fetches the checkpoint from the given address. If no checkpoint found, MongoShake will fetch oplog start with this value.

Let me give an example based on the default configuration to make more clear. Here comes the default configuration:
```
context.storage = database
context.address = ckpt_default
context.start_position = 2000-01-01T00:00:01Z
```

When starting for the first time, MongoShake checks the checkpoint in the `mongoshake.ckpt_default` collection which is definitely empty. So MongoShake starts syncing begin with the time: `2000-01-01T00:00:01Z`. After 3 minutes, MongoShake updates new checkpoint into `mongoshake.ckpt_default` collection, assume the time is `2018-09-01T00:00:01Z`. Once MongoShake restarts, it'll check the checkpoint again, this time MongoShake will start syncing data begin with the time `2018-09-01T00:00:01Z`.

## If I both have the checkpoint(stores in `mongoshake.ckpt_default` by default) and `context.start_position`, which one will be used?
A: `context.start_position` only works when the checkpoint isn't exists.

## How to connect to different tunnel except `direct`?
A: In `1.4.0` version, we offer receiver program(locates in `bin/receiver` after running the build script) to connect to different tunnels like rpc, tcp, file, mock and kafka. Before using it, users should modify the receiver configuration(locates in `conf/receiver.conf`) based on different needs. The dataflow is `mongoshake(collector)`=>`tunnel`=>`receiver`=>`user's platform`. Users can start receiver just like collector: `./receiver -conf=../conf/receiver.conf -verbose`. Here comes the brief introduction about receiver configuration

- replayer's number must equal to the worker number in the `collector.conf` in order to keep concurrency.
- rpc tunnel: the address is receiver socket address.
- tcp tunnel: the address is receiver socket address.
- file tunnel: the address is the filename of collector writing file.
- mock tunnel: the address is useless. MongoShake will generate random data including "i", "d", "u" and "n" operations like reading from MongoDB.
- kafka tunnel: the address format should be `topic@broker1,broker2,...`, the default topic is `mongoshake` and we only use one partition which is 0 by default. The default kafka reading strategy is reading the oldest offset which also means if the program crashes and then restarts later, the receiver will read from the beginning so that some data is read more than once which may not as expect. A better way to solve this problem is moving kafka offset forwarding once receive ack from the receiver, but we don't offer this code in current open source version.

All the above tunnel address in the receiver should equal to the collector. Users can add logical code in the `handler` function in `receiver/replayer.go` file to do something after receiving data. For a better explanation, I will analyze this function code:
```go
func (er *ExampleReplayer) handler() {
	for msg := range er.pendingQueue {
		count := uint64(len(msg.message.RawLogs))
		if count == 0 {
			// may be probe request
			continue
		}
		// parse batched message
		oplogs := make([]*oplog.PartialLog, len(msg.message.RawLogs), len(msg.message.RawLogs))
		for i, raw := range msg.message.RawLogs {
			oplogs[i] = &oplog.PartialLog{}
			bson.Unmarshal(raw, &oplogs[i])
			oplogs[i].RawSize = len(raw)
			LOG.Info(oplogs[i]) // just print for test
		}
		if callback := msg.completion; callback != nil {
			callback() // exec callback if exist
		}
		// get the newest timestamp
		n := len(oplogs)
		lastTs := utils.TimestampToInt64(oplogs[n - 1].Timestamp)
		er.Ack = lastTs
		// add logical code below
	}
}
```

`pendingQueue` is the receiver queue so that we fetch data from it and do the following steps. At first, we judge whether the length is equal to 0 which means a probe request if so. After that, we parse the batched oplogs into an array named `oplogs`, the reason we do this is several oplogs gather together before sending. As an example, we just print the message `LOG.Info(oplogs[i])` for the test. Then, we execute the callback function if exist, the callback function is set in the different `reader` tunnel. The next step is calculating the newest ack, so that collector can know receiver receive and replay this data successfully, then the new oplog will be sent. At last, users can add their logical code just like reading `oplogs` array and do whatever they want.

## How to improve QPS?
A: There are several ways to improve QPS like:

- Deploy MongoShake close to target MongoDB. It's because the `mgo` driver writing performance is not as well as reading, so reduce the writing IO delay is necessary.
- Increase the worker number. As we said in the detailed document, increase the work number can increase the concurrency.
- Increase the host performance like add more CPU, memory.
- Make collection distribute evenly. The performance won't be good if some collections are quite big while others are small.
- 

## MongoShake crashed because of OOM(Out Of Memory), how can I estimate memory usage?
A: The below picture is the partial inner modules of MongoShake which can be used to estimate the maximum memory usage.

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1584240208258-4e0a39f9-f9bb-4d9a-9510-e80b80b91a02.png" alt="img" style="zoom: 33%;" />

# Reference

1. [https://github.com/alibaba/MongoShake](https://github.com/alibaba/MongoShake)
1. [https://github.com/alibaba/MongoShake/wiki/FAQ](https://github.com/alibaba/MongoShake/wiki/FAQ)
1. [https://github.com/alibaba/MongoShake/wiki/MongoShake-Detailed-Documentation](https://github.com/alibaba/MongoShake/wiki/MongoShake-Detailed-Documentation)
1. [https://github.com/alibaba/MongoShake/wiki/MongoShake-Performance-Document](https://github.com/alibaba/MongoShake/wiki/MongoShake-Performance-Document)
1. [https://github.com/alibaba/MongoShake/wiki/%E7%AC%AC%E4%B8%80%E6%AC%A1%E4%BD%BF%E7%94%A8%EF%BC%8C%E5%A6%82%E4%BD%95%E8%BF%9B%E8%A1%8C%E9%85%8D%E7%BD%AE%EF%BC%9F](https://github.com/alibaba/MongoShake/wiki/%E7%AC%AC%E4%B8%80%E6%AC%A1%E4%BD%BF%E7%94%A8%EF%BC%8C%E5%A6%82%E4%BD%95%E8%BF%9B%E8%A1%8C%E9%85%8D%E7%BD%AE%EF%BC%9F)
1. [https://docs.mongodb.com/manual/](https://docs.mongodb.com/manual/)
1. [https://yq.aliyun.com/articles/603329](https://yq.aliyun.com/articles/603329)
