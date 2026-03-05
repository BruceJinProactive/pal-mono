from __future__ import annotations

import io
import json
import runpy
import sys
from pathlib import Path

import pytest

from services.adora_v3_menu_service import _adora_name_qualifiers as qualifiers
from services.adora_v3_menu_service import _compile_adora_menu_v2 as compile_script
from services.adora_v3_menu_service import _generate_menu_v9 as generate_script


def _build_raw_menu() -> dict[str, object]:
    return {
        "store_id": "TEST",
        "order_types": [
            {
                "order_type_id": 2,
                "name": "Take-Out",
                "address_required": False,
                "minimum_amount": "0",
                "charge": 0,
                "wait_time": "15",
            },
            {
                "order_type_id": 3,
                "name": "Delivery",
                "address_required": True,
                "minimum_amount": 10.0,
                "charge": 2.5,
                "wait_time": 35,
            },
        ],
        "categories": [
            {"category_id": 11, "name": "Pizza"},
            {"category_id": 17, "name": "Subs & Pitas"},
        ],
        "web_categories": [{"web_category_id": 111, "name": "Specialty Pizza"}],
        "modifier_categories": [
            {"modifier_category_id": 2, "name": "Sauce"},
            {"modifier_category_id": 7, "name": "Side Sauce"},
            {"modifier_category_id": 9, "name": "Cheese"},
            {"modifier_category_id": 99, "name": "None"},
        ],
        "modifier_groups": [
            {
                "modifier_group_id": 9,
                "name": "Dipping Sauce 1",
                "min_required_modifier": 1,
                "max_allowed_modifier": 2,
                "must_toggle": True,
            },
            {"modifier_group_id": 28, "name": "Extra Dipping Sauce"},
            {"modifier_group_id": 30, "name": "Cheese Options"},
        ],
        "sizes": [
            {"size_id": 4, "name": '8" Small'},
            {"size_id": 20, "name": '8" Full Sub'},
            {"size_id": 30, "name": '12" Large'},
        ],
        "modifiers": [
            {
                "modifier_id": 61,
                "name": "Sweet BBQ Dipping Sauce",
                "modifier_category_id": 2,
                "description": "Sweet BBQ",
            },
            {
                "modifier_id": 415,
                "name": "Sweet BBQ Dipping Sauce",
                "modifier_category_id": 7,
                "description": "Extra Sweet",
            },
            {
                "modifier_id": 500,
                "name": "Mozzarella",
                "modifier_category_id": 9,
                "description": "Fresh mozzarella",
            },
        ],
        "modifier_weights": [
            {"modifier_weight_id": 1, "name": "No", "default": False},
            {"modifier_weight_id": 2, "name": "Lite", "default": False},
            {"modifier_weight_id": 3, "name": "Regular", "default": True},
            {"modifier_weight_id": 4, "name": "Extra", "default": False},
        ],
        "items": [
            {
                "item_id": 15,
                "name": "Buffalo Chicken",
                "item_category_id": 11,
                "allow_halving": True,
                "prices": [
                    {"size_id": 4, "price": 9.99},
                    {"size_id": 30, "price": 16.99},
                ],
                "order_types": [
                    {
                        "order_type_id": 2,
                        "sizes": [
                            {"size_id": 4, "allow_halving": True},
                            {"size_id": 30, "allow_halving": False},
                        ],
                    },
                    {
                        "order_type_id": 3,
                        "sizes": [{"size_id": 30, "allow_halving": False}],
                    },
                ],
                "modifier_groups": [
                    {
                        "modifier_group_id": 9,
                        "allow_halving": False,
                        "modifiers": [
                            {
                                "modifier_id": 61,
                                "default": False,
                                "price": [
                                    {"size_id": 4, "price": 0.5},
                                    {"size_id": 30, "price": 1.0},
                                ],
                            }
                        ],
                    },
                    {
                        "modifier_group_id": 30,
                        "allow_halving": False,
                        "modifiers": [
                            {"modifier_id": 500, "default": True, "price": []}
                        ],
                    },
                ],
            },
            {
                "item_id": 71,
                "name": "Buffalo Chicken",
                "item_category_id": 17,
                "allow_halving": False,
                "prices": [{"size_id": 20, "price": 10.99}],
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
                        "modifiers": [
                            {
                                "modifier_id": 415,
                                "default": False,
                                "price": [{"size_id": 20, "price": 0.75}],
                            }
                        ],
                    }
                ],
            },
            {
                "item_id": 72,
                "name": "Margherita",
                "web_category_id": 111,
                "allow_halving": False,
                "prices": [{"size_id": 30, "price": 14.5}],
                "order_types": [
                    {
                        "order_type_id": 2,
                        "sizes": [{"size_id": 30, "allow_halving": False}],
                    },
                    {
                        "order_type_id": 3,
                        "sizes": [{"size_id": 30, "allow_halving": False}],
                    },
                ],
                "modifier_groups": [],
            },
        ],
    }


def test_qualifier_helpers_and_maps_cover_ambiguous_names() -> None:
    assert qualifiers.clean_name("  Buffalo   Chicken  ") == "Buffalo Chicken"
    assert qualifiers.clean_name(None) == ""
    assert qualifiers.normalize_name("Buffalo-Chicken!") == "buffalo chicken"
    assert qualifiers._variant_letters(0) == "A"
    assert qualifiers._variant_letters(26) == "AA"
    assert qualifiers._variant_label(1) == "Variant B"
    assert qualifiers._append_qualifier("Buffalo Chicken", "Pizza") == (
        "Buffalo Chicken (Pizza)"
    )

    labels = qualifiers._assign_qualified_labels(
        [
            {
                "key": (2, "B"),
                "base_label": "Combo",
                "category_label": "",
                "size_profile": "",
            },
            {
                "key": (1, "A"),
                "base_label": "Combo",
                "category_label": "",
                "size_profile": "",
            },
        ],
        qualifier_fields=["category_label", "size_profile"],
    )
    assert sorted(labels.values()) == ["Combo (Variant A)", "Combo (Variant B)"]

    maps = qualifiers.build_qualified_name_maps(_build_raw_menu())

    assert maps.item_label_by_id[15] == "Buffalo Chicken (Pizza)"
    assert maps.item_label_by_id[71] == "Buffalo Chicken (Subs & Pitas)"
    assert maps.modifier_occurrence_label[(15, 9, 61)] == (
        "Sweet BBQ Dipping Sauce (Dipping Sauce 1)"
    )
    assert maps.modifier_occurrence_label[(71, 28, 415)] == (
        "Sweet BBQ Dipping Sauce (Extra Dipping Sauce)"
    )
    assert "Mozzarella" in maps.modifier_aliases_by_id[500]


def test_compile_script_functions_and_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    raw_menu = _build_raw_menu()
    input_path = tmp_path / "raw_menu.json"
    output_path = tmp_path / "compiled_menu.json"
    input_path.write_text(json.dumps(raw_menu), encoding="utf-8")

    loaded = compile_script._load_json_object(str(input_path))
    assert loaded["store_id"] == "TEST"

    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(raw_menu)))
    assert compile_script._load_json_object("-")["store_id"] == "TEST"

    compiled = compile_script.compile_menu_v2(raw_menu)
    assert compile_script.compile_menu_v1(raw_menu) == compiled
    assert compiled["version"] == 1
    assert "buffalo chicken pizza" in compiled["items"]
    assert "buffalo chicken subs pitas" in compiled["items"]
    assert "sweet bbq dipping sauce dipping sauce 1" in compiled["modifiers"]

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "compile_adora_menu_v2.py",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--validate",
            "--stats",
        ],
    )
    assert compile_script.main() == 0
    rendered = json.loads(output_path.read_text(encoding="utf-8"))
    assert rendered["store_id"] == "TEST"

    stderr = capsys.readouterr().err
    assert "store_id: TEST" in stderr
    assert "items:" in stderr

    monkeypatch.setattr(
        sys,
        "argv",
        ["compile_adora_menu_v2.py", "--input", str(tmp_path / "missing.json")],
    )
    assert compile_script.main() == 1
    assert "Input file not found" in capsys.readouterr().err


def test_generate_menu_build_verify_render_and_helpers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    raw_menu = _build_raw_menu()
    warnings = generate_script.WarningTracker(max_samples_per_code=2)

    assert not warnings.has_warnings()
    assert (
        generate_script._coerce_float(
            "oops",
            default=1.5,
            warnings=warnings,
            code="bad_float",
            context="charge",
        )
        == 1.5
    )
    assert (
        generate_script._coerce_int(
            "nope",
            default=7,
            warnings=warnings,
            code="bad_int",
            context="wait_time",
        )
        == 7
    )
    assert warnings.has_warnings()
    warnings.print_summary()
    assert "Warnings:" in capsys.readouterr().err

    input_path = tmp_path / "raw_menu.json"
    input_path.write_text(json.dumps(raw_menu), encoding="utf-8")
    assert generate_script.load_menu(input_path)["store_id"] == "TEST"
    assert generate_script.estimate_tokens("12345678") == 2

    model = generate_script.build_llm_menu_v9(raw_menu)
    generate_script.verify_llm_menu_v9(model)
    markdown = generate_script.render_markdown(model, compact=True)
    assert markdown.startswith("# Adora LLM Menu v9")
    assert "Buffalo Chicken (Pizza)" in markdown
    assert "delivery_sizes" in markdown

    item_names = [item["name"] for item in model["items"]]
    assert "Buffalo Chicken (Pizza)" in item_names
    assert "Buffalo Chicken (Subs & Pitas)" in item_names
    assert model["modifier_weights"]["default_weight"] == "Regular"
    assert model["price_templates"]
    assert model["group_templates"]
    assert model["modifier_templates"]

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generate_menu_v9.py",
            "--input",
            str(input_path),
            "--output",
            str(tmp_path / "menu.md"),
            "--count-tokens",
        ],
    )
    generate_script.main()
    stdout = capsys.readouterr().out
    assert "Wrote markdown menu" in stdout
    assert "Approx token count:" in stdout


def test_generate_helpers_handle_invalid_shapes_and_verify_rejects_bad_models(
    capsys: pytest.CaptureFixture[str],
) -> None:
    warnings = generate_script.WarningTracker()

    order_types = generate_script._extract_order_type_metadata(
        {"order_types": "bad-shape"},
        warnings,
    )
    assert order_types["TakeOut"]["order_type_id"] == 2

    (
        size_name_by_id,
        modifier_name_by_id,
        top_group_by_id,
    ) = generate_script._build_name_lookups(
        {
            "sizes": "bad",
            "modifiers": "bad",
            "modifier_groups": "bad",
        },
        warnings,
    )
    assert size_name_by_id == {}
    assert modifier_name_by_id == {}
    assert top_group_by_id == {}

    item = {
        "name": "Broken Pizza",
        "allow_halving": True,
        "prices": "bad",
        "order_types": [
            {"order_type_id": 999, "sizes": []},
            {"order_type_id": 2, "sizes": "bad"},
            {"order_type_id": 3, "sizes": [{"size_id": "bad"}]},
        ],
        "modifier_groups": "bad",
    }
    (
        sizes_by_order_type,
        size_half_half,
        size_prices,
    ) = generate_script._extract_sizes_by_order_type(
        item,
        {4: '8" Small'},
        warnings,
    )
    assert sizes_by_order_type["TakeOut"] == []
    assert size_half_half["Delivery"] == {}
    assert size_prices == {}

    group_rows, default_modifiers = generate_script._extract_item_groups(
        {
            "name": "Broken Pizza",
            "item_id": 9,
            "modifier_groups": [
                {"modifier_group_id": 3, "modifiers": "bad"},
                {
                    "modifier_group_id": 4,
                    "name": "Extras",
                    "modifiers": [{"modifier_id": 55, "default": True, "price": "bad"}],
                },
            ],
        },
        modifier_name_by_id={55: "Cheese"},
        modifier_occurrence_name_by_key={(9, 4, 55): "Cheese"},
        top_group_by_id={3: {"name": "Fallback Group"}},
        size_name_by_id={},
        warnings=warnings,
    )
    assert default_modifiers == ["Cheese"]
    assert group_rows == [
        {
            "name": "Extras",
            "supports_half_half": False,
            "min_required": 0,
            "max_allowed": 0,
            "must_toggle": False,
            "allowed_modifiers": ["Cheese"],
        }
    ]

    warnings.print_summary()
    assert "invalid_group_modifiers_shape" in capsys.readouterr().err

    with pytest.raises(ValueError, match="Missing required top-level key"):
        generate_script.verify_llm_menu_v9({})


def test_runpy_executes_script_entrypoints(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw_menu = _build_raw_menu()
    input_path = tmp_path / "raw_menu.json"
    input_path.write_text(json.dumps(raw_menu), encoding="utf-8")

    compile_output = tmp_path / "compiled.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "compile_adora_menu_v2.py",
            "--input",
            str(input_path),
            "--output",
            str(compile_output),
        ],
    )
    with pytest.raises(SystemExit) as compile_exit:
        runpy.run_module(
            "services.adora_v3_menu_service._compile_adora_menu_v2",
            run_name="__main__",
        )
    assert compile_exit.value.code == 0
    assert compile_output.exists()

    markdown_output = tmp_path / "menu.md"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generate_menu_v9.py",
            "--input",
            str(input_path),
            "--output",
            str(markdown_output),
            "--no-compact",
        ],
    )
    runpy.run_module(
        "services.adora_v3_menu_service._generate_menu_v9",
        run_name="__main__",
    )
    assert markdown_output.exists()
