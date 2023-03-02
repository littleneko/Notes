# 读写流程

## Open

## Put/Delete

Put 和 Delete 对于 leveldb 来说都是 write，只是写如的 ValueType 不同，对于 delete 来说，只有 key，没有 value。Write 的对象是 WriteBatch，WriteBatch 是一个编码后的多个写入操作的 batch。

write 的主要步骤如下：

1. 构建 Writer 对象

   ```cpp
   Status DBImpl::Write(const WriteOptions& options, WriteBatch* updates) {
     Writer w(&mutex_);
     w.batch = updates;
     w.sync = options.sync;
     w.done = false;
   ```

2. 加锁，并把 Writer 对象放到待写队列中

   ```cpp
     MutexLock l(&mutex_);
     writers_.push_back(&w);
   ```

3. Write 支持并发写入，由队列中的第一个 Writer 对后面一批的数据进行批量写入，如果当前 Writer 不是队列中的第一个元素并且没有被其他线程写入，就等待被其他线程唤醒，如果已经被其他线程批量写了，就直接返回成功；

   ```cpp
     while (!w.done && &w != writers_.front()) {
       w.cv.Wait();
     }
     if (w.done) {
       return w.status;
     }
   ```

4. 如果自己就是队列中的第一个元素；或者因为一批写入的数量有限制，被唤醒的时候自己可能没有被写入，但是现在是队列第一个元素，自己需要作为 leader 进行批量写

5. ⭐️判断是否可以直接写或者需要生成新的 mem_table 或是刷 imm_memtable（`DBImpl::MakeRoomForWrite()`）

   1. 如果 LEVEL 0 的文件数目超过了 8 (`kL0_SlowdownWritesTrigger`)，则 sleep 进行 delay（该 delay 只会发生一次）；
   2. 如果当前 memtable 的 size 未达到阈值 write_buffer_size (默认 4MB)，则允许这次写；
   3. 如果当前 memtable 的 size 已经达到阈值，但 immutable memtable 仍存在，则等待 compact 将其 dump 完成；
   4. 如果 LEVEL 0 的文件数目达到 12 (`kL0_StopWritesTrigger`) 阈值，则等待 compact memtable 完成；
   5. 上述条件都不满足，则是 memtable 已经写满，并且 immutable memtable 不存在，则将当前 memtable 置为 immutable memtable，生成新的 memtable 和 log file，主动触发 compact， 允许该次写；

6. 从当前待写队列中取出 Writer，然后用 Writer 中的 WriteBatch 构建新的 WriteBatch，最终的 WriteBatch 有大小限制（`BuildBatchGroup()`）

7. 设置当前 WriteBatch 的 SequnceNumber 为 last_sequence + 1（注意：==这里一个 WriteBatch 都是同一个 SequnceNumber，而且这个 WriteBatch 可能对应上层的多个单独的 Put 操作==）

8. 将 WriteBatch 中的数据写到 log（`Log::AddRecord()`）

9. 将 WriteBatch 应用在 memtable 上（`WriteBatchInternal::InsertInto()`），即遍历 decode 出 WriteBatch 中的 key/value/ValueType，根据 ValueType 对 memetable 进行 put/delete 操作。

10. 更新 `Version::SequnceNumber`（`last_sequnce + WriteBatch::count()`）。

11. 唤醒当前已经写入完成的 Writer，如果这一批没有把队列中的所有数据写完，还要唤醒队列中第一个 Writer。

### WriteBatch

WriteBatch 保存编码后的多个待写入的 Key-Value，并提供遍历接口。

```
+-------------+----------+----------+----------+----------+----------+
| sequence(8) | count(4) | record_1 | Record_2 | ... ...  | Record_N |
+-------------+----------+----------+----------+----------+----------+

Record 分为两种:
1. Put
+------------------+------------------+------+---------------------+-------+
| kTypeValue(1)    | key_len(varin32) | key  | value_len(varint32) | value |
+------------------+------------------+------+---------------------+-------+

2. Delete
+------------------+------------------+------+
| kTypeDeletion(1) | key_len(varin32) | key  |
+------------------+------------------+------+
```

## Get

Get 的逻辑很简单，首先在 memtable 中查找，找不到就去 imm_memtable 中找，再找不到才会去 sstable 中查找。

```cpp
  // Unlock while reading from files and memtables
  {
    mutex_.Unlock();
    // First look in the memtable, then in the immutable memtable (if any).
    LookupKey lkey(key, snapshot);
    if (mem->Get(lkey, value, &s)) {
      // Done
    } else if (imm != nullptr && imm->Get(lkey, value, &s)) {
      // Done
    } else {
      s = current->Get(options, lkey, value, &stats);
      have_stat_update = true;
    }
    mutex_.Lock();
  }
```

### Version::Get()

`Version::Get()` 函数最终调用 `Version::ForEachOverlapping()` 完成 key 的查找，由于Level 0 之间的 SST 文件可能会有 Key Overlap，Level 1~N 之间的 SST 文件不会有 Key Overlap，所以查找 sstable 时 L0 需要遍历所有文件才能找到可能存在该 key 的文件，其他 Level 二分查找定位到可能存在该 key 的文件。

```cpp
void Version::ForEachOverlapping(Slice user_key, Slice internal_key, void* arg,
                                 bool (*func)(void*, int, FileMetaData*)) {
  const Comparator* ucmp = vset_->icmp_.user_comparator();

  // Search level-0 in order from newest to oldest.
  std::vector<FileMetaData*> tmp;
  tmp.reserve(files_[0].size());
  for (uint32_t i = 0; i < files_[0].size(); i++) {
    FileMetaData* f = files_[0][i];
    if (ucmp->Compare(user_key, f->smallest.user_key()) >= 0 &&
        ucmp->Compare(user_key, f->largest.user_key()) <= 0) {
      tmp.push_back(f);
    }
  }
  if (!tmp.empty()) {
    std::sort(tmp.begin(), tmp.end(), NewestFirst); // NewestFirst 按 filenumber 排序
    for (uint32_t i = 0; i < tmp.size(); i++) {
      if (!(*func)(arg, 0, tmp[i])) {
        return;
      }
    }
  }

  // Search other levels.
  for (int level = 1; level < config::kNumLevels; level++) {
    size_t num_files = files_[level].size();
    if (num_files == 0) continue;

    // Binary search to find earliest index whose largest key >= internal_key.
    uint32_t index = FindFile(vset_->icmp_, files_[level], internal_key);
    if (index < num_files) {
      FileMetaData* f = files_[level][index];
      if (ucmp->Compare(user_key, f->smallest.user_key()) < 0) {
        // All of "f" is past any data for user_key
      } else {
        if (!(*func)(arg, level, f)) {
          return;
        }
      }
    }
  }
}
```

## GetSnapshot

// TODO

# Recovery

// TODO
