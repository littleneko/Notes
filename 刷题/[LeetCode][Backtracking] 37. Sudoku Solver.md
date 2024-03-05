# Description
Write a program to solve a Sudoku puzzle by filling the empty cells.
A sudoku solution must satisfy **all of the following rules**:

1. Each of the digits `1-9` must occur exactly once in each row.
2. Each of the digits `1-9` must occur exactly once in each column.
3. Each of the the digits `1-9` must occur exactly once in each of the 9 `3x3` sub-boxes of the grid.

Empty cells are indicated by the character `'.'`.
![](https://cdn.nlark.com/yuque/0/2020/png/385742/1586745454183-31d2769c-bf57-41a7-a08e-7f3ac02a6151.png#align=left&display=inline&height=250&originHeight=250&originWidth=250&size=0&status=done&style=none&width=250)
A sudoku puzzle...
![](https://cdn.nlark.com/yuque/0/2020/png/385742/1586745454272-37d469da-6c54-4344-8462-529339bb25bf.png#align=left&display=inline&height=250&originHeight=250&originWidth=250&size=0&status=done&style=none&width=250)
...and its solution numbers marked in red.
**Note:**

- The given board contain only digits `1-9` and the character `'.'`.
- You may assume that the given Sudoku puzzle will have a single unique solution.
- The given board size is always `9x9`.

# Solution
**解题思路：**
回溯，对每个没有填充的位置试着填充1-9，然后检查是否符合数独要求。
```java
public class Solution {
    // record the 0 - 9 is in every row, col, and subCell
    boolean[][] row = new boolean[9][9];
    boolean[][] col = new boolean[9][9];
    boolean[][] box = new boolean[9][9];
    int dotInt = '.' - '0' - 1;

    public void solveSudoku(char[][] board) {
        for (int i = 0; i < 9; i++) {
            for (int j = 0; j < 9; j++) {
                int chInt = board[i][j] - '0' - 1;
                if (chInt != dotInt) {
                    row[i][chInt] = true;
                    col[j][chInt] = true;
                    int nineIndex = (i / 3) * 3 + (j / 3) % 3;
                    box[nineIndex][chInt] = true;
                }
            }
        }
        solve(board, 0, 0);
    }

    private boolean solve(char[][] board, int i, int j) {
        if (i == board.length) return true;
        if (j == board.length) return solve(board, i + 1, 0);
        if (board[i][j] != '.') return solve(board, i, j + 1);

        // for each cell, try to set it to 0 - 9 and check is valid
        for (int k = '1'; k <= '9'; k++) {
            int chInt = k - '0' - 1;
            int nineIndex = (i / 3) * 3 + (j / 3) % 3;
            if (!row[i][chInt] && !col[j][chInt] && !box[nineIndex][chInt]) {
                row[i][chInt] = true;
                col[j][chInt] = true;
                box[nineIndex][chInt] = true;
                board[i][j] = (char) k;

                if (solve(board, i, j + 1)) {
                    return true;
                }

                row[i][chInt] = false;
                col[j][chInt] = false;
                box[nineIndex][chInt] = false;
                board[i][j] = '.';
            }
        }
        return false;
    }
}
```
