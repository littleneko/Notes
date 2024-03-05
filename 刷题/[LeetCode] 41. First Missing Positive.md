# Description
Given an unsorted integer array, find the smallest missing positive integer.
**Example 1:**
```
Input: [1,2,0]
Output: 3
```
**Example 2:**
```
Input: [3,4,-1,1]
Output: 2
```
**Example 3:**
```
Input: [7,8,9,11,12]
Output: 1
```
**Note:**
Your algorithm should run in _O_(_n_) time and uses constant extra space.

# Solution
首先，我们可以得到如下结论：缺失的最小正整数 `X` 一定满足条件： `1 <= X <= N + 1` ，最小值是 `1` 很好理解，最大的 `X` 即Input数组为 `[1, 2, 3, ... N]` 的结果。

先忽略题目中的常数空间复杂度的要求，可以用一个数组 `flag` 记录 `(0, N)` 之间哪个数字出现过，最后遍历一遍 `flag` 找到第一个缺失的数字就是答案。代码如下：
```java
public class Solution {
    /**
     * @param nums
     * @return
     */
    public int firstMissingPositive(int[] nums) {
        boolean[] flag = new boolean[nums.length];
        for (int i = 0; i < nums.length; i++) {
            if (nums[i] > 0 && nums[i] <= nums.length) {
                flag[nums[i] - 1] = true;
            }
        }

        int first = 0;
        for (int i = 0; i < nums.length; i++) {
            if (!flag[i]) {
                first = i + 1;
                break;
            }
        }
        return first == 0 ? nums.length + 1 : first;
    }
}
```
再来看题目要求常数空间复杂度，这里用了 `nums.length` 大小的数组保存位置信息，显然不符合要求，我们可以复用 `nums` 数组来记录原flag记录的信息。

遍历数组 `nums` 的每个元素，如果 `1 <= nums[i] <= nums.length` ，那么就把它放到正确的位置上，即 `nums[nums[i] - 1]` （这里要减1的原因是要把 `[1, N]` 的数字放到 `[0, N-1]` 的数组中）。如果该位置本身就是正确的或者是小于 `0` 或大于 `N+1` 的数，就直接跳过。
需要注意的是，因为要复用 `nums` ，把 `nums[i]` 放到 `nums[nums[i] - 1]` 的位置上后，原本 `nums[nums[i] - 1]` 位置上的数不要忘了处理。

| idx | 0(1) | 1(2) | 2(3) | 3(4) | 备注 |
| --- | --- | --- | --- | --- | --- |
| nums | 3 | 4 | -1 | 1 |  |
| i = 0 | -1 | 4 | 3 | 1 |  |
| i = 0 | -1 | 4 | 3 | 1 | 因为交换了0，2位置上的数字，需要对交换过来的数字处理 |
| i = 1 | -1 | 1 | 3 | 4 |  |
| i = 1 | 1 | -1 | 3 | 4 |  |
| i = 1 | 1 | -1 | 3 | 4 |  |
| i = 2 | 1 | -1 | 3 | 4 |  |
| i = 3 | 1 | -1 | 3 | 4 |  |

上图中可以看到，遍历到最后，1、3、4都放到正确的位置上去了，接下来只要遍历nums一遍就知道缺了2了。

```java
public class Solution {
    public int firstMissingPositive(int[] nums) {
        int i = 0;
        while (i < nums.length) {
            if (nums[i] > 0 && nums[i] < nums.length && nums[i] != nums[nums[i] - 1]) {
                swap(nums, i, nums[i] - 1);
            } else {
                i++;
            }
        }

        for (int j = 0; j < nums.length; j++) {
            if (nums[j] != j + 1) {
                return j + 1;
            }
        }
        return nums.length + 1;
    }

    private void swap(int[] nums, int i, int j) {
        int tmp = nums[i];
        nums[i] = nums[j];
        nums[j] = tmp;
    }
}
```
