"""Tests for Adora API client helpers."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from services.knowledge_service.adora._client import download_coupons, download_menu


def _mock_response(payload: object) -> MagicMock:
    response = MagicMock()
    response.json.return_value = payload
    return response


def test_download_coupons_fetches_store_coupons() -> None:
    raw_coupons = [{"id": 10, "name": "SAVE20", "isAIOffer": True}]
    response = _mock_response(raw_coupons)

    with patch(
        "services.knowledge_service.adora._client.requests.get",
        return_value=response,
    ) as mock_get:
        result = download_coupons(
            store_id="STORE123",
            token="bearer-token",
            general_api_endpoint="https://public.api.adorapos.net/api/v1/OrderHub",
        )

    assert result == raw_coupons
    mock_get.assert_called_once_with(
        "https://public.api.adorapos.net/api/v1/OrderHub/coupons",
        headers={"Authorization": "Bearer bearer-token"},
        params={"sid": "STORE123"},
        timeout=10,
    )
    response.raise_for_status.assert_called_once_with()


def test_download_coupons_requires_array_response() -> None:
    response = _mock_response({"coupons": []})

    with (
        patch(
            "services.knowledge_service.adora._client.requests.get",
            return_value=response,
        ),
        pytest.raises(ValueError, match="not a JSON array"),
    ):
        download_coupons(
            store_id="STORE123",
            token="bearer-token",
            general_api_endpoint="https://public.api.adorapos.net/api/v1/OrderHub/",
        )


def test_download_menu_uses_order_hub_url_builder() -> None:
    response = _mock_response({"latitude": 1.0, "longitude": 2.0, "items": []})

    with patch(
        "services.knowledge_service.adora._client.requests.get",
        return_value=response,
    ) as mock_get:
        result = download_menu(
            store_id="STORE123",
            token="bearer-token",
            general_api_endpoint="https://public.api.adorapos.net/api/v1/OrderHub/",
        )

    assert result == {"latitude": 1.0, "longitude": 2.0, "items": []}
    mock_get.assert_called_once_with(
        "https://public.api.adorapos.net/api/v1/OrderHub/menu",
        headers={"Authorization": "Bearer bearer-token"},
        params={"sid": "STORE123"},
        timeout=10,
    )


def test_download_coupons_wraps_http_error() -> None:
    response = _mock_response([])
    response.status_code = 500
    response.reason = "Internal Server Error"
    http_error = requests.exceptions.HTTPError(response=response)
    response.raise_for_status.side_effect = http_error

    with (
        patch(
            "services.knowledge_service.adora._client.requests.get",
            return_value=response,
        ),
        pytest.raises(RuntimeError, match="Error downloading coupons: 500") as exc_info,
    ):
        download_coupons(
            store_id="STORE123",
            token="bearer-token",
            general_api_endpoint="https://public.api.adorapos.net/api/v1/OrderHub",
        )

    assert exc_info.value.__cause__ is http_error


def test_download_coupons_wraps_network_error() -> None:
    request_error = requests.exceptions.RequestException("timed out")

    with (
        patch(
            "services.knowledge_service.adora._client.requests.get",
            side_effect=request_error,
        ),
        pytest.raises(
            RuntimeError, match="Network error downloading coupons"
        ) as exc_info,
    ):
        download_coupons(
            store_id="STORE123",
            token="bearer-token",
            general_api_endpoint="https://public.api.adorapos.net/api/v1/OrderHub",
        )

    assert exc_info.value.__cause__ is request_error
