"""Tests for tools.utils.url_shortener."""

from unittest.mock import MagicMock

import pytest


@pytest.mark.parametrize(
    ("runtime_env", "expected_url"),
    [
        ("lat", "https://lat-console.palona.ai/checkout/toast?t=token"),
        ("stg", "https://stg-console.palona.ai/checkout/toast?t=token"),
        ("prd", "https://console.palona.ai/checkout/toast?t=token"),
    ],
)
def test_shorten_url_uses_env_aware_destination_url(
    monkeypatch, runtime_env, expected_url
):
    from tools.utils import url_shortener

    post_mock = MagicMock()
    post_mock.return_value.status_code = 200
    post_mock.return_value.json.return_value = {
        "data": {"tiny_url": "https://pay.palona.ai/abc123"}
    }

    monkeypatch.setenv("RUNTIME_ENV", runtime_env)
    monkeypatch.setenv("TINYURL_DOMAIN_NAME", "pay.palona.ai")
    monkeypatch.setattr(
        url_shortener,
        "get_server_secret_with_fallback",
        lambda _name: "tiny-url-api-token",
    )
    monkeypatch.setattr(url_shortener.requests, "post", post_mock)

    result = url_shortener.shorten_url(
        "https://console.palona.ai/checkout/toast?t=token",
        use_env_url_prefix=True,
    )

    assert result == "https://pay.palona.ai/abc123"
    post_mock.assert_called_once()
    assert post_mock.call_args.kwargs["json"]["url"] == expected_url
    assert post_mock.call_args.kwargs["json"]["domain"] == "pay.palona.ai"


def test_shorten_url_returns_env_aware_url_when_api_key_missing(monkeypatch):
    from tools.utils import url_shortener

    monkeypatch.setenv("RUNTIME_ENV", "lat")
    monkeypatch.setattr(
        url_shortener,
        "get_server_secret_with_fallback",
        lambda _name: "",
    )

    result = url_shortener.shorten_url(
        "https://console.palona.ai/checkout/toast?t=token",
        use_env_url_prefix=True,
    )

    assert result == "https://lat-console.palona.ai/checkout/toast?t=token"
