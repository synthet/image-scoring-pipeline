"""Tests for agent cull response schema validation."""

import json

from modules.agent_cull.schema import validate_agent_response, validate_raw_agent_response


def _valid_response(*, stack_id=1, sub_stack_id=None, rejected=(10,), picked=(11,)):
    return {
        "schema_version": "agent-cull-response-v1",
        "stack_id": stack_id,
        "sub_stack_id": sub_stack_id,
        "group_decision": "apply_removals",
        "confidence": 0.9,
        "summary": "Near duplicates.",
        "rejected_image_decisions": [
            {
                "image_id": rejected[0],
                "filename": "a.jpg",
                "decision": "remove",
                "confidence": 0.92,
                "reason": "Blurrier duplicate.",
                "better_alternatives": [picked[0]],
                "risk_flags": [],
            }
        ],
    }


def test_valid_response():
    data = _valid_response()
    result = validate_agent_response(
        data,
        stack_id=1,
        sub_stack_id=None,
        rejected_image_ids={10},
        picked_image_ids={11},
    )
    assert result.ok is True


def test_malformed_json():
    result = validate_raw_agent_response(
        "not json",
        stack_id=1,
        sub_stack_id=None,
        rejected_image_ids={10},
        picked_image_ids={11},
    )
    assert result.ok is False
    assert result.error_code == "malformed_json"


def test_wrong_rejected_count():
    data = _valid_response()
    result = validate_agent_response(
        data,
        stack_id=1,
        sub_stack_id=None,
        rejected_image_ids={10, 12},
        picked_image_ids={11},
    )
    assert result.ok is False


def test_alternative_not_picked():
    data = _valid_response()
    data["rejected_image_decisions"][0]["better_alternatives"] = [99]
    result = validate_agent_response(
        data,
        stack_id=1,
        sub_stack_id=None,
        rejected_image_ids={10},
        picked_image_ids={11},
    )
    assert result.ok is False


def test_markdown_fenced_json_parses():
    inner = _valid_response()
    raw = "```json\n" + json.dumps(inner) + "\n```"
    result = validate_raw_agent_response(
        raw,
        stack_id=1,
        sub_stack_id=None,
        rejected_image_ids={10},
        picked_image_ids={11},
    )
    assert result.ok is True


def test_optional_vision_fields_accepted():
    data = _valid_response()
    data["vision_used"] = True
    data["viewed_image_ids"] = [10, 11]
    result = validate_agent_response(
        data,
        stack_id=1,
        sub_stack_id=None,
        rejected_image_ids={10},
        picked_image_ids={11},
        all_image_ids={10, 11},
    )
    assert result.ok is True


def test_viewed_unknown_image_id_rejected():
    data = _valid_response()
    data["viewed_image_ids"] = [99]
    result = validate_agent_response(
        data,
        stack_id=1,
        sub_stack_id=None,
        rejected_image_ids={10},
        picked_image_ids={11},
        all_image_ids={10, 11},
    )
    assert result.ok is False
    assert any("viewed_unknown_image_id" in e for e in result.errors)


def _advisory(*, image_id=11, issue="misfocus", alts=(11,)):
    return {
        "image_id": image_id,
        "filename": "DSC_8825.NEF",
        "issue": issue,
        "confidence": 0.88,
        "reason": "Foreground fawn soft; adults sharp behind.",
        "suggested_alternatives": list(alts),
        "risk_flags": ["foreground_soft", "score_technical_mismatch"],
    }


def test_picked_advisory_valid():
    data = _valid_response(picked=(11, 12))
    data["picked_image_advisories"] = [_advisory(image_id=11, alts=(12,))]
    result = validate_agent_response(
        data,
        stack_id=1,
        sub_stack_id=None,
        rejected_image_ids={10},
        picked_image_ids={11, 12},
    )
    assert result.ok is True


def test_picked_advisory_image_must_be_picked():
    data = _valid_response()
    # 10 is rejected, not picked
    data["picked_image_advisories"] = [_advisory(image_id=10, alts=())]
    result = validate_agent_response(
        data,
        stack_id=1,
        sub_stack_id=None,
        rejected_image_ids={10},
        picked_image_ids={11},
    )
    assert result.ok is False
    assert any("advisory_image_not_picked" in e for e in result.errors)


def test_picked_advisory_suggested_must_be_picked():
    data = _valid_response()
    data["picked_image_advisories"] = [_advisory(image_id=11, alts=(99,))]
    result = validate_agent_response(
        data,
        stack_id=1,
        sub_stack_id=None,
        rejected_image_ids={10},
        picked_image_ids={11},
    )
    assert result.ok is False
    assert any("advisory_suggested_not_picked" in e for e in result.errors)


def test_picked_advisory_cannot_suggest_itself():
    data = _valid_response()
    data["picked_image_advisories"] = [_advisory(image_id=11, alts=(11,))]
    result = validate_agent_response(
        data,
        stack_id=1,
        sub_stack_id=None,
        rejected_image_ids={10},
        picked_image_ids={11},
    )
    assert result.ok is False
    assert any("advisory_suggested_self" in e for e in result.errors)


def test_picked_advisory_invalid_issue():
    data = _valid_response()
    data["picked_image_advisories"] = [_advisory(image_id=11, issue="banana", alts=())]
    result = validate_agent_response(
        data,
        stack_id=1,
        sub_stack_id=None,
        rejected_image_ids={10},
        picked_image_ids={11},
    )
    assert result.ok is False
    assert any("invalid_issue" in e for e in result.errors)


def test_picked_advisory_visual_issue_requires_viewed_when_enforced():
    data = _valid_response()
    data["vision_used"] = True
    data["viewed_image_ids"] = [10]  # picked 11 not viewed
    data["picked_image_advisories"] = [_advisory(image_id=11, alts=())]
    result = validate_agent_response(
        data,
        stack_id=1,
        sub_stack_id=None,
        rejected_image_ids={10},
        picked_image_ids={11},
        all_image_ids={10, 11},
        require_vision_evidence=True,
    )
    assert result.ok is False
    assert any("advisory_image_not_viewed" in e for e in result.errors)


def test_picked_audit_requires_vision_used_when_enforced():
    data = _valid_response()
    data["vision_used"] = False
    data["viewed_image_ids"] = [10, 11]
    data["picked_image_advisories"] = []
    result = validate_agent_response(
        data,
        stack_id=1,
        sub_stack_id=None,
        rejected_image_ids={10},
        picked_image_ids={11},
        all_image_ids={10, 11},
        require_vision_evidence=True,
    )
    assert result.ok is False
    assert any("picked_audit_vision_not_used" in e for e in result.errors)


def test_picked_audit_requires_every_pick_viewed_even_without_advisories():
    data = _valid_response(picked=(11, 12))
    data["vision_used"] = True
    data["viewed_image_ids"] = [10, 11]
    data["picked_image_advisories"] = []
    result = validate_agent_response(
        data,
        stack_id=1,
        sub_stack_id=None,
        rejected_image_ids={10},
        picked_image_ids={11, 12},
        all_image_ids={10, 11, 12},
        require_vision_evidence=True,
    )
    assert result.ok is False
    assert any("picked_audit_images_not_viewed:12" in e for e in result.errors)


def test_picked_advisory_other_issue_skips_viewed_rule():
    data = _valid_response()
    data["vision_used"] = True
    data["viewed_image_ids"] = [10, 11]
    data["picked_image_advisories"] = [_advisory(image_id=11, issue="other", alts=())]
    result = validate_agent_response(
        data,
        stack_id=1,
        sub_stack_id=None,
        rejected_image_ids={10},
        picked_image_ids={11},
        all_image_ids={10, 11},
        require_vision_evidence=True,
    )
    assert result.ok is True


def test_trailing_prose_after_json_parses():
    raw = json.dumps(_valid_response()) + "\n\nNote: this stack had soft foreground frames."
    result = validate_raw_agent_response(
        raw,
        stack_id=1,
        sub_stack_id=None,
        rejected_image_ids={10},
        picked_image_ids={11},
    )
    assert result.ok is True


# --- undeclared top-level keys (#747) -----------------------------------------

def _validate(data):
    return validate_agent_response(data, stack_id=1, sub_stack_id=None, rejected_image_ids={10}, picked_image_ids={11})


def test_undeclared_top_level_keys_are_dropped_and_recorded():
    data = _valid_response()
    data.update({"review_unit_key": "stack:1", "group_confidence": 0.8, "subject_focus_checks": []})
    result = _validate(data)
    assert result.ok is True
    assert result.stripped_keys == ["group_confidence", "review_unit_key", "subject_focus_checks"]
    assert "review_unit_key" not in result.data
    assert result.data["group_decision"] == "apply_removals"


def test_valid_reply_without_extras_strips_nothing():
    result = _validate(_valid_response())
    assert result.ok is True and result.stripped_keys == []


def test_missing_required_key_still_fails_even_with_extras_dropped():
    data = _valid_response()
    del data["group_decision"]
    data["review_unit_key"] = "stack:1"
    result = _validate(data)
    assert result.ok is False
    assert result.stripped_keys == ["review_unit_key"]


def test_undeclared_key_inside_a_decision_still_fails():
    data = _valid_response()
    data["rejected_image_decisions"][0]["extra_nested"] = True
    result = _validate(data)
    assert result.ok is False
    assert result.error_code == "schema_invalid"
