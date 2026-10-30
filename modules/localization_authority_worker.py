"""Independent CPU-only shadow authority worker; never schedules inference."""
from copy import deepcopy
import logging
import threading

from modules.localization_authority_store import AuthorityStore, fingerprint

logger = logging.getLogger(__name__)
_DIAGNOSTIC_LOCK = threading.Lock()
_DIAGNOSTICS = {"running": False, "availability": "not_started", "authority_granted": False}


def get_diagnostic_state():
    with _DIAGNOSTIC_LOCK:
        return deepcopy(_DIAGNOSTICS)


def observe_source(path):
    from modules.rendition import source_identity
    try:
        digest, version = source_identity(path)
        return {"status": "available", "hash": digest, "version": version}
    except OSError:
        return {"status": "unreadable"}


class ShadowAuthorityWorker:
    def __init__(self, store=None, *, batch_size=100, poll_interval=5.0):
        self._store = store
        self.batch_size = max(1, min(int(batch_size), 100))
        self.poll_interval = max(0.1, float(poll_interval))
        self._stop = threading.Event()
        self._thread = None

    @property
    def store(self):
        if self._store is None:
            self._store = AuthorityStore()
        return self._store

    def _publish_diagnostics(self, **extra):
        data = self.store.diagnostics()
        data.update(running=bool(self._thread and self._thread.is_alive()), **extra)
        with _DIAGNOSTIC_LOCK:
            _DIAGNOSTICS.clear()
            _DIAGNOSTICS.update(data)

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="localization-authority", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        with _DIAGNOSTIC_LOCK:
            _DIAGNOSTICS["running"] = bool(self._thread and self._thread.is_alive())

    def _run(self):
        failures = 0
        while not self._stop.is_set():
            try:
                self.poll_once()
                failures = 0
                delay = self.poll_interval
            except Exception as exc:
                failures += 1
                # Infrastructure outages cannot be written to an unavailable DB.
                # Retain a diagnostic and retry slowly; per-image faults below
                # have a durable terminal budget instead of an infinite loop.
                delay = 60 if failures == 1 else 300
                with _DIAGNOSTIC_LOCK:
                    _DIAGNOSTICS.update(availability="unavailable", error_code=type(exc).__name__,
                                        retry_seconds=delay, running=True)
                logger.warning("Authority observation unavailable (%s); retry in %ss", type(exc).__name__, delay)
            self._stop.wait(delay)

    def _complete_with_heartbeat(self, claim):
        finished = threading.Event()

        def renew():
            while not finished.wait(20):
                try:
                    if not self.store.renew(claim):
                        return
                except Exception:
                    logger.warning("Authority lease renewal failed", exc_info=True)
                    return
        heartbeat = threading.Thread(target=renew, name="authority-lease", daemon=True)
        heartbeat.start()
        try:
            item = self.store.claim_input(claim)
            source = observe_source(item["file_path"]) if item else {"status": "unreadable"}
            if self.store.control()["mode"] == "active":
                from modules.localization_active import ActiveAuthority
                return ActiveAuthority(self.store).apply_claim(claim, source_observation=source)
            return self.store.complete(claim, source_observation=source)
        finally:
            finished.set()
            heartbeat.join(timeout=1)

    def poll_once(self):
        control = self.store.control()
        if not control:
            raise RuntimeError("authority schema unavailable")
        if control.get("selection_freshness_enabled") and control["mode"] != "shadow":
            from modules.localization_active import ActiveAuthority
            ActiveAuthority(self.store).cleanup_invalid(limit=self.batch_size)
        if control["mode"] not in ("shadow", "active"):
            self._publish_diagnostics(scanned=0, completed=0)
            return 0
        rows = self.store.scan_batch(self.batch_size)
        if rows:
            policies = self.store.policies()
            for row in rows:
                if self._stop.is_set():
                    return 0  # do not advance the durable cursor past unfinished work
                source = observe_source(row["file_path"])
                input_hash = fingerprint({"run_id": row["id"], "source": source})
                for policy in policies:
                    key = policy["policy_hash"]
                    if not self.store.scan_allowed(row["image_id"], key, input_hash):
                        continue
                    try:
                        self.store.observe(row["image_id"], key, source_observation=source)
                    except Exception as exc:
                        self.store.record_scan_fault(row["image_id"], key, input_hash, type(exc).__name__)
                        logger.warning("Authority input observation failed (%s)", type(exc).__name__)
                    else:
                        self.store.recover_scan(row["image_id"], key, input_hash)
            self.store.finish_scan(rows)
        completed = 0
        for _ in range(self.batch_size):
            if self._stop.is_set() or self.store.control()["mode"] not in ("shadow", "active"):
                break
            claim = self.store.claim_next()
            if claim is None:
                break
            try:
                completed += int(self._complete_with_heartbeat(claim))
            except Exception as exc:
                self.store.fail(claim, type(exc).__name__)
                logger.warning("Authority proposal failed (%s)", type(exc).__name__)
        self._publish_diagnostics(scanned=len(rows), completed=completed)
        if self.store.control()["mode"]=="active":
            from modules.localization_species import CPU_ACTIONS,SpeciesStore
            species=SpeciesStore(self.store.conn)
            species_rows=species.scan_batch(self.batch_size)
            for row in species_rows:
                if self._stop.is_set():
                    return completed
                species.observe(row['id'],source_observation=observe_source(row['file_path']))
            species.finish_scan(species_rows)
            for _ in range(self.batch_size):
                claim=species.claim_next(actions=CPU_ACTIONS)
                if not claim:
                    break
                try:
                    species.publish(claim)
                except Exception as exc:
                    species.fail(claim,type(exc).__name__)
        return completed
