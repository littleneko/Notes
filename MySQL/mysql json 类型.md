相关代码：

1. json_binary.cc/h: json编码、解码
2. json_dom.cc/h: json对象的内存表示
3. json_path.cc/h: 将字符串解析成json

关于mysql json类型的使用参考 [https://dev.mysql.com/doc/refman/5.7/en/json.html](https://dev.mysql.com/doc/refman/5.7/en/json.html)
# 存储格式
## Overview
在json_binary.h的开头有一大段注释，基本把mysql中json类型的存储格式说清楚了
```cpp
/**
  @file
 
  This file specifies the interface for serializing JSON values into
  binary representation, and for reading values back from the binary
  representation.
 
  The binary format is as follows:
 
  Each JSON value (scalar, object or array) has a one byte type
  identifier followed by the actual value.
 
  If the value is a JSON object, its binary representation will have a
  header that contains:
 
  - the member count
  - the size of the binary value in bytes
  - a list of pointers to each key
  - a list of pointers to each value
 
  The actual keys and values will come after the header, in the same
  order as in the header.
 
  Similarly, if the value is a JSON array, the binary representation
  will have a header with
 
  - the element count
  - the size of the binary value in bytes
  - a list of pointers to each value
 
  followed by the actual values, in the same order as in the header.
 
  @verbatim
  doc ::= type value
 
  type ::=
      0x00 |       // small JSON object
      0x01 |       // large JSON object
      0x02 |       // small JSON array
      0x03 |       // large JSON array
      0x04 |       // literal (true/false/null)
      0x05 |       // int16
      0x06 |       // uint16
      0x07 |       // int32
      0x08 |       // uint32
      0x09 |       // int64
      0x0a |       // uint64
      0x0b |       // double
      0x0c |       // utf8mb4 string
      0x0f         // custom data (any MySQL data type)
 
  value ::=
      object  |
      array   |
      literal |
      number  |
      string  |
      custom-data
 
  object ::= element-count size key-entry* value-entry* key* value*
 
  array ::= element-count size value-entry* value*
 
  // number of members in object or number of elements in array
  element-count ::=
      uint16 |  // if used in small JSON object/array
      uint32    // if used in large JSON object/array
 
  // number of bytes in the binary representation of the object or array
  size ::=
      uint16 |  // if used in small JSON object/array
      uint32    // if used in large JSON object/array
 
  key-entry ::= key-offset key-length
 
  key-offset ::=
      uint16 |  // if used in small JSON object
      uint32    // if used in large JSON object
 
  key-length ::= uint16    // key length must be less than 64KB
 
  value-entry ::= type offset-or-inlined-value
 
  // This field holds either the offset to where the value is stored,
  // or the value itself if it is small enough to be inlined (that is,
  // if it is a JSON literal or a small enough [u]int).
  offset-or-inlined-value ::=
      uint16 |   // if used in small JSON object/array
      uint32     // if used in large JSON object/array
 
  key ::= utf8mb4-data
 
  literal ::=
      0x00 |   // JSON null literal
      0x01 |   // JSON true literal
      0x02 |   // JSON false literal
 
  number ::=  ....  // little-endian format for [u]int(16|32|64), whereas
                    // double is stored in a platform-independent, eight-byte
                    // format using float8store()
 
  string ::= data-length utf8mb4-data
 
  custom-data ::= custom-type data-length binary-data
 
  custom-type ::= uint8   // type identifier that matches the
                          // internal enum_field_types enum
 
  data-length ::= uint8*  // If the high bit of a byte is 1, the length
                          // field is continued in the next byte,
                          // otherwise it is the last byte of the length
                          // field. So we need 1 byte to represent
                          // lengths up to 127, 2 bytes to represent
                          // lengths up to 16383, and so on...
  @endverbatim
*/

```

![](https://cdn.nlark.com/yuque/0/2019/png/385742/1573718332214-429bd26f-af6c-4629-91bc-23ec658e4170.png#align=left&display=inline&height=412&originHeight=412&originWidth=950&size=0&status=done&style=none&width=950)

1. 上图为json object格式的图示，对于json array，实际上没有key idx
2. 每个value又可以是json object，json array和scalar：
   - OBJECT和ARRAY: 嵌套一个上图结构
   - INT, DOUBLE等类型直接存储对应字节数的数据
   - STRING: 变长长度字段 + 数据
   - OPAQUE: 1字节type + 变长长度字段 + 数据
### Key idx和Value Idx的格式
```cpp
// source: json_binary.cc
 
/*
 * The size of offset or size fields in the small and the large storage
 * format for JSON objects and JSON arrays.
 */
public static final int  SMALL_OFFSET_SIZE       = 2;
public static final int  LARGE_OFFSET_SIZE       = 4;
 
/*
 * The size of key entries for objects when using the small storage format
 * or the large storage format. In the small format it is 4 bytes (2 bytes
 * for key length and 2 bytes for key offset). In the large format it is 6
 * (2 bytes for length, 4 bytes for offset).
 */
public static final int  KEY_ENTRY_SIZE_SMALL    = (2 + SMALL_OFFSET_SIZE);
public static final int  KEY_ENTRY_SIZE_LARGE    = (2 + LARGE_OFFSET_SIZE);
 
/*
 * The size of value entries for objects or arrays. When using the small
 * storage format, the entry size is 3 (1 byte for type, 2 bytes for
 * offset). When using the large storage format, it is 5 (1 byte for type, 4
 * bytes for offset).
 */
public static final int  VALUE_ENTRY_SIZE_SMALL  = (1 + SMALL_OFFSET_SIZE);
public static final int  VALUE_ENTRY_SIZE_LARGE  = (1 + LARGE_OFFSET_SIZE);
```

key idx由 2 字节的key长度和SMALL_OFFSET_SIZE(2字节)或LARGE_OFFSET_SIZE(4字节)的offset组成，value idx由 1 字节的类型和2或4字节的offset组成。
## 存储解析后的二进制数据(calss Value)
Value用来保存从二进制解析出来的一个OBJECT或ARRAY或其他具体类型的值

```cpp
/**
  Class used for reading JSON values that are stored in the binary
  format. Values are parsed lazily, so that only the parts of the
  value that are interesting to the caller, are read. Array elements
  can be looked up in constant time using the element() function.
  Object members can be looked up in O(log n) time using the lookup()
  function.
*/
class Value
{
public:
  enum enum_type
  {
    OBJECT, ARRAY, STRING, INT, UINT, DOUBLE,
    LITERAL_NULL, LITERAL_TRUE, LITERAL_FALSE,
    OPAQUE,
    ERROR /* Not really a type. Used to signal that an
             error was detected. */
  };
  /**
    Does this value, and all of its members, represent a valid JSON
    value?
  // 此处省略一万行 ... ...
  Value element(size_t pos) const;
  Value key(size_t pos) const;
  Value lookup(const char *key, size_t len) const;
  bool raw_binary(String *buf) const;
 
private:
  /** The type of the value. */
  const enum_type m_type;
  /**
    The MySQL field type of the value, in case the type of the value is
    OPAQUE. Otherwise, it is unused.
  */
  const enum_field_types m_field_type ;
  /**
    Pointer to the start of the binary representation of the value. Only
    used by STRING, OBJECT and ARRAY.
 
    The memory pointed to by this member is not owned by this Value
    object. Callers that create Value objects must make sure that the
    memory is not freed as long as the Value object is alive.
  */
  const char *m_data;
  /**
    Element count for arrays and objects. Unused for other types.
  */
  const size_t m_element_count;
  /**
    The full length (in bytes) of the binary representation of an array or
    object, or the length of a string or opaque value. Unused for other types.
  */
  const size_t m_length;
  /** The value if the type is INT or UINT. */
  const int64 m_int_value;
  /** The value if the type is DOUBLE. */
  const double m_double_value;
  /**
    True if an array or an object uses the large storage format with 4
    byte offsets instead of 2 byte offsets.
  */
  const bool m_large;
 
};
```

### 重要Field
可以看到Value类中，有两个type相关的field

- m_type类型是enum_type，表示该Value的类型是OBJECT、ARRAY、INT、OPAQUE, ...等
- m_field_type类型是enum_field_types，只对于m_type是OPAQUE时有效


其他各field的意义如下：

- m_data: 二进制数据，在m_type是STRING、OBJECT、ARRAY和OPAQUE时有用
- m_int_value和m_int_double_value，对于INT和DOUBLE类型这里直接解析出值

### 重要函数
#### 取value（element）
只对于ARRAY和OBJECT类型有意义，对于ARRAY返回地post个元素；对于OBJECT返回第pos个key对应的元素（MySQL JSON中的key是有序的）
流程是先找到value的type，然后根据type调用parse_scalar或parse_value处理得到一个Value
#### **取key（key）**
只对于OBJECT类型有效，返回第pos个key的值，类型为STRING
#### **根据key查找value（lookup）**
根据key的值查找value，使用二分查找找到对应的key的idx，然后调用element(idx)直接取得对应的Value
#### 序列化（row_binary）
把json_binary::Value序列化成String对象
### Value的Type

```cpp
// file: libbinlogevents/export/binary_log_types.h
//
typedef enum enum_field_types {
  MYSQL_TYPE_DECIMAL, MYSQL_TYPE_TINY,
  MYSQL_TYPE_SHORT,  MYSQL_TYPE_LONG,
  MYSQL_TYPE_FLOAT,  MYSQL_TYPE_DOUBLE,
  MYSQL_TYPE_NULL,   MYSQL_TYPE_TIMESTAMP,
  MYSQL_TYPE_LONGLONG,MYSQL_TYPE_INT24,
  MYSQL_TYPE_DATE,   MYSQL_TYPE_TIME,
  MYSQL_TYPE_DATETIME, MYSQL_TYPE_YEAR,
  MYSQL_TYPE_NEWDATE, MYSQL_TYPE_VARCHAR,
  MYSQL_TYPE_BIT,
  MYSQL_TYPE_TIMESTAMP2,
  MYSQL_TYPE_DATETIME2,
  MYSQL_TYPE_TIME2,
  MYSQL_TYPE_JSON=245,
  MYSQL_TYPE_NEWDECIMAL=246,
  MYSQL_TYPE_ENUM=247,
  MYSQL_TYPE_SET=248,
  MYSQL_TYPE_TINY_BLOB=249,
  MYSQL_TYPE_MEDIUM_BLOB=250,
  MYSQL_TYPE_LONG_BLOB=251,
  MYSQL_TYPE_BLOB=252,
  MYSQL_TYPE_VAR_STRING=253,
  MYSQL_TYPE_STRING=254,
  MYSQL_TYPE_GEOMETRY=255
} enum_field_types;
```

## 解析和序列化
MySQL JSON相关函数，源码位置 [json_binary.cc](http://json_binary.cc/)

1. 序列化Json_dom：_bool serialize(const Json_dom *dom, String *dest)_
2. 解析二进制到json_binary::Value：_Value parse_binary(const char *data, size_t len)_
### 解析
#### 重要函数

1. parse_value: 解析value的入口
2. parse_array_or_object
3. parse_scalar: 解析其他类型，LITERAL、INT、DOUBLE、STRING、OPAQUE(特殊类型)

parse_binary调用parse_value解析的到Value，这里实际上只解析了头，即element_count和size，后续的解析在Value::element中进行。

```cpp
/**
  Parse a JSON value within a larger JSON document.
 
  @param type   the binary type of the value to parse
  @param data   pointer to the start of the binary representation of the value
  @param len    the maximum number of bytes to read from data
  @return  an object that allows access to the value
*/
static Value parse_value(uint8 type, const char *data, size_t len)
{
  switch (type)
  {
  case JSONB_TYPE_SMALL_OBJECT:
    return parse_array_or_object(Value::OBJECT, data, len, false);
  case JSONB_TYPE_LARGE_OBJECT:
    return parse_array_or_object(Value::OBJECT, data, len, true);
  case JSONB_TYPE_SMALL_ARRAY:
    return parse_array_or_object(Value::ARRAY, data, len, false);
  case JSONB_TYPE_LARGE_ARRAY:
    return parse_array_or_object(Value::ARRAY, data, len, true);
  default:
    return parse_scalar(type, data, len);
  }
}
```

#### OPAQUE类型的Value的存储格式

```cpp
static Value parse_scalar(uint8 type, const char *data, size_t len)
{
  switch (type)
  {
  // 此处省略一万行 ... ...
  case JSONB_TYPE_OPAQUE:
    {
      /*
        There should always be at least one byte, which tells the field
        type of the opaque value.
      */
      if (len < 1)
        return err();                         /* purecov: inspected */
 
      // The type is encoded as a uint8 that maps to an enum_field_types.
      uint8 type_byte= static_cast<uint8>(*data);
      enum_field_types field_type= static_cast<enum_field_types>(type_byte);
 
      // Then there's the length of the value.
      size_t val_len;
      size_t n;
      if (read_variable_length(data + 1, len - 1, &val_len, &n))
        return err();                         /* purecov: inspected */
      if (len < 1 + n + val_len)
        return err();                         /* purecov: inspected */
      return Value(field_type, data + 1 + n, val_len);
    }
  default:
    // Not a valid scalar type.
    return err();
  }
}
```

可以看到OPAQUE数据的格式是：1byte类型 + 变长长度字段 + 数据
#### STRING和OPAQUE类型的长度

```cpp
/**
  Read a variable length written by append_variable_length().
 
  @param[in] data  the buffer to read from
  @param[in] data_length  the maximum number of bytes to read from data
  @param[out] length  the length that was read
  @param[out] num  the number of bytes needed to represent the length
  @return  false on success, true on error
*/
static bool read_variable_length(const char *data, size_t data_length,
                                 size_t *length, size_t *num)
{
  /*
    It takes five bytes to represent UINT_MAX32, which is the largest
    supported length, so don't look any further.
  */
  const size_t max_bytes= std::min(data_length, static_cast<size_t>(5));
 
  size_t len= 0;
  for (size_t i= 0; i < max_bytes; i++)
  {
    // Get the next 7 bits of the length.
    len|= (data[i] & 0x7f) << (7 * i);
    if ((data[i] & 0x80) == 0)
    {
      // The length shouldn't exceed 32 bits.
      if (len > UINT_MAX32)
        return true;                          /* purecov: inspected */
 
      // This was the last byte. Return successfully.
      *num= i + 1;
      *length= len;
      return false;
    }
  }
 
  // No more available bytes. Return true to signal error.
  return true;                                /* purecov: inspected */
}
```

可以看到表示长度的字段是一个变长字段，使用最高位是否是1来判断是否还要继续向后解析，解析时每次都只取低7位。
### 序列化
序列化实际上是将Json_dom对象序列化成String对象(sql_string.h中定义)
#### 重要函数

1. serialize_json_value: 序列化入口函数，对于object和array会调用对应的函数处理，对于其他类型，直接在这里处理
2. serialize_json_array

3. serialize_json_object
## Example（todo）
关联canal

1. insert into json_test values(NULL, '{"key1": "abc", "key2": "xyz", "key3": 0.0}')
2. update json_test set person_desc = json_set(person_desc, "$.key3", 0.0) where id = 3
3. update json_test set person_desc = json_set(person_desc, "$.key1", "aaa") where id = 3
### UPDATE 1
第一次update后得到的相关binlog的二进制数据
```
00000000  fc 03 00 00 00 36 00 00  00 00 03 00 35 00 19 00  |.....6......5...|
00000010  04 00 1d 00 04 00 21 00  04 00 0c 25 00 0c 29 00  |......!....%..).|
00000020  0b 2d 00 6b 65 79 31 6b  65 79 32 6b 65 79 33 03  |.-.key1key2key3.|
00000030  61 62 63 03 78 79 7a 00  00 00 00 00 00 00 00 fc  |abc.xyz.........|
00000040  03 00 00 00 34 00 00 00  00 03 00 33 00 19 00 04  |....4......3....|
00000050  00 1d 00 04 00 21 00 04  00 0c 25 00 0c 29 00 0f  |.....!....%..)..|
00000060  2d 00 6b 65 79 31 6b 65  79 32 6b 65 79 33 03 61  |-.key1key2key3.a|
00000070  62 63 03 78 79 7a f6 04  02 01 80 00              |bc.xyz......|
0000007c
```

实际的json数据从offset 0xa 位置开始，下面是json数据的解析。
Before Image

| 
 | field |  | len | 原始值(hex) | 解析值(dec) | 备注 |
| :--- | :--- | :--- | :--- | :--- | :--- | --- |
| 
 | count |  | 2 | _03 00_ | 3 | 顶层json object一共3个field |
| 
 | size |  | 2 | _35 00_ | 53 | 该json object的总长度为53字节，从count处开始计算 |
| key entry | key1 | offset | 2 | _19 00_ | 25 | 第一个key在距离json起始位置25字节处 |
|  |  | len | 2 | _04 00_ | 4 | key的长度为4字节 |
|  | key2 | offset | 2 | _1d 00_ | 29 | 
 |
|  |  | len | 2 | _04 00_ | 4 | 
 |
|  | key3 | offset | 2 | _21 00_ | 33 | 
 |
|  |  | len | 2 | _04 00_ | 4 | 
 |
| value entry | v1 | type | 1 | _0c_ | 12 → JSONB_TYPE_STRING | 
 |
|  |  | offset | 2 | _25 00_ | 37 | 
 |
|  | v2 | type | 1 | _0c_ | 12 → JSONB_TYPE_STRING | 
 |
|  |  | offset | 2 | _29 00_ | 41 | 
 |
|  | v3 | type | 1 | _0b_ | 11 → JSON_TYPE_DOUBLE | 
 |
|  |  | offset | 2 | _2d 00_ | 45 | 
 |
| key
 | key1 |  | 4 | _6b 65 79 31_ | key1 | 
 |
|  | key2 |  | 4 | _6b 65 79 32_ | key2 | 
 |
|  | key3 |  | 4 | _6b 65 79 33_ | key3 | 
 |
| value | value1 | len | 1 | _03_ | 3 | string类型长度占用的字节数通过判断第一字节的最高位是否是1来判断 |
|  |  | value | 3 | _61 62 63_ | abc | 
 |
|  | value2 | len | 1 | _03_ | 3 | 
 |
|  |  | value | 3 | _78 79 7a_ | xyz | 
 |
|  | value3 | value | 8 | _0000 0000 0000 0000_ | 0 | double类型直接取64bit的值 |
| 
 | 
 | 
 | 
 | 
 | 
 | 
 |

### After Image
从图中可以看到after image的数据和before image类似，区别在于

1. size由53变为了51

2. v3的type由0b(11) → 0f(15)，即JSON_TYPE_DOUBLE → JSONB_TYPE_OPAQUE

3. v3的值由 _0000 0000 0000 0000 _变为 _f604 0201 8000_


key3的value类型是OPAQUE，解析逻辑和解析BI时不同，最终解析时分为了3部分

| field |  | 原始值(hex) | 解析值(dec) | 备注 |
| :--- | :--- | :--- | :--- | --- |
| value3 | type_bytes | f6 | 246 | 该值用于构建Json_Value类时的m_field_type参数（只有在m_type为OPAQUE时需要） |
|  | len | 04 | 4 | 值占4个字节 |
|  | value | 0201 8000 | 
 | 
 |


## UPDATE 2

```
00000000  fc 03 00 00 00 34 00 00  00 00 03 00 33 00 19 00  |.....4......3...|
00000010  04 00 1d 00 04 00 21 00  04 00 0c 25 00 0c 29 00  |......!....%..).|
00000020  0f 2d 00 6b 65 79 31 6b  65 79 32 6b 65 79 33 03  |.-.key1key2key3.|
00000030  61 62 63 03 78 79 7a f6  04 02 01 80 00 fc 03 00  |abc.xyz.........|
00000040  00 00 33 00 00 00 00 03  00 32 00 19 00 04 00 1d  |..3......2......|
00000050  00 04 00 21 00 04 00 0c  25 00 0c 29 00 0f 2d 00  |...!....%..)..-.|
00000060  6b 65 79 31 6b 65 79 32  6b 65 79 33 03 61 61 61  |key1key2key3.aaa|
00000070  03 78 79 7a f6 03 01 01  80                       |.xyz.....|
00000079
```

UPDATE 2执行后，可以看到Before Image和UPDATE 1之后的After Image相同，符合预期。
# JSON在内存中的表示（DOM）
## Json_dom

```cpp
/**
  @class
  @brief JSON DOM classes: Abstract base class is Json_dom -
  MySQL representation of in-memory JSON objects used by the JSON type
  Supports access, deep cloning, and updates. See also Json_wrapper and
  json_binary::Value.
  Uses heap for space allocation for now. FIXME.
 
  Class hierarchy:
  <code><pre>
      Json_dom (abstract)
       Json_scalar (abstract)
         Json_string
         Json_number (abstract)
           Json_decimal
           Json_int
           Json_uint
           Json_double
         Json_boolean
         Json_null
         Json_datetime
         Json_opaque
       Json_object
       Json_array
  </pre></code>
  At the outset, object and array add/insert/append operations takes
  a clone unless specified in the method, e.g. add_alias hands the
  responsibility for the passed in object over to the object.
*/
class Json_dom
{
  // so that these classes can call set_parent()
  friend class Json_object;
  friend class Json_array;
public:
  /**
    Json values in MySQL comprises the stand set of JSON values plus a
    MySQL specific set. A Json _number_ type is subdivided into _int_,
    _uint_, _double_ and _decimal_.
 
    MySQL also adds four built-in date/time values: _date_, _time_,
    _datetime_ and _timestamp_.  An additional _opaque_ value can
    store any other MySQL type.
 
    The enumeration is common to Json_dom and Json_wrapper.
 
    The enumeration is also used by Json_wrapper::compare() to
    determine the ordering when comparing values of different types,
    so the order in which the values are defined in the enumeration,
    is significant. The expected order is null < number < string <
    object < array < boolean < date < time < datetime/timestamp <
    opaque.
  */
  enum enum_json_type {
    J_NULL,
    J_DECIMAL,
    J_INT,
    J_UINT,
    J_DOUBLE,
    J_STRING,
    J_OBJECT,
    J_ARRAY,
    J_BOOLEAN,
    J_DATE,
    J_TIME,
    J_DATETIME,
    J_TIMESTAMP,
    J_OPAQUE,
    J_ERROR
  };
 
  /**
    Extended type ids so that JSON_TYPE() can give useful type
    names to certain sub-types of J_OPAQUE.
  */
  enum enum_json_opaque_type {
    J_OPAQUE_BLOB,
    J_OPAQUE_BIT,
    J_OPAQUE_GEOMETRY
  };
 
 
public:
  /**
    Parse Json text to DOM (using rapidjson). The text must be valid JSON.
    The results when supplying an invalid document is undefined.
    The ownership of the returned object is henceforth with the caller.
 
    If the parsing fails because of a syntax error, the errmsg and
    offset arguments will be given values that point to a detailed
    error message and where the syntax error was located. The caller
    will have to generate an error message with my_error() in this
    case.
 
    If the parsing fails because of some other error (such as out of
    memory), errmsg will point to a location that holds the value
    NULL. In this case, parse() will already have called my_error(),
    and the caller doesn't need to generate an error message.
 
    @param[in]  text   the JSON text
    @param[in]  length the length of the text
    @param[out] errmsg any syntax error message (will be ignored if it is NULL)
    @param[out] offset the position in the parsed string a syntax error was
                       found (will be ignored if it is NULL)
    @param[in]  preserve_neg_zero_int whether integer negative zero should
                                      be preserved. If set to TRUE, -0 is
                                      handled as a DOUBLE. Double negative
                                      zero (-0.0) is preserved regardless of
                                      what this parameter is set to.
 
    @result the built DOM if JSON text was parseable, else NULL
  */
  static Json_dom *parse(const char *text, size_t length,
                         const char **errmsg, size_t *offset,
                         bool preserve_neg_zero_int= false);
 
  /**
    Construct a DOM object based on a binary JSON value. The ownership
    of the returned object is henceforth with the caller.
  */
  static Json_dom* parse(const json_binary::Value &v)
 
 
  // 此处省略一万行 ... ...
}
```

其中enum_json_type对应Json_dom的各个子类的类型，parse函数把json_binary::Value类型转换为Json_dom类型
### Json_dom::enum_json_type
... ...
### 重要函数
#### 解析json字符串到Json_dom对象（parse）
使用rapidjson实现
#### 解析json_binary::Value到Json_dom对象（parse）
... ...
## Json_wrapper

```cpp
/**
  @class
  Abstraction for accessing JSON values irrespective of whether they
  are (started out as) binary JSON values or JSON DOM values. The
  purpose of this is to allow uniform access for callers. It allows us
  to access binary JSON values without necessarily building a DOM (and
  thus having to read the entire value unless necessary, e.g. for
  accessing only a single array slot or object field).
 
  Instances of this class are usually created on the stack. In some
  cases instances are cached in an Item and reused, in which case they
  are allocated from query-duration memory (which is why the class
  inherits from Sql_alloc).
*/
class Json_wrapper : Sql_alloc
{
private:
  bool m_is_dom;      //!< Wraps a DOM iff true
  bool m_dom_alias;   //!< If true, don't deallocate in destructor
  json_binary::Value m_value;
  Json_dom *m_dom_value;
 
  /**
    Get the wrapped datetime value in the packed format.
 
    @param[in,out] buffer a char buffer with space for at least
    Json_datetime::PACKED_SIZE characters
    @return a char buffer that contains the packed representation of the
    datetime (may or may not be the same as buffer)
  */
  const char *get_datetime_packed(char *buffer) const;
 
public:
  /**
    Get the wrapped contents in DOM form. The DOM is (still) owned by the
    wrapper. If this wrapper originally held a value, it is now converted
    to hold (and eventually release) the DOM version.
 
    @return pointer to a DOM object, or NULL if the DOM could not be allocated
  */
  Json_dom *to_dom();
  /**
    Get the wrapped contents in binary value form.
 
    @param[in,out] str  a string that will be filled with the binary value
    @retval false on success
    @retval true  on error
  */
  bool to_binary(String *str) const;
 
  /**
    Format the JSON value to an external JSON string in buffer in
    the format of ISO/IEC 10646.
 
    @param[in,out] buffer      the formatted string is appended, so make sure
                               the length is set correctly before calling
    @param[in]     json_quoted if the JSON value is a string and json_quoted
                               is false, don't perform quoting on the string.
                               This is only used by JSON_UNQUOTE.
    @param[in]     func_name   The name of the function that called to_string().
 
    @return false formatting went well, else true
  */
  bool to_string(String *buffer, bool json_quoted, const char *func_name) const;
  /**
    If this wrapper holds a JSON object, get the value corresponding
    to the member key. Valid for J_OBJECT.  Calling this method if the type is
    not J_OBJECT will give undefined results.
 
    @param[in]     key name for identifying member
    @param[in]     len length of that member name
 
    @return the member value
  */
  Json_wrapper lookup(const char *key, size_t len) const;
  // 此处省略一万行 ... ...
}
```

### 序列化（Json_wrapper::to_binary）

1. 对于Json_dom类型直接调用json_binary::serialize序列化。m_is_dom: json_binary::serialize(m_dom_value, str);
2. 对于json_binary::Value类型，调用Value::raw_binary处理。m_value.raw_binary(str);
### 转成json字符串（Json_wrapper::to_string）
直接调用wrapper_to_string函数
**
**wrapper_to_string**
该函数实际上就是对json_binary::Value的不同类型分别做解析，然后拼接成json串

```cpp
/**
  Helper function which does all the heavy lifting for
  Json_wrapper::to_string(). It processes the Json_wrapper
  recursively. The depth parameter keeps track of the current nesting
  level. When it reaches JSON_DOCUMENT_MAX_DEPTH, it gives up in order
  to avoid running out of stack space.
 
  @param[in]     wr          the value to convert to a string
  @param[in,out] buffer      the buffer to write to
  @param[in]     json_quoted quote strings if true
  @param[in]     pretty      add newlines and indentation if true
  @param[in]     func_name   the name of the calling function
  @param[in]     depth       the nesting level of @a wr
 
  @retval false on success
  @retval true on error
*/
static bool wrapper_to_string(const Json_wrapper &wr, String *buffer,
                              bool json_quoted, bool pretty,
                              const char *func_name, size_t depth)
{
  if (check_json_depth(++depth))
    return true;
 
  switch (wr.type())
  {
  case Json_dom::J_TIME:
  case Json_dom::J_DATE:
  case Json_dom::J_DATETIME:
  case Json_dom::J_TIMESTAMP:
    {
      // 处理TIME类型
  case Json_dom::J_ARRAY:
    {
      // ... ...
    }
  case Json_dom::J_DOUBLE:
    {
      // ... ...
    }
  case Json_dom::J_INT:
    {
      // ... ...
    }
  case Json_dom::J_OBJECT:
    {
      // ... ...
    }
  case Json_dom::J_DECIMAL:
    {
      // ... ...
    }
  case Json_dom::J_OPAQUE:
    {
      // ... ...
    }
  case Json_dom::J_STRING:
    {
      // ... ...
    }
}
```

### json_binary::Value::enum_type → Json_dom::enum_json_type

```cpp
// file: json_dom.cc
//
Json_dom::enum_json_type Json_wrapper::type() const
{
  if (empty())
  {
    return Json_dom::J_ERROR;
  }
 
  if (m_is_dom)
  {
    return m_dom_value->json_type();
  }
 
  json_binary::Value::enum_type typ= m_value.type();
 
  if (typ == json_binary::Value::OPAQUE)
  {
    const enum_field_types ftyp= m_value.field_type();
 
    switch (ftyp)
    {
    case MYSQL_TYPE_NEWDECIMAL:
      return Json_dom::J_DECIMAL;
    case MYSQL_TYPE_DATETIME:
      return Json_dom::J_DATETIME;
    case MYSQL_TYPE_DATE:
      return Json_dom::J_DATE;
    case MYSQL_TYPE_TIME:
      return Json_dom::J_TIME;
    case MYSQL_TYPE_TIMESTAMP:
      return Json_dom::J_TIMESTAMP;
    default: ;
      // ok, fall through
    }
  }
 
  return bjson2json(typ);
}
```

## Json字符串解析
# json_path支持
略
# 调用关系
## 写入json字段
## 读取json字段
![image.png](https://cdn.nlark.com/yuque/0/2019/png/385742/1573718708755-c9eb59c1-68d8-4b8a-a614-462e78417a0d.png#align=left&display=inline&height=246&originHeight=491&originWidth=1902&size=230486&status=done&style=none&width=951)

**Reference**

1. [http://mysql.taobao.org/monthly/2016/01/03/](http://mysql.taobao.org/monthly/2016/01/03/)
2. [https://cloud.tencent.com/developer/article/1004449](https://cloud.tencent.com/developer/article/1004449)
3. [https://dev.mysql.com/worklog/task/?id=7909](https://dev.mysql.com/worklog/task/?id=7909)
4. [https://dev.mysql.com/doc/refman/5.7/en/json.html](https://dev.mysql.com/doc/refman/5.7/en/json.html)

