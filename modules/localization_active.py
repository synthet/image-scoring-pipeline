"""Serialized active authority. Callers must hold explicit scoped qualification."""
import json

from modules.localization_authority_inputs import load_inputs
from modules.localization_authority_store import AuthorityStore, fingerprint
from modules.localization_policy_approval import validate_qualification
from modules.localization_selection import revoke_selection, select_region


class StaleLease(RuntimeError):
    pass


class ActiveAuthority:
    def __init__(self, store=None):
        self.store = store or AuthorityStore()
        self.conn = self.store.conn

    def set_freshness(self, enabled):
        def apply(tx):
            control = tx.query_one("SELECT * FROM localization_authority_control WHERE id=1 FOR UPDATE")
            if not enabled and control["mode"] == "active":
                raise ValueError("disable active applications before freshness protection")
            tx.execute("UPDATE localization_authority_control SET selection_freshness_enabled=?,revision=revision+1,scan_cursor=0 WHERE id=1",
                       (bool(enabled),))
        self.conn.run_transaction(apply)

    def activate(self, policy_hash, qualification_sha256, *, confirmed=False):
        if not confirmed:
            raise ValueError("explicit activation confirmation required")
        def apply(tx):
            control = tx.query_one("SELECT * FROM localization_authority_control WHERE id=1 FOR UPDATE")
            if not control["selection_freshness_enabled"] or not control["reservation_inventory_sha256"]:
                raise ValueError("freshness protection and verified reservation inventory required")
            if not tx.query_one(
                "SELECT policy_hash FROM localization_policy_approvals WHERE policy_hash=? "
                "AND qualification_sha256=? AND active AND geometry_allowed FOR SHARE",
                (policy_hash,qualification_sha256),
            ):
                raise ValueError("no qualified policy")
            tx.execute("UPDATE localization_authority_control SET mode='active',revision=revision+1,scan_cursor=0 WHERE id=1")
        self.conn.run_transaction(apply)

    def approve(self, policy_hash, path, expected_sha256, actor, *, confirmed=False):
        if not confirmed or not actor or not actor.strip():
            raise ValueError("explicit identified approval required")
        policy = self.conn.query_one("SELECT * FROM localization_authority_policies WHERE policy_hash=?", (policy_hash,))
        if not policy:
            raise ValueError("unknown policy")
        receipt = validate_qualification(path, expected_sha256, policy)
        def apply(tx):
            tx.query_one("SELECT id FROM localization_authority_control WHERE id=1 FOR UPDATE")
            tx.query_one("SELECT policy_hash FROM localization_authority_policies WHERE policy_hash=? FOR UPDATE", (policy_hash,))
            prior = tx.query_one("SELECT revision FROM localization_policy_approvals WHERE policy_hash=? FOR UPDATE", (policy_hash,))
            revision = (prior["revision"] if prior else 0) + 1
            tx.execute(
                "INSERT INTO localization_policy_approvals (policy_hash,revision,active,geometry_allowed,species_allowed,"
                "qualification_sha256,receipt,approved_by) VALUES (?,?,TRUE,TRUE,?,?,?::jsonb,?) "
                "ON CONFLICT (policy_hash) DO UPDATE SET revision=EXCLUDED.revision,active=TRUE,geometry_allowed=TRUE,"
                "species_allowed=EXCLUDED.species_allowed,qualification_sha256=EXCLUDED.qualification_sha256,"
                "receipt=EXCLUDED.receipt,approved_by=EXCLUDED.approved_by,updated_at=clock_timestamp()",
                (policy_hash, revision, receipt.get("species_allowed") is True, expected_sha256, json.dumps(receipt), actor),
            )
            tx.execute("INSERT INTO localization_policy_events (policy_hash,revision,action,evidence) VALUES (?,?,'approve',?::jsonb)",
                       (policy_hash, revision, json.dumps({"sha256": expected_sha256, "actor": actor})))
            tx.execute("UPDATE localization_authority_control SET revision=revision+1,scan_cursor=0 WHERE id=1")
        self.conn.run_transaction(apply)

    def revoke_policy(self, policy_hash, reason):
        if not reason or not reason.strip():
            raise ValueError("revocation reason required")
        def apply(tx):
            tx.query_one("SELECT id FROM localization_authority_control WHERE id=1 FOR UPDATE")
            row = tx.query_one("SELECT * FROM localization_policy_approvals WHERE policy_hash=? FOR UPDATE", (policy_hash,))
            if not row or not row["active"]:
                return False
            revision = row["revision"] + 1
            tx.execute("UPDATE localization_policy_approvals SET active=FALSE,revision=?,updated_at=clock_timestamp() WHERE policy_hash=?",
                       (revision, policy_hash))
            tx.execute("INSERT INTO localization_policy_events (policy_hash,revision,action,evidence) VALUES (?,?,'revoke',?::jsonb)",
                       (policy_hash, revision, json.dumps({"reason": reason})))
            tx.execute(
                "INSERT INTO localization_change_journal (image_id,kind,resource_key,owner_context,payload) "
                "SELECT s.image_id,'authority',s.id::text,'policy-revocation',?::jsonb FROM localization_selection_lineage l "
                "JOIN image_localization_selections s ON s.id=l.selection_id WHERE l.policy_hash=? AND s.revoked_at IS NULL",
                (json.dumps({"reason": reason, "approval_revision": revision}), policy_hash),
            )
            tx.execute("UPDATE localization_authority_control SET revision=revision+1,scan_cursor=0 WHERE id=1")
            return True
        return self.conn.run_transaction(apply)

    @staticmethod
    def _finish(tx, claim, disposition, result):
        count = tx.execute(
            "UPDATE localization_authority_attempts SET status='completed',disposition=?,proposal=?::jsonb,"
            "completed_at=clock_timestamp(),lease_until=NULL WHERE id=? AND status='running' "
            "AND fencing_token=? AND lease_until>clock_timestamp()",
            (disposition, json.dumps(result), claim["id"], claim["fencing_token"]),
        )
        if not count:
            raise StaleLease("publication lease expired")

    def apply_claim(self, claim, *, source_observation):
        def apply(tx):
            evaluation = tx.query_one(
                "SELECT e.* FROM localization_authority_evaluations e JOIN localization_authority_attempts w "
                "ON w.evaluation_id=e.id WHERE w.id=?", (claim["id"],),
            )
            if not evaluation:
                return False
            control = tx.query_one("SELECT * FROM localization_authority_control WHERE id=1 FOR SHARE")
            policy = tx.query_one("SELECT * FROM localization_authority_policies WHERE policy_hash=? FOR SHARE", (evaluation["policy_hash"],))
            approval = tx.query_one("SELECT * FROM localization_policy_approvals WHERE policy_hash=? FOR SHARE", (evaluation["policy_hash"],))
            tx.query_one("SELECT id FROM images WHERE id=? FOR UPDATE", (evaluation["image_id"],))
            snapshot = load_inputs(tx, evaluation["image_id"], source_observation, control["reservation_inventory_sha256"])
            observed = tx.query_one("SELECT revision FROM localization_authority_observations WHERE image_id=? FOR SHARE", (evaluation["image_id"],))
            work = tx.query_one("SELECT *,lease_until>clock_timestamp() AS live FROM localization_authority_attempts WHERE id=? FOR UPDATE", (claim["id"],))
            if not work or not work["live"] or work["status"] != "running" or work["fencing_token"] != claim["fencing_token"]:
                if work:
                    tx.execute("UPDATE localization_authority_attempts SET fenced_rejections=fenced_rejections+1 WHERE id=?", (claim["id"],))
                return False
            context = work["context"]
            reason = None
            if control["mode"] != "active" or not control["selection_freshness_enabled"]:
                reason = "inactive"
            elif not approval or not approval["active"] or not approval["geometry_allowed"]:
                reason = "policy_unqualified"
            elif context["control_revision"] != control["revision"] or context["approval_revision"] != approval["revision"]:
                reason = "superseded"
            elif not observed or observed["revision"] != context["observation_revision"] or not snapshot:
                reason = "superseded"
            elif (fingerprint(snapshot["components"]) != context["components_hash"] or
                  fingerprint({"run": snapshot["run"], "regions": snapshot["regions"]}) != evaluation["artifact_fingerprint"]):
                reason = "input_changed"
            elif snapshot["components"]["reservation"]["images"]:
                reason = "image_reserved"
            elif not control["reservation_inventory_sha256"]:
                reason = "reservation_inventory_unverified"
            elif evaluation["outcome"] != "accept":
                reason = evaluation["outcome"]
            elif policy["rule_kind"] == "r2" and (
                    not snapshot["population"]["bird_tagged"] or snapshot["population"]["has_active_selection"]):
                # Evaluation caching never freezes application eligibility.
                reason = "outside_original_population"
            elif not (source_observation.get("status") == "available" and
                      (source_observation.get("hash"), source_observation.get("version")) ==
                      (snapshot["run"]["source_hash"], snapshot["run"]["source_hash_version"])):
                reason = "source_changed"
            elif evaluation["result"]["band"] not in approval["receipt"].get("geometry_bands", []):
                reason = "band_unqualified"
            if reason:
                self._finish(tx, claim, reason, {"authority_granted": False})
                return False
            iid = evaluation["image_id"]
            selection = snapshot["components"]["authority"]["selection"]
            baseline = snapshot["components"]["authority"]["projection"]
            tx.execute("SELECT set_config('vexlum.authority_publication',?,TRUE)", (f"authority:{claim['id']}",))
            if selection:
                owned = tx.query_one("SELECT * FROM localization_selection_lineage WHERE selection_id=?", (selection["id"],))
                edit = tx.query_one(
                    "SELECT owner_context FROM localization_change_journal WHERE image_id=? AND kind='authority' "
                    "AND payload->>'table'='images' ORDER BY id DESC LIMIT 1", (iid,),
                )
                if (not owned or policy["rule_kind"] != "runtime" or baseline != selection["projected_bird_bbox"]
                        or not edit or not (edit["owner_context"] or "").startswith("authority:")):
                    self._finish(tx, claim, "ownership_conflict", {"authority_granted": False})
                    return False
                if (selection["region_id"] == evaluation["result"]["region_id"]
                        and owned["policy_hash"] == evaluation["policy_hash"]
                        and owned["approval_revision"] == approval["revision"]):
                    self._finish(tx, claim, "already_applied", {"authority_granted": True})
                    return False
                baseline = owned["baseline_bird_bbox"]
                revoke_selection(iid, "policy-owned replacement", transaction=tx)
            tx.execute(
                "INSERT INTO localization_discovery_state (image_id,legacy_positive,selection_only) "
                "VALUES (?,?,?) ON CONFLICT DO NOTHING",
                (iid, snapshot["population"]["bird_tagged"], not snapshot["population"]["bird_tagged"]),
            )
            result = select_region(iid, evaluation["result"]["region_id"],
                                   "authority:" + evaluation["policy_hash"],
                                   {"approval_revision": approval["revision"]}, expect_bird_bbox=baseline, transaction=tx)
            if result["status"] != "selected":
                raise RuntimeError("atomic selection publication rejected: " + result["status"])
            tx.execute(
                "INSERT INTO localization_selection_lineage (selection_id,policy_hash,approval_revision,baseline_bird_bbox,"
                "source_hash,source_hash_version,rendition_hash) VALUES (?,?,?,?::jsonb,?,?,?)",
                (result["selection_id"], evaluation["policy_hash"], approval["revision"], json.dumps(baseline),
                 snapshot["run"]["source_hash"], snapshot["run"]["source_hash_version"], snapshot["run"]["rendition_hash"]),
            )
            self._finish(tx, claim, "applied", {**result, "authority_granted": True})
            return True
        try:
            return self.conn.run_transaction(apply)
        except StaleLease:
            return False

    def cleanup_invalid(self, limit=100):
        """Bounded policy-owned rollback runs even while authority is off."""
        candidates = self.conn.query(
            "SELECT s.id,s.image_id,l.policy_hash FROM image_localization_selections s "
            "JOIN localization_selection_lineage l ON l.selection_id=s.id "
            "LEFT JOIN localization_policy_approvals a ON a.policy_hash=l.policy_hash "
            "WHERE s.revoked_at IS NULL AND (a.active IS NOT TRUE OR a.revision<>l.approval_revision "
            "OR NOT localization_selection_is_fresh(s.id)) ORDER BY s.id LIMIT ?",
            (max(1,min(int(limit),100)),),
        )
        count = 0
        for candidate in candidates:
            def cleanup(tx):
                tx.query_one("SELECT id FROM localization_authority_control WHERE id=1 FOR SHARE")
                tx.query_one("SELECT policy_hash FROM localization_authority_policies WHERE policy_hash=? FOR SHARE", (candidate["policy_hash"],))
                approval = tx.query_one("SELECT * FROM localization_policy_approvals WHERE policy_hash=? FOR SHARE", (candidate["policy_hash"],))
                tx.query_one("SELECT id FROM images WHERE id=? FOR UPDATE", (candidate["image_id"],))
                selection = tx.query_one(
                    "SELECT s.*,l.approval_revision,localization_selection_is_fresh(s.id) AS fresh "
                    "FROM image_localization_selections s JOIN localization_selection_lineage l ON l.selection_id=s.id "
                    "WHERE s.id=? AND s.revoked_at IS NULL FOR UPDATE OF s", (candidate["id"],),
                )
                if not selection or (approval and approval["active"] and approval["revision"] == selection["approval_revision"] and selection["fresh"]):
                    return False
                edit = tx.query_one(
                    "SELECT owner_context FROM localization_change_journal WHERE image_id=? AND kind='authority' "
                    "AND payload->>'table'='images' ORDER BY id DESC LIMIT 1", (candidate["image_id"],),
                )
                tx.execute("SELECT set_config('vexlum.authority_publication','authority:cleanup',TRUE)")
                if edit and (edit["owner_context"] or "").startswith("authority:"):
                    revoke_selection(candidate["image_id"], "authority invalidated", transaction=tx)
                else:
                    # An explicit external projection edit transfers ownership,
                    # including an assignment of the same JSON value.
                    tx.execute("UPDATE image_localization_selections SET revoked_at=clock_timestamp(),revoked_reason='external projection preserved' WHERE id=?", (candidate["id"],))
                return True
            count += int(self.conn.run_transaction(cleanup))
        return count
