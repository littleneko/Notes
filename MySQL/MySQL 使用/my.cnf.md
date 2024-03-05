```
[mysql]
port=3306
socket=/mysql/datadir/mysql.sock

[mysqld]
basedir=/usr/local/mysql
datadir=/var/lib/mysql
plugin-dir=/mysql/mysql/lib/plugin
log-error=/var/log/mariadb/mariadb.log
pid-file=/var/run/mariadb/mariadb.pid
socket=/var/lib/mysql/mysql.sock

# Disabling symbolic-links is recommended to prevent assorted security risks
symbolic-links=0
# Settings user and group are ignored when systemd is used.
# If you need to run mysqld under a different user or group,
# customize your systemd unit file for mariadb according to the
# instructions in http://fedoraproject.org/wiki/Systemd
bind-address = 0.0.0.0
port = 3306
user = mysql

log-bin = mysql-bin
log-slave-updates = true
server-id=3
gtid_mode=ON
enforce-gtid-consistency=true
master-info-repository=TABLE
relay-log-info-repository=TABLE

replicate-ignore-db = mysql
replicate-ignore-db = information_schema
replicate-ignore-db = performance_schema
replicate-ignore-db = sys


innodb_file_per_table = ON
innodb_flush_log_at_trx_commit = 1
sync_binlog = 1
innodb_flush_method = O_DIRECT
#binlog_cache_size = 
innodb_buffer_pool_size = 67108864
#innodb_max_dirty_pages_pct = 
innodb_read_io_threads = 2
innodb_write_io_threads = 2



[mysqld_safe]
log-error=/var/log/mariadb/mariadb.log
pid-file=/var/run/mariadb/mariadb.pid

#
# include all files from the config directory
#
!includedir /etc/my.cnf.d
```
```
#MySQL 5.5.x
[client]
port            = 3306
socket          = /data/var/mysql.sock

[mysqld]
port            = 3306
socket          = /data/var/mysql.sock
user            = mysql

auto_increment_increment = 2
#auto_increment_offset =(master:1, slave:2)
auto_increment_offset = 1

skip-name-resolve
skip-slave-start
report_host = $reporthost$

max_allowed_packet = 64M
max_connect_errors = 1000000
max_connections = 12384
max_user_connections = 9000
#net_buffer_length = 8K
#read_rnd_buffer_size = 512K

#default-storage-engine=InnoDB
character-set-server = utf8
collation-server = utf8_bin
init-connect='SET NAMES utf8'

#--------cache---------
key_buffer_size = 2M
read_buffer_size = 2M
sort_buffer_size = 2M
binlog_cache_size = 32M
thread_cache_size = 300
table_open_cache = 16384
table_definition_cache = 16384
query_cache_limit = 0
query_cache_size = 0
query_cache_type = 0

#READ-UNCOMMITTED, READ-COMMITTED, REPEATABLE-READ, SERIALIZABLE
transaction_isolation = REPEATABLE-READ
tmp_table_size = 256M

#--------log---------
sync_binlog = 1000
back_log = 1000
log_queries_not_using_indexes = 0
min_examined_row_limit = 0
slow_query_log = 1
slow_query_log_file = slow.log
long_query_time = 0.1
log-error = err.log
log_slave_updates = 1
expire_logs_days = 30
binlog_format = row
log-bin = dd-bin
relay-log = dd-relay
show_compatibility_56 = on

#last intranet ip
server-id = $serverid$
datadir = /home/mysql/var
tmpdir = /dev/shm

#--------innodb--------------
#innodb_data_home_dir = /data/ibdata
innodb_open_files = 102400
innodb_old_blocks_time = 1000
innodb_flush_method = O_DIRECT
innodb_autoextend_increment = 256
innodb_data_file_path=ibdata1:10M;ibdata2:10M:autoextend
innodb_table_locks = 1
innodb_lock_wait_timeout = 5

#(50-80)% * total memory ( 5G )
innodb_buffer_pool_size = 10G
innodb_buffer_pool_instances = 8
#innodb_additional_mem_pool_size=128M

innodb_max_dirty_pages_pct = 70
innodb_max_dirty_pages_pct_lwm = 40
innodb_read_io_threads = 16
innodb_write_io_threads = 16


#A recommended value is 2 times the number of CPUs plus the number of disks.
#5.5.8 default 0
innodb_thread_concurrency = 64
#innodb_log_group_home_dir = /data/iblogs
innodb_log_files_in_group = 2
innodb_flush_log_at_trx_commit = 2
innodb_file_per_table = 1


innodb_log_file_size = 5G #25% *buffer pool size (1G)
innodb_log_buffer_size = 96M


#suppression of duplicate-key and no-key-found errors
#slave_exec_mode=IDEMPOTENT

#MySQL5.7 New Parameter
skip-ssl
innodb_support_xa = ON
explicit_defaults_for_timestamp = 0
performance_schema = ON

master_info_repository = TABLE
relay_log_info_repository = TABLE
relay_log_recovery = ON
gtid_mode = ON
binlog_group_commit_sync_delay = 0
binlog_group_commit_sync_no_delay_count = 0
enforce_gtid_consistency = 1
binlog_gtid_simple_recovery = 1
binlog_rows_query_log_events = 1

innodb_undo_logs = 128
innodb_undo_tablespaces = 3
innodb_undo_log_truncate = 1
innodb_max_undo_log_size = 2G
innodb_print_all_deadlocks = 1
innodb_online_alter_log_max_size = 1G
slave-parallel-type = LOGICAL_CLOCK
slave-parallel-workers = 0
log_slow_admin_statements = 1
log_slow_slave_statements = 1
transaction_write_set_extraction = MURMUR32
innodb_page_cleaners = 16
innodb_purge_threads = 4
innodb_large_prefix = 1
innodb_lru_scan_depth = 4096
innodb_io_capacity = 6000
innodb_io_capacity_max = 8000
innodb_buffer_pool_dump_pct = 40
log_timestamps = SYSTEM
innodb_temp_data_file_path = innodb_tem_tbs:100M:autoextend:max:10G
#rpl_semi_sync_master_timeout=1
#rpl_semi_sync_master_wait_no_slave=OFF
log_error_verbosity = 3
innodb_buffer_pool_load_at_startup = 0
innodb_buffer_pool_dump_at_shutdown = 0
sql_mode = ""
slave_net_timeout = 60
slave_preserve_commit_order = 1
slave_transaction_retries = 128
slave_pending_jobs_size_max = 96M

[mysqld$port$]
port                            = $port$
socket                          = $datadir$mysql.sock
pid-file                        = $datadir$mysql.pid
datadir                         = $datadir$var/
innodb_data_home_dir            = $datadir$var/
innodb_log_group_home_dir       = $datadir$var/
tmpdir                          = $datadir$var/
log-bin                         = $binlogdir$var/dd-bin
relay-log                       = $binlogdir$var/dd-relay
innodb_buffer_pool_size         = $bufferpool$
innodb_data_file_path           = $innodb_data_file_path$
server-id                       = $serverid$
mysqld                          = /data1/mysql/mysqld/$mysqlversion$/bin/mysqld_safe
basedir                         = /data1/mysql/mysqld/$mysqlversion$/


[mysql]
no-auto-rehash
default_character_set = utf8

[mysqldump]
quick
max_allowed_packet = 16M

[isamchk]
key_buffer = 20M
sort_buffer_size = 20M
read_buffer = 2M
write_buffer = 2M

[myisamchk]
key_buffer = 20M
sort_buffer_size = 20M
read_buffer = 2M
write_buffer = 2M

[mysqlhotcopy]
interactive-timeout

[mysqld_multi]
mysqld = mysqld_safe
log = /data1/mysql/mysqld_multi.log
```

