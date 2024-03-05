# Description
Given a linked list, reverse the nodes of a linked list _k_ at a time and return its modified list.
_k_ is a positive integer and is less than or equal to the length of the linked list. If the number of nodes is not a multiple of _k_ then left-out nodes in the end should remain as it is.


**Example:**
Given this linked list: `1->2->3->4->5`
For _k_ = 2, you should return: `2->1->4->3->5`
For _k_ = 3, you should return: `3->2->1->4->5`
**Note:**

- Only constant extra memory is allowed.
- You may not alter the values in the list's nodes, only nodes itself may be changed.
# Solution
**解题思路**：拆分成revert n/k个长度为k（可能小于k）的list

```java
public class Solution {
    //Definition for singly-linked list.
    public static class ListNode {
        int val;
        ListNode next;

        ListNode(int x) {
            val = x;
        }
    }

    /**
     * 拆分成revert n/k个长度为k（可能小于k）的list
     *
     * @param head
     * @param k
     * @return
     */
    public ListNode reverseKGroup(ListNode head, int k) {
        ListNode dummy = new ListNode(-1);
        dummy.next = head;

        // lastGroupTail record the tail of the last group
        // example:
        // when we finished revert the first group of 1 -> 2 -> 3 -> 4 -> 5 -> 6
        // we got 3 -> 2 -> 1 -> null and 4 -> 5 - >6
        // and we set lastGroupTail = node(1)
        // now we start revert 4 -> 5 -> 6 and got 6 -> 5 -> 4 -> null
        // and we set node(1).next = 6, lastGroupTail = node(4)
        ListNode lastGroupTail = dummy;
        ListNode curGroupStart = head;
        ListNode workNode = head;
        while (true) {
            int count = 0;
            while (count < k && workNode != null) {
                workNode = workNode.next;
                count++;
            }
            // when this while pass, workNode point to the start of next group
            // example:
            // 1 -> 2 -> 3 -> 4 -> 5 -> 6
            // workNode = node(4)
            if (count < k) {
                lastGroupTail.next = curGroupStart;
                break;
            }
            lastGroupTail.next = revertK(curGroupStart, k);
            // after we revert a group, the tail of this group is the head of the group before revert
            // example:
            // 1 -> 2 -> 3 => 3 -> 2 -> 1 -> null
            // the tail of the group after revert is node(3), and it's the head of the group before revert
            lastGroupTail = curGroupStart;
            // set the next start of a group
            curGroupStart = workNode;
        }
        return dummy.next;
    }

    /**
     * revert the list from start
     * example:
     * original list: 1 -> 2 -> 3 -> 4 -> 5 -> 6, k = 3
     * after revert: 3 -> 2 -> 1 -> null
     * <p>
     * tips:
     * we don't set the node(1).next = node(4),
     * because we have record the node(4) in func reverseKGroup
     *
     * @param start
     * @param k
     * @return the new list head
     */
    private ListNode revertK(ListNode start, int k) {
        ListNode pre = null, cur = start;
        while (k > 0) {
            ListNode tmp = cur.next;
            cur.next = pre;
            pre = cur;
            cur = tmp;
            k--;
        }
        return pre;
    }
}
```

