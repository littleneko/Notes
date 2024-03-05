# Description
Given a string **s**, find the longest palindromic substring in **s**. You may assume that the maximum length of **s** is 1000.

**Example 1:**
```
Input: "babad"
Output: "bab"
Note: "aba" is also a valid answer.
```

**Example 2:**
```
Input: "cbbd"
Output: "bb"
```

# Solution
## Approach 4: Expand Around Center


**解题思路**
依次以某一个字符或两个字符为中心点，向两边扩展，寻找最大回文子串。需要特别注意回文的字符是偶数个和奇数个的情况。
所以这里的寻找回文子串的函数  `expandAroundCenter`  有两个参数作为中心，分别处理上述两种情况。

```java
  class Solution {
	public String longestPalindrome(String s) {
        if (s == null || s.length() < 1) return "";
        int start = 0, end = 0;
        for (int i = 0; i < s.length(); i++) {
            int len1 = expandAroundCenter(s, i, i);
            int len2 = expandAroundCenter(s, i, i + 1);
            int len = Math.max(len1, len2);

            // 如果是以某个字符为中心的回文子串最长（len1），len一定是奇数（babad）
            // 如果是以两个字符为中心的回文子串最长（len2），len一定是偶数（cbbd）
            if (len > end - start + 1) {
                // 0    1   2   3   4
                // b    a   b   a   d
                // i = 2时，得到的len = 3，start = 1, end = 3
                // c    b   b   d
                // i = 1时，得到的len=2，start = 1, end = 2
                start = i - (len - 1) / 2;
                end = i + len / 2;
            }
        }
        return s.substring(start, end + 1);
    }

    /**
     * 以left和right为中心，向两边扩展去找最长回文子串
     *
     * @param s
     * @param left
     * @param right
     * @return
     */
    private int expandAroundCenter(String s, int left, int right) {
        int L = left, R = right;
        while (L >= 0 && R < s.length() && s.charAt(L) == s.charAt(R)) {
            L--;
            R++;
        }
        // 这里因为最后一次循环L--了R++，所以最后的长度需要减1
        return R - L - 1;
    }
 }
```

## Approach 3: Dynamic Programming
To improve over the brute force solution, we first observe how we can avoid unnecessary re-computation while validating palindromes. Consider the case "ababa". If we already knew that "bab" is a palindrome, it is obvious that "ababa" must be a palindrome since the two left and right end letters are the same.

We define ![](https://cdn.nlark.com/yuque/__latex/2ccc34e12c17d05e5ab4edce34608a75.svg#card=math&code=P%28i%2Cj%29&height=18&id=irzOw) as following:
![](https://cdn.nlark.com/yuque/__latex/e6728b80d5a29d3e9c556bed6ea9542a.svg#card=math&code=p%28i%2Cj%29%20%3D%0A%5Cbegin%7Bcases%7D%0Atrue%2C%20%20%26%20%5Ctext%7Bif%20the%20substring%20%24S_i%20...%20S_j%24%20is%20a%20palindrome%7D%20%5C%5C%0Afalse%2C%20%26%20%5Ctext%7Botherwise%7D%0A%5Cend%7Bcases%7D&height=39&id=h8H4r)

Therefore,
![](https://cdn.nlark.com/yuque/__latex/1fad5cf06819e69dc3f5b6ac1bc8e988.svg#card=math&code=P%28i%2Cj%29%3D%28P%28i%2B1%2Cj%E2%88%921%29&height=18&id=uFIUd)_ and _![](https://cdn.nlark.com/yuque/__latex/4dd62bc42503dd0972ee2cf8952f3576.svg#card=math&code=S_i%3D%3DS_j%29&height=19&id=M9QRB)

The base cases are:
![](https://cdn.nlark.com/yuque/__latex/048bf4ebccff2718c82eb268e14a846f.svg#card=math&code=P%28i%2Ci%29%3Dtrue&height=18&id=X9Ife)
![](https://cdn.nlark.com/yuque/__latex/e7945b755dc79187edd915ec48d46086.svg#card=math&code=P%28i%2C%20i%2B1%29%20%3D%20%28%20S_i%20%3D%3D%20S_%7Bi%2B1%7D%29&height=18&id=ff2tY)

This yields a straight forward DP solution, which we first initialize the one and two letters palindromes, and work our way up finding all three letters palindromes, and so on...

**Complexity Analysis**

- Time complexity : O(n^2). This gives us a runtime complexity of O(n^2).
- Space complexity : O(n^2). It uses O(n^2) space to store the table.



**Additional Exercise**
Could you improve the above space complexity further and how?

| i, j | 0(b) | 1(a) | 2(b) | 3(a) | 4(d) |
| --- | --- | --- | --- | --- | --- |
| 0(b) | true | f | t | f | f |
| 1(a) | --- | true | f | t | f |
| 2(b) | --- | --- | true | f | f |
| 3(a) | --- | --- | --- | true | f |
| 4(d) | --- | --- | --- | --- | true |


如图所示， `P(i, i)` 肯定为 `true` 。

1. 我们只需要判断 `j > i`  的情况。
2. **对于 **`**i**`** **`**j**`** 的遍历，一定是从  **`**i: n -> 0**`** **`**j: i -> n**`** 的顺序，因为判断 **`**P(i, j)**`** 需要知道 **`**P(i +1, j-1)**`** 的结果。如图所示 **`**P(1, 4) = P(2, 3) and S_i == S_j**`** ，要先算出 **`**P(2, 3)**`** **
3. 需要特殊处理 `P(i, i+1)` 的情况，该情况下只要满足 `S_i == S_i+1` 就为 `true` 

```java
class Solution {  
	public String longestPalindrome(String s) {
        if (s == null || s.length() < 1) return "";
        int n = s.length();
        int start = 0, end = 0;
        boolean[][] p = new boolean[n][n];
		
        // i从大到小，j从小到大遍历
        for (int i = n - 2; i >= 0; i--) {
            for (int j = i + 1; j < n; j++) {
                // 这里并没有在一开始初始化p(i,i)的值为true，
                // 而是直接在这里通过 j - i <= 2 的条件和P(i, i+1)的特殊情况一起处理了
                if (s.charAt(i) == s.charAt(j) && (j - i <= 2 || p[i + 1][j - 1])) {
                    p[i][j] = true;
                    if (j - i + 1 > end - start + 1) {
                        start = i;
                        end = j;
                    }
                }
            }
        }
        return s.substring(start, end + 1);
    }
}
```

