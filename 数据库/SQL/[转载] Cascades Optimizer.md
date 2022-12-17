# 概述

在数据库中，SQL是用户首先感知的部分，用户只需进行『声明式』地编程，不需要指明具体的执行过程，即可从复杂的存储结构中获得想要的数据。在此过程中，优化器发挥的作用功不可没，向前承接用户查询，向后为执行指明方向，可谓是数据库的大脑。

对优化器的研究从上世纪七十年代既已开始，到如今已经发展了数十年，其中有很多里程碑式的进展，例如 Volcano/Cascades。在近些年新出现的一些数据库中，例如 TiDB、CockroachDB、GreenPlum、Calcite 等，也已经开始探索和尝试 Cascades 技术。

本文将围绕 Cascades Optimizer，对其问题背景、理论原理、设计空间进行分析，同时也会对具体的工程实现做一些介绍。

# 问题定义

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-f1d719b8de4a750288501ec4d54a5d7f_1440w.jpg" alt="img" style="zoom:50%;" />

首先需要讨论的一个问题是，什么是优化器？

很多时候我们在讨论优化器的时候，其实讨论的是优化规则。一些常见的优化规则，例如谓词下推、常量折叠、子查询内联，这些想必不用赘述。对于具体规则来说，有些规则一定能带来收益，减小查询的代价，但另一些却未必，甚至会增加查询的代价。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-d7bd8620b272fd426c157dafd45390fe_1440w.jpg" alt="img" style="zoom: 50%;" />

例如这里将谓词下推到具体的 Scan 算子上，由于能够减少 Join 时需要处理的数据量，显然是能够带来收益的。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-539f7763f5be6392439afca301832915_1440w.jpg" alt="img" style="zoom:50%;" />

但对于 Join 顺序的枚举来说则未必，这里将原本的 `(A JOIN B) JOIN C` 替换成 `(B JOIN C) JOIN A`，也许能带来收益。例如 A 有1000 条数据，B 有 100 条，C 有 10 条数据，三个表之间存在一定的 Join 谓词使得，`A JOIN B` 返回 10000 条数据，`B JOIN C` 返回 200 条数据；如果采用最朴素的 NestLoop，那么前一个执行计划需要处理 `1000 * 100 + 10000 * 10 = 200000` 次循环，而后一个执行计划则需要处理 `100 * 10 + 200 * 1000 = 200100` 次循环，因此前者会更优一点。

## Cost & Heuristic

那么此时就会面临选择，需要从多个执行计划中选择出最优的。一种也许可行的方式就是『经验主义』，也称之为 Heuristic-Based，例如『按照表从小到大的顺序 Join』就是一条 Heuristic，但比较遗憾的是，这条规则并不适用于所有场景，在上面的 `(B JOIN C) JOIN A` 的执行计划并不如从大到小来的好。另一种方式则是『数据主义』，也称之为 Cost-Based，这种方式就需要事先进行统计，对数据量、数据分布等情况进行估算，遇到选择时就可以利用这些统计信息来评估不同的执行计划的好坏。

事实上这两种方法并不是泾渭分明的，如今的数据库基本已经没有完全基于经验的优化器实现了，多少都会基于代价来对计划进行评估，并且也会包含人为设定的经验。也就是说，优化器可以分解成三部分：

- statistics：维护统计信息，用于代价评估
- cost model：基于统计信息，对具体的执行计划评估代价
- plan enumeration：对可能的执行计划进行搜索，对其代价进行评估，选择最优执行计划

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-a369cbeda3b3e886ff7debdf2afe66b8_1440w.jpg" alt="img" style="zoom:50%;" />

## 动态规划

优化器的统计信息、代价模型、计划搜索几个问题都值得深究，这里仅仅涉猎计划搜索这一问题。

对于一个成熟的优化器来说，可能有几百条规则，每条规则都会作用于查询树，并产生一个逻辑等价的执行计划，因此我们可以把优化的问题理解为搜索的问题。更进一步，可以应用动态规划的思想，即可以把原问题分解成子问题来解决复杂问题。动态规划有几点需要注意（引用自 Wikipedia）：

- 最优子结构：如果问题的最优解所包含的子问题的解也是最优的，我们就称该问题具有最优子结构性质（即满足最优化原理）
- 无后效性：即子问题的解一旦确定，就不再改变，不受在这之后、包含它的更大的问题的求解决策影响。
- 重叠子问题：自顶向下对问题进行求解时，可能会遇到重复的子问题，对于子问题的解可以记录下来避免重复计算

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-294369f498767f93e2390dcc275d11c8_1440w.jpg" alt="img" style="zoom:50%;" />

具体到查询这一问题，对于初始的 Join Tree 来说，Join 算子会有多种实现，例如 NestLoop 和 HashJoin，也即 Join 可以分解为两个子问题，NestLoop 和 HashJoin。而对于 NestLoop 来说，需要求解其子节点 `SCAN A` 和 `SCAN B`，SCAN 也有多种实现，例如 SeqScan 和 IndexScan。同时，这里遇到了重叠子问题，在求解 HashJoin 的时候也需要计算 SCAN A。

通过将原问题分解成对子问题的求解，再佐之以代价模型，即可在茫茫的搜索空间中，选中那万中无一的查询计划了。

# 自底向上

具体在搜索时有两种流派，一种是以 **System R** 为代表的自底向上，另一种则是 **Cascades** 流派的自顶向下。

## 访问路径



<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-263b3c0d36ee7f7a439e6dc9f7c21b9b_1440w.jpg" alt="img" style="zoom:50%;" />



自底向上的算法会先计算基表的访问路径（Access Path），通常来说存在几种：顺序扫描、索引扫描、组合索引等，而存在多个索引时，每个索引都视作一个访问路径。接着，枚举两表 Join，这里同时还需要对 Join 的物理实现进行枚举，所以第二层的状态会比第一层多许多。一层层往上搜索，即可得到多表 Join 的执行计划。

## 动态规划



<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-6bdeef50781893341328ffe96a26d78d_1440w.jpg" alt="img" style="zoom:50%;" />

在搜索过程中，如果是纯粹地枚举所有可能的组合，则搜索空间会非常大。因此通常会对 Join Tree 的形状进行限制，也会在搜索过程中进行一定的剪枝。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-e4542c0825a7070b6438b016cf606f2d_1440w.jpg" alt="img" style="zoom:50%;" />

例如这里的两种典型的 Join Tree，Left-deep 和 Bushy-Join。相比于 Bushy-Tree 的 `(2n-2)!/(n-1)!` 的复杂度，Left-Deep 只有 `n!`，搜索空间小了很多。

## Interesting Order

在搜索过程中，每一层不需要保留所有的组合，而是保留代价最低的即可。但需要考虑到一个问题，两表 Join 的最优解，未必能得到三表 Join 的最优解，例如两表用了 HashJoin，那么输出的结果会是无序的；相比之下，如果用 MergeJoin，两表 Join 可能不是代价最小的， 但是在三表 Join 时，就可以利用其有序性，对上层的 Join 进行优化。

为了刻画这个问题，引入了 Interesting Order，即上层对下层的输出结果的顺序感兴趣。因此自底向上枚举时，A JOIN B 不仅仅是保留代价最小的，还需要对每种 Interesting Order 的最小代价的 Join 进行保留。例如 `A JOIN B` 输出的顺序可能是 `(A.x), (A.x, B.y), (None)` 等多种可能性，就需要保留每种 Interesting Order。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-56921cbe9bca56774d34ce8647dea63f_1440w.jpg" alt="img" style="zoom:50%;" />



这里其实引出一个问题，自底向上的搜索过程中，下层无法知道上层需要的顺序，即便保留所有的 Order，也未必能得到最优解。例如对 A、B 两表做笛卡尔积再排序，其代价可能要比先排序在做 Join 要高，但是在枚举 Join 时，无法知道上层需要的顺序，也就无法搜索这个计划。

## PostgreSQL实现

```c
join_search() {
    join_levels[1] = initial_rels;
    for (level : 2 -> N) {
        join_search_one_level() {
            // linear
            for (outer : join_levels[level-1]) {
                for (inner : join_levels[1]) {
                    if (overlap(outer, inner)) {
                        continue;
                    }
                    if (!has_restriction(outer, inner)) {
                        continue;
                    }
                    join_levels[level].add_path(make_join_rel(outer, inner));
				}
            }
            // bushy
            for (k : 2 -> N - 2) {
                for (outer : join_levels[k]) {
                    for (inner : join_levels[N-k]) {
                        ...
                    }
                }
            }
            // cross-product
        }
    }
}
```

PostgreSQL 实现的 Join 算法就是经典的自底向上的动态规划，上面是其伪代码：

- 首先计算基表访问路径，PostgreSQL 实现了 SeqScan、IndexScan、BitmapScan、TidScan 等方式
- 搜索空间的第一层即为基表
- 向上搜索每一层，先尝试 linear tree，枚举上一层的每个 Relation，与第一层的 Relation 进行组合，如果没有重叠并且有 Join 谓词连接，即调用 add_path 增加一条访问路径
- add_path：并不是直接把访问路径加到这一层，而是先评估其代价和 Interesting Order，如果代价更优，或者产生了新的 Interesting Order，才会加到这一层的访问路径中
- bushy tree：枚举 bushy tree 会把 `[2, N-2]` 层的 Relation 和 N-k 层的 Relation 进行组合
- cross-product：如果上述两种枚举都没有搜索出可行的 Join，则采取笛卡尔积，这个产生的结果通常较多

注意到其中一个细节，尝试组合两个 Relation 时，会判断两个 Relation 是否存在 Join 谓词，例如 JOIN A, B ON A.x = B.x，如果有连接谓词作为过滤条件，生成的结果会大大减少。这种先枚举再测试连通性的方式称之为『generate and test』，在特定的场景下效率并不高，test 这个步骤占据了很大开销，存在一定的优化空间，后面会做介绍。

# 自顶向下-Cascades

经过以上的铺垫，自底向上的方法基本有了一个轮廓，同时我们在探索的过程中也意识到自底向上的一些局限性：

- 适用于 Join Enumeration 问题，但对其他的优化并不适用
- 在处理 Interesting Order 问题时，不能覆盖所有的搜索空间
- 剪枝有限，很有可能下层会产生一些代价非常大的解决方案，本可以预先剪枝掉

为此，我们尝试另一种思路，自顶向下的搜索方案：Cascades。Cascades 其实是继承了 Volcano Optimizer Generator，并做了很多优化，也对算法细节做了更多工作，因此我们直接跳过 Volcano 来看 Cascades。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-294369f498767f93e2390dcc275d11c8_1440w.jpg" alt="img" style="zoom:50%;" />

自顶向下个人感觉更加直观一点，对于一个 Operator Tree 来说，从根节点往下遍历，每个节点可以做多种变换：

- Implementation：逻辑算子可以转换成物理算子；例如 Join 转换成 NestLoop 或者 HashJoin 等
- Exploration：逻辑算子可以做等价变换；例如交换 Inner Join 的两个子节点，即可枚举 Join 顺序

## Memo⭐️

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-1c8cb3c04d66b05cbd0e8b22f4a9a729_1440w.jpg" alt="img" style="zoom: 67%;" />

自顶向下的搜索过程中，整个搜索空间会形成一个 Operator Tree 的森林，因此很重要的一个问题是，如何高效地保存搜索状态。

Cascades 首先将整个 Operator Tree 按节点拷贝到一个 **Memo** 的数据结构中，每个 Operator 放在一个 Group。对于有子节点的 Operator 来说，将原本对Operator 的直接引用，变成对 Group 的引用。例如上图的 Group 0，引用了 Group 1 和 Group 2。

![img](https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-21d1e0ec3c0b1bb4c4d7a8eb5cf717c0_1440w.jpg)

而每个 Group 中会存在多个成员，成员通常称之为 **Group Expression**。成员之间是逻辑等价的，也就意味着他们输出的结果是一样的。随着搜索过程的推进，对 Operator Tree 进行变换时会产生新的 Operator Tree，这些 Tree 仍然存储在 Memo 中。例如上图的的 Group1，既包含了初始的 Scan A，也包含了后续搜索产生的 TableScan、SortedIDXScan。由于 Group 引用的是其他 Group，这里可以视作形成了一个 Group Tree，例如上面的 Group 7 引用了 Group3、Group4，Group3 又是一个 Join 算子，引用了 Group1、Group2。

在搜索完成之后，我们可以从每个 Group 中选择出最优的 Operator，并递归构建其子节点，即可得到最优的 Operator Tree。	

## Stats Derivation



<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-9697eb9488705ebdbc127c6b8bf603ae_1440w.jpg" alt="img" style="zoom: 67%;" />



在搜索过程中，需要对 Group Expression 的代价进行评估，而代价评估则依赖于统计信息。统计信息的构建是一个自底向上的过程，每个基表维护直方图等统计信息，向上可进一步推导出 Join 的统计信息。由于 Group 中的多个 Expression 是逻辑等价的，因此他们共享一个 statistics。这一过程称之为『Stats Derivation』。

## Branch and bound

前面提到自顶向下的搜索可以进行更多的剪枝，这里的原理是根据代价的 upper bound 剪枝。将最初的 Operator Tree 的代价计算其 lower bound 和 upper bound，之后的搜索过程中，如果还没搜索到最底层的节点，其代价已经超过了 upper bound，那么这个解决方案即可放弃，不会更优只会雪上加霜。

理想情况下，这种剪枝能过滤掉很多不必要的搜索，但依赖于初始计划的代价。初始计划如果很糟糕，代价很大，对后续的搜索将无法发挥剪枝的作用。因此通常的优化器会在搜索之前进行称之为 Transformation/Rewrite/Normalize 的阶段，应用一些 Heuristic 的规则，预先对 Plan 进行优化，减小后面的搜索空间。

## Search

优化规则和搜索过程是 Cascades 的核心，也是优化器的工作重心。在传统的优化器实现中，往往是面向过程的，一条一条地应用优化规则，对 Operator Tree 进行变换。这种 hardcode 的方式往往难以扩展，想增加一条规则较为困难，需要考虑规则之间的应用顺序。而 Cascades 在处理这一问题时，将搜索过程与具体的规则解耦，用面向对象的方式对优化规则进行建模，规则的编写不需要关心搜索过程。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-1e18a23c28f5bf838fb9f4d9e2764ee3_1440w.jpg" alt="img" style="zoom:50%;" />

这里的搜索过程分解为几种 Task：

- Optimize Group：对一个 Group 进行优化，具体来说就是对其中每个 Expression 进行优化
- Optimize Expression：优化一个 Expression，对每个 Expression 应用优化规则，并寻找代价最小的 Expression
- Explore Group & Explore Expression：Explore 过程是对逻辑算子进行等价变化
- Apply Rule：应用具体的优化规则，从逻辑表达式推导出等价的逻辑表达式，或者从逻辑表达式推导物理表达式
- Optimize Input：对代价进行估算，这是一个自底向上的过程，需要递归地计算子节点的统计信息和代价，再计算当前节点

这些 Task 会进行递归搜索，因此有两种选择，一种是直接递归调用，另一种则是用一个显式的的 Stack，对任务进行调度：

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-8525b33d8bad1edf4df83cc73eea0513_1440w.jpg" alt="img" style="zoom:50%;" />

## Property Enforcer

前面提到 Interesting Order 的问题，在自顶向下的搜索过程中可以更加优雅地解决。这里讲 Interesting Order 的问题推广到 Property，在分布式数据库的场景下，Property 包含了数据分布的方式。例如分布式 HashJoin 要求两个表按 照 Hash 分布，如果不满足这个属性，则需要对数据进行一次重分布。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/v2-aa35dccd5a93cfa0db73423508fa8c35_1440w.jpg" alt="img" style="zoom:67%;" />

自顶向下的搜索过程可以用需求驱动的方式来计算属性，例如需要对 T1.a 进行排序的方式有多种，即可分解成多个子问题，对 HashJoin 的结果进行归并排序，或者把数据收集到一个节点之后再进行排序，都是可能的解决方案。对于不同的解决方案仍然是基于代价来选择出最优的方案，从而形成整体的最优解。

## Cascades

至此，基本覆盖了 Cascades 的原理，虽然理解起来很简单，但具体实现需要考虑更多的问题，工程实现的细节在这里无法一一枚举，有兴趣可参考具体的实现。在工业界，Peleton、Orca、SQL Server、Calcite、Cockroach 等都算是 Cascades 的实现，其中不乏开源的优秀实现。



---

作者：[hellocode](https://www.zhihu.com/people/hellocode-ming)
链接：https://zhuanlan.zhihu.com/p/73545345
来源：知乎