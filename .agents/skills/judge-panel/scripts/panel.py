"""Judge-panel harness: blind CLI vision judges -> votes -> Jev adjudication -> analysis.

A panel is described by a *spec module* (a .py file) that exposes:

    NAME: str                      panel name; outputs go to <out>/<NAME>/
    PROMPT: str                    judge prompt with an {items} placeholder
    def items(manifest) -> list    [{"key": str, "files": [path, ...], "text": str}], one prompt item each
    def parse(text) -> dict        judge raw output -> {key: value}; missing keys = not answered
    # optional
    AGENT_HINT: dict               extra line per agent (default: "view every image before answering")
    def jev_batches(manifest, votes) -> list   [{"keys": [...], "state": {...}, "questions": {...}}]
    def jev_collect(batch, answers) -> dict    one Jev response -> {key: value}
    def analyze(manifest, votes, jev, out_dir) -> None

The manifest is a JSON file the panel's own build step writes (renders, ground truth, whatever the spec needs).

Commands (all resumable; raw outputs are kept and re-used):
    python panel.py run     --spec S --manifest M [--agents claude,codex,agy,cursor] [--batch 3] [--test]
    python panel.py votes   --spec S --manifest M            -> <panel>/votes.json
    python panel.py jev     --spec S --manifest M [--dry-run] -> <panel>/jev_payloads.json, jev_raw.jsonl, jev.json
    python panel.py analyze --spec S --manifest M
    python panel.py status  --spec S --manifest M
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

AGENTS = ("claude", "codex", "agy", "cursor")
DEFAULT_HINT = "Open and view every image file listed before answering."
JEV_HOME = Path(os.environ["JEV_MCP_HOME"]) if os.environ.get("JEV_MCP_HOME") else None


# ----------------------------------------------------------------------------------------------------- spec


def load_spec(path: str):
    p = Path(path).resolve()
    sys.path.insert(0, str(p.parent))
    spec = importlib.util.spec_from_file_location(p.stem, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for need in ("NAME", "PROMPT", "items", "parse"):
        if not hasattr(mod, need):
            raise SystemExit(f"spec {p} is missing {need}")
    return mod


def panel_dir(spec, manifest: Path) -> Path:
    d = manifest.parent / spec.NAME if manifest.parent.name != spec.NAME else manifest.parent
    (d / "raw").mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------------------------------- agents


def _cursor_cmd() -> list[str]:
    # agent.cmd goes through cmd.exe, which mangles | < > in the prompt; call node directly.
    vers = Path(os.environ["LOCALAPPDATA"]) / "cursor-agent" / "versions"
    d = max(vers.iterdir())
    return [str(d / "node.exe"), str(d / "index.js")]


def run_cmd(cmd, prompt=None, timeout=1800, cwd=None) -> str:
    p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=timeout, cwd=cwd)
    return p.stdout + ("\n[stderr]\n" + p.stderr[-4000:] if p.returncode else "")


def render_items(batch, attached: bool) -> str:
    """One prompt block per item. With attached images (codex -i) files are referred to by attachment number."""
    lines, k = [], 0
    for n, it in enumerate(batch, 1):
        refs = []
        for f in it["files"]:
            k += 1
            refs.append(f"attached image {k}" if attached else f)
        lines.append(f"{n}. {it['key']}" + (f" {it['text']}" if it.get("text") else ""))
        lines += [f"     - {r}" for r in refs]
    return "\n".join(lines)


def call(spec, agent: str, batch) -> str:
    hint = getattr(spec, "AGENT_HINT", {}).get(agent, DEFAULT_HINT)
    dirs = sorted({str(Path(f).parent) for it in batch for f in it["files"]})
    if agent == "codex":
        cmd = ["codex.cmd" if os.name == "nt" else "codex", "exec", "--skip-git-repo-check", "--sandbox", "read-only"]
        for it in batch:
            for f in it["files"]:
                cmd += ["-i", f]
        return run_cmd(cmd + ["-"], spec.PROMPT.format(items=render_items(batch, True)))
    prompt = spec.PROMPT.format(items=render_items(batch, False)) + "\n" + hint
    if agent == "claude":
        cmd = ["claude", "-p", "--allowedTools", "Read"]
        for d in dirs:
            cmd += ["--add-dir", d]
        return run_cmd(cmd, prompt + "\nUse the Read tool to view each image file.")
    if agent == "agy":
        cmd = ["agy"]
        for d in dirs:
            cmd += ["--add-dir", d]
        return run_cmd(cmd + ["-p", prompt])
    if agent == "cursor":
        return run_cmd([*_cursor_cmd(), "-p", "--trust", "--mode", "ask", "--output-format", "text", prompt],
                       cwd=dirs[0])
    raise SystemExit(f"unknown agent {agent!r}; known: {', '.join(AGENTS)}")


# ------------------------------------------------------------------------------------------------------- run


def batches(items, n):
    return [items[k:k + n] for k in range(0, len(items), n)]


def raw_file(pdir: Path, agent: str, k: int) -> Path:
    return pdir / "raw" / f"{agent}_{k:03d}.txt"


def worker(spec, pdir, agent, bs, keep_ratio):
    ran = 0
    for k, b in enumerate(bs):
        f = raw_file(pdir, agent, k)
        if f.exists() and len(spec.parse(f.read_text(encoding="utf-8"))) >= keep_ratio * len(b):
            continue
        try:
            txt = call(spec, agent, b)
        except subprocess.TimeoutExpired:
            txt = "[timeout]"
        f.write_text(txt, encoding="utf-8")
        ran += 1
        print(f"{agent} batch {k + 1}/{len(bs)}: parsed {len(spec.parse(txt))}/{len(b)}", file=sys.stderr, flush=True)
    return agent, ran


def cmd_run(spec, manifest, a):
    pdir = panel_dir(spec, a.manifest)
    items = spec.items(manifest)
    agents = a.agents.split(",")
    if a.test:
        for ag in agents:
            txt = call(spec, ag, items[:a.batch])
            got = spec.parse(txt)
            print(f"===== {ag}: parsed {len(got)}/{min(a.batch, len(items))}\n{txt[-1500:]}\n-> {json.dumps(got)[:800]}")
        return
    bs = batches(items, a.batch)
    (pdir / "batches.json").write_text(json.dumps({"batch": a.batch, "keys": [[i["key"] for i in b] for b in bs]}),
                                       encoding="utf-8")
    with ThreadPoolExecutor(len(agents)) as pool:
        for ag, n in pool.map(lambda ag: worker(spec, pdir, ag, bs, a.keep), agents):
            print(f"{ag}: ran {n} batches", file=sys.stderr)


# ----------------------------------------------------------------------------------------------------- votes


def load_votes(spec, pdir) -> dict:
    votes: dict = {}
    for f in sorted((pdir / "raw").glob("*.txt")):
        agent = f.stem.rsplit("_", 1)[0]
        votes.setdefault(agent, {}).update(spec.parse(f.read_text(encoding="utf-8")))
    return votes


def cmd_votes(spec, manifest, a):
    pdir = panel_dir(spec, a.manifest)
    votes = load_votes(spec, pdir)
    (pdir / "votes.json").write_text(json.dumps(votes, indent=1), encoding="utf-8")
    n = len(spec.items(manifest))
    for ag, v in sorted(votes.items()):
        print(f"{ag}: {len(v)}/{n} items")


def cmd_status(spec, manifest, a):
    pdir = panel_dir(spec, a.manifest)
    n = len(spec.items(manifest))
    for ag, v in sorted(load_votes(spec, pdir).items()):
        print(f"{ag}: {len(v)}/{n} items answered")
    j = pdir / "jev_raw.jsonl"
    if j.exists():
        print(f"jev: {sum(1 for _ in j.open(encoding='utf-8'))} batches answered")


# ------------------------------------------------------------------------------------------------------- jev


async def _jev_calls(payloads, raw: Path):
    if JEV_HOME is None or not (JEV_HOME / "scripts/run_jev_mcp.py").is_file():
        raise SystemExit("Set JEV_MCP_HOME to a verified local jev-mcp checkout")
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    done = {json.loads(line)["batch"] for line in raw.open(encoding="utf-8")} if raw.exists() else set()
    params = StdioServerParameters(command=sys.executable, args=[str(JEV_HOME / "scripts" / "run_jev_mcp.py")],
                                   env={**os.environ, "JEV_ENV_FILE": str(JEV_HOME / ".env")}, cwd=str(JEV_HOME))
    async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
        await s.initialize()
        for n, b in enumerate(payloads):
            if n in done:
                continue
            res = await s.call_tool("jev_system_one", {"model": "jev-1.13.0", "state": b["state"], "questions": b["questions"]})
            txt = "".join(getattr(c, "text", "") for c in res.content)
            try:
                d = json.loads(txt)
                d = d.get("result", d)
                answers = d["answers"]
            except Exception:  # noqa: BLE001 - keep going; the batch is retried on the next run
                print(f"jev batch {n}: unparsable response: {txt[:300]}", file=sys.stderr)
                continue
            with raw.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"batch": n, "model": d.get("model"), "answers": answers}) + "\n")
            print(f"jev batch {n + 1}/{len(payloads)}: {len(answers)} answers ({d.get('model')})", file=sys.stderr,
                  flush=True)


def cmd_jev(spec, manifest, a):
    if not hasattr(spec, "jev_batches"):
        raise SystemExit("spec has no jev_batches()")
    pdir = panel_dir(spec, a.manifest)
    votes = load_votes(spec, pdir)
    payloads = spec.jev_batches(manifest, votes)
    (pdir / "jev_payloads.json").write_text(json.dumps(payloads, indent=1), encoding="utf-8")
    nq = sum(len(p["questions"]) for p in payloads)
    print(f"{len(payloads)} Jev batches, {nq} questions -> {pdir / 'jev_payloads.json'}")
    if a.dry_run:
        return
    raw = pdir / "jev_raw.jsonl"
    asyncio.run(_jev_calls(payloads, raw))
    out = {}
    for line in raw.open(encoding="utf-8"):
        d = json.loads(line)
        out.update(spec.jev_collect(payloads[d["batch"]], d["answers"]))
    (pdir / "jev.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"{len(out)} Jev results -> {pdir / 'jev.json'}")


# --------------------------------------------------------------------------------------------------- analyze


def cmd_analyze(spec, manifest, a):
    if not hasattr(spec, "analyze"):
        raise SystemExit("spec has no analyze()")
    pdir = panel_dir(spec, a.manifest)
    jp = pdir / "jev.json"
    spec.analyze(manifest, load_votes(spec, pdir), json.loads(jp.read_text(encoding="utf-8")) if jp.exists() else {},
                 pdir)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["run", "votes", "jev", "analyze", "status"])
    ap.add_argument("--spec", required=True)
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--agents", default="claude,codex")
    ap.add_argument("--batch", type=int, default=3, help="prompt items per judge call")
    ap.add_argument("--keep", type=float, default=0.8, help="re-run a raw batch below this parsed fraction")
    ap.add_argument("--test", action="store_true", help="one batch per agent, printed, nothing saved")
    ap.add_argument("--authorized-export", action="store_true", help="Confirm explicit user authority for the selected provider calls and cost")
    ap.add_argument("--dry-run", action="store_true", help="jev: write payloads only, no paid calls")
    a = ap.parse_args()
    if (a.command == "run" or a.command == "jev" and not a.dry_run) and not a.authorized_export:
        ap.error("provider calls require explicit task authority and --authorized-export")
    if a.batch < 1 or not 0 < a.keep <= 1 or any(ag not in AGENTS for ag in a.agents.split(",")):
        ap.error("invalid agents, batch size or keep ratio")
    spec = load_spec(a.spec)
    manifest = json.loads(a.manifest.read_text(encoding="utf-8"))
    {"run": cmd_run, "votes": cmd_votes, "jev": cmd_jev, "analyze": cmd_analyze, "status": cmd_status}[a.command](
        spec, manifest, a)


if __name__ == "__main__":
    main()
