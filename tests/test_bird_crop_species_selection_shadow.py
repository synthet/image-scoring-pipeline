"""Species shadow re-run on promoted selections (#493): per-image outcome and summary."""
from __future__ import annotations

import pytest

from scripts.research.bird_crop.species_selection_shadow import compare, render_markdown, summarise


def _old(species, conf=0.5, source="bioclip", also=()):
    return {"species": species, "confidence": conf, "source": source, "all": [species, *also]}


@pytest.mark.parametrize("old, preds, outcome", [
    (_old("osprey"), [("Osprey", 0.7)], "same"),
    (_old("osprey"), [("Bald Eagle", 0.6), ("Osprey", 0.3)], "changed"),
    (None, [("Osprey", 0.4)], "now_labelled"),
    (_old("osprey"), [("Osprey", 0.05)], "now_abstains"),
    (None, [("Osprey", 0.05)], "both_abstain"),
    (None, [], "both_abstain"),
])
def test_compare_outcomes_apply_the_threshold_to_the_new_top1(old, preds, outcome):
    assert compare(old, preds, threshold=0.1)["outcome"] == outcome


def test_compare_keeps_unthresholded_top_and_delta_only_for_same_label():
    same = compare(_old("osprey", 0.5), [("Osprey", 0.7), ("Bald Eagle", 0.2)], 0.1)
    assert same["conf_delta"] == pytest.approx(0.2)
    assert same["new_top3"] == [["osprey", 0.7], ["bald eagle", 0.2]]
    abstain = compare(_old("osprey", 0.5), [("Osprey", 0.05)], 0.1)
    assert abstain["new"] is None and abstain["new_top"] == "osprey" and abstain["conf_delta"] is None


def test_summarise_rates_and_markdown():
    results = [
        compare(_old("osprey", 0.5), [("Osprey", 0.7)], 0.1),
        compare(_old("osprey", 0.4), [("Bald Eagle", 0.6)], 0.1),
        compare(None, [("Osprey", 0.4)], 0.1),
    ]
    s = summarise(results)
    assert s["n"] == 3
    assert s["outcomes"] == {"same": 1, "changed": 1, "now_labelled": 1}
    assert s["changed_rate"] == 0.5
    assert s["same_label_conf_delta"]["rose"] == 1
    assert s["changed_conf"] == {"old_mean": 0.4, "new_mean": 0.6}
    md = render_markdown({"selected_by": "r", "threshold": 0.1, "elapsed_s": 1.0, "skipped": {}}, s)
    assert "| changed | 1 |" in md and "0.4 -> 0.6" in md


def test_changed_to_another_stored_species_is_flagged_and_placeholder_conf_ignored():
    r = compare(_old("osprey", None, "auto", also=("bald eagle",)), [("Bald Eagle", 0.6)], 0.1)
    assert r["outcome"] == "changed" and r["new_in_old_set"] is True
    s = summarise([r])
    assert s["changed_but_in_old_set"] == 1
    assert s["changed_conf"] == {"old_mean": None, "new_mean": None}
