mysql-server版本: 5.7.24

MySQL一条query的执行过程
```java
(gdb) bt
#0  ha_innobase::index_first (this=0x7fff9801a780, buf=0x7fff9801ab90 "") at /root/mysql-server/storage/innobase/handler/ha_innodb.cc:9141
#1  0x0000000001983b29 in ha_innobase::rnd_next (this=0x7fff9801a780, buf=0x7fff9801ab90 "") at /root/mysql-server/storage/innobase/handler/ha_innodb.cc:9243
#2  0x0000000000f2be6f in handler::ha_rnd_next (this=0x7fff9801a780, buf=0x7fff9801ab90 "") at /root/mysql-server/sql/handler.cc:2947
#3  0x0000000001458e24 in rr_sequential (info=0x7fff9801cc48) at /root/mysql-server/sql/records.cc:510
#4  0x00000000014f0c44 in join_init_read_record (tab=0x7fff9801cbf8) at /root/mysql-server/sql/sql_executor.cc:2484
#5  0x00000000014ede81 in sub_select (join=0x7fff9801c630, qep_tab=0x7fff9801cbf8, end_of_records=false) at /root/mysql-server/sql/sql_executor.cc:1277
#6  0x00000000014ed814 in do_select (join=0x7fff9801c630) at /root/mysql-server/sql/sql_executor.cc:950
#7  0x00000000014eb77b in JOIN::exec (this=0x7fff9801c630) at /root/mysql-server/sql/sql_executor.cc:199
#8  0x000000000158460e in handle_query (thd=0x7fff98000b70, lex=0x7fff98002e88, result=0x7fff980070d0, added_options=0, removed_options=0) at /root/mysql-server/sql/sql_select.cc:184
#9  0x000000000153a41f in execute_sqlcom_select (thd=0x7fff98000b70, all_tables=0x7fff980067c8) at /root/mysql-server/sql/sql_parse.cc:5144
#10 0x0000000001533e3d in mysql_execute_command (thd=0x7fff98000b70, first_level=true) at /root/mysql-server/sql/sql_parse.cc:2816
#11 0x000000000153b382 in mysql_parse (thd=0x7fff98000b70, parser_state=0x7fffdc37f690) at /root/mysql-server/sql/sql_parse.cc:5570
#12 0x0000000001530c93 in dispatch_command (thd=0x7fff98000b70, com_data=0x7fffdc37fdf0, command=COM_QUERY) at /root/mysql-server/sql/sql_parse.cc:1484
#13 0x000000000152fafc in do_command (thd=0x7fff98000b70) at /root/mysql-server/sql/sql_parse.cc:1025
#14 0x0000000001660328 in handle_connection (arg=0x3659310) at /root/mysql-server/sql/conn_handler/connection_handler_per_thread.cc:300
#15 0x00000000018f73b9 in pfs_spawn_thread (arg=0x359f900) at /root/mysql-server/storage/perfschema/pfs.cc:2190
#16 0x00007ffff7bc6dc5 in start_thread () from /lib64/libpthread.so.0
#17 0x00007ffff668321d in clone () from /lib64/libc.so.6
```

```java
|connection_handler_per_thread.cc	sql_parse.cc				sql_select.cc		sql_resolver.cc		sql_optimizer.cc	sql_executor.cc	records.cc	handler.cc	ha_innodb.cc
|-----------------------------------|---------------------------|-------------------|-------------------|-------------------|---------------|-----------|-----------
|handle_connection					|							|					|					|					|				|			|				
|-do_command						|							|					|					|					|				|			|			
|									|dispatch_command			|					|					|					|				|			|			
|									|mysql_parse				|					|					|					|				|			|			
|									|-parse_sql					|					|					|					|				|			|			
|									|-mysql_execute_command		|					|					|					|				|			|			
|									|--execute_sqlcom_select	|					|					|					|				|			|			
|									|							|handle_query		|					|					|				|			|			
|									|							|-prepare			|					|					|				|			|			
|									|							|					|SELECT_LEX::prepare|					|				|			|			
|									|							|-optimize			|					|					|				|			|			
|									|							|					|					|JOIN::optimize()	|				|			|			
|									|							|-JOIN::exec		|					|					|				|			|
|									|							|					|					|					|				|			|
```

**sql_parse.cc**```cpp
/**
  Perform one connection-level (COM_XXXX) command.
  @param thd             connection handle
  @param command         type of command to perform
  @com_data              com_data union to store the generated command
  @todo
    set thd->lex->sql_command to SQLCOM_END here.
  @todo
    The following has to be changed to an 8 byte integer
  @retval
    0   ok
  @retval
    1   request of thread shutdown, i. e. if command is
        COM_QUIT/COM_SHUTDOWN
*/
bool dispatch_command(THD *thd, const COM_DATA *com_data, enum enum_server_command command)
{
  // ... ...
  switch (command) {
  // .... ...
  case COM_QUERY:
  {
    DBUG_ASSERT(thd->m_digest == NULL);
    thd->m_digest= & thd->m_digest_state;
    thd->m_digest->reset(thd->m_token_array, max_digest_length);
 
    // Read query from packet and store in thd->query. Used in COM_QUERY and COM_STMT_PREPARE.
    if (alloc_query(thd, com_data->com_query.query, com_data->com_query.length))
      break;					// fatal error is set
    MYSQL_QUERY_START(const_cast<char*>(thd->query().str), thd->thread_id(),
                      (char *) (thd->db().str ? thd->db().str : ""),
                      (char *) thd->security_context()->priv_user().str,
                      (char *) thd->security_context()->host_or_ip().str);
    const char *packet_end= thd->query().str + thd->query().length;
    if (opt_general_log_raw)
      query_logger.general_log_write(thd, command, thd->query().str,
                                     thd->query().length);
    DBUG_PRINT("query",("%-.4096s", thd->query().str));
#if defined(ENABLED_PROFILING)
    thd->profiling.set_query_source(thd->query().str, thd->query().length);
#endif
    Parser_state parser_state;
    if (parser_state.init(thd, thd->query().str, thd->query().length))
      break;
    mysql_parse(thd, &parser_state);
	// ... ...
    }
  // ... ...
  }
 // ... ...
}
```

```cpp
/*
  When you modify mysql_parse(), you may need to mofify
  mysql_test_parse_for_slave() in this same file.
*/
/**
  Parse a query.
  @param       thd     Current thread
  @param       rawbuf  Begining of the query text
  @param       length  Length of the query text
  @param[out]  found_semicolon For multi queries, position of the character of
                               the next query in the query text.
*/
void mysql_parse(THD *thd, Parser_state *parser_state)
{
  int error MY_ATTRIBUTE((unused));
  DBUG_ENTER("mysql_parse");
  DBUG_PRINT("mysql_parse", ("query: '%s'", thd->query().str));
  DBUG_EXECUTE_IF("parser_debug", turn_parser_debug_on(););
  /*
    Warning.
    The purpose of query_cache_send_result_to_client() is to lookup the
    query in the query cache first, to avoid parsing and executing it.
    So, the natural implementation would be to:
    - first, call query_cache_send_result_to_client,
    - second, if caching failed, initialise the lexical and syntactic parser.
    The problem is that the query cache depends on a clean initialization
    of (among others) lex->safe_to_cache_query and thd->server_status,
    which are reset respectively in
    - lex_start()
    - mysql_reset_thd_for_next_command()
    So, initializing the lexical analyser *before* using the query cache
    is required for the cache to work properly.
    FIXME: cleanup the dependencies in the code to simplify this.
  */
  mysql_reset_thd_for_next_command(thd);
  lex_start(thd);
  thd->m_parser_state= parser_state;
  invoke_pre_parse_rewrite_plugins(thd);
  thd->m_parser_state= NULL;
  enable_digest_if_any_plugin_needs_it(thd, parser_state);
  // 先去缓存里查，但因为缓存是只要有update就全部失效，一般不开启，这里可以忽略缓存
  if (query_cache.send_result_to_client(thd, thd->query()) <= 0)
  {
    LEX *lex= thd->lex;
    const char *found_semicolon;
    bool err= thd->get_stmt_da()->is_error();
    if (!err)
    {
      err= parse_sql(thd, parser_state, NULL);
      if (!err)
        err= invoke_post_parse_rewrite_plugins(thd, false);
      found_semicolon= parser_state->m_lip.found_semicolon;
    }
	// ... ...
  }
  // ... ...
}
```

```cpp
/**
  Execute command saved in thd and lex->sql_command.
  @param thd                       Thread handle
  @todo
    - Invalidate the table in the query cache if something changed
    after unlocking when changes become visible.
    @todo: this is workaround. right way will be move invalidating in
    the unlock procedure.
    - TODO: use check_change_password()
  @retval
    FALSE       OK
  @retval
    TRUE        Error
*/
int
mysql_execute_command(THD *thd, bool first_level)
{
  // ... ...
  switch (lex->sql_command) {
  // ... ...
  case SQLCOM_SHOW_COLLATIONS:
  case SQLCOM_SHOW_STORAGE_ENGINES:
  case SQLCOM_SHOW_PROFILE:
  case SQLCOM_SELECT:
  {
    DBUG_EXECUTE_IF("use_attachable_trx",
                    thd->begin_attachable_ro_transaction(););
    thd->clear_current_query_costs();
    res= select_precheck(thd, lex, all_tables, first_table);
    if (!res)
      res= execute_sqlcom_select(thd, all_tables);
  // ... ...
}
```


[https://blog.csdn.net/vipshop_fin_dev/article/details/79688717](https://blog.csdn.net/vipshop_fin_dev/article/details/79688717)
