"""Unit tests for the Jev agent harness (scripts/agent_harness).

Network-free: a fake client stands in for TypeSafe, and every test works on a
temporary repo so no real session state or secrets are touched.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import types
from pathlib import Path

import pytest

from modules.typesafe import rubrics as rubrics_mod
from modules.typesafe.normalize import Judgment
from scripts.agent_harness import budget, bundle, hook, packs, policy, route, subgoals
from scripts.agent_harness.jev_gate import JevGate, contains_secret, redact

ROOT = Path(__file__).resolve().parents[1]


# -- fakes -------------------------------------------------------------------


class FakeClient:
    """Stands in for TypeSafeClient; answers from a canned table."""

    def __init__(self, answers=None, subject_answers=None, raises=False):
        self.available = True
        self.answers = answers or {}
        self.subject_answers = subject_answers or {}
        self.raises = raises
        self.calls = []

    def judge(self, state, rubric_keys, *, check_evidence=True, criteria=None):
        self.calls.append(("judge", rubric_keys, state, criteria))
        if self.raises:
            raise RuntimeError("boom")
        return {k: self.answers[k] for k in rubric_keys if k in self.answers}

    def judge_subjects(self, state, rubric_key, subjects, *, check_evidence=True):
        self.calls.append(("subjects", rubric_key, state, subjects))
        if self.raises:
            raise RuntimeError("boom")
        return {s: self.subject_answers[s] for s in subjects if s in self.subject_answers}


def choice(key, value, p):
    return Judgment(key=key, rubric_version="v1", question_type="choice", value=value,
                    probabilities={value: p}, confidence=p, model="jev-test")


def noul(key, value):
    return Judgment(key=key, rubric_version="v1", question_type="noul", value=value, model="jev-test")


def make_gate(repo, client=None, decisions=None, **extra):
    cfg = {
        "model": "jev-test",
        "timeout_seconds": 1,
        "max_calls_per_session": 5,
        "decisions": decisions or {},
        **extra,
    }
    return JevGate(repo=repo, session_id="s1", client_factory=(lambda: client) if client else None, config=cfg)


@pytest.fixture(autouse=True)
def _no_mode_override(monkeypatch):
    monkeypatch.delenv("JEV_HARNESS_MODE", raising=False)


@pytest.fixture
def repo(tmp_path):
    rules = tmp_path / ".cursor" / "rules"
    rules.mkdir(parents=True)
    (rules / "always.mdc").write_text("---\ndescription: Always on\nalwaysApply: true\n---\n\nAlways body\n")
    (rules / "db-footguns.mdc").write_text(
        "---\ndescription: DB footguns\nglobs: \"modules/db*.py,sql/**\"\nalwaysApply: false\n---\n\n# DB\nUse [0-9] not \\d.\n"
    )
    (rules / "mcp-triage.mdc").write_text("---\ndescription: MCP triage\nalwaysApply: false\n---\n\n# MCP\nsearch then dispatch\n")
    (tmp_path / "scripts").mkdir()
    return tmp_path


# -- rubrics -----------------------------------------------------------------


def test_harness_rubrics_registered_and_versioned():
    for key in (
        "harness.context.visibility",
        "harness.bundle.visibility",
        "harness.tool.pick",
        "harness.permission.exec",
        "harness.review.sensitivity",
        "harness.route.leave_frontier",
        "harness.subgoal.duplicate",
    ):
        rubric = rubrics_mod.get_rubric(key)
        assert rubric.version == "v1"


def test_build_question_accepts_call_time_criteria(monkeypatch):
    mod = types.ModuleType("typesafe_sdk")

    class _Q:
        def __init__(self, **kw):
            self.kw = kw

    mod.Choice = mod.Noul = mod.Score = _Q
    monkeypatch.setitem(sys.modules, "typesafe_sdk", mod)
    rubric = rubrics_mod.get_rubric("harness.tool.pick")
    q = rubrics_mod.build_question(rubric, criteria={"a.b": "first", "c.d": "second"})
    assert q.kw["criteria"] == {"a.b": "first", "c.d": "second"}


# -- policy ------------------------------------------------------------------


@pytest.mark.parametrize(
    "path,expected",
    [
        ("secrets.json", policy.RESTRICTED),
        ("sub/dir/secrets.json", policy.RESTRICTED),
        (".env", policy.RESTRICTED),
        (".env.local", policy.RESTRICTED),
        (".env.example", policy.PUBLIC),
        ("config.example.json", policy.PUBLIC),
        ("docs/x.md", policy.PUBLIC),
        ("modules/db.py", policy.STANDARD),
        ("Dockerfile", policy.UNKNOWN),
    ],
)
def test_classify_path(path, expected, repo):
    assert policy.classify_path(path, repo) == expected


def test_restricted_globs_extend_per_repo(repo):
    assert policy.classify_path("config.json", repo) == policy.UNKNOWN
    assert policy.classify_path("config.json", repo, {"restricted_globs": ["config.json"]}) == policy.RESTRICTED


@pytest.mark.parametrize(
    "command,decision",
    [
        ("cat secrets.json", "deny"),
        ("git add .env", "deny"),
        ("cp secrets.json /tmp/x", "deny"),
        ("ls secrets.json", None),
        ("git rm --cached secrets.json", None),
        ('rg -n "secrets.json" modules', None),
        ('git commit -m "never read secrets.json"', None),
        ("cat .env.example", None),
        ("git config user.email a@b", "deny"),
        ("git config --get user.email", None),
        ("git config --global core.editor vim", "ask"),
        ("git config extensions.worktreeConfig true", "deny"),
        ("git push --force origin master", "deny"),
        ("git push -u origin feature", None),
        ("git push -f origin feature", "ask"),
        ("rm -rf modules", "ask"),
        ("rm -rf .agent/scratch/x", None),
        ("rm --force stray.txt", None),
        ("alembic downgrade -1", "ask"),
        ("docker compose down -v", "ask"),
        ("docker compose down", None),
        ('psql -c "DELETE FROM images;"', "ask"),
        ('psql -c "DELETE FROM images WHERE id = 1;"', None),
        ("git status && cat secrets.json", "deny"),
        ("python -m pytest -q", None),
    ],
)
def test_check_command(command, decision, repo):
    assert policy.check_command(command, repo).decision == decision


def test_script_inspection_flags_egress_and_sql(repo):
    (repo / "scripts" / "push.py").write_text(
        "import requests\nrequests.post('https://example.com/upload', data=open('x').read())\n"
    )
    (repo / "scripts" / "local.py").write_text("import requests\nrequests.get('http://localhost:7860/api/health')\n")
    (repo / "scripts" / "wipe.py").write_text("cur.execute('TRUNCATE images')\n")
    v = policy.check_command("python scripts/push.py --all", repo)
    assert v.decision == "ask" and v.script == "scripts/push.py"
    assert [f["kind"] for f in v.findings] == ["network_egress"]
    assert "requests.post" in v.excerpt
    assert policy.check_command("python scripts/local.py", repo).decision is None
    assert [f["kind"] for f in policy.check_command("python3 scripts/wipe.py", repo).findings] == ["destructive_sql"]


def test_inspect_skip(repo):
    (repo / "scripts" / "push.py").write_text("requests.post('https://example.com')\n")
    v = policy.check_command("python scripts/push.py", repo, {"inspect_skip": ["scripts/push.py"]})
    assert v.decision is None and v.script is None


# -- gate --------------------------------------------------------------------


def test_redaction():
    text = 'api_key = "abcd1234efgh5678" token: ghp_' + "a" * 30 + " postgres://u:p@h/db"  # fake values
    out = redact(text)
    assert "abcd1234efgh5678" not in out and "ghp_" not in out and "u:p@h" not in out
    assert contains_secret(text) and not contains_secret("scripts/agent_harness/policy.py")


def test_gate_off_does_not_call(repo):
    client = FakeClient()
    gate = make_gate(repo, client, decisions={"route": "off"})
    assert gate.ask("route", "harness.route.leave_frontier", {"x": 1}) is None
    assert client.calls == []


def test_env_mode_overrides(repo, monkeypatch):
    gate = make_gate(repo, FakeClient(), decisions={"route": "on"})
    monkeypatch.setenv("JEV_HARNESS_MODE", "off")
    assert gate.mode("route") == "off"


def test_gate_caches_budgets_and_logs(repo):
    key = "harness.route.leave_frontier"
    client = FakeClient(answers={key: noul(key, 0.9)})
    gate = make_gate(repo, client, decisions={"route": "on"}, max_calls_per_session=1)
    first = gate.ask("route", key, {"task": "a"})
    again = gate.ask("route", key, {"task": "a"})
    assert first["value"] == again["value"] == 0.9
    assert len(client.calls) == 1  # second answer came from the cache
    assert gate.ask("route", key, {"task": "b"}) is None  # budget of 1 spent
    log = (repo / ".agent/scratch/jev-harness/decisions.jsonl").read_text().splitlines()
    assert [json.loads(line)["cached"] for line in log] == [False, True]


def test_gate_redacts_state_before_sending(repo):
    key = "harness.route.leave_frontier"
    client = FakeClient(answers={key: noul(key, 0.9)})
    gate = make_gate(repo, client, decisions={"route": "on"})
    gate.ask("route", key, {"task": "use password=hunter2secret"})
    assert "hunter2secret" not in json.dumps(client.calls[0][2])


def test_gate_fail_safe(repo):
    gate = make_gate(repo, FakeClient(raises=True), decisions={"route": "on"})
    assert gate.ask("route", "harness.route.leave_frontier", {"t": 1}) is None


def test_gate_unavailable_without_key(repo, monkeypatch):
    for name in ("TYPESAFE_API_KEY", "JEV_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("modules.config.get_secret", lambda _name: None)
    gate = make_gate(repo, decisions={"route": "on"})
    assert gate.available() is False
    assert gate.ask("route", "harness.route.leave_frontier", {"t": 1}) is None


# -- packs -------------------------------------------------------------------


def test_parse_frontmatter_block_and_lists():
    meta, body = packs.parse_frontmatter("---\nname: x\ndescription: >\n  folded\n  text\npaths:\n  - \"a/**\"\n---\nbody\n")
    assert meta == {"name": "x", "description": "folded text", "paths": ["a/**"]}
    assert body == "body\n"


def test_split_globs_respects_braces():
    assert packs.split_globs('frontend/**/*.{tsx,css,ts},docs/**') == ["frontend/**/*.{tsx,css,ts}", "docs/**"]


def test_load_packs_skips_always_apply(repo):
    names = [p.name for p in packs.load_packs(repo, {"packs": {"mcp-triage": {"triggers": ["why did"]}}})]
    assert names == ["db-footguns", "mcp-triage"]


# -- hook: context -----------------------------------------------------------


def test_user_prompt_deterministic_fallback(repo):
    gate = make_gate(repo, decisions={"context": "off"}, packs={"mcp-triage": {"triggers": ["why did"]}})
    out = hook.on_user_prompt({"prompt": "why did scoring fail?"}, gate)
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert "mcp-triage" in ctx and "db-footguns" not in ctx
    # Same rung again: nothing new to inject.
    assert hook.on_user_prompt({"prompt": "why did scoring fail again?"}, gate) is None


def test_user_prompt_jev_ladder_acts_when_on(repo):
    key = "harness.context.visibility"
    client = FakeClient(subject_answers={"db-footguns": choice(key, "full", 0.9), "mcp-triage": choice(key, "hide", 0.8)})
    gate = make_gate(repo, client, decisions={"context": "on"}, packs={"mcp-triage": {"triggers": ["why did"]}})
    ctx = hook.on_user_prompt({"prompt": "why did this SQL query break on the regex?"}, gate)["hookSpecificOutput"]["additionalContext"]
    assert "### db-footguns (full)" in ctx and "Use [0-9]" in ctx
    assert "mcp-triage" not in ctx
    # Shadow: Jev is asked, but the deterministic rungs are used.
    gate2 = make_gate(repo, client, decisions={"context": "shadow"}, packs={"mcp-triage": {"triggers": ["why did"]}})
    gate2.session_id = "s2"
    ctx2 = hook.on_user_prompt({"prompt": "why did this SQL query break on the regex?"}, gate2)["hookSpecificOutput"]["additionalContext"]
    assert "mcp-triage" in ctx2 and "(full)" not in ctx2


def test_session_compact_repins(repo):
    gate = make_gate(repo, decisions={"context": "off"}, packs={"mcp-triage": {"triggers": ["why did"]}})
    hook.on_user_prompt({"prompt": "why did it fail"}, gate)
    out = hook.on_session_compact({"source": "compact"}, gate)
    assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "mcp-triage" in out["hookSpecificOutput"]["additionalContext"]


# -- hook: permissions -------------------------------------------------------


def _decision(out):
    return out["hookSpecificOutput"]["permissionDecision"] if out else None


def test_pre_bash_deterministic(repo):
    gate = make_gate(repo)
    assert _decision(hook.on_pre_bash({"tool_input": {"command": "cat secrets.json"}}, gate)) == "deny"
    assert hook.on_pre_bash({"tool_input": {"command": "git status"}}, gate) is None


def test_pre_bash_jev_escalates_only(repo):
    (repo / "scripts" / "push.py").write_text("requests.post('https://example.com')\n")
    (repo / "scripts" / "plain.py").write_text("print('hi')\n")
    key = "harness.permission.exec"
    allow = make_gate(repo, FakeClient(answers={key: choice(key, "allow", 0.99)}), decisions={"permission": "on"})
    # Deterministic ask survives a confident Jev "allow".
    assert _decision(hook.on_pre_bash({"tool_input": {"command": "python scripts/push.py"}}, allow)) == "ask"
    deny = make_gate(repo, FakeClient(answers={key: choice(key, "deny", 0.9)}), decisions={"permission": "on"})
    assert _decision(hook.on_pre_bash({"tool_input": {"command": "python scripts/plain.py"}}, deny)) == "deny"
    shadow = make_gate(repo, FakeClient(answers={key: choice(key, "deny", 0.9)}), decisions={"permission": "shadow"})
    shadow.session_id = "s3"
    assert hook.on_pre_bash({"tool_input": {"command": "python scripts/plain.py"}}, shadow) is None


def test_pre_review_sensitivity(repo):
    gate = make_gate(repo)
    out = hook.on_pre_review({"tool_input": {"files": ["modules/a.py", ".env"], "task": "review"}}, gate)
    assert _decision(out) == "deny" and ".env" in out["hookSpecificOutput"]["permissionDecisionReason"]
    leaked = {"tool_input": {"files": ["modules/a.py"], "task": "use token=abcdef123456 to call"}}
    assert _decision(hook.on_pre_review(leaked, gate)) == "deny"
    key = "harness.review.sensitivity"
    jev = make_gate(repo, FakeClient(subject_answers={"Dockerfile": choice(key, "restricted", 0.8)}),
                    decisions={"review_sensitivity": "on"})
    assert _decision(hook.on_pre_review({"tool_input": {"files": ["Dockerfile"]}}, jev)) == "deny"
    assert hook.on_pre_review({"tool_input": {"files": ["modules/a.py", "docs/x.md"]}}, gate) is None


def test_hook_main_is_fail_safe(monkeypatch, capsys, repo):
    monkeypatch.setattr(sys, "stdin", types.SimpleNamespace(read=lambda: "not json"))
    assert hook.main(["pre-bash", "--repo", str(repo)]) == 0
    assert capsys.readouterr().out == ""


# -- route / subgoals / bundle / budget --------------------------------------


def test_route_arithmetic_matches_design_note():
    prices = {"frontier": {"input": 5, "output": 25}, "delegate": {"input": 3, "output": 15}}
    m = 1_000_000
    stay, naive, _ = route.costs(x=int(0.65 * m), y=int(0.12 * m), z=int(0.23 * m), b=0, s=0, prices=prices)
    assert stay == pytest.approx(4.15) and naive == pytest.approx(6.19)


def test_route_recommendation(repo):
    (repo / "scripts" / "small.py").write_text("x = 1\n")
    key = "harness.route.leave_frontier"
    cfg = {"route": {"frontier": {"input": 5, "output": 25}, "delegate": {"input": 3, "output": 15},
                     "chars_per_token": 4, "leave_frontier_threshold": 0.7}}
    yes = make_gate(repo, FakeClient(answers={key: noul(key, 0.9)}), decisions={"route": "on"}, **cfg)
    assert route.estimate(yes, "rename a var", ["scripts/small.py"]).recommendation == "delegate"
    no = make_gate(repo, FakeClient(answers={key: noul(key, 0.2)}), decisions={"route": "on"}, **cfg)
    # Answers are cached repo-wide per question, so ask a different one.
    assert route.estimate(no, "rename another var", ["scripts/small.py"]).recommendation == "stay"
    (repo / ".env").write_text("X=1\n")
    assert route.estimate(yes, "rename a var", [".env"]).recommendation == "stay"


def test_subgoal_dedup(repo, tmp_path):
    ledger = tmp_path / "sg.jsonl"
    key = "harness.subgoal.duplicate"
    client = FakeClient(subject_answers={"sg-001": noul(key, 0.95)})
    gate = make_gate(repo, client, decisions={"subgoal_dedup": "on"})
    assert subgoals.add(gate, "Add tests for the permission hook", ledger) == {"registered": "sg-001"}
    assert subgoals.add(gate, "add tests for the permission hook", ledger)["by"] == "exact"
    assert subgoals.add(gate, "Cover pre-bash decisions with unit tests", ledger)["by"] == "jev"
    subgoals.set_status(ledger, "sg-001", "dropped")
    assert "registered" in subgoals.add(gate, "Add tests for the permission hook", ledger)


def test_bundle_built_once_and_excludes_restricted(repo):
    def git(*a):
        subprocess.run(["git", *a], cwd=repo, check=True, capture_output=True)

    git("init", "-q")
    git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "base")
    (repo / "scripts" / "feature.py").write_text("def f():\n    return 1\n")
    (repo / ".env").write_text("SECRET=1\n")
    git("add", "-f", "scripts/feature.py", ".env")
    gate = make_gate(repo, decisions={"context": "off"})
    path, info = bundle.build(gate, base="HEAD")
    text = path.read_text()
    assert info["excluded"] == [".env"] and "SECRET" not in text and "def f()" in text
    assert bundle.build(gate, base="HEAD")[1] == {"reused": True}


def test_budget_counts_only_unconditional(repo):
    rules = repo / ".claude" / "rules"
    rules.mkdir(parents=True)
    (rules / "a.md").write_text("---\ndescription: a\n---\nalways\n")
    (rules / "b.md").write_text("---\ndescription: b\npaths:\n  - \"x/**\"\n---\nscoped\n")
    skill = repo / ".claude" / "skills" / "op"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: op\ndescription: operator only\ndisable-model-invocation: true\n---\n")
    report = budget.measure(repo)
    assert ".claude/rules/a.md" in report["always_on"] and ".claude/rules/b.md" in report["on_demand"]
    assert report["always_on"]["skill+command listing"] == 0


# -- sync translation --------------------------------------------------------


def _sync_module():
    spec = importlib.util.spec_from_file_location("sync_assistant_trees", ROOT / "scripts" / "sync_assistant_trees.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_sync_translates_rule_frontmatter():
    sync = _sync_module()
    always = sync.claude_rule_text("---\ndescription: d\nalwaysApply: true\n---\n\nbody\n")
    assert always == "---\ndescription: d\n---\n\nbody\n"
    scoped = sync.claude_rule_text('---\ndescription: d\nglobs: "a/**,b/*.{ts,tsx}"\nalwaysApply: false\n---\nbody\n')
    assert 'paths:\n  - "a/**"\n  - "b/*.{ts,tsx}"' in scoped and "globs" not in scoped
    assert sync.claude_rule_text("---\ndescription: d\nalwaysApply: false\n---\nbody\n") is None


# -- MCP search rerank -------------------------------------------------------


def test_search_rerank_only_when_low_confidence(monkeypatch):
    from modules.mcp.actions import search

    monkeypatch.setattr(search, "_rerank_enabled", lambda: True)
    picks = []

    def fake_pick(query, rows):
        picks.append(query)
        return rows[-1]["action_id"], 0.9

    monkeypatch.setattr(search, "_jev_pick", fake_pick)
    low = search.search_actions("status", limit=5)  # ambiguous: BM25 is unsure
    assert low["low_confidence"] and low["rerank"]["by"] == "jev"
    assert low["results"][0]["action_id"] == low["rerank"]["action_id"]
    picks.clear()
    confident = search.search_actions("run doctor without gpu", limit=5)
    assert not confident["low_confidence"]
    assert "rerank" not in confident and picks == []


def test_search_rerank_requires_master_switch(monkeypatch):
    from modules.mcp.actions import search

    monkeypatch.setattr("modules.config.get_config_section", lambda _n: {"mcp_search_rerank": True})
    assert search._rerank_enabled() is False
    monkeypatch.setattr("modules.config.get_config_section", lambda _n: {"enabled": True, "mcp_search_rerank": True})
    assert search._rerank_enabled() is True
