# Description
Given two non-empty binary trees **s** and **t**, check whether tree **t** has exactly the same structure and node values with a subtree of **s**. A subtree of **s** is a tree consists of a node in **s** and all of this node's descendants. The tree **s** could also be considered as a subtree of itself.
**
**Example 1:**
Given tree s:
```
		 3
    / \
   4   5
  / \
 1   2
```
Given tree t:
```
   4 
  / \
 1   2
```
Return true, because t has the same structure and node values with a subtree of s.

**
**Example 2:**
Given tree s:
```
		 3
    / \
   4   5
  / \
 1   2
    /
   0
```
Given tree t:
```
	 4
  / \
 1   2
```
Return **false**.
# Solution
```java
/**
 * Definition for a binary tree node.
 * public class TreeNode {
 *     int val;
 *     TreeNode left;
 *     TreeNode right;
 *     TreeNode(int x) { val = x; }
 * }
 */
class Solution {
    public boolean isSubtree(TreeNode s, TreeNode t) {
        if (s == null) return t == null;
        return isEqual(s, t) || isSubtree(s.left, t) || isSubtree(s.right, t);
    }

    private boolean isEqual(TreeNode s, TreeNode t) {
        if (s == null && t == null) return true;
        if (s == null || t == null) return false;
        
        if (t.val != s.val) return false;
        return isEqual(s.left, t.left) && isEqual(s.right, t.right);
    }
}
```

扩展：如果此题要求Example 2也返回 `true` 的话，可以在 `iSEqual` 中判断如果 `t==null` ，就返回 `true` 


# 变种
leetcode 572要求了t不为null
[https://leetcode-cn.com/problems/shu-de-zi-jie-gou-lcof/](https://leetcode-cn.com/problems/shu-de-zi-jie-gou-lcof/)
