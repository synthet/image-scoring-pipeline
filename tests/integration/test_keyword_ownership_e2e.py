"""E2E: phase-scoped keyword writes keep rows other writers own (#586). ``pytest.mark.postgres``.

A keywords run used to delete every ``image_keywords`` row of an image and write back only its
CLIP tags, so species labels and hand-entered keywords were lost. A species write rewrote every
row with ``source='auto'``, so the next keywords run would treat hand-entered rows as its own.
"""

from __future__ import annotations

import uuid

import pytest

pytestmark = [pytest.mark.postgres]

from modules import db  # noqa: E402


@pytest.fixture(autouse=True)
def _postgres_clean(postgres_test_session, clean_postgres):
    yield


def _image() -> int:
    row = db.get_connector().execute_returning(
        "INSERT INTO images (file_path) VALUES (?) RETURNING id", (f"/tmp/kw-{uuid.uuid4().hex}.jpg",))
    return int(row[0]["id"])


def _seed(iid: int, rows: dict[str, tuple[str, float]]) -> None:
    """Write ``{keyword: (source, confidence)}`` as a full keyword edit."""
    db.update_image_keywords_for_image(
        iid, ",".join(rows), source="auto",
        source_map={k.lower(): s for k, (s, _) in rows.items()},
        confidence_map={k.lower(): c for k, (_, c) in rows.items()})


def _rows(iid: int) -> dict[str, tuple[str, float]]:
    rows = db.get_connector().query(
        "SELECT kd.keyword_norm, ik.source, ik.confidence FROM image_keywords ik "
        "JOIN keywords_dim kd ON kd.keyword_id = ik.keyword_id WHERE ik.image_id = ?", (iid,))
    return {r["keyword_norm"]: (r["source"], round(float(r["confidence"]), 3)) for r in rows}


def _legacy_csv(iid: int) -> set[str]:
    row = db.get_connector().query_one("SELECT keywords FROM images WHERE id = ?", (iid,))
    return {k.strip().lower() for k in (row["keywords"] or "").split(",") if k.strip()}


def test_keywords_run_replaces_only_its_own_rows():
    iid = _image()
    _seed(iid, {
        "nature": ("auto", 0.8), "urban": ("repair_legacy_keywords_junction", 1.0),
        "wildlife": ("legacy_backfill", 1.0), "travel": ("electron_ui", 1.0),
        "birds": ("localization_selection", 1.0), "species:Carolina Wren": ("bioclip_region", 0.9),
        "birds:species-exhausted": ("auto", 1.0),
    })

    db.update_image_keywords_for_image(iid, "birds,forest", source="auto", confidence_map={"forest": 0.6},
                                       scope="keywords")

    assert _rows(iid) == {
        "forest": ("auto", 0.6),
        "birds": ("localization_selection", 1.0),
        "travel": ("electron_ui", 1.0),
        "species:carolina wren": ("bioclip_region", 0.9),
        "birds:species-exhausted": ("auto", 1.0),
    }
    assert _legacy_csv(iid) == set(_rows(iid))


@pytest.mark.parametrize("scored", [False, True])
def test_tagging_write_keeps_species_and_hand_entered_keywords(scored):
    from types import SimpleNamespace

    from modules import tagging_image_processor as processor

    iid = _image()
    _seed(iid, {"birds": ("auto", 0.7), "urban": ("repair_legacy_keywords_junction", 1.0),
                "travel": ("electron_ui", 1.0), "species:Carolina Wren": ("bioclip_region", 0.9)})
    runner = SimpleNamespace(write_metadata=lambda *a, **kw: None)
    result = processor._InferenceResult(tags=["birds", "forest"], caption="", title="",
                                        confidence_map={"birds": 0.8, "forest": 0.6} if scored else {},
                                        relevance_map={})

    processor._write_outputs(runner, {"id": iid}, result, processing_path="/tmp/x.jpg",
                             original_path="/tmp/x.jpg", alt_text=None, extended_description=None,
                             write_keyword_relevance=scored, job_id=None)

    rows = _rows(iid)
    assert set(rows) == {"birds", "forest", "travel", "species:carolina wren"}
    assert rows["travel"] == ("electron_ui", 1.0)
    assert rows["species:carolina wren"] == ("bioclip_region", 0.9)


def test_keywords_run_keeps_birds_while_a_species_label_survives():
    iid = _image()
    _seed(iid, {"birds": ("auto", 0.7), "nature": ("auto", 0.7), "species:Carolina Wren": ("bioclip", 0.9)})

    db.update_image_keywords_for_image(iid, "forest", source="auto", scope="keywords")

    assert set(_rows(iid)) == {"forest", "birds", "species:carolina wren"}


def test_keywords_run_without_species_drops_birds():
    iid = _image()
    _seed(iid, {"birds": ("auto", 0.7), "travel": ("electron_ui", 1.0)})

    db.update_image_keywords_for_image(iid, "forest", source="auto", scope="keywords")

    assert set(_rows(iid)) == {"forest", "travel"}


def test_species_write_keeps_other_rows_source_and_confidence():
    iid = _image()
    _seed(iid, {"travel": ("electron_ui", 0.9), "birds": ("auto", 0.7),
                "species:Old Bird": ("bioclip", 0.8), "birds:species-exhausted": ("auto", 1.0)})

    db.update_image_keywords_for_image(
        iid, "travel,birds,species:New Bird", source="auto", confidence_map={"species:new bird": 0.95},
        source_map={"species:new bird": "bioclip_region"}, scope="species")

    assert _rows(iid) == {
        "travel": ("electron_ui", 0.9),
        "birds": ("auto", 0.7),
        "species:new bird": ("bioclip_region", 0.95),
    }


def test_species_abstention_clears_only_species_rows():
    iid = _image()
    _seed(iid, {"travel": ("electron_ui", 0.9), "birds": ("auto", 0.7), "species:Old Bird": ("bioclip", 0.8)})

    db.update_image_keywords_for_image(iid, "travel,birds", source="auto", scope="species")

    assert _rows(iid) == {"travel": ("electron_ui", 0.9), "birds": ("auto", 0.7)}


def test_full_edit_still_replaces_every_row():
    iid = _image()
    _seed(iid, {"travel": ("electron_ui", 0.9), "species:Old Bird": ("bioclip", 0.8)})

    db.update_image_keywords_for_image(iid, "nature", source="electron_ui")

    assert _rows(iid) == {"nature": ("electron_ui", 1.0)}
