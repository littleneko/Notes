# Introduction
It supports both ==point lookups== and ==range scans==, and provides different types of ==ACID guarantees==.
# High Level Architecture
RocksDB organizes all data in sorted order and the common operations are `Get(key)`, `NewIterator()`, `Put(key, val)`, `Delete(key)`, and `SingleDelete(key)`.

The three basic constructs of RocksDB are **memtable**, **sstfile **and **logfile**. The [memtable](https://github.com/facebook/rocksdb/wiki/MemTable) is an in-memory data structure - new writes are inserted into the_memtable_and are optionally written to the [logfile(aka. Write Ahead Log(WAL))](https://github.com/facebook/rocksdb/wiki/Write-Ahead-Log). The logfile is a sequentially-written file on storage. When the memtable fills up, it is flushed to a [sstfile](https://github.com/facebook/rocksdb/wiki/Rocksdb-BlockBasedTable-Format) on storage and the corresponding logfile can be safely deleted. The data in an sstfile is sorted to facilitate easy lookup of keys.

![image.png](https://littleneko.oss-cn-beijing.aliyuncs.com/img/1621567944340-4f381da1-e27e-407e-a0c7-a0acf072c089.png)

# Features

- **Column Families **: RocksDB guarantees users a consistent view across column families, including after crash recovery when WAL is enabled or atomic flush is enabled. It also supports atomic cross-column family operations via the `WriteBatch` API.
- **Iterators** : An `Iterator` API allows an application to do a range scan on the database. ==A consistent-point-in-time view of the database is created when the Iterator is created.== Thus, all keys returned via the Iterator are from a consistent view of the database.
- **Snapshots** : A `Snapshot` API allows an application to ==create a point-in-time view of a database.== The `Get` and `Iterator` APIs can be used to read data from a specified snapshot.
- **Transactions** It supports both of optimistic and pessimistic mode.
- **Prefix Iterators** : Applications can configure a `Options.prefix_extractor` to enable a key-prefix based filtering. When `Options.prefix_extractor` is set, a hash of the prefix is also added to the Bloom. An `Iterator` that specifies a key-prefix (in `ReadOptions`) will use the Bloom Filter to avoid looking into data files that do not contain keys with the specified key-prefix
- **Persistence** : WAL
- **Multi-Threaded Compactions**
- **Compaction **:
   - Level Style Compaction (default) typically optimizes ==disk footprint== vs. ==logical database size== (space amplification) by minimizing the files involved in each compaction step: merging one file in Ln with all its overlapping files in Ln+1 and replacing them with new files in Ln+1.
   - Universal Style Compaction typically optimizes ==total bytes written to disk== vs. ==logical database size== (write amplification) by merging potentially many files and levels at once, requiring more temporary space. Universal typically results in lower write-amplification but higher space- and read-amplification than Level Style Compaction.
   - FIFO Style Compaction drops oldest file when obsolete and can be used for cache-like data. In FIFO compaction, all files are in level 0. When total size of the data exceeds configured size (CompactionOptionsFIFO::max_table_files_size), we delete the oldest table file.
   - We also enable developers to develop and experiment with custom compaction policies.
- **Compaction Filter** : Some applications may want to process keys at compaction time. For example, a database with inherent support for time-to-live (TTL) may remove expired keys. This can be done via an application-defined Compaction-Filter. If the application wants to continuously delete data older than a specific time, it can use the compaction filter to drop records that have expired. The RocksDB Compaction Filter gives control to the application to modify the value of a key or to drop a key entirely as part of the compaction process. For example, an application can continuously run a data sanitizer as part of the compaction.
- **Data Compression** : RocksDB supports lz4, zstd, snappy, zlib, and lz4_hc compression.
- **Full Backups and Replication**
- Block Cache -- Compressed and Uncompressed Data
- Pluggable Memtables : Three memtables are part of the library: a skiplist memtable, a vector memtable and a prefix-hash memtable. 
- Memtable Pipelining

> **TIPS**:
> In a sense, a `Snapshot` and an `Iterator` both provide a point-in-time view of the database, but their implementations are different. Short-lived/foreground scans are best done via an iterator while long-running/background scans are better done via a snapshot. ==An `Iterator` keeps a reference count on all underlying files that correspond to that point-in-time-view of the database - these files are not deleted until the `Iterator` is released.== A `Snapshot`, on the other hand, does not prevent file deletions; ==instead the compaction process understands the existence of `Snapshots` and promises never to delete a key that is visible in any existing `Snapshot`.==


# Links

1. [https://github.com/facebook/rocksdb/wiki/RocksDB-Overview](https://github.com/facebook/rocksdb/wiki/RocksDB-Overview)
