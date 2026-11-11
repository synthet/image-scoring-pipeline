"""#851: production selections under the #694 owner standard — draw, hard stops, batches and analysis."""
import json

import pytest

from scripts.research.detector_benchmark import promotion_694_owner as owner694
from scripts.research.detector_benchmark import promotion_851_production as p851

BOXES = {"large": (0.1, 0.1, 0.4, 0.4), "medium": (0.1, 0.1, 0.2, 0.2), "small": (0.1, 0.1, 0.15, 0.15)}


def selection(image_id, band, rule=None, coord="display_normalized"):
    rule = rule or ("v1_regate_rule/4" if band == "small" else "v1_regate_rule/3")
    x1, y1, x2, y2 = BOXES[band]
    return {"image_id": image_id, "selected_by": f"{rule}:abc", "run_id": image_id + 1, "region_id": image_id + 2,
            "rendition_hash": f"r{image_id}", "coord_space": coord, "x1": x1, "y1": y1, "x2": x2, "y2": y2,
            "file_path": f"/photos/{image_id}.nef", "folder_id": image_id // 7}


def production_rows(per_band=150):
    return [selection(50000 + b * 1000 + i, band) for b, band in enumerate(p851.BANDS) for i in range(per_band)]


def sample694():
    return [{**selection(10000 + b * 1000 + i, band), "band": band}
            for b, band in enumerate(p851.BANDS) for i in range(130)]


@pytest.fixture
def env(tmp_path, monkeypatch):
    root, p694 = tmp_path / "851", tmp_path / "694"
    root.mkdir()
    p694.mkdir()
    excluded = [50000, 51000, 52000]  # the first id of every production band
    (p694 / "exclusions-frozen-20261026.json").write_text(json.dumps({"ids": excluded}), encoding="utf-8")
    (p694 / "sample-frozen-20261026.json").write_text(json.dumps({"frames": sample694()}), encoding="utf-8")
    (p694 / "controls4-batch-20261109.json").write_text(json.dumps({"low_pool": [{"image_id": 50001}]}),
                                                        encoding="utf-8")
    (root / p851.PREREG).write_text("frozen\n", encoding="utf-8")
    receipt = {"preregistration": p851.PREREG, "preregistration_sha256": p851.sha256(root / p851.PREREG),
               "exclusions_sha256": p851.sha256(p694 / "exclusions-frozen-20261026.json"),
               "seeds": {"production": p851.SEED_SAMPLE, "repeats": p851.SEED_REPEATS, "order": p851.SEED_ORDER}}
    (root / p851.FREEZE).write_text(json.dumps(receipt), encoding="utf-8")
    monkeypatch.setattr(p851, "FREEZE_SHA256", p851.sha256(root / p851.FREEZE))
    return root, p694


def frozen(env):
    root, p694 = env
    p851.freeze_sample(root, p694, production_rows(), lambda p: True, now="2026-11-11T00:00:00+00:00")
    return p851.load_sample(root)


def test_classify_raises_every_pre_registered_hard_stop():
    rows = [selection(1, "small", rule="v1_regate_rule/3"), selection(2, "large", rule="v1_regate_rule/4"),
            selection(3, "medium", coord="original_pixels"), {**selection(4, "large"), "x2": 0.05},
            selection(5, "large"), selection(5, "large")]
    _, stops, _ = p851.classify(rows, lambda p: True)
    reasons = {reason for reason, _ in stops}
    assert reasons == {"v1_regate_rule/3 box in the small band", "v1_regate_rule/4 box in the large band",
                       "coordinate space is not display_normalized", "invalid box",
                       "duplicate active selections for one image"}


def test_missing_files_are_dropped_not_stopped():
    pools, stops, missing = p851.classify(production_rows(2), lambda p: not p.endswith("50000.nef"))
    assert not stops and missing == 1 and len(pools["large"]) == 1


def test_draw_is_seeded_excludes_earlier_samples_and_fills_14_batches(env):
    sample = frozen(env)
    frames = sample["frames"]
    assert len(frames) == 420 and [r["batch"] for r in sample["items"]].count(14) == 30
    production = [r for r in frames if r["kind"] == "production"]
    assert {50000, 50001, 51000, 52000} & {r["image_id"] for r in production} == set()
    assert {b: sum(r["band"] == b for r in production) for b in p851.BANDS} == dict.fromkeys(p851.BANDS, 130)
    repeats = [r for r in frames if r["kind"] == "repeat"]
    assert {b: sum(r["band"] == b for r in repeats) for b in p851.BANDS} == dict.fromkeys(p851.BANDS, 10)
    pool = sorted(r["image_id"] for r in production_rows() if r["image_id"] not in {50000, 50001}
                  and r["image_id"] < 51000)
    assert [r["image_id"] for r in production if r["band"] == "large"] == p851.seeded(pool, p851.SEED_SAMPLE)[:130]


def test_the_sample_is_create_only_and_its_hash_is_checked(env):
    root, p694 = env
    frozen(env)
    with pytest.raises(FileExistsError):
        p851.freeze_sample(root, p694, production_rows(), lambda p: True)
    sample = json.loads((root / p851.SAMPLE).read_text(encoding="utf-8"))
    sample["frames"][0]["band"] = "small"
    (root / p851.SAMPLE).write_text(json.dumps(sample), encoding="utf-8")
    with pytest.raises(ValueError, match="sample changed"):
        p851.load_sample(root)


def test_a_short_band_is_a_hard_stop(env):
    root, p694 = env
    with pytest.raises(ValueError, match="hard stop"):
        p851.freeze_sample(root, p694, production_rows(131), lambda p: True)
    assert not (root / p851.SAMPLE).exists()


def test_an_edited_preregistration_or_exclusion_file_is_refused(env):
    root, p694 = env
    (p694 / "exclusions-frozen-20261026.json").write_text(json.dumps({"ids": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="exclusions changed"):
        p851.freeze_sample(root, p694, production_rows(), lambda p: True)
    (root / p851.PREREG).write_text("edited\n", encoding="utf-8")
    with pytest.raises(ValueError, match="pre-registration changed"):
        p851.load_freeze(root)


def test_the_public_sheet_hides_which_frames_are_repeats(env, tmp_path):
    from PIL import Image

    root, _ = env
    sample = frozen(env)

    def render(frame, overview, crop):
        for target in (overview, crop):
            Image.new("RGB", (8, 8)).save(target, "JPEG")

    assert p851.render_sample(root, tmp_path, sample, render) == 420
    sheet = (root / p851.BLIND / "sheet.json").read_text(encoding="utf-8")
    assert "repeat" not in sheet and "image_id" not in sheet and len(json.loads(sheet)["batches"]) == 14
    manifest = json.loads((root / p851.MANIFEST).read_text(encoding="utf-8"))["items"]
    assert sum(r["kind"] == "repeat" for r in manifest) == 30


def record_all(root, label_for):
    items = p851.load_sample(root)["items"]
    for batch in range(1, p851.BATCHES + 1):
        rows = [r for r in items if r["batch"] == batch]
        p851.record(root, batch, {r["token"]: label_for(r) for r in rows}, {}, "sha")


def test_batches_are_recorded_in_order_and_count_down_from_14(env):
    root, _ = env
    frozen(env)
    items = p851.load_sample(root)["items"]
    with pytest.raises(ValueError, match="next is 1"):
        p851.record(root, 2, {r["token"]: "usable" for r in items if r["batch"] == 2}, {}, "sha")
    first = p851.record(root, 1, {r["token"]: "usable" for r in items if r["batch"] == 1}, {}, "sha")
    assert first["batches_left"] == 13


def write_694(p694, label_for):
    rows = sample694()
    order = owner694.mixed_order([r["image_id"] for r in rows])
    band = {r["image_id"]: r["band"] for r in rows}
    manifest = [{"id": r["token"], "image_id": r["image_id"], "band": band[r["image_id"]]} for r in order]
    (p694 / owner694.MANIFEST).write_text(json.dumps({"items": manifest}), encoding="utf-8")
    for batch in range(1, 14):
        owner694.record_batch(p694 / owner694.RECORD, order, batch,
                              {r["id"]: label_for(r) for r in manifest if order[int(r["id"][1:]) - 1]["batch"] == batch},
                              {})


def test_analysis_keeps_repeats_out_of_the_bands_and_measures_consistency(env, tmp_path):
    from PIL import Image

    root, p694 = env
    sample = frozen(env)
    p851.render_sample(root, tmp_path, sample,
                       lambda f, o, c: [Image.new("RGB", (8, 8)).save(t, "JPEG") for t in (o, c)])
    kind = {r["id"]: r["kind"] for r in json.loads((root / p851.MANIFEST).read_text(encoding="utf-8"))["items"]}
    write_694(p694, lambda r: "poor_crop" if r["band"] != "large" else "usable")
    record_all(root, lambda r: "no_bird" if kind[r["token"]] == "repeat" else "usable")
    result = p851.analyze(root, p694)
    assert {b: result["bands"][b]["usable"] for b in p851.BANDS} == dict.fromkeys(p851.BANDS, 130)
    assert all(result["bands"][b]["passed"] for b in p851.BANDS)
    assert result["consistency"]["repeats"] == 30 and result["consistency"]["exact"] == 0
    assert result["compare_694"]["medium"]["usable_diff"] == pytest.approx(1.0)
    assert result["compare_694"]["large"]["usable_diff"] == pytest.approx(0.0)
    assert result["verdict"] == "inconclusive"  # large matches #694, so its difference includes 0
    assert result["selection_changes"] == 0


def test_newcombe_matches_the_published_example():
    low, high = p851.newcombe(56, 70, 48, 80)  # Newcombe (1998), example (a): 0.0524 to 0.3339
    assert low == pytest.approx(0.0524, abs=5e-4) and high == pytest.approx(0.3339, abs=5e-4)


@pytest.mark.parametrize("large_pass,medium_pass,large_ci,medium_ci,expected", [
    (False, True, (0.1, 0.2), (0.1, 0.2), "standard_explains"),
    (True, False, (0.1, 0.2), (0.1, 0.2), "standard_explains"),
    (True, True, (0.1, 0.2), (0.05, 0.3), "yolo_cohort_crops_worse"),
    (True, True, (-0.1, 0.2), (0.1, 0.2), "inconclusive"),
])
def test_verdict_follows_the_frozen_rule(large_pass, medium_pass, large_ci, medium_ci, expected):
    bands = {"large": {"passed": large_pass}, "medium": {"passed": medium_pass}, "small": {"passed": False}}
    compare = {"large": {"usable_diff_ci": list(large_ci)}, "medium": {"usable_diff_ci": list(medium_ci)},
               "small": {"usable_diff_ci": [-1.0, -0.5]}}
    assert p851.verdict(bands, compare) == expected
