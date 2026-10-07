# Claude Code hooks — Jev agent harness

`.claude/settings.json` (tracked) wires four hooks to one entrypoint,
[`scripts/agent_harness/hook.py`](../scripts/agent_harness/hook.py), using a
path relative to the repository working directory. The settings avoid
`$CLAUDE_PROJECT_DIR`: Cursor on Windows can supply the drive root instead of
the repository path. Full design:
[docs/technical/JEV_AGENT_HARNESS.md](../docs/technical/JEV_AGENT_HARNESS.md).

| Event | Matcher | Argument | Effect |
|-------|---------|----------|--------|
| `UserPromptSubmit` | — | `user-prompt` | Injects intent-scoped rule packs from `.cursor/rules/` at the rung Jev picks (hide / short / full); only packs that are new or upgraded this session. |
| `SessionStart` | `compact` | `session-compact` | Re-pins the packs that were active before compaction. |
| `PreToolUse` | `Bash` | `pre-bash` | Deterministic deny/ask policy + script inspection; Jev may only escalate (`permission` mode). |
| `PreToolUse` | `mcp__.*__run_subagent` | `pre-review` | Blocks restricted files / secret-looking text going to external Codex/Gemini reviewers. |

## Behaviour guarantees

- **Fail-open to Claude Code's normal flow.** Any hook error exits 0 with no output; the usual
  permission prompts still apply. The hooks never emit `allow` — granting stays with the
  `permissions.allow` list.
- **No secrets leave the machine.** State sent to Jev is redacted; restricted files are sent by path
  and metadata only, never contents.
- **Everything is logged** to `.agent/scratch/jev-harness/decisions.jsonl` (gitignored).

## Turning things off

- All Jev calls: `JEV_HARNESS_MODE=off` (deterministic policy still runs).
- One decision: set its mode to `off` in [`.agent/jev_harness.json`](../.agent/jev_harness.json).
- Everything: remove the `hooks` block from your `settings.local.json` override, or run
  Claude Code with `--settings` pointing at a file without hooks.

Personal allowlists belong in `.claude/settings.local.json` (gitignored), not in the tracked file.
