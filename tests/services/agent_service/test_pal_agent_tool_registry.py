"""Tests for pal-agents tool registry."""

from services.agent_service._pal_agent_tool_registry import merge_auth_with_credentials

# Test constants to avoid Ruff S105/S106 security warnings for hardcoded credentials
TEST_CLIENT_ID = "test_client_id"
TEST_CLIENT_SECRET = "test_client_secret"  # noqa: S105
TEST_CUSTOM_TOKEN_URL = "https://custom.token.url/oauth/token"
TEST_DEFAULT_TOKEN_URL = "https://default.token.url/oauth/token"


def test_merge_auth_with_credentials_with_token_url():
    """Test that default_token_url is injected into bearer rotation config."""
    auth_config = {
        "type": "bearer",
        "rotation": {
            "enabled": True,
        },
    }

    result = merge_auth_with_credentials(
        auth_config=auth_config,
        client_id=TEST_CLIENT_ID,
        client_secret=TEST_CLIENT_SECRET,
        default_token_url=TEST_CUSTOM_TOKEN_URL,
    )

    assert result is not None
    assert result["type"] == "bearer"
    assert result["rotation"]["token_url"] == TEST_CUSTOM_TOKEN_URL
    assert result["rotation"]["client_id"] == TEST_CLIENT_ID
    assert result["rotation"]["client_secret"] == TEST_CLIENT_SECRET


def test_merge_auth_with_credentials_without_token_url_uses_default():
    """Test that default_token_url is used to build auth from scratch."""
    result = merge_auth_with_credentials(
        auth_config=None,
        client_id=TEST_CLIENT_ID,
        client_secret=TEST_CLIENT_SECRET,
        default_token_url=TEST_DEFAULT_TOKEN_URL,
    )

    assert result is not None
    assert result["type"] == "bearer"
    assert result["rotation"]["token_url"] == TEST_DEFAULT_TOKEN_URL
    assert result["rotation"]["client_id"] == TEST_CLIENT_ID
    assert result["rotation"]["client_secret"] == TEST_CLIENT_SECRET
