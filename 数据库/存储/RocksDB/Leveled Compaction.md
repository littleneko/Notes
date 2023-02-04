## Structure of the files
Files on disk are organized in multiple levels. We call them level-1, level-2, etc, or L1, L2, etc, for short. A special level-0 (or L0 for short) contains files just flushed from in-memory write buffer (memtable). Each level (except level 0) is one data sorted run:

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/level_structure.png" alt="img" style="zoom: 33%;" />

Inside each level (except level 0), data is range partitioned into multiple SST files:

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/level_files.png" alt="img" style="zoom:33%;" />

The level is a sorted run because keys in each SST file are sorted (See [Block-based Table Format](https://github.com/facebook/rocksdb/wiki/Rocksdb-BlockBasedTable-Format) as an example). To identify a position for a key, we first binary search the start/end key of all files to identify which file possibly contains the key, and then binary search inside the file to locate the exact position. In all, it is a full binary search across all the keys in the level.

All non-0 levels have target sizes. Compaction's goal will be to restrict data size of those levels to be under the target. The size targets are usually exponentially increasing:

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/level_targets.png" alt="img" style="zoom:33%;" />

## Compactions
Compaction triggers when number of L0 files reaches `level0_file_num_compaction_trigger`, files of L0 will be merged into L1. ==Normally we have to pick up all the L0 files because they usually are overlapping==:

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/pre_l0_compaction.png" alt="img" style="zoom:33%;" />

After the compaction, it may push the size of L1 to exceed its target:

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/post_l0_compaction.png" alt="img" style="zoom:33%;" />

In this case, we will pick at least one file from L1 and merge it with the overlapping range of L2. The result files will be placed in L2:

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/pre_l1_compaction.png" alt="img" style="zoom:33%;" />

If the results push the next level's size exceeds the target, we do the same as previously -- pick up a file and merge it into the next level:

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/post_l1_compaction.png" alt="img" style="zoom:33%;" />

and then

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/pre_l2_compaction.png" alt="img" style="zoom:33%;" />

and then

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/post_l2_compaction.png" alt="img" style="zoom:33%;" />

Multiple compactions can be executed in parallel if needed:

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/multi_thread_compaction.png" alt="img" style="zoom:33%;" />

Maximum number of compactions allowed is controlled by `max_background_compactions`.

However, L0 to L1 compaction is not parallelized by default. In some cases, it may become a bottleneck that limit the total compaction speed. RocksDB supports subcompaction-based parallelization only for L0 to L1. To enable it, users can set `max_subcompactions` to more than 1. Then, we'll try to partition the range and use multiple threads to execute it:

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/subcompaction.png" alt="img" style="zoom:33%;" />

## Compaction Picking ⭐️
When multiple levels trigger the compaction condition, RocksDB needs to pick which level to compact first. A score is generated for each level:

* ==For non-zero levels, the score is total size of the level divided by the **target size**==. If there are already files picked that are being compacted into the next level, the size of those files is not included into the total size, because they will soon go away.

* for level-0, the score is the total number of files, divided by `level0_file_num_compaction_trigger`, or total size over `max_bytes_for_level_base`, which ever is larger. (if the file size is smaller than `level0_file_num_compaction_trigger`, compaction won't trigger from level 0, no matter how big the score is.)

We compare the score of each level, and the level with highest score takes the priority to compact.

Which file(s) to compact from the level are explained in [[Choose Level Compaction Files]].

## Levels' Target Size ⭐️
### `level_compaction_dynamic_level_bytes` is `false`
If `level_compaction_dynamic_level_bytes` is false, then level targets are determined as following: L1's target will be `max_bytes_for_level_base`. And then `Target_Size(Ln+1) = Target_Size(Ln) * max_bytes_for_level_multiplier * max_bytes_for_level_multiplier_additional[n]`. `max_bytes_for_level_multiplier_additional` is by default all 1.

For example, if `max_bytes_for_level_base = 16384`, `max_bytes_for_level_multiplier = 10` and `max_bytes_for_level_multiplier_additional` is not set, then size of L1, L2, L3 and L4 will be 16384, 163840, 1638400, and 16384000, respectively.  

### `level_compaction_dynamic_level_bytes` is `true`
Target size of the last level (`num_levels`-1) will always be actual size of the level. And then `Target_Size(Ln-1) = Target_Size(Ln) / max_bytes_for_level_multiplier`. We won't fill any level whose target will be lower than `max_bytes_for_level_base / max_bytes_for_level_multiplier `. These levels will be kept empty and all L0 compaction will skip those levels and directly go to the first level with valid target size.

For example, if `max_bytes_for_level_base` is 1GB, `num_levels=6` and the actual size of last level is 276GB, then the target size of L1-L6 will be 0, 0, 0.276GB, 2.76GB, 27.6GB and 276GB, respectively.

==This is to guarantee a stable LSM-tree structure, where 90% of data is stored in the last level==, which can't be guaranteed if `level_compaction_dynamic_level_bytes` is `false`. For example, in the previous example:

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/dynamic_level.png" alt="img" style="zoom:33%;" />

We can guarantee 90% of data is stored in the last level, 9% data in the second last level. There will be multiple benefits to it. 

### When L0 files piled up
Sometimes writes are heavy, temporarily or permanently, so that number of L0 files piled up before they can be compacted to lower levels. When it happens, the behavior of leveled compaction changes:
#### Intra-L0 Compaction
Too many L0 files hurt read performance in most queries. To address the issue, RocksDB may choose to ==compact some L0 files together to a larger file==. This ==sacrifices write amplification== by one but may ==significantly improve read amplification in L0== and in turn ==increase the capability RocksDB can hold data in L0==. This would generate other benefits which would be explained below. ==Additional write amplification of 1 is far smaller than the usual write amplification of leveled compaction==, which is often larger than 10. So we believe it is a good trade-off.
Maximum size of Intra-L0 compaction is also bounded by `options.max_compaction_bytes`. If the option takes a reasonable value, total L0 size will still be bounded, even with Intra-L0 files.

#### Adjust level targets
If total L0 size grows too large, it can be even larger than target size of L1, or even lower levels. It doesn't make sense to continue following this configured targets for each level. Instead, for dynamic level, target levels are adjusted. Size of L1 will be adjusted to actual size of L0. And all levels between L1 and the last level will have adjusted target sizes, so that levels will have the same multiplier. The motivation is to make compaction down to lower levels to happen slower. If data stuck in L0->L1 compaction, it is wasteful to still aggressively compacting lower levels, which competes I/O with higher level compactions.

For example, if configured multiplier is 10, configured base level size is 1GB, and actual L1 to L4 size is 640MB, 6.4GB, 64GB, 640GB, accordingly. If a spike of writes come, and push total L0 size up to 10GB. L1 size will be adjusted to 10GB, and size target of L1 to L4 becomes 10GB, 40GB, 160GB, 640GB. If it is a temporary recent spike, where the new data is likely still staying in its current level L0 or maybe next level L1 , then actual file size of lower levels (i.e, L3, L4) are still close to the previous size while the their size targets have increased. Therefore lower level compaction almost stops and all the resource is used for L0 => L1 and L1 => L2 compactions, so that it can clear L0 files sooner. In case the high write rate becomes permanent. The adjusted targets's write amplification (expected 14) is better than the configured one (expected 32), so it's still a good move.

The goal for this feature is for leveled compaction to handle temporary spike of writes more smoothly. Note that leveled compaction still cannot efficiently handle write rate that is too much higher than capacity based on the configuration. Works on going to further improve it.

## TTL
A file could exist in the LSM tree without going through the compaction process for a really long time if there are no updates to the data in the file's key range. For example, in certain use cases, the keys are "soft deleted" -- set the values to be empty instead of actually issuing a Delete. There might not be any more writes to this "deleted" key range, and if so, such data could remain in the LSM for a really long time resulting in wasted space.

A dynamic `ttl` column-family option has been introduced to solve this problem. Files (and, in turn, data) older than TTL will be scheduled for compaction when there is no other background work. This will make the data go through the regular compaction process, reach to the bottommost level and get rid of old unwanted data.
This also has the (good) side-effect of all the data in the non-bottommost level being newer than ttl, and all data in the bottommost level older than ttl. Note that it could lead to more writes as RocksDB would schedule more compactions.

## Periodic compaction
If compaction filter is present, RocksDB ensures that data go through compaction filter after a certain amount of time. This is achieved via `options.periodic_compaction_seconds`. Setting it to 0 disables this feature. Leaving it the default value, i.e. UINT64_MAX - 1, indicates that RocksDB controls the feature. At the moment, RocksDB will change the value to 30 days. Whenever RocksDB tries to pick a compaction, files older than 30 days will be eligible for compaction and be compacted to the same level.



---

https://github.com/facebook/rocksdb/wiki/Leveled-Compaction