# Overview

sstable 相关代码全部在 table 目录中，其中定义了 sstfile 的格式以及读写接口，主要代码如下：

* table.cc/h：sstfile 读取和遍历接口
* table_builder.cc/h block_builder.cc/h：写入和构造 sstfile 接口
* block.cc/h：Block 读取和遍历接口
* format.cc/h：sstfile 相关结构定义

# SST file Format

SST file 由 Block 组成， 整体的格式如下图所示：

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-ca3684deaebf6c6fd10fc6312e8919d1_1440w.jpg" alt="img" style="zoom:67%;" />

- **DataBlock**：存储实际的 kv data。
- MetaBlock：暂时没有使用，不过可将 Filter Block 当成一种特殊的 MetaBlock。
- FilterBlock：用于快速过滤一个 Key 是否在 Block 中（默认使用 BloomFilter，因此只能确定 Key 不在 Block 中）。
- MetaIndexBlock：保存 MetaBlock 的索引信息，目前仅有一行 KV 数据，记录了 FilterBlock 的 name 以及 offset/size。
- **IndexBlock**：保存每个 DataBlock 的 LastKey 和在 SST 文件中的 offset/size。
- Footer：文件末尾固定长度的数据，保存 MetaIndexBlock、IndexBlock 的索引信息。

SSTable 中的 BlockSize 大小默认为 4K，MetaIndex、DataBlock、IndexBlock 都是使用同样的 BlockBuilder 来构建 Block，区别是里面的 KV 数据不同。

DataBlock 中的 KV 是有序存储的，相邻的 key 之间很有可能重复，因此采用==前缀压缩==来存储 key，后一个 key 只存储与前一个 key 不同的部分。==如果所有 key 都这样压缩，那么得到一个完整的 key 需要从 block 的第一个 key 开始遍历，为了避免这种情况，每隔 block_restart_interval（默认 16）个 key 就存储完整的 key，然后 restart 指出的位置就表示该 key 不按前缀压缩，而是完整存储该 key==。

对于 MetaBlock 和 IndexBlock 来说由于相邻 key 差距比较大，所以不开启前缀压缩，即 block_restart_interval 为 1。

> **Tips**:
>
> 打开一个 SSTable 的步骤是：读取 FooterBlock -> 读取 IndexBlock 和 MetaIndexBlock -> 根据 MetaIndexBlock 中记录的 FilterBlock 信息读取 FilterBlock。（ref: Table::Open()）

# 相关数据结构

## BlockHandle

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

## BlockContents

BlockContents 保存一个 Block 的数据，ReadBlock() 函数根据 BlockHandle 中的信息读取一个 Block，然后把数据保存在 BlockContents 中：

```cpp
struct BlockContents {
  Slice data;           // Actual contents of data
  bool cachable;        // True iff data can be cached
  bool heap_allocated;  // True iff caller should delete[] data.data()
};
```

## ReadBlock

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
      if (data != buf) {
        // File implementation gave us pointer to some other data.
        // Use it directly under the assumption that it will be live
        // while the file is open.
        delete[] buf;
        result->data = Slice(data, n);
        result->heap_allocated = false;
        result->cachable = false;  // Do not double-cache
      } else {
        result->data = Slice(buf, n);
        result->heap_allocated = true;
        result->cachable = true;
      }

      // Ok
      break;
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

* 非压缩数据：
  * File Read 的时候没有使用堆上分配的 scratch，在 File 层会保证数据一直可用，不需要 cache
  * File Read 的时候使用了在堆上分配的 scratch，heap_allocated 和 cachable 都是 true
* 压缩数据：必须在堆上分配空间，heap_allocated 和 cachable 都是 true

# Block

Block 即上图中的 DataBlock/MetaBlock/MetaIndexBlockIndexBlock 的抽象，使用 ReadBlock 读取到 Block 的数据到 BlockContents 后，就可以使用该 BlockContents 构造一个 Block 对象了，然后实现对 Block 中每个 Record 遍历的接口（Record 可能是 KV data、Index 等）。

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

* **restart_offset_** 表示 restart 数据的起始位置 offset，计算方法是：

  `restart_offset_ = size_ - (1 + num_restarts) * sizeof(uint32_t);` （即 N 个 4 字节的 restart 和 1 个 4 字节的 num_restarts）

* **size_**：即 BlockContents::data 的 size，不包括 compression_type 和 crc32 的部分

## Iterator

Iter 可以顺序遍历、逆序遍历、根据 key Seek 三种方式访问，其中 Seek 的语义是 “==定位到**第一个大于等于** target 的位置==”，这也是 leveldb 中所有继承自 Iterator 的迭代器的语义。

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

> **Tips**:
>
> Iterator 的定义如下，目前继承自该 Iterator 的对象有：Block::Iter、DBIter、Version::LevelFileNumIterator、MemTableIterator、MergingIterator、TwoLevelIterator，这些 Iter 的 Seek 方法的语义都是定位到第一个大于等于 target 的位置。另外，SkipList 的 Iter 虽然不是继承自该类，但是其 Seek 方法的语义也相同。
>
> ```cpp
> class LEVELDB_EXPORT Iterator {
> public:
> Iterator();
> 
> // An iterator is either positioned at a key/value pair, or
> // not valid.  This method returns true iff the iterator is valid.
> virtual bool Valid() const = 0;
> 
> // Position at the first key in the source.  The iterator is Valid()
> // after this call iff the source is not empty.
> virtual void SeekToFirst() = 0;
> 
> // Position at the last key in the source.  The iterator is
> // Valid() after this call iff the source is not empty.
> virtual void SeekToLast() = 0;
> 
> // Position at the first key in the source that is at or past target.
> // The iterator is Valid() after this call iff the source contains
> // an entry that comes at or past target.
> virtual void Seek(const Slice& target) = 0;
> 
> // Moves to the next entry in the source.  After this call, Valid() is
> // true iff the iterator was not positioned at the last entry in the source.
> // REQUIRES: Valid()
> virtual void Next() = 0;
> 
> // Moves to the previous entry in the source.  After this call, Valid() is
> // true iff the iterator was not positioned at the first entry in source.
> // REQUIRES: Valid()
> virtual void Prev() = 0;
> 
> // ... ...
> }
> ```

### SeekToFirst

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

### 顺序遍历

顺序遍历即调用 Next 进行遍历，ParseNextKey 用于处理下一个 value，可能需要把 restart_index_ 指针移动到下一个位置：

```cpp
  // Return the offset in data_ just past the end of the current entry.
	// 在 SeekToFirst 后, value 的 size 为 0, 所以这里的 offset 算出来是 0
	// 此后, value 表示正常的 record, 该函数返回的是下一个 record 的起始 offset
  inline uint32_t NextEntryOffset() const {
    return (value_.data() + value_.size()) - data_;
  }

	bool ParseNextKey() {
    // 根据上一个 value 大小计算出当前 value 的起始位置
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
      key_.resize(shared); // 保留和前一个 key 相比 shared 部分的 key
      key_.append(p, non_shared); // DecodeEntry 完成后, p 移动到了 nonshared_key 数据的位置
      value_ = Slice(p + non_shared, value_length);
      // 判断当前的 record 是否还在 restart_index_ 表示的 restart group 中, 即需要把 restart_index_ 向后移动, 
      // 如果下一个 restart index 指向的数据的 offset 比当前的数据的 offset 小,
      // 即当前的 record 应该在 restart_index + 1 的 restart group 中,
      // 就需要移动到下一个 restart group
      while (restart_index_ + 1 < num_restarts_ && GetRestartPoint(restart_index_ + 1) < current_) {
        ++restart_index_;
      }
      return true;
    }
  }
};
```

### 逆序遍历

```cpp
  void Prev() override {
    assert(Valid());

    // Scan backwards to a restart point before current_
    const uint32_t original = current_;
    // 当上一次遍历到了 restart group 的第一个元素的时候, 等号成立,
    // 因此需要移动到前一个 restart group. (正常来说是不会大于的)
    while (GetRestartPoint(restart_index_) >= original) {
      if (restart_index_ == 0) {
        // No more entries
        current_ = restarts_;
        restart_index_ = num_restarts_;
        return;
      }
      restart_index_--;
    }

    // 每次都从该 restart group 的第一个元素向后遍历，直到找到上次遍历到的元素(original)的前一个元素
    SeekToRestartPoint(restart_index_);
    do {
      // Loop until end of current entry hits the start of original entry
    } while (ParseNextKey() && NextEntryOffset() < original);
  }
```

> **Tips**:
>
> 从实现上能看到，逆序遍历每次都要从 restart group 的第一个元素向后遍历一遍，效率比正序遍历要差。

### Seek

Seek 的语义是定位到==**第一个大于等于** target 的 key==，Seek 的时候使用传入的自定义 Comparator 进行 key 的比较，默认是 InternalKeyComparator，因此实际上是定位到比给定 key 版本相等或小的最大版本的位置。由于 Block 内的数据是有序的，因此 Seek 可以用==二分查找==的方式。

在 Seek 的实现上有个优化，首先用 target 和当前遍历到的 key 进行比较，缩小二分查找的 left 或 right 范围。



==二分查找的对象是 restart array==，目的是找到==**最大**的 restart point 满足 key < target==（https://github.com/google/leveldb/issues/109）。

```cpp
    while (left < right) {
      uint32_t mid = (left + right + 1) / 2;
      uint32_t region_offset = GetRestartPoint(mid);
      uint32_t shared, non_shared, value_length;
      const char* key_ptr =
          DecodeEntry(data_ + region_offset, data_ + restarts_, &shared, &non_shared, &value_length);
      if (key_ptr == nullptr || (shared != 0)) {
        CorruptionError();
        return;
      }
      Slice mid_key(key_ptr, non_shared);
      if (Compare(mid_key, target) < 0) {
        // Key at "mid" is smaller than "target".  Therefore all
        // blocks before "mid" are uninteresting.
        left = mid;
      } else {
        // Key at "mid" is >= "target".  Therefore all blocks at or
        // after "mid" are uninteresting.
        right = mid - 1;
      }
    }
```

接着从找到的 key 的位置（left）向后遍历，直到找到 first key >= target。

```cpp
    // We might be able to use our current position within the restart block.
    // This is true if we determined the key we desire is in the current block
    // and is after than the current key.
    assert(current_key_compare == 0 || Valid());
    bool skip_seek = left == restart_index_ && current_key_compare < 0;
    if (!skip_seek) {
      SeekToRestartPoint(left);
    }
    // Linear search (within restart block) for first key >= target
    while (true) {
      if (!ParseNextKey()) {
        return;
      }
      if (Compare(key_, target) >= 0) {
        return;
      }
    }
```

> **Tips**:
>
> 1. 每个 restart group 的第一个 key，保存的都是完整的 key，因此 shared size 应该是 0；然后遍历到下一个 key 的时候，只需要跳过下一个 key 的 shared size，然后 append non_shared 部分即可。
> 2. restart_index_ 的作用：
>    1. 在顺序遍历（Next）的时候，实际上没什么作用，但是仍然要记录下来，目的是为了逆序遍历（Prev）
>    2. 在逆序遍历（Prev）的时候，遍历到一个 restart group 的第一个元素的时候，下一次需要跳到上一个 restart group 的起始位置按顺序遍历，原因是 record 存储的时候做了前缀压缩，必须从一个 restart group 的第一个元素向后遍历。（因此逆序遍历时每次都要从当前 restart group 的第一个元素向后遍历一遍）
>    3. 在 Seek 的时候，同样需要以 restart group 为单位做二分查找。

## Record Format (data/index/…)

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220504221858602.png" alt="image-20220504221858602" style="zoom:50%;" />

Record 实现了前缀压缩，每 block_restart_interval 个 record 重新开始计算压缩前缀。

* shared key size：和==前一个== key 相同的部分的长度
* noshared key size：剩余部分 key 的长度
* value size：value 的长度
* noshared key：noshared key 的数据
* value：value 的数据

Record 格式在上面的图中已经给出，详细读取和写入可以参考 `DecodeEntry()` 和 `BlockBuilder::Add()` 函数的实现。

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

## Index Block

Index Block 也是一个普通的 Block，其数据存储方式和数据 Block 没有区别，也是以 Record 为单位，不过其 *block_restart_interval* 的值为 1（即没有前缀压缩），在 `TableBuilder::Rep` 初始化的时候会设置 index_block_options.block_restart_interval 为 1。

Index Block 中存储的是当前 sstable 中每个 data block 的最大值，以及 offset 和 size，可以方便定位到一个 block。

`TableBuilder::Rep` 中与 Index Block 相关的 field 如下：

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



index block 的写入也是调用 `Block::Add()` 函数完成的，和 data block 没有区别，只是 data block 的 kv 是用户写入的 kv，index 的 kv 是 last_key 和 BlockHandle 信息。

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

## FilterBlock

// TODO

# Footer

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

# Table

leveldb 中用 Table 类表示一个 SSTable，Table 对外提供 Iter 和 Get 接口，并且是线程安全的。

## Init (Open)

静态函数 `Table::Open()` 构造并初始化一个 Table 对象，open 一个 SSTable 文件分为以下几步：

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

## Get (InternalGet)

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
    // index block 的 value 就是 data block 的 offset 和 size
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
      // 3. 在 data block 中找到第一个大于等于 k 的数据, 如果找到了就执行 handle 回调函数
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

前面我们介绍 Iterator 的时候知道，`Iterator::Seek()` 只是找到第一个大于等于给定 Key 的数据，大于的情况可能是 user_key 相等版本更小，也有可能是 user_key 就不相等，因此需要调用者处理，这里是在回调函数（handle_result）中处理的：

```cpp
// file: version.cc

// 从上层传进来的 Saver 的初始 state 是 kNotFound, ref: Version::Get()
static void SaveValue(void* arg, const Slice& ikey, const Slice& v) {
  Saver* s = reinterpret_cast<Saver*>(arg);
  ParsedInternalKey parsed_key;
  if (!ParseInternalKey(ikey, &parsed_key)) {
    s->state = kCorrupt;
  } else {
    // 只有 user_key 相等才算找到
    if (s->ucmp->Compare(parsed_key.user_key, s->user_key) == 0) {
      s->state = (parsed_key.type == kTypeValue) ? kFound : kDeleted;
      if (s->state == kFound) {
        s->value->assign(v.data(), v.size());
      }
    }
  }
}
```

## Read Data by Index (BlockReader)

BlockReader 函数实现了根据 index block 读取 data block 的功能，同时会更新 block cache。

1. 解码出 index value，即指向的 data block 的 offset 和 size（BlockHandle）
2. 如果在 cache 中已经右该 block，就从 cache 中取；否则就读取该 block（ReadBlock）
3. 对该 data block 构造一个 iter 并返回

## Iter (TwoLevelIterator)

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

## SSTable Write

SSTable 的构造和写入主要通过 TableBuilder 和 BlockBuilder 实现，Builder 中实现了对 data block、index block、meta_index block、footer 的写入。

### BlockBuilder

```cpp
void BlockBuilder::Add(const Slice& key, const Slice& value) {
  Slice last_key_piece(last_key_);
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

### TableBuilder

TableBuilder::Rep 持有 data_block 和 index_block 两个 BlockBuilder 对象，用于 DataBlock 和 IndexBlock 的构造：

```cpp
struct TableBuilder::Rep {
  // ... ...
	Options options;
  Options index_block_options;
  WritableFile* file;
  uint64_t offset;
  Status status;
  BlockBuilder data_block;
  BlockBuilder index_block;
  std::string last_key;
  int64_t num_entries;
  bool closed;  // Either Finish() or Abandon() has been called.
  FilterBlockBuilder* filter_block;

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
```

其中，pending_index_entry 表示当前是否构造完并写入了一个 DataBlock，需要写入这个 DataBlock 的 index 信息。

`TableBuilder::Add()` 用于写入一条 kv 数据：

```cpp
void TableBuilder::Add(const Slice& key, const Slice& value) {
  Rep* r = rep_;

  // 向 index block 中写入一条 index 数据
  if (r->pending_index_entry) {
    assert(r->data_block.empty());
    r->options.comparator->FindShortestSeparator(&r->last_key, key);
    std::string handle_encoding;
    r->pending_handle.EncodeTo(&handle_encoding);
    r->index_block.Add(r->last_key, Slice(handle_encoding));
    r->pending_index_entry = false;
  }

  if (r->filter_block != nullptr) {
    r->filter_block->AddKey(key);
  }

  // 保存当前 block 的最大（最新）的 key，并构造 data block
  r->last_key.assign(key.data(), key.size());
  r->num_entries++;
  r->data_block.Add(key, value);

  // 当前 DataBlock 写满后, Flush 写入文件(WriteBlock) 
  const size_t estimated_block_size = r->data_block.CurrentSizeEstimate();
  if (estimated_block_size >= r->options.block_size) {
    Flush();
  }
}
```

注意在写入 index block 数据的时候先调用了 `FindShortestSeparator()` 函数，其两个参数分别为需要写入 index 的 DataBlock 的最大 key，以及现在的 key。并且最终写入 IndexBlock 中的 key 数据并不是原始的 last_key，而是经过 FindShortestSeparator 处理后的 key。

该函数的注释如下解释：

>   // If *start < limit, changes *start to a short string in [start,limit).
>   // Simple comparator implementations may return with *start unchanged,
>   // i.e., an implementation of this method that does nothing is correct.

即找到 start  和 limit 之间最短的字符串，比如 "helloworld" 和 "hellozoomer" 之间最短的字符串是 "hellox"。

因此 IndexBlock 中的 max_key 并不是这个 DataBlock 的最后一个 key，而是介于这个 DataBlock 的 max_key 和 下一个 DataBlock 的 min_key 之间的某一个字符串，这样做的好处是可以减小 IndexBlock 的大小。

同时，这样做并不会影响最终结果的正确性，以上面的 "helloworld" 和 "hellozoomer" 的例子来说，如果要查找的 key 是 "hellowpxxx"，这个 key 显然是不存在的。如果 IndexBlock 中存储的 max_key 是 "helloworld"，会定位到下一个 DataBlock 中查找；如果 IndexBlock 中存储的 max_key 是 "hellox"，会定位到当前 DataBlock 中查找，两种情况都找不到这个