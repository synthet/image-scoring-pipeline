"""Frozen R2 evaluation proposes eligibility without granting runtime authority."""

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

import pytest

from modules.localization_evaluation import (
    ArtifactScope, R2_RULE_ID, R2_RULE_SHA256, evaluate_r2,
)


SCOPE = ArtifactScope("bird-detector-fixture/1", "config-fixture", "rendition-fixture/1")


def run(**changes):
    return {
        "id": 11, "image_id": 7, "detector_key": "bird", "is_current": True,
        "status": "detected", "coord_space": "display_normalized",
        "detector_version": SCOPE.detector_version,
        "detector_config_hash": SCOPE.detector_config_hash,
        "rendition_version": SCOPE.rendition_version,
        **changes,
    }


def region(**changes):
    return {
        "id": 23, "localization_run_id": 11, "object_class": "bird", "rank": 0,
        "confidence": 0.7, "x1": 0.0, "y1": 0.0, "x2": 1.0, "y2": 0.02,
        **changes,
    }


def evaluate(regions=None, **changes):
    return evaluate_r2(
        changes.pop("run", run()), [region()] if regions is None else regions,
        bird_tagged=changes.pop("bird_tagged", True),
        has_active_selection=changes.pop("has_active_selection", False),
        scope=changes.pop("scope", SCOPE), **changes,
    )


def test_r2_accepts_threshold_candidate_as_proposed_geometry_and_species_input():
    result = evaluate()
    assert result.status == "accept"
    assert result.reason == "r2_eligible"
    assert result.region_id == 23
    assert result.area_fraction == 0.02
    assert result.band == "large"
    assert result.geometry_eligible and result.species_eligible


def test_fixture_is_the_exact_frozen_rule():
    raw = (Path(__file__).parent / "fixtures/localization/rule-frozen-20261026.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == R2_RULE_SHA256
    rule = json.loads(raw)
    assert rule["id"] == R2_RULE_ID
    assert (rule["candidate"], rule["min_confidence"], rule["max_regions"], rule["rank"]) == (
        "R2", 0.7, 3, 0,
    )
    assert (rule["small_max_area_exclusive"], rule["medium_max_area_exclusive"]) == (0.005, 0.02)
    assert rule["small_use"] == "geometry_only"


@pytest.mark.parametrize("area,band,species", [
    (0.00001, "small", False),
    (math.nextafter(0.005, 0), "small", False),
    (0.005, "medium", True),
    (math.nextafter(0.02, 0), "medium", True),
    (0.02, "large", True), (1.0, "large", True),
])
def test_area_boundaries_and_small_geometry_only(area, band, species):
    result = evaluate([region(y2=area)])
    assert result.status == "accept"
    assert result.area_fraction == area and result.band == band
    assert result.geometry_eligible
    assert result.species_eligible is species


@pytest.mark.parametrize("confidence", [math.nextafter(0.7, 0), 0.0, None])
def test_below_threshold_or_missing_confidence_is_rejected(confidence):
    result = evaluate([region(confidence=confidence)])
    assert result.status == "reject" and result.reason == "confidence_below_threshold"
    assert result.region_id is None
    assert not result.geometry_eligible and not result.species_eligible


@pytest.mark.parametrize("confidence", [math.nan, math.inf, -math.inf, True, "0.9", -0.1, 1.1])
def test_malformed_confidence_is_invalid(confidence):
    result = evaluate([region(confidence=confidence)])
    assert result.status == "invalid" and result.reason == "invalid_confidence"


def test_stored_rank_zero_wins_even_when_another_region_has_higher_confidence():
    rows = [region(id=24, rank=1, confidence=0.99), region(confidence=0.69)]
    assert evaluate(rows).status == "reject"
    rows[1]["confidence"] = 0.7
    assert evaluate(rows).region_id == 23
    assert evaluate(list(reversed(rows))).region_id == 23


@pytest.mark.parametrize("count", [1, 2, 3])
def test_one_to_three_total_regions_are_eligible(count):
    rows = [region(id=23 + i, rank=i) for i in range(count)]
    assert evaluate(rows).status == "accept"


def test_count_all_stored_regions_including_other_classes():
    rows = [region(), *[region(id=23 + i, rank=i, object_class="animal") for i in range(1, 4)]]
    result = evaluate(rows)
    assert result.status == "reject" and result.reason == "region_count_outside_rule"


@pytest.mark.parametrize("rows,reason", [
    ([], "missing_rank_zero"),
    ([region(rank=1)], "missing_rank_zero"),
    ([region(), region(id=24, object_class="animal")], "ambiguous_rank_zero"),
    ([region(), region(rank=1)], "duplicate_region_id"),
    ([region(localization_run_id=12)], "region_run_mismatch"),
    ([region(id=True)], "invalid_region_identity"),
    ([region(rank=False)], "invalid_region_rank"),
    ([region(rank=-1)], "invalid_region_rank"),
])
def test_incomplete_or_ambiguous_artifacts_fail_closed(rows, reason):
    result = evaluate(rows)
    assert result.status == "invalid" and result.reason == reason
    assert not result.geometry_eligible and not result.species_eligible


@pytest.mark.parametrize("field,value", [
    ("x1", math.nan), ("y1", math.inf), ("x2", -math.inf), ("y2", None),
    ("x1", -0.0001), ("x2", 1.00001), ("x1", True), ("y2", "0.5"),
    ("x1", 1.0), ("y2", 0.0), ("x1", 10 ** 400),
])
def test_invalid_geometry_is_not_clamped_or_promoted(field, value):
    result = evaluate([region(**{field: value})])
    assert result.status == "invalid" and result.reason == "invalid_geometry"
    assert result.region_id is None


@pytest.mark.parametrize("changes", [
    {"bird_tagged": False}, {"has_active_selection": True},
    {"bird_tagged": None}, {"has_active_selection": None},
    {"run": run(detector_key="animal")}, {"run": run(is_current=False)},
    {"run": run(is_current="true")}, {"run": run(status="no_detection")},
    {"run": run(coord_space="legacy_unverified")},
    {"run": run(detector_version="other-model")},
    {"run": run(detector_config_hash="other-config")},
    {"run": run(rendition_version="other-rendition")},
    {"run": run(detector_config_hash=None)}, {"scope": None},
    {"scope": ArtifactScope("", "", "")},
    {"rule_id": "future-rule/2"}, {"rule_sha256": "0" * 64},
])
def test_outside_original_population_or_unknown_identity_abstains(changes):
    result = evaluate(**changes)
    assert result.status == "abstain"
    assert result.region_id is None
    assert not result.geometry_eligible and not result.species_eligible


def test_generic_animal_region_cannot_supply_bird_species_permission():
    result = evaluate([region(object_class="animal")])
    assert result.status == "abstain" and result.reason == "unknown_object_class"


@pytest.mark.parametrize("changes", [{"id": None}, {"id": True}, {"image_id": -1}])
def test_invalid_run_identity_fails_closed(changes):
    result = evaluate(run=run(**changes))
    assert result.status == "invalid" and result.reason == "invalid_run_identity"


def test_evaluation_does_not_mutate_its_inputs():
    artifact, rows = run(), [region(id=24, rank=1), region()]
    original = deepcopy((artifact, rows))
    evaluate(rows, run=artifact)
    assert (artifact, rows) == original


def test_species_permission_also_respects_existing_decimal_area_boundary():
    # Float R2 banding rounds this product up to 0.005; stored decimal area is
    # below the existing species boundary and must not gain species permission.
    result = evaluate([region(x2=0.1, y2=0.049999999999999996)])
    assert result.status == "accept" and result.band == "medium"
    assert result.geometry_eligible
    assert not result.species_eligible
