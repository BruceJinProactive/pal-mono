"""Tests for Adora V3 menu asset generation."""

import pytest

from services.adora_v3_menu_service import build_menu_assets


def test_build_menu_assets_generates_prompt_and_compiled_menu() -> None:
    raw_menu = {
        "store_id": "TEST",
        "order_types": [
            {
                "order_type_id": 2,
                "name": "Take-Out",
                "address_required": False,
                "minimum_amount": 0.0,
                "charge": 0.0,
                "wait_time": 15,
            },
            {
                "order_type_id": 3,
                "name": "Delivery",
                "address_required": True,
                "minimum_amount": 10.0,
                "charge": 2.0,
                "wait_time": 35,
            },
        ],
        "categories": [
            {"category_id": 11, "name": "Pizza"},
            {"category_id": 17, "name": "Subs & Pitas"},
        ],
        "modifier_categories": [
            {"modifier_category_id": 2, "name": "Sauce"},
            {"modifier_category_id": 7, "name": "Side Sauce"},
        ],
        "modifier_groups": [
            {"modifier_group_id": 9, "name": "Dipping Sauce 1"},
            {"modifier_group_id": 28, "name": "Extra Dipping Sauce"},
        ],
        "sizes": [
            {"size_id": 4, "name": '8" Small'},
            {"size_id": 20, "name": '8" Full Sub'},
        ],
        "modifiers": [
            {
                "modifier_id": 61,
                "name": "Sweet BBQ Dipping Sauce",
                "modifier_category_id": 2,
            },
            {
                "modifier_id": 415,
                "name": "Sweet BBQ Dipping Sauce",
                "modifier_category_id": 7,
            },
        ],
        "modifier_weights": [
            {"modifier_weight_id": 1, "name": "No", "default": False},
            {"modifier_weight_id": 3, "name": "Regular", "default": True},
        ],
        "items": [
            {
                "item_id": 15,
                "name": "Buffalo Chicken",
                "item_category_id": 11,
                "allow_halving": True,
                "order_types": [
                    {
                        "order_type_id": 2,
                        "sizes": [{"size_id": 4, "allow_halving": True}],
                    }
                ],
                "modifier_groups": [
                    {
                        "modifier_group_id": 9,
                        "allow_halving": False,
                        "modifiers": [{"modifier_id": 61, "default": False}],
                    }
                ],
            },
            {
                "item_id": 71,
                "name": "Buffalo Chicken",
                "item_category_id": 17,
                "allow_halving": False,
                "order_types": [
                    {
                        "order_type_id": 2,
                        "sizes": [{"size_id": 20, "allow_halving": False}],
                    }
                ],
                "modifier_groups": [
                    {
                        "modifier_group_id": 28,
                        "allow_halving": False,
                        "modifiers": [{"modifier_id": 415, "default": False}],
                    }
                ],
            },
        ],
    }

    result = build_menu_assets(raw_menu)

    assert result.english_menu_prompt.startswith("# Adora LLM Menu v9")
    assert "Buffalo Chicken (Pizza)" in result.english_menu_prompt
    assert "Buffalo Chicken (Subs & Pitas)" in result.english_menu_prompt
    assert result.menu_data["version"] == 1
    assert "buffalo chicken pizza" in result.menu_data["items"]
    assert "buffalo chicken subs pitas" in result.menu_data["items"]


def test_build_menu_assets_requires_store_id() -> None:
    with pytest.raises(ValueError, match="non-empty store_id"):
        build_menu_assets({"items": []})
