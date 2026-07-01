from __future__ import annotations

from typing import Any

import pytest
from pal_agents.menu_assets.olo import OloMenuCompileError

from services.knowledge_service.olo import (
    compile_olo_menu_data,
    fetch_and_compile_olo_menu_data,
)
from services.knowledge_service.olo._client import (
    _get_product_modifiers,
    get_restaurant_menu_bundle,
)


def _raw_olo_bundle() -> dict[str, Any]:
    return {
        "restaurant_id": "259950",
        "menu": {
            "categories": [
                {
                    "id": 10,
                    "name": "Burgers",
                    "products": [
                        {
                            "id": 100,
                            "name": "Cheeseburger",
                            "description": "Burger with cheese",
                            "cost": 8.99,
                        }
                    ],
                },
                {
                    "id": 11,
                    "name": "Shakes",
                    "products": [{"id": 101, "name": "Vanilla Shake"}],
                },
            ]
        },
        "modifiers_by_product_id": {
            "100": {
                "optiongroups": [
                    {
                        "id": 200,
                        "description": "Meal",
                        "mandatory": True,
                        "maxselects": "1",
                        "options": [
                            {
                                "id": 300,
                                "name": "Burger Only",
                                "cost": 0,
                                "isdefault": True,
                            }
                        ],
                    }
                ]
            }
        },
    }


def test_compile_olo_menu_data_returns_project_integration_menu_data() -> None:
    compiled = compile_olo_menu_data(
        _raw_olo_bundle(),
        selected_categories=["Burgers"],
        make_unique_categories=["Burgers"],
    )

    assert compiled["version"] == 1
    assert compiled["restaurant_id"] == "259950"
    assert [item["item_name"] for item in compiled["items"]] == [
        "Burgers / Cheeseburger"
    ]
    assert "modifier_groups_by_id" in compiled
    assert "option_paths_by_product_id" in compiled


def test_compile_olo_menu_data_rejects_legacy_indexing_shape() -> None:
    with pytest.raises(OloMenuCompileError, match="menu"):
        compile_olo_menu_data({"categories": {"Burgers": []}})


def test_get_restaurant_menu_bundle_fetches_raw_menu_and_modifiers(monkeypatch) -> None:
    raw_menu = {
        "categories": [
            {
                "id": 10,
                "name": "Burgers",
                "products": [{"id": 100, "name": "Cheeseburger"}],
            }
        ],
        "singleusecategories": [
            {
                "id": 11,
                "name": "Specials",
                "products": [{"id": 101, "name": "One Day Shake"}],
            }
        ],
    }
    request_calls: list[tuple[str, dict[str, str]]] = []
    modifier_calls: list[int] = []

    def fake_make_signed_request(
        api_function: str,
        _client_id: str,
        _client_secret: str,
        _general_api_endpoint: str,
        query_params: dict[str, str],
    ) -> dict[str, Any]:
        request_calls.append((api_function, query_params))
        return raw_menu

    def fake_get_product_modifiers(
        product_id: int,
        _client_id: str,
        _client_secret: str,
        _general_api_endpoint: str,
    ) -> dict[str, Any]:
        modifier_calls.append(product_id)
        return {"optiongroups": [{"id": product_id + 1000}]}

    monkeypatch.setattr(
        "services.knowledge_service.olo._client.make_signed_request",
        fake_make_signed_request,
    )
    monkeypatch.setattr(
        "services.knowledge_service.olo._client._get_product_modifiers",
        fake_get_product_modifiers,
    )

    bundle = get_restaurant_menu_bundle(
        "259950",
        "cid",
        "secret",
        "https://ordering.api.olo.com",
    )

    assert request_calls == [
        (
            "/v1.1/restaurants/259950/menu",
            {"includedisabled": "false", "deliverymode": "delivery"},
        )
    ]
    assert modifier_calls == [100, 101]
    assert bundle == {
        "restaurant_id": "259950",
        "menu": raw_menu,
        "modifiers_by_product_id": {
            "100": {"optiongroups": [{"id": 1100}]},
            "101": {"optiongroups": [{"id": 1101}]},
        },
    }


def test_get_product_modifiers_uses_delivery_mode_query(monkeypatch) -> None:
    request_calls: list[tuple[str, dict[str, str]]] = []

    def fake_make_signed_request(
        api_function: str,
        _client_id: str,
        _client_secret: str,
        _general_api_endpoint: str,
        query_params: dict[str, str],
    ) -> dict[str, Any]:
        request_calls.append((api_function, query_params))
        return {
            "optiongroups": [
                {
                    "id": 200,
                    "description": "Size",
                    "mandatory": True,
                    "minselects": 1,
                    "maxselects": 1,
                    "options": [{"id": 300, "name": "Regular", "cost": 0}],
                }
            ]
        }

    monkeypatch.setattr(
        "services.knowledge_service.olo._client.make_signed_request",
        fake_make_signed_request,
    )

    modifiers = _get_product_modifiers(
        100,
        "cid",
        "secret",
        "https://ordering.api.olo.com",
    )

    assert request_calls == [
        (
            "/v1.1/products/100/modifiers",
            {"includedisabled": "false", "deliverymode": "delivery"},
        )
    ]
    assert modifiers == {
        "optiongroups": [
            {
                "id": 200,
                "description": "Size",
                "mandatory": True,
                "minselects": 1,
                "maxselects": 1,
                "options": [{"id": 300, "name": "Regular", "cost": 0}],
            }
        ]
    }


def test_get_restaurant_menu_bundle_skips_products_without_ids(monkeypatch) -> None:
    raw_menu = {
        "categories": [
            {
                "id": 10,
                "name": "Burgers",
                "products": [
                    {"name": "Hidden Burger"},
                    {"id": 100, "name": "Cheeseburger"},
                ],
            }
        ]
    }
    modifier_calls: list[int] = []

    monkeypatch.setattr(
        "services.knowledge_service.olo._client.make_signed_request",
        lambda *_args, **_kwargs: raw_menu,
    )

    def fake_get_product_modifiers(
        product_id: int,
        _client_id: str,
        _client_secret: str,
        _general_api_endpoint: str,
    ) -> dict[str, Any]:
        modifier_calls.append(product_id)
        return {"optiongroups": []}

    monkeypatch.setattr(
        "services.knowledge_service.olo._client._get_product_modifiers",
        fake_get_product_modifiers,
    )

    bundle = get_restaurant_menu_bundle("259950", "cid", "secret")

    assert modifier_calls == [100]
    assert bundle == {
        "restaurant_id": "259950",
        "menu": raw_menu,
        "modifiers_by_product_id": {"100": {"optiongroups": []}},
    }


def test_get_restaurant_menu_bundle_returns_none_when_modifiers_fail(
    monkeypatch,
) -> None:
    raw_menu = {
        "categories": [
            {
                "id": 10,
                "name": "Burgers",
                "products": [{"id": 100, "name": "Cheeseburger"}],
            }
        ]
    }

    monkeypatch.setattr(
        "services.knowledge_service.olo._client.make_signed_request",
        lambda *_args, **_kwargs: raw_menu,
    )
    monkeypatch.setattr(
        "services.knowledge_service.olo._client._get_product_modifiers",
        lambda *_args, **_kwargs: None,
    )

    assert get_restaurant_menu_bundle("259950", "cid", "secret") is None


def test_get_restaurant_menu_bundle_returns_none_when_menu_fetch_fails(
    monkeypatch,
) -> None:
    def fake_make_signed_request(*_args, **_kwargs) -> dict[str, Any]:
        raise RuntimeError("Olo is unavailable")

    monkeypatch.setattr(
        "services.knowledge_service.olo._client.make_signed_request",
        fake_make_signed_request,
    )

    assert get_restaurant_menu_bundle("259950", "cid", "secret") is None


def test_fetch_and_compile_olo_menu_data_reuses_olo_api_client(monkeypatch) -> None:
    raw_bundle = _raw_olo_bundle()
    calls: list[tuple[str, str, str, str]] = []

    def fake_get_restaurant_menu_bundle(
        restaurant_id: str,
        client_id: str,
        client_secret: str,
        general_api_endpoint: str,
    ) -> dict[str, Any]:
        calls.append((restaurant_id, client_id, client_secret, general_api_endpoint))
        return raw_bundle

    monkeypatch.setattr(
        "services.knowledge_service.olo.menu_data.get_restaurant_menu_bundle",
        fake_get_restaurant_menu_bundle,
    )

    compiled = fetch_and_compile_olo_menu_data(
        restaurant_id="259950",
        client_id="cid",
        client_secret="secret",
        general_api_endpoint="https://ordering.api.olo.com",
        selected_categories=["Burgers"],
        make_unique_categories=["Burgers"],
    )

    assert calls == [
        ("259950", "cid", "secret", "https://ordering.api.olo.com"),
    ]
    assert [item["item_name"] for item in compiled["items"]] == [
        "Burgers / Cheeseburger"
    ]


def test_fetch_and_compile_olo_menu_data_rejects_empty_download(monkeypatch) -> None:
    monkeypatch.setattr(
        "services.knowledge_service.olo.menu_data.get_restaurant_menu_bundle",
        lambda *_args, **_kwargs: None,
    )

    with pytest.raises(ValueError, match="Failed to fetch menu"):
        fetch_and_compile_olo_menu_data(
            restaurant_id="259950",
            client_id="cid",
            client_secret="secret",
            general_api_endpoint="https://ordering.api.olo.com",
        )
