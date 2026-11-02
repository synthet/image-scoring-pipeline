"""Direct PostgreSQL execution for db.* actions."""

from __future__ import annotations

from typing import Any

from modules.mcp.actions.errors import McpActionError, ValidationError


def _normalize(query: str) -> str:
    from modules.mcp import tool_support as ts

    normalized = ts.strip_sql_comments_for_mcp(query or "")
    if not normalized:
        raise ValidationError("empty query")
    ok, err = ts.mcp_sql_single_statement(normalized)
    if not ok:
        raise ValidationError(str(err))
    return query.strip().rstrip(";")


def _ensure_db() -> None:
    from modules import config

    if config.get_database_engine() != "postgres":
        raise McpActionError("db.* actions require database.engine=postgres")
    try:
        from modules.mcp_server import prepare_mcp_embedded

        prepare_mcp_embedded()
    except Exception:  # noqa: BLE001 - pool init below reports the real error
        pass


def _rows(cur: Any, max_rows: int) -> dict[str, Any]:
    from modules.mcp import tool_support as ts

    if cur.description is None:
        return {"columns": [], "rows": [], "row_count": 0, "truncated": False}
    columns = [d[0] for d in cur.description]
    fetched = cur.fetchmany(max_rows + 1)
    rows = [ts.sanitize_for_mcp(dict(zip(columns, r))) for r in fetched[:max_rows]]
    return {"columns": columns, "rows": rows, "row_count": len(rows), "truncated": len(fetched) > max_rows}


def run_query(args: dict[str, Any]) -> dict[str, Any]:
    from modules import db_postgres
    from modules.mcp import tool_support as ts

    sql = _normalize(args["query"])
    if not ts.is_mcp_read_only_sql(ts.strip_sql_comments_for_mcp(sql)):
        raise ValidationError("db.query accepts SELECT/WITH only; use db.execute for writes")
    _ensure_db()
    max_rows = int(args.get("max_rows") or 200)
    with db_postgres.PGConnectionManager() as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute(sql, tuple(args.get("params") or ()) or None)
            return _rows(cur, max_rows)


def run_execute(args: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    from modules import db_postgres

    sql = _normalize(args["query"])
    _ensure_db()
    max_rows = int(args.get("max_rows") or 200)
    with db_postgres.PGConnectionManager(commit=not dry_run) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(args.get("params") or ()) or None)
            out = _rows(cur, max_rows)
            out["rowcount"] = cur.rowcount
            out["status_message"] = getattr(cur, "statusmessage", None)
    out["committed"] = not dry_run
    if dry_run:
        out["rolled_back"] = True
    return out


def run_schema(args: dict[str, Any]) -> Any:
    from modules.mcp_server import get_db_schema

    return get_db_schema(**{k: v for k, v in args.items() if v is not None})
