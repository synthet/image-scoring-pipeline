"""Durable observation metadata. This module has no production selection writer."""
from dataclasses import asdict
import hashlib
import json

from modules.localization_authority_inputs import load_inputs
from modules.localization_evaluation import ArtifactScope, R2_RULE_ID, R2_RULE_SHA256, evaluate_r2


def fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False, default=str).encode()).hexdigest()


class AuthorityStore:
    def __init__(self, connector=None):
        if connector is None:
            from modules import db
            connector = db.get_connector()
        self.conn = connector

    def register_policy(self, rule_bytes: bytes, scope: ArtifactScope) -> str:
        if hashlib.sha256(rule_bytes).hexdigest() != R2_RULE_SHA256:
            raise ValueError("frozen R2 rule hash mismatch")
        if any(not isinstance(value, str) or not value.strip() for value in asdict(scope).values()):
            raise ValueError("complete producer scope required")
        # Scope is part of this observation-policy identity. The registered
        # protocol hash alone never grants authority to a new combination.
        key = fingerprint({"schema": "r2-shadow-observation/1", "rule": R2_RULE_SHA256,
                           "scope": asdict(scope)})

        def register(tx):
            tx.query_one("SELECT id FROM localization_authority_control WHERE id=1 FOR UPDATE")
            added = tx.execute(
                "INSERT INTO localization_authority_policies (policy_hash,rule_id,rule_sha256,scope) "
                "VALUES (?,?,?,?::jsonb) ON CONFLICT DO NOTHING",
                (key, R2_RULE_ID, R2_RULE_SHA256, json.dumps(asdict(scope))),
            )
            if added:
                tx.execute("UPDATE localization_authority_control SET revision=revision+1,scan_cursor=0 WHERE id=1")
            return key
        return self.conn.run_transaction(register)

    def set_mode(self, mode: str):
        if mode not in ("off", "shadow"):
            raise ValueError("mode must be off or shadow; active authority is not implemented")
        self.conn.execute(
            "UPDATE localization_authority_control SET mode=?,revision=revision+1,scan_cursor=0,"
            "updated_at=clock_timestamp() WHERE id=1 AND mode<>?", (mode, mode),
        )

    def control(self):
        return self.conn.query_one("SELECT * FROM localization_authority_control WHERE id=1")

    def policies(self):
        return self.conn.query("SELECT policy_hash FROM localization_authority_policies ORDER BY policy_hash")

    def scan_batch(self, limit=100):
        """Keep a finite sweep watermark so sustained ingestion cannot starve old images."""
        limit = max(1, min(int(limit), 100))

        def scan(tx):
            control = tx.query_one("SELECT * FROM localization_authority_control WHERE id=1 FOR UPDATE")
            if not control or control["mode"] != "shadow":
                return []
            upper = control["scan_upper_bound"]
            if not upper:
                upper = tx.query_one("SELECT COALESCE(MAX(id),0) AS id FROM image_localization_runs")["id"]
                tx.execute("UPDATE localization_authority_control SET scan_upper_bound=? WHERE id=1", (upper,))
            rows = tx.query(
                "SELECT r.id,r.image_id,i.file_path FROM image_localization_runs r "
                "JOIN images i ON i.id=r.image_id WHERE r.id>? AND r.id<=? "
                "AND r.detector_key='bird' AND r.is_current ORDER BY r.id LIMIT ?",
                (control["scan_cursor"], upper, limit),
            )
            if not rows:
                tx.execute("UPDATE localization_authority_control SET scan_cursor=0,scan_upper_bound=0 WHERE id=1")
            for row in rows:
                row["scan_revision"] = control["revision"]
                row["scan_cursor"] = control["scan_cursor"]
                row["scan_upper_bound"] = upper
            return rows
        return self.conn.run_transaction(scan)

    def finish_scan(self, rows):
        if not rows:
            return
        last = rows[-1]
        done = last["id"] >= last["scan_upper_bound"]
        self.conn.execute(
            "UPDATE localization_authority_control SET scan_cursor=?,scan_upper_bound=? "
            "WHERE id=1 AND revision=? AND scan_cursor=? AND scan_upper_bound=?",
            (0 if done else last["id"], 0 if done else last["scan_upper_bound"],
             last["scan_revision"], last["scan_cursor"], last["scan_upper_bound"]),
        )

    def scan_allowed(self, image_id, policy_hash, input_hash):
        row = self.conn.query_one(
            "SELECT status,retry_at<=clock_timestamp() AS due FROM localization_authority_scan_faults "
            "WHERE image_id=? AND policy_hash=? AND input_fingerprint=?", (image_id, policy_hash, input_hash),
        )
        return not row or row["status"] == "recovered" or (row["status"] == "waiting" and row["due"])

    def record_scan_fault(self, image_id, policy_hash, input_hash, error_code):
        self.conn.execute(
            "INSERT INTO localization_authority_scan_faults (image_id,policy_hash,input_fingerprint,error_code) "
            "VALUES (?,?,?,?) ON CONFLICT (image_id,policy_hash,input_fingerprint) DO UPDATE "
            "SET attempts=localization_authority_scan_faults.attempts+1,"
            "status=CASE WHEN localization_authority_scan_faults.attempts>=2 THEN 'exhausted' ELSE 'waiting' END,"
            "retry_at=clock_timestamp()+interval '300 seconds',error_code=EXCLUDED.error_code",
            (image_id, policy_hash, input_hash, error_code),
        )

    def recover_scan(self, image_id, policy_hash, input_hash):
        self.conn.execute(
            "UPDATE localization_authority_scan_faults SET status='recovered' WHERE image_id=? "
            "AND policy_hash=? AND input_fingerprint=? AND status='waiting'", (image_id, policy_hash, input_hash),
        )

    def claim_input(self, claim):
        return self.conn.query_one(
            "SELECT e.image_id,i.file_path FROM localization_authority_evaluations e "
            "JOIN images i ON i.id=e.image_id WHERE e.id=?", (claim["evaluation_id"],),
        )

    def diagnostics(self):
        control = self.control()
        if control is None:
            return {"availability": "unavailable", "reason": "authority_schema_uninitialized"}
        work = self.conn.query_one(
            "SELECT count(*) FILTER (WHERE status<>'completed') AS pending,"
            "COALESCE(MAX(EXTRACT(EPOCH FROM clock_timestamp()-created_at)) "
            "FILTER (WHERE status<>'completed'),0) AS oldest_seconds,"
            "COALESCE(SUM(fenced_rejections),0) AS fenced_rejections FROM localization_authority_attempts",
        )
        proposals = self.conn.query(
            "SELECT proposal->>'species_action' AS action,count(*) AS count FROM localization_authority_attempts "
            "WHERE disposition='proposed' GROUP BY proposal->>'species_action'",
        )
        return {
            "availability": "available", "mode": control["mode"], "revision": control["revision"],
            "scan_cursor": control["scan_cursor"], "scan_upper_bound": control["scan_upper_bound"],
            "reservation_inventory_verified": bool(control["reservation_inventory_sha256"]),
            "reserved_images": self.conn.query_one("SELECT count(DISTINCT image_id) AS n FROM localization_authority_reservations")["n"],
            "pending": work["pending"], "oldest_pending_seconds": float(work["oldest_seconds"]),
            "fenced_write_rejections": work["fenced_rejections"],
            "decisions": self.conn.query("SELECT outcome,reason,count(*) AS count FROM localization_authority_evaluations GROUP BY outcome,reason"),
            "applications": self.conn.query("SELECT disposition,count(*) AS count FROM localization_authority_attempts GROUP BY disposition"),
            "reservation_conflicts": self.conn.query_one(
                "SELECT count(*) AS n FROM localization_authority_attempts WHERE proposal->>'application_blocked'='image_reserved'",
            )["n"],
            "scan_faults": self.conn.query("SELECT status,error_code,count(*) AS count FROM localization_authority_scan_faults GROUP BY status,error_code"),
            "proposed_actions": {row["action"]: row["count"] for row in proposals},
            "proposed_geometry_actions": self.conn.query(
                "SELECT proposal->>'geometry_action' AS action,count(*) AS count FROM localization_authority_attempts "
                "WHERE disposition='proposed' GROUP BY proposal->>'geometry_action'",
            ),
            "authority_granted": False,
        }

    def observe(self, image_id, policy_hash, *, source_observation=None):
        """Cache evaluation once and enqueue a revision-specific proposal atomically."""
        def observe(tx):
            control = tx.query_one("SELECT * FROM localization_authority_control WHERE id=1 FOR SHARE")
            if not control or control["mode"] != "shadow":
                return None
            policy = tx.query_one(
                "SELECT * FROM localization_authority_policies WHERE policy_hash=? FOR SHARE", (policy_hash,),
            )
            if policy is None:
                raise ValueError("unknown observation policy")
            snapshot = load_inputs(tx, image_id, source_observation, control["reservation_inventory_sha256"])
            if snapshot is None:
                return None
            components = snapshot["components"]
            tx.execute(
                "INSERT INTO localization_authority_observations (image_id,components) "
                "VALUES (?,?::jsonb) ON CONFLICT DO NOTHING", (image_id, json.dumps(components)),
            )
            observed = tx.query_one(
                "SELECT * FROM localization_authority_observations WHERE image_id=? FOR UPDATE", (image_id,),
            )
            if observed["components"] != components:
                increments = []
                for name in ("authority", "discovery", "ownership", "source", "reservation"):
                    if observed["components"][name] != components[name]:
                        # Names are fixed above, never supplied by an input.
                        increments.append(f"{name}_revision={name}_revision+1")
                observed = tx.query_one(
                    "UPDATE localization_authority_observations SET revision=revision+1,"
                    "components=?::jsonb,updated_at=clock_timestamp()," + ",".join(increments) +
                    " WHERE image_id=? RETURNING *", (json.dumps(components), image_id),
                )
            artifact_hash = fingerprint({"run": snapshot["run"], "regions": snapshot["regions"]})
            evaluation = tx.query_one(
                "SELECT * FROM localization_authority_evaluations WHERE policy_hash=? AND artifact_fingerprint=?",
                (policy_hash, artifact_hash),
            )
            if evaluation is None:
                result = evaluate_r2(snapshot["run"], snapshot["regions"],
                                     scope=ArtifactScope(**policy["scope"]), **snapshot["population"])
                tx.execute(
                    "INSERT INTO localization_authority_evaluations "
                    "(policy_hash,image_id,run_id,artifact_fingerprint,outcome,reason,result,population_snapshot) "
                    "VALUES (?,?,?,?,?,?,?::jsonb,?::jsonb) ON CONFLICT DO NOTHING",
                    (policy_hash, image_id, snapshot["run"]["id"], artifact_hash, result.status,
                     result.reason, json.dumps(asdict(result)), json.dumps(snapshot["population"])),
                )
                evaluation = tx.query_one(
                    "SELECT * FROM localization_authority_evaluations WHERE policy_hash=? AND artifact_fingerprint=?",
                    (policy_hash, artifact_hash),
                )
            context = {key: observed[key] for key in (
                "authority_revision", "discovery_revision", "ownership_revision", "source_revision", "reservation_revision",
            )}
            context.update(control_revision=control["revision"], approval_revision=policy["approval_revision"],
                           observation_revision=observed["revision"], components_hash=fingerprint(components))
            context_hash = fingerprint(context)
            tx.execute(
                "INSERT INTO localization_authority_attempts (evaluation_id,context_hash,context) "
                "VALUES (?,?,?::jsonb) ON CONFLICT DO NOTHING",
                (evaluation["id"], context_hash, json.dumps(context)),
            )
            attempt = tx.query_one(
                "SELECT id FROM localization_authority_attempts WHERE evaluation_id=? AND context_hash=?",
                (evaluation["id"], context_hash),
            )
            return {"evaluation_id": evaluation["id"], "attempt_id": attempt["id"], "outcome": evaluation["outcome"]}
        return self.conn.run_transaction(observe)

    def claim_next(self):
        def claim(tx):
            tx.execute(
                "UPDATE localization_authority_attempts SET status='completed',disposition='retry_exhausted',"
                "completed_at=clock_timestamp(),lease_until=NULL WHERE status='running' "
                "AND lease_until<=clock_timestamp() AND attempts>=3",
            )
            return tx.query_one(
                "WITH picked AS (SELECT id FROM localization_authority_attempts "
                "WHERE attempts<3 AND available_at<=clock_timestamp() AND "
                "EXISTS (SELECT 1 FROM localization_authority_control WHERE id=1 AND mode='shadow') AND "
                "(status='queued' OR (status='running' AND lease_until<=clock_timestamp())) "
                "ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1) "
                "UPDATE localization_authority_attempts w SET status='running',"
                "fencing_token=w.fencing_token+1,attempts=w.attempts+1,"
                "lease_until=clock_timestamp()+interval '60 seconds' FROM picked WHERE w.id=picked.id RETURNING w.*",
            )
        return self.conn.run_transaction(claim)

    def renew(self, claim):
        return bool(self.conn.execute(
            "UPDATE localization_authority_attempts SET lease_until=clock_timestamp()+interval '60 seconds' "
            "WHERE id=? AND fencing_token=? AND status='running' AND lease_until>clock_timestamp()",
            (claim["id"], claim["fencing_token"]),
        ))

    def fail(self, claim, error_code):
        """Only live workers can retry; faults have a three-attempt 60/300s budget."""
        return bool(self.conn.execute(
            "UPDATE localization_authority_attempts SET "
            "status=CASE WHEN attempts>=3 THEN 'completed' ELSE 'queued' END,"
            "disposition=CASE WHEN attempts>=3 THEN 'retry_exhausted' ELSE NULL END,"
            "completed_at=CASE WHEN attempts>=3 THEN clock_timestamp() ELSE NULL END,"
            "available_at=clock_timestamp()+CASE WHEN attempts=1 THEN interval '60 seconds' ELSE interval '300 seconds' END,"
            "lease_until=NULL,last_error=? WHERE id=? AND fencing_token=? AND status='running' "
            "AND lease_until>clock_timestamp()", (error_code, claim["id"], claim["fencing_token"]),
        ))

    def complete(self, claim, *, source_observation=None):
        """Publish metadata only, serialized against mode and observed-input changes.

        Lock order: control -> policy -> image -> observation/work/lineage.
        Claim-only transactions finish before this transaction begins.
        """
        def complete(tx):
            evaluation = tx.query_one(
                "SELECT e.* FROM localization_authority_evaluations e "
                "JOIN localization_authority_attempts a ON a.evaluation_id=e.id WHERE a.id=?", (claim["id"],),
            )
            if evaluation is None:
                return False
            control = tx.query_one("SELECT * FROM localization_authority_control WHERE id=1 FOR SHARE")
            policy = tx.query_one(
                "SELECT * FROM localization_authority_policies WHERE policy_hash=? FOR SHARE",
                (evaluation["policy_hash"],),
            )
            snapshot = load_inputs(tx, evaluation["image_id"], source_observation,
                                   control["reservation_inventory_sha256"])
            observation = tx.query_one(
                "SELECT revision FROM localization_authority_observations WHERE image_id=? FOR SHARE",
                (evaluation["image_id"],),
            )
            work = tx.query_one(
                "SELECT *,lease_until>clock_timestamp() AS live FROM localization_authority_attempts WHERE id=? FOR UPDATE",
                (claim["id"],),
            )
            if not work or work["status"] != "running" or not work["live"] or work["fencing_token"] != claim["fencing_token"]:
                if work:
                    tx.execute("UPDATE localization_authority_attempts SET fenced_rejections=fenced_rejections+1 WHERE id=?", (claim["id"],))
                return False
            context = work["context"]
            current = bool(snapshot and control["mode"] == "shadow"
                           and observation and context["observation_revision"] == observation["revision"]
                           and context["control_revision"] == control["revision"]
                           and context["approval_revision"] == policy["approval_revision"]
                           and context["components_hash"] == fingerprint(snapshot["components"])
                           and evaluation["artifact_fingerprint"] == fingerprint(
                               {"run": snapshot["run"], "regions": snapshot["regions"]}))
            proposal = self._proposal(evaluation, snapshot) if current else None
            updated = tx.execute(
                "UPDATE localization_authority_attempts SET status='completed',disposition=?,proposal=?::jsonb,"
                "completed_at=clock_timestamp(),lease_until=NULL WHERE id=? AND fencing_token=? "
                "AND status='running' AND lease_until>clock_timestamp()",
                ("proposed" if current else "superseded", json.dumps(proposal), claim["id"], claim["fencing_token"]),
            )
            if not updated or not current:
                return False
            tx.execute(
                "INSERT INTO localization_authority_lineage (attempt_id,image_id,input_state,proposed_action) "
                "VALUES (?,?,?::jsonb,?)",
                (claim["id"], evaluation["image_id"], json.dumps(snapshot["components"]), proposal["species_action"]),
            )
            return True
        return self.conn.run_transaction(complete)

    @staticmethod
    def _proposal(evaluation, snapshot):
        result = evaluation["result"]
        components = snapshot["components"]
        reservation = components["reservation"]
        blocked = ("image_reserved" if reservation["images"] else
                   "reservation_inventory_unverified" if not reservation["inventory_hash"] else "policy_unqualified")
        source = components["source"]
        run = snapshot["run"]
        fresh = (source.get("status") == "available" and source.get("hash") == run["source_hash"]
                 and source.get("version") == run["source_hash_version"])
        population = snapshot["population"]
        if not fresh:
            action = "preserve" if population["has_active_selection"] else "none"
        elif population["has_active_selection"]:
            action = "preserve"
        elif result["species_eligible"] and population["bird_tagged"]:
            action = "classify"
        else:
            action = "none"
        propose_selection = bool(fresh and result["geometry_eligible"] and population["bird_tagged"]
                                 and not population["has_active_selection"])
        geometry_action = ("refresh_artifact" if not fresh else "propose_selection" if propose_selection
                           else "preserve_selection" if population["has_active_selection"] else "none")
        blockers = ["shadow_mode", "policy_unqualified"]
        if blocked != "policy_unqualified":
            blockers.append(blocked)
        return {"evaluation": result, "species_action": action, "outputs_protected": True,
                "source_current": fresh, "application_blocked": blocked,
                "application_blockers": blockers, "geometry_action": geometry_action,
                "propose_selection": propose_selection,
                "authority_granted": False}
