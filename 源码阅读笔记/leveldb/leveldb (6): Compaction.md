# Compaction

LevelDB 的写入和删除都是追加写 WAL，所以需要 Compaction 来删除那些重复的、过期的、待删除的 KV 数据，同时也可以加速读的作用。

LevelDB 中有三类 Compaction：

* **Minor Compaction**：immutable memtable 持久化为 sstable
* **Major Compaction**：sstable 之间的 compaction，多路归并排序
* **Manual Compaction**：外部调用 CompactRange 产生的 Compaction

其中 Major Compaction 有两类：

* size compaction：根据 level 的大小来触发
* seek compaction：每个 sstable 都有一个 seek miss 阈值，超过了就会触发



LevelDB 在函数 `DBImpl::MaybeScheduleCompaction()` -> `DBImpl::BackgroundCompaction()` 中完成对 compaction 优先级的调度。

具体优先级为：minor > manual > size > seek。

1. 如果 immutable memtable 不为空，则 dump 到 L0 的 sstable（`DBImpl::CompactMemTable()`）
2. 如果 is_manual 为 true 即 manual compaction，则调用 `DBImpl::CompactRange()`
3. 最后调用 `VersionSet::PickCompaction()` 函数，里面会优先进行 size compaction，再进行 seek compaction



所有调用 `DBImpl::MaybeScheduleCompaction()` 的地方：

* `DBImpl::Open()` 的时候
* `DBImpl::Get()` 的时候发现 sstable 的 miss 数量超过阈值（`Version::UpdateStats()`）
* `DBImpl::MakeRoomForWrite()` 的时候发现需要生成新的 memtable，然后把老的 memtable 转成 imm memtable，需要进行 minor compaction
* `Version::RecordReadSample()` // todo

# Minor Compaction

## 触发时机

Write(Put/Delete)、CompactRange、Recovery 以及 compaction 之后都会触发 minor compaction，最频繁触发的操作还是 Write 操作。

## 执行过程

Minor Compaction 由函数 `DBImpl::CompactMemTable()` 完成，主要是两个步骤：

1. 调用 `DBImpl::WriteLevel0Table()` 写入 sstable 文件，同时记录新文件信息到 VersionEdit 中
2. 生成新的 Version 并更新 Manifest 文件（`VersionSet::LogAndApply()`）

当 immutable memtable 持久化为 sstable 的时候，大多数情况下都会放在 L0，然后并不是所有的情况都会放在 L0，具体放在哪一层由 `Version::PickLevelForMemTableOutput()` 函数计算。

理论上应该需要将 dump 的 sstable 推至高 level，因为 L0 文件过多会导致**查找耗时增加**以及 **compaction 时内部 IO 消耗严重**；但是又不能推至太高的 level，因为需要控制查找的次数，而且某些范围的 key 更新频繁时，往高 level compaction **内部 IO 消耗严重**，而且也不易 compaction 到高 level，导致**空间放大严重**。所以 `Version::PickLevelForMemTableOutput()` 在选择输出到哪个 level 的时候，需要权衡查找效率、compaction IO 消耗以及空间放大，大体策略如下：

1. 最高可推至哪层由 kMaxMemCompactLevel 控制，默认最高 L2。
2. 如果 dump 成的 sstable 和 L0/L1 有重叠，则放到 L0（`Version::OverlapInLevel()`）。
3. 如果 dump 成的 sstable 和 L2 有重叠且重叠 sstable 总大小超过 10 * max_file_size，则放在 L0。
   
   > 此时如果放在 L1 会造成 compaction IO 消耗比较大，所以放在 L0，之后和 L1 的 sstable 进行 compaction，减小 sstable 的 key 范围，从而减小下次 compaction 涉及的 sstable 总大小。
4. 如果 dump 成的 sstable 和 L3 有重叠且重叠 sstable 总大小超过 10 * max_file_size，则放在 L1。

# Major Compaction

Major compaction 是 LevelDB compaction 中最复杂的部分，主要包含 size_compaction 和 seek_compaction，会进行重复数据、待删除的数据的清理，减少空间放大，提高读效率。

## Seek Compaction

在 LevelDB 中，每一个新的 sst 文件，都有一个 `allowed_seek` 的初始阈值，表示最多容忍 seek miss 次数，每当 Get miss 的时候都会减 1，当减为 0 的时候标记为需要 compaction 的文件。==LevelDB 认为如果一个 key 在 level i 中总是没找到，而是在 level i+1 中找到，这说明两层之间 key 的范围重叠很严重，当这种 seek miss 积累到一定次数之后，就考虑将其从 level i 中合并到 level i+1 中，这样可以避免不必要的 seek miss 消耗 read I/O==。其中 allowed_seek 的初始阈值的计算方式为：

```cpp
/ We arrange to automatically compact this file after
// a certain number of seeks.  Let's assume:
//   (1) One seek costs 10ms
//   (2) Writing or reading 1MB costs 10ms (100MB/s)
//   (3) A compaction of 1MB does 25MB of IO:
//         1MB read from this level
//         10-12MB read from next level (boundaries may be misaligned)
//         10-12MB written to next level
// This implies that 25 seeks cost the same as the compaction
// of 1MB of data.  I.e., one seek costs approximately the
// same as the compaction of 40KB of data.  We are a little
// conservative and allow approximately one seek for every 16KB
// of data before triggering a compaction.

f->allowed_seeks = static_cast<int>((f->file_size / 16384U));
if (f->allowed_seeks < 100) f->allowed_seeks = 100;
```

在 Version 中记录了相关的信息：

```cpp
  // Next file to compact based on seek stats.
  FileMetaData* file_to_compact_;
  int file_to_compact_level_;
```

不过引入了布隆过滤器之后，查找 miss 消耗的 IO 就会小很多，seek compaction 的作用也大大减小。

## Size Compaction

Size Compaction 是 levelDB 的核心 Compact 过程，其主要是为了均衡各个 level 的数据， 从而保证读写的性能均衡。在 Version 中记录了下次需要 compaction 的信息：

```cpp
  // Level that should be compacted next and its compaction score.
  // Score < 1 means compaction is not strictly needed.  These fields
  // are initialized by Finalize().
  double compaction_score_;
  int compaction_level_;
```

**触发条件**

1. 触发得分：在每次写入 sstable 的时候（`VersionSet::LogAndApply()`），levelDB 会计算每个 level 的总的文件大小，并根据此计算出一个 score，最后会根据这个 score 来选择合适 level 和文件进行 Compact，具体得分原则如下（`VersionSet::Finalize()`）：

   * level 0： level 0 的文件总数 / 4

   * 其他 level：当前 level 所有的文件 size 之和 / 此 level 的阈值，Level i 的阈值 (10^i) M （`MaxBytesForLevel()`）

     > 为什么 level 0 采用文件数，而不是文件大小计算 score 的原因：
     >
     > 1. With larger write-buffer sizes, it is nice not to do too many level-0 compactions.
     > 2. The files in level-0 are merged on every read and therefore we wish to ==avoid too many files when the individual file size is small== (perhaps because of a small write-buffer setting, or very high compression ratios, or lots of overwrites/deletions).

2. 当进行 Compation 时，判断上面的得分是否大于1，如果是则进行 Size Compaction（`VersionSet::PickCompaction()`）

## 执行过程

1. 调用 `VersionSet::PickCompaction()` 函数获取需要参加 compaction 的 sstable。

2. 如果不是 manual 且可以 TrivialMove，则直接将 sstable 逻辑上移动到下一层。

   > **TrivialMove**:
   >
   > 当且仅当 level i 的 sstable 个数为 1，level i+1 的 sstable 个数为 0，且该sstable 与 level i+2 层重叠的总大小不超过10 * max_file_size。

3. 获取 smallest_snapshot 作为 sequence_number

   * 如果有 snapshot 则使用所有 snapshot 中最小的 sequence_number
   * 否则使用当前 version 的 sequence_number。(`DBImpl::DoCompactionWork()`)

4. 生成 MergingIterator 对参与 compaction 的 sstable 进行多路归并排序。

5. 依次处理每对 KV，把有效的 KV 数据通过 TableBuilder 写入到 level+1 层的 sstable 中。

   1. 期间如果有 immu memtable，则优先执行 minor compaction。
   2. 重复的数据直接跳过，具体细节处理如下：
      1. 如果有 snapshot，则保留大于 smallest_snapshot 的所有的 record 以及一个小于 smallest_snapshot 的 record。
      2. 如果没有 snapshot，则仅保留 sequence_number 最大的 record。
   3. ==有删除标记的数据则**判断 level i+2 以上层有没有该数据**，有则保留，否则丢弃==。

6. `DBImpl::InstallCompactionResults()` 将本次 compaction 产生的 VersionEdit 调用 `VersionSet::LogAndApply()` 写入到 Manifest 文件中，期间会创建新的Version 成为 Current Version。

7. `DBImpl::CleanupCompaction()` 以及调用 `DBImpl::DeleteObsoleteFiles()` 删除不属于任何 version 的 sstable 文件以及 WAL、Manifest 文件。

```cpp
  while (input->Valid() && !shutting_down_.load(std::memory_order_acquire)) {
    // ... ...
    Slice key = input->key();
    // ... ...
    
		// Handle key/value, add to state, etc.
    bool drop = false;
    if (!ParseInternalKey(key, &ikey)) {
      // Do not hide error keys
      // ... ...
    } else {
      if (!has_current_user_key ||
          user_comparator()->Compare(ikey.user_key, Slice(current_user_key)) != 0) {
        // First occurrence of this user key
        current_user_key.assign(ikey.user_key.data(), ikey.user_key.size());
        has_current_user_key = true;
        last_sequence_for_key = kMaxSequenceNumber;
      }

      if (last_sequence_for_key <= compact->smallest_snapshot) {
        // Hidden by an newer entry for same user key
        drop = true;  // (A)
      } else if (ikey.type == kTypeDeletion &&
                 ikey.sequence <= compact->smallest_snapshot &&
                 compact->compaction->IsBaseLevelForKey(ikey.user_key)) {
        // For this user key:
        // (1) there is no data in higher levels
        // (2) data in lower levels will have larger sequence numbers
        // (3) data in layers that are being compacted here and have
        //     smaller sequence numbers will be dropped in the next
        //     few iterations of this loop (by rule (A) above).
        // Therefore this deletion marker is obsolete and can be dropped.
        drop = true;
      }

      last_sequence_for_key = ikey.sequence;
    }
    
    if (!drop) {
      // Open output file if necessary
      if (compact->builder == nullptr) {
        status = OpenCompactionOutputFile(compact);
        if (!status.ok()) {
          break;
        }
      }
      if (compact->builder->NumEntries() == 0) {
        compact->current_output()->smallest.DecodeFrom(key);
      }
      compact->current_output()->largest.DecodeFrom(key);
      compact->builder->Add(key, input->value());

      // Close output file if it is big enough
      if (compact->builder->FileSize() >=
          compact->compaction->MaxOutputFileSize()) {
        status = FinishCompactionOutputFile(compact, input);
        if (!status.ok()) {
          break;
        }
      }
    }

    input->Next();
  }
```

### MergingIterator

MergingIterator 接受多个 Iter 作为输入，最终 Next() 输出的是这些 Iter 归并排序后的数据：

```cpp
  void Next() override {
    assert(Valid());

    // Ensure that all children are positioned after key().
    // If we are moving in the forward direction, it is already
    // true for all of the non-current_ children since current_ is
    // the smallest child and key() == current_->key().  Otherwise,
    // we explicitly position the non-current_ children.
    if (direction_ != kForward) {
      for (int i = 0; i < n_; i++) {
        IteratorWrapper* child = &children_[i];
        if (child != current_) {
          child->Seek(key());
          if (child->Valid() &&
              comparator_->Compare(key(), child->key()) == 0) {
            child->Next();
          }
        }
      }
      direction_ = kForward;
    }

    current_->Next();
    FindSmallest();
  }
```

在 Compaction 中，MergingIterator 的输入就是所有 level i  和 level i+1 的 sstable 的 Iter：

```cpp
  // Level-0 files have to be merged together.  For other levels,
  // we will make a concatenating iterator per level.
  // TODO(opt): use concatenating iterator for level-0 if there is no overlap
  const int space = (c->level() == 0 ? c->inputs_[0].size() + 1 : 2);
  Iterator** list = new Iterator*[space];
  int num = 0;
  for (int which = 0; which < 2; which++) {
    if (!c->inputs_[which].empty()) {
      if (c->level() + which == 0) {
        const std::vector<FileMetaData*>& files = c->inputs_[which];
        for (size_t i = 0; i < files.size(); i++) {
          list[num++] = table_cache_->NewIterator(options, files[i]->number,
                                                  files[i]->file_size);
        }
      } else {
        // Create concatenating iterator for the files from this level
        list[num++] = NewTwoLevelIterator(
            new Version::LevelFileNumIterator(icmp_, &c->inputs_[which]),
            &GetFileIterator, table_cache_, options);
      }
    }
  }
  assert(num <= space);
  Iterator* result = NewMergingIterator(&icmp_, list, num);
```

## Pick SSTable⭐️

选取哪些 sstable 进行 compaction 在 `VersionSet::PickCompaction()` 函数中实现：

1. 选取 level i 上需要 compaction 的文件，即 `Compaction::inputs_[0]`

   * 对于 SizeCompaction 来说，计算 score 的同时也会记录 compaction_level_ 信息。每个 level 都有一个 string 类型的 compact_pointer 来判断需要从该 level 的那个位置开始 compaction（即上次 compaction 结束的位置），选取 compact_pointer_[level] 的下一个 sstable 作为初始的文件。

   ```cpp
     if (size_compaction) {
       level = current_->compaction_level_;
       c = new Compaction(options_, level);
       
   		// Pick the first file that comes after compact_pointer_[level]
       for (size_t i = 0; i < current_->files_[level].size(); i++) {
         FileMetaData* f = current_->files_[level][i];
         if (compact_pointer_[level].empty() ||
             icmp_.Compare(f->largest.Encode(), compact_pointer_[level]) > 0) {
           c->inputs_[0].push_back(f);
           break;
         }
       }
       if (c->inputs_[0].empty()) {
         // Wrap-around to the beginning of the key space
         c->inputs_[0].push_back(current_->files_[level][0]);
       }
   ```

   * 对于 Seek Compaction 来说，直接记录了需要 Compaction 的文件信息

   ```cpp
     } else if (seek_compaction) {
       level = current_->file_to_compact_level_;
       c = new Compaction(options_, level);
       c->inputs_[0].push_back(current_->file_to_compact_);
   ```

   * 另外，对于 L0 的 compaction，因为文件可能有 Overlap，所以需要把和上面 inputs_[0] 所有有 overlap 的 sstable 加入到待 compaction 的文件列表中

   ```cpp
     // Files in level 0 may overlap each other, so pick up all overlapping ones
     if (level == 0) {
       InternalKey smallest, largest;
       GetRange(c->inputs_[0], &smallest, &largest);
       // Note that the next call will discard the file we placed in
       // c->inputs_[0] earlier and replace it with an overlapping set
       // which will include the picked file.
       current_->GetOverlappingInputs(0, &smallest, &largest, &c->inputs_[0]);
       assert(!c->inputs_[0].empty());
     }
   ```

   * 此外，这里修复过一个 bug：https://github.com/google/leveldb/pull/339

     **BUG 的产生**：随着 compaction 的不断进行，在有 snapshot 的情况下，可能会导致每一层中有许多按照 sequence number 排序的 user_key 相同的record，如果这些 record 比较多或者对应的 value 比较大，那么这些 record 就会被分散保存到相邻的 sstable，从而导致把较新的 record compaction 到下层了，但是这些老的 record 还在上层。

     **BUG 修复**：在 `VersionSet::SetupOtherInputs()` 中调用 `VersionSet::AddBoundaryInputs()` 函数添加同层的有和当前选取的 sstable 的 largest_key 的 user_key 相等的其他 sstable 参与 compaction。

   <img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-cc40d2b357f0d40da4c6c049da587b9e_1440w.jpg" alt="img" style="zoom: 67%;" />

2. 选取 level i + 1 上需要 compaction 的文件，即 `Compaction::inputs_[1]` 

   根据 level i 上选取出的 sstable，确定其 [smallest, largest]，然后选出 level i+1 上与其有重叠的所有 sstable（`VersionSet::SetupOtherInputs()`）

   ```cpp
     GetRange(c->inputs_[0], &smallest, &largest);
     current_->GetOverlappingInputs(level + 1, &smallest, &largest, &c->inputs_[1]);
   ```

3. **==扩展 level i 上的 sstable==**

   在已经选取的 level i+1 的 sstable 数量不变的情况下，尽可能的增加 level i 中参与 compaction 的 sstable 数量，总的参与 compaction 的 sstable 的大小阈值为 25 * max_file_size。

   计算出 level i 和 level i+1 的 [smallest, largest]，然后计算出和 level i 上有哪些 sstable 重叠，如果 level i 上新增的 sstable 不会与 level i+1 上的非compaction 的 sstable 重叠，则加入此次 compaction（即一次尽可能把更多的 level i 推向 level i + 1）。

   <img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-4cc6c6694069021a2761fe2faa1f40ea_1440w.jpg" alt="img" style="zoom:67%;" />

# Manual Compaction

// TODO

# Links

1. https://zhuanlan.zhihu.com/p/360345923
