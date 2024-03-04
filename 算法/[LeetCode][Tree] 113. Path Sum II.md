# Description
Given a binary tree and a sum, find all root-to-leaf paths where each path's sum equals the given sum.
**Note:** A leaf is a node with no children.
**Example:**
Given the below binary tree and `sum = 22`,
```
      5
     / \
    4   8
   /   / \
  11  13  4
 /  \    / \
7    2  5   1
```
Return:


```
[
   [5,4,11,2],
   [5,8,4,5]
]
```
# Solution
DFS（Backtracking），遍历的过程中记录path。
注意：

1. 不能遍历到null节点时再去记录path，否则同一个path会被记录2遍，左右子树都需要回溯
2. 得到target的path后，需要把当前节点加进去；或者先把当前节点加到curPath，然后在得到target后再remove
```java
public class LeetCode113 {
    //Definition for a binary tree node.
    public static class TreeNode {
        int val;
        TreeNode left;
        TreeNode right;

        TreeNode() {
        }

        TreeNode(int val) {
            this.val = val;
        }

        TreeNode(int val, TreeNode left, TreeNode right) {
            this.val = val;
            this.left = left;
            this.right = right;
        }
    }

    public List<List<Integer>> pathSum(TreeNode root, int sum) {
        List<List<Integer>> path = new ArrayList<>();
        findPath(path, new ArrayList<Integer>(), root, sum);
        return path;
    }

    private void findPath(List<List<Integer>> path, List<Integer> curPath, TreeNode curNode, int target) {
        if (curNode == null) return;
        // leaf node
        if (curNode.left == null && curNode.right == null) {
            if (target == curNode.val) {
                List<Integer> tmp = new ArrayList<>(curPath);
                // add cur node to the path
                // 记住只能加到tmp，不能加到curPath，否则回溯的时候会多一个节点
                tmp.add(curNode.val);
                path.add(tmp);
            }
        }

        curPath.add(curNode.val);
        findPath(path, curPath, curNode.left, target - curNode.val);
        findPath(path, curPath, curNode.right, target - curNode.val);
        curPath.remove(curPath.size() - 1);
    }

    public static void main(String[] args) {
        TreeNode node5 = new TreeNode(5);
        TreeNode node4 = new TreeNode(4);
        TreeNode node8 = new TreeNode(8);
        TreeNode node11 = new TreeNode(11);
        TreeNode node13 = new TreeNode(13);
        TreeNode node4_2 = new TreeNode(4);
        TreeNode node7 = new TreeNode(7);
        TreeNode node2 = new TreeNode(2);
        TreeNode node5_2 = new TreeNode(5);
        TreeNode node1 = new TreeNode(1);
        node5.left = node4;
        node5.right = node8;
        node4.left = node11;
        node11.left = node7;
        node11.right = node2;
        node8.left = node13;
        node8.right = node4_2;
        node4_2.left = node5_2;
        node4_2.right = node1;
        List<List<Integer>> path = new LeetCode113().pathSum(node5, 22);
        System.out.println(path);
    }
}
```
