# 目标文件格式

- 可重定位目标文件（ `.o` 文件）
- 可执行目标文件（linux上即为 `ELF` 文件）
- 共享目标文件（ `.so` 和 `.a` 文件）

# 可重定位目标文件
<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1566743933764-d9b34652-3bb2-4b68-b9ac-d82a7c065fe4.png" alt="image.png" style="zoom: 50%;" />

- **.text** 已编译程序的机器代码
- **.rodata** 只读数据，比如 print 语句中的 format 串
- **.data** ==已初始化==的==全局==和==静态== C 变量。局部 C 变量在运行时被保存在栈中，既不出现在 .data 中也不出现在 .bss 中
- **.bss** ==未初始化==的==全局==和==静态== C 变量，以及所有被初始化为 0 的全局或静态变量。在目标文件中不占实际空间，仅仅是一个占位符；运行时，在内存中分配这些变量，初始值为 0。
- **.symtab** 符号表，存放程序中==定义==和==引用==的==函数==和==全局变量==的信息
- **.rel.text** 一个 .text 节中位置的列表，当链接器把这个目标文件和其他文件组合时，需要修改这些位置
- **.rel.data** 被模块引用或定义的所有全局变量的重定位信息
- **.debug** 调试符号表，-g 时才有
- **.line**
- **.strtab**

# 符号和符号表
在链接器的上下文中一共有 3 种符号

- 由模块 m 定义被能被其他模块引用的 **`全局符号`** 。去那句链接器符号对应于非静态的 C 函数和全局变量
- 由其他模块定义并被模块 m 引用的全局符号。这些符号称为 **`外部符号`** ，对应于其他模块中定义的非静态 C 函数和全局变量
- 只被模块 m 定义和引用的 **`局部符号`** 。他们对应于带 static 属性的 C 函数和全局变量
> 需要注意的是==本地链接器符号==和==本地程序变量==是不同的，==`.symtab` 中的符号表不包含本地非静态程序变量的任何符号==。这些符号在运行时在栈中被管理，链接器对此符号不感兴趣。
> 另外，带有 C static 属性的本地过程变量是不在栈中管理的。相反，编译器在 .data 或 .bss 中为每个定义分配空间，并在符号表中创建一个有唯一名字的本地链接器符号。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1566745418786-31bde851-6f64-488c-a958-ca525ed11dc5.png" alt="image.png" style="zoom:50%;" />

_$ readelf -a main.o_

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1566745968683-a6955239-3f4d-4753-a1b1-6d92adee2bb8.png" alt="image.png" style="zoom: 50%;" />


# 符号解析
## 强弱符号
在编译时，编译器向汇编器输出每个全局符号，或者是_强(strong)_或者是_弱(weak)_，而汇编器把这个信息隐含地编码在可重定位目标文件的符号表里。==函数==和==已初始化的全局变量==是==**强符号**==，==未初始化的全局变量==是==**弱符号**==。


根据强弱符号的定义，Linux 链接器使用下面的规则来处理多重定义的符号名：

- 规则1：不允许有多个同名的强符号
- 规则2：如果有一个强符号和多个弱符号同名那么选择强符号
- 规则3：如果有多个弱符号同名那么从这些弱符号中任意选择一个
## 静态链接
```bash
linux> gcc -c main2.c
linux> gcc -static -o prog2c main2.o rivector
```

图 7-8 概括了链接器的行为。 `--static` 参数告诉编译器驱动程序，链接器应该构建一个完全链接的可执行目标文件，它可以加载到内存并运行，在加载时无须更进一步的链接。 `-lvector` 参数是 `libvector.a` 的缩写， `-L` 参数告诉链接器在当前目录下查找 `libvector.a` 。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1566746377440-a838a8d0-7bc2-48b4-a89a-34952f560ff9.png" alt="image.png" style="zoom:50%;" />

# 重定位
一旦链接器完成了符号解析这一步，就把代码中的每个符号引用和正好一个符号定义（即它的一个输入目标模块中的一个符号表条目）关联起来。此时，链接器就知道它的输入目标模块中的代码节和数据节的确切大小。现在就可以开始重定位步骤了，在这个步骤中,将合并输入模块，并为每个符号分配运行时地址。重定位由两步组成：


- ==**_重定位节和符号定义_**==      在这一步中，链接器将所有相同类型的节合并为同一类型的新的聚合节。例如，来自所有输入模块的 `.data` 节被全部合并成一个节，这个节成为输出的可执行目标文件的 `.data` 节。然后，链接器将运行时内存地址赋给新的聚合节，赋给输入模块定义的每个节，以及赋给输人模块定义的每个符号。当这一步完成时，程序中的每条指令和全局变量都有唯一的运行时内存地址了。
- ==**_重定位节中的符号引用_**==    在这一步中，==链接器修改代码节和数据节中对每个符号的引用，使得它们指向正确的运行时地址==。要执行这一步，链接器依赖于可重定位目标模块中称为==_重定位条目 (relocation entry)_== 的数据结构，我们接下来将会描述这种数据结构。
## 重定位条目
==当汇编器生成一个目标模块时，它并不知道数据和代码最终将放在内存中的什么位置，它也不知道这个模块引用的任何外部定义的函数或者全局变量的位置。==所以无论何时汇编器遇到对最终位置未知的目标引用，它就会生成一个==重定位条目==，告诉链接器在目标文件合并成可执行文件时如何修改这个引用。代码的重定位条目放在 `.rel.text` 中。已初始化数据的重定位条目放在 `.re1.data` 中。

图 7-9 展示了 ELF 重定位条目的格式。 `offset` 是需要被修改的引用的节偏移。 `symbol` 标识被修改引用应该指向的符号。 `type` 告知链接器如何修改新的引用。 `addend` 是一个有符号常数，一些类型的重定位要使用它对被修改引用的值做偏移调整。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1566920688142-5a5c751f-8f58-4fff-9d68-34bf0751fc5b.png" alt="image.png" style="zoom:50%;" />


ELF 定义了 32 种不同的重定位类型，有些相当隐秘。我们只关心其中两种最基本的重定位类型：

- **R_X86_64_PC32**    重定位一个使用 32 位 PC 相对地址的引用。回想一下 3.6.3 节，一个 PC 相对地址就是距程序计数器 (PC) 的当前运行时值的偏移量。当 CPU 执行一条使用 PC 相对寻址的指令时，它就将在指令中编码的 32 位值加上 PC 的当前行时值，得到有效地址(如 `call` 指令的目标)，PC 值通常是下一条指令在内存中的地址。
- **R_X86_64_32**    重定位一个使用 32 位绝对地址的引用。通过绝对寻址，CPU 直接使用在指令中编码的 32 位值作为有效地址,不需要进一步修改。

这两种重定位类型支持 x86-64 小型代码模型 (small code model)，该模型假设可执行文件中的代码和数据的总体大小小于 2GB，因此在运行时可以用 32 位 PC 相对地址来访问。GCC 默认使用小型代码模型。大于 2GB 的程序可以用 `-mcmodel=medium` (中型代码模型)和 `-mcmodel=large` (大型代码模型)标志来编译，不过在此我们不讨论这些模型。
## 重定位符号引用
<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1566748980749-2b282aa1-b2be-43dd-935f-317338f6024d.png" alt="image.png" style="zoom:50%;" />

_$ objdump -dx main.o_

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1566752647952-309be669-17e4-4630-bdb1-3e988c1824c5.png" alt="image.png" style="zoom:50%;" />

`main` 函数引用了两个全局符号， `array` 和 `sum` 。为每个引用，编译器产生一个重定位条目。这些重定位条目告诉链接器对 `sum` 的引用要使用 32 位 PC 相对地址进行重定位，而对 `array` 的引用要使用32位绝对地址进行重定位。

### 重定位 PC 相对引用
上图可以看到 `call` 指令（_e8 00 00 00 00_）开始于节偏移 `0xe` 的地方，包括一字节的操作码 `0xe8` ，后面跟着的是对目标 `sum` 的32位PC相对引用的占位符（_00 00 00 00_）。

相应的重定位条目如下：

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1566747942782-073c00c0-19a4-4233-80a7-0e7ec099ed30.png" alt="image.png" style="zoom:50%;" />

这些字段告诉链接器修改开始于偏移量 `0xf` 处（_0xf = 0xe + 0x1，即需要重定位的目标在距离.text起始位置0xf处_）的32位PC相对引用（即上图中 `main.o` 中的4字节的占位符 _00 00 00 00_)，这样它在运行时才会指向 `sum` 。

现在假设连接器已经确定，
	**ADDR(s) = ADDR(.text) = _0x4004d0_**（运行时 `.text` 节的起始地址）
	**ADDR(r.symbol) = ADDR(sum) = _0x4004e8_** （运行时 `sum` 函数的起始地址）

连接器首先计算出引用的运行时地址，
	**refaddr = ADDR(s) + r.offset**
					**= _0x4004d0_ + _0xf_**
					**= _0x4004df_**

即需要重定位运行时地址为 `0x4004df` 位置的PC相对引用

然后，更新该引用，使得它在运行时指向 `sum` 例程，
**refptr = (ungigned)(ADDR(r.symbol) + r.addend - refaddr)**
			**= (unsigned)(_0x4004e8_            + (-4)          - _0x4004df_)**
			**= (unsigned)(_0x5_)**

在最后得到的可执行目标文件中， `call` 指令有如下的重定位形式：

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1566749553896-7332e062-4103-42d9-a799-91f8ddd9fb16.png" alt="image.png" style="zoom:50%;" />

如图， `call` 指令的起始地址在 `0x4004de` ，重定位后的目标（ `0x5` )在 `0x4004df` 处。


在运行时， `call` 指令将存放在 `0x4004de` 处，当CPU执行 `call` 指令时，PC的值为 `0x4004e3` ，即紧随在 `call` 指令之后的指令的地址（_0x4004de + 0x5 = 0x4004e3_）。为了执行这条指令，CPU执行以下步骤：

1. **将PC压入栈中**
1. **PC <- PC + _0x5_ = _0x4004e3 + 0x5 = 0x4004e8_**

因此要执行的下一条指令就是 `sum` 的第一条指令的地址

---

#### 重定位完成后的结果
最终生成的可执行文件的结果

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1566752582898-b170db6e-deff-4d86-afaa-30f066a9cc51.png" alt="image.png" style="zoom:50%;" />

_refaddr = 0x4004d0 + 0xf = 0x4004df_
_*refptr = 0x4004e8 - 0x4 - 0x4004df = 0x5_


_PC <- PC + 0x08 = 0x4004e3 + 0x05 = 0x4004e8_

---

从上面一堆复杂的计算中，简化一下实际上就是计算的 `sum` 的起始地址（_0x4004e8_）和 `call` 指令的下一条指令的地址（_0x4004e3，即当前PC的值_）之间的差值。这样，在执行的时候，就可以直接跳转到 `sum` 执行。


_即 0x4004e8 - 0x4 - 0x4004e3 = 0x4004e8 - (0x4 + 0x4004de) = 0x4004e8 - 0x4004e3 = 0x5_
### 重定位绝对引用
重定位绝对引用相当简单，例如，图7-11的第4行中， `mov` 指令将 `arrary` 的地址（一个32位立即数值）复制到寄存器 `%edi` 中。mov指令（_bf 00 00 00 00_）开始于节偏移量 `0x9` 的位置，包括1字节的操作码 `0xbf` ，后面跟着对32位绝对引用的占位符。

对应的重定位条目如下：

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1566834335637-9839c044-8228-40e9-8f06-c89f6668b61e.png" alt="image.png" style="zoom:50%;" />

这些字段告诉链接器要修改从偏移量 `0xa` （_0xa = 0x0 + 0x1，即需要重定位的目标在距离.data起始位置0xa处_）开始的绝对引用（00 00 00 00)，这样在运行时它将指向 `array` 的地一个字节。

现在，假设链接器已经确定，
	**ADDR(r.symbol) = ADDR(array) = _0x601018_** (运行时 `array` 数组的起始地址)

链接器使用图7-10中的算法修改引用如下：
**\*refptr = (unsigned)(ADDR(r.symbol) + r.addend)**
			**= (unsigned)(_0x601018_           + 0)**
			**= (unsigned)(_0x601018_)**

在得到的可执行文件中，该引用有如下的重定位形式：

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1566835182771-44469abc-2e2b-4f72-8bed-f58ca3c061f9.png" alt="image.png" style="zoom:50%;" />

即运行时 `mov` 指令能正确地将 `array` 的地址 `0x601018` 复制到寄存器 `%edi` 

重定位后的可执行文件中 `.data` 节如下所示

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1566835363420-e87b81de-740f-4cd8-973d-02b9cecef640.png" alt="image.png" style="zoom:50%;" />


# 可执行目标文件
<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1566835552022-989d00a2-9d59-4636-b0f9-7fbac9889361.png" alt="image.png" style="zoom:50%;" />

ELF文件被设计地很容易加载到内存，可执行文件连续的片（chunk）被映射到连续的内存段。程序头部表（programer header table）描述了这种映射关系。

<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1566835760691-28edc59e-7507-43b9-a9ed-475e8dfd2703.png" alt="image.png" style="zoom:50%;" />

## 程序运行时的内存映像
<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1566835801552-e65999ae-3a08-460e-b841-2c8bd9d782e3.png" alt="image.png" style="zoom:50%;" />

# 动态链接库
<img src="https://littleneko.oss-cn-beijing.aliyuncs.com/img/1566835891965-6e284148-b704-4bb5-8c06-ad89f9c3ee7a.png" alt="image.png" style="zoom:50%;" />

动态链接是指在程序加载时，动态完成一些链接过程。没有任何 `libvector.so` 的代码和数据节真正被复制到prog21中。反之，链接器复制了一些重定位和符号表信息，它们使得可以在运行时解析对 `libvector.so` 中代码和数据的引用。


当加载器加载和运行可执行文件prog21时，它利用7.9节中讨论过的技术，加载部分链接的可执行文件prog21。接着它注意到prog21包含一个 `.interp` 节，这一节包含动态链接器的路径名，动态链接器本身就是一个共享目标(如在Linux系统上的 `ld-linux.so` )。==加载器不会像它通常所做地那样将控制传递给应用，而是加载和运行这个动态链接器。然后，动态链接器通过执行下面的**重定位**完成链接任务==：

- 重定位 `libc.so` 的文本和数据到某个内存段
- 重定位 `libvector.so` 的文本和数据到另一个内存段
- 重定位prog21中所有对由 `libc.so` 和 `libvector.so` 定义的符号的引用



最后，动态链接器将控制传递给应用程序。从这个时刻开始，共享库的位置就固定了，并目在程序执行的过程中都不会改变。

# 位置无关代码

TODO

# 附录

本文用到的两段代码：

```c
/* main.c */
/* $begin main */
int sum(int *a, int n);

int array[2] = {1, 2};

int main() 
{
    int val = sum(array, 2);
    return val;
}
/* $end main */
```


```c
/* sum.c */
/* $begin sum */
int sum(int *a, int n)
{
    int i, s = 0;
    
    for (i = 0; i < n; i++) { 
        s += a[i];
    }
    return s;
}        
/* $end sum */
```

**gcc 编译的流程**

1. 预处理（cpp）：main.c -> main.i
1. 编译（cc1）：main.i -> main.s
1. 汇编（as）：main.s -> main.o
1. 链接（ld）：xxx.o -> main(elf)

# Reference

1. Bryant R E, David Richard O H, David Richard O H. Computer systems: a programmer's perspective[M]. Upper Saddle River: Prentice Hall, 2003.
