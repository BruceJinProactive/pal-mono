"""
Palona DB Explorer — Read-only MCP server for database introspection.

Usage (stdio, local dev):
    uv run mcp_server/server.py

Usage (HTTP, remote / docker-compose / ECS):
    python mcp_server/server.py --http

Deployment:
    Same Dockerfile + entrypoint.sh as the main app. In ECS/docker-compose,
    override the command:
        command: ["python", "mcp_server/server.py", "--http"]

Configuration:
    DB connection: same env vars as the main app (DB_HOST, DB_PORT, etc.)
    Auth (remote only):
        MCP_AUTH_TOKEN  — required for HTTP transport. Clients must send
                          Authorization: Bearer <token> header.
    Server:
        MCP_HOST        — bind address (default: 0.0.0.0)
        MCP_PORT        — port (default: 8080)
"""

from __future__ import annotations

import os
import re
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine

from db.settings import db_settings
from db.tables import Base  # noqa: F401 — registers all models into Base.metadata
from db.tables import types as db_types

# ---------------------------------------------------------------------------
# Read-only engine
# ---------------------------------------------------------------------------


_engine: Engine = create_engine(
    db_settings.get_db_url(),
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=1800,
    pool_pre_ping=True,
)


# Enforce read-only at the Postgres transaction level.
# Even if a tool accidentally issues a write, Postgres will reject it.
@event.listens_for(_engine, "begin")
def _set_readonly(conn: Any) -> None:
    conn.exec_driver_sql("SET TRANSACTION READ ONLY")


# ---------------------------------------------------------------------------
# Auth — bearer token verification for remote (HTTP) transport
# ---------------------------------------------------------------------------

_AUTH_TOKEN = os.environ.get("MCP_AUTH_TOKEN", "")


def _build_auth_kwargs() -> dict[str, Any]:
    """Return FastMCP auth kwargs if MCP_AUTH_TOKEN is set, else empty dict."""
    if not _AUTH_TOKEN:
        return {}

    from mcp.server.auth.provider import AccessToken, TokenVerifier
    from mcp.server.auth.settings import AuthSettings
    from pydantic import AnyHttpUrl

    host = os.environ.get("MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("MCP_PORT", "8080"))
    server_url = os.environ.get("MCP_SERVER_URL", f"http://{host}:{port}")

    class BearerTokenVerifier(TokenVerifier):
        """Validates incoming bearer tokens against the MCP_AUTH_TOKEN env var."""

        async def verify_token(self, token: str) -> AccessToken | None:
            if token == _AUTH_TOKEN:
                return AccessToken(
                    token=token,
                    client_id="mcp-client",
                    scopes=["read"],
                    expires_at=None,
                )
            return None

    return {
        "token_verifier": BearerTokenVerifier(),
        "auth": AuthSettings(
            issuer_url=AnyHttpUrl(server_url),
            resource_server_url=AnyHttpUrl(server_url),
            required_scopes=["read"],
        ),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MAX_ROWS = 500  # hard ceiling for any query


def _safe_select(sql: str) -> str:
    """Validate that a SQL string is a SELECT (not DML/DDL)."""
    stripped = sql.strip().rstrip(";").strip()
    if not re.match(r"(?i)^(SELECT|WITH)\b", stripped):
        raise ValueError("Only SELECT / WITH (CTE) queries are allowed.")
    # Block obvious mutation keywords even inside CTEs
    forbidden = re.compile(
        r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE|COPY)\b",
        re.IGNORECASE,
    )
    if forbidden.search(stripped):
        raise ValueError("Mutation statements are not allowed in read-only mode.")
    return stripped


def _rows_to_text(columns: list[str], rows: Any, total: int | None = None) -> str:
    """Format query results as a readable text table."""
    if not rows:
        return "No rows returned."

    lines: list[str] = []
    # Header
    lines.append(" | ".join(columns))
    lines.append("-" * len(lines[0]))
    # Rows
    for row in rows:
        lines.append(" | ".join(str(v) for v in row))

    if total is not None:
        lines.append(f"\n({len(rows)} rows shown, {total} total)")
    else:
        lines.append(f"\n({len(rows)} rows)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

_is_http = "--http" in sys.argv
_auth_kwargs = _build_auth_kwargs() if _is_http else {}

mcp = FastMCP(
    "Palona DB Explorer",
    instructions=(
        "Read-only database explorer for the Palona pal-mono service. "
        "Use these tools to understand the schema, explore relationships, "
        "query data, and gather statistics. All queries are enforced read-only "
        "at the Postgres transaction level."
    ),
    host=os.environ.get("MCP_HOST", "0.0.0.0"),
    port=int(os.environ.get("MCP_PORT", "8080")),
    **_auth_kwargs,
)


# ---- Schema tools ----------------------------------------------------------


@mcp.tool()
def list_tables() -> str:
    """List all tables in the database with their row counts.

    Returns a table of (table_name, row_count) sorted alphabetically.
    Useful as a starting point to understand what data exists.
    """
    inspector = inspect(_engine)
    table_names = sorted(inspector.get_table_names())

    lines: list[str] = ["table_name | row_count", "-" * 40]
    with _engine.connect() as conn:
        for name in table_names:
            result = conn.execute(text(f'SELECT COUNT(*) FROM "{name}"'))  # noqa: S608
            count = result.scalar()
            lines.append(f"{name} | {count}")
    return "\n".join(lines)


@mcp.tool()
def describe_table(table_name: str) -> str:
    """Describe a table's columns, types, nullability, defaults, and indexes.

    Args:
        table_name: Name of the table to describe (e.g. 'accounts', 'projects').
    """
    inspector = inspect(_engine)

    # Validate table exists
    all_tables = inspector.get_table_names()
    if table_name not in all_tables:
        return f"Table '{table_name}' not found. Available: {', '.join(sorted(all_tables))}"

    # Columns
    columns = inspector.get_columns(table_name)
    col_lines: list[str] = ["## Columns", "name | type | nullable | default", "-" * 60]
    for col in columns:
        col_lines.append(
            f"{col['name']} | {col['type']} | {col['nullable']} | {col.get('default', '')}"
        )

    # Primary key
    pk = inspector.get_pk_constraint(table_name)
    pk_line = f"\n## Primary Key\n{pk.get('constrained_columns', [])}"

    # Foreign keys
    fks = inspector.get_foreign_keys(table_name)
    fk_lines: list[str] = ["\n## Foreign Keys"]
    if fks:
        for fk in fks:
            fk_lines.append(
                f"  {fk['constrained_columns']} -> {fk['referred_table']}.{fk['referred_columns']}"
            )
    else:
        fk_lines.append("  (none)")

    # Indexes
    indexes = inspector.get_indexes(table_name)
    idx_lines: list[str] = ["\n## Indexes"]
    if indexes:
        for idx in indexes:
            unique = " (unique)" if idx.get("unique") else ""
            idx_lines.append(f"  {idx['name']}: {idx['column_names']}{unique}")
    else:
        idx_lines.append("  (none)")

    return "\n".join(col_lines) + pk_line + "\n".join(fk_lines) + "\n".join(idx_lines)


@mcp.tool()
def get_relationships() -> str:
    """Show all foreign key relationships between tables.

    Returns a list of (source_table.column -> target_table.column) relationships.
    Note: This codebase also uses indexed columns without FK constraints for
    some relationships (managed by application code).
    """
    inspector = inspect(_engine)
    table_names = sorted(inspector.get_table_names())

    lines: list[str] = ["source_table.column -> target_table.column", "-" * 60]
    for table in table_names:
        fks = inspector.get_foreign_keys(table)
        for fk in fks:
            for src_col, ref_col in zip(
                fk["constrained_columns"], fk["referred_columns"]
            ):
                lines.append(f"{table}.{src_col} -> {fk['referred_table']}.{ref_col}")

    if len(lines) == 2:
        lines.append("(no foreign key constraints found)")

    return "\n".join(lines)


@mcp.tool()
def get_enums() -> str:
    """List all domain enum types and their values.

    These enums are used throughout the database for status fields,
    categories, types, etc. Useful for understanding valid filter values.
    """
    import enum
    import inspect as py_inspect

    lines: list[str] = []
    # Get all enum classes from db.tables.types
    for name, obj in sorted(py_inspect.getmembers(db_types)):
        if (
            py_inspect.isclass(obj)
            and issubclass(obj, enum.Enum)
            and obj is not enum.Enum
        ):
            values = [e.value for e in obj]
            lines.append(f"## {name}")
            lines.append(f"  Values: {', '.join(str(v) for v in values)}")
            lines.append("")

    return "\n".join(lines) if lines else "No enums found."


# ---- Query tools -----------------------------------------------------------


@mcp.tool()
def get_sample_data(table_name: str, limit: int = 5) -> str:
    """Get sample rows from a table to understand its data shape.

    Args:
        table_name: Name of the table to sample.
        limit: Number of rows to return (max 50, default 5).
    """
    limit = min(limit, 50)
    inspector = inspect(_engine)
    all_tables = inspector.get_table_names()
    if table_name not in all_tables:
        return f"Table '{table_name}' not found. Available: {', '.join(sorted(all_tables))}"

    with _engine.connect() as conn:
        result = conn.execute(
            text(f'SELECT * FROM "{table_name}" LIMIT :lim'), {"lim": limit}
        )  # noqa: S608
        columns = list(result.keys())
        rows = result.fetchall()

    return _rows_to_text(columns, rows)


@mcp.tool()
def run_query(sql: str, limit: int = 100) -> str:
    """Execute a read-only SQL query and return results.

    Only SELECT and WITH (CTE) statements are allowed. A row limit is enforced.
    The database connection is read-only at the Postgres transaction level.

    Args:
        sql: The SELECT query to execute.
        limit: Maximum rows to return (max 500, default 100).

    Examples:
        - "SELECT * FROM accounts WHERE status = 'active' LIMIT 10"
        - "SELECT p.name, a.name as account FROM projects p JOIN accounts a ON p.account_id = a.id"
        - "WITH recent AS (SELECT * FROM conversations WHERE created_at > now() - interval '7 days') SELECT * FROM recent"
    """
    limit = min(limit, _MAX_ROWS)
    safe_sql = _safe_select(sql)

    # Wrap in a subquery to enforce limit if not already present
    if not re.search(r"\bLIMIT\b", safe_sql, re.IGNORECASE):
        safe_sql = f"SELECT * FROM ({safe_sql}) _sub LIMIT {limit}"

    with _engine.connect() as conn:
        result = conn.execute(text(safe_sql))
        columns = list(result.keys())
        rows = result.fetchmany(limit)

    return _rows_to_text(columns, rows)


@mcp.tool()
def search_table(
    table_name: str,
    column: str,
    value: str,
    limit: int = 20,
) -> str:
    """Search a table by a column value (case-insensitive LIKE match).

    Convenient for quick lookups without writing full SQL.

    Args:
        table_name: Table to search.
        column: Column to filter on.
        value: Value to search for (supports % wildcards, e.g. '%palona%').
        limit: Max rows (default 20, max 100).
    """
    limit = min(limit, 100)
    inspector = inspect(_engine)
    all_tables = inspector.get_table_names()
    if table_name not in all_tables:
        return f"Table '{table_name}' not found. Available: {', '.join(sorted(all_tables))}"

    col_names = [c["name"] for c in inspector.get_columns(table_name)]
    if column not in col_names:
        return f"Column '{column}' not found in '{table_name}'. Available: {', '.join(col_names)}"

    with _engine.connect() as conn:
        sql = text(
            f'SELECT * FROM "{table_name}" WHERE "{column}"::text ILIKE :val LIMIT :lim'  # noqa: S608
        )
        result = conn.execute(sql, {"val": value, "lim": limit})
        columns = list(result.keys())
        rows = result.fetchall()

    return _rows_to_text(columns, rows)


# ---- Stats tools -----------------------------------------------------------


@mcp.tool()
def get_table_stats(table_name: str) -> str:
    """Get statistics for a table: row count, column value distributions for
    enum/status columns, and date ranges for timestamp columns.

    Args:
        table_name: Table to analyze.
    """
    inspector = inspect(_engine)
    all_tables = inspector.get_table_names()
    if table_name not in all_tables:
        return f"Table '{table_name}' not found. Available: {', '.join(sorted(all_tables))}"

    columns = inspector.get_columns(table_name)
    lines: list[str] = []

    with _engine.connect() as conn:
        # Row count
        count = conn.execute(
            text(f'SELECT COUNT(*) FROM "{table_name}"')
        ).scalar()  # noqa: S608
        lines.append(f"## {table_name} — {count} rows\n")

        for col in columns:
            col_name = col["name"]
            col_type = str(col["type"]).upper()

            # Date ranges for timestamp/date columns
            if "DATE" in col_type or "TIMESTAMP" in col_type:
                result = conn.execute(
                    text(
                        f'SELECT MIN("{col_name}"), MAX("{col_name}") FROM "{table_name}"'
                    )  # noqa: S608
                )
                row = result.fetchone()
                if row and row[0]:
                    lines.append(f"  {col_name} ({col_type}): {row[0]} to {row[1]}")

            # Value distributions for string/enum columns (low cardinality)
            elif (
                "VARCHAR" in col_type
                or "TEXT" in col_type
                or "ENUM" in col_type
                or col_type == "STRING"
            ):
                result = conn.execute(
                    text(
                        f'SELECT "{col_name}", COUNT(*) as cnt FROM "{table_name}" '  # noqa: S608
                        f'GROUP BY "{col_name}" ORDER BY cnt DESC LIMIT 15'
                    )
                )
                dist = result.fetchall()
                if dist and len(dist) <= 15:
                    dist_str = ", ".join(f"{r[0]}={r[1]}" for r in dist)
                    lines.append(f"  {col_name}: {dist_str}")

    return "\n".join(lines) if lines else f"No stats available for '{table_name}'."


@mcp.tool()
def get_schema_overview() -> str:
    """Get a high-level overview of the entire database schema.

    Returns each table with its column count, row count, and which tables
    it references via foreign keys. Good for understanding the data model
    at a glance.
    """
    inspector = inspect(_engine)
    table_names = sorted(inspector.get_table_names())

    lines: list[str] = ["table | columns | rows | references", "-" * 70]

    with _engine.connect() as conn:
        for table in table_names:
            cols = inspector.get_columns(table)
            fks = inspector.get_foreign_keys(table)
            refs = [fk["referred_table"] for fk in fks]
            count = conn.execute(
                text(f'SELECT COUNT(*) FROM "{table}"')
            ).scalar()  # noqa: S608
            ref_str = ", ".join(refs) if refs else "-"
            lines.append(f"{table} | {len(cols)} | {count} | {ref_str}")

    return "\n".join(lines)


# ---- Resources (static schema info) ----------------------------------------


@mcp.resource("schema://overview")
def schema_overview_resource() -> str:
    """Complete database schema overview as a resource."""
    return get_schema_overview()


@mcp.resource("schema://enums")
def enums_resource() -> str:
    """All domain enum types and their values."""
    return get_enums()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    transport = "streamable-http" if _is_http else "stdio"

    if _is_http and not _AUTH_TOKEN:
        print(
            "ERROR: MCP_AUTH_TOKEN is required for HTTP transport. "
            "Set MCP_AUTH_TOKEN env var before starting the server remotely.",
            file=sys.stderr,
        )
        sys.exit(1)

    mcp.run(transport=transport)
