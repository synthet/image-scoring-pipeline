---
description: Send a message to another agent (e.g., electron-gallery.agent) via the agent-mailbox
---

1. Send a message to the target agent. By default, this sends a test event to `electron-gallery.agent`. Modify the payload as needed for your specific use case.

   ```
   mailbox_send(
       from="image-scoring.agent",
       to="electron-gallery.agent",
       type="event",
       payload={
           "event": "manual_test",
           "message": "Hello from manual workflow trigger"
       }
   )
   ```
