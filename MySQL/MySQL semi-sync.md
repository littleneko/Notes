# MySQL Asynchronous Replication

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20221114231007636.png" alt="image-20221114231007636" style="zoom: 33%;" />

# MySQL Semisynchronous Replication
MySQL的 semi-sync 如下图所示，Master 先写 binlog，Slave 收到 Master 的 binlog 并且写 relay log 之后给Master 回复 ACK，此时 Master 才 commit 事物。MySQL 的 semi-sync 实际上保证的是事物提交之前已经至少有一个 Slave 接收到该数据的 binlog 了。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20221114231151677.png" alt="image-20221114231151677" style="zoom: 33%;" />

## AFTER SYNC 和 AFTER COMMIT
上图中可以看到最后一个步骤是 commit，具体这个 COMMIT 是指什么？MySQL 的事物提交其实是 binlog 和 redolog 两阶段提交，这里的 commit 是指两阶段的哪一步？

实际上根据 _rpl_semi_sync_master_wait_point_ 参数设置的不同，有两种情况。

- `AFTER_SYNC` (the default): The master writes each transaction to its binary log and the slave, and syncs the binary log to disk. The master waits for slave acknowledgment of transaction receipt after the sync. Upon receiving acknowledgment, the master commits the transaction to the storage engine and returns a result to the client, which then can proceed.
- `AFTER_COMMIT`: The master writes each transaction to its binary log and the slave, syncs the binary log, and commits the transaction to the storage engine. The master waits for slave acknowledgment of transaction receipt after the commit. Upon receiving acknowledgment, the master returns a result to the client, which then can proceed.

**AFTER SYNC **示意图

![image-20221114231253829](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20221114231253829.png)

**AFTER COMMIT **示意图：

![image-20221114231420578](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20221114231420578.png)

所以这两中方式的区别在于 engine 提交的时机：

- `AFTER_SYNC` ：master 收到 binlog ack -> ==engine commit== -> 返回客户端成功
- `AFTER_COMMIT` ：==engine commit== -> master 收到 binlog ack -> 返回客户端成功

一句话总结：==_**after_commit 在主机事务提交后将日志传送到从机，after_sync 是先传再提交**_==


The replication characteristics of these settings differ as follows:

- With `AFTER_SYNC`, ==all clients see the committed transaction at the same time==: After it has been acknowledged by the slave and committed to the storage engine on the master. Thus, all clients see the same data on the master.

  In the event of master failure, all transactions committed on the master have been replicated to the slave (saved to its relay log). A crash of the master and failover to the slave is lossless because the slave is up to date.

- With `AFTER_COMMIT`, ==the client issuing the transaction gets a return status only after the server commits to the storage engine and receives slave acknowledgment==. _After the commit and before slave acknowledgment, other clients can see the committed transaction before the committing client._
If something goes wrong such that the slave does not process the transaction, then in the event of a master crash and failover to the slave, it is possible that such clients will see a loss of data relative to what they saw on the master.

==`AFTER_COMMIT` 下，因为 engine 先 commit 了，事务持有锁的时间更短，但是如果这时主库 crash，从切换为主，可能导致在从上读不到数据。==

=="Engine Commit" makes data permanent and release locks on the data. So other sessions can reach the data since then==, even if the session is still waiting for the acknowledgement. It will cause ==phantom read== if master crashes and slave takes work over.

![image.png](https://littleneko.oss-cn-beijing.aliyuncs.com/img/1586189316982-4ef4d477-fbec-4741-94dc-b5102ae40139-20221114233912363.png)

# Links

1. [https://dev.mysql.com/doc/refman/5.7/en/group-replication-primary-secondary-replication.html](https://dev.mysql.com/doc/refman/5.7/en/group-replication-primary-secondary-replication.html)
2. [https://dev.mysql.com/doc/refman/5.7/en/replication-semisync.html](https://dev.mysql.com/doc/refman/5.7/en/replication-semisync.html)
3. [http://my-replication-life.blogspot.com/2013/09/loss-less-semi-synchronous-replication.html](http://my-replication-life.blogspot.com/2013/09/loss-less-semi-synchronous-replication.html)
4. [http://my-replication-life.blogspot.com/2013/12/enforced-semi-synchronous-replication.html](http://my-replication-life.blogspot.com/2013/12/enforced-semi-synchronous-replication.html)
5. [http://my-replication-life.blogspot.com/2014/03/faster-semisync-replication.html](http://my-replication-life.blogspot.com/2014/03/faster-semisync-replication.html)

## 扩展阅读

- P8 级面试难题，after_sync vs after_commit，哪个性能更好？：[https://mp.weixin.qq.com/s/fvvEn6nSYzQs9NCa1eCOIQ](https://mp.weixin.qq.com/s/fvvEn6nSYzQs9NCa1eCOIQ)
