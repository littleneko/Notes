# Description
Given an array of size _n_, find the majority element. The majority element is the element that appears **more than** `⌊ n/2 ⌋` times.
You may assume that the array is non-empty and the majority element always exist in the array.
**
**Example 1:**
```
Input: [3,2,3]
Output: 3
```
**Example 2:**

```
Input: [2,2,1,1,1,2,2]
Output: 2
```
# Solution
**解题思路：**
> 本题常见解法如下：
> 1. **哈希表统计法**： 遍历数组 nums ，用 HashMap 统计各数字的数量，最终超过数组长度一半的数字则为众数。此方法时间和空间复杂度均为 O(N) 。
> 2. **数组排序法**： 将数组 nums 排序，由于众数的数量超过数组长度一半，因此 数组中点的元素 一定为众数。此方法时间复杂度 O(Nlog2N)。
> 3. **摩尔投票法**： 核心理念为 “正负抵消” ；时间和空间复杂度分别为 O(N) 和 O(1) ；是本题的最佳解法。


**摩尔投票法：**
**票数和：** 由于众数出现的次数超过数组长度的一半；若记 **众数** 的票数为 +1 ，**非众数** 的票数为 −1 ，则一定有所有数字的 **票数和 >0** 。
**票数正负抵消：** 设数组 `nums`  中的众数为 x ，数组长度为 n 。若 nums 的前 a 个数字的 票数和 =0 ，则 数组后 (n−a) 个数字的 **票数和**一定仍 >0 （即后 (n−a) 个数字的 众数仍为 x ）。
![image.png](https://cdn.nlark.com/yuque/0/2020/png/385742/1588684480142-4dfdedb3-e07d-4402-81e0-21b591c4ebc2.png#align=left&display=inline&height=425&originHeight=850&originWidth=1132&size=77144&status=done&style=none&width=566)

**算法原理：**

- 为构建正负抵消，假设数组首个元素 n1
为众数，遍历统计票数，当发生正负抵消时，剩余数组的众数一定不变，这是因为（设真正的众数为 x ）：
   - 当 n1
= x ： 抵消的所有数字中，有一半是众数 x 。
   - 当 n1 != x ： 抵消的所有数字中，少于或等于一半是众数 x 。
- 利用此特性，每轮假设都可以 缩小剩余数组区间 。当遍历完成时，最后一轮假设的数字即为众数（由于众数超过一半，最后一轮的票数和必为正数）。

**算法流程:**

1. 初始化： 票数统计 votes=0 ， 众数 x；
2. 循环抵消： 遍历数组 nums 中的每个数字num ；
   1. 当 票数 votes 等于 0 ，则假设 当前数字 num 为 众数 x ；
   2. 当 num=x 时，票数 votes 自增 1 ；否则，票数 votes 自减 1 。
3. 返回值： 返回 众数 x 即可。

**复杂度分析：**

- 时间复杂度 O(N) ： N 为数组 nums 长度。
- 空间复杂度 O(1) ： votes 变量使用常数大小的额外空间。

**摩尔投票法**
```java
public class LeetCode169 {
    public int majorityElement(int[] nums) {
        int x = nums[0];
        int votes = 0;
        for (int i = 0; i < nums.length; i++) {
            if (votes == 0) x = nums[i];
            if (nums[i] == x) {
                votes++;
            } else {
                votes--;
            }
        }
        return x;
    }
}
```
**
**数组排序法的扩展**
如果数组中一个数字出现的次数超过了n/2，那么排序完成后，位于数组n/2处的数字就一定是那个出现次数超过n/2的数字，即中位数。我们可以利用快速排序算法每次partition后的数字一定是排序后该数字最终的位置这个特性，每次选择一个数字，如果partition后该数字的下标正好是n/2，那么就返回该数字；如果该数字的位置小于n/2，那么中位数一定在该数字的右边；反之就在左边。
```java
public class LeetCode169 {
    public int majorityElement(int[] nums) {
        int mid = nums.length / 2;
        int start = 0, end = nums.length - 1;
        int pidx = partition(nums, start, end);
        while (pidx != mid) {
            if (pidx < mid) {
                start = pidx + 1;
            } else {
                end = pidx - 1;
            }
            pidx = partition(nums, start, end);
        }

        return nums[pidx];
    }

    private int partition(int[] nums, int left, int right) {
        int p = nums[right];
        int smallIdx = left;
        for (int i = left; i < right; i++) {
            if (nums[i] <= p) {
                swap(nums, smallIdx, i);
                smallIdx++;
            }
        }
        swap(nums, smallIdx, right);
        return smallIdx;
    }

    private void swap(int[] nums, int i, int j) {
        int tmp = nums[i];
        nums[i] = nums[j];
        nums[j] = tmp;
    }
}
```
该方法的时间复杂度也是O(N)，但是可能会超时
