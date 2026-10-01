"""Reply parsing and majority voting for the scene-route CLI judges (#412)."""

import csv
import json

from scripts.research.scene_route.cli_judges import consensus, parse_reply


def test_parse_reply_takes_last_valid_json_and_drops_bad_rows():
    text = ('thinking {"images": []} ... final:\n```json\n{"images":[{"image_id":1,"scene":"landscape",'
            '"bird_visible":"No"},{"image_id":2,"scene":"spaceship","bird_visible":"yes"}]}\n```')
    assert parse_reply(text) == {1: {"scene": "landscape", "bird_visible": "no"}}
    assert parse_reply("no json here") == {}


def _reply(rows):
    return json.dumps({"images": [{"image_id": i, "scene": s, "bird_visible": b} for i, s, b in rows]})


def test_consensus_majority_ties_and_disputes(tmp_path):
    with (tmp_path / "cohort.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["image_id", "stratum", "file_path"])
        w.writerows([[1, "x", "a"], [2, "x", "b"], [3, "x", "c"]])
    votes = {"codex": [(1, "landscape", "no"), (2, "people", "yes"), (3, "vehicles", "no")],
             "agy": [(1, "landscape", "no"), (2, "landscape", "no"), (3, "other", "yes")],
             "claude": [(1, "landscape", "no"), (2, "people", "no")]}
    for judge, rows in votes.items():
        (tmp_path / "judges" / judge).mkdir(parents=True)
        (tmp_path / "judges" / judge / "b.json").write_text(_reply(rows))
    summary = consensus(tmp_path)
    with (tmp_path / "judge_labels.csv").open() as fh:
        labels = {int(r["image_id"]): (r["scene"], r["bird_visible"]) for r in csv.DictReader(fh)}
    assert labels == {1: ("landscape", "no"), 2: ("people", "no"), 3: ("cant_tell", "yes")}
    assert summary["unanimous"] == 1 and summary["disputed"] == 2
    assert summary["pairwise"]["codex~agy"] == {"n": 3, "scene_agree": 1, "bird_agree": 1}
