如果對 Isolation Levels 記憶模糊可以參考這一篇：

[複習資料庫的 Isolation Level 與圖解五個常見的 Race Conditions](https://medium.com/@chester.yw.chu/複習資料庫的-isolation-level-與常見的五個-race-conditions-圖解-16e8d472a25c?postPublishedType=repub)

一開始我們先看一個例子。有兩個 Transaction 同時操作 gamer 這個表格，其中一個 select 所有的資料，另一個則在中間新增了一個新的玩家，Frank，然後 commit。在 MySQL InnoDB Engine 的環境下，使用 Repeatable Read Isolation (RR Isolation) 時，資料庫的行為如下圖：

![img](https://littleneko.oss-cn-beijing.aliyuncs.com/img/1*j4E-CkOqXJHc7xzH6ZnQmw.png)

<center>Phantom Read don’t occur</center>

從上圖可以看到，在 Transaction B 新增了一筆資料之後，Transaction A 還是只讀取到 5 筆資料，沒有玩家 Frank 的資料，[Phantom 現象](https://medium.com/@chester.yw.chu/複習資料庫的-isolation-level-與常見的五個-race-conditions-圖解-16e8d472a25c)並沒有發生。所以大家可能會問，MySQL InnoDB Engine 的 RR Isolation 是不是 Phantom Safe 的呢？網路上的確也有不少文章是這麼認為的。

但是讓我們繼續這個例子。Transaction A 的任務是在每週的最後一天為當下分數最高的前三名玩家增加 credit，前三名玩家的 credit 都各增加 1 分。依照上圖可以知道現在前三名的玩家分別是 Alice、Carol 跟 Bob，三個玩家的分數都達到了 740 分以上，所以可以很簡單的使用 Atomic Update (credit = credit + 1)，為所有分數達到 740 分以上的玩家 credit 加 1。

雖然目前資料庫實際上有 6 筆玩家的資料，但是從 Transaction A 的視角只有看到總共 5 筆玩家的資料。在這樣的情況下，Transaction A 所做的更新是不是理論上只會影響到這 5 筆資料呢？實際的實驗結果如下圖：

![img](https://littleneko.oss-cn-beijing.aliyuncs.com/img/1*s0_RCKos45xJAtXqRUCtBw.png)

<center>Phantom caused Write Skew</center>

從上圖中可以看到，在 Transaction A 執行更新指令後，如果馬上再重新讀取一次 gamer 表格，玩家 Frank 的資料竟然意外的出現在列表中，發生了 Phantom 現象。不僅如此，照原本的邏輯 Transaction A 應該只會為前 3 名的玩家增加 credit，但是因為 Frank 的分數也同樣高於 740 分，同樣也被增加了 credit。最後被增加 credit 的玩家總共有 4 個 ，比原本系統預計送出的 credit 還多。這種現象屬於 [Write Skew](https://medium.com/@chester.yw.chu/複習資料庫的-isolation-level-與常見的五個-race-conditions-圖解-16e8d472a25c)，在這個例子中是因為 Phamtom 而導致的 Write Skew。

## 誤解 1 ：MySQL Repeatable Read Isolation 可以避免 Phantom

這就是常見的第一個誤解。在做過第一個實驗後，我們常常會誤以為 MySQL 的 RR Isolation 是 Phantom Safe，但其實不是。MySQL InnoDB Engine 跟 PostgreSQL 一樣，它們 RR Isolation 的實作都是採用 [Snapshot Islolation](https://medium.com/@chester.yw.chu/複習資料庫的-isolation-level-與常見的五個-race-conditions-圖解-16e8d472a25c)。如果瞭解 Snapshot Isolation 的機制，就可以知道 Snapshot Isolation 在 read-only Transaction 中才可以避免 Phantom，但是像在像上面的例子使用的 read-write Transaction 中，就有可能出現 Phantom，進而導致 Write Skew。

> Snapshot isolation avoids phantoms in read-only queries, but in read-write transactions, phantoms can lead to particularly tricky cases of write skew.

Snapshot Isolation 會在每個 Transaction 第一次 SELECT 資料的時候，記錄下一個概念上像是時間標記的資料，每個 Transaction 在執行完第一次 SELECT 之後，Transaction 就只允許讀取:

1. 在這個時間標記之前就已經 commit 的資料
2. Transaction 自己本身對資料庫所做的更動

這就像對資料庫做了一個 Snapshot 一樣，Transaction 只能看到這個 Snapshot 的內容，但是無法讀取到其他 Transaction 所做的更新。但是在 InnoDB 的實作中，這個規則只限於 SELECT (DQL) 指令，其他像是 INSERT、UPDATE 和 DELETE 等 DML 指令，看到的就不是 Snapshot，而是指令執行當下所有已經被 commit 的資料。所以在上面的例子中，Transaction 在進行 UPDATE 指令時，看到的就是資料庫當下真實的資料，所有已經被 Commit 的資料都包含在內。這也就是為什麼 Transaction A 在執行 UPDATE 時可以看到玩家 Frank，並且幫他增加 credit。而且在執行完 UPDATE 後，重新 SELECT 一次時，玩家 Frank 也出現在列表中 (Transaction 可以看到自己所做的更新)。

同樣是採用 Snapshot Isolation 實作 RR Isolation 的 PostgreSQL，它的 Snapshot 就不只在 SELECT 指令有效，其他像 INSERT、UPDATE 和 DELETE 等 DML 指令上也都有效。所以上面例子中的 Phantom 現象並不會在 PostgreSQL 發生。

## 如何避免 Phantom 跟 Write Skew？

1. 在上面的例子裡我們可以用很簡單的指令來避免：

```
UPDATE gamer SET credit = credit + 1
WHERE name IN ("Alice", "Bob", "Carol");
```

因為是直接指定要增加 credit 的玩家，所以不會意外更新到剛被新增的玩家。

但是其實不是所有的 Write Skew 都可以用這種方法一勞永逸，每個 Write Skew 的情境都是不同的。當然直接改成 Serializable Isolation 就不會有 Write Skew 的發生，但是在不改變 Isolation Level 的情況下，為了避免 Write Skew，我們只能針對每種不同的 Write Skew 現象去設計不同的資料庫結構和 Query 方法，或是用 Materializing Conflicts 等技巧來防止 Write Skew 的發生。所以，在使用資料庫的 Isolation 功能時，我們必須先瞭解各個 Isolation Level 所有可能發生的 Conflict 和 Race Conditions，才有辦法在資料庫設計的階段就將這些因素考慮進去，避免後續的麻煩。

2. 另外一種比較暴力的方法就是使用 MySQL 的 Share Lock 或是 Exclusive Lock 指令，Block 住其它想更改資料的 Transaction，例如使用 MySQL 的 LOCK IN SHARE MODE 指令：

```
SELECT * FROM gamer LOCK IN SHARE MODE;UPDATE gamer SET credit = credit + 1
WHERE score >= 740;COMMIT;
```

3. 最直接的方法是將 MySQL 設定為 [Serialzable Isolation](https://medium.com/@chester.yw.chu/複習資料庫的-isolation-level-與常見的五個-race-conditions-圖解-16e8d472a25c)，MySQL 就會自動為所有的 SELECT 都加上 LOCK IN SHARE MODE。

必須注意的是，不管是手動加 Lock 或是使用 Serialzable Isolation，都會影響到效能。尤其如果沒有為欄位做好 Index ，就有可能會造成 Full-Table-Lock，應該盡量避免使用。

## 誤解 2：Repeatable Read Isolation 不會有 Lost Update

在 WIKI Isolation Level 的頁面上有下面這一張表：

![img](https://littleneko.oss-cn-beijing.aliyuncs.com/img/1*1jIMhU4wZ7O2Gg3QF_l5XA.png)

[Image Source](https://en.wikipedia.org/wiki/Isolation_(database_systems))

依據這張表，Repeatable Read Isolation 是可以避免 [Lost Update](https://medium.com/@chester.yw.chu/複習資料庫的-isolation-level-與常見的五個-race-conditions-圖解-16e8d472a25c) 現象的。但是實際在 MySQL 上測試，如下圖中的 Lost Update 例子卻成功了：

![img](https://littleneko.oss-cn-beijing.aliyuncs.com/img/1*SGa1A9vBHetIm53WFjKjlA.png)

<center>Lost Update</center>

在這個例子中，兩個 Transaction 同時進行賣出 Item A 的操作，一個賣出 4 個，一個賣出 1 個。理論上，庫存記錄應該從原本的 10 個減少為 5 個才對。但是最後庫存的記錄卻是 quantity = 9，Transaction A 的更新被 Transaction B 的覆蓋掉了，這就是 Lost Update 現象。Lost Update 現象通常都發生在像這種對資料庫做 read-modify-write 的操作。有的資料庫會實作 Lost Update 的自動偵測機制來避免這種錯誤，像是 PostgreSQL 的 RR Isolation。但是 MySQL 則沒有，所以 Lost Update 現象是有可能在 MySQL 的 RR Isolation 發生的。

## 如何避免 Lost Update？

1. 使用 Atomic Operations

```
UPDATE inventory SET quantity = quantity - 4
WHERE item = A;
```

2. 使用 SHARE LOCK / EXCLUSIVE LOCK (不建議)

```
SELECT * FROM inventory FOR UPDATE;UPDATE inventory SET quantity = 6 WHERE item = A;COMMIT;
```

## 正確的 Isolation Level 表格

原本 WIKI 給的表格應該改成如下：

![img](https://littleneko.oss-cn-beijing.aliyuncs.com/img/1*Ht6oQj3ULgoYvU_F6zMWLg.png)

Repeatable Read Isolation 只保證不會出現 Non-repeatable Read 現象，並不保證不會出現 Lost Update，依照每個資料庫對 RR Isolation 的實作方法不同，有的資料庫能避免 Lost Update 現象，有的資料庫則不能。還有一些例外像 PostgreSQL 的 RR Isolation 還可以避免 Phantom。

1992 年發表的 SQL Standard 對 RR Isolation 的定義其實非常模糊，只要能夠避免 [Dirty Read 和 Non-Repeatable Read](https://medium.com/@chester.yw.chu/複習資料庫的-isolation-level-與常見的五個-race-conditions-圖解-16e8d472a25c) 就可以稱作是 RR Isolation，在實作上並沒有特別的定義。而 Snapshot Isolation 剛好符合這項定義，所以 MySQL 跟 PostgreSQL 才會稱呼他們的 Snapshot Isolation 為 RR Isolation。PostgreSQL 還另外在 Snapshot Isolation 上實作了 Lost Update 自動偵測機制，但是 MySQL 則沒有。

Lost Update 和 Write Skew 等現象是在 SQL Standard 之後才被發表的，目前都沒有對這些現象訂定出新的 Isolation Level 標準。所以對於一個資料庫是否是 Lost Update Safe，我們無法直接從資料庫設定的 Isolation Level 得知，必須另外去了解資料庫背後對 RR Isolation 的實作，才能判斷。所以，每個資料庫的 Isolation Level 表格都會有一些差異，這邊分別列出 MySQL 跟 PostgreSQL 的表格。

MySQL

![img](https://littleneko.oss-cn-beijing.aliyuncs.com/img/1*1b85GId5OCbuRnZLhzba-A.png)

PostgreSQL

![img](https://littleneko.oss-cn-beijing.aliyuncs.com/img/1*q33nDX8pJjYqRNfPBtEdpw.png)

## 誤解 3：MySQL Range Locks on Indexed and Non-indexed Column

MySQL 的文件中介紹它的 [Range Lock](https://medium.com/@chester.yw.chu/複習資料庫的-isolation-level-與常見的五個-race-conditions-圖解-16e8d472a25c) 採用的是 Next-Key Lock，Next-Key Lock 只對有 Index 的欄位有作用，沒有做 Index 的欄位則沒有作用，且可能造成 Full Table Lock。我們先看下面的 SELECT 指令：

```
SELECT * FROM student WHERE height >= 170 FOR UPDATE;
```

在 MySQL RR Isolation Level 中，SELECT 指令並不會對資料做任何的 Lock，除非額外下 Shared Lock 或 Exclusive Lock 指令。像在上面的例子使用 FOR UPDATE 指令，就會對所有 SELECT 出來的資料做 Exclusive Lock。對資料做 Shared Lock 或 Exclusive Lock 之後，MySQL 還會另外做 Range Lock。以上面的例子來說，會對 height 這個欄位做 Range Lock，Lock 的範圍是 170 到無限大，不允許其他 Transaction 新增任何 height 的值介於這個範圍內的資料，如下圖：

![img](https://littleneko.oss-cn-beijing.aliyuncs.com/img/1*7pRoOa8fxQ6V8dqDnCt51g.png)

在上圖中，Transaction B 可以很順利的新增一筆 height = 160 的資料，但是想要新增另外一筆 height = 180 的資料時，會被 Transaction A 的 Range Lock Block 住，要等到 Transaction A Commit 後才能執行。這個機制的好處是可以只 Lock 所有跟 Transaction A 有關的『資料 Range』，而不是 Lock 整張 Table ，減少對效能的影響。要特別注意的是在 MySQL RR Isolation，如果沒有額外下 Shared Lock 或是 Exclusive Lock 指令，Range Lock 就不會生效。

現在我們改看 weight 這個欄位。與 height 欄位的差別是，weight 欄位並沒有做 index，如果對 weight 欄位做一樣的操作時，結果如下圖：

![img](https://littleneko.oss-cn-beijing.aliyuncs.com/img/1*Mq80_PGd2FJ1XP-o7DCcNA.png)

在上圖中，Transaction B 想要新增一筆 weight = 50 的資料。雖然 50 並不在 Range Lock 的範圍 (58 到無限大)，卻還是被 Block 住了。這是因為 MySQL 的 Range Lock 其實是 Index-record Lock，當 weight 欄位沒有做 Index 時，就沒有該欄位的 Index Record 可以做 Lock，為了繼續維持 Transaction 之間的 Isolation，MySQL 就只好 Lock 整張 student 表格。所以其實不只是無法新增 weight = 50 的資料，在 Transaction A Commit 前，任何對 student 表的新增跟修改都是不允許的。如果沒有特別注意，很容易在不知情的情況下造成 Full Table Lock，大大的影響效能。

## 小結

在上面的幾個例子中我們可以看到 MySQL 的 Repeatable Read Isolation 對 Lost Update、Phantom 跟 Write Skew 現象的行為。而必須做這些實驗的原因，就是：

> Nobody really knows what repeatable read means.

這是 [Designing Data-Intensive Applications](https://www.amazon.com/Designing-Data-Intensive-Applications-Reliable-Maintainable/dp/1449373321) 這本書裡面對 Repeatable Read Isolation 的註解。其他三個 Isolation Level 我們都可以很清楚的知道它們分別避免哪些 Race Conditions，但是 Repeatable Read Isolation 的行為則依照每個資料庫的實作而有所不同。需要靠使用者自己去閱讀文件或是瞭解資料庫背後的實作方法，才能夠判別。讓我們再複習一次這張表格：

![img](https://littleneko.oss-cn-beijing.aliyuncs.com/img/1*Ht6oQj3ULgoYvU_F6zMWLg.png)

## References

- WIKI: [Isolation (database systems)](https://en.wikipedia.org/wiki/Isolation_(database_systems))
- [Designing Data-Intensive Applications](https://www.amazon.com/Designing-Data-Intensive-Applications-Reliable-Maintainable/dp/1449373321)
- [SQL Standard 1992, ISO/IEC 9075:1992](http://www.contrib.andrew.cmu.edu/~shadow/sql/sql1992.txt)
- [Understanding MySQL Isolation Levels: Repeatable-Read](https://blog.pythian.com/understanding-mysql-isolation-levels-repeatable-read/)
- [InnoDB Locking](https://dev.mysql.com/doc/refman/5.7/en/innodb-locking.html#innodb-gap-locks)
- [MySQL 5.7: Transaction Isolation Levels](https://dev.mysql.com/doc/refman/5.7/en/innodb-transaction-isolation-levels.html)
- [PostgreSQL 11: Transaction Isolation](https://www.postgresql.org/docs/11/transaction-iso.html)



---

https://medium.com/@chester.yw.chu/%E5%B0%8D%E6%96%BC-mysql-repeatable-read-isolation-%E5%B8%B8%E8%A6%8B%E7%9A%84%E4%B8%89%E5%80%8B%E8%AA%A4%E8%A7%A3-7a9afbac65af