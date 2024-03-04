# Description
Given _n_ non-negative integers _a_, _a_, ..., _a_, where each represents a point at coordinate (_i_, _a_). _n_ vertical lines are drawn such that the two endpoints of line _i_ is at (_i_, _a_) and (_i_, 0). Find two lines, which together with x-axis forms a container, such that the container contains the most water.
**Note: **You may not slant the container and _n_ is at least 2.
 
![](https://cdn.nlark.com/yuque/0/2020/jpeg/385742/1585152477251-d4edaab5-0012-4424-b515-4368ab41e1d1.jpeg#align=left&display=inline&height=287&originHeight=383&originWidth=801&size=0&status=done&style=none&width=600)
The above vertical lines are represented by array [1,8,6,2,5,4,8,3,7]. In this case, the max area of water (blue section) the container can contain is 49.
 
**Example:**
```
Input: [1,8,6,2,5,4,8,3,7]
Output: 49
```


# Solution
#### Approach 2: Two Pointer Approach
**Algorithm**
The intuition behind this approach is that the area formed between the lines will always be limited by the height of the shorter line. Further, the farther the lines, the more will be the area obtained.
We take two pointers, one at the beginning and one at the end of the array constituting the length of the lines. Futher, we maintain a variable \text{maxarea}maxarea to store the maximum area obtained till now. At every step, we find out the area formed between them, update \text{maxarea}maxarea and move the pointer pointing to the shorter line towards the other end by one step.
The algorithm can be better understood by looking at the example below:
```
1 8 6 2 5 4 8 3 7
```

**How this approach works?**
Initially we consider the area constituting the exterior most lines. Now, to maximize the area, we need to consider the area between the lines of larger lengths. If we try to move the pointer at the longer line inwards, we won't gain any increase in area, since it is limited by the shorter line. But moving the shorter line's pointer could turn out to be beneficial, as per the same argument, despite the reduction in the width. This is done since a relatively longer line obtained by moving the shorter line's pointer might overcome the reduction in area caused by the width reduction.
For further clarification click [here](https://leetcode.com/problems/container-with-most-water/discuss/6099/yet-another-way-to-see-what-happens-in-the-on-algorithm) and for the proof click [here](https://leetcode.com/problems/container-with-most-water/discuss/6089/Anyone-who-has-a-O(N)-algorithm/7268).

解题思路：

1. 初始起点 `i = 0` ，终点 `j = n - 1` ，计算出此时的容积
2. 然后移动 `i` 和 `j` 得到其他情况下的体积，计算最大值。要得到尽可能大的容积，需要移动 `i` 和 `j` 中高度更短的点。因为容积是 `i` 和 `j` 中高度较短的边决定的（ `min(height[i], height[j]) * (j - i))` ），移动高度更长的边并不能增加容积，只有移动短边才有可能得到更大的容积。

```java
public class Solution {
    public int maxArea(int[] height) {
        int maxWater = 0;
        int i = 0, j = height.length - 1;
        while (i < j) {
            maxWater = Math.max(maxWater, (j - i) * Math.min(height[i], height[j]));
            if (height[i] < height[j]) i++;
            else j--;
        }

        return maxWater;
    }
}
```

**Complexity Analysis**

- Time complexity : O(n)_O_(_n_). Single pass.

- Space complexity : O(1)_O_(1). Constant space is used.

