常见的使用不当造成的性能下降：

1. 字段定义为 `varchar` ，查询时使用 `int` ，导致无法使用索引
2. 分页时直接使用 `select * from t1 order by idx_1 limit x, y` ，导致随着x的增大越来越慢。
   1. 原因：limit会先扫描x行，再向后取y行，相当于扫描了x+y行（不算回表）。
   2. 解决方案：
      1. 每次分页完成后记录上一次最大的 `idx_1` ， `select * from t1 where idx_1 >= xxx order by idx_1 limit y` 的条件，该方法在 `idx_1` 非唯一索引时可能有重复数据。
      2. `select * from table where id >= (select id from table 1imit 1000,1) limit 10` ，使用覆盖索引避免了前1000条的回表
      3. `select id from table limit 10000, 10; Select * from table where id in (123,345....);` 
      4. `select * from (select id from job limit 1000000,100) a left join job b on a.id = b.id;` 
      5. 谁分那么多页，打死
3. 在一个事务中先 `select status from t where id = x` ，判断完 `status` 的值后直接 `update ... where id = x` 。
   1. 原因：因为在RR隔离级别下，第一个select是快照读，但是第二个update时status的值可能已经被其他事务更新了。另外MySQL并不支持快照（Snapshot）隔离级别，Snapshot 隔离级别可以解决这个问题。
   2. 解决方法：1. 第一个SQL语句改成 `select ... for update` ，会给数据行加上行锁；2. 第二个SQL语句改成 `update ... where id = x and status = origin_status` ，即使用乐观锁的方式
4. 在一个事务中先 `select ... from t where status = x` ，做一些判断后后 `update ... where status = x` ，发现返回的affect row = 0，而且数据没被更新成功。原因同上
