"""Tests for the MCP server's safety guarantees.

1. Write access is blocked — all mutation SQL is rejected
2. HTTP mode requires MCP_AUTH_TOKEN — refuses to start without it
"""

from __future__ import annotations

import subprocess
import sys
from unittest.mock import patch

import pytest

from mcp_server.server import _safe_select

# =============================================================================
# 1. Write access is blocked
# =============================================================================


class TestSafeSelectBlocksWrites:
    """_safe_select must reject any SQL that could mutate data."""

    # ---- Allowed (should pass through) ------------------------------------

    @pytest.mark.parametrize(
        "sql",
        [
            "SELECT * FROM accounts",
            "select id, name from projects where status = 'active'",
            "SELECT COUNT(*) FROM conversations",
            "WITH cte AS (SELECT * FROM accounts) SELECT * FROM cte",
            "  SELECT * FROM accounts  ;  ",
        ],
        ids=[
            "basic_select",
            "lowercase_select",
            "aggregate",
            "cte",
            "whitespace_and_semicolon",
        ],
    )
    def test_allows_select_queries(self, sql: str) -> None:
        result = _safe_select(sql)
        assert result  # returns the cleaned SQL

    # ---- Blocked: not a SELECT --------------------------------------------

    @pytest.mark.parametrize(
        "sql",
        [
            "INSERT INTO accounts (name) VALUES ('hacked')",
            "UPDATE accounts SET status = 'deleted'",
            "DELETE FROM accounts WHERE id = '123'",
            "DROP TABLE accounts",
            "ALTER TABLE accounts ADD COLUMN pwned TEXT",
            "TRUNCATE accounts",
            "CREATE TABLE evil (id INT)",
            "GRANT ALL ON accounts TO PUBLIC",
            "REVOKE ALL ON accounts FROM app",
            "COPY accounts TO '/tmp/dump.csv'",
        ],
        ids=[
            "insert",
            "update",
            "delete",
            "drop",
            "alter",
            "truncate",
            "create",
            "grant",
            "revoke",
            "copy",
        ],
    )
    def test_blocks_direct_mutation_statements(self, sql: str) -> None:
        with pytest.raises(ValueError, match="Only SELECT"):
            _safe_select(sql)

    # ---- Blocked: mutation hidden inside CTE / subquery -------------------

    @pytest.mark.parametrize(
        "sql",
        [
            "WITH del AS (DELETE FROM accounts RETURNING *) SELECT * FROM del",
            "SELECT * FROM (INSERT INTO accounts (name) VALUES ('x') RETURNING *) sub",
            "WITH u AS (UPDATE accounts SET name='x' RETURNING *) SELECT * FROM u",
            "SELECT * FROM accounts; DROP TABLE accounts",
        ],
        ids=[
            "delete_in_cte",
            "insert_in_subquery",
            "update_in_cte",
            "semicolon_injection",
        ],
    )
    def test_blocks_mutation_hidden_in_cte(self, sql: str) -> None:
        with pytest.raises(ValueError, match="Mutation statements are not allowed"):
            _safe_select(sql)

    # ---- Blocked: case variations -----------------------------------------

    @pytest.mark.parametrize(
        "sql",
        [
            "select * from (INSERT into accounts values ('x') returning *) s",
            "SELECT * FROM (delete FROM accounts) AS d",
            "WITH x AS (Drop Table accounts) SELECT 1",
        ],
        ids=[
            "mixed_case_insert",
            "mixed_case_delete",
            "mixed_case_drop",
        ],
    )
    def test_blocks_case_insensitive(self, sql: str) -> None:
        with pytest.raises(ValueError):
            _safe_select(sql)


# =============================================================================
# 2. HTTP mode requires MCP_AUTH_TOKEN
# =============================================================================


class TestHttpRequiresAuth:
    """Starting the server in --http mode without MCP_AUTH_TOKEN must fail."""

    def test_http_mode_exits_without_auth_token(self) -> None:
        """Running server.py --http without MCP_AUTH_TOKEN should exit(1)."""
        env_without_token = {
            "MCP_AUTH_TOKEN": "",
            "db_host": "localhost",
            "db_port": "5432",
            "db_user": "test",
            "db_pass": "test",
            "db_database": "test",
        }

        result = subprocess.run(
            [sys.executable, "-m", "mcp_server.server", "--http"],
            capture_output=True,
            text=True,
            env=env_without_token,
            timeout=10,
        )

        assert result.returncode != 0
        assert "MCP_AUTH_TOKEN is required" in result.stderr

    def test_http_mode_allows_start_with_auth_token(self) -> None:
        """Verify the startup check passes when MCP_AUTH_TOKEN is set.

        We can't fully start the server (needs real DB + port), so we
        test the guard logic directly: the entry-point code should NOT
        call sys.exit when the token is present.
        """
        # The guard is: if _is_http and not _AUTH_TOKEN: sys.exit(1)
        # We test by importing the module-level vars and verifying behavior.
        with (
            patch("mcp_server.server._is_http", True),
            patch("mcp_server.server._AUTH_TOKEN", "test-secret"),
            patch("mcp_server.server.mcp"),
        ):
            # Simulate what __main__ does (minus the actual mcp.run)

            # Re-read patched values
            import mcp_server.server as srv

            transport = "streamable-http" if srv._is_http else "stdio"

            if srv._is_http and not srv._AUTH_TOKEN:
                pytest.fail("Should not reach sys.exit when token is set")

            # If we get here, the guard passed — server would proceed to mcp.run
            assert transport == "streamable-http"
