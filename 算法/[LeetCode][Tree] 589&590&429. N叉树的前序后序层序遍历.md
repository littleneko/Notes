# 589. N叉树的前序遍历
参考 144. Binary Tree Preorder Traversal [Medium]
```java
class Solution {
    public List<Integer> preorder(Node root) {
        LinkedList<Node> stack = new LinkedList<>();
        LinkedList<Integer> output = new LinkedList<>();
        if (root == null) {
            return output;
        }

        stack.add(root);
        while (!stack.isEmpty()) {
            Node node = stack.pollLast();
            output.add(node.val);
            Collections.reverse(node.children);
            for (Node item : node.children) {
                stack.add(item);
            }
        }
        return output;
    }
}
```

# 590. N叉树的后序遍历
参考前序的实现以及二叉树后序遍历的实现
```java
class Solution {
    public List<Integer> postorder(Node root) {
        LinkedList<Node> stack = new LinkedList<>();
        LinkedList<Integer> ret = new LinkedList<>();

        if (root == null) return ret;

        stack.add(root);

        while (!stack.isEmpty()) {
            Node node = stack.pollLast();
            ret.addFirst(node.val);
            for (Node n: node.children) {
                stack.add(n);
            }
        }
        return ret;
    }
}
```

# 429. N叉树的层序遍历
```java

class Solution {
    public List<List<Integer>> levelOrder(Node root) {
        List<List<Integer>> ret = new LinkedList<>();
        Queue<Node> queue = new LinkedList<>();

        if (root == null) return ret;
        queue.add(root);
        while (!queue.isEmpty()) {
            int size = queue.size();
            List<Integer> level = new ArrayList<>(size);
            for (int i = 0; i < size; i++) {
                Node tmp = queue.poll();
                level.add(tmp.val);
                queue.addAll(tmp.children);
            }
            ret.add(level);
        }
        return ret;
    }
}
```
