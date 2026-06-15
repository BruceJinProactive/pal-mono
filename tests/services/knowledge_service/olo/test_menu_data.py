from __future__ import annotations

from typing import Any

import pytest
from pal_agents.menu_assets.olo import OloMenuCompileError

from services.knowledge_service.olo import compile_olo_menu_data


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
