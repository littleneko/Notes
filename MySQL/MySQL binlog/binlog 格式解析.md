# FORMAT_DESCRIPTION_EVENT
FDE是binlog中的第一个event，先解析它
## FDE格式说明
这里还是先搬出FDE的格式描述，v4 format description event (size ≥ 91 bytes; the size is 76 + the number of event types):
```java
+=====================================+
| event  | timestamp         0 : 4    |
| header +----------------------------+
|        | type_code         4 : 1    | = FORMAT_DESCRIPTION_EVENT = 15
|        +----------------------------+
|        | server_id         5 : 4    |
|        +----------------------------+
|        | event_length      9 : 4    | >= 91
|        +----------------------------+
|        | next_position    13 : 4    |
|        +----------------------------+
|        | flags            17 : 2    |
+=====================================+
| event  | binlog_version   19 : 2    | = 4
| data   +----------------------------+
|        | server_version   21 : 50   |
|        +----------------------------+
|        | create_timestamp 71 : 4    |
|        +----------------------------+
|        | header_length    75 : 1    |
|        +----------------------------+
|        | post-header      76 : n    | = array of n bytes, one byte per event
|        | lengths for all            |   type that the server knows about
|        | event types                |
+=====================================+
```
## Example
### show binlog events 结果
&nbsp;展开源码
```java
mysql> show binlog events in 'mysql-bin.000005';
+------------------+-----+----------------+-----------+-------------+--------------------------------------------------------------------+
| Log_name         | Pos | Event_type     | Server_id | End_log_pos | Info                                                               |
+------------------+-----+----------------+-----------+-------------+--------------------------------------------------------------------+
| mysql-bin.000005 |   4 | Format_desc    |         1 |         123 | Server ver: 5.7.24-log, Binlog ver: 4                              |
| mysql-bin.000005 | 123 | Previous_gtids |         1 |         194 | a09129d9-0728-11e9-aa93-d227f810ba81:1-73                          |
| mysql-bin.000005 | 194 | Gtid           |         1 |         259 | SET @@SESSION.GTID_NEXT= 'a09129d9-0728-11e9-aa93-d227f810ba81:74' |
| mysql-bin.000005 | 259 | Query          |         1 |         339 | BEGIN                                                              |
| mysql-bin.000005 | 339 | Table_map      |         1 |         395 | table_id: 129 (test.user)                                          |
| mysql-bin.000005 | 395 | Write_rows     |         1 |         465 | table_id: 129 flags: STMT_END_F                                    |
| mysql-bin.000005 | 465 | Xid            |         1 |         496 | COMMIT /* xid=581292 */                                            |
+------------------+-----+----------------+-----------+-------------+--------------------------------------------------------------------+
7 rows in set (0.00 sec)
```
这部分我们需要解析的是这个binlog中的第一个Event – Format_desc
### mysqlbinlog 解析结果
先用mysqlbinlog解析出来看看：
&nbsp;展开源码
```java
[xiaoju@mysql-test01 data]$ mysqlbinlog -vvv  mysql-bin.000005
/*!50530 SET @@SESSION.PSEUDO_SLAVE_MODE=1*/;
/*!50003 SET @OLD_COMPLETION_TYPE=@@COMPLETION_TYPE,COMPLETION_TYPE=0*/;
DELIMITER /*!*/;
# at 4
#190103 18:57:46 server id 1  end_log_pos 123 CRC32 0xccaee2f7 	Start: binlog v 4, server v 5.7.24-log created 190103 18:57:46
# Warning: this binlog is either in use or was not closed properly.
BINLOG '
quotXA8BAAAAdwAAAHsAAAABAAQANS43LjI0LWxvZwAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAEzgNAAgAEgAEBAQEEgAAXwAEGggAAAAICAgCAAAACgoKKioAEjQA
Affirsw=
'/*!*/;
# at 123
#190103 18:57:46 server id 1  end_log_pos 194 CRC32 0xe255aab5 	Previous-GTIDs
# a09129d9-0728-11e9-aa93-d227f810ba81:1-73
# at 194
#190103 18:58:14 server id 1  end_log_pos 259 CRC32 0x6f968591 	GTID	last_committed=0	sequence_number=1	rbr_only=yes
/*!50718 SET TRANSACTION ISOLATION LEVEL READ COMMITTED*//*!*/;
SET @@SESSION.GTID_NEXT= 'a09129d9-0728-11e9-aa93-d227f810ba81:74'/*!*/;
# at 259
#190103 18:58:14 server id 1  end_log_pos 339 CRC32 0xa0f8337f 	Query	thread_id=155	exec_time=0	error_code=0
SET TIMESTAMP=1546513094/*!*/;
SET @@session.pseudo_thread_id=155/*!*/;
SET @@session.foreign_key_checks=1, @@session.sql_auto_is_null=0, @@session.unique_checks=1, @@session.autocommit=1/*!*/;
SET @@session.sql_mode=1436549152/*!*/;
SET @@session.auto_increment_increment=1, @@session.auto_increment_offset=1/*!*/;
/*!\C utf8 *//*!*/;
SET @@session.character_set_client=33,@@session.collation_connection=33,@@session.collation_server=33/*!*/;
SET @@session.time_zone='SYSTEM'/*!*/;
SET @@session.lc_time_names=0/*!*/;
SET @@session.collation_database=DEFAULT/*!*/;
BEGIN
/*!*/;
# at 339
#190103 18:58:14 server id 1  end_log_pos 395 CRC32 0xd94a0655 	Table_map: `test`.`user` mapped to number 129
# at 395
#190103 18:58:14 server id 1  end_log_pos 465 CRC32 0x19a92318 	Write_rows: table id 129 flags: STMT_END_F
BINLOG '
xuotXBMBAAAAOAAAAIsBAAAAAIEAAAAAAAEABHRlc3QABHVzZXIABQgPCA8RBWAAYAAAAFUGStk=
xuotXB4BAAAARgAAANEBAAAAAIEAAAAAAAEAAgAF/+AUAAAAAAAAAAVsaXRhb24AAAAAAAAAB2Jl
aWppbmc4bNMAGCOpGQ==
'/*!*/;
### INSERT INTO `test`.`user`
### SET
###   @1=20 /* LONGINT meta=0 nullable=0 is_null=0 */
###   @2='litao' /* VARSTRING(96) meta=96 nullable=0 is_null=0 */
###   @3=110 /* LONGINT meta=0 nullable=0 is_null=0 */
###   @4='beijing' /* VARSTRING(96) meta=96 nullable=0 is_null=0 */
###   @5=946656000 /* TIMESTAMP(0) meta=0 nullable=0 is_null=0 */
# at 465
#190103 18:58:14 server id 1  end_log_pos 496 CRC32 0x73f13ad3 	Xid = 581292
COMMIT/*!*/;
SET @@SESSION.GTID_NEXT= 'AUTOMATIC' /* added by mysqlbinlog */ /*!*/;
DELIMITER ;
# End of log file
/*!50003 SET COMPLETION_TYPE=@OLD_COMPLETION_TYPE*/;
/*!50530 SET @@SESSION.PSEUDO_SLAVE_MODE=0*/;
```
可以看到其中第一个at 4的event就是FDE，可以看到有如下信息：
### 原始16进制 binlog
下面来看看binlog的16进制：
```java
[xiaoju@mysql-test01 data]$ hexdump -v -C mysql-bin.000005
00000000  fe 62 69 6e aa ea 2d 5c  0f 01 00 00 00 77 00 00  |.bin..-\.....w..|
00000010  00 7b 00 00 00 01 00 04  00 35 2e 37 2e 32 34 2d  |.{.......5.7.24-|
00000020  6c 6f 67 00 00 00 00 00  00 00 00 00 00 00 00 00  |log.............|
00000030  00 00 00 00 00 00 00 00  00 00 00 00 00 00 00 00  |................|
00000040  00 00 00 00 00 00 00 00  00 00 00 00 00 00 00 13  |................|
00000050  38 0d 00 08 00 12 00 04  04 04 04 12 00 00 5f 00  |8............._.|
00000060  04 1a 08 00 00 00 08 08  08 02 00 00 00 0a 0a 0a  |................|
00000070  2a 2a 00 12 34 00 01 f7  e2 ae cc aa ea 2d 5c 23  |**..4........-\#|
00000080  01 00 00 00 47 00 00 00  c2 00 00 00 80 00 01 00  |....G...........|
00000090  00 00 00 00 00 00 a0 91  29 d9 07 28 11 e9 aa 93  |........)..(....|
000000a0  d2 27 f8 10 ba 81 01 00  00 00 00 00 00 00 01 00  |.'..............|
000000b0  00 00 00 00 00 00 4a 00  00 00 00 00 00 00 b5 aa  |......J.........|
000000c0  55 e2 c6 ea 2d 5c 21 01  00 00 00 41 00 00 00 03  |U...-\!....A....|
000000d0  01 00 00 00 00 00 a0 91  29 d9 07 28 11 e9 aa 93  |........)..(....|
000000e0  d2 27 f8 10 ba 81 4a 00  00 00 00 00 00 00 02 00  |.'....J.........|
000000f0  00 00 00 00 00 00 00 01  00 00 00 00 00 00 00 91  |................|
00000100  85 96 6f c6 ea 2d 5c 02  01 00 00 00 50 00 00 00  |..o..-\.....P...|
00000110  53 01 00 00 08 00 9b 00  00 00 00 00 00 00 04 00  |S...............|
00000120  00 22 00 00 00 00 00 00  01 20 00 a0 55 00 00 00  |."....... ..U...|
00000130  00 06 03 73 74 64 04 21  00 21 00 21 00 05 06 53  |...std.!.!.!...S|
00000140  59 53 54 45 4d 74 65 73  74 00 42 45 47 49 4e 7f  |YSTEMtest.BEGIN.|
00000150  33 f8 a0 c6 ea 2d 5c 13  01 00 00 00 38 00 00 00  |3....-\.....8...|
00000160  8b 01 00 00 00 00 81 00  00 00 00 00 01 00 04 74  |...............t|
00000170  65 73 74 00 04 75 73 65  72 00 05 08 0f 08 0f 11  |est..user.......|
00000180  05 60 00 60 00 00 00 55  06 4a d9 c6 ea 2d 5c 1e  |.`.`...U.J...-\.|
00000190  01 00 00 00 46 00 00 00  d1 01 00 00 00 00 81 00  |....F...........|
000001a0  00 00 00 00 01 00 02 00  05 ff e0 14 00 00 00 00  |................|
000001b0  00 00 00 05 6c 69 74 61  6f 6e 00 00 00 00 00 00  |....litaon......|
000001c0  00 07 62 65 69 6a 69 6e  67 38 6c d3 00 18 23 a9  |..beijing8l...#.|
000001d0  19 c6 ea 2d 5c 10 01 00  00 00 1f 00 00 00 f0 01  |...-\...........|
000001e0  00 00 00 00 ac de 08 00  00 00 00 00 d3 3a f1 73  |.............:.s|
000001f0
```
### 各字段值解析
对着上面的FDE格式一个个解析出来如下：

| 

 | field | len | 原始值(0x) | 解析值 | 备注 |
| --- | --- | --- | --- | --- | --- |
| header | **timestamp** | 4 | aa ea 2d 5c | 1546513066 -> 2019/1/3 18:57:46 | 小端存储 |
|  | **type_code** | 1 | of | 15 -> FORMAT_DESCRIPTION_EVENT | 

 |
|  | **server_id** | 4 | 01 00 00 00 | 1 | 

 |
|  | **event_length** | 4 | 77 00 00 00 | 119 | 

 |
|  | **next_position** | 4 | 7b 00 00 00 | 0x0000007b | 示下一个event的起始位置为0x00007b,即当前event在0x0000007a结束 |
|  | **flags** | 2 | 01 00 | 

 | 

 |
| data | **binlog_version** | 2 | 04 00 | 4 | 小端序 |
|  | **server_version** | 50 | 35 2e 37 2e 32 34 2d 6c 6f 67 00 00 00 00 ... ... 00 | 5.7.24-log | 字符串，以00结尾，补0 |
|  | **create_timestamp** | 4 | 00 00 00 00 | 0 | 

 |
|  | **header_length** | 1 | 13 | 19 | 

 |
|  | **post-header's len** | 119-19-57-5 = 38 | 见下面详解 | 

 | 

 |


#### event type header length
 [_string.EOF_](https://dev.mysql.com/doc/internals/en/describing-packets.html#type-string.EOF)_ _-- a array indexed by `Binlog Event Type` - 1 to extract the length of the event specific header.
post-header's len 实际上后面跟了1字节的checksumAlg和4字节的checksum值。
![](https://cdn.nlark.com/yuque/0/2019/png/385742/1564035718357-c023e9f5-6899-46fc-91f0-4bc20da16865.png#height=63&id=BCajP&originHeight=63&originWidth=631&originalType=binary&ratio=1&status=done&style=none&width=631)
该字段从00000050位置到从0000007b结束，一共43字节（包括1字节checksumAlg和4字节checksum）
该字段表示不同类型event的header的长度，每种类型1字节，对应关系见官方文档: [https://dev.mysql.com/doc/internals/en/format-description-event.html](https://dev.mysql.com/doc/internals/en/format-description-event.html)
实际上是按event type号的一个数组，event type的定义见mysql源码：_libbinlogevents/include/binlog_event.h_。
例如：WRITE_ROWS_EVENT（30）对应的大小为 post-header_len[30] = 0x0a = 10
canal中对该字段的解析如下：
```java
// buffer.position(LOG_EVENT_MINIMAL_HEADER_LEN
// + ST_COMMON_HEADER_LEN_OFFSET + 1);
postHeaderLen = new short[numberOfEventTypes];
for (int i = 0; i < numberOfEventTypes; i++) {
    postHeaderLen[i] = (short) buffer.getUint8();
}
```
### checksum

| field | 原始值 | 解析值 | 备注 |
| --- | --- | --- | --- |
| checksumAlg | 01 | crc32 | 与mysqlbinog解析出来的结果(crc32)一致。 |
| checksum | f7 e2 ae cc | 

 | 与mysqlbinog解析出来的结果(0xccaee2f7)一致。 |


## binlog-checksum=NONE的情况
```java
[xiaoju@mysql-test01 data]$ hexdump -v -C mysql-bin.000006
00000000  fe 62 69 6e a1 df 2d 5c  0f 01 00 00 00 77 00 00  |.bin..-\.....w..|
00000010  00 7b 00 00 00 01 00 04  00 35 2e 37 2e 32 34 2d  |.{.......5.7.24-|
00000020  6c 6f 67 00 00 00 00 00  00 00 00 00 00 00 00 00  |log.............|
00000030  00 00 00 00 00 00 00 00  00 00 00 00 00 00 00 00  |................|
00000040  00 00 00 00 00 00 00 00  00 00 00 00 00 00 00 13  |................|
00000050  38 0d 00 08 00 12 00 04  04 04 04 12 00 00 5f 00  |8............._.|
00000060  04 1a 08 00 00 00 08 08  08 02 00 00 00 0a 0a 0a  |................|
00000070  2a 2a 00 12 34 00 00 2d  ee 7d 1b a1 df 2d 5c 23  |**..4..-.}...-\#|
00000080  01 00 00 00 43 00 00 00  be 00 00 00 80 00 01 00  |....C...........|
00000090  00 00 00 00 00 00 a0 91  29 d9 07 28 11 e9 aa 93  |........)..(....|
000000a0  d2 27 f8 10 ba 81 01 00  00 00 00 00 00 00 01 00  |.'..............|
000000b0  00 00 00 00 00 00 4a 00  00 00 00 00 00 00 45 e0  |......J.......E.|
000000c0  2d 5c 21 01 00 00 00 3d  00 00 00 fb 00 00 00 00  |-\!....=........|
000000d0  00 00 a0 91 29 d9 07 28  11 e9 aa 93 d2 27 f8 10  |....)..(.....'..|
000000e0  ba 81 4a 00 00 00 00 00  00 00 02 00 00 00 00 00  |..J.............|
000000f0  00 00 00 01 00 00 00 00  00 00 00 45 e0 2d 5c 02  |...........E.-\.|
00000100  01 00 00 00 4c 00 00 00  47 01 00 00 08 00 03 00  |....L...G.......|
00000110  00 00 00 00 00 00 04 00  00 22 00 00 00 00 00 00  |........."......|
00000120  01 20 00 a0 55 00 00 00  00 06 03 73 74 64 04 21  |. ..U......std.!|
00000130  00 21 00 21 00 05 06 53  59 53 54 45 4d 74 65 73  |.!.!...SYSTEMtes|
00000140  74 00 42 45 47 49 4e 45  e0 2d 5c 13 01 00 00 00  |t.BEGINE.-\.....|
00000150  36 00 00 00 7d 01 00 00  00 00 6c 00 00 00 00 00  |6...}.....l.....|
00000160  01 00 04 74 65 73 74 00  04 74 65 73 74 00 06 08  |...test..test...|
00000170  0f 08 0f 11 05 06 60 00  60 00 00 08 20 45 e0 2d  |......`.`... E.-|
00000180  5c 1e 01 00 00 00 4b 00  00 00 c8 01 00 00 00 00  |\.....K.........|
00000190  6c 00 00 00 00 00 01 00  02 00 06 ff c0 16 00 00  |l...............|
000001a0  00 00 00 00 00 05 6c 69  74 61 6f c9 00 00 00 00  |......litao.....|
000001b0  00 00 00 08 73 68 61 6e  67 68 61 69 3a 34 fa 00  |....shanghai:4..|
000001c0  9a 99 99 99 99 99 e9 3f  45 e0 2d 5c 10 01 00 00  |.......?E.-\....|
000001d0  00 1b 00 00 00 e3 01 00  00 00 00 23 00 00 00 00  |...........#....|
000001e0  00 00 00                                          |...|
000001e3
```
与上面的唯一区别是原本chencksum的位置变成了_00 2d ee 7d 1b_， 其中 _00 _表示_checksumAlg=NONE_，因为next-position仍然是 _7b 00 00 00_，所以 _2d ee 7d 1b_ 只是单纯的占位(?)
# `ROWS_EVENT`
ROWS_EVENT包括[https://dev.mysql.com/doc/internals/en/event-data-for-specific-event-types.html](https://dev.mysql.com/doc/internals/en/event-data-for-specific-event-types.html)**Write_rows_log_event/WRITE_ROWS_EVENT**`WRITE_ROWS_EVENT、UPDATE_ROWS_EVENT和DELETE_ROWS_EVENT，这三种的格式相同。详细格式参考：的节。`
这里仍然使用上面的binlog作为例子解析。
```java
00000180  05 60 00 60 00 00 00 55  06 4a d9 c6 ea 2d 5c 1e  |.`.`...U.J...-\.|
00000190  01 00 00 00 46 00 00 00  d1 01 00 00 00 00 81 00  |....F...........|
000001a0  00 00 00 00 01 00 02 00  05 ff e0 14 00 00 00 00  |................|
000001b0  00 00 00 05 6c 69 74 61  6f 6e 00 00 00 00 00 00  |....litaon......|
000001c0  00 07 62 65 69 6a 69 6e  67 38 6c d3 00 18 23 a9  |..beijing8l...#.|
000001d0  19 c6 ea 2d 5c 10 01 00  00 00 1f 00 00 00 f0 01  |...-\...........|
```
WriteRowsEvent从 0x018b 开始 到

| 

 | field |  | len | 原始值 | 解析值 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| header | **timestamp** |  | 4 |  | 

 | 

 |
|  | **type_code** |  | 1 |  | 30 -> WRITE_ROWS_EVENT | 

 |
|  | **server_id** |  | 4 |  | 1 | 

 |
|  | **event_length** |  | 4 |  | 70 | 

 |
|  | **next_position** |  | 4 |  | 0x000001d1 | 

 |
|  | **flags** |  | 2 |  | 

 | 

 |
|  | **extra_headers** |  | 0 | 

 | 

 | 

 |
| data | post header | table_id | 6 |  | 129 |  |
|  |  | reserve | 2 |  | 1 | 好像是 flags: STMT_END_F |
|  |  | 

 | 2 |  | 

 | 具体意义见下面代码 |
|  | column_len |  | x = 1 |  | 5 | 长度见下面代码 |
|  | columns_bitmap |  | 1 |  | 

 | 每列都有值 |
|  | columns_change_bitmap |  | 0 | 

 | 

 | for `UPDATE_ROWS_LOG_EVENT`
 only |
|  | data |  | 

 | 

 | 

 | todo |
| 

 | **checksum** |  | 4 |  |  | 

 |



canal中解析column_len的代码为：
```java
/**
 * Return next packed number from buffer. (little-endian)
 * 
 * @see LogBuffer#getPackedLong(int)
 */
public final long getPackedLong() {
    final int lead = getUint8();
    if (lead < 251) return lead;

    switch (lead) {
        case 251:
            return NULL_LENGTH;
        case 252:
            return getUint16();
        case 253:
            return getUint24();
        default: /* Must be 254 when here */
            final long value = getUint32();
            position += 4; /* ignore other */
            return value;
    }
}
```
所以column_len实际上是一个可变长度的值。

canal中解析RowsLogEvent的代码：
&nbsp;展开源码
```java
public RowsLogEvent(LogHeader header, LogBuffer buffer, FormatDescriptionLogEvent descriptionEvent){
    super(header);

    final int commonHeaderLen = descriptionEvent.commonHeaderLen;
    final int postHeaderLen = descriptionEvent.postHeaderLen[header.type - 1];
    int headerLen = 0;
    buffer.position(commonHeaderLen + RW_MAPID_OFFSET);
    if (postHeaderLen == 6) {
        /*
         * Master is of an intermediate source tree before 5.1.4. Id is 4
         * bytes
         */
        tableId = buffer.getUint32();
    } else {
        tableId = buffer.getUlong48(); // RW_FLAGS_OFFSET
    }
    flags = buffer.getUint16();

    if (postHeaderLen == FormatDescriptionLogEvent.ROWS_HEADER_LEN_V2) {
        headerLen = buffer.getUint16();
        headerLen -= 2;
        int start = buffer.position();
        int end = start + headerLen;
        for (int i = start; i < end;) {
            switch (buffer.getUint8(i++)) {
                case RW_V_EXTRAINFO_TAG:
                    // int infoLen = buffer.getUint8();
                    buffer.position(i + EXTRA_ROW_INFO_LEN_OFFSET);
                    int checkLen = buffer.getUint8(); // EXTRA_ROW_INFO_LEN_OFFSET
                    int val = checkLen - EXTRA_ROW_INFO_HDR_BYTES;
                    assert (buffer.getUint8() == val); // EXTRA_ROW_INFO_FORMAT_OFFSET
                    for (int j = 0; j < val; j++) {
                        assert (buffer.getUint8() == val); // EXTRA_ROW_INFO_HDR_BYTES
                                                           // + i
                    }
                    break;
                default:
                    i = end;
                    break;
            }
        }
    }

    buffer.position(commonHeaderLen + postHeaderLen + headerLen);
    columnLen = (int) buffer.getPackedLong();
    columns = buffer.getBitmap(columnLen);

    if (header.type == UPDATE_ROWS_EVENT_V1 || header.type == UPDATE_ROWS_EVENT) {
        changeColumns = buffer.getBitmap(columnLen);
    } else {
        changeColumns = columns;
    }

    // XXX: Don't handle buffer in another thread.
    int dataSize = buffer.limit() - buffer.position();
    rowsBuf = buffer.duplicate(dataSize);
}
```
上面的代码可以得到，postHeaderLen == FormatDescriptionLogEvent.ROWS_HEADER_LEN_V2时，会另外解析一个headerLen。这里WriteRowsEvent的postHeaderLen正好是10（见上一节FDE解析结果）

canal相关代码位置：

- com.taobao.tddl.dbsync.binlog.event.LogHeader.java
- com.taobao.tddl.dbsync.binlog.event.FormatDescriptionLogEvent.java
- com.taobao.tddl.dbsync.binlog.event.RowsLogEvent.java
- com.taobao.tddl.dbsync.binlog.event.RowsLogBuffer.java
# 参考资料

1. [https://dev.mysql.com/doc/internals/en/event-header-fields.html](https://dev.mysql.com/doc/internals/en/event-header-fields.html)
2. [https://dev.mysql.com/doc/internals/en/event-flags.html](https://dev.mysql.com/doc/internals/en/event-flags.html)
3. [https://dev.mysql.com/doc/internals/en/binary-log-versions.html](https://dev.mysql.com/doc/internals/en/binary-log-versions.html)
4. [https://dev.mysql.com/doc/internals/en/format-description-event.html](https://dev.mysql.com/doc/internals/en/format-description-event.html)
5. [https://dev.mysql.com/doc/refman/5.6/en/replication-options-binary-log.html#option_mysqld_binlog-checksum](https://dev.mysql.com/doc/refman/5.6/en/replication-options-binary-log.html#option_mysqld_binlog-checksum)
6. [https://dev.mysql.com/doc/internals/en/event-data-for-specific-event-types.html](https://dev.mysql.com/doc/internals/en/event-data-for-specific-event-types.html)

## Attachments:
![](https://cdn.nlark.com/yuque/0/2019/gif/385742/1564035719116-7d1d28d6-9b56-49d1-a74f-c90d954c2275.gif#height=8&id=wkVB7&originHeight=8&originWidth=8&originalType=binary&ratio=1&status=done&style=none&width=8)[image2019-5-3_1-13-49.png](https://cdn.nlark.com/yuque/0/2019/png/385742/1564035718357-c023e9f5-6899-46fc-91f0-4bc20da16865.png)
