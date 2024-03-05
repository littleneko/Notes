```
grant all privileges  on *.* to root@'%' identified by "root"

mysqld --defaults-file=/etc/my2.cnf --user=mysql --basedir=/usr/local/mysql  --initialize

ALTER USER 'root'@'localhost' IDENTIFIED BY 'MyNewPass';


mysqld_safe --defaults-file=/etc/my2.cnf &


CREATE USER 'repl'@'%' IDENTIFIED BY '123456';
GRANT REPLICATION SLAVE ON *.* TO 'repl'@'%';


sysbench oltp_read_write --mysql-host=127.0.0.1 --mysql-port=3306  --tables=10 --table-size=1000000 --threads=10 --time=120 --report-interval=1 prepare
```
```sql
CREATE USER 'db_user'@'%' IDENTIFIED BY '123456';
CREATE USER 'db_user_o'@'%' IDENTIFIED BY '123456';
CREATE USER 'db_user_r'@'%' IDENTIFIED BY '123456';
CREATE USER 'mha_user'@'%' IDENTIFIED BY '123456';
CREATE USER 'operator'@'%' IDENTIFIED BY '123456';
CREATE USER 'rpl'@'%' IDENTIFIED BY '123456';
CREATE USER 'admin'@'%' IDENTIFIED BY '123456';
CREATE USER 'ddl_user'@'%' IDENTIFIED BY '123456';
CREATE USER 'dba'@'%' IDENTIFIED BY '123456';
CREATE USER 'root'@'127.0.0.1' IDENTIFIED BY '123456';

GRANT USAGE ON *.* TO 'db_user'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE ON `test`.* TO 'db_user'@'%';
GRANT SELECT ON `performance_schema`.`replication_group_members` TO 'db_user'@'%';
GRANT SELECT ON `performance_schema`.`global_status` TO 'db_user'@'%';

GRANT USAGE ON *.* TO 'db_user_o'@'%';
GRANT SELECT ON `test`.* TO 'db_user_o'@'%';
GRANT SELECT ON `performance_schema`.`global_status` TO 'db_user_o'@'%';
GRANT SELECT ON `performance_schema`.`replication_group_members` TO 'db_user_o'@'%';

GRANT USAGE ON *.* TO 'db_user_r'@'%';
GRANT SELECT ON `test`.* TO 'db_user_r'@'%';
GRANT SELECT ON `performance_schema`.`global_status` TO 'db_user_r'@'%';
GRANT SELECT ON `performance_schema`.`replication_group_members` TO 'db_user_r'@'%';

GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, PROCESS, SUPER ON *.* TO 'mha_user'@'%';

GRANT SELECT, INSERT, UPDATE, DELETE ON *.* TO 'operator'@'%';

GRANT SELECT, REPLICATION SLAVE, REPLICATION CLIENT ON *.* TO 'rpl'@'%';

GRANT ALL PRIVILEGES ON *.* TO 'admin'@'%';

GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, PROCESS, INDEX, ALTER, SUPER, LOCK TABLES, REPLICATION SLAVE, REPLICATION CLIENT, TRIGGER ON *.* TO 'ddl_user'@'%';

GRANT SELECT, INSERT, UPDATE, CREATE, RELOAD, SHUTDOWN, PROCESS, FILE, REFERENCES, INDEX, ALTER, SHOW DATABASES, SUPER, CREATE TEMPORARY TABLES, LOCK TABLES, EXECUTE, REPLICATION SLAVE, REPLICATION CLIENT, CREATE VIEW, SHOW VIEW, CREATE ROUTINE, ALTER ROUTINE, CREATE USER, EVENT, TRIGGER, CREATE TABLESPACE ON *.* TO 'dba'@'%';

GRANT ALL PRIVILEGES ON *.* TO 'root'@'127.0.0.1' WITH GRANT OPTION;
```
