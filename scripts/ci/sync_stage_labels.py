#!/usr/bin/env python3
"""Two-way sync between the Project board ``Stage`` field and ``stage:*`` issue labels.

Cloud agent sessions cannot reach the Project board (GraphQL and ``users/*/projectsV2``
are blocked there), but they can read and write issue labels. This script runs in
GitHub Actions (``.github/workflows/board-stage-sync.yml``) and mirrors Stage onto
labels so those sessions can pick, claim, and transition work. See
docs/project/00-backlog-workflow.md §6.

Rule per open board issue: labels matching the board are a no-op; otherwise the newer
side wins, comparing the Stage value's ``updatedAt`` with the latest ``labeled`` event
of the issue's current ``stage:*`` labels. Closed board issues move to Stage = Done, and
any ``stage:*`` labels they carry collapse to ``stage:done``.

Usage:
  python scripts/ci/sync_stage_labels.py --dry-run
  python scripts/ci/sync_stage_labels.py
"""

from __future__ import annotations

import argparse
import datetime
import sys
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent_skills"))

from backlog_stage import (  # noqa: E402
    OWNER,
    PROJECT_NUMBER,
    REPOS,
    STAGE_OPTIONS,
    gh_json,
    gh_run,
    set_stage,
)

LABEL_PREFIX = "stage:"
LABEL_COLOR = "bfd4f2"
STAGE_LABELS = tuple(LABEL_PREFIX + key.replace("_", "-") for key in STAGE_OPTIONS)
_STAGE_BY_OPTION = {option: key for key, option in STAGE_OPTIONS.items()}
_NEVER = datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)

_ITEMS_QUERY = """
query($owner: String!, $number: Int!, $after: String) {
  user(login: $owner) {
    projectV2(number: $number) {
      items(first: 100, after: $after) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          stage: fieldValueByName(name: "Stage") {
            ... on ProjectV2ItemFieldSingleSelectValue { optionId updatedAt }
          }
          content {
            __typename
            ... on Issue {
              number
              state
              repository { nameWithOwner }
              labels(first: 50) { nodes { name } }
            }
          }
        }
      }
    }
  }
}
"""


def label_for(stage_key: str) -> str:
    return LABEL_PREFIX + stage_key.replace("_", "-")


def stage_for_label(label: str) -> str | None:
    if not label.startswith(LABEL_PREFIX):
        return None
    key = label[len(LABEL_PREFIX):].replace("-", "_")
    return key if key in STAGE_OPTIONS else None


def _ts(value: str | None) -> datetime.datetime | None:
    return datetime.datetime.fromisoformat(value) if value else None


@dataclass(frozen=True)
class Decision:
    set_board: str | None = None
    add: tuple[str, ...] = ()
    remove: tuple[str, ...] = ()

    @property
    def is_noop(self) -> bool:
        return not (self.set_board or self.add or self.remove)


def decide(
    board_stage: str | None,
    board_updated_at: str | None,
    labels: dict[str, str | None],
) -> Decision:
    """Reconcile one issue.

    ``labels`` maps each ``stage:*`` label currently on the issue (as a stage key) to
    the time it was last added, or None when unknown.
    """
    present = set(labels)
    if board_stage and present == {board_stage}:
        return Decision()
    if not present:
        return Decision(add=(board_stage,)) if board_stage else Decision()

    latest = max(present, key=lambda k: (_ts(labels[k]) or _NEVER, k))
    latest_at = _ts(labels[latest])
    board_at = _ts(board_updated_at)
    label_wins = board_stage is None or (
        latest != board_stage and latest_at is not None and (board_at is None or latest_at > board_at)
    )
    if label_wins:
        return Decision(set_board=latest, remove=tuple(sorted(present - {latest})))
    return Decision(
        add=() if board_stage in present else (board_stage,),
        remove=tuple(sorted(present - {board_stage})),
    )


def decide_closed(board_stage: str | None, present: set[str]) -> Decision:
    """Closed issues are Done: move the board there; collapse existing stage labels."""
    return Decision(
        set_board=None if board_stage == "done" else "done",
        add=("done",) if present and "done" not in present else (),
        remove=tuple(sorted(present - {"done"})),
    )


@dataclass(frozen=True)
class Planned:
    repo: str
    number: int
    item_id: str
    decision: Decision


def plan(
    items: Iterable[dict],
    *,
    label_events: Callable[[str, int], dict[str, str]],
) -> Iterator[Planned]:
    """Yield the non-noop decisions for board issues in REPOS."""
    repos = set(REPOS.values())
    for item in items:
        content = item.get("content") or {}
        if content.get("__typename") != "Issue":
            continue
        repo = (content.get("repository") or {}).get("nameWithOwner")
        if repo not in repos:
            continue
        stage = item.get("stage") or {}
        board_stage = _STAGE_BY_OPTION.get(stage.get("optionId") or "")
        present = {
            key
            for node in (content.get("labels") or {}).get("nodes") or []
            if (key := stage_for_label(node.get("name") or ""))
        }
        if content.get("state") == "CLOSED":
            decision = decide_closed(board_stage, present)
            if not decision.is_noop:
                yield Planned(repo, content["number"], str(item["id"]), decision)
            continue
        if board_stage and present == {board_stage}:
            continue
        if not present and not board_stage:
            continue
        times = label_events(repo, content["number"]) if present else {}
        decision = decide(board_stage, stage.get("updatedAt"), {k: times.get(k) for k in present})
        if not decision.is_noop:
            yield Planned(repo, content["number"], str(item["id"]), decision)


def fetch_items() -> list[dict]:
    items: list[dict] = []
    after: str | None = None
    while True:
        args = ["api", "graphql", "-f", f"query={_ITEMS_QUERY}", "-f", f"owner={OWNER}",
                "-F", f"number={PROJECT_NUMBER}"]
        if after:
            args += ["-f", f"after={after}"]
        page = gh_json(*args)["data"]["user"]["projectV2"]["items"]
        items.extend(page["nodes"])
        if not page["pageInfo"]["hasNextPage"]:
            return items
        after = page["pageInfo"]["endCursor"]


def fetch_label_events(repo: str, number: int) -> dict[str, str]:
    """Latest ``labeled`` time per stage key, from the issue's event history."""
    out = gh_run(
        "api", "--paginate", f"repos/{repo}/issues/{number}/events",
        "--jq", '.[] | select(.event == "labeled") | "\\(.label.name)\\t\\(.created_at)"',
    )
    latest: dict[str, str] = {}
    for line in out.splitlines():
        name, _, created_at = line.partition("\t")
        key = stage_for_label(name)
        if key and (key not in latest or _ts(created_at) > _ts(latest[key])):
            latest[key] = created_at
    return latest


def ensure_labels(dry_run: bool) -> None:
    for repo in REPOS.values():
        existing = {row["name"] for row in gh_json("label", "list", "--repo", repo, "--limit", "500",
                                                    "--json", "name")}
        for key in STAGE_OPTIONS:
            name = label_for(key)
            if name in existing:
                continue
            print(f"create label {name} in {repo}")
            if not dry_run:
                gh_run("label", "create", name, "--repo", repo, "--color", LABEL_COLOR,
                       "--description", f"Project board Stage (synced): {key.replace('_', ' ')}")


def apply(p: Planned) -> None:
    d = p.decision
    if d.set_board:
        set_stage(p.item_id, d.set_board)
    edit = ["issue", "edit", str(p.number), "--repo", p.repo]
    if d.add:
        edit += ["--add-label", ",".join(label_for(k) for k in d.add)]
    if d.remove:
        edit += ["--remove-label", ",".join(label_for(k) for k in d.remove)]
    if d.add or d.remove:
        gh_run(*edit)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="print planned changes only")
    args = parser.parse_args()

    ensure_labels(args.dry_run)
    items = fetch_items()
    counts = {"board": 0, "labels": 0, "errors": 0}
    for p in plan(items, label_events=fetch_label_events):
        d = p.decision
        print(
            f"{p.repo}#{p.number}: board->{d.set_board or '-'} "
            f"+{[label_for(k) for k in d.add]} -{[label_for(k) for k in d.remove]}"
        )
        if args.dry_run:
            continue
        try:
            apply(p)
        except RuntimeError as exc:
            counts["errors"] += 1
            print(f"  error: {exc}", file=sys.stderr)
            continue
        counts["board"] += bool(d.set_board)
        counts["labels"] += bool(d.add or d.remove)
    mode = "dry-run" if args.dry_run else "applied"
    print(f"{len(items)} board items; {mode}: board={counts['board']} labels={counts['labels']} "
          f"errors={counts['errors']}")
    return 1 if counts["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
