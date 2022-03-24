# Storage
We will focus on a “disk-oriented” DBMS architecture that assumes that the primary storage location of the database is on non-volatile disk(s).

The DBMS's components manage the movement of data between non-volatile and volatile storage.

## Storage Hierarchy

At the top of the storage hierarchy, you have the devices that are closest to the CPU. This is the fastest storage, but it is also the smallest and most expensive. The further you get away from the CPU, the larger but slower the storage devices get. These devices also get cheaper per GB.

![image-20220306011136433](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220306011136433.png)

![image-20220306011207507](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220306011207507.png)

## Sequential vs. Random Access

Random access on non-volatile storage is usually much slower than sequential access.

DBMS will want to maximize sequential access.

* Algorithms try to reduce number of writes to random pages so that data is stored in contiguous blocks.
* Allocating multiple pages at the same time is called an extent.

## System Design Goals

* Allow the DBMS to manage databases that exceed the amount of memory available.
* Reading/writing to disk is expensive, so it must be managed carefully to avoid large stalls and performance degradation.
* Random access on disk is usually much slower than sequential access, so the DBMS will want to maximize sequential access.

# Disk-Oriented DBMS

![image-20220306011936169](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220306011936169.png)

# DBMS vs. OS

A high-level design goal of the DBMS is to support databases that exceed the amount of memory available. Since reading/writing to disk is expensive, disk use must be carefully managed. ==We do not want large stalls from fetching something from disk to slow down everything else. We want the DBMS to be able to process other queries while it is waiting to get the data from disk.==

This high-level design goal is like virtual memory, where there is a large address space and a place for the OS to bring in pages from disk. 

One way to achieve this virtual memory is by using *mmap* to map the contents of a file in a process’ address space, which makes the OS responsible for moving pages back and forth between disk and memory. Unfortunately, ==this means that if mmap hits a page fault, the process will be blocked.==

* You never want to use mmap in your DBMS if you need to write.
* The DBMS (almost) always wants to control things itself and can do a better job at it since it knows more about the data being accessed and the queries being processed.
* The operating system is not your friend.

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220306012715423.png" alt="image-20220306012715423" style="zoom:33%;" />

It is possible to use the OS by using:

* **madvise**: Tells the OS know when you are planning on reading certain pages.
* **mlock**: Tells the OS to not swap memory ranges out to disk.
* **msync**: Tells the OS to flush memory ranges out to disk.

We do not advise using mmap in a DBMS for correctness and performance reasons.

Even though the system will have functionalities that seem like something the OS can provide, having the DBMS implement these procedures itself gives it better control and performance.

DBMS (almost) always wants to control things itself and can do a better job than the OS.

* Flushing dirty pages to disk in the correct order.
* Specialized prefetching.
* Buffer replacement policy.
* Thread/process scheduling.

# Database Storage

Problem #1: How the DBMS represents the database in files on disk.
Problem #2: How the DBMS manages its memory and moves data back-and-forth from disk.

## File Storage

The DBMS’s **storage manager** is responsible for managing a database’s files. It represents the files as a collection of pages. It also keeps track of what data has been read and written to pages as well how much free space there is in these pages.

### Database Pages

The DBMS organizes the database across one or more files in ==fixed-size== blocks of data called *pages*. 

* It can contain tuples, meta-data, indexes, log records...
* Most systems do not mix page types.
* Some systems require a page to be self-contained.

Each page is given a unique identifier. If the database is a single file, then the page id can just be the file offset. Most DBMSs have an indirection layer that maps a page id to a file path and offset. The upper levels of the system will ask for a specific page number. Then, the storage manager will have to turn that page number into a file and an offset to find the page.

Most DBMSs uses fixed-size pages to avoid the engineering overhead needed to support variable-sized pages. For example, with variable-size pages, deleting a page could create a hole in files that the DBMS cannot easily fill with new pages.

There are three concepts of pages in DBMS.

* Hardware page (usually 4 KB).
* OS page (4 KB).
* Database page (1-16 KB).

==The storage device guarantees an atomic write of the size of the hardware page==. If the hardware page is 4 KB and the system tries to write 4 KB to the disk, either all 4 KB will be written, or none of it will. ==This means that if our database page is larger than our hardware page, the DBMS will have to take extra measures to ensure that the data gets written out safely since the program can get partway through writing a database page to disk when the system crashes.==

### Database Heap

A heap file is an unordered collection of pages where ==tuples are stored in random order==.

* Create / Get / Write / Delete Page
* Must also support iterating over all pages.

The DBMS can locate a page on disk given a page id by using a linked list of pages or a page directory.

* **Linked List**: Header page holds pointers to a list of free pages and a list of data pages. However, if the DBMS is looking for a specific page, it has to do a sequential scan on the data page list until it finds the page it is looking for.

  <img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220306014527789.png" alt="image-20220306014527789" style="zoom:33%;" />

* **Page Directory**: DBMS maintains special pages that track locations of data pages along with the amount of free space on each page.

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220306014656227.png" alt="image-20220306014656227" style="zoom:33%;" />

## Page Layout

Every page includes a header that records meta-data about the page’s contents:

* Page size.
* Checksum.
* DBMS version.
* Transaction visibility.
* Self-containment. (Some systems like Oracle require this.)

A strawman approach to laying out data is to keep track of how many tuples the DBMS has stored in a page and then append to the end every time a new tuple is added. ==However, problems arise when tuples are deleted or when tuples have variable-length attributes.==

There are two main approaches to laying out data in pages: (1) slotted-pages and (2) log-structured.

### Slotted Pages

* Most common approach used in DBMSs today.
* Header keeps track of the number of used slots, the offset of the starting location of the last used slot, and a slot array, which keeps track of the location of the start of each tuple.
* To add a tuple, the slot array will grow from the beginning to the end, and the data of the tuples will grow from end to the beginning. The page is considered full when the slot array and the tuple data meet.

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220306015542853.png" alt="image-20220306015542853" style="zoom:33%;" />

After delete a tuple and then vacuum the page.

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220306015836158.png" alt="image-20220306015836158" style="zoom:33%;" />

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220306015855330.png" alt="image-20220306015855330" style="zoom:33%;" />

The DBMS needs a way to keep track of individual tuples. Each tuple is assigned a unique record identifier.

* Most common: *page_id + offset/slot*
* Can also contain file location info.

An application cannot rely on these IDs to mean anything.

### Log-Structured

* Stores records to file of how the database was modified (insert, update, deletes).
* To read a record, the DBMS scans the log file backwards and “recreates” the tuple.
* Fast writes, potentially slow reads.
* Works well on append-only storage because the DBMS cannot go back and update the data.
* To avoid long reads, the DBMS can have indexes to allow it to jump to specific locations in the log. It can also periodically compact the log. (If it had a tuple and then made an update to it, it could compact it down to just inserting the updated tuple.) The issue with compaction is that the DBMS ends up with write amplification. (It re-writes the same data over and over again.)

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220306020829545.png" alt="image-20220306020829545" style="zoom:33%;" />

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220306020854322.png" alt="image-20220306020854322" style="zoom:33%;" />

> **Tips**:
>
> 为什么读的时候是逆序扫描而不是顺序扫描，正常来说需要从头顺序扫描才能重建一条记录。逆序扫描的好处是对于 delete 和 insert 的记录友好，扫描到这两种记录的时候就不需要再向前扫了。

#### Indexes

Build indexes to allow it to jump to locations in the log.

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220306021225660.png" alt="image-20220306021225660" style="zoom:33%;" />

#### Compact

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220306021248792.png" alt="image-20220306021248792" style="zoom:33%;" />

#### Compaction

Compaction coalesces larger log files into smaller files by removing unnecessary records.

![image-20220306021355194](https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220306021355194.png)

## Tuple Layout

A tuple is essentially a sequence of bytes. It is the DBMS’s job to interpret those bytes into attribute types and values.

**Tuple Header**: Contains meta-data about the tuple.

* Visibility information for the DBMS’s concurrency control protocol (i.e., information about which transaction created/modified that tuple).
* ==Bit Map for NULL values==.
* ==Note that the DBMS does not need to store meta-data about the schema of the database here.==

**Tuple Data**: Actual data for attributes.

* Attributes are typically stored in the order that you specify them when you create the table.
* Most DBMSs do not allow a tuple to exceed the size of a page.

**Unique Identifier**:

* Each tuple in the database is assigned a unique identifier.
* Most common: page id + (offset or slot).
* An application cannot rely on these ids to mean anything.

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220306020510609.png" alt="image-20220306020510609" style="zoom:33%;" />

**Denormalized Tuple Data**: If two tables are related, the DBMS can “pre-join” them, so the tables end up on the same page. This makes reads faster since the DBMS only has to load in one page rather than two separate pages. However, it makes updates more expensive since the DBMS needs more space for each tuple.

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220306020409234.png" alt="image-20220306020409234" style="zoom:33%;" />

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220306020431045.png" alt="image-20220306020431045" style="zoom:25%;" />

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20220306020442585.png" alt="image-20220306020442585" style="zoom:25%;" />