# 什么是binlog
MySQL的binlog日志是由MySQL server层生成的日志，用来记录MysSQL内部增删改查等对mysql数据库有更新的内容的记录(对数据库的改动)，对数据库的查询select或show等不会被binlog日志记录。binlog以event形式记录，还包含语句所执行的消耗的时间，binlog是事务安全型的
# 如何开启和查看binlog
## 开启binlog
配置文件中增加如下配置项：`log-bin = mysql-bin`
其中`mysql-bin`是binlog文件的文件名，启动mysql后将会生成下面两种文件:

- 二进制日志索引文件（文件名后缀为.index）用于记录所有的二进制文件
- 二进制日志文件（文件名后缀为.00000*）记录数据库所有的DDL和DML(除了数据查询语句select)语句事件
## 查看binlog
查看binlog信息有两种方式：

- 在MySQL Client中执行命令: `show binlog events in 'mysql-bin.000001'`
![](https://cdn.nlark.com/yuque/0/2019/png/385742/1564035718133-825ebc41-96aa-4a7e-b945-26efbf133ea7.png#height=1047&id=s8rmZ&originHeight=1047&originWidth=1159&originalType=binary&ratio=1&status=done&style=none&width=1159)
- 使用mysql官方提供的`mysqlbinlog`工具
![](https://cdn.nlark.com/yuque/0/2019/png/385742/1564035718214-d8fd955d-a935-40d3-84d9-cd6b9ba2a828.png#height=536&id=H1MRK&originHeight=536&originWidth=1068&originalType=binary&ratio=1&status=done&style=none&width=1068)
## binlog的作用

1. recovery
2. replication
[https://dev.mysql.com/doc/refman/5.7/en/replication.html](https://dev.mysql.com/doc/refman/5.7/en/replication.html)
# MySQL binlog格式
## binlog格式配置
### `[binlog_format](https://dev.mysql.com/doc/refman/5.7/en/replication-options-binary-log.html#sysvar_binlog_format)`
默认值: `ROW`
MySQL binlog有ROW、Statement、MiXED三种格式,可通过my.cnf配置文件及`set global binlog_format='ROW/STATEMENT/MIXED'`进行修改，命令行`show variables like 'binlog_format'` 命令查看binglog格式。

- _Row level_: 仅保存记录被修改细节，不记录sql语句上下文相关信息。
优点：能非常清晰的记录下每行数据的修改细节，不需要记录上下文相关信息，因此不会发生某些特定情况下的procedure、function、及trigger的调用触发无法被正确复制的问题，任何情况都可以被复制，且能加快从库重放日志的效率，保证从库数据的一致性。
缺点:由于所有的执行的语句在日志中都将以每行记录的修改细节来记录，因此，可能会产生大量的日志内容，干扰内容也较多；比如一条update语句，如修改多条记录，则binlog中每一条修改都会有记录，这样造成binlog日志量会很大，特别是当执行alter table之类的语句的时候，由于表结构修改，每条记录都发生改变，那么该表每一条记录都会记录到日志中，实际等于重建了表。
- _Statement level_: 每一条会修改数据的sql都会记录在binlog中。
优点：只需要记录执行语句的细节和上下文环境，避免了记录每一行的变化，在一些修改记录较多的情况下相比ROW level能大大减少binlog日志量，节约IO，提高性能；还可以用于实时的还原；同时主从版本可以不一样，从服务器版本可以比主服务器版本高。
缺点：为了保证sql语句能在slave上正确执行，必须记录上下文信息，以保证所有语句能在slave得到和在master端执行时候相同的结果；另外，主从复制时，存在部分函数（如sleep）及存储过程在slave上会出现与master结果不一致的情况，而相比Row level记录每一行的变化细节，绝不会发生这种不一致的情况。
- _Mixedlevel level_: 以上两种level的混合使用经过前面的对比，可以发现ROW level和statement level各有优势，如能根据sql语句取舍可能会有更好地性能和效果；Mixed level便是以上两种leve的结合。不过，新版本的MySQL对row level模式也被做了优化，并不是所有的修改都会以row level来记录，像遇到表结构变更的时候就会以statement模式来记录，如果sql语句确实就是update或者delete等修改数据的语句，那么还是会记录所有行的变更；因此，现在一般使用row level即可。
### `[binlog_row_image](https://dev.mysql.com/doc/refman/5.7/en/replication-options-binary-log.html#sysvar_binlog_row_image)`
默认值: `full`

- _full_: 在`before image`和`after image`中记录所有的列的信息。
- _minimal_: 在`befor image`中只记录改变的列和PEK; 在`after image`中只记录SQL语句中的列和自增列。
- _noblob_: 和fulle相同，除了`BLOB`和`TEXT`列以外
> 上面三个参数中，`full`和`minimal`相对比较常见，后者相对于前者更节省空间，但是因为没有完整的列信息，在某些场景下会有问题。比如我们基于canal的naruto，必须配置该参数为full，因为在下游分表时需要某些列做hash实现分表，该列在BI和AI中都不能缺失。

不同SQL语句生成的biblog区别请参考: [https://dev.mysql.com/doc/internals/en/binlog-row-image.html](https://dev.mysql.com/doc/internals/en/binlog-row-image.html)
说明：如无特殊说明，下面所有的例子都以`binlog_format = ROW`,`binlog_row_image = full`为前提。
# binlog相关参数

- sync_binlog
- binlog_cache_size
- max_binlog_cache_size
- max_binlog_size
# 参考资料
[1] [https://dev.mysql.com/doc/refman/5.7/en/server-system-variables.html](https://dev.mysql.com/doc/refman/5.7/en/server-system-variables.html)
[2] [https://dev.mysql.com/doc/refman/5.7/en/replication-options-binary-log.html](https://dev.mysql.com/doc/refman/5.7/en/replication-options-binary-log.html)
[3] [https://dev.mysql.com/doc/refman/5.7/en/binary-log.html](https://dev.mysql.com/doc/refman/5.7/en/binary-log.html)
[4] [https://dev.mysql.com/doc/refman/5.7/en/mysqlbinlog.html](https://dev.mysql.com/doc/refman/5.7/en/mysqlbinlog.html)
[5] [https://dev.mysql.com/doc/internals/en/binary-log.html](https://dev.mysql.com/doc/internals/en/binary-log.html)
[6] [http://mysql.taobao.org/monthly/2014/12/05/](http://mysql.taobao.org/monthly/2014/12/05/)
[7] [http://www.broadview.com.cn/article/310](http://www.broadview.com.cn/article/310)
[8] [https://www.jianshu.com/p/c16686b35807](https://www.jianshu.com/p/c16686b35807)
[9] [http://www.php.cn/mysql-tutorials-361643.html](http://www.php.cn/mysql-tutorials-361643.html)
[10] [https://cloud.tencent.com/developer/article/1032755](https://cloud.tencent.com/developer/article/1032755)
