# Architecture

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/119747261-310fb300-be47-11eb-92c3-c11719fa8a0c.png" alt="img" style="zoom: 33%;" />

(上图来自 [RocksDB wiki](https://github.com/facebook/rocksdb/wiki/RocksDB-Overview)，两者架构基本相同)



LevelDB 整体由以下 6 个模块构成：

* **MemTable**：KV 数据在内存的存储格式，由 SkipList 组织，整体有序。

* **Immutable MemTable**：MemTable 达到一定阈值后变为不可写的 MemTable，等待被 Flush 到磁盘上。
* **Log**：有点类似于文件系统的 Journal，用来保证 Crash 不丢数据，支持批量写的原子操作、转换随机写为顺序写。
* **SSTable**：KV 数据在磁盘的存储格式，文件里面的 Key 整体有序，一旦生成便是只读的，L0 可能会有 Overlap，其他层 sstable 之间都是有序的。
* **Manifest**：增量的保存 DB 的状态信息，使得重启或者故障后可以恢复到退出前的状态。
* **Current**：记录当前最新的 Manifest 文件名。



一个完整的 leveldb 目录文件如下：

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220503225229761.png" alt="image-20220503225229761" style="zoom: 50%;" />

# 代码目录结构

* **include/leveldb**：使用者需要的头文件，包含基本的接口，可以自定义的 comparator/env/cache，以及依赖的头文件。 
* **db**：主要逻辑的实现。
  * 接口的实现（db_impl/db_iter）
  * 内部结构的定义 （dbformat/memtable/skiplist/write_batch）
  * db 运行状态以及操作的包装 （version_set/version_edit）
  * log 格式相关（log/log_reader/log_writer）
  * filename 处理相 关（filename）
  * sstable 相关（builder/table_cache）. 
* **table**：sstable 相关的数据格式定义以及操作实现。 
  * 格式定义（format）
  * block 相关的操作（block/block_builder）
  * sstable 相关的操作 （table/table_builder）
  * 操作便利封装的复合 Iterator（two_level_iterator/ merger）
  * 优化 Iterator 的 wrapper（iterator_wrapper）
* **port**：根据系统环境，为移植实现的锁/信号/原子操作/压缩相关，提供 posix/android。
* **util**：提供的通用功能实现
  * memtable 使用的简单内存管理（arena）
  * LRU cache 的实现（cache）
  * comparator 的默认实现 （comparator）
  * 通用功能的实现（coding/crc32c/hash/random/MutexLock/logging）
  * leveldb 将文件/进程相关的操作封装成 Env，提供了默认的实现（env_posix）
* **helper/memenv** 实现了一个简单的完全内存的文件系统，提供操作目录文件的接口。

# 基本概念

## Slice

为操作数据的方便，将数据和长度包装成 Slice 使用，直接操控指针避免不必要的数据拷贝。

* 定义：

```cpp
class Slice {
public:
    // ... ...
private:
  const char* data_;
  size_t size_;
};
```

- 注意事项：==Slice 的数据是外部管理的，因此 Slice 的使用者需要保证生命周期内 data_ 指向的内存是有效的==。
- 源码文件：include/slice.h

> **Tips**:
>
> 因为 Slice 只是数据的一个引用，并不拥有 data_ 指向内存的所有权，在有些需要返回 Slice 的地方，会提供一个 `std::string*` 类型的 scratch 参数，用于把数据存储到 scratch 中，然后用 *scratch 初始化 Slice。
>
> e.g. Reader 中有如下函数：
>
> ```c++
>   bool ReadRecord(Slice* record, std::string* scratch);
> ```
>
> 或者有时候需要记录 Slice 指向的数据是否是在堆上新分配的：
>
> ```c++
> struct BlockContents {
>   	Slice data;           // Actual contents of data
>   	bool cachable;        // True iff data can be cached
>   	bool heap_allocated;  // True iff caller should delete[] data.data()
> };
> ```

## Env

* leveldb 将操作系统相关的操作（文件、线程、时间）抽象成 Env，用户可以实现自己的 Env(BlueRocksEnv)，灵活性比较高。
* 源码文件：include/leveldb/env.h util/env_posix.h

## Varint

* leveldb 采用了 protocalbuffer 里使用的变长整形编码方法，节省空间。

```cpp
// Lower-level versions of Put... that write directly into a character buffer
// and return a pointer just past the last byte written.
// REQUIRES: dst has enough space for the value being written
char* EncodeVarint32(char* dst, uint32_t value);
char* EncodeVarint64(char* dst, uint64_t value);
```

* 源码文件：util/coding.h

## ValueType 

leveldb 更新（put/delete）某个 key 时不会操控到 DB 中的数据，每次操作都是直接新插入一份 KV 数据，具体的数据合并和清除由后台的 Compact 完成。所以每次 put，DB 中就会新加入一份 KV 数据， 即使该 key 已经存在；而 delete 等同于 put 空的 Value。为了区分真实 KV 数据和删除操作的 Mock 数据，使用 ValueType 来标识。

* 定义：

```cpp
// Value types encoded as the last component of internal keys.
// DO NOT CHANGE THESE ENUM VALUES: they are embedded in the on-disk
// data structures.
enum ValueType { kTypeDeletion = 0x0, kTypeValue = 0x1 };
// kValueTypeForSeek defines the ValueType that should be passed when
// constructing a ParsedInternalKey object for seeking to a particular
// sequence number (since we sort sequence numbers in decreasing order
// and the value type is embedded as the low 8 bits in the sequence
// number in internal keys, we need to use the highest-numbered
// ValueType, not the lowest).
static const ValueType kValueTypeForSeek = kTypeValue;
```

源码文件：db/dbformat.h

## SequnceNnumber

leveldb 中的每次更新（put/delete）操作都拥有一个版本，由 SequnceNumber 来标识，整个 DB 有一个全局值保存着当前使用到的 SequnceNumber。SequnceNumber 在 leveldb 有重要的地位，key 的排序、compact 以及 snapshot 都依赖于它。 

* 定义：

```cpp
typedef uint64_t SequenceNumber;
// We leave eight bits empty at the bottom so a type and sequence#
// can be packed together into 64-bits.
static const SequenceNumber kMaxSequenceNumber = ((0x1ull << 56) - 1);
```

* 格式：==存储时，SequnceNumber 只占用 56 bits，ValueType 占用 8 bits，二者共同占用 64bits (uint64_t)==。

```cpp
static uint64_t PackSequenceAndType(uint64_t seq, ValueType t) {
  assert(seq <= kMaxSequenceNumber);
  assert(t <= kValueTypeForSeek);
  return (seq << 8) | t;
}
```

* 源码文件：db/dbformat.h

## ParsedInternalKey

db 内部操作的 key，db 内部需要将 user key 加入元信息（ValueType/SequenceNumber）一并做处理。

* 定义：

```c++
struct ParsedInternalKey {
  Slice user_key;
  SequenceNumber sequence;
  ValueType type;

  ParsedInternalKey() {}  // Intentionally left uninitialized (for speed)
  ParsedInternalKey(const Slice& u, const SequenceNumber& seq, ValueType t)
      : user_key(u), sequence(seq), type(t) {}
  std::string DebugString() const;
};
```

* 源码文件：db/dbformat.h

## InternalKey

db 内部，包装易用的结构，包含 userkey 与 SequnceNumber/ValueType。

* 格式：数据存储在一个 string 中，格式为：==**[user_key]\[SequnceNumber | ValueType]**==，后半部分固定 8 字节

* 定义：

```cpp
// Modules in this directory should keep internal keys wrapped inside
// the following class instead of plain strings so that we do not
// incorrectly use string comparisons instead of an InternalKeyComparator.
class InternalKey {
 private:
  std::string rep_;

 public:
  InternalKey() {}  // Leave rep_ as empty to indicate it is invalid
  InternalKey(const Slice& user_key, SequenceNumber s, ValueType t) {
    AppendInternalKey(&rep_, ParsedInternalKey(user_key, s, t));
  }

  Slice user_key() const { return ExtractUserKey(rep_); }

  void SetFrom(const ParsedInternalKey& p) {
    rep_.clear();
    AppendInternalKey(&rep_, p);
  }
};


void AppendInternalKey(std::string* result, const ParsedInternalKey& key) {
  result->append(key.user_key.data(), key.user_key.size());
  PutFixed64(result, PackSequenceAndType(key.sequence, key.type));
}

// Returns the user key portion of an internal key.
inline Slice ExtractUserKey(const Slice& internal_key) {
  assert(internal_key.size() >= 8);
  return Slice(internal_key.data(), internal_key.size() - 8);
}
```

* 源码文件：db/dbformat.h

## LookupKey

db 内部在为查找 memtable/sstable 方便，包装使用的 key 结构，保存有 user_key 与 SequnceNumber/ValueType dump 在内存的数据。

* 定义：

```cpp
class LookupKey {
public:
  // ... ...
    
  // Return a key suitable for lookup in a MemTable.
  Slice memtable_key() const { return Slice(start_, end_ - start_); }

  // Return an internal key (suitable for passing to an internal iterator)
  Slice internal_key() const { return Slice(kstart_, end_ - kstart_); }

  // Return the user key
  Slice user_key() const { return Slice(kstart_, end_ - kstart_ - 8); }

private:
  // We construct a char array of the form:
  //    klength  varint32               <-- start_
  //    userkey  char[klength]          <-- kstart_
  //    tag      uint64
  //                                    <-- end_
  // The array is a suitable MemTable key.
  // The suffix starting with "userkey" can be used as an InternalKey.
  const char* start_;
  const char* kstart_;
  const char* end_;
};
```

* 格式：数据经过编码后存储

```cpp
LookupKey::LookupKey(const Slice& user_key, SequenceNumber s) {
  size_t usize = user_key.size();
  size_t needed = usize + 13;  // A conservative estimate
  char* dst;
  if (needed <= sizeof(space_)) {
    dst = space_;
  } else {
    dst = new char[needed];
  }
  start_ = dst;
  dst = EncodeVarint32(dst, usize + 8);
  kstart_ = dst;
  std::memcpy(dst, user_key.data(), usize);
  dst += usize;
  EncodeFixed64(dst, PackSequenceAndType(s, kValueTypeForSeek));
  dst += 8;
  end_ = dst;
}
```

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220504003340582.png" alt="image-20220504003340582" style="zoom:50%;" />

* 源码文件：db/dbformat.h

## Comparator

对 key 排序时使用的比较方法。leveldb 中 key 为升序。用户可以自定义 userkey 的 comparator (user_comparator)，作为 option 传入，默认采用 byte compare(memcmp)， comparator 中有 FindShortestSeparator()/ FindShortSuccessor() 两个接口：

* FindShortestSeparator(start, limit) 是获得大于 start 但小于 limit 的最小值。
* FindShortSuccessor(start) 是获得比 start 大的最小值。比较都基于 user_commparator，二者会被用来确定 sstable 中 block 的 end_key。

源码文件：include/leveldb/comparator.h util/comparator.cc

## InternalKeyComparator 

db 内部做 key 排序时使用的比较方法。

排序时，会先使用 user_comparator 比较 user_key，如果 user-key 相同，则比较 SequnceNumber，SequnceNumber 大的为小。因为 SequnceNumber 在 db 中全局递增，所以，对于相同的 user_key，最新的更新（SequnceNumber 更大）排在前面，在查找的时候会被先找到。 

```cpp
// A comparator for internal keys that uses a specified comparator for
// the user key portion and breaks ties by decreasing sequence number.
class InternalKeyComparator : public Comparator {
 private:
  const Comparator* user_comparator_;

 public:
  explicit InternalKeyComparator(const Comparator* c) : user_comparator_(c) {}
  const char* Name() const override;
  int Compare(const Slice& a, const Slice& b) const override;
  void FindShortestSeparator(std::string* start,
                             const Slice& limit) const override;
  void FindShortSuccessor(std::string* key) const override;

  const Comparator* user_comparator() const { return user_comparator_; }

  int Compare(const InternalKey& a, const InternalKey& b) const;
};

int InternalKeyComparator::Compare(const Slice& akey, const Slice& bkey) const {
  // Order by:
  //    increasing user key (according to user-supplied comparator)
  //    decreasing sequence number
  //    decreasing type (though sequence# should be enough to disambiguate)
  int r = user_comparator_->Compare(ExtractUserKey(akey), ExtractUserKey(bkey));
  if (r == 0) {
    const uint64_t anum = DecodeFixed64(akey.data() + akey.size() - 8);
    const uint64_t bnum = DecodeFixed64(bkey.data() + bkey.size() - 8);
    if (anum > bnum) {
      r = -1;
    } else if (anum < bnum) {
      r = +1;
    }
  }
  return r;
}
```

InternalKeyComparator 中 FindShortestSeparator（）/ FindShortSuccessor（）的实现，仅从传入的内部 key 参数，解析出 user-key，然后再调用 user-comparator 的对应接口。

## WriteBatch

对若干数目 key 的 write 操作（put/delete）封装成 WriteBatch。它会将 userkey 连同 SequnceNumber 和 ValueType 先做 encode，然后做 decode，将数据 insert 到指定的 Handler （memtable）上面。上层的处理逻辑简洁，但 encode/decode 略有冗余。

## TableCache

TableCache 是一个 LRU cache，保存了最近的打开的 sstable 的信息：

```cpp
struct TableAndFile {
  RandomAccessFile* file;
  Table* table; // sstable 对象
};
```

## Version

将每次 compact 后的最新数据状态定义为 Version，也就是当前 db 元信息以及每个 level 上具有最新数据状态的 sstable 集合。compact 会在某个 level 上新加入或者删除一些 sstable，但可能这个时候， 那些要删除的 sstable 正在被读，为了处理这样的读写竞争情况，基于 sstable 文件一旦生成就不会改动的特点，每个 Version 加入引用计数，读以及解除读操作会将引用计数相应加减一。这样，db 中可能有多个 Version 同时存在（提供服务），它们通过链表链接起来。当 Version 的引用计数为 0 并 且不是当前最新的 Version 时，它会从链表中移除；对应的，该 Version 内的 sstable 就可以删除了（这些废弃的 sstable 会在下一次 compact 完成时被清理掉）。

```cpp
class Version {
public:
  // ... ...

private:
  VersionSet* vset_;  // VersionSet to which this Version belongs
  Version* next_;     // Next version in linked list
  Version* prev_;     // Previous version in linked list
  int refs_;          // Number of live refs to this version

  // List of files per level
  std::vector<FileMetaData*> files_[config::kNumLevels];

  // Next file to compact based on seek stats.
  FileMetaData* file_to_compact_;
  int file_to_compact_level_;

  // Level that should be compacted next and its compaction score.
  // Score < 1 means compaction is not strictly needed.  These fields
  // are initialized by Finalize().
  double compaction_score_;
  int compaction_level_;
};
```

## VersionSet

整个 db 的当前状态被 VersionSet 管理着，其中有当前最新的 Version 以及其他正在服务的 Version 链表；全局的 SequnceNumber、FileNumber；当前的 manifest_file_number；封装 sstable 的 TableCache。 每个 level 中下一次 compact 要选取的 start_key 等等。

```cpp
class VersionSet {
public:
  // ... ...
private:
  Env* const env_;
  const std::string dbname_;
  const Options* const options_;
  TableCache* const table_cache_;
  const InternalKeyComparator icmp_;
  uint64_t next_file_number_;
  uint64_t manifest_file_number_;
  uint64_t last_sequence_;
  uint64_t log_number_;
  uint64_t prev_log_number_;  // 0 or backing store for memtable being compacted

  // Opened lazily
  WritableFile* descriptor_file_;
  log::Writer* descriptor_log_;
  Version dummy_versions_;  // Head of circular doubly-linked list of versions.
  Version* current_;        // == dummy_versions_.prev_

  // Per-level key at which the next compaction at that level should start.
  // Either an empty string, or a valid InternalKey.
  std::string compact_pointer_[config::kNumLevels];
};
```

## VersionEdit

compact 过程中会有一系列改变当前 Version 的操作（FileNumber 增加，删除 input 的 sstable，增加输出的 sstable），为了缩小 Version 切换的时间点，将这些操作封装成 VersionEdit，compact 完成时，将 VersionEdit 中的操作一次应用到当前 Version 即可得到最新状态的 Version。

# 数据结构和存储格式

## MemTable

```cpp
class MemTable {
 public:
  // Return an iterator that yields the contents of the memtable.
  //
  // The caller must ensure that the underlying MemTable remains live
  // while the returned iterator is live.  The keys returned by this
  // iterator are internal keys encoded by AppendInternalKey in the
  // db/format.{h,cc} module.
  Iterator* NewIterator();

  // Add an entry into memtable that maps key to value at the
  // specified sequence number and with the specified type.
  // Typically value will be empty if type==kTypeDeletion.
  void Add(SequenceNumber seq, ValueType type, const Slice& key,
           const Slice& value);

  // If memtable contains a value for key, store it in *value and return true.
  // If memtable contains a deletion for key, store a NotFound() error
  // in *status and return true.
  // Else, return false.
  bool Get(const LookupKey& key, std::string* value, Status* s);
 
private:
  struct KeyComparator {
    const InternalKeyComparator comparator;
    explicit KeyComparator(const InternalKeyComparator& c) : comparator(c) {}
    int operator()(const char* a, const char* b) const;
  };

  typedef SkipList<const char*, KeyComparator> Table;

  KeyComparator comparator_;
  int refs_;
  Arena arena_;
  Table table_;
};
```

MemTable 以及 Immutable MemTable 是 KV 数据在内存中的存储格式，底层数据结构都是 SkipList，插入查找的时间复杂度都是 Olog(n)。

MemTable 的大小通过参数 *write_buffer_size* 控制，默认 4MB，最多 5MB dump（最大 batch size 为 1MB）成 SSTable。

当一个 MemTable 大小达到阈值后，将会变成 Immutable MemTable，同时生成一个新的 MemTable 来支持新的写入，Compaction 线程将 Immutable MemTable Flush 到 L0/L1/… 上。所以在LevelDB中，同时最多只会存在两个 MemTable，一个可写的，一个只读的。



由于 SkipList 是链表形式的，所以我们需要把 KV 数据的映射形式转换成该形式，如图所示，[start, node_end] 区间就代表一个 SkipList Node。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-00a21206a818ce6d3a9ae0d35b9e0363_1440w.jpg" alt="img" style="zoom:50%;" />

## WAL/LOG

WAL 即 Log，每次数据都会先顺序写到 Log 中，然后再写入 MemTable，可以起到转换随机写为顺序写以及保证 Crash 不丢数据的作用。

一个完整的 Log 由多个固定大小的 block 组成，block 大小默认 32KB；block 由一个或者多个 record 组成。

**相关源码**：db/log_format.h, db/log_reader.h/cc, db/log_writer.h/cc

### LOG Format

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-6d05ad55b349ff12653dd9f1b245e96f_1440w.jpg" alt="img" style="zoom:67%;" />

一个 Record 可以跨越多个 Block。

### Record Format

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-297b2d28520fbab67587471b2a1973b8_1440w.jpg" alt="img" style="zoom:50%;" />

- checksum：计算 type 和 data 的 crc。
- length：data 的长度，2Byte 可表示 64KB，而 block 为 32KB，刚好够用。
- type：一个 record 可以在一个或者跨越多个 block，类型有 5 种：FULL、First、Middle、Last、Zero (预分配连续的磁盘空间用)。
- data：用户的 kv 数据。

### Read

对 WAL log 的读取通过 `Reader::ReadRecord()` 接口实现，函数原型如下：

```cpp
  // Read the next record into *record.  Returns true if read
  // successfully, false if we hit end of the input.  May use
  // "*scratch" as temporary storage.  The contents filled in *record
  // will only be valid until the next mutating operation on this
  // reader or the next mutation to *scratch.
  bool ReadRecord(Slice* record, std::string* scratch);
```

另外，在初始化啊 Reader 的时候，可以传入一个 initial_offset 表示从某个位置开始读取。因为 Log 的读取以 block 为单位，所以在开始读取前会直接跳转到该 offset 所在的 block 的起始位置（`Reader::SkipToInitialBlock()`）。

> 目前所有用到 Reader 的地方 initial_offset 都是 0。

实际在读取的时候会跳过 record data start offset 小于 initial_offset 的 record：

```cpp
    // Skip physical record that started before initial_offset_
    if (end_of_buffer_offset_ - buffer_.size() - kHeaderSize - length <
        initial_offset_) {
      result->clear();
      return kBadRecord;
    }
```

---

ReadRecord 函数第二个参数 scratch 表示返回的 record 的内存，不过 Reader 本身拥有一个 block 大小的 buffer，如果 record 没有跨 block（即 FULL 类型的 record），那么返回的 Slice 直接指向这个内部的 buffer，不会用到这个 scratch；只有在跨 block 的 record 时，才会把 record copy 到 scratch 中。

### Write

log 的 写入很简单，需要注意的是如果当前 block 剩余空间小于 kHeaderSize (7 byte)，已经放不下一个完整的 header 了，就把该 block 剩余空间全填 0：

```cpp
    const int leftover = kBlockSize - block_offset_;
    assert(leftover >= 0);
    if (leftover < kHeaderSize) {
      // Switch to a new block
      if (leftover > 0) {
        // Fill the trailer (literal below relies on kHeaderSize being 7)
        static_assert(kHeaderSize == 7, "");
        dest_->Append(Slice("\x00\x00\x00\x00\x00\x00", leftover));
      }
      block_offset_ = 0;
    }
```

## SSTable

### SSTable Format

SSTable 整体的格式如下图所示：

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-ca3684deaebf6c6fd10fc6312e8919d1_1440w.jpg" alt="img" style="zoom:67%;" />

- DataBlock：存储实际的 kv data、type、crc。
- MetaBlock：暂时没有使用，不过可将 Filter Block 当成一种特殊的 MetaBlock。
- MetaIndexBlock：保存 MetaBlock 的索引信息，目前仅有一行 KV 数据，记录了 FilterBlock 的 name 以及 offset/size。
- IndexBlock：保存每个 DataBlock 的 LastKey 和在 SST 文件中的 offset/size。
- Footer：文件末尾固定长度的数据，保存 MetaIndexBlock、IndexBlock 的索引信息。

SSTable 中的 BlockSize 大小默认为 4K，MetaIndex、DataBlock、IndexBlock 都是使用同样的 BlockBuilder 来构建 Block，区别是里面的 KV 数据不同。

DataBlock 中的 KV 是有序存储的，相邻的 key 之间很有可能重复，因此采用==前缀压缩==来存储 key，后一个 key 只存储与前一个 key 不同的部分。==如果所有 key 都这样压缩，那么得到一个完整的 key 需要从 block 的第一个 key 开始遍历，为了避免这种情况，每隔 block_restart_interval（默认 16）个 key 就存储完整的 key，然后 restart 指出的位置就表示该 key 不按前缀压缩，而是完整存储该 key==。

对于 MetaBlock 和 IndexBlock 来说由于相邻 key 差距比较大，所以不开启前缀压缩，即 block_restart_interval 为 1。

### 相关数据结构

**BlockHandle**

BlockHandle 表示一个 Block 的信息，包括 offset 和 size：

```cpp
// BlockHandle is a pointer to the extent of a file that stores a data
// block or a meta block.
class BlockHandle {
 public:
  // Maximum encoding length of a BlockHandle
  enum { kMaxEncodedLength = 10 + 10 };
  // ... ...

 private:
  uint64_t offset_;
  uint64_t size_; // size 不包含结尾 1 byte 的 compression type 和 4 bytes 的 crc32
};
```

**BlockContents**

BlockContents 表示一个 Block 的数据，ReadBlock() 通过 BlockHandle 的信息读取一个 Block，然后把数据保存在 BlockContents 中：

```cpp
struct BlockContents {
  Slice data;           // Actual contents of data
  bool cachable;        // True iff data can be cached
  bool heap_allocated;  // True iff caller should delete[] data.data()
};
```

### Block

Block 中保存了读取到的数据，并且提供对 Block 中每个 Record 遍历的接口。

```cpp
class Block {
 public:
  // Initialize the block with the specified contents.
  explicit Block(const BlockContents& contents);

  Block(const Block&) = delete;
  Block& operator=(const Block&) = delete;

  ~Block();

  size_t size() const { return size_; }
  Iterator* NewIterator(const Comparator* comparator);

 private:
  class Iter;

  uint32_t NumRestarts() const;

  const char* data_;
  size_t size_;
  uint32_t restart_offset_;  // Offset in data_ of restart array
  bool owned_;               // Block owns data_[]
};
```

* **restart_offset_** 表示 restart 数据开始的 offset，可以直接算出来：

  `restart_offset_ = size_ - (1 + NumRestarts()) * sizeof(uint32_t);`

* **size_** 不包括 compression_type 和 crc32 的部分

#### Iter

Iter 可以顺序遍历，同时支持根据 key Seek，实现是==二分查找==。

```cpp
class Block::Iter : public Iterator {
 private:
  const Comparator* const comparator_;
  const char* const data_;       // underlying block contents
  uint32_t const restarts_;      // Offset of restart array (list of fixed32)
  uint32_t const num_restarts_;  // Number of uint32_t entries in restart array

  // current_ is offset in data_ of current entry.  >= restarts_ if !Valid
  uint32_t current_;
  uint32_t restart_index_;  // Index of restart block in which current_ falls
  std::string key_;
  Slice value_;
  Status status_;
  
// ... ...
};
```

* **current_** 表示当前 value(record) 在 block 中的 offset，初始值是 restarts_，即 iter 初始是 !Valid，在第一次使用之前需要先 SeekToFirst()
* **value_** 表示当前的 value(record)，在 SeekToFirst() 之后才会真正表示第一个 record 的值

```cpp
  void SeekToFirst() override {
    SeekToRestartPoint(0);
    ParseNextKey();
  }

  void SeekToRestartPoint(uint32_t index) {
    key_.clear();
    restart_index_ = index;
    // current_ will be fixed by ParseNextKey();

    // ParseNextKey() starts at the end of value_, so set value_ accordingly
    uint32_t offset = GetRestartPoint(index);
    value_ = Slice(data_ + offset, 0);
  }

	// 解出第 index 个 restart 的值，即指向的数据的 offset
  uint32_t GetRestartPoint(uint32_t index) {
    assert(index < num_restarts_);
    return DecodeFixed32(data_ + restarts_ + index * sizeof(uint32_t));
  }
```

SeekToRestartPoint(0) 实际上是把 restart_index_ 置为 0，GetRestartPoint(0) 返回的是第 0 个 restart 指向的数据的 offset，也就是 0；最后当前 value 的值置为指向 data 大小为 0 的值，这里是为了方便 ParseNextKey() 统一处理。

ParseNextKey 用于处理下一个 value，可能需要把 restart_index_ 指针移动到下一个位置：

```cpp
  // Return the offset in data_ just past the end of the current entry.
	// 在 SeekToFirst 后, value 的 size 为 0, 所以这里的 offset 算出来是 0
	// 此后, value 表示正常的 record, 该函数返回的是下一个 record 的起始 offset
  inline uint32_t NextEntryOffset() const {
    return (value_.data() + value_.size()) - data_;
  }

	bool ParseNextKey() {
    // SeekToFirst 后, 第一次返回值为 0
    current_ = NextEntryOffset();
    const char* p = data_ + current_;
    const char* limit = data_ + restarts_;  // Restarts come right after data
    // ...

    // Decode next entry
    uint32_t shared, non_shared, value_length;
    p = DecodeEntry(p, limit, &shared, &non_shared, &value_length);
    if (p == nullptr || key_.size() < shared) {
      CorruptionError();
      return false;
    } else {
      key_.resize(shared);
      key_.append(p, non_shared);
      value_ = Slice(p + non_shared, value_length);
      // 判断是否需要把 restart_index_ 向后移动, 如果下一个 restart 指向的数据 offset 比当前的数据 offset 小,
      // 即当前的 record 应该是 restart_index + 1 的 restart 来表示的
      while (restart_index_ + 1 < num_restarts_ && GetRestartPoint(restart_index_ + 1) < current_) {
        ++restart_index_;
      }
      return true;
    }
  }
};
```

---

#### Read

对于 Block 的读取通过 ReadBlock() 函数实现，其接受一个 BlockHandle 作为参数，返回读取到的数据 保存在 BlockContents 中，主要流程如下：

```cpp
// 1-byte type + 32-bit crc
static const size_t kBlockTrailerSize = 5;

Status ReadBlock(RandomAccessFile* file, const ReadOptions& options,
                 const BlockHandle& handle, BlockContents* result) {
  // ... ...
  
  // Read the block contents as well as the type/crc footer.
  // See table_builder.cc for the code that built this structure.
  size_t n = static_cast<size_t>(handle.size());
  char* buf = new char[n + kBlockTrailerSize];
  Slice contents;
  Status s = file->Read(handle.offset(), n + kBlockTrailerSize, &contents, buf);
  
  // Check the crc of the type and the block contents
  const char* data = contents.data();  // Pointer to where Read put the data
  // ... ...
  
  switch (data[n]) {
    case kNoCompression:
      // 
    case kSnappyCompression: {
      // 需要先解压, 因此需要 new 出来一个 buffer
      char* ubuf = new char[ulength];
      if (!port::Snappy_Uncompress(data, n, ubuf)) {
        // ...
      }
      result->data = Slice(ubuf, ulength);
      result->heap_allocated = true;
      result->cachable = true;
    }
  }
}
```

### Record (data/index/…)

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220504221858602.png" alt="image-20220504221858602" style="zoom:50%;" />

Record 实现了前缀压缩，每 block_restart_interval 个 record 重新开始计算压缩前缀。

* shared key size：和前一个 key 相同的部分的长度
* noshared key size：剩余部分 key 的长度
* value size：value 的长度
* noshared key：noshared key 的数据
* value：value 的数据

Record 格式在上面的图中已经给出，可以看 DecodeEntry() 和 BlockBuilder::Add() 函数的实现。

```cpp
// Helper routine: decode the next block entry starting at "p",
// storing the number of shared key bytes, non_shared key bytes,
// and the length of the value in "*shared", "*non_shared", and
// "*value_length", respectively.  Will not dereference past "limit".
//
// If any errors are detected, returns nullptr.  Otherwise, returns a
// pointer to the key delta (just past the three decoded values).
static inline const char* DecodeEntry(const char* p, const char* limit,
                                      uint32_t* shared, uint32_t* non_shared,
                                      uint32_t* value_length) {
  if (limit - p < 3) return nullptr;
  *shared = reinterpret_cast<const uint8_t*>(p)[0];
  *non_shared = reinterpret_cast<const uint8_t*>(p)[1];
  *value_length = reinterpret_cast<const uint8_t*>(p)[2];
  if ((*shared | *non_shared | *value_length) < 128) {
    // Fast path: all three values are encoded in one byte each
    p += 3;
  } else {
    if ((p = GetVarint32Ptr(p, limit, shared)) == nullptr) return nullptr;
    if ((p = GetVarint32Ptr(p, limit, non_shared)) == nullptr) return nullptr;
    if ((p = GetVarint32Ptr(p, limit, value_length)) == nullptr) return nullptr;
  }

  if (static_cast<uint32_t>(limit - p) < (*non_shared + *value_length)) {
    return nullptr;
  }
  return p;
}
```

```cpp
void BlockBuilder::Add(const Slice& key, const Slice& value) {
  Slice last_key_piece(last_key_);
  assert(!finished_);
  assert(counter_ <= options_->block_restart_interval);
  assert(buffer_.empty()  // No values yet?
         || options_->comparator->Compare(key, last_key_piece) > 0);
  size_t shared = 0;
  if (counter_ < options_->block_restart_interval) {
    // See how much sharing to do with previous string
    const size_t min_length = std::min(last_key_piece.size(), key.size());
    while ((shared < min_length) && (last_key_piece[shared] == key[shared])) {
      shared++;
    }
  } else {
    // Restart compression
    restarts_.push_back(buffer_.size());
    counter_ = 0;
  }
  const size_t non_shared = key.size() - shared;

  // 下面两部分详细表示了 record 的格式
  
  // Add "<shared><non_shared><value_size>" to buffer_
  PutVarint32(&buffer_, shared);
  PutVarint32(&buffer_, non_shared);
  PutVarint32(&buffer_, value.size());

  // Add string delta to buffer_ followed by value
  buffer_.append(key.data() + shared, non_shared);
  buffer_.append(value.data(), value.size());

  // Update state
  last_key_.resize(shared);
  last_key_.append(key.data() + shared, non_shared);
  assert(Slice(last_key_) == key);
  counter_++;
}
```

### Index Block

Index Block 也是一个普通的 Block，其数据存储方式和数据 Block 没有区别，也是以 Record 为单位，不过其 block_restart_interval 的值为 1（即没有前缀压缩），在 TableBuilder::Rep 初始化的时候会设置 index_block_options.block_restart_interval 为 1。

Index Block 中存储的是当前 sstable 中每个 data block 的最大值，以及 offset 和 size，可以方便定位到一个 block。

TableBuilder::Rep 中与 Index Block 相关的 field 如下：

```cpp
struct TableBuilder::Rep {
  Options index_block_options;
  BlockBuilder data_block;
  BlockBuilder index_block;
  std::string last_key;

  // We do not emit the index entry for a block until we have seen the
  // first key for the next data block.  This allows us to use shorter
  // keys in the index block.  For example, consider a block boundary
  // between the keys "the quick brown fox" and "the who".  We can use
  // "the r" as the key for the index block entry since it is >= all
  // entries in the first block and < all entries in subsequent
  // blocks.
  //
  // Invariant: r->pending_index_entry is true only if data_block is empty.
  bool pending_index_entry;
  BlockHandle pending_handle;  // Handle to add to index block
};
```

* **last_key** 表示当前 data block 的最大值（最后一个值）
* **pending_handle** 表示当前待写入的 data block 的 offset 和 size 信息，在每次写入 data block 的时候会更新（TableBuilder::WriteBlock()）



index block 的写入也是调用 Block::Add() 函数完成的，和 data block 没有区别，只是 data block 的 kv 是用户写入的 kv，index 的 kv 是 last_key 和 BlockHandle 信息。

```cpp
  if (r->pending_index_entry) {
    assert(r->data_block.empty());
    r->options.comparator->FindShortestSeparator(&r->last_key, key);
    std::string handle_encoding;
    r->pending_handle.EncodeTo(&handle_encoding);
    r->index_block.Add(r->last_key, Slice(handle_encoding));
    r->pending_index_entry = false;
  }
```

### Footer

Footer 包括两个 BlockHandler 和 一个 8Byte 的 magic number，固定大小 48 Bytes，因为 offset 和 size 都是 varint64 编码的，如果总大小小于 48 Bytes，剩余部分填 0。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220504223013839.png" alt="image-20220504223013839" style="zoom:33%;" />

```cpp
// Footer encapsulates the fixed information stored at the tail
// end of every table file.
class Footer {
 public:
  // Encoded length of a Footer.  Note that the serialization of a
  // Footer will always occupy exactly this many bytes.  It consists
  // of two block handles and a magic number.	
  enum { kEncodedLength = 2 * BlockHandle::kMaxEncodedLength + 8 };

 private:
  BlockHandle metaindex_handle_;
  BlockHandle index_handle_;
};
```

### Open

打开一个 sstable 文件分为以下几步：

1. 读取并解析 Footer

   ```cpp
     char footer_space[Footer::kEncodedLength];
     Slice footer_input;
     Status s = file->Read(size - Footer::kEncodedLength, Footer::kEncodedLength, &footer_input, footer_space);
     if (!s.ok()) return s;
   
     Footer footer;
     s = footer.DecodeFrom(&footer_input);
   ```

2. 根据 Footer 的 index_handle_ 信息读取 index block 的数据

   ```cpp
     // Read the index block
     BlockContents index_block_contents;
     ReadOptions opt;
     if (options.paranoid_checks) {
       opt.verify_checksums = true;
     }
     s = ReadBlock(file, opt, footer.index_handle(), &index_block_contents);
   ```

3. 构建 index block 信息以及 Table

   ```cpp
     if (s.ok()) {
       // We've successfully read the footer and the index block: we're
       // ready to serve requests.
       Block* index_block = new Block(index_block_contents);
       Rep* rep = new Table::Rep;
       rep->options = options;
       rep->file = file;
       rep->metaindex_handle = footer.metaindex_handle();
       rep->index_block = index_block;
       rep->cache_id = (options.block_cache ? options.block_cache->NewId() : 0);
       rep->filter_data = nullptr;
       rep->filter = nullptr;
       *table = new Table(rep);
       (*table)->ReadMeta(footer);
     }
   ```

### Get

调用关系：DBImpl::Get() -> Version::Get() -> TableCache::Get() -> Table::InternalGet()，其中 handle_result 的回调函数是 SaveValue。

其主要逻辑分为两步：

1. 根据 index block 定位到 data block
2. 在 data block 中查找

```cpp
Status Table::InternalGet(const ReadOptions& options, const Slice& k, void* arg,
                          void (*handle_result)(void*, const Slice&,
                                                const Slice&)) {
  // 1. 在 index block 中根据 key 二分查找找到第一个大于等于 key 的位置
  // 因为 index block 的 key 是每个 block 的 max_key，因此这里实际上是定位到了
  // k 可能存在的 block，接下来还需要进一步在 block 中查找该 k
  Status s;
  Iterator* iiter = rep_->index_block->NewIterator(rep_->options.comparator);
  iiter->Seek(k);
  if (iiter->Valid()) {
    Slice handle_value = iiter->value();
    FilterBlockReader* filter = rep_->filter;
    BlockHandle handle;
    // 2.1 如果有 fliter，并且判断出 k 不存在，那么就真的不存在了
    if (filter != nullptr && handle.DecodeFrom(&handle_value).ok() &&
        !filter->KeyMayMatch(handle.offset(), k)) {
      // Not found
    } else {
      // 2.2 否则读取 k 可能存在的 data block 的数据
      Iterator* block_iter = BlockReader(this, options, iiter->value());
      // 3. 在 data block 中搜索 k, 如果找到了就执行 handle 回调函数
      block_iter->Seek(k);
      if (block_iter->Valid()) {
        (*handle_result)(arg, block_iter->key(), block_iter->value());
      }
      s = block_iter->status();
      delete block_iter;
    }
  }
  if (s.ok()) {
    s = iiter->status();
  }
  delete iiter;
  return s;
}
```

### Iterator

对 sstable 的遍历通过 TwoLevelIterator 实现，TwoLevelIterator 实际上是一个支持根据 index block 遍历所有 data block 的结构。

```cpp
class TwoLevelIterator : public Iterator {
 public:
  TwoLevelIterator(Iterator* index_iter, BlockFunction block_function,
                   void* arg, const ReadOptions& options);
  
 private:
  void InitDataBlock();

  BlockFunction block_function_;
  void* arg_;
  const ReadOptions options_;
  Status status_;
  IteratorWrapper index_iter_;
  IteratorWrapper data_iter_;  // May be nullptr
  // If data_iter_ is non-null, then "data_block_handle_" holds the
  // "index_value" passed to block_function_ to create the data_iter_.
  std::string data_block_handle_;
};
```

**data_iter_** 初始值是 nullptr，在每次根据 index_iter 拿到 data block 的信息后会创建一个新的 data block iter。

```cpp
void TwoLevelIterator::InitDataBlock() {
  if (!index_iter_.Valid()) {
    SetDataIterator(nullptr);
  } else {
    Slice handle = index_iter_.value();
    if (data_iter_.iter() != nullptr &&
        handle.compare(data_block_handle_) == 0) {
      // data_iter_ is already constructed with this iterator, so
      // no need to change anything
    } else {
      Iterator* iter = (*block_function_)(arg_, options_, handle);
      data_block_handle_.assign(handle.data(), handle.size());
      SetDataIterator(iter);
    }
  }
}
```

## Manifest

Manifest 文件以增量的方式持久化版本信息，DB 中可能包含多个 Manifest 文件，需要 Current 文件来指向最新的 Manifest。

Manifest 包含了多条 Record，第一条是 Snapshot Record，记录了 DB 初始的状态；之后的每条 Record 记录了从上一个版本到当前版本的变化，具体格式如下图：

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-898aa363e0c914db369bb223e01abb37_1440w.jpg" alt="img" style="zoom:50%;" />

每次做完 Minor Compaction、Major Compaction 或者重启 Replay 日志生成新的 Level0 文件，都会触发版本变更。

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

5. 判断是否可以直接写或者需要生成新的 mem_table 或是刷 imm_memtable（MakeRoomForWrite()）

   1. 如果 LEVEL 0 的文件数目超过了 8 (`kL0_SlowdownWritesTrigger`)，则 sleep 进行 delay（该 delay 只会发生一次）
   2. 如果当前 memtable 的 size 未达到阈值 write_buffer_size (默认 4MB)，则允许这次写
   3. 如果 memtable 已经达到阈值，但 immutable memtable 仍存在，则等待 compact 将其 dump 完成
   4. 如果 LEVEL 0 的文件数目达到 12 (`kL0_StopWritesTrigger`) 阈值，则等待 compact memtable 完成
   5. 上述条件都不满足，则是 memtable 已经写满，并且 immutable memtable 不存在，则将当前 memtable 置为 immutable memtable，生成新的 memtable 和 log file，主动触发 compact， 允许该次写

6. 从当前待写队列中取出 Writer 构建新的 WriteBatch，有大小限制（`BuildBatchGroup()`）

7. 设置当前 WriteBatch 的 SequnceNumber 为 last_sequence + 1（注意：==这里一个 WriteBatch 都是同一个 SequnceNumber，而且这个 WriteBatch 可能对应上层的多个单独的 Put 操作==）

8. 将 WriteBatch 中的数据写到 log（`Log::AddRecord()`）

9. 将 WriteBatch 应用在 memtable 上。（`WriteBatchInternal::InsertInto()`）,即遍历 decode 出 WriteBatch 中的 key/value/ValueType，根据 ValueType 对 memetable 进行 put/delete 操作

10. 更新 Version::SequnceNumber（`last_sequnce + WriteBatch::count()`）

11. 唤醒当前已经写入完成的 Writer，如果这一批没有把队列中的所有数据写完，还要唤醒队列中第一个 Writer

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

### Version::Get

由于Level0 之间的 SST 文件可能会有 Key Overlap，Level1~N 之间的 SST 文件不会有 Key Overlap，所以查找 sstable 时 L0 需要遍历，其他 Level 二分查找。

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



# Recovery



# Compction

LevelDB 的写入和删除都是追加写 WAL，所以需要 Compaction 来删除那些重复的、过期的、待删除的 KV 数据，同时也可以加速读的作用。



LevelDB 中有三类 Compaction：

* minor compaction：immutable memtable 持久化为 sstable
* major compaction：sstable 之间的 compaction，多路归并排序
* manual compaction：外部调用 CompactRange 产生的 Compaction

其中 major compaction 有两类：

* size compaction：根据 level 的大小来触发
* seek compaction：每个 sstable 都有一个 seek miss 阈值，超过了就会触发



LevelDB 在 MaybeScheduleCompaction() -> BackgroundCompaction() 中完成对 compaction 优先级的调度。

具体优先级为：minor > manual > size > seek。

1. 如果 immutable memtable 不为空，则 dump 到 L0 的 sstable（`CompactMemTable()`）
2. 如果 is_manual 为 true 即 manual compaction，则调用 `CompactRange()`
3. 最后调用 `PickCompaction()` 函数，里面会优先进行 size compaction，再进行 seek compaction



调用 MaybeScheduleCompaction() 的地方：

* Open() 的时候
* Get() 的时候发现 sstable 的 miss 数量超过阈值（`Version::UpdateStats()`）
* MakeRoomForWrite() 的时候发现需要生成新的 memtable，然后把老的 memtable 转成 imm memtable，需要进行 minor compaction
* RecordReadSample() // todo

## Minor Compaction

Minor Compaction 由函数 `DBImpl::CompactMemTable()` 完成，主要是两个步骤：

1. 调用 `DBImpl::WriteLevel0Table()` 写入 sstable 文件，同时记录新文件信息到 VersionEdit 中
2. 生成新的 Version 并更新 Manifest 文件（`VersionSet::LogAndApply()`）



当 immutable memtable 持久化为 sstable 的时候，大多数情况下都会放在 L0，然后并不是所有的情况都会放在 L0，具体放在哪一层由 `Version::PickLevelForMemTableOutput()` 函数计算。

理论上应该需要将 dump 的 sstable 推至高 level，因为 L0 文件过多会导致**查找耗时增加**以及 **compaction 时内部 IO 消耗严重**；

但是又不能推至太高的 level，因为需要控制查找的次数，而且某些范围的 key 更新频繁时，往高 level compaction **内部 IO 消耗严重**，而且也不易 compaction 到高 level，导致**空间放大严重**。

所以 `Version::PickLevelForMemTableOutput()` 在选择输出到哪个 level 的时候，需要权衡查找效率、compaction IO 消耗以及空间放大，大体策略如下：

1. 最高可推至哪层由 kMaxMemCompactLevel 控制，默认最高 L2。
2. 如果 dump 成的 sstable 和 L0/L1 有重叠，则放到 L0（`Version::OverlapInLevel()`）
3. 如果 dump 成的 sstable 和 L2 有重叠且重叠 sstable 总大小超过 10 * max_file_size，则放在 L0
   1. 因为此时如果放在 L1 会造成 compaction IO 消耗比较大，所以放在 L0，之后和 L1 的 sstable 进行 compaction，减小 sstable 的 key 范围，从而减小下次 compaction 涉及的 sstable 总大小
4. 如果 dump 成的 sstable 和 L3 有重叠且重叠 sstable 总大小超过 10 * max_file_size，则放在 L1

## Major Compaction

### Compaction 执行过程

1. 调用 `VersionSet::PickCompaction()` 函数获取需要参加 compaction 的 sstable。

2. 如果不是 manual 且可以 TrivialMove，则直接将 sstable 逻辑上移动到下一层。当且仅当 level i 的 sstable 个数为 1，level i+1 的 sstable 个数为 0，且该sstable 与 level i+2 层重叠的总大小不超过10 * max_file_size。

3. 获取 smallest_snapshot 作为 sequence_number。如果有 snapshot 则使用所有 snapshot 中最小的 sequence_number，否则使用当前 version 的 sequence_number。

4. 生成 MergingIterator 对参与 compaction 的 sstable 进行多路归并排序。

5. 依次处理每对 KV，把有效的 KV 数据通过 TableBuilder 写入到 level+1 层的 sstable 中。

6. 1. 期间如果有 immu memtable，则优先执行 minor compaction。

   2. 重复的数据直接跳过，具体细节处理如下：

   3. 1. 如果有 snapshot，则保留大于 smallest_snapshot 的所有的 record 以及一个小于 smallest_snapshot 的 record。
      2. 如果没有 snapshot，则仅保留 sequence_number 最大的 record。

   4. ==有删除标记的数据则**判断 level i+2 以上层有没有该数据**，有则保留，否则丢弃==。

7. `InstallCompactionResults()` 将本次 compaction 产生的 VersionEdit 调用 `VersionSet::LogAndApply()` 写入到 Manifest 文件中，期间会创建新的Version 成为 Current Version。

8. `CleanupCompaction()`以及调用 `DeleteObsoleteFiles()` 删除不属于任何 version 的 sstable 文件以及 WAL、Manifest 文件。

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



**关于 MergingIterator**：

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

### Seek Compaction

在 levelDB 中，每一个新的 sst 文件，都有一个 allowed_seek 的初始阈值，表示最多容忍 seek miss 次数，每个调用 Get seek miss 的时候，就会执行减 1（allowed_seek--）。其中 allowed_seek 的初始阈值的计算方式为：

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

LevelDB 认为如果一个 sst 文件在 level i 中总是没找到，而是在 level i+1 中找到，这说明两层之间 key 的范围重叠很严重。当这种 seek miss 积累到一定次数之后，就考虑将其从 level i 中合并到 level i+1 中，这样可以避免不必要的 seek miss 消耗 read I/O。



在 Version 中记录了相关的信息：

```cpp
  // Next file to compact based on seek stats.
  FileMetaData* file_to_compact_;
  int file_to_compact_level_;
```

### Size Compaction

Size Compaction 是 levelDB 的核心 Compact 过程，其主要是为了均衡各个 level 的数据， 从而保证读写的性能均衡。

在 Version 中记录了下次需要 compaction 的信息：

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
     > 2. The files in level-0 are merged on every read and therefore we wish to avoid too many files when the individual file size is small (perhaps because of a small write-buffer setting, or very high compression ratios, or lots of overwrites/deletions).

2. 当进行 Compation 时，判断上面的得分是否 >1，如果是则进行 Size Compaction（`VersionSet::PickCompaction()`）

### Pick SSTable

选取哪些 sstable 进行 compaction 在 `VersionSet::PickCompaction()` 函数中实现：

1. 选取 level i 上需要 compaction 的文件，即 `Compaction::inputs_[0]`

   1. 对于 SizeCompaction 来说，计算 score 的同时也会记录 compaction_level_ 信息。每个 level 都有一个 string 类型的 compact_pointer 来判断需要从该 level 的那个位置开始 compaction（即上次 compaction 结束的位置），选取 compact_pointer_[level] 的下一个 sstable 作为初始的文件。

      ```cpp
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

   2. 对于 Seek Compaction 来说，直接记录了需要 Compaction 的文件信息

      ```cpp
        } else if (seek_compaction) {
          level = current_->file_to_compact_level_;
          c = new Compaction(options_, level);
          c->inputs_[0].push_back(current_->file_to_compact_);
      ```

   3. 另外，对于 L0 的 compaction，因为文件可能有 Overlap，所以需要把和上面 inputs_[0] 所有有 overlap 的 sstable 加入到待 compaction 的文件列表中

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

   4. 此外，这里修复过一个 bug：https://github.com/google/leveldb/pull/339

      **BUG 的产生**：随着 compaction 的不断进行，在有 snapshot 的情况下，可能会导致每一层中有许多按照 sequence number 排序的 user_key 相同的record，如果这些 record 比较多或者对应的 value 比较大，那么这些 record 就会被分散保存到相邻的 sstable，从而导致把较新的 record compaction 到下层了，但是这些老的 record 还在上层。

      <img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-cc40d2b357f0d40da4c6c049da587b9e_1440w.jpg" alt="img" style="zoom: 67%;" />

      **BUG 修复**：会调用 `VersionSet::AddBoundaryInputs()` 函数添加同层的有和当前选取的 sstable 的 largest_key 的 user_key 相等的其他 sstable 参与 compaction。

2. 选取 level i + 1 上需要 compaction 的文件，即 `Compaction::inputs_[1]`

   根据 level i 上选取出的 sstable，确定其 [smallest, largest]，然后选出 level i+1 上与其有重叠的所有 sstable（`VersionSet::SetupOtherInputs()`）

   ```cpp
     GetRange(c->inputs_[0], &smallest, &largest);
     current_->GetOverlappingInputs(level + 1, &smallest, &largest, &c->inputs_[1]);
   ```

3. **==扩展 level i 上的 sstable==**

   在已经选取的 level i+1 的 sstable 数量不变的情况下，尽可能的增加 level i 中参与 compaction 的 sstable 数量，总的参与 compaction 的 sstable 的大小阈值为 25 * max_file_size。

   计算出 level i 和 level i+1 的 [smallest, largest]，然后计算出和 level i 上有哪些 sstable 重叠，如果 level i 上新增的 sstable 不会与 level i+1 上的非compaction 的 sstable 重叠，则加入此次 compaction。（即一次尽可能把更多的 level i 推向 level i + 1）

   <img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-4cc6c6694069021a2761fe2faa1f40ea_1440w.jpg" alt="img" style="zoom:67%;" />

## Manual Compaction



# Links

1. https://github.com/google/leveldb/blob/main/doc/index.md
2. https://zhuanlan.zhihu.com/p/360345923
3. https://zhuanlan.zhihu.com/p/80684560