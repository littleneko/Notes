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

- checksum：计算 type 和 data 的 CRC。
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

# Links

1. https://github.com/google/leveldb/blob/main/doc/index.md
2. https://zhuanlan.zhihu.com/p/360345923
3. https://zhuanlan.zhihu.com/p/80684560