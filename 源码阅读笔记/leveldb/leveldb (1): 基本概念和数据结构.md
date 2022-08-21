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

leveldb 更新（put/delete）某个 key 时不会操控到 DB 中原有的数据，每次操作都是直接新插入一份 KV 数据，具体的数据合并和清除由后台的 Compact 完成。所以每次 put，DB 中就会新加入一份 KV 数据， 即使该 key 已经存在；而 delete 等同于 put 空的 Value。为了区分真实 KV 数据和删除操作的 Mock 数据，使用 ValueType 来标识。

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

db 内部操作的 key。db 内部需要将 user key 加入元信息（ValueType/SequenceNumber）一并做处理。

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

db 内部包装易用的结构，包含 user key 与 SequnceNumber/ValueType。

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

排序时，会先使用 user_comparator 比较 user_key，如果 user_key 相同，则比较 SequnceNumber，SequnceNumber 大的为小。==因为 SequnceNumber 在 db 中全局递增，所以对于相同的 user_key，最新的更新（SequnceNumber 更大）排在前面，在查找的时候会被先找到==。 

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

InternalKeyComparator 中 FindShortestSeparator()/ FindShortSuccessor() 的实现，仅从传入的内部 key 参数，解析出 user_key，然后再调用 user_comparator 的对应接口。

## WriteBatch

对若干数目 key 的 write 操作（put/delete）封装成 WriteBatch。它会将 userkey 连同 SequnceNumber 和 ValueType 先做 encode，然后做 decode，将数据 insert 到指定的 Handler (memtable) 上面。上层的处理逻辑简洁，但 encode/decode 略有冗余。

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

整个 db 的当前状态被 VersionSet 管理着，其中有当前最新的 Version 以及其他正在服务的 Version 链表；全局的 SequnceNumber、FileNumber；当前的 manifest_file_number；封装 sstable 的 TableCache；每个 level 中下一次 compact 要选取的 start_key 等等。

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

当一个 MemTable 大小达到阈值后，将会变成 Immutable MemTable，同时生成一个新的 MemTable 来支持新的写入，Compaction 线程将 Immutable MemTable Flush 到 L0/L1/… 上。所以在LevelDB中，同时最多只会存在两个 MemTable：一个可写的，一个只读的。

### 数据格式

由于 SkipList 是链表形式的，所以我们需要把 KV 数据的映射形式转换成该形式，如图所示，[start, node_end] 区间就代表一个 SkipList Node。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-00a21206a818ce6d3a9ae0d35b9e0363_1440w.jpg" alt="img" style="zoom:50%;" />

### Comparator

SkipList 插入和查找节点时需要自定义 Comparator，MemTable 初始化时使用 MemTable::KeyComparator 作为 SkipList 的 Comparator。MemTable::KeyComparator 接受 SkipList Node 数据作为其参数，比较流程是先取出 SkipList Node 中的 InternalKey，然后调用 InternalKeyComparator 的 Compare 方法（先比较 user_key，相同时再比较 SequenceNumber）。

```c++
static Slice GetLengthPrefixedSlice(const char* data) {
  uint32_t len;
  const char* p = data;
  p = GetVarint32Ptr(p, p + 5, &len);  // +5: we assume "p" is not corrupted
  return Slice(p, len);
}

int MemTable::KeyComparator::operator()(const char* aptr,
                                        const char* bptr) const {
  // Internal keys are encoded as length-prefixed strings.
  Slice a = GetLengthPrefixedSlice(aptr);
  Slice b = GetLengthPrefixedSlice(bptr);
  return comparator.Compare(a, b);
}
```

### Add/Get

Add 接口很简单，主要是生成如上图所示的 SkipList Node 格式，然后调用 `SkipList::Insert()` 插入到 SkipList 中。



Get 的步骤稍微复杂一些，分为两步：

1. 根据 memtable_key 在 SkipList 中 Seek
2. 如果找到的 SkipList Node 的 user_key 相等，就算找到，==不需要比较 SequenceNumber 是否相等==；否则出错

首先，Seek 的语义是找到==第一个**大于等于**给定 Key 的节点==，等于的情况肯定是找到了，大于分为两种情况：

* 没找到给定的 memtable_key 中的 user_key，简单来说就是没找到
* ==找到了给定的 memtable_key 中的 user_key，但是 SequenceNumber 比 memtable_key 中的要小（InternalKeyComparator 中 SequenceNumber 越小的越大），也就是找到了一个比指定 user_key 的版本更小的数据==。（可能会有比指定版本更大版本的数据存在）

综上所述，==**MemTable::Get() 的语义是返回指定 user_key 小于等于 SequenceNumber 的最大版本的值**==。

因此，在 `iter.Valid()` 的情况下还需要再次比较 user_key 是否相等，而不需要比较 SequenceNumber 是否相等。

> **Tips**:
>
> 在实际的使用中，调用 MemTable::Get() 的时候传入的 SequenceNumber 只有两种情况：Snapshot 的 SequenceNumber 和 当前系统最新的 SequenceNumber，前者是查找特定版本的数据，后者是查找最新的 user_key 的数据。（@see: DBImpl::Get()）

## WAL/LOG

WAL 即 Log，每次数据都会先顺序写到 Log 中，然后再写入 MemTable，可以起到转换随机写为顺序写以及保证 Crash 不丢数据的作用。

一个完整的 Log 由多个固定大小的 block 组成，block 大小默认 32KB；block 由一个或者多个 record 组成。

**相关源码**：db/log_format.h, db/log_reader.h/cc, db/log_writer.h/cc

### LOG Format

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-6d05ad55b349ff12653dd9f1b245e96f_1440w.jpg" alt="img" style="zoom:67%;" />

一个 Record 可以跨越多个 Block。

### Record Format

```
+---------------+-------------+-----------+----------+
|	Checksum(4B)	|	Length(2B)	|	Type(1B)	|	Data		 |
+---------------+-------------+-----------+----------+
```

- checksum：计算 type 和 data 的 crc。
- length：data 的长度，2Byte 可表示 64KB，而 block 为 32KB，刚好够用。
- type：一个 record 可以在一个或者跨越多个 block，类型有 5 种：Full、First、Middle、Last、Zero (预分配连续的磁盘空间用)。
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

## Manifest

Manifest 文件以增量的方式持久化版本信息，DB 中可能包含多个 Manifest 文件，需要 Current 文件来指向最新的 Manifest。

Manifest 包含了多条 Record，第一条是 Snapshot Record，记录了 DB 初始的状态；之后的每条 Record 记录了从上一个版本到当前版本的变化，具体格式如下图：

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-898aa363e0c914db369bb223e01abb37_1440w.jpg" alt="img" style="zoom:50%;" />

每次做完 Minor Compaction、Major Compaction 或者重启 Replay 日志生成新的 Level0 文件，都会触发版本变更。

# Links

1. https://github.com/google/leveldb/blob/main/doc/index.md
2. https://zhuanlan.zhihu.com/p/360345923
3. https://zhuanlan.zhihu.com/p/80684560