binlog格式分为v1、v3、v4版，这里主要关注v4
# Header
```java
+============================+
| timestamp         0 : 4    |
+----------------------------+
| type_code         4 : 1    |
+----------------------------+
| server_id         5 : 4    |
+----------------------------+
| event_length      9 : 4    |
+----------------------------+
| next_position    13 : 4    |
+----------------------------+
| flags            17 : 2    |
+----------------------------+
| extra_headers    19 : x-19 |
+============================+
```
## 重要字段

- timestamp

4 bytes. 表示语句被执行时的时间戳

- type_code

1 byte. event的type，在 enum [`Log_event_type`](https://dev.mysql.com/doc/internals/en/event-classes-and-types.html)(log_event.h)中定义。比如: 1 -> START_EVENT_V3, 2 -> QUERY_EVENT.

- server_id

4 bytes. The ID of the mysqld server that originally created the event. It comes from the server-id option that is set in the server configuration file for the purpose of replication. The server ID enables endless loops to be avoided when circular replication is used (with option --log-slave-updates on). Suppose that M1, M2, and M3 have server ID values of 1, 2, and 3, and that they are replicating in circular fashion: M1 is the master for M2, M2 is the master for M3, and M3 is that master for M1. The master/server relationships look like this:

```java
M1---->M2
 ^      |
 |      |
 +--M3<-+
```

A client sends an INSERT statement to M1. This is executed on M1 and written to its binary log with an event server ID of 1. The event is sent to M2, which executes it and writes it to its binary log; the event is still written with server ID 1 because that is the ID of the server that originally created the event. The event is sent to M3, which executes it and writes it to its binary log, still with server ID 1. Finally, the event is sent to M1, which sees server ID = 1 and understands this event originated from itself and therefore must be ignored.

- event_length

4 bytes. The total size of this event. This includes both the header and data parts. Most events are less than 1000 bytes, except when using LOAD DATA INFILE (where events contain the loaded file, so they can be big).

- next_position (not present in v1 format).

v4版中表示下一个event的起始位置

- flags (not present in v1 format)
- extra_headers (not present in v1, v3 formats)
# body
## 常见event
### format_desc event
FDE是一个binlog的第一个event，记录了当前mysql binlog的一些信息。
源码中的类继承关系：
![](https://cdn.nlark.com/yuque/0/2019/png/385742/1564035718273-dbaf2a37-e932-4708-96eb-7358de9e16b7.png#align=left&display=inline&height=400&originHeight=1016&originWidth=1204&status=done&style=none&width=1204)
FDE格式：
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
#### 重要字段

1. header_length: 头长度，包括extra_headers长度。
   - Currently in v4, the header length (at offset 75) is 19, which means that in other events, no extra headers will follow theflags field.
   - Note: The FORMAT_DESCRIPTION_EVENT itself contains no extra_headers field. 
2. post-header: 下一节解释
### rotate event
### query event
### table_map event
### write_rows event
### ![](https://cdn.nlark.com/yuque/0/2019/png/385742/1564035718315-a39439c0-9182-4204-bbb7-f59a8796192e.png#align=left&display=inline&height=400&originHeight=1056&originWidth=860&status=done&style=none&width=860)
# 参考资料：

1. [https://dev.mysql.com/doc/internals/en/event-flags.html](https://dev.mysql.com/doc/internals/en/event-flags.html)
2. [https://dev.mysql.com/doc/internals/en/event-header-fields.html](https://dev.mysql.com/doc/internals/en/event-header-fields.html)
3. [https://dev.mysql.com/doc/internals/en/binary-log-versions.html](https://dev.mysql.com/doc/internals/en/binary-log-versions.html)
4. [https://dev.mysql.com/doc/internals/en/format-description-event.html](https://dev.mysql.com/doc/internals/en/format-description-event.html)

## Attachments:
![](https://cdn.nlark.com/yuque/0/2019/gif/385742/1564035719116-7d1d28d6-9b56-49d1-a74f-c90d954c2275.gif#align=left&display=inline&height=8&originHeight=8&originWidth=8&status=done&style=none&width=8)[image2019-5-3_1-12-16.png](https://cdn.nlark.com/yuque/0/2019/png/385742/1564035718273-dbaf2a37-e932-4708-96eb-7358de9e16b7.png)
![](https://cdn.nlark.com/yuque/0/2019/gif/385742/1564035719116-7d1d28d6-9b56-49d1-a74f-c90d954c2275.gif#align=left&display=inline&height=8&originHeight=8&originWidth=8&status=done&style=none&width=8)[image2019-5-3_1-12-35.png](https://cdn.nlark.com/yuque/0/2019/png/385742/1564035718315-a39439c0-9182-4204-bbb7-f59a8796192e.png)
