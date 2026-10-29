"""Selection freshness is independent of whether its artifact is the current run.

Regression scenarios follow image-scoring-skills experiments/authority.py at
67584e376d1b84f8e2acd4d7a7b7e97519b6c415, adapted to backend source versions
and policy revocation. The backend remains the production authority.
"""
from dataclasses import dataclass

FRESHNESS_KEY = "localization.selection_freshness.enabled"


def freshness_enabled(conn):
    """Read the independently persisted runtime control; default off before migration."""
    try:
        row = conn.query_one("SELECT selection_freshness_enabled FROM localization_authority_control WHERE id=1")
        return bool(row and row.get("selection_freshness_enabled"))
    except Exception as exc:
        # Only an explicitly absent pre-migration schema defaults off. A
        # transient read failure must not make stale projections available.
        if getattr(exc, "sqlstate", None) in ("42P01", "42703"):
            return False
        raise


@dataclass(frozen=True)
class Freshness:
    usable: bool
    reason: str


def selection_freshness(selected_run, *, current_run=None, source=None, approval=None, managed=False):
    if not selected_run or selected_run.get("status") != "detected":
        return Freshness(False, "selected_artifact_missing")
    if selected_run.get("detector_key") != "bird" or selected_run.get("coord_space") != "display_normalized":
        return Freshness(False, "coordinate_space_unverified")
    if managed and (not approval or not approval.get("active")):
        return Freshness(False, "policy_revoked")
    source_hash, source_version = selected_run.get("source_hash"), selected_run.get("source_hash_version")
    for other in (current_run or {},):
        if (source_hash and other.get("source_hash") and
                (source_hash, source_version) != (other["source_hash"], other.get("source_hash_version"))):
            return Freshness(False, "source_changed")
        if (selected_run.get("rendition_hash") and other.get("rendition_hash")
                and selected_run["rendition_hash"] != other["rendition_hash"]):
            return Freshness(False, "rendition_changed")
    if source and source.get("status") == "available":
        if source_hash and (source_hash, source_version) != (source.get("hash"), source.get("version")):
            return Freshness(False, "source_changed")
    elif managed:
        return Freshness(False, "source_unavailable")
    if not source_hash or not source_version:
        return Freshness(not managed, "legacy_unverified" if not managed else "source_unavailable")
    return Freshness(True, "fresh")
