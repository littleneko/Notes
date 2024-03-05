[https://leetcode.cn/problems/er-cha-sou-suo-shu-yu-shuang-xiang-lian-biao-lcof/](https://leetcode.cn/problems/er-cha-sou-suo-shu-yu-shuang-xiang-lian-biao-lcof/)
# Description
输入一棵二叉搜索树，将该二叉搜索树转换成一个排序的循环双向链表。要求不能创建任何新的节点，只能调整树中节点指针的指向。

为了让您更好地理解问题，以下面的二叉搜索树为例：
![image.png](https://cdn.nlark.com/yuque/0/2020/png/385742/1588412517734-00106ecf-6961-4f14-9110-d4fd3534756b.png#averageHue=%23fcfcfc&height=196&id=TlniK&originHeight=392&originWidth=681&originalType=binary&ratio=1&rotation=0&showTitle=false&size=18312&status=done&style=none&title=&width=340.5)
我们希望将这个二叉搜索树转化为双向循环链表。链表中的每个节点都有一个前驱和后继指针。对于双向循环链表，第一个节点的前驱是最后一个节点，最后一个节点的后继是第一个节点。

下图展示了上面的二叉搜索树转化成的链表。“head” 表示指向链表中有最小元素的节点。
![image.png](https://cdn.nlark.com/yuque/0/2020/png/385742/1588412527482-482f93d0-a161-47af-9850-b88883ac566a.png#averageHue=%23fafafa&height=188&id=SX7Ie&originHeight=375&originWidth=1149&originalType=binary&ratio=1&rotation=0&showTitle=false&size=14780&status=done&style=none&title=&width=574.5)
特别地，我们希望可以就地完成转换操作。当转化完成以后，树中节点的左指针需要指向前驱，树中节点的右指针需要指向后继。还需要返回链表中的第一个节点的指针。

注意：本题与主站 426 题相同：[https://leetcode-cn.com/problems/convert-binary-search-tree-to-sorted-doubly-linked-list/](https://leetcode-cn.com/problems/convert-binary-search-tree-to-sorted-doubly-linked-list/)

注意：此题对比原题有改动。

# Solution
**解题思路**：二叉搜索树的中序遍历序列即是一个递增的序列，因此可以使用中序遍历的方法把二叉树的 `left` 和 `right` 指针串起来
![image.png](https://cdn.nlark.com/yuque/0/2020/png/385742/1588412687773-5d5976d1-7fa3-4e49-a34e-657519c62acc.png#averageHue=%23ededed&height=219&id=Ikfru&originHeight=530&originWidth=1808&originalType=binary&ratio=1&rotation=0&showTitle=false&size=147191&status=done&style=none&title=&width=746)

![image.png](https://cdn.nlark.com/yuque/0/2020/png/385742/1588412700247-c6ddd6c3-1f12-4b52-adb6-1ec373d221f0.png#averageHue=%23e9e9e9&height=203&id=inY8T&originHeight=548&originWidth=944&originalType=binary&ratio=1&rotation=0&showTitle=false&size=105658&status=done&style=none&title=&width=350)

如上图所示，二叉树和转换后的双向链表如图所示，主要需要考虑的是怎么把前后节点连接起来。对于节点 `10` 来说，它的 `left` 指针在遍历完成后应该指向左子树的最大值节点 `8` ， `right` 指针应该指向右子树的最小值节点 `12` ，接下来就是怎么获取这个最小值和最大值节点的问题。其实节点 `10` 的左子树的最大值节点就是左子树遍历完成后的最后一个节点，因此该问题实际上可以通过递归解决。
我们知道中序遍历的顺序是 `left -> root -> right` 的顺序，对于一个3个节点的树（比如说 `10` 的左子树来说），我们只要记录遍历过程中的前一个节点 `preNode` ，就可以得到 `[4 -> 6 -> 8]` 的序列，遍历完成后 `preNode` 指向节点 `8` ，即最大值节点。

### 递归解法
```java
public class LeetCode426 {
    // 记录当前遍历的前一个节点
    Node lastNode = null;
    Node head = null;
    
    public Node treeToDoublyList(Node root) {
        if (root == null) return null;
        convertNode(root);
        head.left = lastNode;
        lastNode.right = head;

        return head;
    }

    // 中序遍历同时记录遍历的最后一个节点
    private void convertNode(Node node) {
        if (node == null) return;

        convertNode(node.left);

        if (lastNode == null) {
            head = node;
        } else {
            lastNode.right = node;
        }
        node.left = lastNode;
        // 更新中序遍历最后访问的节点
        lastNode = node;

        convertNode(node.right);
    }

    public static void main(String[] args) {
        Node n4 = new Node(4);
        Node n2 = new Node(2);
        Node n5 = new Node(5);
        Node n1 = new Node(1);
        Node n3 = new Node(3);
        n4.left = n2;
        n4.right = n5;
        n2.left = n1;
        n2.right = n3;
        Node head = new LeetCode426().treeToDoublyList(n4);

        Node workNode = head;
        System.out.print(workNode.val + " -> ");
        workNode = workNode.right;
        while (workNode != head) {
            System.out.print(workNode.val + " -> ");
            workNode = workNode.right;
        }
    }
}
```

### 非递归（迭代）
```java
public class LeetCode426 {
	// 非递归版本
    public Node treeToDoublyListIterate(Node root) {
        if (root == null) return null;

        Stack<Node> stack = new Stack<>();
        Node p = root;
        Node newHead = null, preNode = null;
        while (p != null || !stack.empty()) {
            while (p != null) {
                stack.push(p);
                p = p.left;
            }

            if (!stack.empty()) {
                Node tmp = stack.pop();
                p = tmp.right;

                if (preNode == null) {
                    newHead = tmp;
                } else {
                    preNode.right = tmp;
                }
                tmp.left = preNode;
                preNode = tmp;
            }
        }

        newHead.left = preNode;
        preNode.right = newHead;
        return newHead;
    }
}
```
