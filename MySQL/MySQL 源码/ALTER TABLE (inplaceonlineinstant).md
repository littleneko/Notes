# Overvire
入口函数:  `mysql_alter_table()`  ( `sql_table.cc` )

**调用该函数的位置有3个:**

1. **mysql_execute_command()** { switch (lex->sql_command) { case SQLCOM_DROP_INDEX: //... }
2. **Sql_cmd_alter_table::execute()**: mysql_execute_command() { switch (lex->sql_command) { case SQLCOM_ALTER_TABLE: lex->m_sql_cmd->execute(thd); }
3. **Sql_cmd_optimize_table::execute** / ... → mysql_recreate_table()

我们主要关注第2个普通的alter table语句的逻辑。


**重要函数调用关系：**
mysql_alter_table()

- mysql_prepare_alter_table()
- create_table_impl()
- fill_alter_inplace_info()
- ha_innobase::check_if_supported_inplace_alter()
- mysql_inplace_alter_table() // if support inplace alter table
   - ha_innobase::ha_prepare_inplace_alter_table()
   - ha_innobase::ha_inplace_alter_table()
   - ha_innobase::ha_commit_inplace_alter_table()


**对于MySQL DDL的一些说明：**

- COPY: 即最原始的DDL方法，在server层实现表的copy过程，整个DDL过程不是online的
- **INPLACE**：Online DDL新增的方法，在InnoDB层实现的DDL
   - **Rebuilds Table**：是否需要重建表（只对于inplace），常见的操作如下：
      - 不需要rebuild table: Add/Drop Secondary Index；
      - 需要rebuild table: Add/Drop Column

注意：是否rebuild table和是否是online之间并没有关系，上述这两种操作都是online的。

   - **Only Modifies Metadata**: 只需要修改元信息，比如Dropping an index、Renaming a column、Extending VARCHAR column size（有条件，可能需要rebuild table）等
- **Online**：即DDL过程中是否允许对表进行DML（LOCK = NONE），对于INPLACE来说，如果不在DDL语句中显示指定LOCK，常见的非online的DDL操作有：Adding a FULLTEXT/SPATIAL index

还有一些非online的操作不是INPLACE的，比如Dropping a primary key、Changing the column data type；
实际上对于非online的情况又可以细分为是读写都不允许还是只允许读。
ref: [https://dev.mysql.com/doc/refman/5.7/en/innodb-online-ddl-operations.html](https://dev.mysql.com/doc/refman/5.7/en/innodb-online-ddl-operations.html)**


Here is an outline of on-line/in-place ALTER TABLE execution through this interface.

**Phase 1 : Initialization**
========================
During this phase we determine which algorithm should be used for execution of ALTER TABLE and what level concurrency it will require.

1. This phase starts by opening the table and preparing description of the new version of the table.
2. Then we check if it is impossible even in theory to carry out this ALTER TABLE using the in-place algorithm. For example, because we need to change storage engine or the user has explicitly requested usage of the "copy" algorithm.
3. If in-place ALTER TABLE is theoretically possible, we continue by compiling differences between old and new versions of the table in the form of HA_ALTER_FLAGS bitmap. We also build a few auxiliary structures describing requested changes and store all these data in the Alter_inplace_info object.
4. Then the handler::check_if_supported_inplace_alter() method is called in order to find if the storage engine can carry out changes requested by this ALTER TABLE using the in-place algorithm. To determine this, the engine can rely on data in HA_ALTER_FLAGS/Alter_inplace_info passed to it as well as on its own checks. If the in-place algorithm can be used for this ALTER TABLE, the level of required concurrency for its execution is also returned. 

If any errors occur during the handler call, ALTER TABLE is aborted and no further handler functions are called.

5. Locking requirements of the in-place algorithm are compared to any concurrency requirements specified by user. If there is a conflict between them, we either switch to the copy algorithm or emit an error.

**Phase 2 : Execution**
========================

1. As the first step, we acquire a lock corresponding to the concurrency level which was returned by handler::check_if_supported_inplace_alter() and requested by the user. This lock is held for most of the duration of in-place ALTER (if HA_ALTER_INPLACE_SHARED_LOCK_AFTER_PREPARE or HA_ALTER_INPLACE_NO_LOCK_AFTER_PREPARE were returned we acquire an exclusive lock for duration of the next step only).
2. After that we call handler::ha_prepare_inplace_alter_table() to give the storage engine a chance to update its internal structures with a higher lock level than the one that will be used for the main step of algorithm. After that we downgrade the lock if it is necessary.
3. After that, the main step of this phase and algorithm is executed. We call the handler::ha_inplace_alter_table() method, which carries out the changes requested by ALTER TABLE but does not makes them visible to other connections yet.
4. We ensure that no other connection uses the table by upgrading our lock on it to exclusive.
5. a) If the previous step succeeds, handler::ha_commit_inplace_alter_table() is called to allow the storage engine to do any final updates to its structures, to make all earlier changes durable and visible to other connections.

b) If we have failed to upgrade lock or any errors have occured during the handler functions calls (including commit), we call handler::ha_commit_inplace_alter_table() to rollback all changes which were done during previous steps.

**Phase 3 : Final**
========================

1. Update SQL-layer data-dictionary by installing .FRM file for the new version of the table.
2. Inform the storage engine about this change by calling the handler::ha_notify_table_changed() method.
3. Destroy the Alter_inplace_info and handler_ctx objects.

# 流程
## mysql_alter_table()
**
**mysql_alter_table()的主要流程：**

1. open old tables : `open_tables()` 
   1. **Acquire "strong" (SRO, SNW, SNRW) metadata locks on tables** : `open_tables_check_upgradable_mdl()` / `lock_table_names()` -> `thd->mdl_context.acquire_locks(&mdl_requests, lock_wait_timeout)` 
2. **mysql_prepare_alter_table()** : Prepare column and key definitions for CREATE TABLE in ALTER TABLE. lists of columns and keys to add, drop or modify into, essentially, CREATE TABLE definition - a list of columns and keys of the new table. 主要是更新alter_info的信息。
3. **create_table_impl()** : Create .FRM for new version of table with a temporary name. 同时生成key_info和key_count（新表中所有的index信息），后续初始化 Alter_inplace_info::key_info_buffer 时使用
   1. **mysql_prepare_create_table()** : Prepares the table and key structures for table creation.
   2. **rea_create_table()** : Create .FRM (and .PAR file for partitioned table).
4. if not request ALGORITHM_COPY
   1. **fill_alter_inplace_info()** : Mark any changes detected in the ha_alter_flags. 初始化alter_inplace_info::index_drop_buffer / index_add_buffe / index_rename_buffer
   2. **ha_innobase::check_if_supported_inplace_alter()**
      1. innobase_support_instant()
   3. mysql_inplace_alter_table()
      1. **upgrade MDL lock to MDL_EXCLUSIVE/MDL_SHARED_NO_WRITE** `wait_while_table_is_used()` / `thd->mdl_context.upgrade_shared_lock()` 
      2. It's now safe to take the table level lock. `lock_tables()` 
      3. **ha_innobase::ha_prepare_inplace_alter_table()**
      4. **downgrade MDL lock** 
      5. **ha_innobase::ha_inplace_alter_table()**
         1. **row_merge_build_indexes()**
         2. **row_log_table_apply()**
      6. **Upgrade to EXCLUSIVE before commit**. `wait_while_table_is_used()` 
      7. **ha_innobase::ha_commit_inplace_alter_table()**
5. ALTER TABLE using copy algorithm.

```cpp
// file: sql_table.cc
// 
/**
  Alter table

  @param thd              Thread handle
  @param new_db           If there is a RENAME clause
  @param new_name         If there is a RENAME clause
  @param create_info      Information from the parsing phase about new
                          table properties.
  @param table_list       The table to change.
  @param alter_info       Lists of fields, keys to be changed, added
                          or dropped.

  @retval   true          Error
  @retval   false         Success

  This is a veery long function and is everything but the kitchen sink :)
  It is used to alter a table and not only by ALTER TABLE but also
  CREATE|DROP INDEX are mapped on this function.

  When the ALTER TABLE statement just does a RENAME or ENABLE|DISABLE KEYS,
  or both, then this function short cuts its operation by renaming
  the table and/or enabling/disabling the keys. In this case, the FRM is
  not changed, directly by mysql_alter_table. However, if there is a
  RENAME + change of a field, or an index, the short cut is not used.
  See how `create_list` is used to generate the new FRM regarding the
  structure of the fields. The same is done for the indices of the table.

  Altering a table can be done in two ways. The table can be modified
  directly using an in-place algorithm, or the changes can be done using
  an intermediate temporary table (copy). In-place is the preferred
  algorithm as it avoids copying table data. The storage engine
  selects which algorithm to use in check_if_supported_inplace_alter()
  based on information about the table changes from fill_alter_inplace_info().
*/
bool mysql_alter_table(THD *thd, const char *new_db, const char *new_name,
                       HA_CREATE_INFO *create_info,
                       TABLE_LIST *table_list,
                       Alter_info *alter_info)
{
  // ... ...
  // ========================================================================
  // 打开需要alter的表，同时会加上MDL锁
  bool error= open_tables(thd, &table_list, &tables_opened, 0,
                        &alter_prelocking_strategy);
  // ========================================================================
  if (mysql_prepare_alter_table(thd, table, create_info, alter_info,
                                &alter_ctx))
  {
    DBUG_RETURN(true);
  }
  // ========================================================================
  /*
    Upgrade from MDL_SHARED_UPGRADABLE to MDL_SHARED_NO_WRITE.
    Afterwards it's safe to take the table level lock.
  */
  if (thd->mdl_context.upgrade_shared_lock(mdl_ticket, MDL_SHARED_NO_WRITE,
                                           thd->variables.lock_wait_timeout)
      || lock_tables(thd, table_list, alter_ctx.tables_opened, 0))
  {
    DBUG_RETURN(true);
  }
  // ========================================================================
  // 对于一些只能COPY的情况提前检测
  /*
    Use copy algorithm if:
    - old_alter_table system variable is set without in-place requested using
      the ALGORITHM clause.
    - Or if in-place is impossible for given operation.
    - Changes to partitioning which were not handled by
      fast_alter_partition_table() needs to be handled using table copying
      algorithm unless the engine supports auto-partitioning as such engines
      can do some changes using in-place API.
  */
  if ((thd->variables.old_alter_table &&
       alter_info->requested_algorithm !=
       Alter_info::ALTER_TABLE_ALGORITHM_INPLACE &&
       alter_info->requested_algorithm !=
       Alter_info::ALTER_TABLE_ALGORITHM_INSTANT)
      || is_inplace_alter_impossible(table, create_info, alter_info, &alter_ctx)
      || (partition_changed &&
          !(table->s->db_type()->partition_flags() & HA_USE_AUTO_PARTITION))
     )
  {
    if (alter_info->requested_algorithm ==
        Alter_info::ALTER_TABLE_ALGORITHM_INPLACE)
    {
      my_error(ER_ALTER_OPERATION_NOT_SUPPORTED, MYF(0),
               "ALGORITHM=INPLACE", "ALGORITHM=COPY");
      DBUG_RETURN(true);
    }
    if (alter_info->requested_algorithm ==
        Alter_info::ALTER_TABLE_ALGORITHM_NOCOPY)
    {
      my_error(ER_ALTER_OPERATION_NOT_SUPPORTED, MYF(0),
               "ALGORITHM=NOCOPY", "ALGORITHM=COPY");
      DBUG_RETURN(true);
    }
    if (alter_info->requested_algorithm ==
        Alter_info::ALTER_TABLE_ALGORITHM_INSTANT) {
      my_error(ER_ALTER_OPERATION_NOT_SUPPORTED, MYF(0), "ALGORITHM=INSTANT",
               "ALGORITHM=COPY");
      DBUG_RETURN(true);
    }
    alter_info->requested_algorithm= Alter_info::ALTER_TABLE_ALGORITHM_COPY;
  }
 
  // ... ...
  // =====================================================================
  /*
    ALTER TABLE ... ENGINE to the same engine is a common way to
    request table rebuild. Set ALTER_RECREATE flag to force table
    rebuild.
  */
  if (create_info->db_type == table->s->db_type() &&
      create_info->used_fields & HA_CREATE_USED_ENGINE)
    alter_info->flags|= Alter_info::ALTER_RECREATE;
 
  // ... ...
  // =====================================================================
  /*
    Create .FRM for new version of table with a temporary name.
    We don't log the statement, it will be logged later.
 
    Keep information about keys in newly created table as it
    will be used later to construct Alter_inplace_info object
    and by fill_alter_inplace_info() call.
  */
 
  KEY *key_info;
  uint key_count;
  /*
    Remember if the new definition has new VARCHAR column;
    create_info->varchar will be reset in create_table_impl()/
    mysql_prepare_create_table().
  */
  bool varchar= create_info->varchar;
 
 
  // 这里初始化key_info和key_count后续会作为参数传递给Alter_inplace_info()
  error= create_table_impl(thd, alter_ctx.new_db, alter_ctx.tmp_name,
                         alter_ctx.table_name,
                         alter_ctx.get_tmp_path(),
                         create_info, alter_info,
                         true, 0, true, NULL,
                         &key_info, &key_count);
 
 
  // ... ...
  // ===================================================================
  // 对于没有指定ALGORITHM = COPY的情况，判断是否支持INPLACE
  if (alter_info->requested_algorithm != Alter_info::ALTER_TABLE_ALGORITHM_COPY)
  {
    Alter_inplace_info ha_alter_info(create_info, alter_info,
                                     alter_ctx.error_if_not_empty, key_info,
                                     key_count, thd->work_part_info);
    // 新的TABLE对象
    TABLE *altered_table= NULL;
    bool use_inplace= true;
 
    /* Fill the Alter_inplace_info structure. */
    // 主要功能是填充handler_flags
    if (fill_alter_inplace_info(thd, table, varchar, &ha_alter_info))
      goto err_new_table_cleanup;
 
 
    // -----------------------------------------------------------------
    // 初始化altered_table
    if (!(altered_table= open_table_uncached(thd, alter_ctx.get_tmp_path(),
                                             alter_ctx.new_db,
                                             alter_ctx.tmp_name,
                                             true, false)))
      goto err_new_table_cleanup;
 
    /* Set markers for fields in TABLE object for altered table. */
    update_altered_table(ha_alter_info, altered_table);
 
    /*
      Mark all columns in 'altered_table' as used to allow usage
      of its record[0] buffer and Field objects during in-place
      ALTER TABLE.
    */
    altered_table->column_bitmaps_set_no_signal(&altered_table->s->all_set,
                                                &altered_table->s->all_set);
 
    set_column_defaults(altered_table, alter_info->create_list);
    // -----------------------------------------------------------------
 
    // ... ...
     
    // Ask storage engine whether to use copy or in-place
    // 调用的是ha_innobase::check_if_supported_inplace_alter()
    enum_alter_inplace_result inplace_supported=
      table->file->check_if_supported_inplace_alter(altered_table,
                                                    &ha_alter_info);
     
    // ... ...
    // -----------------------------------------------------------------
    //
    // If INSTANT was requested but it is not supported, report error.
    if (alter_info->requested_algorithm ==
            Alter_info::ALTER_TABLE_ALGORITHM_INSTANT &&
        inplace_supported != HA_ALTER_INPLACE_INSTANT &&
        inplace_supported != HA_ALTER_ERROR) {
      ha_alter_info.report_unsupported_error("ALGORITHM=INSTANT",
                                             "ALGORITHM=COPY/INPLACE/NOCOPY");
      close_temporary_table(thd, altered_table, true, false);
      goto err_new_table_cleanup;
    }
 
    // If NOCOPY was requested but it is not supported, report error.
    if (alter_info->requested_algorithm ==
            Alter_info::ALTER_TABLE_ALGORITHM_NOCOPY &&
        inplace_supported != HA_ALTER_INPLACE_INSTANT &&
        inplace_supported != HA_ALTER_INPLACE_NOCOPY_LOCK &&
        inplace_supported != HA_ALTER_INPLACE_NOCOPY_NO_LOCK &&
        inplace_supported != HA_ALTER_ERROR) {
      ha_alter_info.report_unsupported_error("ALGORITHM=NOCOPY",
                                             "ALGORITHM=COPY/INPLACE");
      close_temporary_table(thd, altered_table, true, false);
      goto err_new_table_cleanup;
    }
    // -----------------------------------------------------------------
    switch (inplace_supported) {
    case HA_ALTER_INPLACE_EXCLUSIVE_LOCK:
      // If SHARED lock and no particular algorithm was requested, use COPY.
      if (alter_info->requested_lock ==
          Alter_info::ALTER_TABLE_LOCK_SHARED &&
          alter_info->requested_algorithm ==
          Alter_info::ALTER_TABLE_ALGORITHM_DEFAULT)
      {
        use_inplace= false;
      }
      // Otherwise, if weaker lock was requested, report errror.
      else if (alter_info->requested_lock ==
               Alter_info::ALTER_TABLE_LOCK_NONE ||
               alter_info->requested_lock ==
               Alter_info::ALTER_TABLE_LOCK_SHARED)
      {
        ha_alter_info.report_unsupported_error("LOCK=NONE/SHARED",
                                               "LOCK=EXCLUSIVE");
        close_temporary_table(thd, altered_table, true, false);
        goto err_new_table_cleanup;
      }
      break;
    case HA_ALTER_INPLACE_SHARED_LOCK_AFTER_PREPARE:
    case HA_ALTER_INPLACE_SHARED_LOCK:
    case HA_ALTER_INPLACE_NOCOPY_LOCK:
      // If weaker lock was requested, report errror.
      if (alter_info->requested_lock ==
          Alter_info::ALTER_TABLE_LOCK_NONE)
      {
        ha_alter_info.report_unsupported_error("LOCK=NONE", "LOCK=SHARED");
        close_temporary_table(thd, altered_table, true, false);
        goto err_new_table_cleanup;
      }
      break;
    case HA_ALTER_INPLACE_NO_LOCK_AFTER_PREPARE:
    case HA_ALTER_INPLACE_NO_LOCK:
    case HA_ALTER_INPLACE_NOCOPY_NO_LOCK:
    case HA_ALTER_INPLACE_INSTANT:
        /*
          Note that instant operations are a subset of nocopy operations,
          that are in turn a subset of in-place operations.
 
          It is totally safe to execute operation using a faster algorithm
          (e.g. INSTANT) if it has no drawbacks as compared to a slower
          algorithm (e.g. NOCOPY or INPLACE) even if the user explicitly asked
          for the slower one. Doing so also allows to keep code in engines which
          support only limited subset of in-place ALTER TABLE operations as
          instant metadata only changes simple.
 
          If the faster algorithm has some downsides to the slower algorithm and
          user explicitly asks for the slower one, it is responsibility of
          storage engine to fallback to the slower algorithm execution by
          returning the corresponding HA_ALTER_INPLACE_* constant from
          check_if_supported_inplace_alter().
        */
      break;
    case HA_ALTER_INPLACE_NOT_SUPPORTED:
      // If INPLACE was requested, report error.
      if (alter_info->requested_algorithm ==
          Alter_info::ALTER_TABLE_ALGORITHM_INPLACE)
      {
        ha_alter_info.report_unsupported_error("ALGORITHM=INPLACE",
                                               "ALGORITHM=COPY");
        close_temporary_table(thd, altered_table, true, false);
        goto err_new_table_cleanup;
      }
      // COPY with LOCK=NONE is not supported, no point in trying.
      if (alter_info->requested_lock ==
          Alter_info::ALTER_TABLE_LOCK_NONE)
      {
        ha_alter_info.report_unsupported_error("LOCK=NONE", "LOCK=SHARED");
        close_temporary_table(thd, altered_table, true, false);
        goto err_new_table_cleanup;
      }
      // Otherwise use COPY
      use_inplace= false;
      break;
    case HA_ALTER_ERROR:
    default:
      close_temporary_table(thd, altered_table, true, false);
      goto err_new_table_cleanup;
    }
    // -----------------------------------------------------------------
    if (use_inplace)
    {
      if (mysql_inplace_alter_table(thd, table_list, table,
                                    altered_table,
                                    &ha_alter_info,
                                    inplace_supported, &target_mdl_request,
                                    &alter_ctx))
      {
        thd->count_cuted_fields= CHECK_FIELD_IGNORE;
        DBUG_RETURN(true);
      }
 
      goto end_inplace;
    }
    else
    {
      close_temporary_table(thd, altered_table, true, false);
    }
  }
   
  // ===================================================================
  /* ALTER TABLE using copy algorithm. */
  // ... ...
 
}
```

### 重要数据结构
#### calss Alter_info {}
在yacc中初始化，在mysql_prepare_alter_table() 之后实际上会包含alter之后新表完整的信息（column、key、...）

| **Field** | **Type** | **Desc** |
| --- | --- | --- |
| flags | uint |  |
| requested_algorithm | enum_alter_table_algorithm |  |
| requested_lock | enum_alter_table_lock |  |
| drop_list | List<Alter_drop> | Columns and keys to be dropped. After mysql_prepare_alter_table() it contains only foreign keys and virtual generated columns to be dropped. This information is necessary for the storage engine to do in-place alter. |
| alter_list | List<Alter_column> | Columns for ALTER_COLUMN_CHANGE_DEFAULT. |
| key_list | List<Key> | List of keys, used by both CREATE and ALTER TABLE. 
在进入mysql_alter_table()函数时的初始值只有新加的index (ADD INDEX)信息，在mysql_prepare_alter_table() 之后包括了所有index的信息 |
| alter_rename_key_list | List<Alter_rename_key> |  |
| create_list | List<Create_field> | List of columns, used by both CREATE and ALTER TABLE.  
在进入mysql_alter_table()函数时的初始值只有新加 / 修改（ADD COLUMN / MODIFY COLUMN）的COLUMN的信息；在 mysql_prepare_alter_table() 之后包括了所有的column信息 |


#### class Alter_inplace_info {}
| **Field** | **Type** | **Desc** |
| --- | --- | --- |
| create_info | HA_CREATE_INFO* | Create options (like MAX_ROWS) for the new version of table.  |
| alter_info | Alter_info* | Alter options, fields and keys for the new version of table. |
| error_if_not_empty | bool |  |
| key_info_buffer | KEY* | Array of KEYs for new version of table - including KEYs to be added.  
新表中所有的index信息，在 create_table_impl() 中生成，实例化时作为参数传入 |
| key_count | uint |  |
| index_drop_count | uint |  |
| index_drop_buffer | KEY** | Array of pointers to KEYs to be dropped belonging to the TABLE instance for the old version of the table. 
在fill_alter_inplace_info() 中初始化 |
| index_add_count | uint | Size of index_add_buffer array |
| index_add_buffer | uint* | Array of indexes into key_info_buffer for KEYs to be added, sorted in increasing order. 
表示key_info_buffer中新加的index信息，在fill_alter_inplace_info() 中初始化 |
| index_rename_count | uint |  |
| index_rename_buffer | KEY_PAIR* | Array of KEY_PAIR objects describing indexes being renamed.   在fill_alter_inplace_info() 中初始化 |
| handler_ctx | inplace_alter_handler_ctx* | 在ha_innobase::prepare_inplace_alter_table() 初始化 |
| handler_flags | HA_ALTER_FLAGS | 在函数mysql_alter_table() --> fill_alter_inplace_info() 函数中计算 |
| inplace_method | enum_alter_inplace_result |  |
| online | bool | true for online operation (LOCK=NONE).  在 mysql_inplace_alter_table() 中赋值 |


#### struct ha_innobase_inplace_ctx : public inplace_alter_handler_ctx {}
在 ha_innobase::prepare_inplace_alter_table() 中实例化

| **Field** | **Type** | **Desc** |
| --- | --- | --- |
| add_index | dict_index_t** | InnoDB indexes being created. 对于rebuild table的情况,包括了所有索引信息;不需要rebuild table的情况,todo。在prepare_inplace_alter_table_dict()中初始化,idx的信息在 innobase_create_key_defs() 中生成,使用 index_def_t 描述 |
| add_key_numbers | const ulint* | MySQL key numbers for the InnoDB indexes that are being created. |
| num_to_add_index | ulint | number of InnoDB indexes being created. |
| drop_index | dict_index_t**  |  |
| num_to_drop_index | const ulint |  |
| rename | dict_index_t** |  |
| num_to_rename | const ulint |  |
| online | bool |  |
| old_table | dict_table_t* |  |
| new_table | dict_table_t* | table where the indexes are being created or dropped. 需要rebuild table的情况下,表示新表(tablename临时生成)。在prepare_inplace_alter_table_dict()中的rebuild_table / ... 逻辑中create |
| col_map | const ulint* |  |
| col_names | const char** |  |
| add_cols | const dtuple_t* | default values of ADD COLUMN, or NULL |
| add_icol | dict_col_t* |  |
| skip_pk_sort | bool | whether the order of the clustered index is unchanged.

innobase_pk_order_preserved()

Determine whether both the indexes have same set of primary key
fields arranged in the same order.

Rules when we cannot skip sorting:
(1) Removing existing PK columns somewhere else than at the end of the PK;
(2) Adding existing columns to the PK, except at the end of the PK when no
columns are removed from the PK;
(3) Changing the order of existing PK columns;
(4) Decreasing the prefix length just like removing existing PK columns
follows rule(1), Increasing the prefix length just like adding existing
PK columns follows rule(2). |


### MDL锁的使用
DDL的整体流程参考[mysql_alter_table](#aGign)一节，MDL锁在DDL主流程中如下：

1. MDL lock
2. check if support inplace
3. upgrade MDL lock (MDL_EXCLUSIVE/MDL_SHARED_NO_WRITE)
4. prepare
5. downgrade MDL lock (MDL_SHARED_NO_WRITE/MDL_SHARED_UPGRADABLE)
6. inplace
7. upgrade MDL lock (MDL_EXCLUSIVE)
8. commit

可以看到，对于online DDL加锁过程只在prepare流程和commit流程，在最耗时的执行流程中，是不需要加锁的

```java
static bool mysql_inplace_alter_table(
    // ... ...)
{
  // ... ...
  /*
    Upgrade to EXCLUSIVE lock if:
    - This is requested by the storage engine
    - Or the storage engine needs exclusive lock for just the prepare
      phase
    - Or requested by the user

    Note that we handle situation when storage engine needs exclusive
    lock for prepare phase under LOCK TABLES in the same way as when
    exclusive lock is required for duration of the whole statement.
  */
  if (inplace_supported == HA_ALTER_INPLACE_EXCLUSIVE_LOCK ||
      ((inplace_supported == HA_ALTER_INPLACE_SHARED_LOCK_AFTER_PREPARE ||
        inplace_supported == HA_ALTER_INPLACE_NO_LOCK_AFTER_PREPARE) &&
       (thd->locked_tables_mode == LTM_LOCK_TABLES ||
        thd->locked_tables_mode == LTM_PRELOCKED_UNDER_LOCK_TABLES)) ||
       alter_info->requested_lock == Alter_info::ALTER_TABLE_LOCK_EXCLUSIVE)
  {
    if (wait_while_table_is_used(thd, table, HA_EXTRA_FORCE_REOPEN))
      goto cleanup;
    /*
      Get rid of all TABLE instances belonging to this thread
      except one to be used for in-place ALTER TABLE.

      This is mostly needed to satisfy InnoDB assumptions/asserts.
    */
    close_all_tables_for_name(thd, table->s, alter_ctx->is_table_renamed(),
                              table);
    /*
      If we are under LOCK TABLES we will need to reopen tables which we
      just have closed in case of error.
    */
    reopen_tables= true;
  }
  else if (inplace_supported == HA_ALTER_INPLACE_SHARED_LOCK_AFTER_PREPARE ||
           inplace_supported == HA_ALTER_INPLACE_NO_LOCK_AFTER_PREPARE)
  {
    /*
      Storage engine has requested exclusive lock only for prepare phase
      and we are not under LOCK TABLES.
      Don't mark TABLE_SHARE as old in this case, as this won't allow opening
      of table by other threads during main phase of in-place ALTER TABLE.
    */
    if (thd->mdl_context.upgrade_shared_lock(table->mdl_ticket, MDL_EXCLUSIVE,
                                             thd->variables.lock_wait_timeout))
      goto cleanup;

    tdc_remove_table(thd, TDC_RT_REMOVE_NOT_OWN_KEEP_SHARE,
                     table->s->db.str, table->s->table_name.str,
                     false);
  }

  /*
    Upgrade to SHARED_NO_WRITE lock if:
    - The storage engine needs writes blocked for the whole duration
    - Or this is requested by the user
    Note that under LOCK TABLES, we will already have SHARED_NO_READ_WRITE.
  */
  if ((inplace_supported == HA_ALTER_INPLACE_SHARED_LOCK ||
       alter_info->requested_lock == Alter_info::ALTER_TABLE_LOCK_SHARED) &&
      thd->mdl_context.upgrade_shared_lock(table->mdl_ticket,
                                           MDL_SHARED_NO_WRITE,
                                           thd->variables.lock_wait_timeout))
  {
    goto cleanup;
  }

  // It's now safe to take the table level lock.
  if (lock_tables(thd, table_list, alter_ctx->tables_opened, 0))
    goto cleanup;
  
  // ========================================================================
  table->file->ha_prepare_inplace_alter_table(altered_table, ha_alter_info)
  // ========================================================================
  
  /*
    Downgrade the lock if storage engine has told us that exclusive lock was
    necessary only for prepare phase (unless we are not under LOCK TABLES) and
    user has not explicitly requested exclusive lock.
  */
  if ((inplace_supported == HA_ALTER_INPLACE_SHARED_LOCK_AFTER_PREPARE ||
       inplace_supported == HA_ALTER_INPLACE_NO_LOCK_AFTER_PREPARE) &&
      !(thd->locked_tables_mode == LTM_LOCK_TABLES ||
        thd->locked_tables_mode == LTM_PRELOCKED_UNDER_LOCK_TABLES) &&
      (alter_info->requested_lock != Alter_info::ALTER_TABLE_LOCK_EXCLUSIVE))
  {
    /* If storage engine or user requested shared lock downgrade to SNW. */
    if (inplace_supported == HA_ALTER_INPLACE_SHARED_LOCK_AFTER_PREPARE ||
        alter_info->requested_lock == Alter_info::ALTER_TABLE_LOCK_SHARED)
      table->mdl_ticket->downgrade_lock(MDL_SHARED_NO_WRITE);
    else
    {
      DBUG_ASSERT(inplace_supported == HA_ALTER_INPLACE_NO_LOCK_AFTER_PREPARE);
      table->mdl_ticket->downgrade_lock(MDL_SHARED_UPGRADABLE);
    }
  }
    
  // ========================================================================
  table->file->ha_inplace_alter_table(altered_table, ha_alter_info))
  // ========================================================================
      
  // Upgrade to EXCLUSIVE before commit.
  if (wait_while_table_is_used(thd, table, HA_EXTRA_PREPARE_FOR_RENAME))
    goto rollback;
    
  // ========================================================================
   table->file->ha_commit_inplace_alter_table(altered_table, ha_alter_info, true)
  // ========================================================================
}
```

## Check if Support Inplace Alter Table
//todo
retval

- **HA_ALTER_INPLACE_NOT_SUPPORTED**: Not supported
- **HA_ALTER_INPLACE_NO_LOCK**: Supported
- **HA_ALTER_INPLACE_SHARED_LOCK_AFTER_PREPARE**: Supported, but requires lock during main phase and exclusive lock during prepare phase.
- **HA_ALTER_INPLACE_NO_LOCK_AFTER_PREPARE**: Supported, prepare phase requires exclusive lock (any transactions that have accessed the table must commit or roll back first, and no transactions can access the table while prepare_inplace_alter_table() is executing)

## Prepare Inplace Alter Table
Allows InnoDB to **update internal structures** with concurrent writes blocked (provided that check_if_supported_inplace_alter() did not return HA_ALTER_INPLACE_NO_LOCK). This will be invoked before inplace_alter_table()

**调用栈：**
```
(gdb) bt
#0  dict_create_table_step (thr=0x7f680004fb48) at /data1/code/mysql-server-5.7/storage/innobase/dict/dict0crea.cc:1441
#1  0x0000558b50ff000c in que_thr_step (thr=0x7f680004fb48) at /data1/code/mysql-server-5.7/storage/innobase/que/que0que.cc:1065
#2  0x0000558b50ff01b0 in que_run_threads_low (thr=0x7f680004fb48) at /data1/code/mysql-server-5.7/storage/innobase/que/que0que.cc:1119
#3  0x0000558b50ff0387 in que_run_threads (thr=0x7f680004fb48) at /data1/code/mysql-server-5.7/storage/innobase/que/que0que.cc:1159
#4  0x0000558b5104a510 in row_create_table_for_mysql (table=0x7f6800022db0, compression=0x7f68000506f8 "", trx=0x7f685d4dd170, commit=false)
    at /data1/code/mysql-server-5.7/storage/innobase/row/row0mysql.cc:3093
#5  0x0000558b50f2a6f2 in prepare_inplace_alter_table_dict (ha_alter_info=0x7f685c1ef380, altered_table=0x7f680000a320, old_table=0x7f680000c6f0, table_name=0x7f680000ee75 "t1", flags=33, 
    flags2=80, fts_doc_id_col=18446744073709551615, add_fts_doc_id=false, add_fts_doc_id_idx=false) at /data1/code/mysql-server-5.7/storage/innobase/handler/handler0alter.cc:4724
#6  0x0000558b50f2eeb6 in ha_innobase::prepare_inplace_alter_table (this=0x7f680004f460, altered_table=0x7f680000a320, ha_alter_info=0x7f685c1ef380)
    at /data1/code/mysql-server-5.7/storage/innobase/handler/handler0alter.cc:6204
#7  0x0000558b504c1069 in handler::ha_prepare_inplace_alter_table (this=0x7f680004f460, altered_table=0x7f680000a320, ha_alter_info=0x7f685c1ef380)
    at /data1/code/mysql-server-5.7/sql/handler.cc:4843
#8  0x0000558b50bc3298 in mysql_inplace_alter_table (thd=0x7f6800000e10, table_list=0x7f6800008a68, table=0x7f680000c6f0, altered_table=0x7f680000a320, ha_alter_info=0x7f685c1ef380, 
    inplace_supported=HA_ALTER_INPLACE_NO_LOCK_AFTER_PREPARE, target_mdl_request=0x7f685c1ef5a0, alter_ctx=0x7f685c1efcf0) at /data1/code/mysql-server-5.7/sql/sql_table.cc:7557
#9  0x0000558b50bc890f in mysql_alter_table (thd=0x7f6800000e10, new_db=0x7f6800008ff0 "test", new_name=0x0, create_info=0x7f685c1f0d50, table_list=0x7f6800008a68, 
    alter_info=0x7f685c1f0ca0) at /data1/code/mysql-server-5.7/sql/sql_table.cc:9807
#10 0x0000558b50d50789 in Sql_cmd_alter_table::execute (this=0x7f68000091a8, thd=0x7f6800000e10) at /data1/code/mysql-server-5.7/sql/sql_alter.cc:333
#11 0x0000558b50b2b7b5 in mysql_execute_command (thd=0x7f6800000e10, first_level=true) at /data1/code/mysql-server-5.7/sql/sql_parse.cc:4845
#12 0x0000558b50b2d89c in mysql_parse (thd=0x7f6800000e10, parser_state=0x7f685c1f2530) at /data1/code/mysql-server-5.7/sql/sql_parse.cc:5584
#13 0x0000558b50b227fb in dispatch_command (thd=0x7f6800000e10, com_data=0x7f685c1f2de0, command=COM_QUERY) at /data1/code/mysql-server-5.7/sql/sql_parse.cc:1491
#14 0x0000558b50b21687 in do_command (thd=0x7f6800000e10) at /data1/code/mysql-server-5.7/sql/sql_parse.cc:1032
#15 0x0000558b50c64c0e in handle_connection (arg=0x558b53502560) at /data1/code/mysql-server-5.7/sql/conn_handler/connection_handler_per_thread.cc:313
#16 0x0000558b51348da5 in pfs_spawn_thread (arg=0x558b5353cde0) at /data1/code/mysql-server-5.7/storage/perfschema/pfs.cc:2197
#17 0x00007f6866e95422 in start_thread () from /usr/lib/libpthread.so.0
#18 0x00007f68666b0bf3 in clone () from /usr/lib/libc.so.6
```

**ha_innobase::prepare_inplace_alter_table()的主要流程：**

1. 各种check
   1. todo
   2. Check if any index name is reserved. innobase_index_name_is_reserved()
   3. Check that index keys are sensible. innobase_check_index_keys()
   4. Prohibit renaming a column to something that the table already contains.
   5. Check each index's column length to make sure they do not exceed limit. innobase_check_column_length(). index长度767 or 3072 限制在这里检测 （ER_INDEX_COLUMN_TOO_LONG）（MySQL实际限制是所有index长度累加值，这里只分别检测了每个key的长度）
   6. We won't be allowed to add fts index to a table with fts indexes already but without AUX_HEX_NAME set.
   7. Check existing index definitions for too-long column prefixes as well, in case max_col_len shrunk.
2. DROP_FOREIGN_KEY // todo
3. DROP_INDEX / DROP_UNIQUE_INDEX / DROP_PK_INDEX //todo
4. Create a list of dict_index_t objects that are to be renamed, also checking for requests to rename nonexistent indexes.
5. ADD_FOREIGN_KEY // todo
6. 对于**没有ALTER DATA (REBUILD|ONLINE_CREATE(ADD INDEX等))** 和 **不需要rebuild table的****CHANGE_CREATE_OPTION** ，在这里直接做一些处理后就返回Success(false). 
   1. DROP_VIRTUAL_COLUMN: prepare_inplace_drop_virtual()
   2. ADD_VIRTUAL_COLUMN: prepare_inplace_add_virtual()
7. full-text search index // todo
8. See if an AUTO_INCREMENT column was added.
9. create ha_innobase_inplace_ctx, **prepare_inplace_alter_table_dict()**

**prepare_inplace_alter_table_dict()主要流程：**

1. 处理DROP_VIRTUAL_COLUMN和ADD_VIRTUAL_COLUMN（ALTER TABLR t1 ADD COLUMN c1，ADD VIRTUAL COLUMN ...）
2. Create a background transaction for the operations on the data dictionary tables.
3. Create table containing all indexes to be built in this ALTER TABLE ADD INDEX so that they are in the correct order in the table. `innobase_create_key_defs()` 会利用 `Alter_inplace_info::key_info_buff` 的信息生成 `struct index_def_t` ，即生成的index_def是新表的所有index信息。
4. Acquire a lock on the table before creating any indexes. 对于非online的情况需要 `row_merge_lock_table()` 
5. Latch the InnoDB data dictionary exclusively so that no deadlocks or lock waits can happen in it during an index create operation. `row_mysql_lock_data_dictionary(ctx->trx)` 
6. 对于rebuild table 创建新表的情况
   1. new_table_name = dict_mem_create_temporary_tablename(). i.e. "test/#sql-ib104-4021736443"
   2. 从 altered_table->s→fields 中统计得到n_cols 和 n_v_cols. i.e. n_cols = 5, ==> [id, a, c1, c2, c3(new add)]
   3. space_id = ...
   4. 处理mysql type到innobase type的转换
   5. **创建临时表** `row_create_table_for_mysql(ctx->new_table, compression, ctx->trx, false)` -> `dict_create_table_step()` 
   6. if SUCCESS: open table. `dict_table_open_on_name(ctx->new_table->name.m_name, ...)` 
7. not need rebuild table. // todo
8. 对于新加的index. Create the indexes in SYS_INDEXES and load into dictionary. `for (ulint a = 0; a < ctx->num_to_add_index; a++) {...}` 
   1. 根据 innobase_create_key_defs() 中生成的 index_defs 信息生成ctx->add_index (dict_index_t). `ctx->add_index[a] = row_merge_create_index(ctx->trx, ctx->new_table, &index_defs[a], add_v, add_i);` 
   2. If only online ALTER TABLE operations have been requested, allocate a modification log. If the table will be locked anyway, the modification log is unnecessary. When rebuilding the table (new_clustered), we will allocate the log for the clustered index of the old table, later. 这里实际上是**创建用于每个新加index的rowlog**： `row_log_allocate(ctx->add_index[a], NULL, true, NULL, NULL, path);` 
9. **对于rebuild table的情况，创建old clust index的rowlog**： `row_log_allocate(clust_index, ctx->new_table, !(ha_alter_info->handler_flag & Alter_inplace_info::ADD_PK_INDEX), ctx->add_cols, ctx->col_map, path)` 


对于不需要rebuild table的情况，可以参考官方文档[online DDL](https://dev.mysql.com/doc/refman/5.7/en/innodb-online-ddl-operations.html)相关的章节，常见的有_ADD/DROP/RENAME INDEX__、__Setting/Dropping a column default value__、__Extending VARCHAR column size（有条件__）__、__Adding/Droping VIRTUAL column__、__Adding/Dropping a foreign key constraint_ 。

> **TIPS:**
> Compact格式下某些情况下Extending VARCHAR column size是需要rebuild table的，从record的非null[变长字段长度列表](https://www.yuque.com/littleneko/ubavq5/gw2r53#dys7V)一节我们知道，非null变长字段长度是1字节或2字节，而且与VARCHAR(X)的X有关。
> 
> 结论如下 (以latin1字符集为例)：
> - 数据实际长度小于128：Extending（即更改X）不rebuild table
> - **数据实际长度[128, 256)：X从小于256的值Extending到大于等于256的值，需要rebuild table**
> - 数据实际长度大于等于256：X原始值肯定大于等于256，不需要rebuild table
> 
> e.g.原始数据长度为150，
> Extending VARCHAR(200) -> VARCHAR(300)，需要rebuild table
> Extending VARCHAR(200) -> VARCHAR(250)，不需要rebuild table
> 

```cpp
/** Operations for creating secondary indexes (no rebuild needed) */
static const Alter_inplace_info::HA_ALTER_FLAGS INNOBASE_ONLINE_CREATE
	= Alter_inplace_info::ADD_INDEX
	| Alter_inplace_info::ADD_UNIQUE_INDEX
	| Alter_inplace_info::ADD_SPATIAL_INDEX;

/** Operations for rebuilding a table in place */
static const Alter_inplace_info::HA_ALTER_FLAGS INNOBASE_ALTER_REBUILD
	= Alter_inplace_info::ADD_PK_INDEX
	| Alter_inplace_info::DROP_PK_INDEX
	| Alter_inplace_info::CHANGE_CREATE_OPTION
	/* CHANGE_CREATE_OPTION needs to check innobase_need_rebuild() */
	| Alter_inplace_info::ALTER_COLUMN_NULLABLE
	| Alter_inplace_info::ALTER_COLUMN_NOT_NULLABLE
	| Alter_inplace_info::ALTER_STORED_COLUMN_ORDER
	| Alter_inplace_info::DROP_STORED_COLUMN
	| Alter_inplace_info::ADD_STORED_BASE_COLUMN
	| Alter_inplace_info::RECREATE_TABLE
	/*
	| Alter_inplace_info::ALTER_STORED_COLUMN_TYPE
	*/
	;

/** Operations that require changes to data */
static const Alter_inplace_info::HA_ALTER_FLAGS INNOBASE_ALTER_DATA
	= INNOBASE_ONLINE_CREATE | INNOBASE_ALTER_REBUILD;

/** Operations for altering a table that InnoDB does not care about */
static const Alter_inplace_info::HA_ALTER_FLAGS INNOBASE_INPLACE_IGNORE
	= Alter_inplace_info::ALTER_COLUMN_DEFAULT
	| Alter_inplace_info::ALTER_COLUMN_COLUMN_FORMAT
	| Alter_inplace_info::ALTER_COLUMN_STORAGE_TYPE
	| Alter_inplace_info::ALTER_VIRTUAL_GCOL_EXPR
	| Alter_inplace_info::ALTER_RENAME;

/** Operations on foreign key definitions (changing the schema only) */
static const Alter_inplace_info::HA_ALTER_FLAGS INNOBASE_FOREIGN_OPERATIONS
	= Alter_inplace_info::DROP_FOREIGN_KEY
	| Alter_inplace_info::ADD_FOREIGN_KEY;

/** Operations that InnoDB cares about and can perform without rebuild */
static const Alter_inplace_info::HA_ALTER_FLAGS INNOBASE_ALTER_NOREBUILD
	= INNOBASE_ONLINE_CREATE
	| INNOBASE_FOREIGN_OPERATIONS
	| Alter_inplace_info::DROP_INDEX
	| Alter_inplace_info::DROP_UNIQUE_INDEX
	| Alter_inplace_info::RENAME_INDEX
	| Alter_inplace_info::ALTER_COLUMN_NAME
	| Alter_inplace_info::ALTER_COLUMN_EQUAL_PACK_LENGTH
	| Alter_inplace_info::ALTER_INDEX_COMMENT
	| Alter_inplace_info::ADD_VIRTUAL_COLUMN
	| Alter_inplace_info::DROP_VIRTUAL_COLUMN
	| Alter_inplace_info::ALTER_VIRTUAL_COLUMN_ORDER
        | Alter_inplace_info::ALTER_COLUMN_INDEX_LENGTH;
	/* | Alter_inplace_info::ALTER_VIRTUAL_COLUMN_TYPE; */
```
**index_def_t**
```cpp
/** Definition of an index being created */
struct index_def_t {
	const char*	name;		/*!< index name */
	bool		rebuild;	/*!< whether the table is rebuilt */
	ulint		ind_type;	/*!< 0, DICT_UNIQUE,
					or DICT_CLUSTERED */
	ulint		key_number;	/*!< MySQL key number,
					or ULINT_UNDEFINED if none */
	ulint		n_fields;	/*!< number of fields in index */
	index_field_t*	fields;		/*!< field definitions */
	st_mysql_ftparser*
			parser;		/*!< fulltext parser plugin */
	bool		is_ngram;	/*!< true if it's ngram parser */
};
```
## Inplace Alter Table

1. ha_innobase::inplace_alter_table()
   1. Read the clustered index of the table and build indexes based on this information using temporary files and merge sort. `row_merge_build_indexes()` 
      1. Read clustered index of the table and create files for secondary index entries for merge sort `row_merge_read_clustered_index()` 
      2. for every new_index (all for rebuild table or new added index), sort and insert. `row_merge_sort()` / `row_merge_insert_index_tuples()` 
      3. `row_log_apply()` 
   2. online && need_rebuild: `row_log_table_apply()` (第一次调用apply，在commit阶段还会第二次调用apply)

### row0merge
相关数据结构
```cpp
/** Merge record in row_merge_buf_t */
struct mtuple_t {
	dfield_t*	fields;		/*!< data fields */
};

/** Buffer for sorting in main memory. */
struct row_merge_buf_t {
	mem_heap_t*	heap;		/*!< memory heap where allocated */
	dict_index_t*	index;		/*!< the index the tuples belong to */
	ulint		total_size;	/*!< total amount of data bytes */
	ulint		n_tuples;	/*!< number of data tuples */
	ulint		max_tuples;	/*!< maximum number of data tuples */
	mtuple_t*	tuples;		/*!< array of data tuples */
	mtuple_t*	tmp_tuples;	/*!< temporary copy of tuples,
					for sorting */
};
```
`row_merge_buf_t`  用于保存要写入new_index的记录，每个new_index都对应一个该结构。在 `row_merge_read_clustered_index()` 中初始化和使用：
```cpp
merge_buf = static_cast<row_merge_buf_t**>(
    ut_malloc_nokey(n_index * sizeof *merge_buf));

for (ulint i = 0; i < n_index; i++) {
    // ... ...
    merge_buf[i] = row_merge_buf_create(index[i]);
}
```
其中 `tuples` 和 `tmp_tuples` 的大小（即 `max_tuples` ），在 `row_merge_buf_create()` 中计算：
```cpp
/******************************************************//**
Allocate a sort buffer.
@return own: sort buffer */
row_merge_buf_t*
row_merge_buf_create(
/*=================*/
	dict_index_t*	index)	/*!< in: secondary index */
{
    // ... ...
	max_tuples = static_cast<ulint>(srv_sort_buf_size)
		/ ut_max(static_cast<ulint>(1),
			 dict_index_get_min_size(index));
    // ... ...
    buf = row_merge_buf_create_low(heap, index, max_tuples, buf_size);
}


/********************************************************************//**
Returns the minimum data size of an index record.
@return minimum data size in bytes */
UNIV_INLINE
ulint
dict_index_get_min_size(
/*====================*/
	const dict_index_t*	index)	/*!< in: index */
{
	ulint	n	= dict_index_get_n_fields(index);
	ulint	size	= 0;

	while (n--) {
		size += dict_col_get_min_size(dict_index_get_nth_col(index,
								     n));
	}

	return(size);
}
```
实际上计算的是最好的情况下（rec大小最小）一个 `srv_sort_buf_size` 的大小能存储的记录数量。

`total_size` 表示当前的merge_buffer中数据的总大小，详细情况参考merge_file的格式。

```cpp
/** Information about temporary files used in merge sort */
struct merge_file_t {
	int		fd;		/*!< file descriptor */
	ulint		offset;		/*!< file offset (end of file) */ // srv_sort_buf_size单位
	ib_uint64_t	n_rec;		/*!< number of records in the file */
};
```
`merge_file_t` 用于对读取的old_clust_index的数据进行排序，对于每个sec index，都是需要排序的；如果更改了pk，pk也要排序。
```cpp
dberr_t
row_merge_build_indexes(
    // ... ...
    )
{
	merge_files = static_cast<merge_file_t*>(
		ut_malloc_nokey(n_indexes * sizeof *merge_files));

	/* Initialize all the merge file descriptors, so that we
	don't call row_merge_file_destroy() on uninitialized
	merge file descriptor */

	for (i = 0; i < n_indexes; i++) {
		merge_files[i].fd = -1;
	}
    // ... ...
}
```

入口函数： `row_merge_build_indexes()` 

1. 初始化merge_block: ` block = alloc.allocate_large(3 * srv_sort_buf_size, &block_pfx)` 
2. 初始化每个new_index的merge_files
3. Read clustered index of the table and create files for secondary index entries for merge sort. `row_merge_read_clustered_index()` 
   1. 初始化每个new_index的merge_buf。 `merge_buf[i] = row_merge_buf_create(index[i])` 
   2. 定位到old_table 的 clust_index的第一条记录，用于全表扫描。 `btr_pcur_open_at_index_side()` 
   3. 对于需要rebuild table 的情况，需要判断是不是有从nullable的列变成了notnull的列的情况（保存到nonnull数组中），后序全表扫描时如果遇到NULL值且改成了notnull，会报错。
   4. _**BEGIN**_: Scan the clustered index.
   5. 如果是online，需要MVCC读。 `row_vers_build_for_consistent_read()` 
   6. 从old rec中读取数据到dtuple中，**rec -> row**，这里读出来的row是对应于new_table的（注意add_cols参数）: `row_build_w_add_vcol()` 
   7. 判断old rec是否是NULL值
   8. **write_buffers.**** **遍历每个new_index，对于rebuild table的情况来说，new_index是所有新的index；对于不需要rebuild table的情况来说，new_index只包含了新add的index（每个new_index都需要写一份merge_buffer）
      1. 写入数据到new_index对应的merge_buff，**row -> merge_buff**。 `row_merge_buf_add()` 
         1. **对于compact->redundant的DD****L**，且 `col->mtype == DATA_MYSQL && col->len != field->len` 的情况，由于CHAR(X)在compact下可能是变长字段，在redundant下是定长字段（数据填0），需要转换格式： `row_merge_buf_redundant_convert()` 
         2. 同时在该函数中会计算该条记录的data_size，并判断 `buf->total_size + data_size >= srv_sort_buf_size - 1` 保证写入merge_buffer中的数据不会超过 `srv_sort_buf_size - 1` 的大小。（最后1字节用作chunk结束符号）
      2. **_if merge_buff full_**
      3. 当merge_buff满了之后，对merge_buff处理
         1. skip_sort: 不需要写merge file，直接写index。 `row_merge_insert_index_tuples()` 
         2. unique index: 去重+merge_buffer排序。 `row_merge_buf_sort(buf, &dup)` 
         3. other: merge_buffer排序。 `row_merge_buf_sort(buf, NULL)` 
      4. merge_buff sort完成后，写merge_file：Secondary index and clustered index which is not in sorted order can use the temporary file. Fulltext index should not use the temporary file.
         1. `row_merge_file_create_if_needed()` 
         2. **merge_buff -> block** (merge_file的格式参考该函数): `row_merge_buf_write(buf, file, block)` （因为写merge_buff的流程已经确保了merge_buff中的数据不会超过srv_sort_buf_size大小，因此这里不用考虑block大小的问题）
            1. `row_merge_buf_encode()` 
               1. `rec_convert_dtuple_to_temp()` 
         3. **block -> merge_file**: `row_merge_write()` 
      5. **_end if_**
   9. _**NEXT**_ clustered index rec -> d
4. Now we have files containing index entries ready for sorting and inserting. `for (i = 0; i < n_indexes; i++) {...}` 
   1. 对merge_file进行排序，merge_file的每个chunk内是有序的（已经排序过了），使用归并排序：`row_merge_sort()` 
   2. merge_file写入new_index `row_merge_insert_index_tuples()` 


row_merge_insert_index_tuples() 函数根据参数的不同，可以从row_merge_buff或row_merge_file中读取数据并写到指定的index中。
从row_merge_buff写入index流程：

1. 根据index初始化dtuple： `dtuple_create()` / `dtuple_set_n_fields_cmp()` 
2. 遍历每条记录
3. mtuple_t->dtuple_t，Convert merge tuple record from row buffer to data tuple record. `row_merge_mtuple_to_dtuple()` 
4. 处理ext //todo
5. `btr_bulk->insert(dtuple)` 

从row_merge_file写入index流程：

1. 从row_merge_file中读取数据到row_merge_block_t中： `row_merge_read(fd, foffs, block)` 
2. 遍历每条记录
3. block -> mrec_t: `row_merge_read_rec()` 
4. mrec_t -> dtuple_t: `row_rec_to_index_entry_low()` 
5. 略


**merge_file的格式：**
![image.png](https://cdn.nlark.com/yuque/0/2020/png/385742/1597940595936-72783ab5-e919-4542-9e11-232ec6c35538.png#align=left&display=inline&height=232&originHeight=464&originWidth=1696&size=41249&status=done&style=none&width=848)
merge_block大小相关的值srv_sort_buf_size由参数 `[innodb_sort_buffer_size](https://dev.mysql.com/doc/refman/5.7/en/innodb-parameters.html#sysvar_innodb_sort_buffer_size)` 定义

| Property | Value |
| --- | --- |
| Command-Line Format | `--innodb-sort-buffer-size=#` |
| System Variable | `[innodb_sort_buffer_size](https://dev.mysql.com/doc/refman/5.7/en/innodb-parameters.html#sysvar_innodb_sort_buffer_size)` |
| Scope | Global |
| Dynamic | No |
| Type | Integer |
| Default Value | `1048576` |
| Minimum Value | `65536` |
| Maximum Value | `67108864` |

Specifies the size of sort buffers used to sort data during creation of an `InnoDB` index. The specified size defines the amount of data that is read into memory for internal sorting and then written out to disk. This process is referred to as a “run”. During the merge phase, pairs of buffers of the specified size are read and merged. The larger the setting, the fewer runs and merges there are.

This sort area is only used for merge sorts during index creation, not during later index maintenance operations. Buffers are deallocated when index creation completes.

The value of this option also controls the amount by which the temporary log file is extended to record concurrent DML during [online DDL](https://dev.mysql.com/doc/refman/5.7/en/glossary.html#glos_online_ddl) operations.


Before this setting was made configurable, the size was hardcoded to 1048576 bytes (1MB), which remains the default.


During an [`ALTER TABLE`](https://dev.mysql.com/doc/refman/5.7/en/alter-table.html) or [`CREATE TABLE`](https://dev.mysql.com/doc/refman/5.7/en/create-table.html) statement that creates an index, 3 buffers are allocated, each with a size defined by this option. Additionally, auxiliary pointers are allocated to rows in the sort buffer so that the sort can run on pointers (as opposed to moving rows during the sort operation).


For a typical sort operation, a formula such as this one can be used to estimate memory consumption:
```
(6 /*FTS_NUM_AUX_INDEX*/ * (3*@@GLOBAL.innodb_sort_buffer_size)
+ 2 * number_of_partitions * number_of_secondary_indexes_created
* (@@GLOBAL.innodb_sort_buffer_size/dict_index_get_min_size(index)*/)
* 8 /*64-bit sizeof *buf->tuples*/")
```

`@@GLOBAL.innodb_sort_buffer_size/dict_index_get_min_size(index)` indicates the maximum tuples held. `2 * (@@GLOBAL.innodb_sort_buffer_size/*dict_index_get_min_size(index)*/) * 8 /*64-bit size of *buf->tuples*/` indicates auxiliary pointers allocated.

> **Note**
For 32-bit, multiply by 4 instead of 8.


For parallel sorts on a full-text index, multiply by the [`innodb_ft_sort_pll_degree`](https://dev.mysql.com/doc/refman/5.7/en/innodb-parameters.html#sysvar_innodb_ft_sort_pll_degree) setting:
```
(6 /*FTS_NUM_AUX_INDEX*/ * @@GLOBAL.innodb_ft_sort_pll_degree)
```


### row0log
```cpp
/** @brief Buffer for logging modifications during online index creation

All modifications to an index that is being created will be logged by
row_log_online_op() to this buffer.

All modifications to a table that is being rebuilt will be logged by
row_log_table_delete(), row_log_table_update(), row_log_table_insert()
to this buffer.

When head.blocks == tail.blocks, the reader will access tail.block
directly. When also head.bytes == tail.bytes, both counts will be
reset to 0 and the file will be truncated. */
struct row_log_t {
	int		fd;	/*!< file descriptor */
	ib_mutex_t	mutex;	/*!< mutex protecting error,
				max_trx and tail */
	page_no_map*	blobs;	/*!< map of page numbers of off-page columns
				that have been freed during table-rebuilding
				ALTER TABLE (row_log_table_*); protected by
				index->lock X-latch only */
	dict_table_t*	table;	/*!< table that is being rebuilt,
				or NULL when this is a secondary
				index that is being created online */
	bool		same_pk;/*!< whether the definition of the PRIMARY KEY
				has remained the same */
	const dtuple_t*	add_cols;
				/*!< default values of added columns, or NULL */
	const ulint*	col_map;/*!< mapping of old column numbers to
				new ones, or NULL if !table */
	dberr_t		error;	/*!< error that occurred during online
				table rebuild */
	trx_id_t	max_trx;/*!< biggest observed trx_id in
				row_log_online_op();
				protected by mutex and index->lock S-latch,
				or by index->lock X-latch only */
	row_log_buf_t	tail;	/*!< writer context;
				protected by mutex and index->lock S-latch,
				or by index->lock X-latch only */
	row_log_buf_t	head;	/*!< reader context; protected by MDL only;
				modifiable by row_log_apply_ops() */
	ulint		n_old_col;
				/*!< number of non-virtual column in
				old table */
	ulint		n_old_vcol;
				/*!< number of virtual column in old table */
	const char*	path;	/*!< where to create temporary file during
				log operation */
};
```
```cpp
/** Log block for modifications during online ALTER TABLE */
struct row_log_buf_t {
	byte*		block;	/*!< file block buffer */
	ut_new_pfx_t	block_pfx; /*!< opaque descriptor of "block". Set
				by ut_allocator::allocate_large() and fed to
				ut_allocator::deallocate_large(). */
	mrec_buf_t	buf;	/*!< buffer for accessing a record
				that spans two blocks */
	ulint		blocks; /*!< current position in blocks */
	ulint		bytes;	/*!< current position within block */
	ulonglong	total;	/*!< logical position, in bytes from
				the start of the row_log_table log;
				0 for row_log_online_op() and
				row_log_apply(). */
};
```

`row_log_t` 通过 `row_log_t::head` 和 `row_log_t::tail` 管理row log，row log temp file以block为单位组织，每个block大小为 `srv_sort_buf_size` ；tail指向row log temp file的结尾位置，head指向开头位置，在apply的时候会更新head。

- 对于add index类型的DDL，每个新加的index（共有 `ctx->num_to_add_index` 个）都会生成一个 `row_log_t` 结构，保存在 `ctx->add_index[i]->online_log` 中；
- 对于需要rebuild table的情况，只需要一个old_clustered_index对应的 `row_log_t` ，保存在 `old_clust_index->online_log` 中

`row_log_buf_t` 中的相关变量意义如下：

- block: 用于读取row log temp file时候的缓存，每次读取一个block大小
- buf: 当一条mrec跨越了两个block时，需要把两部分数据都copy到buf中
- blocks: 以block为单位的偏移
- bytes: block内的偏移

![image.png](https://cdn.nlark.com/yuque/0/2020/png/385742/1597766577657-487ba8fa-152e-49c2-ba09-25441a5129ca.png#align=left&display=inline&height=221&originHeight=442&originWidth=1526&size=27229&status=done&style=none&width=763)
rowlog file的大小由参数 `[innodb_online_alter_log_max_size](https://dev.mysql.com/doc/refman/5.7/en/innodb-parameters.html#sysvar_innodb_online_alter_log_max_size)` 控制

| Property | Value |
| --- | --- |
| Command-Line Format | `--innodb-online-alter-log-max-size=#` |
| System Variable | `[innodb_online_alter_log_max_size](https://dev.mysql.com/doc/refman/5.7/en/innodb-parameters.html#sysvar_innodb_online_alter_log_max_size)` |
| Scope | Global |
| Dynamic | Yes |
| Type | Integer |
| Default Value | `134217728` |
| Minimum Value | `65536` |
| Maximum Value | `2**64-1` |

Specifies an upper limit in bytes on the size of the temporary log files used during [online DDL](https://dev.mysql.com/doc/refman/5.7/en/glossary.html#glos_online_ddl) operations for `InnoDB` tables. There is one such log file for each index being created or table being altered. This log file stores data inserted, updated, or deleted in the table during the DDL operation. 
The temporary log file is extended when needed by the value of [`innodb_sort_buffer_size`](https://dev.mysql.com/doc/refman/5.7/en/innodb-parameters.html#sysvar_innodb_sort_buffer_size), up to the maximum specified by [`innodb_online_alter_log_max_size`](https://dev.mysql.com/doc/refman/5.7/en/innodb-parameters.html#sysvar_innodb_online_alter_log_max_size). If a temporary log file exceeds the upper size limit, the [`ALTER TABLE`](https://dev.mysql.com/doc/refman/5.7/en/alter-table.html) operation fails and all uncommitted concurrent DML operations are rolled back. Thus, a large value for this option allows more DML to happen during an online DDL operation, but also extends the period of time at the end of the DDL operation when the table is locked to apply the data from the log.


需要rebuild table情况下三种row log类型：

- DELETE: `row_log_table_delete(rec, ventry, index, offsets, sys)` ; rec: clustered index leaf page record, page X-latched.
   - `btr_cur_del_mark_set_clust_rec()` 
      - **DELETE**** :** `row_upd_del_mark_clust_rec()` 
      - **UPDATE by DELETE-MARK and INSERT**:  `row_upd_clust_rec_by_insert()` 
      - `row_explicit_rollback()` : insert 失败时的rollback操作
   - **UNDO INSERT****:** `row_undo_ins_remove_clust_rec()` <- `row_undo_ins()` <- `row_undo()` 
   - **UNDO UPD DEL REC****:** `row_undo_mod_clust()` ( `node->rec_type == TRX_UNDO_UPD_DEL_REC` )  <- `row_undo_mod()` <- `row_undo()`
- UPDATE: `row_log_table_update(rec, index, offsets, old_pk, new_v_row, old_v_row)` ; rec: new clustered index leaf page record.
   - **UPDATE**: `row_upd_clust_rec()` 
   - **UNDO UPD EXIST REC**: `row_undo_mod_clust()` (`node->rec_type == TRX_UNDO_UPD_EXIST_REC`)
- INSERT: `row_log_table_insert(rec, ventry, index, offsets)` 
   - **INSERT**: `row_ins_clust_index_entry_low()` / `row_ins_index_entry_big_rec_func()` 
   - **UNDO DEL MARK REC**: `row_undo_mod_clust()` (`node->rec_type == TRX_UNDO_DEL_MARK_REC`)

sec index creating op log:

- `row_log_online_op(index, tuple, trx_id)` ; Logs an operation to a secondary index that is (or was) being created. tuple: index tuple

log apply:

- `row_log_table_apply(thr, old_table, table, stage)` 
- `row_log_apply(trx, index, table, stage)`  


undo中涉及到rowlog的逻辑：
```cpp
row_undo_step()
	row_undo()
		row_undo_mod()
			row_undo_mod_clust()
    			TRX_UNDO_UPD_DEL_REC: row_log_table_delete()
    			TRX_UNDO_UPD_EXIST_REC: row_log_table_update()
    			TRX_UNDO_DEL_MARK_REC: row_log_table_insert()
    	row_undo_ins()
    		row_undo_ins_remove_clust_rec()
    			row_log_table_delete()
```

#### row log format
##### delete
![image.png](https://cdn.nlark.com/yuque/0/2020/png/385742/1597755121516-25f67def-1269-437a-a0f4-1c668dc3da94.png#align=left&display=inline&height=212&originHeight=424&originWidth=2002&size=58506&status=done&style=none&width=1001)
> TIPS：
> - temp record format 基于compact row format，只是没有hdr信息
> - 如果原记录是compact且是Instant的，temp record 会增加一个字节存储info_bits（其实是为了instant flag信息）（INSTANT ADD COLUMN特性新增）


row_ext_t的结构如下，其初始化逻辑可以参考 `row_ext_create()` 函数，malloc时会分配 `(sizeof *ret) + (n_ext - 1) * sizeof ret->len)` 大小的空间，多malloc的空间表示len[1] - len[n_ext - 1]。
```cpp
/** Prefixes of externally stored columns */
struct row_ext_t{
	ulint		n_ext;	/*!< number of externally stored columns */
	const ulint*	ext;	/*!< col_no's of externally stored columns */
	byte*		buf;	/*!< backing store of the column prefix cache */
	ulint		max_len;/*!< maximum prefix length, it could be
				REC_ANTELOPE_MAX_INDEX_COL_LEN or
				REC_VERSION_56_MAX_INDEX_COL_LEN depending
				on row format */
	page_size_t	page_size;
				/*!< page size of the externally stored
				columns */
	ulint		len[1];	/*!< prefix lengths; 0 if not cached */
};
```

##### insert
![image.png](https://cdn.nlark.com/yuque/0/2020/png/385742/1598608292822-dffde7e8-c5d6-43ee-ab3d-eff71193bdd2.png#align=left&display=inline&height=201&originHeight=402&originWidth=1362&size=35966&status=done&style=none&width=681)
这里的new temp rec实际上不是通过 `rec_convert_dtuple_to_temp()` 函数得到的，而是直接copy除了hdr外的数据得到（temp rec于compact rec相比，少了hdr信息，其他部分一样） 。
```cpp
row_log_table_low(//...)
{
    // ... ...
    	/* Check the instant to decide copying info bit or not */
	omit_size = REC_N_NEW_EXTRA_BYTES -
		(index->has_instant_cols() ? REC_N_TMP_EXTRA_BYTES : 0);

	extra_size = rec_offs_extra_size(offsets) - omit_size;
    
    // row_log_table_open:
		memcpy(b, rec - rec_offs_extra_size(offsets), extra_size);
		b += extra_size;
		memcpy(b, rec, rec_offs_data_size(offsets));
		b += rec_offs_data_size(offsets);
    // ... ...
}
```
![image.png](https://cdn.nlark.com/yuque/0/2020/png/385742/1598608224937-261fb2bd-f88f-4185-a1b3-348d79eee7a5.png#align=left&display=inline&height=352&originHeight=704&originWidth=1724&size=82334&status=done&style=none&width=862)


##### update
![image.png](https://cdn.nlark.com/yuque/0/2020/png/385742/1598608313301-b7d70920-f134-4b03-a48f-8e4fc6f8c4eb.png#align=left&display=inline&height=201&originHeight=402&originWidth=1762&size=48888&status=done&style=none&width=881)

如果是没有更改pk（index->online_log->same_pk），就不会有old_pk_extra_size和old_pk_temp_rec两个字段，不更改pk的情况有以下2种：

- add sec index (not need rebuild table, 应该不会写update row log，而是写op row log)
- rebuild table and `!(ha_alter_info->handler_flags & Alter_inplace_info::ADD_PK_INDEX`  (ref: `prepare_inplace_alter_table_dict()` )

#### sec index online op log
// todo `row_log_online_op()` 

#### row log apply
函数调用关系：

- row_log_table_apply()
   - row_log_table_apply_ops()
      - read every log block: `os_file_read_no_error_handling_int_fd()` 
      - row_log_table_apply_op()
         - ROW_T_INSERT: `row_log_table_apply_insert()` -> `row_log_table_apply_insert_low()` 
            - mrec -> row (同时处理ext): `row_log_table_apply_convert_mrec()` 
            - clust index: 
               - `entry = row_build_index_entry()` 
               - `row_ins_clust_index_entry_low(entry, ...)` 
            - for every sec index: ...
         - ROW_T_DELETE: `row_log_table_apply_delete()` 
            - btr_cur_pessimistic_delete()
         - ROW_T_UPDATE: `row_log_table_apply_update()` 

注意这里处理一个mrec跨越block情况的代码：
```cpp
		} else {
			memcpy(index->online_log->head.buf, mrec,
			       mrec_end - mrec);
			mrec_end += index->online_log->head.buf - mrec;
			mrec = index->online_log->head.buf;
			goto process_next_block;
		}
```

### ⭐️row log apply with ext when rollback
row log中并没有存ext字段的offpage数据，事务rollback或delete数据后offpage会被删除，等到apply row log的时候会找不到offpage数据。这时候会跳过这个log，但是跳过之后会造成old rec中的TRX_ID和ROLL_PTR和log中记录的不一样

**INSERT**

- **DB_MISSING_HISTORY**: Because some BLOBs are missing, we know that the transaction was rolled back later (a rollback of an insert can free BLOBs). We can simply skip the insert: the subsequent ROW_T_DELETE will be ignored, or a ROW_T_UPDATE will be interpreted as ROW_T_INSERT.
- insert

e.g. 1. 
BEGIN;
INSERT INTO t SET blob_col='blob value';
ROLLBACK;
row log: 
ROW_T_INSERT
ROW_T_DELETE
因为rollback删除了offpage数据，回放第1个ROW_T_INSERT时因为找不到offpage数据，会得到DB_MISSING_HISTORY错误，然后跳过这个insert；回放第2个ROW_T_DELETE时，找不到该条记录，然后直接返回成功。

BEGIN; INSERT; UPDATE; ROLLBACK的例子在下面UPDATE一节详述。


**DELETE**

- **The record was not found****:** This should only happen when an earlier ROW_T_INSERT was skipped or ROW_T_UPDATE was interpreted as ROW_T_DELETE due to BLOBs having been freed by rollback. All done（ignored）
- **The ROW_T_DELETE was logged for a different PRIMARY KEY,DB_TRX_ID,DB_ROLL_PTR**. This is possible if a ROW_T_INSERT was skipped or a ROW_T_UPDATE was interpreted as ROW_T_DELETE because some BLOBs were missing due to 

	(1) rolling back the initial insert, or 
	(2) purging the BLOB for a later ROW_T_DELETE 
	(3) purging 'old values' for a later ROW_T_UPDATE or ROW_T_DELETE.
All done（ignored）

- delete

**UPDATE**

- **DB_MISSING_HISTORY**: The record contained BLOBs that are now missing. Whether or not we are updating the PRIMARY KEY, we know that there should be a subsequent ROW_T_DELETE for rolling back a preceding ROW_T_INSERT, overriding this ROW_T_UPDATE record. (*1)

This allows us to interpret this ROW_T_UPDATE as ROW_T_DELETE.
When applying the subsequent ROW_T_DELETE, no matching record will be found. 
Fall through. continue.

- DB_SUCCESS: continue
- **The record was not found**. This should only happen when an earlier ROW_T_INSERT or ROW_T_UPDATE was diverted because BLOBs were freed when the insert was later rolled back.
   - **error == DB_SUCCESS**: An earlier ROW_T_INSERT could have been skipped because of a missing BLOB, like this:

BEGIN;
INSERT INTO t SET blob_col='blob value';
UPDATE t SET blob_col='';
ROLLBACK;

This would generate the following records:
ROW_T_INSERT (referring to 'blob value')
ROW_T_UPDATE
ROW_T_UPDATE (referring to 'blob value')
ROW_T_DELETE
[ROLLBACK removes the 'blob value']

The ROW_T_INSERT would have been skipped because of a missing BLOB. Now we are executing the first ROW_T_UPDATE. The second ROW_T_UPDATE (for the ROLLBACK) would be interpreted as ROW_T_DELETE, because the BLOB would be missing.

We could probably assume that the transaction has been rolled back and simply skip the 'insert' part of this ROW_T_UPDATE record. However, there might be some complex scenario that could interfere with such a shortcut. So, we will insert the row (and risk introducing a bogus duplicate key error for the ALTER TABLE), and a subsequent ROW_T_UPDATE or ROW_T_DELETE will delete it. return  `error = row_log_table_apply_insert_low()` 

   - **error == DB_MISSING_HISTORY**: Some BLOBs are missing, so we are interpreting this ROW_T_UPDATE as ROW_T_DELETE (see *1). Because the record was not found, we do nothing. return  `error = DB_SUCCESS` 
- **The ROW_T_UPDATE was logged for a different DB_TRX_ID,DB_ROLL_PTR**. This is possible if an earlier ROW_T_INSERT or ROW_T_UPDATE was diverted because some BLOBs were missing due to rolling back the initial insert or due to purging the old BLOB values of an update.
   - **error = DB_MISSING_HISTORY**: Some BLOBs are missing, so we are interpreting this ROW_T_UPDATE as ROW_T_DELETE (see *1). Because this is a different row, we will do nothing. return `error = DB_SUCCESS` 
   - **error == DB_SUCCESS**: Because the user record is missing due to BLOBs that were missing when processing an earlier log record, we should interpret the ROW_T_UPDATE as ROW_T_INSERT. However, there is a different user record with the same PRIMARY KEY value already. return `error = DB_DUPLICATE_KEY` 
- **error == ****DB_MISSING_HISTORY**: Some BLOBs are missing, so we are interpreting this ROW_T_UPDATE as ROW_T_DELETE (see *1). `row_log_table_apply_delete_low()` 
- **If the record contains any externally stored columns**, perform the update by delete and insert, because we will not write any undo log that would allow purge to free any orphaned externally stored columns. `row_log_table_apply_delete_low()` and `row_log_table_apply_insert_low()` 
- Other: `row_log_table_apply_insert_low()` 

## Commit Inplace Alter Table

1. **Exclusively lock the table**, to ensure that no other transaction is holding locks on the table while we change the table definition. The MySQL meta-data lock should normally guarantee that no conflicting locks exist. However, FOREIGN KEY constraints checks and any transactions collected during crash recovery could be holding InnoDB locks only, not MySQL locks. `row_merge_lock_table(m_prebuilt->trx, ctx->old_table, LOCK_X)` 
2. **开启一个事务用于更新dict：** `trx_start_for_ddl(trx, TRX_DICT_OP_INDEX)` 
3. Latch the InnoDB data dictionary exclusively so that no deadlocks or lock waits can happen in it during the data dictionary operation. `row_mysql_lock_data_dictionary(trx)` 
4. need rebuild: `commit_try_rebuild()` 
   1. Clear the to_be_dropped flag in the data dictionary cache of user_table. `index->to_be_dropped = 0;` 
   2. Apply any last bit of the rebuild log. 这里是第二次apply table log，在这里已经lock table了，第一次是在 `row_log_table_apply()` 
   3. We can now rename the old table as a temporary table, rename the new temporary table as the old table and drop the old table. First, we only do this in the data dictionary tables. The actual renaming will be performed in commit_cache_rebuild(), once the data dictionary transaction has been successfully committed. `row_merge_rename_tables_dict()` 
5. not need rebuild: `commit_try_norebuild()` 
   - ADD INDEX: 删除index name的 `TEMP_INDEX_PREFIX_STR` 前缀 `row_merge_rename_index_to_add()`
   - DROP INDEX: 需要drop的index name添加 `TEMP_INDEX_PREFIX_STR` 前缀 `row_merge_rename_index_to_drop()`
   - ALTER_COLUMN_NAME: `innobase_rename_columns_try()`
   - ALTER_COLUMN_EQUAL_PACK_LENGTH: `innobase_enlarge_columns_try()`
   - RENAME_INDEX: `rename_indexes_in_data_dictionary()`
   - DROP_VIRTUAL_COLUMN: `innobase_drop_virtual_try()`
   - ADD_VIRTUAL_COLUMN: `innobase_add_virtual_try()`
6. Commit or roll back the changes to the data dictionary.
7. Flush the log to reduce probability that the .frm files and the InnoDB data dictionary get out-of-sync if the user runs with innodb_flush_log_at_trx_commit = 0. `log_buffer_flush_to_disk()` 
8. At this point, the changes to the persistent storage have been committed or rolled back. What remains to be done is to update the in-memory structures, close some handles, release temporary files, and (unless we rolled back) update persistent statistics.
   1. Free the modification log for online table rebuild. `innobase_online_rebuild_log_free()` 
9. **Release the table locks.** `trx_commit_for_mysql(m_prebuilt->trx)` 
10. Drop the copy of the old table, which was renamed to ctx->tmp_name at the atomic DDL transaction commit.  If the system crashes before this is completed, some orphan tables with ctx->tmp_name may be recovered. `row_merge_drop_table(trx, ctx->old_table)` 
11. Unlocks the data dictionary exclusive lock. `row_mysql_unlock_data_dictionary(trx)` 

# Other
## Online DDL Space Requirements
Online DDL operations have the following space requirements:

- Space for temporary log files
A temporary log file records concurrent DML when an online DDL operation creates an index or alters a table. The temporary log file is extended as required by the value of [`innodb_sort_buffer_size`](https://dev.mysql.com/doc/refman/5.7/en/innodb-parameters.html#sysvar_innodb_sort_buffer_size) up to a maximum specified by [`innodb_online_alter_log_max_size`](https://dev.mysql.com/doc/refman/5.7/en/innodb-parameters.html#sysvar_innodb_online_alter_log_max_size). If a temporary log file exceeds the size limit, the online DDL operation fails, and uncommitted concurrent DML operations are rolled back. A large [`innodb_online_alter_log_max_size`](https://dev.mysql.com/doc/refman/5.7/en/innodb-parameters.html#sysvar_innodb_online_alter_log_max_size) setting permits more DML during an online DDL operation, but it also extends the period of time at the end of the DDL operation when the table is locked to apply logged DML.
If the operation takes a long time and concurrent DML modifies the table so much that the size of the temporary log file exceeds the value of [`innodb_online_alter_log_max_size`](https://dev.mysql.com/doc/refman/5.7/en/innodb-parameters.html#sysvar_innodb_online_alter_log_max_size), the online DDL operation fails with a `DB_ONLINE_LOG_TOO_BIG` error.

- Space for temporary sort files
Online DDL operations that rebuild the table write temporary sort files to the MySQL temporary directory (`$TMPDIR` on Unix, `%TEMP%` on Windows, or the directory specified by [`--tmpdir`](https://dev.mysql.com/doc/refman/5.7/en/server-system-variables.html#sysvar_tmpdir)) during index creation. Temporary sort files are not created in the directory that contains the original table. Each temporary sort file is large enough to hold one column of data, and each sort file is removed when its data is merged into the final table or index. Operations involving temporary sort files may require temporary space equal to the amount of data in the table plus indexes. An error is reported if online DDL operation uses all of the available disk space on the file system where the data directory resides.
If the MySQL temporary directory is not large enough to hold the sort files, set [`tmpdir`](https://dev.mysql.com/doc/refman/5.7/en/server-system-variables.html#sysvar_tmpdir) to a different directory. Alternatively, define a separate temporary directory for online DDL operations using [`innodb_tmpdir`](https://dev.mysql.com/doc/refman/5.7/en/innodb-parameters.html#sysvar_innodb_tmpdir). This option was introduced in MySQL 5.7.11 to help avoid temporary directory overflows that could occur as a result of large temporary sort files.

- Space for an intermediate table file
Some online DDL operations that rebuild the table create a temporary intermediate table file in the same directory as the original table. An intermediate table file may require space equal to the size of the original table. Intermediate table file names begin with `#sql-ib` prefix and only appear briefly during the online DDL operation.
The [`innodb_tmpdir`](https://dev.mysql.com/doc/refman/5.7/en/innodb-parameters.html#sysvar_innodb_tmpdir) option is not applicable to intermediate table files.

## Online DDL and Metadata Locks
Online DDL operations can be viewed as having three phases:

- _Phase 1: Initialization_
In the initialization phase, the server determines how much concurrency is permitted during the operation, taking into account storage engine capabilities, operations specified in the statement, and user-specified `ALGORITHM` and `LOCK` options. During this phase, a shared upgradeable metadata lock is taken to protect the current table definition.

- _Phase 2: Execution_
In this phase, the statement is prepared and executed. Whether the metadata lock is upgraded to exclusive depends on the factors assessed in the initialization phase. If an exclusive metadata lock is required, it is only taken briefly during statement preparation.

- _Phase 3: Commit Table Definition_
In the commit table definition phase, the metadata lock is upgraded to exclusive to evict the old table definition and commit the new one. Once granted, the duration of the exclusive metadata lock is brief.


Due to the exclusive metadata lock requirements outlined above, an online DDL operation may have to wait for concurrent transactions that hold metadata locks on the table to commit or rollback. Transactions started before or during the DDL operation can hold metadata locks on the table being altered. In the case of a long running or inactive transaction, an online DDL operation can time out waiting for an exclusive metadata lock. Additionally, a pending exclusive metadata lock requested by an online DDL operation blocks subsequent transactions on the table.
