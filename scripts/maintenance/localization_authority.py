"""Local observational authority maintenance. Run with python -m from repo root."""
import argparse
import json
from pathlib import Path

from modules.localization_authority_reservations import import_frozen_reservations, read_frozen_inventory
from modules.localization_authority_store import AuthorityStore
from modules.localization_authority_worker import ShadowAuthorityWorker
from modules.localization_evaluation import ArtifactScope


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
