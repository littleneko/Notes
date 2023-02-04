# Q&A
**Q: What's the difference between storing data in multiple column family and in multiple rocksdb database?**
A: The main differences will be backup, atomic writes and performance of writes. The advantage of using multiple databases: database is the unit of backup or checkpoint. It's easier to copy a database to another host than a column family. Advantages of using multiple column families:

1. write batches are atomic across multiple column families on one database. You can't achieve this using multiple RocksDB databases
1. If you issue sync writes to WAL, too many databases may hurt the performance.



**Q: Is RocksDB really “lockless” in reads?**
A: Reads might hold mutex in the following situations:

1. access the sharded block cache
1. access table cache if `options.max_open_files != -1`
1. if a read happens just after flush or compaction finishes, it may briefly hold the global mutex to fetch the latest metadata of the LSM tree.
1. the memory allocators RocksDB relies on (e.g. jemalloc), may sometimes hold locks. These locks are only held rarely, or in fine granularity.



**Q: What's the best practice to iterate all the keys?**
A: If it's a small or read-only database, just create an iterator and iterate all the keys. Otherwise consider to recreate iterators once a while, because an iterator will hold all the resources from being released. If you need to read from consistent view, create a snapshot and iterate using it.
​

**Q: Is the performance of iterator `Next()` the same as `Prev()`?**
A: The performance of reversed iteration is usually much worse than forward iteration. There are various reasons for that:

1. delta encoding in data blocks is more friendly to `Next()`
1. the skip list used in the memtable is single-direction, so `Prev()` is another binary search
1. the internal key order is optimized for `Next()`.




---

**Q: Is it possible to scan/iterate over keys only? If so, is that more efficient than loading keys and values?**
A: No it is usually not more efficient. RocksDB's values are normally stored inline with keys. When a user iterates over the keys, the values are already loaded in memory, so skipping the value won't save much. In BlobDB, keys and large values are stored separately so it maybe beneficial to only iterate keys, but it is not supported yet. We may add the support in the future.
​
