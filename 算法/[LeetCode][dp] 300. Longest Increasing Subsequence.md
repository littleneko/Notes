# Description
Given an unsorted array of integers, find the length of longest increasing subsequence.

**Example**:
```java
Input: [10,9,2,5,3,7,101,18]
Output: 4 
Explanation: The longest increasing subsequence is [2,3,7,101], therefore the length is 4.
```
**Note**:

- There may be more than one LIS combination, it is only necessary for you to return the length.
- Your algorithm should run in O(n2) complexity.

Follow up: Could you improve it to O(n log n) time complexity?

# Solution
## dp
使用dp[i]表示前i个元素中，**包含nums[i]的**最长上升子序列，那么：
    dp[i] = max(dp[j]) + 1 (其中0≤_j_<_i_且_num_[_j_]<_num_[_i_])

```java
class Solution {
    public int lengthOfLIS(int[] nums) {
        if (nums == null || nums.length == 0) return 0;

        int n = nums.length;
        int[] dp = new int[n];
        Arrays.fill(dp, 1);

        int globalMax = 1;
        for (int i = 1; i < n; i++) {
            for (int j = 0; j < i; j++) {
                if (nums[j] < nums[i]) dp[i] = Math.max(dp[i], dp[j] + 1);
            }
            globalMax = Math.max(globalMax, dp[i]);
        }

        return globalMax;
    }
}
```

## xxx
