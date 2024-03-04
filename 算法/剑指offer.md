# 基本数据结构
## 数组

   - **二维数组搜索（剑指offer，逆序）**，C字符串替换，数组合并

    ![image.png](https://cdn.nlark.com/yuque/0/2020/png/385742/1587298766202-5ff51e48-5197-4d69-9d4d-934dd5eed9ce.png#averageHue=%23ebebeb&height=309&id=zWkRW&originHeight=1234&originWidth=1486&originalType=binary&ratio=1&rotation=0&showTitle=false&size=593201&status=done&style=none&title=&width=372)
## 链表

   - 逆序输出：栈，递归（先访问后 print）
## 树（二叉树）

   - 前序遍历，中序遍历，后续遍历（递归/迭代），宽度优先遍历
   - 二叉搜索树
   - 堆，红黑树

1. 根据前序遍历和中序遍历重建二叉树

![image.png](https://cdn.nlark.com/yuque/0/2020/png/385742/1587299697353-273aaf63-1626-448e-8ada-544339336c73.png#averageHue=%23f4f4f4&height=227&id=D87MQ&originHeight=454&originWidth=1030&originalType=binary&ratio=1&rotation=0&showTitle=false&size=111715&status=done&style=none&title=&width=515)
## 栈和队列

- 两个栈实现队列，两个队列实现栈
# 基本算法和数据操作
## 查找和排序

- 顺序查找、二分查找、哈希表查找、二叉搜索树查找
- 插入排序、冒泡排序、归并排序、快速排序
- 快排的另一个用处：快选，选择第K大的数

1. 旋转数组的最小元素， `[3, 4, 5, 1, 2]` 中的最小元素

方法：二分搜索，注意特例（ `[1, 0, 1, 1, 1]` , `1, 1, 1, 0, 1` ）
## 递归和循环
递归的缺点：

   - 可能栈溢出
   - 效率低：函数调用的开销，重复计算（以斐波拉契数列为例）

![image.png](https://cdn.nlark.com/yuque/0/2020/png/385742/1587306456031-f25fbec9-8bf5-412b-a847-e582e5621460.png#averageHue=%23e7e7e7&height=217&id=AOnbP&originHeight=434&originWidth=756&originalType=binary&ratio=1&rotation=0&showTitle=false&size=79832&status=done&style=none&title=&width=378)
扩展：青蛙跳台阶，矩形覆盖可以转化为斐波拉契数列
## 位操作

- 判断整数的二进制中 `1` 的个数
- 判断是否是2^n
- 两个数m和n需要改变二进制多少位才能得到另一个数

![image.png](https://cdn.nlark.com/yuque/0/2020/png/385742/1587309746298-7d603006-b2aa-4f84-a293-266e2991f00f.png#averageHue=%23e5e5e5&height=85&id=XWzfg&originHeight=222&originWidth=1568&originalType=binary&ratio=1&rotation=0&showTitle=false&size=138577&status=done&style=none&title=&width=600)
# 经典算法

- **完整性**：**功能测试、边界测试、负面测试**（整型溢出、0、负数、递归和循环的边界条件、错误的输入即输入不符合要求）
- **鲁棒性**：**检查输入（空指针，字符串为空）**

## 面试题11：实现 double Power(double base, int exponent) 不考虑大数问题
[https://leetcode-cn.com/problems/shu-zhi-de-zheng-shu-ci-fang-lcof/](https://leetcode-cn.com/problems/shu-zhi-de-zheng-shu-ci-fang-lcof/)
需要注意的点：

   - `exponent` 是零和负数的情况
   - `base` 是 `0` 且 `exponent` 是负数的时候非法，1/0非法
   - 判断 `base` 为 `0` 的方法，由于浮点数精度的问题， `double` 不能直接判等，只能取与 `0.0` 的差的绝对值在某一个很小的范围内即认为相等

优化：累乘的方法效率低，可以优化为logn时间复杂度：
![](https://cdn.nlark.com/yuque/__latex/75b7e108f94ffe0dbb8c42ec7c81f24f.svg#card=math&code=a%5En%20%3D%0A%5Cbegin%7Bcases%7D%0Aa%5E%7Bn%2F2%7D%2Aa%5E%7Bn%2F2%7D%2C%20%20%26%20%5Ctext%7Bif%20%24n%24%20is%20even%7D%20%5C%5C%0Aa%5E%7B%28n-1%29%2F2%7D%2Aa%5E%7B%28n-1%29%2F2%7D%2Aa%2C%20%26%20%5Ctext%7Bif%20%24n%24%20is%20odd%7D%0A%5Cend%7Bcases%7D&height=45&id=zpMYa)
然后使用递归计算
> 递归可以优化成迭代

## 面试题12：打印 `1` 到最大的 `n` 位数
需要注意的点：n 位数可能会溢出
解法1：字符串模拟数字加法然后打印
解法2：实际上是要打印 `N` 个 `0` 到 `9` 的全排列

## 面试题13：[LinkedList] O(1) 时间内删除单向链表给定节点
思路：要删除链表一个节点，那么一般要拿到它的前一个节点，需要从head开始遍历，复杂度为 `O(n)` 。我们这里可以直接把当前节点的下一个节点的值赋值给当前节点，转化为删除当前节点的下一个节点
需要注意的边界条件：要删除的节点是最后一个节点，链表只有一个节点

## 面试题14：调整数组，使奇数位于前半部分，偶数位于后半部分
思路：两个指针指向数组的开头和结尾，扫描并交换不符合条件的数字

## 面试题15：[LinkedList] 链表倒数第k个节点
思路：两个相隔k-1个节点的指针，从头遍历一次
需要注意的点：1. 检查输入head为空；2. 链表总长度小于k； 3. k = 0
扩展：

   - 求链表中间节点：快慢指针
   - 判断链表是否有环

## 面试题16：[LinkedList] 反转链表
需要注意的点：头指针是null，链表只有一个节点

## 面试题17：[LinkedList] 合并排序链表
注意：输入的链表为空

## 面试题18：[Tree] 子树问题（[LeetCode] 572. Subtree of Another Tree [Easy]）
[https://leetcode.com/problems/subtree-of-another-tree/](https://leetcode.com/problems/subtree-of-another-tree/)
注意：输入为空，只有左子树或右子树
```java
/**
 * Definition for a binary tree node.
 * public class TreeNode {
 *     int val;
 *     TreeNode left;
 *     TreeNode right;
 *     TreeNode(int x) { val = x; }
 * }
 */
class Solution {
    public boolean isSubtree(TreeNode s, TreeNode t) {
        if (s == null) return t == null;
        return isEqual(s, t) || isSubtree(s.left, t) || isSubtree(s.right, t);
    }

    private boolean isEqual(TreeNode s, TreeNode t) {
        if (s == null && t == null) return true;
        if (s == null || t == null) return false;
        
        if (t.val != s.val) return false;
        return isEqual(s.left, t.left) && isEqual(s.right, t.right);
    }
}
```

## 面试题19：[Tree] 镜像二叉树（[LeetCode] 226. Invert Binary Tree, 101 [Easy]）
[https://leetcode.cn/problems/er-cha-shu-de-jing-xiang-lcof/](https://leetcode.cn/problems/er-cha-shu-de-jing-xiang-lcof/)
Invert a binary tree.
**Example:**
Input:
```
		 4
   /   \
  2     7
 / \   / \
1   3 6   9
```
Output:
```
		 4
   /   \
  7     2
 / \   / \
9   6 3   1
```
**Trivia:**
This problem was inspired by [this original tweet](https://twitter.com/mxcl/status/608682016205344768) by [Max Howell](https://twitter.com/mxcl):
```java
/**
 * Definition for a binary tree node.
 * public class TreeNode {
 *     int val;
 *     TreeNode left;
 *     TreeNode right;
 *     TreeNode(int x) { val = x; }
 * }
 */
class Solution {
    public TreeNode invertTree(TreeNode root) {
        // 注意root为null的判断
        if (root == null || (root.left == null && root.right == null)) return root;

        TreeNode tmp = root.left;
        root.left = root.right;
        root.right = tmp;

        invertTree(root.left);
        invertTree(root.right);
        return root;
    }
}
```
## 面试题21：[Stack]包含min函数的栈（[LeetCode] 155. Min Stack [Easy]）
[https://leetcode-cn.com/problems/bao-han-minhan-shu-de-zhan-lcof/](https://leetcode-cn.com/problems/bao-han-minhan-shu-de-zhan-lcof/)
    ![image.png](https://cdn.nlark.com/yuque/0/2020/png/385742/1588004781727-c286de29-7caa-40a0-b44c-33c38410a458.png#averageHue=%23ececec&height=100&id=fLIV9&originHeight=354&originWidth=1766&originalType=binary&ratio=1&rotation=0&showTitle=false&size=104728&status=done&style=none&title=&width=500)
    ![image.png](https://cdn.nlark.com/yuque/0/2020/png/385742/1588004798058-bafd8c27-e1ea-4597-a550-f7f256b80851.png#averageHue=%23f0f0f0&height=122&id=yQKYi&originHeight=436&originWidth=1792&originalType=binary&ratio=1&rotation=0&showTitle=false&size=113088&status=done&style=none&title=&width=500)
## 面试题22：[Stack] 验证栈的压入弹出序列（[LeetCode] 946. Validate Stack Sequences [Medium]）
[https://leetcode-cn.com/problems/zhan-de-ya-ru-dan-chu-xu-lie-lcof/](https://leetcode-cn.com/problems/zhan-de-ya-ru-dan-chu-xu-lie-lcof/)
```java
public class LeetCode946 {
    public boolean validateStackSequences(int[] pushed, int[] popped) {
        Stack<Integer> stack = new Stack<>();
        int i = 0, j = 0;
        while (i < pushed.length) {
            stack.push(pushed[i++]);
            while (!stack.empty() && j < popped.length && stack.peek() == popped[j]) {
                stack.pop();
                j++;
            }
        }

        return j == popped.length;
    }

    public static void main(String[] args) {
        int[] pushed = new int[]{1, 2, 3, 4, 5};
        int[] popped = new int[]{4, 3, 5, 1, 2};
        new LeetCode946().validateStackSequences(pushed, popped);
    }
}
```
## 面试题23：[Tree] 层序遍历二叉树（[LeetCode] 102. Binary Tree Level Order Traversal, 107 [Medium]）
[https://leetcode.cn/problems/cong-shang-dao-xia-da-yin-er-cha-shu-lcof/](https://leetcode.cn/problems/cong-shang-dao-xia-da-yin-er-cha-shu-lcof/)
```java
public class LeetCode102 {
    // Definition for a binary tree node.
    public class TreeNode {
        int val;
        TreeNode left;
        TreeNode right;

        TreeNode(int x) {
            val = x;
        }
    }

    public List<List<Integer>> levelOrder(TreeNode root) {
        List<List<Integer>> ans = new ArrayList<>();
        if (root == null) return ans;
        Queue<TreeNode> queue = new LinkedList<>();
        queue.offer(root);

        while (!queue.isEmpty()) {
            List<Integer> level = new ArrayList<>();
            int size = queue.size();
            for (int i = 0; i < size; i++) {
                TreeNode tmp = queue.poll();
                if (tmp != null) {
                    level.add(tmp.val);
                    if (tmp.left != null) queue.offer(tmp.left);
                    if (tmp.right != null) queue.offer(tmp.right);
                }
            }
            ans.add(level);
        }
        return ans;
    }
}
```
## 面试题24：[Tree] 判断是否是二叉搜索树的后续遍历序列（[LeetCode] 255. Verify Preorder Sequence in Binary Search Tree [Medium]）
[https://leetcode.cn/problems/er-cha-sou-suo-shu-de-hou-xu-bian-li-xu-lie-lcof/](https://leetcode.cn/problems/er-cha-sou-suo-shu-de-hou-xu-bian-li-xu-lie-lcof/)
**Example**
```
Input: [5, 7, 6, 9, 11, 10, 8]
Output: true
Explanation: 
     8
    / \
   6   10
  / \  / \
 5  7 9  11
```

解题思路：最后一个一个数字 `8` 是root节点， `[5, 6, 7]` 是左子树， `[9, 11, 10]` 是右子树，满足左子树比根节点值小，右子树比根节点值大，然后就可以继续递归判断了。

## 面试题25：[Tree] 二叉树中和为某一值的路径（[LeetCode] 112|113|437. Path Sum [Easy]）
ref: [https://www.yuque.com/littleneko/yxpqg3/kd32hd](https://www.yuque.com/littleneko/yxpqg3/kd32hd)

## 面试题26：[LinkedList] 复杂链表的复制（[LeetCode] 138. Copy List with Random Pointer [Medium]）
[https://leetcode.cn/problems/fu-za-lian-biao-de-fu-zhi-lcof/](https://leetcode.cn/problems/fu-za-lian-biao-de-fu-zhi-lcof/)

## 面试题27：[Tree][LinkedList] 二叉搜索树与双向链表（[LeetCode] 426. Convert Binary Search Tree to Sorted Doubly Linked List [Medium]）
[https://leetcode.cn/problems/er-cha-sou-suo-shu-yu-shuang-xiang-lian-biao-lcof/](https://leetcode.cn/problems/er-cha-sou-suo-shu-yu-shuang-xiang-lian-biao-lcof/)
ref: [https://www.yuque.com/littleneko/yxpqg3/ec4ifx](https://www.yuque.com/littleneko/yxpqg3/ec4ifx)

## 面试题28：[DFS] 字符串的排列
[https://leetcode.cn/problems/zi-fu-chuan-de-pai-lie-lcof/](https://leetcode.cn/problems/zi-fu-chuan-de-pai-lie-lcof/)

**解题思路：**
**排列方案数量**： 对于一个长度为 nn 的字符串（假设字符互不重复），其排列共有 n×(n−1)×(n−2)…×2×1 种方案。

**排列方案的生成方法**： 根据字符串排列的特点，考虑深度优先搜索所有排列方案。即通过字符交换，先固定第 1 位字符（ n 种情况）、再固定第 2 位字符（n−1 种情况）、... 、最后固定第 n 位字符（ 1 种情况）。
    ![image.png](https://cdn.nlark.com/yuque/0/2020/png/385742/1588603224281-cb7b4474-52ad-412d-805a-a0de47d4bc67.png#averageHue=%23000000&height=421&id=AayMq&originHeight=841&originWidth=1120&originalType=binary&ratio=1&rotation=0&showTitle=false&size=69235&status=done&style=none&title=&width=560)
**重复方案与剪枝**： 当字符串存在重复字符时，排列方案中也存在重复方案。为排除重复方案，需在固定某位字符时，保证 “每种字符只在此位固定一次” ，即遇到重复字符时不交换，直接跳过。从 DFS 角度看，此操作称为 “剪枝” 。
    ![image.png](https://cdn.nlark.com/yuque/0/2020/png/385742/1588603237879-739d518b-c1da-4948-a57e-b677485646a5.png#averageHue=%23010101&height=421&id=W2S9I&originHeight=841&originWidth=1120&originalType=binary&ratio=1&rotation=0&showTitle=false&size=76994&status=done&style=none&title=&width=560)

**递归解析**：

1. **终止条件**： 当 x = len(c) - 1 时，代表所有位已固定（最后一位只有 1 种情况），则将当前组合 c 转化为字符串并加入 res，并返回；
2. **递推参数**： 当前固定位 x ；
3. **递推工作**： 初始化一个 Set ，用于排除重复的字符；将第 x 位字符与 i∈[x,len(c)] 字符分别交换，并进入下层递归；
   1. **剪枝**： 若 c[i] 在 Set 中，代表其是重复字符，因此“剪枝”；
   2. 将 c[i] 加入 Set ，以便之后遇到重复字符时剪枝；
   3. **固定字符**： 将字符 c[i] 和 c[x] 交换，即固定 c[i] 为当前位字符；
   4. **开启下层递归**： 调用 dfs(x+1) ，即开始固定第 x+1 个字符；
   5. **还原交换**： 将字符 c[i] 和 c[x] 交换（还原之前的交换）；
```java
class Solution {
    public String[] permutation(String s) {
        List<String> res = new ArrayList<>();
        backtracking(res, s.toCharArray(), 0);
        return res.toArray(new String[0]);
    }

    private void backtracking(List<String> res, char[] s, int idx) {
        //System.out.println("idx=" + idx + ", s=" + Arrays.toString(s));
        if (idx == s.length - 1) {
            res.add(String.valueOf(s));
            return;
        }
        
        HashSet<Character> set = new HashSet<>();
        // 固定第idx位字符，有 (s.length - idx) 种选择
        for (int i = idx; i < s.length; i++) {
            if (set.contains(s[i])) continue;
            set.add(s[i]);
            swap(s, i, idx);
            //System.out.println("idx=" + idx + ", i=" + i + ", s=" + Arrays.toString(s));
            // 接着固定第 idx + 1 位字符
            backtracking(res, s, idx + 1);
            swap(s, idx, i);
        }
    }

    private void swap(char[] s, int i, int j) {
        char tmp = s[i];
        s[i] = s[j];
        s[j] = tmp;
    }
}
```

## 面试题29：[QuickSelect] 数组中出现次数超过一半的数字（[LeetCode] 169. Majority Element）
[https://www.yuque.com/littleneko/yxpqg3/ewnn09](https://www.yuque.com/littleneko/yxpqg3/ewnn09)

## 面试题30：[QuickSelect][Heap] 最小的K个数
[https://www.yuque.com/littleneko/yxpqg3/uosnun](https://www.yuque.com/littleneko/yxpqg3/uosnun)
