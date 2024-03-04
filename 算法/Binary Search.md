二分查找看似简单，实际上有很多细节需要注意

- while (l < r) 还是 while (l <= r)
- l = mid + 1 还是 l = mid
- r = mid - 1 还是 r = mid

二分法实际上分为下面三种：

1. 查找特定存在的数字：最简单的二分
2. 查找某一个元素在有序数组中的插入位置，即查找的元素可能存在也可能不存在
   1. 查找的元素存在
      1. 插到第一个前面：查找第一个等于target的元素位置
      2. 插到最后一个后面：查找最后一个等于target的元素的位置
   2. 查找的元素不存在：查找最后一个小于target的位置，或这是第一个大于target的位置


典型题目：
[**34. 在排序数组中查找元素的第一个和最后一个位置**](https://leetcode-cn.com/problems/find-first-and-last-position-of-element-in-sorted-array/)** ：查找第一个和最后一个元素位置**
[**300. 最长上升子序列**](https://leetcode-cn.com/problems/longest-increasing-subsequence/)** ：查找插入点，最后一个小于target的位置**
[**378. 有序矩阵中第K小的元素**](https://leetcode-cn.com/problems/kth-smallest-element-in-a-sorted-matrix/)** **
[剑指 Offer 11. 旋转数组的最小数字](https://leetcode-cn.com/problems/xuan-zhuan-shu-zu-de-zui-xiao-shu-zi-lcof/)




