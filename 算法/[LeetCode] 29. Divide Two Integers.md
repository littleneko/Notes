# Description
Given two integers `dividend` and `divisor`, divide two integers without using multiplication, division and mod operator.
Return the quotient after dividing `dividend` by `divisor`.
The integer division should truncate toward zero, which means losing its fractional part. For example, `truncate(8.345) = 8` and `truncate(-2.7335) = -2`.
**Example 1:**

```
Input: dividend = 10, divisor = 3
Output: 3
Explanation: 10/3 = truncate(3.33333..) = 3.
```
**Example 2:**

```
Input: dividend = 7, divisor = -3
Output: -2
Explanation: 7/-3 = truncate(-2.33333..) = -2.
```
**Note:**

- Both dividend and divisor will be 32-bit signed integers.
- The divisor will never be 0.
- Assume we are dealing with an environment which could only store integers within the 32-bit signed integer range: [−2,  2 − 1]. For the purpose of this problem, assume that your function **returns 2 − 1 when the division result overflows**.
# Solution
解题思路(先不考虑符号，符号最后考虑)：

1. 最简单的方法自然是累加divisor，直到和大于dividend，记录累加的次数
2. 但是累加的方法太慢了，有没有更快速的方法呢？那就是每次x2，即等价与累加次数为1, 2, 4, 8, 16, ...类似于2分搜索
   - 记录累加第N次时和sum1小于dividend，累加第M次时和sum2大于dividend。
   - 那么怎么找到介于N和M之间那个准确结果D呢？实际上 D = N + (dividend - sum1)/divisor
   - 对于(dividend - sum1)/divisor 用同样的方法计算
   - 直到(dividend - sum1) < divisor

Example:
Input: 20 / 3

第一轮：

| multiple | sum | dividend |
| --- | --- | --- |
| 1 | 3 | <20 |
| 2 | 3+3=6 | <20 |
| 4 | 6+6=12 | <20 |
| 8 | 12+12=24 | >20 |

经过第一轮后，知道商的精确值一定是>4且<8

第二轮：

| multiple | sum | dividend |
| --- | --- | --- |
| 1 | 3 | <20-12=8 |
| 2 | 3+3=6 | <8 |
| 3 | 6+6=12 | >8 |

经过第二轮之后知道商的精确值一定>4+2=6且<4+3=7

第三轮：

| multiple | sum | dividend |
| --- | --- | --- |
| 1 | 3 | >8-6=2 |

经过第3轮之后，知道商的精确值一定是6.x，所以说最终的结果是6

```java
public class Solution {
    /**
     * @param dividend
     * @param divisor
     * @return
     */
    public int divide(int dividend, int divisor) {
        //Use long to avoid integer overflow cases.
        int sign = 1;
        if ((dividend > 0 && divisor < 0) || (dividend < 0 && divisor > 0))
            sign = -1;
        long ldividend = Math.abs((long) dividend);
        long ldivisor = Math.abs((long) divisor);

        //Take care the edge cases.
        if (ldivisor == 0) return Integer.MAX_VALUE;
        if ((ldividend == 0) || (ldividend < ldivisor)) return 0;

        long lans = ldivide(ldividend, ldivisor);

        int ans;
        if (lans > Integer.MAX_VALUE) { //Handle overflow.
            ans = (sign == 1) ? Integer.MAX_VALUE : Integer.MIN_VALUE;
        } else {
            ans = (int) (sign * lans);
        }
        return ans;
    }

    private long ldivide(long dividend, long divisor) {
        if (dividend < divisor) return 0;

        // Find the largest multiple that (divisor * multiple <= dividend)
        // we move the multiple like 1, 2, 4, 8, 16, ...
        // like a binary search
        int multiple = 1;
        long sum = divisor;
        while (sum << 1 < dividend) {
            sum = sum << 1;
            multiple = multiple << 1;
        }

        return multiple + ldivide(dividend - sum, divisor);
    }

    /**
     * 非递归
     *
     * @param dividend
     * @param divisor
     * @return
     */
    private long ldivide2(long dividend, long divisor) {
        // Find the largest multiple that (divisor * multiple <= dividend)
        // we move the multiple like 1, 2, 4, 8, 16, ...
        // like a binary search
        long multiple = 0; // must long, think 2147483648/1
        long newDividend = dividend;
        while (newDividend >= divisor) {
            int curMultiple = 1;
            long curSum = divisor;
            while (curSum << 1 < newDividend) {
                curSum = curSum << 1;
                curMultiple = curMultiple << 1;
            }

            newDividend -= curSum;
            multiple += curMultiple;
        }
        return multiple;
    }

    public static void main(String[] args) {
        int d = new LeetCode29().divide(-2147483648, -1);
        System.out.println(d);
    }
}
```

