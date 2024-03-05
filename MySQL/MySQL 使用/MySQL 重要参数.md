# 参数汇总
1. [binlog_cache_size](https://dev.mysql.com/doc/refman/5.7/en/replication-options-binary-log.html#sysvar_binlog_cache_size)
2. [sync_binlog](https://dev.mysql.com/doc/refman/5.7/en/replication-options-binary-log.html#sysvar_sync_binlog)
3. innodb_buffer_pool_size
4. innodb_file_per_table
5. innodb_flush_log_at_trx_commit
6. innodb_flush_method
7. innodb_max_dirty_pages_pct
8. innodb_read_io_threads
9. innodb_read_only
10. innodb_write_io_threads
11. innodb_support_xa

# [binlog_cache_size](https://dev.mysql.com/doc/refman/5.7/en/replication-options-binary-log.html#sysvar_binlog_cache_size)

| Property | Value |
| --- | --- |
| Command-Line Format | `--binlog-cache-size=#` |
| System Variable | [binlog_cache_size](https://dev.mysql.com/doc/refman/5.7/en/replication-options-binary-log.html#sysvar_binlog_cache_size) |
| Scope | Global |
| Dynamic | Yes |
| Type (64-bit platforms) | integer |
| Type (32-bit platforms) | integer |
| Default Value (64-bit platforms) | `32768` |
| Default Value (32-bit platforms) | `32768` |
| Minimum Value (64-bit platforms) | `4096` |
| Minimum Value (32-bit platforms) | `4096` |
| Maximum Value (64-bit platforms) | `18446744073709551615` |
| Maximum Value (32-bit platforms) | `4294967295` |



The size of the cache to hold changes to the binary log during a transaction. A binary log cache is allocated for each client if the server supports any transactional storage engines and if the server has the binary log enabled ([`--log-bin`](https://dev.mysql.com/doc/refman/5.7/en/replication-options-binary-log.html#option_mysqld_log-bin) option). If you often use large transactions, you can increase this cache size to get better performance. The [`Binlog_cache_use`](https://dev.mysql.com/doc/refman/5.7/en/server-status-variables.html#statvar_Binlog_cache_use) and [`Binlog_cache_disk_use`](https://dev.mysql.com/doc/refman/5.7/en/server-status-variables.html#statvar_Binlog_cache_disk_use) status variables can be useful for tuning the size of this variable. See [Section 5.4.4, “The Binary Log”](https://dev.mysql.com/doc/refman/5.7/en/binary-log.html).
`binlog_cache_size` sets the size for the transaction cache only; the size of the statement cache is governed by the [`binlog_stmt_cache_size`](https://dev.mysql.com/doc/refman/5.7/en/replication-options-binary-log.html#sysvar_binlog_stmt_cache_size) system variable.

# [sync_binlog](https://dev.mysql.com/doc/refman/5.7/en/replication-options-binary-log.html#sysvar_sync_binlog)

| Property | Value |
| --- | --- |
| Command-Line Format | `--sync-binlog=#` |
| System Variable | [sync_binlog](https://dev.mysql.com/doc/refman/5.7/en/replication-options-binary-log.html#sysvar_sync_binlog) |
| Scope | Global |
| Dynamic | Yes |
| Type | integer |
| Default Value (>= 5.7.7) | `1` |
| Default Value (<= 5.7.6) | `0` |
| Minimum Value | `0` |
| Maximum Value | `4294967295` |



Controls the number of binary log commit groups to collect before synchronizing the binary log to disk. When [sync_binlog=0](https://dev.mysql.com/doc/refman/5.7/en/replication-options-binary-log.html#sysvar_sync_binlog), the binary log is never synchronized to disk, and when [sync_binlog](https://dev.mysql.com/doc/refman/5.7/en/replication-options-binary-log.html#sysvar_sync_binlog) is set to a value greater than 0 this number of binary log commit groups is periodically synchronized to disk. When[sync_binlog=1](https://dev.mysql.com/doc/refman/5.7/en/replication-options-binary-log.html#sysvar_sync_binlog), all transactions are synchronized to the binary log before they are committed. Therefore, even in the event of an unexpected restart, any transactions that are missing from the binary log are only in prepared state. This causes the server's automatic recovery routine to roll back those transactions. This guarantees that no transaction is lost from the binary log, and is the safest option. However this can have a negative impact on performance because of an increased number of disk writes. Using a higher value improves performance, but with the increased risk of data loss.
When [`sync_binlog=0`](https://dev.mysql.com/doc/refman/5.7/en/replication-options-binary-log.html#sysvar_sync_binlog) or [`sync_binlog`](https://dev.mysql.com/doc/refman/5.7/en/replication-options-binary-log.html#sysvar_sync_binlog) is greater than 1, transactions are committed without having been synchronized to disk. Therefore, in the event of a power failure or operating system crash, it is possible that the server has committed some transactions that have not been synchronized to the binary log. Therefore it is impossible for the recovery routine to recover these transactions and they will be lost from the binary log.

Prior to MySQL 5.7.7, the default value of [`sync_binlog`](https://dev.mysql.com/doc/refman/5.7/en/replication-options-binary-log.html#sysvar_sync_binlog) was 0, which configures no synchronizing to disk—in this case, the server relies on the operating system to flush the binary log's contents from time to time as for any other file. MySQL 5.7.7 and later use a default value of 1, which is the safest choice, but as noted above can impact performance.

# innodb_file_per_table

| Property | Value |
| --- | --- |
| Command-Line Format | `--innodb-file-per-table` |
| System Variable | [innodb_file_per_table](https://dev.mysql.com/doc/refman/5.7/en/innodb-parameters.html#sysvar_innodb_file_per_table) |
| Scope | Global |
| Dynamic | Yes |
| Type | boolean |
| Default Value | `ON` |



When `innodb_file_per_table` is enabled (the default), `InnoDB` stores the data and indexes for each newly created table in a separate [`.ibd` file](https://dev.mysql.com/doc/refman/5.7/en/glossary.html#glos_ibd_file) instead of the system tablespace. The storage for these tables is reclaimed when the tables are dropped or truncated. This setting enables `InnoDB`features such as table[compression](https://dev.mysql.com/doc/refman/5.7/en/glossary.html#glos_compression). See [Section 14.7.4, “InnoDB File-Per-Table Tablespaces”](https://dev.mysql.com/doc/refman/5.7/en/innodb-multiple-tablespaces.html) for more information.
Enabling [`innodb_file_per_table`](https://dev.mysql.com/doc/refman/5.7/en/innodb-parameters.html#sysvar_innodb_file_per_table) also means that an [`ALTER TABLE`](https://dev.mysql.com/doc/refman/5.7/en/alter-table.html) operation moves an `InnoDB` table from the system tablespace to an individual `.ibd` file in cases where [`ALTER TABLE`](https://dev.mysql.com/doc/refman/5.7/en/alter-table.html) rebuilds the table (`ALGORITHM=COPY`). An exception to this rule is for tables placed in the system tablespace using the`TABLESPACE=innodb_system` option with [`CREATE TABLE`](https://dev.mysql.com/doc/refman/5.7/en/create-table.html) or [`ALTER TABLE`](https://dev.mysql.com/doc/refman/5.7/en/alter-table.html). These tables are unaffected by the `innodb_file_per_table` setting and can only be moved to file-per-table tablespaces using [`ALTER TABLE ... TABLESPACE=innodb_file_per_table`](https://dev.mysql.com/doc/refman/5.7/en/alter-table.html).
When `innodb_file_per_table` is disabled, `InnoDB` stores the data for tables and indexes in the [ibdata files](https://dev.mysql.com/doc/refman/5.7/en/glossary.html#glos_ibdata_file) that make up the [system tablespace](https://dev.mysql.com/doc/refman/5.7/en/glossary.html#glos_system_tablespace). This setting reduces the performance overhead of file system operations for operations such as [`DROP TABLE`](https://dev.mysql.com/doc/refman/5.7/en/drop-table.html) or [`TRUNCATE TABLE`](https://dev.mysql.com/doc/refman/5.7/en/truncate-table.html). It is most appropriate for a server environment where entire storage devices are devoted to MySQL data. Because the system tablespace never shrinks, and is shared across all databases in an [instance](https://dev.mysql.com/doc/refman/5.7/en/glossary.html#glos_instance), avoid loading huge amounts of temporary data on a space-constrained system when `innodb_file_per_table` is disabled. Set up a separate instance in such cases, so that you can drop the entire instance to reclaim the space.
`innodb_file_per_table` is enabled by default. Consider disabling it if backward compatibility with MySQL 5.5 or 5.1 is a concern. This will prevent [`ALTER TABLE`](https://dev.mysql.com/doc/refman/5.7/en/alter-table.html) from moving [`InnoDB`](https://dev.mysql.com/doc/refman/5.7/en/innodb-storage-engine.html) tables from the system tablespace to individual `.ibd` files.
[`innodb_file_per_table`](https://dev.mysql.com/doc/refman/5.7/en/innodb-parameters.html#sysvar_innodb_file_per_table) is dynamic and can be set `ON` or `OFF` using `SET GLOBAL`. You can also set this option in the MySQL [configuration file](https://dev.mysql.com/doc/refman/5.7/en/glossary.html#glos_configuration_file) (`my.cnf` or `my.ini`) but this requires shutting down and restarting the server.
Dynamically changing the value requires the `SUPER` privilege and immediately affects the operation of all connections.

# innodb_buffer_pool_size

| Property | Value |
| --- | --- |
| Command-Line Format | `--innodb-buffer-pool-size=#` |
| System Variable | [innodb_buffer_pool_size](https://dev.mysql.com/doc/refman/5.7/en/innodb-parameters.html#sysvar_innodb_buffer_pool_size)`` |
| Scope | Global |
| Dynamic (>= 5.7.5) | Yes |
| Dynamic (<= 5.7.4) | No |
| Type (64-bit platforms) | integer |
| Type (32-bit platforms) | integer |
| Default Value (64-bit platforms) | `134217728` |
| Default Value (32-bit platforms) | `134217728` |
| Minimum Value (64-bit platforms) | `5242880` |
| Minimum Value (32-bit platforms) | `5242880` |
| Maximum Value (64-bit platforms) | `2**64-1` |
| Maximum Value (32-bit platforms) | `2**32-1` |



The size in bytes of the [buffer pool](https://dev.mysql.com/doc/refman/5.7/en/glossary.html#glos_buffer_pool), the memory area where `InnoDB` caches table and index data. The default value is 134217728 bytes (128MB). The maximum value depends on the CPU architecture; the maximum is 4294967295 (2-1) on 32-bit systems and 18446744073709551615 (2-1) on 64-bit systems. On 32-bit systems, the CPU architecture and operating system may impose a lower practical maximum size than the stated maximum. When the size of the buffer pool is greater than 1GB, setting[`innodb_buffer_pool_instances`](https://dev.mysql.com/doc/refman/5.7/en/innodb-parameters.html#sysvar_innodb_buffer_pool_instances) to a value greater than 1 can improve the scalability on a busy server.
A larger buffer pool requires less disk I/O to access the same table data more than once. On a dedicated database server, you might set the buffer pool size to 80% of the machine's physical memory size. Be aware of the following potential issues when configuring buffer pool size, and be prepared to scale back the size of the buffer pool if necessary.

- Competition for physical memory can cause paging in the operating system.
- `InnoDB` reserves additional memory for buffers and control structures, so that the total allocated space is approximately 10% greater than the specified buffer pool size.
- Address space for the buffer pool must be contiguous, which can be an issue on Windows systems with DLLs that load at specific addresses.
- The time to initialize the buffer pool is roughly proportional to its size. On instances with large buffer pools, initialization time might be significant. To reduce the initialization period, you can save the buffer pool state at server shutdown and restore it at server startup. See [Section 14.6.3.8, “Saving and Restoring the Buffer Pool State”](https://dev.mysql.com/doc/refman/5.7/en/innodb-preload-buffer-pool.html).

When you increase or decrease buffer pool size, the operation is performed in chunks. Chunk size is defined by the [`innodb_buffer_pool_chunk_size`](https://dev.mysql.com/doc/refman/5.7/en/innodb-parameters.html#sysvar_innodb_buffer_pool_chunk_size) configuration option, which has a default of 128 MB.
Buffer pool size must always be equal to or a multiple of [`innodb_buffer_pool_chunk_size`](https://dev.mysql.com/doc/refman/5.7/en/innodb-parameters.html#sysvar_innodb_buffer_pool_chunk_size) *[`innodb_buffer_pool_instances`](https://dev.mysql.com/doc/refman/5.7/en/innodb-parameters.html#sysvar_innodb_buffer_pool_instances). If you alter the buffer pool size to a value that is not equal to or a multiple of [`innodb_buffer_pool_chunk_size`](https://dev.mysql.com/doc/refman/5.7/en/innodb-parameters.html#sysvar_innodb_buffer_pool_chunk_size) * [`innodb_buffer_pool_instances`](https://dev.mysql.com/doc/refman/5.7/en/innodb-parameters.html#sysvar_innodb_buffer_pool_instances), buffer pool size is automatically adjusted to a value that is equal to or a multiple of [`innodb_buffer_pool_chunk_size`](https://dev.mysql.com/doc/refman/5.7/en/innodb-parameters.html#sysvar_innodb_buffer_pool_chunk_size) *[`innodb_buffer_pool_instances`](https://dev.mysql.com/doc/refman/5.7/en/innodb-parameters.html#sysvar_innodb_buffer_pool_instances) that is not less than the specified buffer pool size.
`innodb_buffer_pool_size` can be set dynamically, which allows you to resize the buffer pool without restarting the server. The [`Innodb_buffer_pool_resize_status`](https://dev.mysql.com/doc/refman/5.7/en/server-status-variables.html#statvar_Innodb_buffer_pool_resize_status) status variable reports the status of online buffer pool resizing operations. See [Section 14.6.3.2, “Configuring InnoDB Buffer Pool Size”](https://dev.mysql.com/doc/refman/5.7/en/innodb-buffer-pool-resize.html) for more information.

# innodb_file_per_table

| Property | Value |
| --- | --- |
| Command-Line Format | `--innodb-file-per-table` |
| System Variable | [innodb_file_per_table](https://dev.mysql.com/doc/refman/5.7/en/innodb-parameters.html#sysvar_innodb_file_per_table)`` |
| Scope | Global |
| Dynamic | Yes |
| Type | boolean |
| Default Value | `ON` |



When `innodb_file_per_table` is enabled (the default), `InnoDB` stores the data and indexes for each newly created table in a separate [`.ibd` file](https://dev.mysql.com/doc/refman/5.7/en/glossary.html#glos_ibd_file) instead of the system tablespace. The storage for these tables is reclaimed when the tables are dropped or truncated. This setting enables `InnoDB`features such as table[compression](https://dev.mysql.com/doc/refman/5.7/en/glossary.html#glos_compression). See [Section 14.7.4, “InnoDB File-Per-Table Tablespaces”](https://dev.mysql.com/doc/refman/5.7/en/innodb-multiple-tablespaces.html) for more information.
Enabling [`innodb_file_per_table`](https://dev.mysql.com/doc/refman/5.7/en/innodb-parameters.html#sysvar_innodb_file_per_table) also means that an [`ALTER TABLE`](https://dev.mysql.com/doc/refman/5.7/en/alter-table.html) operation moves an `InnoDB` table from the system tablespace to an individual `.ibd` file in cases where [`ALTER TABLE`](https://dev.mysql.com/doc/refman/5.7/en/alter-table.html) rebuilds the table (`ALGORITHM=COPY`). An exception to this rule is for tables placed in the system tablespace using the`TABLESPACE=innodb_system` option with [`CREATE TABLE`](https://dev.mysql.com/doc/refman/5.7/en/create-table.html) or [`ALTER TABLE`](https://dev.mysql.com/doc/refman/5.7/en/alter-table.html). These tables are unaffected by the `innodb_file_per_table` setting and can only be moved to file-per-table tablespaces using [`ALTER TABLE ... TABLESPACE=innodb_file_per_table`](https://dev.mysql.com/doc/refman/5.7/en/alter-table.html).
When `innodb_file_per_table` is disabled, `InnoDB` stores the data for tables and indexes in the [ibdata files](https://dev.mysql.com/doc/refman/5.7/en/glossary.html#glos_ibdata_file) that make up the [system tablespace](https://dev.mysql.com/doc/refman/5.7/en/glossary.html#glos_system_tablespace). This setting reduces the performance overhead of file system operations for operations such as [`DROP TABLE`](https://dev.mysql.com/doc/refman/5.7/en/drop-table.html) or [`TRUNCATE TABLE`](https://dev.mysql.com/doc/refman/5.7/en/truncate-table.html). It is most appropriate for a server environment where entire storage devices are devoted to MySQL data. Because the system tablespace never shrinks, and is shared across all databases in an [instance](https://dev.mysql.com/doc/refman/5.7/en/glossary.html#glos_instance), avoid loading huge amounts of temporary data on a space-constrained system when `innodb_file_per_table` is disabled. Set up a separate instance in such cases, so that you can drop the entire instance to reclaim the space.
`innodb_file_per_table` is enabled by default. Consider disabling it if backward compatibility with MySQL 5.5 or 5.1 is a concern. This will prevent [`ALTER TABLE`](https://dev.mysql.com/doc/refman/5.7/en/alter-table.html) from moving [`InnoDB`](https://dev.mysql.com/doc/refman/5.7/en/innodb-storage-engine.html) tables from the system tablespace to individual `.ibd` files.
[`innodb_file_per_table`](https://dev.mysql.com/doc/refman/5.7/en/innodb-parameters.html#sysvar_innodb_file_per_table) is dynamic and can be set `ON` or `OFF` using `SET GLOBAL`. You can also set this option in the MySQL [configuration file](https://dev.mysql.com/doc/refman/5.7/en/glossary.html#glos_configuration_file) (`my.cnf` or `my.ini`) but this requires shutting down and restarting the server.
Dynamically changing the value requires the `SUPER` privilege and immediately affects the operation of all connections.

# innodb_flush_log_at_trx_commit

| Property | Value |
| --- | --- |
| Command-Line Format | `--innodb-flush-log-at-trx-commit[=#]` |
| System Variable | [innodb_flush_log_at_trx_commit](https://dev.mysql.com/doc/refman/5.7/en/innodb-parameters.html#sysvar_innodb_flush_log_at_trx_commit)`` |
| Scope | Global |
| Dynamic | Yes |
| Type | enumeration |
| Default Value | `1` |
| Valid Values | `0`
`1`
`2` |


Controls the balance between strict [ACID](https://dev.mysql.com/doc/refman/5.7/en/glossary.html#glos_acid) compliance for [commit](https://dev.mysql.com/doc/refman/5.7/en/glossary.html#glos_commit) operations and higher performance that is possible when commit-related I/O operations are rearranged and done in batches. You can achieve better performance by changing the default value but then you can lose up to a second of transactions in a crash.

- The default value of 1 is required for full ACID compliance. With this value, the contents of the InnoDB [log buffer](https://dev.mysql.com/doc/refman/5.7/en/glossary.html#glos_log_buffer) are written out to the [log file](https://dev.mysql.com/doc/refman/5.7/en/glossary.html#glos_log_file) at each transaction commit and the log file is [flushed](https://dev.mysql.com/doc/refman/5.7/en/glossary.html#glos_flush) to disk.
- With a value of 0, the contents of the `InnoDB` log buffer are written to the log file approximately once per second and the log file is flushed to disk. No writes from the log buffer to the log file are performed at transaction commit. Once-per-second flushing is not guaranteed to happen every second due to process scheduling issues. Because the flush to disk operation only occurs approximately once per second, you can lose up to a second of transactions with any [**mysqld**](https://dev.mysql.com/doc/refman/5.7/en/mysqld.html) process crash.
- With a value of 2, the contents of the `InnoDB` log buffer are written to the log file after each transaction commit and the log file is flushed to disk approximately once per second. Once-per-second flushing is not 100% guaranteed to happen every second, due to process scheduling issues. Because the flush to disk operation only occurs approximately once per second, you can lose up to a second of transactions in an operating system crash or a power outage.
- `InnoDB` log flushing frequency is controlled by [`innodb_flush_log_at_timeout`](https://dev.mysql.com/doc/refman/5.7/en/innodb-parameters.html#sysvar_innodb_flush_log_at_timeout), which allows you to set log flushing frequency to _`N`_ seconds (where _`N`_ is `1 ... 2700`, with a default value of 1). However, any [**mysqld**](https://dev.mysql.com/doc/refman/5.7/en/mysqld.html) process crash can erase up to _`N`_ seconds of transactions.
- DDL changes and other internal `InnoDB` activities flush the `InnoDB` log independent of the`innodb_flush_log_at_trx_commit` setting.
- `InnoDB` [crash recovery](https://dev.mysql.com/doc/refman/5.7/en/glossary.html#glos_crash_recovery) works regardless of the `innodb_flush_log_at_trx_commit` setting. Transactions are either applied entirely or erased entirely.

For durability and consistency in a replication setup that uses `InnoDB` with transactions:

- If binary logging is enabled, set sync_binlog=1.
- Always set `innodb_flush_log_at_trx_commit=1`.

**
**Caution**
Many operating systems and some disk hardware fool the flush-to-disk operation. They may tell [**mysqld**](https://dev.mysql.com/doc/refman/5.7/en/mysqld.html) that the flush has taken place, even though it has not. In this case, the durability of transactions is not guaranteed even with the setting 1, and in the worst case, a power outage can corrupt `InnoDB` data. Using a battery-backed disk cache in the SCSI disk controller or in the disk itself speeds up file flushes, and makes the operation safer. You can also try to disable the caching of disk writes in hardware caches.

# innodb_flush_method

| Property | Value |
| --- | --- |
| Command-Line Format | `--innodb-flush-method=name` |
| System Variable | [innodb_flush_method](https://dev.mysql.com/doc/refman/5.7/en/innodb-parameters.html#sysvar_innodb_flush_method)`` |
| Scope | Global |
| Dynamic | No |
| Type (Windows) | string |
| Type (Unix) | string |
| Default Value (Windows) | `NULL` |
| Default Value (Unix) | `NULL` |
| Valid Values (Windows) | `async_unbuffered`
`normal`
`unbuffered` |
| Valid Values (Unix) | `fsync`
`O_DSYNC`
`littlesync`
`nosync`
`O_DIRECT`
`O_DIRECT_NO_FSYNC` |


Defines the method used to [flush](https://dev.mysql.com/doc/refman/5.7/en/glossary.html#glos_flush) data to `InnoDB` [data files](https://dev.mysql.com/doc/refman/5.7/en/glossary.html#glos_data_files) and [log files](https://dev.mysql.com/doc/refman/5.7/en/glossary.html#glos_log_file), which can affect I/O throughput.
If `innodb_flush_method` is set to `NULL` on a Unix-like system, the `fsync` option is used by default. If`innodb_flush_method` is set to `NULL` on Windows, the `async_unbuffered` option is used by default.
The `innodb_flush_method` options for Unix-like systems include:

- `fsync`: `InnoDB` uses the `fsync()` system call to flush both the data and log files. `fsync` is the default setting.
- `O_DSYNC`: InnoDB uses O_SYNC to open and flush the log files, and fsync() to flush the data files.`InnoDB` does not use `O_DSYNC` directly because there have been problems with it on many varieties of Unix.
- `littlesync`: This option is used for internal performance testing and is currently unsupported. Use at your own risk.
- `nosync`: This option is used for internal performance testing and is currently unsupported. Use at your own risk.
- `O_DIRECT`: InnoDB uses O_DIRECT (or directio() on Solaris) to open the data files, and uses fsync()to flush both the data and log files. This option is available on some GNU/Linux versions, FreeBSD, and Solaris.
- `O_DIRECT_NO_FSYNC`: `InnoDB` uses `O_DIRECT` during flushing I/O, but skips the `fsync()` system call afterward. This setting is suitable for some types of file systems but not others. For example, it is not suitable for XFS. If you are not sure whether the file system you use requires an `fsync()`, for example to preserve all file metadata, use `O_DIRECT` instead.

The `innodb_flush_method` options for Windows systems include:

- `async_unbuffered`: `InnoDB` uses Windows asynchronous I/O and non-buffered I/O. `async_unbuffered` is the default setting on Windows systems.
Running MySQL server on a 4K sector hard drive on Windows is not supported with `async_unbuffered`. The workaround is to use [`innodb_flush_method=normal`](https://dev.mysql.com/doc/refman/5.7/en/innodb-parameters.html#sysvar_innodb_flush_method).
- `normal`: `InnoDB` uses simulated asynchronous I/O and buffered I/O.
- `unbuffered`: `InnoDB` uses simulated asynchronous I/O and non-buffered I/O.

How each setting affects performance depends on hardware configuration and workload. Benchmark your particular configuration to decide which setting to use, or whether to keep the default setting. Examine the[`Innodb_data_fsyncs`](https://dev.mysql.com/doc/refman/5.7/en/server-status-variables.html#statvar_Innodb_data_fsyncs) status variable to see the overall number of `fsync()` calls for each setting. The mix of read and write operations in your workload can affect how a setting performs. For example, on a system with a hardware RAID controller and battery-backed write cache, `O_DIRECT` can help to avoid double buffering between the `InnoDB` buffer pool and the operating system file system cache. On some systems where `InnoDB` data and log files are located on a SAN, the default value or `O_DSYNC` might be faster for a read-heavy workload with mostly `SELECT` statements. Always test this parameter with hardware and workload that reflect your production environment. For general I/O tuning advice, see [Section 8.5.8, “Optimizing InnoDB Disk I/O”](https://dev.mysql.com/doc/refman/5.7/en/optimizing-innodb-diskio.html).

# innodb_max_dirty_pages_pct

| Property | Value |
| --- | --- |
| Command-Line Format | `--innodb-max-dirty-pages-pct=#` |
| System Variable | [innodb_max_dirty_pages_pct](https://dev.mysql.com/doc/refman/5.7/en/innodb-parameters.html#sysvar_innodb_max_dirty_pages_pct)`` |
| Scope | Global |
| Dynamic | Yes |
| Type | numeric |
| Default Value | `75` |
| Minimum Value | `0` |
| Maximum Value (>= 5.7.5) | `99.99` |
| Maximum Value (<= 5.7.4) | `99` |



`InnoDB` tries to [flush](https://dev.mysql.com/doc/refman/5.7/en/glossary.html#glos_flush) data from the [buffer pool](https://dev.mysql.com/doc/refman/5.7/en/glossary.html#glos_buffer_pool) so that the percentage of [dirty pages](https://dev.mysql.com/doc/refman/5.7/en/glossary.html#glos_dirty_page) does not exceed this value. The default value is 75.
The [`innodb_max_dirty_pages_pct`](https://dev.mysql.com/doc/refman/5.7/en/innodb-parameters.html#sysvar_innodb_max_dirty_pages_pct) setting establishes a target for flushing activity. It does not affect the rate of flushing. For information about managing the rate of flushing, see [Section 14.6.3.6, “Configuring InnoDB Buffer Pool Flushing”](https://dev.mysql.com/doc/refman/5.7/en/innodb-performance-adaptive_flushing.html).
For related information, see [Section 14.6.3.7, “Fine-tuning InnoDB Buffer Pool Flushing”](https://dev.mysql.com/doc/refman/5.7/en/innodb-lru-background-flushing.html). For general I/O tuning advice, see [Section 8.5.8, “Optimizing InnoDB Disk I/O”](https://dev.mysql.com/doc/refman/5.7/en/optimizing-innodb-diskio.html).

# innodb_read_io_threads

| Property | Value |
| --- | --- |
| Command-Line Format | `--innodb-read-io-threads=#` |
| System Variable | [innodb_read_io_threads](https://dev.mysql.com/doc/refman/5.7/en/innodb-parameters.html#sysvar_innodb_read_io_threads)`` |
| Scope | Global |
| Dynamic | No |
| Type | integer |
| Default Value | `4` |
| Minimum Value | `1` |
| Maximum Value | `64` |



The number of I/O threads for read operations in `InnoDB`. Its counterpart for write threads is [`innodb_write_io_threads`](https://dev.mysql.com/doc/refman/5.7/en/innodb-parameters.html#sysvar_innodb_write_io_threads). For more information, see [Section 14.6.7, “Configuring the Number of Background InnoDB I/O Threads”](https://dev.mysql.com/doc/refman/5.7/en/innodb-performance-multiple_io_threads.html). For general I/O tuning advice, see [Section 8.5.8, “Optimizing InnoDB Disk I/O”](https://dev.mysql.com/doc/refman/5.7/en/optimizing-innodb-diskio.html).
Note
On Linux systems, running multiple MySQL servers (typically more than 12) with default settings for `innodb_read_io_threads`, [`innodb_write_io_threads`](https://dev.mysql.com/doc/refman/5.7/en/innodb-parameters.html#sysvar_innodb_write_io_threads), and the Linux `aio-max-nr` setting can exceed system limits. Ideally, increase the `aio-max-nr`setting; as a workaround, you might reduce the settings for one or both of the MySQL configuration options.

# innodb_read_only

| Property | Value |
| --- | --- |
| Command-Line Format | `--innodb-read-only=#` |
| System Variable | [innodb_read_only](https://dev.mysql.com/doc/refman/5.7/en/innodb-parameters.html#sysvar_innodb_read_only)`` |
| Scope | Global |
| Dynamic | No |
| Type | boolean |
| Default Value | `OFF` |


Starts `InnoDB` in read-only mode. For distributing database applications or data sets on read-only media. Can also be used in data warehouses to share the same data directory between multiple instances. For more information, see [Section 14.6.2, “Configuring InnoDB for Read-Only Operation”](https://dev.mysql.com/doc/refman/5.7/en/innodb-read-only-instance.html).

# 参考链接
[https://dev.mysql.com/doc/refman/5.7/en/server-system-variables.html](https://dev.mysql.com/doc/refman/5.7/en/server-system-variables.html)
[https://dev.mysql.com/doc/refman/5.7/en/replication-options-binary-log.html](https://dev.mysql.com/doc/refman/5.7/en/replication-options-binary-log.html)
[https://dev.mysql.com/doc/refman/5.7/en/innodb-parameters.html](https://dev.mysql.com/doc/refman/5.7/en/innodb-parameters.html)
