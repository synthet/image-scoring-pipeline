---
name: backlog-triage
description: >-
  Use when the user asks to triage, reprioritize, or review priorities of the GitHub issue
  backlog (e.g. "triage the issues", "are the p0s right?", "what should be Ready?"). Snapshots
  every open issue with its priority label and Project-board Stage, judges priorities against
  a rubric, spot-checks whether issues are already fixed, then applies an agreed plan:
  relabel, close, move Stage, file new issues.
---

# Backlog triage (compiled harness)

Priority triage for [Project board #1](https://github.com/users/synthet/projects/1).
[backlog-housekeeping](../backlog-housekeeping/SKILL.md) fixes mechanical drift (Stage sync,
`area:*` labels, closes listed in its config). **This skill decides what matters most.**
The harness `scripts/agent_skills/backlog_triage.py` gathers the facts and carries out the
plan; the priority calls are yours.

## Workflow

1. **Snapshot.** Read `findings` first, then the issues.
   ```bash
   python scripts/agent_skills/backlog_triage.py snapshot > snap.json      # --repo gallery, --stale-days N
   ```
   `findings` lists:
   - `obsolete_open`, `missing_priority`, `multiple_priorities`
   - `not_on_board`, `no_stage`
   - `stale_claims`: Claimed or In Progress with no activity for more than 21 days
   - `urgent_not_ready`: p0/p1 issues waiting in Backlog while Ready holds lower priorities
   - counts per priority and per priority within Ready

2. **Verify before judging.** For every p0/p1, and every issue you plan to close, read the
   body (`gh issue view N`). Then **check the claim against the code, CI or data**:
   - Is the function still missing?
   - Is the workflow still red (`gh run list --workflow X`)?
   - Is the column still present? Use a read-only `information_schema` query, never a write.

   Issues go stale. On 2026-09-23, one open issue was already fixed in a release, and one
   p0 was a cleanup whose blocker had long gone.

3. **Propose, don't apply.** Show the user tables for close, raise, lower, and board moves,
   each row with a one-line reason tied to evidence. Say how many edits it adds up to, then
   ask. Relabeling and closing are visible to everyone.

4. **Write the agreed plan** as a JSON list of ops. The format is in the script's
   docstring; the ops are `priority`, `close`, `stage`, `comment` and `file`. Then dry-run
   it, then execute:
   ```bash
   python scripts/agent_skills/backlog_triage.py apply --plan plan.json            # dry run
   python scripts/agent_skills/backlog_triage.py apply --plan plan.json --execute
   ```
   Every op is validated before any runs. A `priority` op swaps out the old `priority:*`
   label, and `close` moves the card to Done. Give changes that aren't obvious a
   `comment`, so the issue records why.

5. **Re-run `snapshot --findings-only`** and report the before and after.

## Priority rubric

| Level | Use for |
|---|---|
| **p0** | Broken now, with ongoing cost: CI red on master, data loss or corruption, production pipeline blocked, a security hole with a live exposure. Keep this list very short, about one to three. |
| **p1** | Wrong output or unsafe behaviour that isn't yet spreading: correctness bugs in scoring, clustering or phase status; security weaknesses; test infrastructure that makes results untrustworthy; the next step of the active epic. |
| **p2** | Planned features and refactors in a live epic; bugs with a workaround; data-quality findings with no output impact. |
| **p3** | Nice-to-have work, polish, manual QA of secondary surfaces (the Gradio `/app` page), speculative research, stale branch triage. |

Tie-breakers:
- Cheap fixes to broken documented paths go up.
- Epics take the priority of their most urgent open child.
- Anything labelled `status:obsolete` is closed as *not planned* unless there is a reason
  to keep it.

**Ready** should hold the few issues someone should pick next, ordered p0 then p1, plus the
next slice of the active epic. It should not hold a whole epic's subtasks or polish work.
Move those back to Backlog.

## Rules

- Never close an issue because it *looks* done. Cite the fixing commit, release or
  migration. If only part of it is done, relabel it and comment what remains.
- Don't clear another agent's claim without saying so. Moving a stale claim back to
  Backlog leaves its assignees in place; mention them to the user.
- New work found during triage gets a new issue (a `file` op), never an entry in `TODO.md`.
- Only read-only queries against production data.

## Related

- [backlog-queue](../backlog-queue/SKILL.md): claim and Stage contract.
- [backlog-housekeeping](../backlog-housekeeping/SKILL.md): mechanical reconciliation.
- `scripts/agent_skills/backlog_stage.py`: Stage IDs and updates (reused here).
