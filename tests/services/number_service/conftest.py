"""conftest for number_service tests.

Sets service-specific environment variables. Database and AWS variables
are already configured by the root conftest.py.
"""

import pytest


@pytest.fixture(autouse=True)
def force_test_env(monkeypatch):
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "ACtest123")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "test_auth_token")
