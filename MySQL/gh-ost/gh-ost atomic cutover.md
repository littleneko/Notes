### Safe, locking, atomic, asynchronous table swap
Do read the aforementioned previous posts; the quick-quick recap is: we want to be able to **LOCK** a table **tbl**, then do some stuff, then swap it out and put some **ghost** table in its place. MySQL does not allow us to **rename tbl to tbl_old, ghost to tbl** if we have locks on **tbl** in that session.

The solution we offer is now based on two connections only (as opposed to three, in the _optimistic_ approach). "Our" connections will be C10, C20. The "normal" app connections are C1..C9, C11..C19, C21..C29.

- Connections C1..C9 operate on **tbl** with normal DML: **INSERT, UPDATE, DELETE**
- Connection C10: **CREATE TABLE tbl_old (id int primary key) COMMENT='magic-be-here'**
- Connection C10: **LOCK TABLES tbl WRITE, tbl_old WRITE**
- Connections C11..C19, newly incoming, issue queries on **tbl** but are blocked due to the **LOCK**
- Connection C20: **RENAME TABLE tbl TO tbl_old, ghost TO tbl**
This is blocked due to the **LOCK**, _but_ gets prioritized on top connections C11..C19 and on top C1..C9 or any other connection that attempts DML on **tbl**
- Connections C21..C29, newly incoming, issue queries on **tbl** but are blocked due to the **LOCK** and due to the **RENAME**, waiting in queue
- Connection C10: checks that C20's **RENAME** is applied (looks for the blocked **RENAME** in processlist)
- Connection C10: **DROP TABLE tbl_old**
Nothing happens yet; **tbl** is still locked. All other connections still blocked.
- Connection C10: **UNLOCK TABLES
BAM!** The **RENAME** is first to execute, **ghost** table is swapped in place of **tbl**, then C1..C9, C11..C19, C21..C29 all get to operate on the new and shiny **tbl**

**Some notes**

- We create **tbl_old** as a blocker for a premature swap
- It is allowed for a connection to **DROP** a table it has under a **WRITE LOCK**
- A blocked **RENAME** is always prioritized over a blocked **INSERT/UPDATE/DELETE**, no matter who came first

### What happens on failures?
Much fun. Just works; no rollback required.

- If C10 errors on the **CREATE** we do not proceed.
- If C10 errors on the **LOCK** statement, we do not proceed. The table is not locked. App continues to operate as normal.
- If C10 dies just as C20 is about to issue the**RENAME**:
   - The lock is released, the queries C1..C9, C11..C19 immediately operate on **tbl**.
   - C20's **RENAME** immediately fails because **tbl_old** exists.
The entire operation is failed, but nothing terrible happens; some queries were blocked for some time is all. We will need to retry everything
- If C10 dies while C20 is blocked on **RENAME**: Mostly similar to the above. Lock released, then C20 fails the **RENAME** (because **tbl_old** exists), then all queries resume normal operation
- If C20 dies before C10 drops the table, we catch the error and let C10 proceed as planned: **DROP, UNLOCK**. Nothing terrible happens, some queries were blocked for some time. We will need to retry
- If C20 dies just after C10 **DROP**s the table but before the unlock, same as above.
- If both C10 and C20 die, no problem: **LOCK** is cleared; **RENAME** lock is cleared. C1..C9, C11..C19, C21..C29 are free to operate on **tbl**.

No matter what happens, at the end of operation we look for the **ghost** table. Is it still there? Then we know the operation failed, "atomically". Is it not there? Then it has been renamed to **tbl**, and the operation worked atomically.

A side note on failure is the matter of cleaning up the magic **tbl_old**. Here this is a matter of taste. Maybe just let it live and avoid recreating it, or you can drop it if you like.

### Impact on app
App connections are guaranteed to be blocked, either until **ghost** is swapped in, or until operation fails. In the former, they proceed to operate on the new table. In the latter, they proceed to operate on the original table.

### Impact on replication
Replication only sees the **RENAME**. There is no **LOCK** in the binary logs. Thus, replication sees an atomic two-table swap. There is no table-outage.

### Conclusion
This solution satisfies all we wanted to achieve. We're unlikely to give this another iteration. Well, if some yet-more-elegant solution comes along I'll be tempted, for the beauty of it, but the solution offered in this post is simple-enough, safe, atomic, replication friendly, and should make everyone happy.

### Reference

1. [https://github.com/github/gh-ost/issues/82](https://github.com/github/gh-ost/issues/82)
2. [http://code.openark.org/blog/mysql/solving-the-facebook-osc-non-atomic-table-swap-problem](http://code.openark.org/blog/mysql/solving-the-facebook-osc-non-atomic-table-swap-problem)
3. [http://code.openark.org/blog/mysql/solving-the-non-atomic-table-swap-take-ii](http://code.openark.org/blog/mysql/solving-the-non-atomic-table-swap-take-ii)
4. [http://code.openark.org/blog/mysql/solving-the-non-atomic-table-swap-take-iii-making-it-atomic](http://code.openark.org/blog/mysql/solving-the-non-atomic-table-swap-take-iii-making-it-atomic)
