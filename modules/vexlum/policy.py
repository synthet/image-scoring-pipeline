"""Tiered execute policy: read / write / destructive.

* ``read``        — runs immediately.
* ``write``       — needs ``confirmed=True`` (``dry_run=True`` previews without it).
* ``destructive`` — needs env ``VEXLUM_ALLOW_ELEVATED=1``, a prior ``dry_run=True`` that returned a
  ``confirm_token`` for the *same* arguments, then ``confirmed=True`` with that token.

Tokens are ``<expiry>.<hmac>`` over (action_id, canonical args, expiry). The key comes from
``VEXLUM_TOKEN_SECRET`` or a per-user key file (``~/.vexlum/confirm.key``) so a CLI dry run in one
process can be confirmed by the next one.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any

from modules.mcp.actions.errors import ConfirmationRequiredError, PolicyError

TIERS = ("read", "write", "destructive")
TOKEN_TTL_SECONDS = 600
ELEVATED_ENV = "VEXLUM_ALLOW_ELEVATED"


class ConfirmTokenError(PolicyError):
    code = "confirm_token_invalid"


_key_cache: bytes | None = None


def _key_path() -> Path:
    override = (os.environ.get("VEXLUM_TOKEN_KEY_FILE") or "").strip()
    return Path(override) if override else Path.home() / ".vexlum" / "confirm.key"


def _token_key() -> bytes:
    global _key_cache
    env = (os.environ.get("VEXLUM_TOKEN_SECRET") or "").strip()
    if env:
        return env.encode("utf-8")
    if _key_cache is not None:
        return _key_cache
    path = _key_path()
    try:
        if path.exists():
            _key_cache = path.read_bytes().strip()
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            key = secrets.token_hex(32).encode("ascii")
            fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as fh:
                fh.write(key)
            _key_cache = key
    except FileExistsError:
        _key_cache = path.read_bytes().strip()
    except OSError:
        # Read-only home: fall back to a per-process key (tokens then only live in one process).
        _key_cache = secrets.token_hex(32).encode("ascii")
    return _key_cache


def reset_token_key_cache() -> None:
    """Tests only."""
    global _key_cache
    _key_cache = None


def _canonical(action_id: str, args: dict[str, Any], expiry: int) -> bytes:
    return json.dumps({"a": action_id, "args": args, "exp": expiry}, sort_keys=True, default=str).encode("utf-8")


def issue_token(action_id: str, args: dict[str, Any], *, now: float | None = None) -> dict[str, Any]:
    expiry = int((now if now is not None else time.time()) + TOKEN_TTL_SECONDS)
    sig = hmac.new(_token_key(), _canonical(action_id, args, expiry), hashlib.sha256).hexdigest()[:40]
    return {"confirm_token": f"{expiry}.{sig}", "expires_at": expiry, "ttl_seconds": TOKEN_TTL_SECONDS}


def verify_token(action_id: str, args: dict[str, Any], token: str | None, *, now: float | None = None) -> None:
    if not token or "." not in token:
        raise ConfirmTokenError(
            "destructive action needs confirm_token from a dry_run with the same arguments",
            details={"next": "execute(..., dry_run=True) then execute(..., confirmed=True, confirm_token=...)"},
        )
    exp_raw, sig = token.split(".", 1)
    try:
        expiry = int(exp_raw)
    except ValueError as exc:
        raise ConfirmTokenError("malformed confirm_token") from exc
    if (now if now is not None else time.time()) > expiry:
        raise ConfirmTokenError("confirm_token expired; run dry_run again", details={"expired_at": expiry})
    expected = hmac.new(_token_key(), _canonical(action_id, args, expiry), hashlib.sha256).hexdigest()[:40]
    if not hmac.compare_digest(expected, sig):
        raise ConfirmTokenError(
            "confirm_token does not match this action and arguments (arguments changed?)",
            details={"next": "run dry_run again with the final arguments"},
        )


def elevated_allowed() -> bool:
    return (os.environ.get(ELEVATED_ENV) or "").strip().lower() in {"1", "true", "yes", "on"}


def requirements(tier: str) -> dict[str, Any]:
    """What ``resolve`` advertises for a tier."""
    if tier == "read":
        return {"confirmed": False, "confirm_token": False, "env": None}
    if tier == "write":
        return {"confirmed": True, "confirm_token": False, "env": None}
    return {"confirmed": True, "confirm_token": True, "env": f"{ELEVATED_ENV}=1"}


def check(
    record: dict[str, Any],
    validated_args: dict[str, Any],
    *,
    dry_run: bool,
    confirmed: bool,
    confirm_token: str | None,
) -> None:
    """Raise when the call may not run. Dry runs are always allowed (they never mutate)."""
    tier = str(record.get("tier") or "write")
    if tier not in TIERS:
        raise PolicyError(f"unknown tier {tier!r}", details={"action_id": record.get("action_id")})
    if tier == "read" or dry_run:
        return
    if not confirmed:
        raise ConfirmationRequiredError(
            f"{record.get('action_id')} is tier={tier}; pass confirmed=true"
            + (" with the confirm_token from a dry_run" if tier == "destructive" else ""),
            details={"tier": tier, "requires": requirements(tier)},
        )
    if tier == "destructive":
        if not elevated_allowed():
            raise PolicyError(
                f"{record.get('action_id')} is destructive; set {ELEVATED_ENV}=1 on the vexlum process",
                details={"tier": tier, "requires": requirements(tier), "policy": "elevated_env"},
            )
        verify_token(str(record["action_id"]), validated_args, confirm_token)
