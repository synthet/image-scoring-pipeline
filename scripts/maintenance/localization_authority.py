"""Explicit scoped authority maintenance. Run with python -m from repo root."""
import argparse
import json
from pathlib import Path

from modules.localization_authority_reservations import import_frozen_reservations, read_frozen_inventory
from modules.localization_authority_store import AuthorityStore
from modules.localization_authority_worker import ShadowAuthorityWorker
from modules.localization_evaluation import ArtifactScope
from modules.localization_active import ActiveAuthority
from modules.localization_policy_approval import register_runtime_policy


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expect-database", help="exact database name required before metadata mutations")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    sub.add_parser("run-once")
    mode = sub.add_parser("set-mode")
    mode.add_argument("mode", choices=("off", "shadow"))
    register = sub.add_parser("register-policy")
    register.add_argument("--rule", type=Path, required=True)
    for name in ("detector-version", "detector-config-hash", "rendition-version"):
        register.add_argument(f"--{name}", required=True)
    runtime = sub.add_parser("register-runtime-policy")
    for name in ("detector-version", "detector-config-hash", "rendition-version"):
        runtime.add_argument(f"--{name}", required=True)
    freshness = sub.add_parser("set-freshness")
    freshness.add_argument("value", choices=("on","off"))
    freshness.add_argument("--confirm", action="store_true", required=True)
    approve = sub.add_parser("approve-policy")
    approve.add_argument("--policy-hash", required=True)
    approve.add_argument("--receipt", type=Path, required=True)
    approve.add_argument("--receipt-sha256", required=True)
    approve.add_argument("--actor", required=True)
    approve.add_argument("--confirm", action="store_true", required=True)
    activate = sub.add_parser("activate")
    activate.add_argument("--policy-hash", required=True)
    activate.add_argument("--receipt-sha256", required=True)
    activate.add_argument("--confirm", action="store_true", required=True)
    revoke = sub.add_parser("revoke-policy")
    revoke.add_argument("--policy-hash", required=True)
    revoke.add_argument("--reason", required=True)
    sub.add_parser("cleanup-invalid")
    for action in ("verify-inventory", "import-reservations"):
        inventory = sub.add_parser(action)
        inventory.add_argument("--root", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "verify-inventory":
        digest, rows = read_frozen_inventory(args.root)
        result = {"status": "verified", "inventory_sha256": digest, "images": len(rows)}
    else:
        store = AuthorityStore()
        target = store.conn.query_one("SELECT current_database() AS name")["name"]
        if args.command != "status" and (not args.expect_database or target != args.expect_database):
            parser.error("metadata mutation requires --expect-database matching the connected database")
        if args.command == "register-policy":
            scope = ArtifactScope(args.detector_version, args.detector_config_hash, args.rendition_version)
            result = {"policy_hash": store.register_policy(args.rule.read_bytes(), scope), "approval_granted": False}
        elif args.command == "set-mode":
            store.set_mode(args.mode)
            result = store.diagnostics()
        elif args.command == "register-runtime-policy":
            scope = ArtifactScope(args.detector_version, args.detector_config_hash, args.rendition_version)
            result = {"policy_hash": register_runtime_policy(store,scope), "approval_granted": False}
        elif args.command == "set-freshness":
            ActiveAuthority(store).set_freshness(args.value == "on")
            result = store.diagnostics()
        elif args.command == "approve-policy":
            ActiveAuthority(store).approve(args.policy_hash,args.receipt,args.receipt_sha256,args.actor,confirmed=args.confirm)
            result = store.diagnostics()
        elif args.command == "activate":
            ActiveAuthority(store).activate(args.policy_hash,args.receipt_sha256,confirmed=args.confirm)
            result = store.diagnostics()
        elif args.command == "revoke-policy":
            result = {"revoked": ActiveAuthority(store).revoke_policy(args.policy_hash,args.reason)}
        elif args.command == "cleanup-invalid":
            result = {"cleaned": ActiveAuthority(store).cleanup_invalid()}
        elif args.command == "import-reservations":
            result = import_frozen_reservations(store, args.root)
        elif args.command == "run-once":
            result = {"completed": ShadowAuthorityWorker(store).poll_once(), "diagnostics": store.diagnostics()}
        else:
            result = store.diagnostics()
        result["database"] = target
    print(json.dumps(result, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
