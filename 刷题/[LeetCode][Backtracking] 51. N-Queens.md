# Description
The _n_-queens puzzle is the problem of placing _n_ queens on an _n_×_n_ chessboard such that no two queens attack each other.
![](https://cdn.nlark.com/yuque/0/2020/png/385742/1585060873891-dc6af71d-24da-4143-b0c0-1bda643e45d7.png#align=left&display=inline&height=276&originHeight=276&originWidth=258&size=0&status=done&style=none&width=258)
Given an integer _n_, return all distinct solutions to the _n_-queens puzzle.
Each solution contains a distinct board configuration of the _n_-queens' placement, where `'Q'` and `'.'` both indicate a queen and an empty space respectively.
**
**Example:**
```
Input: 4
Output: [
 [".Q..",  // Solution 1
  "...Q",
  "Q...",
  "..Q."],
 ["..Q.",  // Solution 2
  "Q...",
  "...Q",
  ".Q.."]
]
Explanation: There exist two distinct solutions to the 4-queens puzzle as shown above.
```

# Solution
**解题思路**

- 回溯
- 按行遍历，然后按列遍历，找出每行应该放置的列

```java
public class Solution {
    public List<List<String>> solveNQueens(int n) {
        List<List<String>> ret = new ArrayList<>();
        int[] status = new int[n];
        backtracking(ret, status, 0, n);
        return ret;
    }
    
    /**
     * 
     * @param ret
     * @param status 记录当前遍历的每个皇后放置位置
     * @param curRow
     * @param n
     */
    private void backtracking(List<List<String>> ret, int[] status, int curRow, int n) {
        if (curRow == n) {
            List<String> tmp = new ArrayList<>(n);
            for (int i = 0; i < n; i++) {
                StringBuilder sb = new StringBuilder();
                for (int j = 0; j < n; j++) {
                    if (status[i] == j) {
                        sb.append("Q");
                    } else {
                        sb.append(".");
                    }
                }
                tmp.add(sb.toString());
            }
            ret.add(tmp);
            return;
        }

        // 遍历每一列
        for (int j = 0; j < n; j++) {
            if (check(status, curRow, j)) {
                status[curRow] = j;
                backtracking(ret, status, curRow + 1, n);
                status[curRow] = -1;
            }
        }
    }

    /**
     * 判断是否同行同列和对角线关系
     * 对角线关系为 y = x + b
     * 两个点在对角线上得到 y1 - y2 = x1 - x2
     *
     * @param status
     * @param r
     * @param c
     * @return
     */
    private boolean check(int[] status, int r, int c) {
        for (int i = 0; i < r; i++) {
            if (status[i] == c || Math.abs(i - r) == Math.abs(status[i] - c)) {
                return false;
            }
        }
        return true;
    }
}
```

