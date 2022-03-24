# Data Representation

The data in a tuple is essentially just byte arrays. It is up to the DBMS to know how to interpret those bytes to derive the values for attributes. A *data representation* scheme is how a DBMS stores the bytes for a value.

There are five high level datatypes that can be stored in tuples: integers, variable-precision numbers, fixed-point precision numbers, variable length values, and dates/times.

## Integers
Most DBMSs store integers using their “native” C/C++ types as specified by the IEEE-754 standard. These values are fixed length.

**Examples**: INTEGER, BIGINT, SMALLINT, TINYINT.

## Variable Precision Numbers
These are inexact, variable-precision numeric types that use the “native” C/C++ types specified by IEEE-754 standard. These values are also fixed length.

Operations on variable-precision numbers are faster to compute than arbitrary precision numbers because the CPU can execute instructions on them directly. ==However, there may be rounding errors when performing computations due to the fact that some numbers cannot be represented precisely.==

**Examples**: FLOAT, REAL.

## Fixed-Point Precision Numbers

These are numeric data types with arbitrary precision and scale. They are typically stored in exact, variable-length binary representation (almost like a string) with additional meta-data that will tell the system things like the length of the data and where the decimal should be.

These data types are used when rounding errors are unacceptable, but the DBMS pays a performance penalty to get this accuracy.

**Examples**: NUMERIC, DECIMAL.

![image-20220306131456383](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220306131456383.png)

![image-20220306131524889](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220306131524889.png)

## Variable-Length Data
These represent data types of arbitrary length. They are typically stored with a header that keeps track of the length of the string to make it easy to jump to the next value. It may also contain a checksum for the data.

**Overflow Page**

Most DBMSs do not allow a tuple to exceed the size of a single page. The ones that do store the data on a special “overflow” page and have the tuple contain a reference to that page. These overflow pages can contain pointers to additional overflow pages until all the data can be stored.

To store values that are larger than a page, the DBMS uses separate overflow storage pages.

* Postgres: TOAST (>2KB)
* MySQL: Overflow (>1⁄2 size of page) (注：保证 B+ 树至少有两个孩子节点)
* SQL Server: Overflow (>size of page)

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220306131642005.png" alt="image-20220306131642005" style="zoom:33%;" />

**External File**

Some systems will let you store these large values in an external file, and then the tuple will contain a pointer to that file. For example, if the database is storing photo information, the DBMS can store the photos in the external files rather than having them take up large amounts of space in the DBMS. One downside of this is that the DBMS cannot manipulate the contents of this file. Thus, there are ==no durability or transaction protections==.

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220306131842163.png" alt="image-20220306131842163" style="zoom:33%;" />

**Examples**: VARCHAR, VARBINARY, TEXT, BLOB.

## Dates and Times
Representations for date/time vary for different systems. Typically, these are represented as some unit time (micro/milli) seconds since the unix epoch.

**Examples**: TIME, DATE, TIMESTAMP.

## System Catalogs
In order for the DBMS to be able to deciphter the contents of tuples, it maintains an internal catalog to tell it meta-data about the databases. The meta-data will contain information about what tables and columns the databases have along with their types and the orderings of the values.

* Tables, columns, indexes, views
* Users, permissions
* Internal statistics

Most DBMSs store their catalog inside of themselves in the format that they use for their tables. They use special code to “bootstrap” these catalog tables.

# Workloads

* **On-Line Transaction Processing (OLTP)**: Fast operations that only read/update a small amount of data each time.
* **On-Line Analytical Processing (OLAP)**: Complex queries that read a lot of data to compute aggregates.
* **Hybrid Transaction + Analytical Processing**: OLTP + OLAP together on the same database instance

# Storage Models

There are different ways to store tuples in pages. We have assumed the **n-ary storage model** so far.

## N-Ary Storage Model (NSM)

In the n-ary storage model, the DBMS stores all of the attributes for a single tuple contiguously in a single page, so NSM is also known as a “row store.” This approach is ideal for OLTP workloads where requests are insert-heavy and transactions tend to operate only an individual entity. It is ideal because it takes only one fetch to be able to get all of the attributes for a single tuple.

**Advantages**:

* Fast inserts, updates, and deletes.
* Good for queries that need the entire tuple.

**Disadvantages**:

* Not good for scanning large portions of the table and/or a subset of the attributes. This is because it pollutes the buffer pool by fetching data that is not needed for processing the query.

![image-20220306132746480](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220306132746480.png)

![image-20220306132834289](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220306132834289.png)

## Decomposition Storage Model (DSM)

In the decomposition storage model, the DBMS stores a single attribute (column) for all tuples contiguously in a block of data. Thus, it is also known as a “column store.” This model is ideal for OLAP workloads with many read-only queries that perform large scans over a subset of the table’s attributes.

**Advantages**:

* Reduces the amount of wasted work during query execution because the DBMS only reads the data that it needs for that query.
* Enables ==better compression== because all of the values for the same attribute are stored contiguously.

**Disadvantages**:

* Slow for point queries, inserts, updates, and deletes because of tuple splitting/stitching.

![image-20220306133151998](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220306133151998.png)

### Tuple Identification

**Choice #1: Fixed-length Offsets**

To put the tuples back together when using a column store, there are two common approaches: The most commonly used approach is fixed-length offsets. Assuming the attributes are all fixed-length, the DBMS can compute the offset of the attribute for each tuple. Then when the system wants the attribute for a specific tuple, it knows how to jump to that spot in the file from the offest. ==To accommodate the variable-length fields, the system can either pad fields so that they are all the same length or use a dictionary that takes a fixed-size integer and maps the integer to the value.==

**Choice #2: Embedded Tuple Ids**

A less common approach is to use embedded tuple ids. Here, for every attribute in the columns, the DBMS stores a tuple id (ex: a primary key) with it. The system then would also store a mapping to tell it how to jump to every attribute that has that id. Note that this method has a large storage overhead because it needs to store a tuple id for every attribute entry.

![image-20220306133415595](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220306133415595.png)