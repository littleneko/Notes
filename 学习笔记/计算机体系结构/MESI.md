## **状态介绍**
在缓存行的元信息中有一个 Flag 字段，它会表示 4 种状态，分为对应如下所说的 M、E、S、I 状态

| **状态** | **描述** |
| --- | --- |
| M(Modified) | 代表该缓存行中的内容被修改了，==并且该缓存行只缓存在该 CPU 中==。这个状态的==缓存行中的数据和内存中的不一样==，在未来的某个时刻它会被写入到内存中（当其他 CPU 要读取该缓存行的内容时。或者其他 CPU 要修改该缓存对应的内存中的内容时 |
| E(Exclusive) | 代表==该缓存行对应内存中的内容只被该 CPU 缓存==，其他 CPU 没有缓存该缓存对应内存行中的内容。这个状态的==缓存行中的内容和内存中的内容一致==。该缓存可以在任何其他 CPU 读取该缓存对应内存中的内容时变成S状态。或者本地处理器写该缓存就会变成M状态 |
| S(Shared) | 该状态意味着==数据不止存在本地 CPU 缓存中，还存在别的 CPU 的缓存中==。这个状态的==缓存行中的内容和内存中的数据是一致的==。当其他 CPU 修改该缓存行对应的内存的内容时会使该缓存行变成 I 状态 |
| I(Invalid) | 代表==该缓存行中的内容是无效的== |

## **总线嗅探机制**
CPU 和内存通过总线（BUS）互通消息，CPU 感知其他 CPU 的行为（比如读、写某个缓存行）就是是通过嗅探（Snoop）线性中其他 CPU 发出的请求消息完成的，有时 CPU 也需要针对总线中的某些请求消息进行响应。这被称为”总线嗅探机制“。这些消息类型分为请求消息和响应消息两大类，细分为 6 小类。

| **消息类型** | **请求/响应** | **描述** |
| --- | --- | --- |
| Read | 请求 | 通知其他处理器和内存，当前处理器准备读取某个数据。该消息内包含待读取数据的内存地址 |
| Read Response | 响应 | 该消息内包含了被请求读取的数据。该消息可能是主内存返回的，也可能是其他高速缓存嗅探到Read 消息返回的 |
| Invalidate | 请求 | 通知其他处理器删除指定内存地址的数据副本（缓存行中的数据）。所谓“删除”，其实就是更新下缓存行对应的 FLAG（MESI 那个） |
| Invalidate Acknowledge | 响应 | 接收到 Invalidate 消息的处理器必须回复此消息，表示已经删除了其高速缓存内对应的数据副本 |
| Read Invalidate | 请求 | 此消息为 Read 和 Invalidate 消息组成的复合消息，主要是用于通知其他处理器当前处理器准备更新一个数据了，并请求其他处理器删除其高速缓存内对应的数据副本。接收到该消息的处理器必须回复 Read Response 和 Invalidate Acknowledge 消息 |
| Writeback | 响应 | 消息包含了需要写入内存的数据和其对应的内存地址 |

## **状态流转**
<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/image-20211202022240290.png" alt="image-20211202022240290" style="zoom:50%;" />

### **记忆要点**
有些眼花缭乱，个人总结了一些要点，方便记忆。

- I 状态有 5 条外出的线（local read 有两种可能的状态转移）
   - 当其他 CPU 没有这个缓存行时，当前 CPU 从内存取缓存行更新到 Cache，并把状态设置为 E
   - 当其他 CPU 有这份数据时：
      - 如果其他 CPU 是 M 状态，则同步其缓存到主存，然后两个 CPU 状态再变为 S
      - 如果其他 CPU 是 S 或 E，则两个 CPU 状态都变为 S
- MSE 三个状态都是有 4 条外出的线（对应 4 种操作，只会流转到一个状态）
- 而想从其他状态流转到达 E 状态，比较刁钻。只能从 **I 状态**进行 **local read**，并且**其他 CPU 没有该缓存行数据**时，三个限定条件（加粗部分）缺一不可。



> 1. 假设 CPU0、CPU1、CPU2、CPU3 中有一个缓存行（包含变量 x）都是 S 状态。
> 2. 此时 CPU1 要对变量 x 进行写操作，这时候通过总线嗅探机制，CPU0、CPU2、CPU3 中的缓存行会置为I状态（无效），然后给 CPU1 发响应（Invalidate Acknowledge），收到全部响应后 CPU1 会完成对于变量 x 的写操作，更新了 CPU1 内的缓存行为 M 状态，但不会同步到内存中。
> 3. 接着 CPU0 想要对变量 x 执行读操作，却发现本地缓存行是 I 状态，就会触发 CPU1 去把缓存行写入（回写）到内存中，然后 CPU0 再去主存中同步最新的值。



## **Store Buffer**
当然前面的描述隐藏了一些细节，比如实际 CPU1 在执行写操作，更新缓存行的时候，其实并不会等待其他 CPU 的状态都置为 I 状态，才去做些操作，这是一个同步行为，效率很低。当前的 CPU 都引入了 Store Buffer（写缓存器）技术，也就是在 CPU 和 cache 之间又加了一层 buffer，在 CPU 执行写操作时直接写StoreBuffer，然后就忙其他事去了，等其他 CPU 都置为 I 之后，CPU1 才把 buffer 中的数据写入到缓存行中。


## **Invalidate Queue**
看前面的描述，执行写操作的 CPU1 很聪明啦，引入了 store buffer 不等待其他 CPU 中的对应缓存行失效就忙别的去了。而其他 CPU 也不傻，实际上他们也不会真的把缓存行置为 I 后，才给 CPU0 发响应。他们会写入一个 Invalidate Queue（无效化队列），还没把缓存置为 I 状态就发送响应了。
后续 CPU 会异步扫描 Invalidate Queue，将缓存置为 I 状态。和 Store Buffer 不同的是，在 CPU1 后续读变量 x 的时候，会先查 Store Buffer，再查缓存。而CPU0 要读变量 x 时，则不会扫描 Invalidate Queue，所以存在脏读可能。


# Links
1. [https://zhuanlan.zhihu.com/p/351550104](https://zhuanlan.zhihu.com/p/351550104)
2. [https://wudaijun.com/2019/04/cpu-cache-and-memory-model/](https://wudaijun.com/2019/04/cpu-cache-and-memory-model/)
3. [https://blog.csdn.net/wll1228/article/details/107775976](https://blog.csdn.net/wll1228/article/details/107775976)
