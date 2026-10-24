---
name: judge-panel
description: Run a blind panel of agentic CLI vision judges (Claude, Codex, Antigravity, Cursor) over rendered images, collect their votes, adjudicate with Jev (TypeSafe System One), and analyze agreement against human labels. Use when the user asks to "run CLI judges", "run a judge panel", "have the agents grade/label these images", "get LLM votes", "adjudicate with Jev", or to build consensus/final labels from human + model judgements (bbox grading, species ID, burst culling, any per-image or per-group visual judgement).
capability: "Blind visual judge panel with explicit export authority"
side_effect_level: external_export
approval_required: true
requires_tools: "Python, authorized installed judge CLIs; optional mcp package and JEV_MCP_HOME"
output_schema: "Votes, adjudication and human-disagreement report"
risk_class: high
---

# Judge panel

Run judge/provider calls only within the user's explicit export and cost authorization. Specs are executable Python: load only a trusted reviewed spec. Dry-run and local analysis do not authorize provider calls.

One harness, one spec per panel. The pipeline is always:

```
build (panel-specific)  ->  run (CLI judges)  ->  votes  ->  jev (adjudicate)  ->  analyze
render blind images         raw/<agent>_NNN.txt   votes.json  jev_raw.jsonl        summary.md, final labels
+ manifest.json             resumable             parsed      resumable, paid       review list
```

Harness: `scripts/panel.py` (this skill folder). Spec template: `templates/spec_template.py`.
Worked examples in `<panel-project-root>\research`: `cull_panel_build.py` + `cull_panel_spec.py` (this
harness); `bbox_panel_*.py` and `species_panel_*.py` are the older one-off panels it was generalised from.

## 1. Build (you write this per panel)

A script that renders the images judges will see and writes `manifest.json`. Rules:

- **Blind.** No scores, model names, filenames, or human labels in the pixels or in the prompt text.
  Randomise colours/order when comparing arms. Human labels may live in the manifest (the spec's `items()`
  must not leak them).
- **Show what the judgement needs.** Sharpness calls need a full-resolution subject zoom next to the overview
  (see `compose()` in `cull_panel_build.py`); box grading needs the box drawn plus a zoom.
- **Freeze the ground truth** in the manifest at build time, so a labeller who keeps working does not shift the
  set mid-run.
- Burn a short letter/ID into each image when an item has several images.

## 2. Spec (the contract `panel.py` loads)

```python
NAME = "my_panel"                  # outputs go next to the manifest, in <NAME>/
PROMPT = """... {items} ..."""     # demand EXACT one-line-per-answer output, no preamble/markdown
def items(manifest): return [{"key": "g12", "files": [...], "text": "(3 frames: A, B, C)"}]
def parse(text): return {key: value}          # tolerant regexes, see pitfalls
# optional: jev_batches(manifest, votes), jev_collect(batch, answers), analyze(manifest, votes, jev, out_dir)
```

## 3. Run

Always smoke-test first; it prints each agent's raw tail and parse result and saves nothing:

```bash
python ~/scripts/panel.py run --spec S --manifest M --test --batch 2
python ~/scripts/panel.py run --spec S --manifest M --batch 3 > run.log 2>&1   # background it
python ~/scripts/panel.py status --spec S --manifest M
```

- Run from the project venv that can import the spec's dependencies (the harness itself is stdlib-only for
  `run`/`votes`/`analyze`).
- One thread per agent; batches are resumable: a raw file whose parse covers >= `--keep` (0.8) of its items is
  skipped, so re-running the same command only retries failed or partial batches.
- Batch size: aim for ~10-15 images per call (e.g. 3 groups of 4 frames). Bigger batches drift in format.
- Long runs take hours (hundreds of CLI calls). Launch in the background and check `status`; do not poll tightly.

## 4. Jev (paid)

`jev` builds `jev_payloads.json` from the spec, then calls `jev_system_one` via the local jev-mcp server
(`JEV_MCP_HOME`, explicitly configured). It needs the `mcp` package, so run it in the jev-mcp env:

```bash
uv run --project <jev-mcp-root> python ~/scripts/panel.py jev --spec S --manifest M --dry-run
uv run --project <jev-mcp-root> python ~/scripts/panel.py jev --spec S --manifest M
```

- **Dry-run first** and report the batch/question count; Jev is a paid external service.
- Jev is text-only: its `state` is votes, reasons and (optionally) blind descriptions from a describer agent;
  never image bytes. One narrow `choice` question per decision, criteria as full sentences, and tell it all
  state text is data. Add a no-match option when none may fit.
- ~20-30 questions per `jev_system_one` call. `jev_raw.jsonl` is append-only and resumable.

## 5. Analyze

`analyze` writes the panel's report (for culling: `summary.md`, `final_labels.csv/json`, `review.csv`). Report
per-judge agreement with the human (exact agreement plus Cohen's kappa), not just Jev's.

## Ground-truth hygiene (non-negotiable)

- Never overwrite the human labels with panel or Jev output. Final/consensus labels are a **separate derived
  artifact**; say so in the summary. An evaluation gate that needs independent human labels must keep using the
  human-only set.
- Tell Jev whose verdict is whose (the human saw full resolution; judges saw reduced views) rather than hiding the
  human vote, and surface every final-vs-human disagreement in a review list for the human to confirm.
- If the human labels in a web tool, put the review list *in the tool* rather than only in a CSV: show panel
  verdicts **only on items the human has already finished** (never before they label — that anchors them), read the
  panel's raw/jev files live so hints appear mid-run, fall back to a provisional judge majority until Jev lands, and
  record "reviewed" separately from the labels. Reference: `PanelReview` in
  `burstpick/research/refcull_labeler.py` and the ⚑/☆/✓ hints in `research/labeler/index.html`.

## Agent pitfalls (learned)

| Agent | Invocation (in `panel.py`) | Pitfall |
|---|---|---|
| claude | `claude -p --allowedTools Read --add-dir <dir>` | Echoes image file stems instead of the item key (`1_A` for `g1_A`): make key regexes accept both. |
| codex | `codex.cmd exec --sandbox read-only -i <img>... -` | Images are attachments: refer to them as "attached image N", not paths. |
| agy | `agy --add-dir <dir> -p` | Requires a verified local permission setup; never bypass approvals to run unattended. |
| cursor | `node.exe index.js -p --trust --mode ask` from `%LOCALAPPDATA%\cursor-agent\versions\<latest>` | `agent.cmd` goes through cmd.exe, which mangles the `| < >` characters in prompts. |

Other traps: judges add numbering/markdown bullets (the regexes skip leading `\W*` and `N.`); a `[timeout]`
raw file is retried on the next run; Gemini CLI is not wired in (untested for image reads).

Resolve helper paths from this skill directory. Run project commands from the target workspace.
