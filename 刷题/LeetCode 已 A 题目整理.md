
| **题目** | **TAG** | **备注** |
| --- | --- | --- |
| [3. 无重复字符的最长子串](https://leetcode.cn/problems/longest-substring-without-repeating-characters/) | 滑动窗口 |  |
| [5. 最长回文子串](https://leetcode-cn.com/problems/longest-palindromic-substring/) ⭐️ | DP |  |
| [11. 盛最多水的容器](https://leetcode-cn.com/problems/container-with-most-water/) | Two Pointers |  |
| [22. 括号生成](https://leetcode-cn.com/problems/generate-parentheses/) ⭐️ | Backtracking |  |
| [23. 合并K个升序链表](https://leetcode-cn.com/problems/merge-k-sorted-lists/) ⭐️ | 堆, 分治(归并排序) | 注意归并排序的应用 |
| [25. K 个一组翻转链表](https://leetcode.cn/problems/reverse-nodes-in-k-group/) | 链表 |  |
| [**34. 在排序数组中查找元素的第一个和最后一个位置**](https://leetcode-cn.com/problems/find-first-and-last-position-of-element-in-sorted-array/) | Binary Search | 注意二分搜索的结束条件以及每次l和r的取值，为什么最后一定是在第一个和最后一个x上停下来？ |
| [37. 解数独](https://leetcode-cn.com/problems/sudoku-solver/) ⭐️ | Backtracking |  |
| [39. 组合总和](https://leetcode-cn.com/problems/combination-sum/) ⭐️ | Backtracking | 组合问题 |
| [40. 组合总和 II](https://leetcode-cn.com/problems/combination-sum-ii/) ⭐️ | Backtracking | 组合问题 |
| [42. 接雨水](https://leetcode-cn.com/problems/trapping-rain-water/) ⭐️ | Two Pointers, DP, Stack |  |
| [46. 全排列](https://leetcode-cn.com/problems/permutations/) ⭐️ | Backtracking | 排列问题 |
| [47. 全排列 II](https://leetcode-cn.com/problems/permutations-ii/) ⭐️ | Backtracking | 排列问题
注意跳过重复排列的条件最后的 `vis[i - 1]`条件 |
| [51. N 皇后](https://leetcode-cn.com/problems/n-queens/) | Backtracking |  |
| [53. 最大子序和](https://leetcode-cn.com/problems/maximum-subarray/) | DP |  |
| [60. 第k个排列](https://leetcode-cn.com/problems/permutation-sequence/) ⭐️ | Backtracking, 数学 |  |
| [77. 组合](https://leetcode-cn.com/problems/combinations/) ⭐️ | Backtracking | 组合问题 |
| [78. 子集](https://leetcode-cn.com/problems/subsets/) ⭐️ | Backtracking, 位运算 | 组合问题 |
| [79. 单词搜索](https://leetcode-cn.com/problems/word-search/) | Backtracking |  |
| [90. 子集 II](https://leetcode-cn.com/problems/subsets-ii/) | Backtracking | 组合问题 |
| [94. 二叉树的中序遍历](https://leetcode-cn.com/problems/binary-tree-inorder-traversal/) | TREE | 注意迭代的多种写法 |
| [100. 相同的树](https://leetcode-cn.com/problems/same-tree/) | TREE, DFS |  |
| [107. 二叉树的层次遍历 II](https://leetcode-cn.com/problems/binary-tree-level-order-traversal-ii/) | TREE, BFS | 几乎所有层序遍历都是使用BFS的方法 |
| [110. 平衡二叉树](https://leetcode-cn.com/problems/balanced-binary-tree/) ⭐️ | TREE, DFS | 注意使用“自底向上 ”的递归避免重复计算 |
| [124. 二叉树中的最大路径和](https://leetcode.cn/problems/binary-tree-maximum-path-sum/) ⭐️ | TREE |  |
| [144. 二叉树的前序遍历](https://leetcode-cn.com/problems/binary-tree-preorder-traversal/) | TREE |  |
| [145. 二叉树的后序遍历](https://leetcode-cn.com/problems/binary-tree-postorder-traversal/) | TREE |  |
| [146. LRU 缓存](https://leetcode.cn/problems/lru-cache/) | 双向链表 | 注意双向链表的插入和删除
leveldb 中有个生产级的 LRU 实现，可以参考 |
| [147. 链表插入排序](https://leetcode.cn/problems/insertion-sort-list/) | 链表, 插入排序 |  |
| [148. 排序链表](https://leetcode.cn/problems/sort-list/) | 链表, 归并排序 | 注意归并排序的写法
注意 “自顶向下” 和 “自底向上” 两种写法 |
| [152. 乘积最大子数组](https://leetcode-cn.com/problems/maximum-product-subarray/) ⭐️ | DP | 两个DP同时进行 |
| [198. 打家劫舍](https://leetcode-cn.com/problems/house-robber/) | DP |  |
| [200. 岛屿数量](https://leetcode-cn.com/problems/number-of-islands/) ⭐️ | DFS, BFS, 并查集 | [岛屿问题](https://leetcode-cn.com/problems/number-of-islands/solution/dao-yu-lei-wen-ti-de-tong-yong-jie-fa-dfs-bian-li-/) |
| [213. 打家劫舍 II](https://leetcode-cn.com/problems/house-robber-ii/) | DP |  |
| [216. 组合总和 III](https://leetcode-cn.com/problems/combination-sum-iii/) | DFS | 组合问题 |
| [226. 翻转二叉树](https://leetcode-cn.com/problems/invert-binary-tree/) | TREE |  |
| [239. 滑动窗口最大值](https://leetcode-cn.com/problems/sliding-window-maximum/) ⭐️ | Sliding Window | [滑动窗口问题](https://leetcode-cn.com/tag/sliding-window/) |
| [279. 完全平方数](https://leetcode-cn.com/problems/perfect-squares/) ⭐️ | DP, BFS |  |
| [300. 最长上升子序列](https://leetcode-cn.com/problems/longest-increasing-subsequence/) ⭐️ | DP, Binary Search | 注意这里的二分搜索不是要找到特定元素，而是要找到元素的插入点，即如何找到最后一个小于该元素的位置 |
| [347. 前 K 个高频元素](https://leetcode-cn.com/problems/top-k-frequent-elements/) ⭐️ | Quick Select | 第K大元素问题 |
| [**378. 有序矩阵中第K小的元素**](https://leetcode-cn.com/problems/kth-smallest-element-in-a-sorted-matrix/)** ⭐** | 归并排序, Binary Search | 
1. 注意多个数组归并的写法
2. [二分搜索中返回的值为什么一定是在矩阵中存在的](https://leetcode-cn.com/problems/kth-smallest-element-in-a-sorted-matrix/solution/guan-fang-ti-jie-er-fen-fa-de-jie-guo-wei-shi-yao-/)

ref 34 |
| [380. 常数时间插入、删除和获取随机元素](https://leetcode-cn.com/problems/insert-delete-getrandom-o1/) | 设计, Map, Array | 可以通过把元素和数组在最后一个元素交换的方法来快速在Array中删除一个元素 |
| [404. 左叶子之和](https://leetcode-cn.com/problems/sum-of-left-leaves/) | TREE |  |
| [429. N叉树的层序遍历](https://leetcode-cn.com/problems/n-ary-tree-level-order-traversal/) | TREE, BFS |  |
| [589. N叉树的前序遍历](https://leetcode-cn.com/problems/n-ary-tree-preorder-traversal/) | TREE |  |
| [590. N叉树的后序遍历](https://leetcode-cn.com/problems/n-ary-tree-postorder-traversal/) | TREE | 如何转换成"前序遍历" |
| [662. 二叉树最大宽度](https://leetcode.cn/problems/maximum-width-of-binary-tree/) | TREE, DFS, BFS | 注意两种写法，二叉树子节点的编号 |
| [841. 钥匙和房间](https://leetcode-cn.com/problems/keys-and-rooms/) | DFS, 图 | 如何把题目的描述转换成图的问题 |
| [剑指 Offer 03. 数组中重复的数字](https://leetcode-cn.com/problems/shu-zu-zhong-zhong-fu-de-shu-zi-lcof/) |  |  |
| [剑指 Offer 04. 二维数组中的查找](https://leetcode-cn.com/problems/er-wei-shu-zu-zhong-de-cha-zhao-lcof/) | 双指针 |  |
| [剑指 Offer 07. 重建二叉树](https://leetcode-cn.com/problems/zhong-jian-er-cha-shu-lcof/) | TREE, 分治 | 分治法的应用 |
| [剑指 Offer 11. 旋转数组的最小数字](https://leetcode-cn.com/problems/xuan-zhuan-shu-zu-de-zui-xiao-shu-zi-lcof/) | Binary Search |  |
| [剑指 Offer 12. 矩阵中的路径](https://leetcode-cn.com/problems/ju-zhen-zhong-de-lu-jing-lcof/) | DFS |  |
| [剑指 Offer 13. 机器人的运动范围](https://leetcode-cn.com/problems/ji-qi-ren-de-yun-dong-fan-wei-lcof/) | DFS, BFS |  |
| [剑指 Offer 16. 数值的整数次方](https://leetcode-cn.com/problems/shu-zhi-de-zheng-shu-ci-fang-lcof/) ⭐️ | 递归 | 注意递归和非递归的写法 |
| [剑指 Offer 19. 正则表达式匹配](https://leetcode-cn.com/problems/zheng-ze-biao-da-shi-pi-pei-lcof/) ⭐️ | DP, DFS |  |
| [剑指 Offer 26. 树的子结构](https://leetcode-cn.com/problems/shu-de-zi-jie-gou-lcof/) | TREE |  |
| [剑指 Offer 27. 二叉树的镜像](https://leetcode-cn.com/problems/er-cha-shu-de-jing-xiang-lcof/) ⭐️ | TREE | 递归和非递归写法 |
| [剑指 Offer 28. 对称的二叉树](https://leetcode-cn.com/problems/dui-cheng-de-er-cha-shu-lcof/solution/) ⭐️ | TREE |  |
| [剑指 Offer 29. 顺时针打印矩阵](https://leetcode-cn.com/problems/shun-shi-zhen-da-yin-ju-zhen-lcof/) | ✅ | 注意边界条件 |
| [剑指 Offer 33. 二叉搜索树的后序遍历序列](https://leetcode-cn.com/problems/er-cha-sou-suo-shu-de-hou-xu-bian-li-xu-lie-lcof/) ⭐️ | 分治 |  |
| [剑指 Offer 34. 二叉树中和为某一值的路径](https://leetcode-cn.com/problems/er-cha-shu-zhong-he-wei-mou-yi-zhi-de-lu-jing-lcof/) ⭐️ | TREE, DFS |  |
| [**剑指 Offer 36. 二叉搜索树与双向链表**](https://leetcode-cn.com/problems/er-cha-sou-suo-shu-yu-shuang-xiang-lian-biao-lcof/) ⭐️ | TREE, 分治 |  |
| [剑指 Offer 37. 序列化二叉树](https://leetcode-cn.com/problems/xu-lie-hua-er-cha-shu-lcof/) |  |  |
| [剑指 Offer 38. 字符串的排列](https://leetcode-cn.com/problems/zi-fu-chuan-de-pai-lie-lcof/) | Backtracking | 排列问题 |
| [剑指 Offer 40. 最小的k个数](https://leetcode-cn.com/problems/zui-xiao-de-kge-shu-lcof/) | Quick Select |  |
| [剑指 Offer 41. 数据流中的中位数](https://leetcode-cn.com/problems/shu-ju-liu-zhong-de-zhong-wei-shu-lcof/) | 堆 |  |
| [剑指 Offer 46. 把数字翻译成字符串](https://leetcode-cn.com/problems/ba-shu-zi-fan-yi-cheng-zi-fu-chuan-lcof/) | DP, DFS |  |
| [剑指 Offer 47. 礼物的最大价值](https://leetcode-cn.com/problems/li-wu-de-zui-da-jie-zhi-lcof/) ⭐️ | DP |  |
| [剑指 Offer 48. 最长不含重复字符的子字符串](https://leetcode-cn.com/problems/zui-chang-bu-han-zhong-fu-zi-fu-de-zi-zi-fu-chuan-lcof/) | Two Pointers, Sliding Window |  |
| [剑指 Offer 49. 丑数](https://leetcode-cn.com/problems/chou-shu-lcof/) ⭐️ | DP |  |
| [**剑指 Offer 51. 数组中的逆序对**](https://leetcode-cn.com/problems/shu-zu-zhong-de-ni-xu-dui-lcof/) ⭐️ | 分治 | 注意归并排序的写法 |
| [剑指 Offer 52. 两个链表的第一个公共节点](https://leetcode-cn.com/problems/liang-ge-lian-biao-de-di-yi-ge-gong-gong-jie-dian-lcof/) |  | 注意该题的一些变种 |
| [剑指 Offer 54. 二叉搜索树的第k大节点](https://leetcode-cn.com/problems/er-cha-sou-suo-shu-de-di-kda-jie-dian-lcof/) | TREE | 中序遍历 |
| [剑指 Offer 55 - I. 二叉树的深度](https://leetcode-cn.com/problems/er-cha-shu-de-shen-du-lcof/) | TREE, DFS, BFS | 注意DFS和BFS两种写法 |
| [剑指 Offer 57 - II. 和为s的连续正数序列](https://leetcode-cn.com/problems/he-wei-sde-lian-xu-zheng-shu-xu-lie-lcof/) | Two Pointers, Sliding Window |  |
| [剑指 Offer 59 - I. 滑动窗口的最大值](https://leetcode-cn.com/problems/hua-dong-chuang-kou-de-zui-da-zhi-lcof/) ⭐️ | Sliding Window | 滑动窗口问题 |
| [剑指 Offer 59 - II. 队列的最大值](https://leetcode-cn.com/problems/dui-lie-de-zui-da-zhi-lcof/) ⭐️ | Sliding Window | 滑动窗口问题 |
| [剑指 Offer 60. n个骰子的点数](https://leetcode-cn.com/problems/nge-tou-zi-de-dian-shu-lcof/) ⭐️ | DP, 递归 |  |
| [剑指 Offer 68 - I. 二叉搜索树的最近公共祖先](https://leetcode-cn.com/problems/er-cha-sou-suo-shu-de-zui-jin-gong-gong-zu-xian-lcof/) | TREE |  |
| [剑指 Offer 68 - II. 二叉树的最近公共祖先](https://leetcode-cn.com/problems/er-cha-shu-de-zui-jin-gong-gong-zu-xian-lcof/) | TREE | 注意递归写法 |
|  |  |  |




