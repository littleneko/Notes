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

SkipList 插入和查找节点时需要自定义 Comparator，MemTable 初始化时使用 `MemTable::KeyComparator` 作为 SkipList 的 Comparator。`MemTable::KeyComparator` 接受 SkipList Node 数据作为其参数，比较流程是先取出 SkipList Node 中的 InternalKey，然后调用 InternalKeyComparator 的 Compare 方法（先比较 user_key，相同时再比较 SequenceNumber）。

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

首先，SkipList Seek 的语义是找到==第一个**大于等于**给定 Key 的节点==，等于肯定是找到了 user_key 和 SequenceNumber 都相等的记录，大于分为两种情况：

* 没找到给定的 memtable_key 中的 user_key，此时返回的是第一个比 user_key 大的 key
* ==找到了给定的 memtable_key 中的 user_key，但是 SequenceNumber 比 memtable_key 中的要小（InternalKeyComparator 中 SequenceNumber 逆序排序），也就是找到了一个比指定 SequenceNumber 版本旧的数据==。（可能会有比指定版本更大版本的数据存在）

因此，在 `MemTable::Get()` 实现中，当在 SkipList 中 Seek 返回 `iter.Valid()` 的情况下还需要再次比较 user_key 是否相等（排除第一种情况），而不需要比较 SequenceNumber 是否相等。

综上所述，==**MemTable::Get() 的语义是返回指定 user_key 小于等于 SequenceNumber 的最大版本的值**==。

> **Tips**:
>
> 在实际的使用中，调用 `MemTable::Get()` 的时候传入的 SequenceNumber 只有两种情况：Snapshot 的 SequenceNumber 和 当前系统最新的 SequenceNumber，前者是查找特定版本的数据，后者是查找最新的 user_key 的数据。（@see: DBImpl::Get()）

# Links

1. https://github.com/google/leveldb/blob/main/doc/index.md
2. https://zhuanlan.zhihu.com/p/360345923
3. https://zhuanlan.zhihu.com/p/80684560