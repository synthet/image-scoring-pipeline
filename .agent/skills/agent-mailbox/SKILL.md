---
name: agent-mailbox
description: Inter-project agent messaging — notify electron-image-scoring about DB and WebUI changes via the agent-mailbox MCP server.
---

# Agent Mailbox

The `agent-mailbox` MCP server provides asynchronous message-passing between AI agents across different projects. In this project, it is used to **notify the `electron-image-scoring` Electron app** when changes are made to the shared Firebird database or the Gradio WebUI that may affect the gallery viewer.

## Agent IDs

| Agent | Project | Purpose |
|-------|---------|---------|
| `image-scoring.agent` | This project | Sends change notifications |
| `electron-gallery.agent` | electron-image-scoring | Receives DB/schema/UI change notifications |

## MCP Tools

| Tool | Description |
|------|-------------|
| `mailbox_send` | Send a message to another agent's inbox |
| `mailbox_receive` | Receive and lease pending messages (non-blocking) |
| `mailbox_wait` | Long-poll until a message arrives or timeout |
| `mailbox_ack` | Acknowledge a message (mark done / remove from queue) |
| `mailbox_nack` | Re-queue a message (release lease for another worker) |
| `mailbox_status` | Get queue stats, optionally filtered by agent |

## Message Types

| Type | When to Use |
|------|-------------|
| `task` | Request the other agent to do something |
| `result` | Respond to a task with results |
| `event` | Notify about something that happened (fire-and-forget) |

## When to Notify electron-image-scoring

Send a message to `electron-gallery.agent` after any of these changes:

### Database Schema Changes
- New columns added to `images` table
- New tables created
- Column type or name changes

```
mailbox_send(
  from: "image-scoring.agent",
  to: "electron-gallery.agent",
  type: "event",
  payload: {
    "event": "schema_change",
    "table": "images",
    "change": "Added column score_newmodel DOUBLE PRECISION",
    "migration": "Run _init_db_impl() to auto-migrate"
  }
)
```

### Scoring Formula Changes
- Composite score weights updated
- New model added to scoring pipeline
- Score normalization logic changed

```
mailbox_send(
  from: "image-scoring.agent",
  to: "electron-gallery.agent",
  type: "event",
  payload: {
    "event": "scoring_update",
    "change": "General score formula updated: 0.50*LIQE + 0.30*AVA + 0.20*SPAQ",
    "affected_columns": ["score_general", "score_technical"],
    "action_required": "Update sort/filter options if referencing old formula"
  }
)
```

### WebUI API Changes
- New API endpoints added
- Endpoint signatures changed
- New features that the Electron gallery should mirror

```
mailbox_send(
  from: "image-scoring.agent",
  to: "electron-gallery.agent",
  type: "event",
  payload: {
    "event": "api_change",
    "change": "Added /api/selection endpoint for pick/reject workflow",
    "details": "See modules/api.py for implementation"
  }
)
```

### Bulk Data Changes
- Score recalculation across all images
- Database migration scripts run
- Label/rating bulk updates

```
mailbox_send(
  from: "image-scoring.agent",
  to: "electron-gallery.agent",
  type: "event",
  payload: {
    "event": "data_update",
    "change": "Recalculated all general scores with new formula",
    "affected_rows": "all",
    "script": "scripts/python/recalc_scores.py"
  }
)
```

## Receiving Messages

To check for messages from other agents:

```
mailbox_receive(agent_id: "image-scoring.agent", limit: 5)
```

After processing a message, acknowledge it:

```
mailbox_ack(agent_id: "image-scoring.agent", message_id: "MSG_ID")
```

If you can't handle it now, re-queue it:

```
mailbox_nack(message_id: "MSG_ID")
```

## Checking Queue Status

```
mailbox_status(agent_id: "image-scoring.agent")
```

Returns counts by status (pending, leased, done).

## Correlation IDs

For request/response patterns, use `correlation_id` to pair a task with its result:

```
# Send a task
mailbox_send(
  from: "image-scoring.agent",
  to: "electron-gallery.agent",
  type: "task",
  correlation_id: "schema-check-2026-02-14",
  payload: { "task": "verify_schema_compatibility" }
)

# Later, receive the result with matching correlation_id
mailbox_receive(agent_id: "image-scoring.agent")
# → Message with correlation_id: "schema-check-2026-02-14", type: "result"
```
