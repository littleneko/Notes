- 标记清除（mark-and-sweep）
   - Bitmap marking
   - Lazy sweeping
- 引用计数

_碎片问题_

- Mark-Compact
- Copying GC
- Cheney

- 三色标记
- 分代


三色

- 黑色black，表明对象被 collector 访问过，属于可到达对象
- 灰色gray，也表明对象被访问过，但是它的子节点还没有被 scan 到
- 白色white，表明没有被访问到，如果在本轮遍历结束时还是白色，那么就会被收回

增加的中间状态灰色要求 mutator 不会把黑色对象直接指向白色对象（这称为三色不变性 tri-color invariant），collector 就能够认为黑色对象不需要在 scan，只需要遍历灰色对象即可。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1566198275506-4a0e37a7-e163-4223-a136-8185caea3c79.png" alt="image.png" style="zoom:50%;" />

上图描述了一个违法着色不变性的情况。假设 A 已经被完全地 scan，它本身被标为黑色，字节点被标为灰色，现在假设 mutator 交换了 A–>C 与 B–>D 的指针，现在指向 D 的指针只有 A，而 A 已经被完全地 scan 了，如果继续 scan 过程的话，B 会被置为黑色，C 会被重新访问，而 D 则不会被访问到，在本轮遍历后，D 由于是白色，会被错误的认为是垃圾并被回收掉。


分代
虽然对象的生命周期因应用而异，但对于大多数应用来说，80% 的对象在创建不久即会成为垃圾


1. 垃圾回收的算法与实现
1. Golang’s Real-time GC in Theory and Practice: [https://making.pusher.com/golangs-real-time-gc-in-theory-and-practice/?spm=a2c4e.11153940.blogcont573819.32.b9e922bd8nwhPY](https://making.pusher.com/golangs-real-time-gc-in-theory-and-practice/?spm=a2c4e.11153940.blogcont573819.32.b9e922bd8nwhPY)
1. Getting Started with the G1 Garbage Collector: [https://www.oracle.com/technetwork/tutorials/tutorials-1876574.html](https://www.oracle.com/technetwork/tutorials/tutorials-1876574.html)
1. Java HotSpot Garbage Collection: [https://www.oracle.com/technetwork/java/javase/tech/index-jsp-140228.html](https://www.oracle.com/technetwork/java/javase/tech/index-jsp-140228.html)
1. HotSpot Virtual Machine Garbage Collection Tuning Guide: [https://docs.oracle.com/en/java/javase/12/gctuning/introduction-garbage-collection-tuning.html#GUID-8A443184-7E07-4B71-9777-4F12947C8184](https://docs.oracle.com/en/java/javase/12/gctuning/introduction-garbage-collection-tuning.html#GUID-8A443184-7E07-4B71-9777-4F12947C8184)
1. Wilson P R. Uniprocessor garbage collection techniques[C]//International Workshop on Memory Management. Springer, Berlin, Heidelberg, 1992: 1-42.
1. Printezis T, Detlefs D. A generational mostly-concurrent garbage collector[M]. ACM, 2000.
1. Detlefs D, Flood C, Heller S, et al. Garbage-first garbage collection[C]//Proceedings of the 4th international symposium on Memory management. ACM, 2004: 37-48.
1. Dijkstra E W, Lamport L, Martin A J, et al. On-the-fly garbage collection: an exercise in cooperation[J]. Communications of the ACM, 1978, 21(11): 966-975.
1. Memory Management in the Java HotSpotTM Virtual Machine
1. 深入浅出垃圾回收（四）分代式 GC: [https://liujiacai.net/blog/2018/08/18/generational-gc/](https://liujiacai.net/blog/2018/08/18/generational-gc/)
1. [https://www.memorymanagement.org/glossary/t.html#term-tri-color-marking](https://www.memorymanagement.org/glossary/t.html#term-tri-color-marking)
1. 关于Golang GC的一些误解--真的比Java算法更领先吗: [https://mp.weixin.qq.com/s/eDd212DhjIRGpytBkgfzAg](https://mp.weixin.qq.com/s/eDd212DhjIRGpytBkgfzAg)
1. Go GC: Prioritizing low latency and simplicity: [https://blog.golang.org/go15gc](https://blog.golang.org/go15gc)
1. Hotspot的safe point: [https://xhao.io/2018/03/safepoint-2/](https://xhao.io/2018/03/safepoint-2/)
1. Safepoints: Meaning, Side Effects and Overheads: [http://psy-lob-saw.blogspot.com/2015/12/safepoints.html](http://psy-lob-saw.blogspot.com/2015/12/safepoints.html)
1. Our Collectors: [https://blogs.oracle.com/jonthecollector/the-unspoken-phases-of-cms](https://blogs.oracle.com/jonthecollector/the-unspoken-phases-of-cms)
1. The Unspoken - Phases of CMS: [https://blogs.oracle.com/jonthecollector/our-collectors](https://blogs.oracle.com/jonthecollector/our-collectors)
1. 深入探究 JVM | Safepoint 及 GC 的触发条件: [https://www.sczyh30.com/posts/Java/jvm-gc-safepoint-condition/](https://www.sczyh30.com/posts/Java/jvm-gc-safepoint-condition/)
1. Hotspot的safe point: [https://xhao.io/2018/03/safepoint-2/](https://xhao.io/2018/03/safepoint-2/)
1. GC safe-point (or safepoint) and safe-region: [http://xiao-feng.blogspot.com/2008/01/gc-safe-point-and-safe-region.html](http://xiao-feng.blogspot.com/2008/01/gc-safe-point-and-safe-region.html)
