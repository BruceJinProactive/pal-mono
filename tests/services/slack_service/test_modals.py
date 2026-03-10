"""Tests for Slack modal builders."""

from services.slack_service._modals import (
    build_camera_filter_modal,
    build_date_range_modal,
    build_feedback_lookup_modal,
    build_last_hours_modal,
    build_report_modal,
    build_subscription_lookup_modal,
    build_tool_feedback_modal,
    build_tool_request_modal,
)


class TestBuildToolFeedbackModal:
    def test_returns_modal_with_correct_callback_id(self) -> None:
        result = build_tool_feedback_modal([])
        assert result["type"] == "modal"
        assert result["callback_id"] == "mercury_tool_feedback_submit"

    def test_populates_tool_options_from_tools_list(self) -> None:
        tools = [
            {"name": "Analytics Report", "page_id": "abc123"},
            {"name": "Camera Monitor", "page_id": "def456"},
        ]
        result = build_tool_feedback_modal(tools)
        tool_block = result["blocks"][0]
        options = tool_block["element"]["options"]
        assert len(options) == 2
        assert options[0]["text"]["text"] == "Analytics Report"
        assert options[0]["value"] == "abc123"
        assert options[1]["text"]["text"] == "Camera Monitor"

    def test_shows_empty_state_when_no_tools(self) -> None:
        result = build_tool_feedback_modal([])
        assert "submit" not in result
        assert result["close"]["text"] == "Close"
        assert len(result["blocks"]) == 1
        assert result["blocks"][0]["type"] == "section"
        assert "No internal tools found" in result["blocks"][0]["text"]["text"]

    def test_stores_channel_id_in_private_metadata(self) -> None:
        result = build_tool_feedback_modal([], channel_id="C123")
        assert result["private_metadata"] == "C123"

    def test_has_four_input_blocks(self) -> None:
        tools = [{"name": "Tool", "page_id": "id1"}]
        result = build_tool_feedback_modal(tools)
        assert len(result["blocks"]) == 4

    def test_request_type_options_include_all_types(self) -> None:
        result = build_tool_feedback_modal([{"name": "Tool", "page_id": "id1"}])
        type_block = result["blocks"][1]
        option_values = [o["value"] for o in type_block["element"]["options"]]
        assert "Bug" in option_values
        assert "Improvement" in option_values
        assert "Feature request" in option_values
        assert "Usability" in option_values
        assert "Access/permission" in option_values
        assert "Question" in option_values
        assert "Other" in option_values

    def test_priority_options(self) -> None:
        result = build_tool_feedback_modal([{"name": "Tool", "page_id": "id1"}])
        priority_block = result["blocks"][2]
        option_values = [o["value"] for o in priority_block["element"]["options"]]
        assert option_values == ["P0", "P1", "P2", "P3"]

    def test_truncates_long_tool_names(self) -> None:
        tools = [{"name": "A" * 100, "page_id": "id1"}]
        result = build_tool_feedback_modal(tools)
        option_text = result["blocks"][0]["element"]["options"][0]["text"]["text"]
        assert len(option_text) <= 75

    def test_feedback_text_has_max_length(self) -> None:
        tools = [{"name": "Tool", "page_id": "id1"}]
        result = build_tool_feedback_modal(tools)
        feedback_block = result["blocks"][3]
        assert feedback_block["element"]["max_length"] == 2000


class TestBuildToolRequestModal:
    def test_returns_modal_with_correct_callback_id(self) -> None:
        result = build_tool_request_modal()
        assert result["type"] == "modal"
        assert result["callback_id"] == "mercury_tool_request_submit"

    def test_has_four_input_blocks(self) -> None:
        result = build_tool_request_modal()
        assert len(result["blocks"]) == 4

    def test_request_title_is_required(self) -> None:
        result = build_tool_request_modal()
        request_block = result["blocks"][0]
        assert request_block["block_id"] == "request_title"
        assert request_block.get("optional") is not True

    def test_priority_is_required(self) -> None:
        result = build_tool_request_modal()
        priority_block = result["blocks"][1]
        assert priority_block["block_id"] == "priority"
        assert priority_block.get("optional") is not True

    def test_problem_context_is_optional(self) -> None:
        result = build_tool_request_modal()
        problem_block = result["blocks"][2]
        assert problem_block["block_id"] == "problem_context"
        assert problem_block["optional"] is True

    def test_proposed_solution_is_optional(self) -> None:
        result = build_tool_request_modal()
        solution_block = result["blocks"][3]
        assert solution_block["block_id"] == "proposed_solution"
        assert solution_block["optional"] is True

    def test_text_inputs_have_max_length(self) -> None:
        result = build_tool_request_modal()
        for block in result["blocks"]:
            elem = block["element"]
            if elem["type"] == "plain_text_input":
                assert (
                    elem["max_length"] == 2000
                ), f"block {block['block_id']} missing max_length"

    def test_stores_channel_id_in_private_metadata(self) -> None:
        result = build_tool_request_modal(channel_id="C456")
        assert result["private_metadata"] == "C456"

    def test_priority_options_match_p0_through_p3(self) -> None:
        result = build_tool_request_modal()
        priority_block = result["blocks"][1]
        values = [o["value"] for o in priority_block["element"]["options"]]
        assert values == ["P0", "P1", "P2", "P3"]

    def test_multiline_inputs_for_text_fields(self) -> None:
        result = build_tool_request_modal()
        problem_block = result["blocks"][2]
        solution_block = result["blocks"][3]
        assert problem_block["element"]["multiline"] is True
        assert solution_block["element"]["multiline"] is True


class TestBuildReportModal:
    def test_returns_modal_with_correct_callback_id(self) -> None:
        result = build_report_modal()
        assert result["callback_id"] == "mercury_report_submit"

    def test_has_period_and_account_blocks(self) -> None:
        result = build_report_modal()
        block_ids = [b["block_id"] for b in result["blocks"]]
        assert "report_period" in block_ids
        assert "account_name" in block_ids

    def test_account_name_is_optional(self) -> None:
        result = build_report_modal()
        account_block = next(
            b for b in result["blocks"] if b["block_id"] == "account_name"
        )
        assert account_block["optional"] is True


class TestBuildFeedbackLookupModal:
    def test_returns_modal_with_correct_callback_id(self) -> None:
        result = build_feedback_lookup_modal()
        assert result["callback_id"] == "mercury_feedback_lookup_submit"

    def test_has_client_name_and_lookup_type_blocks(self) -> None:
        result = build_feedback_lookup_modal()
        block_ids = [b["block_id"] for b in result["blocks"]]
        assert "client_name" in block_ids
        assert "lookup_type" in block_ids


class TestBuildCameraFilterModal:
    def test_returns_modal_with_correct_callback_id(self) -> None:
        result = build_camera_filter_modal()
        assert result["callback_id"] == "mercury_camera_filter_submit"

    def test_account_names_is_optional(self) -> None:
        result = build_camera_filter_modal()
        assert result["blocks"][0]["optional"] is True


class TestBuildLastHoursModal:
    def test_returns_modal_with_correct_callback_id(self) -> None:
        result = build_last_hours_modal()
        assert result["callback_id"] == "mercury_last_hours_submit"

    def test_has_hours_and_account_blocks(self) -> None:
        result = build_last_hours_modal()
        block_ids = [b["block_id"] for b in result["blocks"]]
        assert "hours" in block_ids
        assert "account_name" in block_ids

    def test_account_name_is_optional(self) -> None:
        result = build_last_hours_modal()
        account_block = next(
            b for b in result["blocks"] if b["block_id"] == "account_name"
        )
        assert account_block["optional"] is True

    def test_stores_channel_id_in_private_metadata(self) -> None:
        result = build_last_hours_modal(channel_id="C789")
        assert result["private_metadata"] == "C789"


class TestBuildDateRangeModal:
    def test_returns_modal_with_correct_callback_id(self) -> None:
        result = build_date_range_modal()
        assert result["callback_id"] == "mercury_date_range_submit"

    def test_has_start_end_date_and_account_blocks(self) -> None:
        result = build_date_range_modal()
        block_ids = [b["block_id"] for b in result["blocks"]]
        assert "start_date" in block_ids
        assert "end_date" in block_ids
        assert "account_name" in block_ids

    def test_uses_datepicker_elements(self) -> None:
        result = build_date_range_modal()
        start_block = next(b for b in result["blocks"] if b["block_id"] == "start_date")
        end_block = next(b for b in result["blocks"] if b["block_id"] == "end_date")
        assert start_block["element"]["type"] == "datepicker"
        assert end_block["element"]["type"] == "datepicker"

    def test_account_name_is_optional(self) -> None:
        result = build_date_range_modal()
        account_block = next(
            b for b in result["blocks"] if b["block_id"] == "account_name"
        )
        assert account_block["optional"] is True

    def test_stores_channel_id_in_private_metadata(self) -> None:
        result = build_date_range_modal(channel_id="C999")
        assert result["private_metadata"] == "C999"


class TestBuildSubscriptionLookupModal:
    def test_returns_modal_with_correct_callback_id(self) -> None:
        result = build_subscription_lookup_modal()
        assert result["callback_id"] == "mercury_subscription_submit"

    def test_has_account_name_block(self) -> None:
        result = build_subscription_lookup_modal()
        assert result["blocks"][0]["block_id"] == "account_name"
