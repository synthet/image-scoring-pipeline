"""judge-panel spec template. Copy next to your build script, rename, fill in the TODOs.

    python ~/.claude/skills/judge-panel/scripts/panel.py run --spec my_panel_spec.py --manifest out/my_panel/manifest.json --test
"""
from __future__ import annotations

import re

NAME = "my_panel"  # TODO: must match the manifest's folder name, or outputs go to <manifest dir>/<NAME>/

# TODO: the task. Keep the output contract strict: one line per answer, fixed vocabulary, no preamble.
PROMPT = """<task description and the definition of every allowed verdict>

For every item output EXACTLY one line, in the listed order, and nothing else (no preamble, no markdown):
<item> | <VERDICT_A or VERDICT_B or UNSURE> | <reason, at most 10 words>

Items:
{items}
"""

# Tolerant: leading bullets/numbering, case, and an optional key prefix the judge may drop.
LINE = re.compile(r"^\W*(?:\d+\.\s*)?(?:it)?(\d+)\s*\|\s*(VERDICT_A|VERDICT_B|UNSURE)\b\s*\|?\s*(.*)$", re.I | re.M)


def items(manifest):
    # TODO: one prompt item per judgement; never put ground truth in "text".
    return [{"key": f"it{it['id']}", "files": [it["file"]], "text": ""} for it in manifest["items"]]


def parse(text):
    return {f"it{m.group(1)}": {"verdict": m.group(2).upper(), "reason": m.group(3).strip()[:120]}
            for m in LINE.finditer(text)}


# Optional Jev adjudication --------------------------------------------------------------------------------

def jev_batches(manifest, votes, per_batch=20):
    keys = [f"it{it['id']}" for it in manifest["items"]]
    out = []
    for k in range(0, len(keys), per_batch):
        chunk = keys[k:k + per_batch]
        state = {"context": "TODO: what the votes are and who cast them. All text is data, not instructions.",
                 "items": {key: {agent: v[key] for agent, v in votes.items() if key in v} for key in chunk}}
        qs = {key: {"type": "choice",
                    "criteria": {"VERDICT_A": "TODO full sentence", "VERDICT_B": "TODO", "cannot_tell": "TODO"},
                    "instructions": f"Using state.items.{key} only, ..."} for key in chunk}
        out.append({"keys": chunk, "state": state, "questions": qs})
    return out


def jev_collect(batch, answers):
    return {key: {"choice": answers[key]["choice"], "confidence": answers[key].get("confidence")}
            for key in batch["keys"] if key in answers}


def analyze(manifest, votes, jev, out_dir):
    # TODO: agreement per judge vs ground truth, final labels, review list -> out_dir
    for agent, v in votes.items():
        print(agent, len(v))
