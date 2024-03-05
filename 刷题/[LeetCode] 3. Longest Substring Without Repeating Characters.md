# Description
Given a string, find the length of the **longest substring** without repeating characters.
**
**Example 1:**
```
Input: "abcabcbb"
Output: 3 
Explanation: The answer is "abc", with the length of 3.
```



**Example 2:**
```
Input: "bbbbb"
Output: 1
Explanation: The answer is "b", with the length of 1.
```



**Example 3:**

```
Input: "pwwkew"
Output: 3
Explanation: The answer is "wke", with the length of 3. 
             Note that the answer must be a substring, "pwke" is a subsequence and not a substring.
```

# Solution
## Approach 3: Sliding Window Optimized
The above solution requires at most 2n steps. In fact, it could be optimized to require only n steps. Instead of using a set to tell if a character exists or not, we could define a mapping of the characters to its index. Then we can skip the characters immediately when we found a repeated character.
The reason is that if s[j]_s_[_j_] have a duplicate in the range [i, j)[_i_,_j_) with index j'_j_′, we don't need to increase i_i_ little by little. We can skip all the elements in the range [i, j'][_i_,_j_′] and let i_i_ to be j' + 1_j_′+1 directly.

**解题思路：**
扫描数组并记录局部最长无重复子串，然后求出全局最长子串

- [i,j] 两个指针从前往后扫（闭区间），同时记录每一个字母最新出现的位置:
   - 如果[i, j] 之间没有重复的字母（即第j个字母出现的位置x<i），计算当前扫描最长无重复子串长度为 (j - i + 1)，并更新全局最长子串的值
   - 如果[i, j] 之间有重复字母（即第j个字母出现的位置x>i），更新i为(x+1)，计算当前扫描最长无重复子串为 (j - i + 1)，并更新全局最长子串

```java
class Solution { 
	public int lengthOfLongestSubstring(String s) {
        int n = s.length();
        // 记录每个字母最新出现的位置
        Map<Character, Integer> map = new HashMap<>();

        int maxLen = 0;
        for (int i = 0, j = 0; j < n; j++) {
            if(map.containsKey(s.charAt(j))) {
                // 当前字母在[i, j]之间出现过
                // i直接跳转到该字母出现的位置后面
                i = Math.max(map.get(s.charAt(j)) + 1, i);
            }
            maxLen = Math.max(maxLen, j - i + 1);
            // 更新每个字母最新出现的位置
            map.put(s.charAt(j), j);
        }
        return maxLen;
    }
 }
```

