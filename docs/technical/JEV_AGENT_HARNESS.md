---
type: Technical Reference
title: Jev agent harness
description: How Claude Code / Cursor agents in both repos use Jev (TypeSafe System One) for per-turn decisions — conditional instructions, permissions, review sensitivity, routing, subgoal dedup, shared retrieval, MCP tool rerank.
resource: docs/technical/JEV_AGENT_HARNESS.md
tags: [agents, jev, typesafe, harness, hooks, mcp]
timestamp: 2026-09-26T00:00:00Z
okf_version: 0.2
---

# Jev agent harness

How the coding agents in **image-scoring-pipeline** and **image-scoring-gallery** ask Jev (TypeSafe
System One) the per-turn questions that shape what the model sees and may do.

## Why

The design note *Jev Engineering for Coding Agents* argues that an agent loop is simple and the
leverage is in what the harness puts in front of the model each turn. Reading, searching and command
output dominate token spend, while fixed instructions cost 5–12% of every turn. Jev turns structured
state into typed answers (choice, score, noul) with probabilities, so the harness can validate the
answer and branch on it without parsing prose.

Measured before this change, every Claude Code turn paid for all mirrored rules. Claude Code ignores
Cursor's `globs`/`alwaysApply`. Backend always-on text was 44,324 chars (~11.1K tokens), gallery
31,395 (~7.8K). Run `python scripts/agent_harness/cli.py budget` for the current numbers.

## Principles

1. **Deterministic first, Jev second.** Cheap rules settle clear cases. Jev gets the residue, with
   one batched `system_one` call per event (`TypeSafeClient.judge_subjects`).
2. **Fail safe.** No key, no `typesafe-sdk`, timeout, or spent budget → deterministic behaviour. A
   hook that errors exits 0 with no output, so Claude Code's normal permission flow still applies.
3. **Jev only tightens security.** For permissions and review sensitivity it can escalate
   (→ ask, → deny) but never relax. Hooks never emit `allow`.
4. **Nothing restricted goes to Jev.** State is redacted (keys, tokens, DSNs, long hex/base64).
   Restricted files are described by path and metadata only.
5. **Versioned and auditable.** Questions are `harness.*` rubrics in
   [`modules/typesafe/rubrics.py`](../../modules/typesafe/rubrics.py). Every decision is appended to
   `.agent/scratch/jev-harness/decisions.jsonl` (gitignored) with rubric version, evidence hash,
   probabilities and mode.

## Decision points

| Decision (mode key) | Rubric | Type | Where | Default |
|---|---|---|---|---|
| Rule-pack visibility (`context`) | `harness.context.visibility` | choice hide/short/full | `UserPromptSubmit` hook | on |
| Command may run (`permission`) | `harness.permission.exec` | choice allow/ask/deny | `PreToolUse(Bash)` hook | **shadow** |
| File may go to external reviewer (`review_sensitivity`) | `harness.review.sensitivity` | choice public/standard/restricted | `PreToolUse(mcp__*__run_subagent)` hook | on |
| Subtask may leave the main model (`route`) | `harness.route.leave_frontier` | noul | `cli.py route` | on |
| Subgoal is a duplicate (`subgoal_dedup`) | `harness.subgoal.duplicate` | noul per prior subgoal | `cli.py subgoal add` | on |
| Diff chunk visibility for reviewers (`context`) | `harness.bundle.visibility` | choice hide/short/full | `cli.py bundle` | on |
| MCP action rerank | `harness.tool.pick` | choice over BM25 top-k | `is-be-mcp` `search` | off (config) |

Modes: `off` (never ask), `shadow` (ask and log, do not act), `on` (act). Set per decision in
[`.agent/jev_harness.json`](../../.agent/jev_harness.json); `JEV_HARNESS_MODE=off|shadow|on`
overrides every decision. Permission starts in `shadow`. Switch it to `on` once
`decisions.jsonl` shows Jev agreeing with the deterministic policy and the user's own approvals.

The API key comes from `TYPESAFE_API_KEY` / `JEV_TOKEN`, or `secrets.json` → `typesafe.api_key`.
Model is pinned to `jev-1.13.0` with a 4 s timeout, and `max_calls_per_session` caps paid calls.
Answers are cached repo-wide by (rubric version, evidence hash, model), so repeated questions are
free. Examples: the same script run twice, or the same review bundle.

The harness is a developer tool with its own modes. It does **not** read `typesafe.enabled`, which
gates only the pipeline and MCP-server consumers.

## Conditional instructions (visibility ladder)

Rules live in `.cursor/rules/*.mdc`, which is canonical. `scripts/sync_assistant_trees.py`
translates them for Claude Code:

| Cursor frontmatter | Claude Code | Loaded |
|---|---|---|
| `alwaysApply: true` | no `paths` | every turn (keep these few and short) |
| `globs: "a,b"` | `paths:` list | when Claude reads a matching file |
| `alwaysApply: false`, no globs | not mirrored | per request, by the `UserPromptSubmit` hook |

Every non-always rule is a **pack**: *short* is its `description`, *full* is its body. Per prompt, a
keyword prefilter (`packs.<name>.triggers` in `jev_harness.json`) gives a fallback rung. Jev picks
the rung for every pack in one call. Only packs whose rung rose this session are injected, so text
is not re-sent. After compaction, `SessionStart(compact)` re-pins the active packs so a summary
cannot drop them.

Per-area **footguns** packs (`footguns-db`, `-migrations`, `-api`, `-tests` in the backend) are
path-scoped rules distilled from [LESSONS_LEARNED.md](../LESSONS_LEARNED.md). They load when the
agent touches that area or asks about it.

Operator-only skills and commands (`backup-db`, `restore-db`, `release*`, memory promotion,
`windows-keep-awake`, …) carry `disable-model-invocation: true`. They drop out of the model's
per-turn listing and still work when typed as `/name`.

## Programmable permissions

`PreToolUse(Bash)` → [`policy.check_command`](../../scripts/agent_harness/policy.py):

- **deny**:
  - naming a restricted file (`secrets.json`, `.env*` except `.env.example`, keys, `~/.ssh`, plus
    per-repo `restricted_globs`) unless the verb is metadata-only (`ls`, `git rm --cached`, …)
  - `git config` writes and `extensions.worktreeConfig`
  - force-push to master/main
- **ask**:
  - other force-pushes, `git reset --hard`, `git clean -f`
  - `rm -r` outside scratch dirs
  - `alembic downgrade`, `docker compose down -v`
  - `DROP`/`TRUNCATE`, or `DELETE` without `WHERE` via psql
- **script inspection**: before `python|bash|pwsh|node <repo script>` runs, the file is read. It
  is flagged for secret reads, network egress to non-local hosts, destructive SQL, and recursive
  deletes. Any finding → ask. The redacted excerpt then goes to `harness.permission.exec`.

`settings.json` holds a curated allowlist (read-only git/search, the documented test and lint
commands, the harness CLI), `ask` rules for destructive commands, and `deny` rules for secrets and
`.git/config`. Personal allowlists go in `.claude/settings.local.json` (gitignored).

## Security-aware routing for external reviews

`PreToolUse(mcp__*__run_subagent)` checks the `files` and prompt fields sent to Codex/Gemini:

- Restricted files → deny.
- Secret-looking text in `task`/`extraContext` → deny.
- Unknown-class paths (e.g. `Dockerfile`, workflow YAML) → Jev judges sensitivity from the path
  and size alone.

## Routing and sub-agents

`cli.py route --task … --files …` prices one subtask three ways, using the note's per-context-rebuild
arithmetic:

- stay on the main model: `Y·out + Z·in`
- naive delegation that reloads the session: `X·in' + Y·out' + Z·in' + (Y+Z)·in`
- delegation with a purpose-built brief: `B·in' + Y·out' + Z·in' + S·in`

Jev then answers whether the brief alone is sufficient. Restricted files always stay first-party.
Prices in `jev_harness.json` are the illustrative list prices from the note; update them before
relying on absolute numbers. `/decompose` and `autonomous-run-contract` call it.

`cli.py subgoal add "<text>"` keeps a ledger of in-flight and done subgoals. Exact and lexical
repeats are caught deterministically; close candidates go to Jev in one call. Duplicates come back
as `duplicate_of` and are not launched.

## Shared retrieval for background reviewers

`cli.py bundle [--base origin/master]` writes `.agent-runs/bundle-<head>-<hash>.md` once per HEAD +
diff state. Every read-only reviewer starts from it: external Codex/Gemini panels,
`critical-commit-audit`, `subagent-review`. Each changed file gets a rung (full diff, summary with
hunk headers, or path only) chosen by Jev and trimmed to a character budget. Restricted files are
listed as excluded and never read.

## Tool routing (MCP search)

When BM25 is unsure (`low_confidence`), `search_actions` can ask `harness.tool.pick` over the top 8
candidates and move the pick to the front. The response carries a `rerank` field. This requires
`typesafe.enabled` **and** `typesafe.mcp_search_rerank` in `config.json` (both default false). See
[MCP_SEARCH_DISPATCH.md](MCP_SEARCH_DISPATCH.md).

## Gallery

The gallery's hooks call this backend copy with `--repo`, guarded so a missing sibling checkout
is skipped:
`test -f "$F" && python "$F" <event> --repo "$CLAUDE_PROJECT_DIR" || true`, where `$F` is
`$CLAUDE_PROJECT_DIR/../image-scoring-pipeline/scripts/agent_harness/hook.py`. The guard matters
because `python` on a missing file exits 2, and Claude Code treats exit 2 as **block**. The gallery
has its own `.agent/jev_harness.json` and packs.

## Files

- [`scripts/agent_harness/`](../../scripts/agent_harness/):
  - `jev_gate.py`: modes, budget, cache, redaction, log
  - `policy.py`
  - `packs.py`
  - `hook.py`
  - `route.py`
  - `subgoals.py`
  - `bundle.py`
  - `budget.py`
  - `cli.py`
- [`.agent/jev_harness.json`](../../.agent/jev_harness.json): modes, thresholds, pack triggers,
  route prices
- [`.claude/settings.json`](../../.claude/settings.json), [`.claude/HOOKS.md`](../../.claude/HOOKS.md)
- Tests: [`tests/test_agent_harness.py`](../../tests/test_agent_harness.py) (network-free, fake client)

## Follow-ups

- Jev rerank in the gallery's Node `mcp-server` search.
- A Cursor `beforeShellExecution` adapter for the permission gate.
- Flip `permission` to `on` after reviewing shadow-mode agreement in `decisions.jsonl`.
