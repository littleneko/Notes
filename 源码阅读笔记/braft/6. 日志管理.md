# LogManager
LogManager 中封装了日志写入、Truncate 等操作的相关接口，上层 Node、Replicator、Snapshot 等模块都会直接调用这些接口进行日志操作。下面截取了 LogManager 部分定义：
```cpp
class LogManager {
public:
    class StableClosure : public Closure {
    public:
        StableClosure() : _first_log_index(0) {}
        void update_metric(IOMetric* metric);
    protected:
        int64_t _first_log_index;
        IOMetric metric;
    private:
    friend class LogManager;
    friend class AppendBatcher;
        std::vector<LogEntry*> _entries;
    };
  
    // Append log entry vector and wait until it's stable (NOT COMMITTED!)
    // success return 0, fail return errno
    void append_entries(std::vector<LogEntry*> *entries, StableClosure* done);

    // Notify the log manager about the latest snapshot, which indicates the
    // logs which can be safely truncated.
    BRAFT_MOCK void set_snapshot(const SnapshotMeta* meta);

    // We don't delete all the logs before last snapshot to avoid installing
    // snapshot on slow replica. Call this method to drop all the logs before
    // last snapshot immediately.
    BRAFT_MOCK void clear_bufferred_logs();

    // Get the log at |index|
    // Returns:
    //  success return ptr, fail return null
    LogEntry* get_entry(const int64_t index);
  
    // Set the applied id, indicating that the log before applied_id (inclded)
    // can be droped from memory logs
    void set_applied_id(const LogId& applied_id);
  
private:
    void append_to_storage(std::vector<LogEntry*>* to_append, LogId* last_id, IOMetric* metric);

    // _disk_queue 的回调函数
    static int disk_thread(void* meta, bthread::TaskIterator<StableClosure*>& iter);
    
    // delete logs from storage's head, [1, first_index_kept) will be discarded
    // Returns:
    //  success return 0, failed return -1
    int truncate_prefix(const int64_t first_index_kept, std::unique_lock<raft_mutex_t>& lck);
    
    int reset(const int64_t next_log_index, std::unique_lock<raft_mutex_t>& lck);

    // Must be called in the disk thread, otherwise the
    // behavior is undefined
    void set_disk_id(const LogId& disk_id);

    LogEntry* get_entry_from_memory(const int64_t index)；
      
    int check_and_resolve_conflict(std::vector<LogEntry*>* entries, StableClosure* done);

    void unsafe_truncate_suffix(const int64_t last_index_kept);

    // Clear the logs in memory whose id <= the given |id|
    void clear_memory_logs(const LogId& id);
  
    
    LogStorage* _log_storage;
    ConfigurationManager* _config_manager;
    FSMCaller* _fsm_caller;
  
    LogId _disk_id;
    LogId _applied_id;
    // TODO(chenzhangyi01): replace deque with a thread-safe data structure
    std::deque<LogEntry* /*FIXME*/> _logs_in_memory;
    int64_t _first_log_index;
    int64_t _last_log_index;
    // the last snapshot's log_id
    LogId _last_snapshot_id;
    // the virtual first log, for finding next_index of replicator, which 
    // can avoid install_snapshot too often in extreme case where a follower's
    // install_snapshot is slower than leader's save_snapshot
    // [NOTICE] there should not be hole between this log_id and _last_snapshot_id,
    // or may cause some unexpect cases
    LogId _virtual_first_log_id;

    bthread::ExecutionQueueId<StableClosure*> _disk_queue;
}
```
LogManager 最终是通过 LogStorage 操作 log 的，LogStorage 是一个抽象类，braft 中有两个实现：MemoryLogStorage 和 SegmentLogStorage，我们主要关注后者。


_disk_queue 是一个 Wait-Free 的任务处理队列，其回调函数是 `LogManager::disk_thread()` ，对于写 log 类型的任务，会直接调用 AppendBatcher 进行日志的写入；对于非写 log 类型的任务，会依次尝试把 StableClosure cast 为其子类，然后执行子类对应的函数。简化后的实现如下：


```cpp
int LogManager::disk_thread(void* meta, bthread::TaskIterator<StableClosure*>& iter) {
    LogManager* log_manager = static_cast<LogManager*>(meta);
    // FIXME(chenzhangyi01): it's buggy
    LogId last_id = log_manager->_disk_id;
    StableClosure* storage[256];
    AppendBatcher ab(storage, ARRAY_SIZE(storage), &last_id, log_manager);
    
    for (; iter; ++iter) {
        StableClosure* done = *iter;
        done->metric.bthread_queue_time_us = butil::cpuwide_time_us() - done->metric.start_time_us;
        // 写 log 的任务
        if (!done->_entries.empty()) {
            ab.append(done);
        } else {
        	// 其他类型的任务
            ab.flush();
            int ret = 0;
            // 分别处理 4 种不同类型的任务
            do {
                LastLogIdClosure* llic = dynamic_cast<LastLogIdClosure*>(done);
                if (llic) {
                    // Not used log_manager->get_disk_id() as it might be out of date
                    // FIXME: it's buggy
                    llic->set_last_log_id(last_id);
                    break;
                }
              
                TruncatePrefixClosure* tpc = dynamic_cast<TruncatePrefixClosure*>(done);
                if (tpc) {
                    ret = log_manager->_log_storage->truncate_prefix(tpc->first_index_kept());
                    break;
                }
              
                TruncateSuffixClosure* tsc = dynamic_cast<TruncateSuffixClosure*>(done);
                if (tsc) {
                    ret = log_manager->_log_storage->truncate_suffix(tsc->last_index_kept());
                    if (ret == 0) {
                        // update last_id after truncate_suffix
                        last_id.index = tsc->last_index_kept();
                        last_id.term = tsc->last_term_kept();
                        CHECK(last_id.index == 0 || last_id.term != 0)
                                << "last_id=" << last_id;
                    }
                    break;
                }
              
                ResetClosure* rc = dynamic_cast<ResetClosure*>(done);
                if (rc) {
                    ret = log_manager->_log_storage->reset(rc->next_log_index());
                    break;
                }
            } while (0);

            if (ret != 0) {
                log_manager->report_error(ret, "Failed operation on LogStorage");
            }
            done->Run();
        }
    }
    CHECK(!iter) << "Must iterate to the end";
    ab.flush();
    log_manager->set_disk_id(last_id);
    return 0;
}
```


> **Tips**:
> ExecutionQueue is a special wait-free MPSC queue of which the consumer thread is auto started by the execute operation and auto quits if there are no more tasks, in another word there isn't a daemon bthread waiting to consume tasks.



`StableClosure` 是 `bthread::ExecutionQueue` 的回调类型，在 LogManger 中用到了以下 4 种子类：

- LastLogIdClosure
- TruncatePrefixClosure
- TruncateSuffixClosure
- ResetClosure



LogManager 相关 field 初始化：
```cpp
int LogManager::init(const LogManagerOptions &options) {
		// ... ...
	_first_log_index = _log_storage->first_log_index();
    _last_log_index = _log_storage->last_log_index();
    _disk_id.index = _last_log_index;
    // Term will be 0 if the node has no logs, and we will correct the value
    // after snapshot load finish.
    _disk_id.term = _log_storage->get_term(_last_log_index);
}
```
## 写日志
写 raft 日志主要由两个函数实现：`append_entries()`  和 `append_to_storage()` ，前者更新内存缓存并把任务加到 `_disk_queue`  中，后者执行从 `_disk_queue` 中取出的写任务，最终调用 LosStorage 执行实际的写日志操作。
```cpp
void append_entries(std::vector<LogEntry*> *entries, StableClosure* done);
    
void append_to_storage(std::vector<LogEntry*>* to_append, LogId* last_id, IOMetric* metric);
```


`append_entries()` 流程：

1.  检查并处理全局 error（`_has_error`） 
1.  检查日志冲突（`check_and_resolve_conflict()`）： 
   1. 当前 Node 是 Leader，为 LogEntry 分配 index：`(*entries)[i]->id.index = ++_last_log_index;` （注意这里递增了 _last_log_index）
   1. 当前 Node 是 follower，表示 LogEntry 是从 leader 处收到的，We should check and resolve the confliction between the local logs and |entries|
3.  处理 ENTRY_TYPE_CONFIGURATION 类型的 LogEntry 
3.  LogEntry 加到本地缓存 _logs_in_memory 中 
3.  写日志任务提交到 _disk_queue 中  
```cpp
done->_entries.swap(*entries);
int ret = bthread::execution_queue_execute(_disk_queue, done);
```

6. `LogManager::disk_thread()` 执行 _disk_queue 中的写日志任务




---

`check_and_resolve_conflict()` 中对于从 Leader 收到的日志，分为以下几种情况处理：

1. 有 Gap（`entries->front()->id.index > _last_log_index + 1`）：返回错误
1. 是已经 apply 的日志（`entries->back()->id.index <= applied_index`）：返回错误
1. 正好接上本地日志（`entries->front()->id.index == _last_log_index + 1`）：通过check，并更新 `_last_log_index = entries->back()->id.index;`
1. 处于 apply 与 _last_log_index 之间：
   1. 比较收到的日志 index 的 term 与本地日志的 term，如果本地日志 term 与收到的日志 term 不一致，以收到的日志为准，truncate 掉本地有冲突的日志（`unsafe_truncate_suffix((*entries)[conflicting_index]->id.index - 1);`），并更新本地  `_last_log_index = entries->back()->id.index;`
   1. 否则表示 this is a duplicated AppendEntriesRequest, we havenothing to do besides releasing all the entries




---

`LogManager::append_entries()` 把任务提交到 _disk_queue 后，`LogManager::disk_thread()` 的处理流程简化为下面的步骤：
```cpp
AppendBatcher ab(storage, ARRAY_SIZE(storage), &last_id, log_manager);
for (; iter; ++iter) {
	if (!done->_entries.empty()) {
		ab.append(done);
	}
	ab.flush();
    log_manager->set_disk_id(last_id);
}
```


`AppendBatcher::flush()` 中会调用 `LogManager::append_to_storage()` 实现日志的写入，`LogManager::append_to_storage()` 主要是调用 `LogStorage::append_entries()` 实现日志的写入，简化后的逻辑如下：
```cpp
void LogManager::append_to_storage(std::vector<LogEntry*>* to_append, 
                                   LogId* last_id, IOMetric* metric) {
    if (!_has_error.load(butil::memory_order_relaxed)) {
        g_storage_append_entries_concurrency << 1;
        int nappent = _log_storage->append_entries(*to_append, metric);
        g_storage_append_entries_concurrency << -1;
        if (nappent != (int)to_append->size()) {
            // FIXME
            LOG(ERROR) << "Fail to append_entries, "
                       << "nappent=" << nappent 
                       << ", to_append=" << to_append->size();
            report_error(EIO, "Fail to append entries");
        }
        if (nappent > 0) { 
            *last_id = (*to_append)[nappent - 1]->id;
        }
    }
    for (size_t j = 0; j < to_append->size(); ++j) {
        (*to_append)[j]->Release();
    }
    to_append->clear();
}
```
## 读日志
读日志通过 LogManager::get_entry() 函数完成，定义如下：
```cpp
LogEntry* get_entry(const int64_t index);
```
其逻辑很简单，首先去 `_logs_in_memory` 读（`get_entry_from_memory()`），没有的话，再直接通过 LogStorage 的接口读。
## Truncate 日志
truncate log 分为 2 种情况：

1. truncate 某一个 index 之前所有的 log，用于清理日志；
1. truncate 某一个 index 之后所有的日志，用于解决冲突。
```cpp
int truncate_prefix(const int64_t first_index_kept, std::unique_lock<raft_mutex_t>& lck);
void unsafe_truncate_suffix(const int64_t last_index_kept);
```


truncate_prefix() 步骤：

1. 清理 _logs_in_memory 中 index 小于 first_index_kept 的日志
1. 更新 `_first_log_index = first_index_kept;`
1. 这里有一个特殊情况，就是 log 全部被 truncate 了（`first_index_kept > _last_log_index`），也要更新一下 `_last_log_index = first_index_kept - 1;`
1. 更新 configure：`_config_manager->truncate_prefix(first_index_kept);`
1. 提交任务到 _disk_queue 中
```cpp
TruncatePrefixClosure* c = new TruncatePrefixClosure(first_index_kept);
const int rc = bthread::execution_queue_execute(_disk_queue, c);
```

6. `LogManager::disk_thread()` 执行 _disk_queue 中的写日志任务，实际上是调用 `LogStorage::truncate_prefix()` 来完成日志的写入。
## Snapshot
// todo
# LogStorage
braft 中实现了 MemoryLogStorage 和 SegmentLogStorage，我们主要关注后者。SegmentLogStorage 是一个以 Segment 为单位组织的日志存储，一个 LogSegment 对应了一个物理的 log 文件。Segment 分为 closed segment 和 open segment：

- closed segment 表示已经完成写入的 log 文件，文件命名规则是 "log_[_first_index]_[_last_index]"；
- open segment 表示正在写入的 segment，文件命名规则是 "log_inprogress_[_first_index]"。

log 以 segment 为单位管理，truncate 也是以 segment 为单位。
​

Segment 存储了 log segment 的元信息，定义了读取、写入、删除等操作：
```cpp
class Segment {
public:
	// create open segment
    int create();

    // load open or closed segment
    // open fd, load index, truncate uncompleted entry
    int load(ConfigurationManager* configuration_manager);

    // serialize entry, and append to open segment
    int append(const LogEntry* entry);

    // get entry by index
    LogEntry* get(const int64_t index) const;

    // get entry's term by index
    int64_t get_term(const int64_t index) const;

    // close open segment
    int close(bool will_sync = true);

    // sync open segment
    int sync(bool will_sync);

    // unlink segment
    int unlink();

    // truncate segment to last_index_kept
    int truncate(const int64_t last_index_kept);
    
private:
    std::string _path;
    int64_t _bytes;
    mutable raft_mutex_t _mutex;
    int _fd;
    bool _is_open;
    const int64_t _first_index;
    butil::atomic<int64_t> _last_index;
    int _checksum_type;
    std::vector<std::pair<int64_t/*offset*/, int64_t/*term*/> > _offset_and_term;
}
```
其中，_first_index 和 _last_index 信息在初始化 LogStorage 时直接从 log 的文件名得到。


```cpp
// LogStorage use segmented append-only file, all data in disk, all index in memory.
// append one log entry, only cause one disk write, every disk write will call fsync().
//
// SegmentLog layout:
//      log_meta: record start_log
//      log_000001-0001000: closed segment
//      log_inprogress_0001001: open segment
class SegmentLogStorage : public LogStorage {
public:
    typedef std::map<int64_t, scoped_refptr<Segment> > SegmentMap;
    
    // init logstorage, check consistency and integrity
    virtual int init(ConfigurationManager* configuration_manager);

    // first log index in log
    virtual int64_t first_log_index() {
        return _first_log_index.load(butil::memory_order_acquire);
    }

    // last log index in log
    virtual int64_t last_log_index();

    // get logentry by index
    virtual LogEntry* get_entry(const int64_t index);

    // get logentry's term by index
    virtual int64_t get_term(const int64_t index);

    // append entry to log
    int append_entry(const LogEntry* entry);

    // append entries to log and update IOMetric, return success append number
    virtual int append_entries(const std::vector<LogEntry*>& entries, IOMetric* metric);

    // delete logs from storage's head, [1, first_index_kept) will be discarded
    virtual int truncate_prefix(const int64_t first_index_kept);

    // delete uncommitted logs from storage's tail, (last_index_kept, infinity) will be discarded
    virtual int truncate_suffix(const int64_t last_index_kept);

    virtual int reset(const int64_t next_log_index);
    
private:
    std::string _path;
    butil::atomic<int64_t> _first_log_index;
    butil::atomic<int64_t> _last_log_index;
    raft_mutex_t _mutex;
    SegmentMap _segments;
    scoped_refptr<Segment> _open_segment;
    int _checksum_type;
    bool _enable_sync;
}
```


_segments 保存了所有 log segment 的元信息，key 是 first_index；_open_segment 是当前打开的 log segment 信息，两个信息都在 `SegmentLogStorage::list_segments()` 中初始化，其中 `first_index` 和 `last_index` 都是直接从文件名中提取得到的。
## 写日志
写日志通过 `Segment::append()` 实现，同时会更新 _last_log_index
### 日志格式
```cpp
int Segment::append(const LogEntry* entry) {
    if (BAIDU_UNLIKELY(!entry || !_is_open)) {
        return EINVAL;
    } else if (entry->id.index != 
                    _last_index.load(butil::memory_order_consume) + 1) {
        CHECK(false) << "entry->index=" << entry->id.index
                  << " _last_index=" << _last_index
                  << " _first_index=" << _first_index;
        return ERANGE;
    }

    butil::IOBuf data;
    switch (entry->type) {
    case ENTRY_TYPE_DATA:
        data.append(entry->data);
        break;
    case ENTRY_TYPE_NO_OP:
        break;
    case ENTRY_TYPE_CONFIGURATION: 
        {
            butil::Status status = serialize_configuration_meta(entry, data);
            if (!status.ok()) {
                LOG(ERROR) << "Fail to serialize ConfigurationPBMeta, path: " 
                           << _path;
                return -1; 
            }
        }
        break;
    default:
        LOG(FATAL) << "unknow entry type: " << entry->type
                   << ", path: " << _path;
        return -1;
    }
    CHECK_LE(data.length(), 1ul << 56ul);
    char header_buf[ENTRY_HEADER_SIZE];
    const uint32_t meta_field = (entry->type << 24 ) | (_checksum_type << 16);
    RawPacker packer(header_buf);
    packer.pack64(entry->id.term)
          .pack32(meta_field)
          .pack32((uint32_t)data.length())
          .pack32(get_checksum(_checksum_type, data));
    packer.pack32(get_checksum(
                  _checksum_type, header_buf, ENTRY_HEADER_SIZE - 4));
    butil::IOBuf header;
    header.append(header_buf, ENTRY_HEADER_SIZE);
    const size_t to_write = header.length() + data.length();
    butil::IOBuf* pieces[2] = { &header, &data };
    size_t start = 0;
    ssize_t written = 0;
    while (written < (ssize_t)to_write) {
        const ssize_t n = butil::IOBuf::cut_multiple_into_file_descriptor(
                _fd, pieces + start, ARRAY_SIZE(pieces) - start);
        if (n < 0) {
            LOG(ERROR) << "Fail to write to fd=" << _fd 
                       << ", path: " << _path << berror();
            return -1;
        }
        written += n;
        for (;start < ARRAY_SIZE(pieces) && pieces[start]->empty(); ++start) {}
    }
    BAIDU_SCOPED_LOCK(_mutex);
    _offset_and_term.push_back(std::make_pair(_bytes, entry->id.term));
    _last_index.fetch_add(1, butil::memory_order_relaxed);
    _bytes += to_write;

    return 0;
}
```
## 读日志
根据 index 找到对应的 Segment，然后读取日志（`Segment::get()`）。
## Truncate 日志
truncate 以 segment 为单位，遍历 segmens，truncate 所有`segment->last_index() < first_index_kept` 的日志，同时会清理 _segments 中保存的 Segment 的元信息。
```cpp
int SegmentLogStorage::truncate_prefix(const int64_t first_index_kept) {
    // segment files
    if (_first_log_index.load(butil::memory_order_acquire) >= first_index_kept) {
      BRAFT_VLOG << "Nothing is going to happen since _first_log_index=" 
                     << _first_log_index.load(butil::memory_order_relaxed)
                     << " >= first_index_kept="
                     << first_index_kept;
        return 0;
    }
    // NOTE: truncate_prefix is not important, as it has nothing to do with 
    // consensus. We try to save meta on the disk first to make sure even if
    // the deleting fails or the process crashes (which is unlikely to happen).
    // The new process would see the latest `first_log_index'
    if (save_meta(first_index_kept) != 0) { // NOTE
        PLOG(ERROR) << "Fail to save meta, path: " << _path;
        return -1;
    }
    std::vector<scoped_refptr<Segment> > popped;
    pop_segments(first_index_kept, &popped);
    for (size_t i = 0; i < popped.size(); ++i) {
        popped[i]->unlink();
        popped[i] = NULL;
    }
    return 0;
}

void SegmentLogStorage::pop_segments(
        const int64_t first_index_kept,
        std::vector<scoped_refptr<Segment> >* popped) {
    popped->clear();
    popped->reserve(32);
    BAIDU_SCOPED_LOCK(_mutex);
    _first_log_index.store(first_index_kept, butil::memory_order_release);
    for (SegmentMap::iterator it = _segments.begin(); it != _segments.end();) {
        scoped_refptr<Segment>& segment = it->second;
        if (segment->last_index() < first_index_kept) {
            popped->push_back(segment);
            _segments.erase(it++);
        } else {
            return;
        }
    }
    if (_open_segment) {
        if (_open_segment->last_index() < first_index_kept) {
            popped->push_back(_open_segment);
            _open_segment = NULL;
            // _log_storage is empty
            _last_log_index.store(first_index_kept - 1);
        } else {
            CHECK(_open_segment->first_index() <= first_index_kept);
        }
    } else {
        // _log_storage is empty
        _last_log_index.store(first_index_kept - 1);
    }
}
```
