# 编译安装MySQL
这部分内容参考MySQL官方文档[
2.9.2 Installing MySQL Using a Standard Source Distribution](https://dev.mysql.com/doc/refman/5.7/en/installing-source-distribution.html)

1. 添加mysql用户和组用于运行mysqld: `groupadd mysql; useradd -r -g mysql -s /bin/false mysql`
2. 编译:
   - 新建目录用于编译：`mkdir bld`
   - 在bld目录下执行：`cmake .. -DWITH_BOOST=../boost_1_59_0 -DDEFAULT_CHARSET=utf8 -DDEFAULT_COLLATION=utf8_general_ci`
   - `make & make install`
3. 初始化MySQL:
   - `mysqld --initialize --user=mysql`
> 1. 该语句会在控制台打印出MySQL的临时密码，记住改密码用于登录到mysql.
> 2. 该语句的作用是初始化data目录，MySQL默认的data目录是/var/lib/mysql，可以通过配置文件中的 `datadir` 参数修改.

4. 开启MySQL:
使用mysqld_safe:`mysqld_safe --defaults-file=/etc/my2.cnf &`
# 配置双主Replication
这部分内容参考MySQL官方文档[Chapter 16 Replication](https://dev.mysql.com/doc/refman/5.7/en/replication.html)
## 环境
两台虚拟机其中一台部署两个MySQL实例.

- MySQL1(Master): 10.95.179.189:3306
- MySQL2(Master): 10.95.179.183:3306
- MySQL3(Slave): 10.95.179.183:3307

其中MySQL3与MySQL2同步
## 配置文件修改

- 修改MySQL1和MySQL2(master)的配置文件
```
[mysqld] 
server-id=1 
log-bin=mysql-bin 
log-slave-updates = true 
gtid_mode=ON 
enforce-gtid-consistency=true 
master-info-repository=TABLE 
relay-log-info-repository=TABLE 

replicate-ignore-db = mysql 
replicate-ignore-db = information_schema 
replicate-ignore-db = performance_schema 
replicate-ignore-db = sys
```
对参数的解释
server-id 用于标识一台Service，取值为1 - 2^32−1，必须唯一
log-bin, log-slave-updates, gtid_mode 三个参数在GTID模式下必须开启，log-slave-updates在链式replication下需要开启，开启后slave才会将从master同步过来的binlog写到本地binlog。option_mysqld_log-slave-updates
enforce-gtid-consistency=true 只有安全的statements会被记录到binlog中，比如CREATE TABLE ... SELECT这种语句就不会被记录。sysvar_enforce_gtid_consistency

- 修改MySQL3(slave)的配置文件

slave的配置文件与master类似，需要保证`server-id`唯一，并且不需要设置`log-slave-updates = true`

- 新建一个user用于replication
```sql
CREATE USER 'repl'@'%' IDENTIFIED BY '123456'; 
GRANT REPLICATION SLAVE ON *.* TO 'repl'@'%';
```
## 配置Master
MySQL2配置：
`CHANGE MASTER TO MASTER_HOST = '10.95.179.189', MASTER_PORT = 3306, MASTER_USER = 'repl', MASTER_PASSWORD = '123456', MASTER_AUTO_POSITION = 1;`
MySQl1配置：
`CHANGE MASTER TO MASTER_HOST = '10.95.179.183', MASTER_PORT = 3306, MASTER_USER = 'repl', MASTER_PASSWORD = '123456', MASTER_AUTO_POSITION = 1;`
MySQL3配置：
`CHANGE MASTER TO MASTER_HOST = '10.95.179.183', MASTER_PORT = 3306, MASTER_USER = 'repl', MASTER_PASSWORD = '123456', MASTER_AUTO_POSITION = 1;`
初始状态下的Master：
```
mysql> show master status\G 
*************************** 1. row *************************** 
File: mysql-bin.000001 
Position: 154 
Binlog_Do_DB: 
Binlog_Ignore_DB: 
Executed_Gtid_Set: 
1 row in set (0.00 sec)

初始状态下的slave：

mysql> show slave status\G 
*************************** 1. row *************************** 
Slave_IO_State: Waiting for master to send event 
Master_Host: 10.95.179.183 
Master_User: repl 
Master_Port: 3306 
Connect_Retry: 60 
Master_Log_File: mysql-bin.000001 
Read_Master_Log_Pos: 154 
Relay_Log_File: 55e7bf5e6a68-relay-bin.000002 
Relay_Log_Pos: 367 
Relay_Master_Log_File: mysql-bin.000001 
Slave_IO_Running: Yes 
Slave_SQL_Running: Yes 
Replicate_Do_DB: 
Replicate_Ignore_DB: mysql,information_schema,performance_schema,sys 
Replicate_Do_Table: 
Replicate_Ignore_Table: 
Replicate_Wild_Do_Table: 
Replicate_Wild_Ignore_Table: 
Last_Errno: 0 
Last_Error: 
Skip_Counter: 0 
Exec_Master_Log_Pos: 154 
Relay_Log_Space: 581 
Until_Condition: None 
Until_Log_File: 
Until_Log_Pos: 0 
Master_SSL_Allowed: No 
Master_SSL_CA_File: 
Master_SSL_CA_Path: 
Master_SSL_Cert: 
Master_SSL_Cipher: 
Master_SSL_Key: 
Seconds_Behind_Master: 0 
Master_SSL_Verify_Server_Cert: No 
Last_IO_Errno: 0 
Last_IO_Error: 
Last_SQL_Errno: 0 
Last_SQL_Error: 
Replicate_Ignore_Server_Ids: 
Master_Server_Id: 2 
Master_UUID: ea253687-37e1-11e8-8832-4254e7d550ed 
Master_Info_File: mysql.slave_master_info 
SQL_Delay: 0 
SQL_Remaining_Delay: NULL 
Slave_SQL_Running_State: Slave has read all relay log; waiting for more updates 
Master_Retry_Count: 86400 
Master_Bind: 
Last_IO_Error_Timestamp: 
Last_SQL_Error_Timestamp: 
Master_SSL_Crl: 
Master_SSL_Crlpath: 
Retrieved_Gtid_Set: 
Executed_Gtid_Set: 
Auto_Position: 1 
Replicate_Rewrite_DB: 
Channel_Name: 
Master_TLS_Version:
```
## 验证Replication
### MySQl1(Master)添加数据
MySQL1上建表并插入一条数据：
```sql
create database test_db; 
use test_db; 
create table test_table (id int, name varchar(255), city varchar(255)); 
insert into test_table values(1, 'litao', 'beijing');
```
完成后查看MySQl2(Master)的状态：
```
mysql> show slave status\G 
*************************** 1. row *************************** 
Slave_IO_State: Waiting for master to send event 
Master_Host: 10.95.179.189 
Master_User: repl 
Master_Port: 3306 
Connect_Retry: 60 
Master_Log_File: mysql-bin.000001 
Read_Master_Log_Pos: 826 
Relay_Log_File: 55e7bf5e6a68-relay-bin.000002 
Relay_Log_Pos: 1039 
Relay_Master_Log_File: mysql-bin.000001 
Slave_IO_Running: Yes 
Slave_SQL_Running: Yes 
Replicate_Do_DB: 
Replicate_Ignore_DB: mysql,information_schema,performance_schema,sys 
Replicate_Do_Table: 
Replicate_Ignore_Table: 
Replicate_Wild_Do_Table: 
Replicate_Wild_Ignore_Table: 
Last_Errno: 0 
Last_Error: 
Skip_Counter: 0 
Exec_Master_Log_Pos: 826 
Relay_Log_Space: 1253 
Until_Condition: None 
Until_Log_File: 
Until_Log_Pos: 0 
Master_SSL_Allowed: No 
Master_SSL_CA_File: 
Master_SSL_CA_Path: 
Master_SSL_Cert: 
Master_SSL_Cipher: 
Master_SSL_Key: 
Seconds_Behind_Master: 0 
Master_SSL_Verify_Server_Cert: No 
Last_IO_Errno: 0 
Last_IO_Error: 
Last_SQL_Errno: 0 
Last_SQL_Error: 
Replicate_Ignore_Server_Ids: 
Master_Server_Id: 1 
Master_UUID: 3b9b7e0b-37cf-11e8-bf93-128ca0759e53 
Master_Info_File: mysql.slave_master_info 
SQL_Delay: 0 
SQL_Remaining_Delay: NULL 
Slave_SQL_Running_State: Slave has read all relay log; waiting for more updates 
Master_Retry_Count: 86400 
Master_Bind: 
Last_IO_Error_Timestamp: 
Last_SQL_Error_Timestamp: 
Master_SSL_Crl: 
Master_SSL_Crlpath: 
Retrieved_Gtid_Set: 3b9b7e0b-37cf-11e8-bf93-128ca0759e53:1-3 
Executed_Gtid_Set: 3b9b7e0b-37cf-11e8-bf93-128ca0759e53:1-3 
Auto_Position: 1 
Replicate_Rewrite_DB: 
Channel_Name: 
Master_TLS_Version: 
1 row in set (0.00 sec)
```

可以看到，MySQL2已经取回并执行了`3b9b7e0b-37cf-11e8-bf93-128ca0759e53:1-3`
查看`test_table`表也已经正确插入了数据：
```
mysql> select * from test_db.test_table; 
+------+-------+---------+ 
| id | name | city | 
+------+-------+---------+ 
| 1 | litao | beijing | 
+------+-------+---------+ 
1 row in set (0.00 sec)
```
在MySQL3上使用同样的方法也可以看到数据已经正确复制。
> 从master status中可以看到同一个事务在不同机器上的gtid相同

### MySQL2(master)添加数据
MySQl2上插入一条数据：
```sql
insert into test_table values(2, 'litao2', 'beijing2');
```
完成后查看MySQL1(master)的状态：
```
mysql> show slave status\G 
*************************** 1. row *************************** 
Slave_IO_State: Waiting for master to send event 
Master_Host: 10.95.179.183 
Master_User: repl 
Master_Port: 3306 
Connect_Retry: 60 
Master_Log_File: mysql-bin.000001 
Read_Master_Log_Pos: 1105 
Relay_Log_File: af35f56b1c88-relay-bin.000002 
Relay_Log_Pos: 658 
Relay_Master_Log_File: mysql-bin.000001 
Slave_IO_Running: Yes 
Slave_SQL_Running: Yes 
Replicate_Do_DB: 
Replicate_Ignore_DB: mysql,information_schema,performance_schema,sys 
Replicate_Do_Table: 
Replicate_Ignore_Table: 
Replicate_Wild_Do_Table: 
Replicate_Wild_Ignore_Table: 
Last_Errno: 0 
Last_Error: 
Skip_Counter: 0 
Exec_Master_Log_Pos: 1105 
Relay_Log_Space: 872 
Until_Condition: None 
Until_Log_File: 
Until_Log_Pos: 0 
Master_SSL_Allowed: No 
Master_SSL_CA_File: 
Master_SSL_CA_Path: 
Master_SSL_Cert: 
Master_SSL_Cipher: 
Master_SSL_Key: 
Seconds_Behind_Master: 0 
Master_SSL_Verify_Server_Cert: No 
Last_IO_Errno: 0 
Last_IO_Error: 
Last_SQL_Errno: 0 
Last_SQL_Error: 
Replicate_Ignore_Server_Ids: 
Master_Server_Id: 2 
Master_UUID: ea253687-37e1-11e8-8832-4254e7d550ed 
Master_Info_File: mysql.slave_master_info 
SQL_Delay: 0 
SQL_Remaining_Delay: NULL 
Slave_SQL_Running_State: Slave has read all relay log; waiting for more updates 
Master_Retry_Count: 86400 
Master_Bind: 
Last_IO_Error_Timestamp: 
Last_SQL_Error_Timestamp: 
Master_SSL_Crl: 
Master_SSL_Crlpath: 
Retrieved_Gtid_Set: ea253687-37e1-11e8-8832-4254e7d550ed:1 
Executed_Gtid_Set: 3b9b7e0b-37cf-11e8-bf93-128ca0759e53:1-3, 
ea253687-37e1-11e8-8832-4254e7d550ed:1 
Auto_Position: 1 
Replicate_Rewrite_DB: 
Channel_Name: 
Master_TLS_Version: 
1 row in set (0.00 sec)
```
可以看到MySQL1取回了`ea253687-37e1-11e8-8832-4254e7d550ed:1`日志，并正确执行。
MySQL3同上。
## 主从切换
MySQL2换为从，MuySQL3换为主

1. 停止所有slave: `stop slave`
2. 更改MySQL3的master为MySQL1: `CHANGE MASTER TO MASTER_HOST = '10.95.179.189', MASTER_PORT = 3306, MASTER_USER = 'repl', MASTER_PASSWORD = '123456', MASTER_AUTO_POSITION = 1;`
更改MySQl2的master为MySQL3，更改MySQL1的master为MySQL3，语句类似，不再赘述
3. 在MySQL3上插入一条数据
4. 查看MySQL1和MySQL2的结果：
```
mysql> show slave status\G 
*************************** 1. row *************************** 
Slave_IO_State: Waiting for master to send event 
Master_Host: 10.95.179.183 
Master_User: repl 
Master_Port: 3306 
Connect_Retry: 60 
Master_Log_File: mysql-bin.000001 
Read_Master_Log_Pos: 1105 
Relay_Log_File: 55e7bf5e6a68-relay-bin.000002 
Relay_Log_Pos: 1318 
Relay_Master_Log_File: mysql-bin.000001 
Slave_IO_Running: Yes 
Slave_SQL_Running: Yes 
Replicate_Do_DB: 
Replicate_Ignore_DB: mysql,information_schema,performance_schema,sys 
Replicate_Do_Table: 
Replicate_Ignore_Table: 
Replicate_Wild_Do_Table: 
Replicate_Wild_Ignore_Table: 
Last_Errno: 0 
Last_Error: 
Skip_Counter: 0 
Exec_Master_Log_Pos: 1105 
Relay_Log_Space: 1532 
Until_Condition: None 
Until_Log_File: 
Until_Log_Pos: 0 
Master_SSL_Allowed: No 
Master_SSL_CA_File: 
Master_SSL_CA_Path: 
Master_SSL_Cert: 
Master_SSL_Cipher: 
Master_SSL_Key: 
Seconds_Behind_Master: 0 
Master_SSL_Verify_Server_Cert: No 
Last_IO_Errno: 0 
Last_IO_Error: 
Last_SQL_Errno: 0 
Last_SQL_Error: 
Replicate_Ignore_Server_Ids: 
Master_Server_Id: 2 
Master_UUID: ea253687-37e1-11e8-8832-4254e7d550ed 
Master_Info_File: mysql.slave_master_info 
SQL_Delay: 0 
SQL_Remaining_Delay: NULL 
Slave_SQL_Running_State: Slave has read all relay log; waiting for more updates 
Master_Retry_Count: 86400 
Master_Bind: 
Last_IO_Error_Timestamp: 
Last_SQL_Error_Timestamp: 
Master_SSL_Crl: 
Master_SSL_Crlpath: 
Retrieved_Gtid_Set: 3b9b7e0b-37cf-11e8-bf93-128ca0759e53:1-3, 
ea253687-37e1-11e8-8832-4254e7d550ed:1 
Executed_Gtid_Set: 3b9b7e0b-37cf-11e8-bf93-128ca0759e53:1-3, 
ea253687-37e1-11e8-8832-4254e7d550ed:1 
Auto_Position: 1 
Replicate_Rewrite_DB: 
Channel_Name: 
Master_TLS_Version: 
1 row in set (0.00 sec)
```

可以看到有一条新的日志`ea253687-37e1-11e8-8832-4254e7d550ed:1`这是MySQl3产生的。
## 跳过复制错误
配置过程中，因为误操作，slave中的binlog和gtid_executed丢失，再次开启slave后，重新开始回放日志，但是建库建表操作因为slave中已经有该库和表了，导致出错。解决方法就是手动跳过这些出错的日志。

1. 查看slave status,找到出错的Pos，然后使用mysqlbinlog工具查看binlog中对应的gtid。`sqlbinlog --base64-output=DECODE-ROWS --verbose mysql-bin.000001`
2. 跳过这些语句：
```
mysql> stop slave; 
mysql> set session gtid_next='3b9b7e0b-37cf-11e8-bf93-128ca0759e53:1' 
mysql> begin; 
mysql> commit; 
mysql> SET SESSION GTID_NEXT = AUTOMATIC; 
mysql> start slave;
```

