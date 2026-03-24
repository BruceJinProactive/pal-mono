"""Smoke tests for the httpx.AsyncClient fixture.

Verifies the async client can reach the FastAPI app through ASGI transport,
and that DI overrides (auth, DB) are wired correctly.
"""

import httpx
import pytest


@pytest.mark.integration
class TestClientSmoke:
    async def test_client_reaches_app(self, client: httpx.AsyncClient) -> None:
        """Health endpoint is reachable through the test client."""
        response = await client.get("/v1/health")
        assert response.status_code == 200

    async def test_auth_override_prevents_401(self, client: httpx.AsyncClient) -> None:
        """Authenticated endpoint does not return 401 with auth override."""
        response = await client.get("/v1/admin/accounts")
        # Should not be 401/403 — auth is overridden
        assert response.status_code != 401
