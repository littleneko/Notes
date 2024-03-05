# Description
实现函数double Power(double base, int exponent)，求base的exponent次方。不得使用库函数，同时不需要考虑大数问题。

**说明:**

- -100.0 < _x_ < 100.0
- _n_ 是 32 位有符号整数，其数值范围是 [−231, 231 − 1] 。

来源：力扣（LeetCode）
链接：[https://leetcode-cn.com/problems/shu-zhi-de-zheng-shu-ci-fang-lcof](https://leetcode-cn.com/problems/shu-zhi-de-zheng-shu-ci-fang-lcof)
著作权归领扣网络所有。商业转载请联系官方授权，非商业转载请注明出处。

# Solution
由题目知道，n可能是正数也可能是负数，当n是负数的时候，实际上是计算(1/base)^(-exponent)的值，因此我们只需要考虑如何计算x^n(n>0)。

## 方法一：直接累乘
略
## 方法二：递归
```java
class Solution {
	private double pow(double x, long n) {
        if (n == 1) return x;

        double p = pow(x, n/2);
        return p * p * (n%2 == 1?x:1);
    }
}
```

## 方法三：二分
pow(x, n) = pow(x^2, n/2) * (x%2 == 1?x:1)

以pow(x, 14)为例：

1. pow(x, 14)
2. pow(x^2, 14/2) = pow(x^2, 7)
3. pow((x^2)^2, 7/2) * (x^2) = pow(x^4, 3) * x^2 (因为7是奇数，要多乘一个"x"(即x^2))
4. pow(((x^2)^2)^2, 3/2) * ((x^2)^2) * (x^2) = pow(x^8, 1) * x^4 * x^2
5. x^8 * x^4 * x^2
```java
class Solution { 
	private double pow2(double x, long n) {
        if (n == 1) return x;
        
        return pow2(x*x, n>>1) * ((n & 0x01) == 1?x:1);
    }
}
```
写成迭代
```java
class Solution {
	private double pow3(double x, long n) {
        double res = 1.0;
        double p = x;
        while (n > 0) {
            if ((n & 0x01) == 1) {
                res *= p;
                n--;
            } else {
                p *= p;
                n >>= 1;
            }
        }
        return res;
    }
}
```
