# Description 1
Given a **set** of candidate numbers (`candidates`) **(****without duplicates****)** and a target number (`target`), find all unique combinations in `candidates` where the candidate numbers sums to `target`.
The **same** repeated number may be chosen from `candidates` unlimited number of times.
**Note:**

- All numbers (including `target`) will be positive integers.
- The solution set must not contain duplicate combinations.

**Example 1:**
```
Input: candidates = [2,3,6,7], target = 7,
A solution set is:
[
  [7],
  [2,2,3]
]
```

**Example 2:**
```
Input: candidates = [2,3,5], target = 8,
A solution set is:
[
  [2,2,2,2],
  [2,3,3],
  [3,5]
]
```

# Solution 1
关键点：**candidates无重复元素，都是正数，每个元素可以使用无限多次，结果集不能有重复**

```java
public class Solution {
    public List<List<Integer>> combinationSum(int[] candidates, int target) {
        Arrays.sort(candidates);
        List<List<Integer>> ret = new ArrayList<>();
        backtracking(ret, new ArrayList<Integer>(), candidates, target, 0);
        return ret;
    }

    private void backtracking(List<List<Integer>> ret, List<Integer> cur, int[] candidates, int target, int start) {
        // 已经剪枝了，不会出现这种情况
        // if (target < 0) return;
        if (target == 0) {
            ret.add(new ArrayList<>(cur));
            return;
        }

        // 注意i从start开始循环，对于[2, 3, 6, 7] target=7 这个case来说
        // 即第1个位置选了 3 之后，第2个位置从 3 开始选
        // 不能从 2 开始，不然会出现 [2, 3, 3] 和 [3, 2, 3] 两个重复结果
        for (int i = start; i < candidates.length; i++) {
            // 如果 target 减去一个数得到负数，那么减去一个更大的树依然是负数，
            // 同样搜索不到结果。
            // 基于这个想法，我们可以对输入数组进行排序，添加相关逻辑达到进一步剪枝的目的
            if (target - candidates[i] < 0) break;
            
            cur.add(candidates[i]);
            // 因为可以选择重复数字，因此下一个位置仍然从 i 开始，对比40题是从 i+1 开始
            backtracking(ret, cur, candidates, target - candidates[i], i);
            cur.remove(cur.size() - 1);
        }
    }
}
```

# Description 2
Given a collection of candidate numbers (`candidates`) and a target number (`target`), find all unique combinations in `candidates` where the candidate numbers sums to `target`.
Each number in `candidates` may only be used **once** in the combination.
**Note:**

- All numbers (including `target`) will be positive integers.
- The solution set must not contain duplicate combinations.

**Example 1:**
```
Input: candidates = [10,1,2,7,6,1,5], target = 8,
A solution set is:
[
  [1, 7],
  [1, 2, 5],
  [2, 6],
  [1, 1, 6]
]
```

**Example 2:**
```
Input: candidates = [2,5,2,1,2], target = 5,
A solution set is:
[
  [1,2,2],
  [5]
]
```

# Solution 2
该题与上题的区别有两点：

1. 39题中 `candidates` 数组没有重复数字，40题中 `candidates` **可以有重复数字**
2. 39题中每个数字可以使用多次，40题中**每个数字只能使用1次**

两个题目都有的条件是**结果集不能有重复**的。

针对第2个区别，在每次回溯的时候不在是把当前节点加入到结果集中，而是把下一个加入进去。体现在代码上的区别就是：

1. `backtracking(ret, cur, candidates, target - candidates[i], i);` 
2. `backtracking(ret, cur, candidates, target - candidates[i], i + 1);` 

针对第1个区别，带来的结果可能是结果集会重复，比如对于输入 `[10,1,2,7,6,1,5]` ，排序后是 `[1,1,2,5,6,7,10]` ，从第1个 `1` 开始遍历能得到 `[1,1,6]` `[1,2,5]` `[1,7]` 这三个结果集，从第2个 `1` 开始遍历会得到 `[1,2,5]` `[1,7]` 这两个结果集，有重复的结果集，解决办法是在**同一个位置选择遍历起点时**跳过重复数字（不同位置选择的时候不需要跳过）。

![image.png](https://cdn.nlark.com/yuque/0/2020/png/385742/1598978420946-b905bf31-011a-4c04-b08a-8fd73244b787.png#align=left&display=inline&height=231&originHeight=462&originWidth=804&size=31514&status=done&style=none&width=402)

```java
public class Solution {
    public List<List<Integer>> combinationSum2(int[] candidates, int target) {
        Arrays.sort(candidates);
        List<List<Integer>> ret = new ArrayList<>();
        backtracking(ret, new ArrayList<Integer>(), candidates, target, 0);
        return ret;
    }

    private void backtracking(List<List<Integer>> ret, List<Integer> cur, int[] candidates, int target, int start) {
        if (target < 0) return;
        if (target == 0) {
            ret.add(new ArrayList<>(cur));
            return;
        }

        for (int i = start; i < candidates.length && target >= candidates[i]; i++) {
            // 跳过值相同的起点
            // 注意这里 i > start 而不是 i > 0 的原因是为了只在同一个位置选择的时候跳过相同元素
            // 如果该位置的元素与上一位位置相同，是不能跳过的
            if (i > start && candidates[i] == candidates[i - 1]) {
                continue;
            }
            cur.add(candidates[i]);
            backtracking(ret, cur, candidates, target - candidates[i], i + 1);
            cur.remove(cur.size() - 1);
        }
    }
}
```

