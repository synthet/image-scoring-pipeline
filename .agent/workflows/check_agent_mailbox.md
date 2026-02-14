---
description: Check for pending messages in the image-scoring agent's mailbox
---

1. Check the status of the mailbox for `image-scoring.agent` to see if there are pending messages:
   ```
   mailbox_status(agent_id="image-scoring.agent")
   ```

2. If there are pending messages, receive up to 5 of them:
   ```
   mailbox_receive(agent_id="image-scoring.agent", limit=5)
   ```

3. Review the messages. If you process a message successfully, acknowledge it (mark as done):
   ```
   mailbox_ack(agent_id="image-scoring.agent", message_id="MESSAGE_ID")
   ```

4. If you cannot process a message right now, return it to the queue so another worker can handle it:
   ```
   mailbox_nack(message_id="MESSAGE_ID")
   ```
