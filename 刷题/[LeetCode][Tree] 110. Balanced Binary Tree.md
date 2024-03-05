# Description
Given a binary tree, determine if it is height-balanced.
For this problem, a height-balanced binary tree is defined as:
> a binary tree in which the left and right subtrees of _every_ node differ in height by no more than 1.

 
**Example 1:**
Given the following tree `[3,9,20,null,null,15,7]`:
    3
   / \
  9  20
    /  \
   15   7
Return true.

**Example 2:**
Given the following tree `[1,2,2,3,3,null,null,4,4]`:
       1
      / \
     2   2
    / \
   3   3
  / \
 4   4

Return false.

# Solution
## 方法一：自顶向下的递归
```java
class Solution {
    public boolean isBalanced(TreeNode root) {
        if (root == null) {
            return true;
        } else {
            return Math.abs(height(root.left) - height(root.right)) <= 1 && isBalanced(root.left) && isBalanced(root.right);
        }
    }

    public int height(TreeNode root) {
        if (root == null) {
            return 0;
        } else {
            return Math.max(height(root.left), height(root.right)) + 1;
        }
    }
}
```

## 方法二：自底向上的递归⭐️
方法一由于是自顶向下递归，因此对于同一个节点，函数height 会被重复调用，导致时间复杂度较高。如果使用自底向上的做法，则对于每个节点，函数 height 只会被调用一次。

自底向上递归的做法类似于后序遍历，对于当前遍历到的节点，先递归地判断其左右子树是否平衡，再判断以当前节点为根的子树是否平衡。如果一棵子树是平衡的，则返回其高度（高度一定是非负整数），否则返回 −1。如果存在一棵子树不平衡，则整个二叉树一定不平衡。

```java
class Solution {
    public boolean isBalanced(TreeNode root) {
        return height(root) >= 0;
    }

    public int height(TreeNode root) {
        if (root == null) {
            return 0;
        }
        int leftHeight = height(root.left);
        int rightHeight = height(root.right);
        if (leftHeight == -1 || rightHeight == -1 || Math.abs(leftHeight - rightHeight) > 1) {
            return -1;
        } else {
            return Math.max(leftHeight, rightHeight) + 1;
        }
    }
}
```



