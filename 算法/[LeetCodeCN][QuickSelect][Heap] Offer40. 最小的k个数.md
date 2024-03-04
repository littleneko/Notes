# Description
输入整数数组 arr ，找出其中最小的 k 个数。例如，输入4、5、1、6、2、7、3、8这8个数字，则最小的4个数字是1、2、3、4。

示例 1：
```
输入：arr = [3,2,1], k = 2
输出：[1,2] 或者 [2,1]
```
示例 2：
```
输入：arr = [0,1,2,1], k = 1
输出：[0]
```
限制：
```
0 <= k <= arr.length <= 10000
0 <= arr[i] <= 10000
```
链接：[https://leetcode-cn.com/problems/zui-xiao-de-kge-shu-lcof](https://leetcode-cn.com/problems/zui-xiao-de-kge-shu-lcof)

# Solution
## 快选
思路很简单，二分+快排思想，如果选出的数正好是第k个数，就输出前K个数

需要注意的地方：

1. 输入的 `k==0` ，特殊处理，直接返回 `[]` 
2. 输入的 `k == arr.length` ，直接返回整个数组
3. 比较每次选出的p的时候应该比较 `pIdx == k - 1` ，而不是 `k` 
4. `partition` 的时候，循环的次数是 `for i from left to right-1` （假设 `right` 变量包含在了传入的数组的右端点，即需要partition的数组范围是 `[left, right]` 的闭区间）
```java
public class LeetCodeCN40 {
    public int[] getLeastNumbers(int[] arr, int k) {
        if (arr == null || k > arr.length) return arr;
        if (k <= 0) return new int[0];

        int start = 0, end = arr.length - 1;
        int pIdx = partition(arr, start, end);
        // 注意这里是比较 k - 1
        while (pIdx != k - 1) {
            if (pIdx > k - 1) {
                end = pIdx - 1;
            } else {
                start = pIdx + 1;
            }
            pIdx = partition(arr, start, end);
        }

        int[] ret = new int[k];
        for (int i = 0; i < k; i++) {
            ret[i] = arr[i];
        }
        return ret;
    }

    /**
     * 注意partition的区间是个闭区间，即 [left, right]
     * @param arr
     * @param l
     * @param r
     * @return
     */
    private int partition(int[] arr, int l, int r) {
        int p = arr[r];
        int smallIdx = l;
        // 注意这里只遍历到 r - 1，r本身不遍历
        for (int i = l; i < r; i++) {
            if (arr[i] <= p) {
                swap(arr, smallIdx, i);
                smallIdx++;
            }
        }
        swap(arr, smallIdx, r);
        return smallIdx;
    }

    private void swap(int[] arr, int i, int j) {
        int tmp = arr[i];
        arr[i] = arr[j];
        arr[j] = tmp;
    }
    
    public static void main(String[] args) {
        // [3, 2, 1], 2
        // [0, 0, 2, 3, 2, 1, 1, 2, 0, 4], 10
        // [0,0,0,2,0,5], 0
        int[] ret = new LeetCodeCN40().getLeastNumbers(new int[]{0, 0, 0, 2, 0, 5}, 0);
        System.out.println(Arrays.toString(ret));
    }
}
```
## 最大堆
