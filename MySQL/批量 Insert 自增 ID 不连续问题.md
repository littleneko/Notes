## 问题重现
```sql
insert into info (name, city) values ('name1', 'city1'),('name2', 'city2'),('name3', 'city3'),('name4', 'city4'),('name5', 'city5'); 

insert into info (name, city) select name, city from info2; 
insert into info (name, city) values ('namex', 'cityx'); 

select auto_increment from information_schema.tables where table_schema='testdb' and table_name='info';
```
## “INSERT-like” statements:

- Simple inserts:
INSERT and REPLACE statements
- Bulk inserts:
INSERT ... SELECT, REPLACE ... SELECT, and LOAD DATA statements
- Mixed-mode inserts:
INSERT INTO t1 (c1,c2) VALUES (1,'a'), (NULL,'b'), (5,'c'), (NULL,'d');
## InnoDB AUTO_INCREMENT锁定模式:

- innodb_autoinc_lock_mode = 0 (“traditional” lock mode)：
   - AUTO-INC table-level lock
   - hold it until the end of the statement
- innodb_autoinc_lock_mode = 1 (“consecutive” lock mode)：
   1. bulk inserts:
      - AUTO-INC table-level lock
      - hold it until the end of the statement
   2. Simple inserts:
      - a light-weight lock
      - only held for the duration of the allocation process
- innodb_autoinc_lock_mode = 2 (“interleaved” lock mode)
   - not use table-level AUTO-INC lock
   - multiple statements can execute at the same time.
## ID预分配
session1 : insert into pp(name) values('xx');
session2 : insert into pp(name) values('xx'),('xx'),('xx'),('xx')
session3 : insert into pp(name) select name from pp;
　　
![](https://cdn.nlark.com/yuque/0/2019/png/385742/1564035718629-4c73bd0a-9820-48ce-8d06-a82520e9a2a3.png#align=left&display=inline&height=400&originHeight=379&originWidth=733&status=done&width=733)

| 第N条 | 预分配 | 使用 |
| --- | :---: | ---: |
| 1 | 1 | 1 |
| 2 | 2, 3 | 2 |
| 3 | null | 3 |
| 4 | 4, 5, 6, 7 | 4 |
| 5 | null | 5 |

> 中间是否可被打断？比如3-4之间

# InnoDB AUTO_INCREMENT Counter Initialization
If you specify an AUTO_INCREMENT column for an InnoDB table, the table handle in the InnoDB data dictionary contains a special counter called the auto-increment counter that is used in assigning new values for the column. This counter is stored only _in main memory_, _not on disk_.
after restart:
`SELECT MAX(ai_col) FROM table_name FOR UPDATE;`
> information_schema.tables表在内存中，是虚拟的表


**Reference**

1. [https://dev.mysql.com/doc/refman/5.7/en/innodb-auto-increment-handling.html#innodb-auto-increment-initialization](https://dev.mysql.com/doc/refman/5.7/en/innodb-auto-increment-handling.html#innodb-auto-increment-initialization)
2. [https://blog.csdn.net/ashic/article/details/53810319](https://blog.csdn.net/ashic/article/details/53810319)
3. [https://www.cnblogs.com/zengkefu/p/5683258.html](https://www.cnblogs.com/zengkefu/p/5683258.html)

## Attachments:
![](https://cdn.nlark.com/yuque/0/2019/gif/385742/1564035719116-7d1d28d6-9b56-49d1-a74f-c90d954c2275.gif#align=left&display=inline&height=8&originHeight=8&originWidth=8&status=done&width=8)[image2019-5-3_1-52-0.png](https://cdn.nlark.com/yuque/0/2019/png/385742/1564035718629-4c73bd0a-9820-48ce-8d06-a82520e9a2a3.png)
