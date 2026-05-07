"""Tests for build_help_page in Slack formatting module."""

from services.slack_service._formatting import build_help_page


class TestBuildHelpPage:
    def test_returns_blocks_structure(self) -> None:
        result = build_help_page()
        assert "blocks" in result
        assert isinstance(result["blocks"], list)

    def test_starts_with_header_block(self) -> None:
        blocks = build_help_page()["blocks"]
        assert blocks[0]["type"] == "header"
        assert "Mercury" in blocks[0]["text"]["text"]

    def test_ends_with_context_block(self) -> None:
        blocks = build_help_page()["blocks"]
        assert blocks[-1]["type"] == "context"

    def test_has_reports_section_with_buttons(self) -> None:
        blocks = build_help_page()["blocks"]
        actions_blocks = [b for b in blocks if b["type"] == "actions"]
        # First actions block is reports
        report_actions = actions_blocks[0]
        action_ids = [e["action_id"] for e in report_actions["elements"]]
        assert "mercury_daily" in action_ids
        assert "mercury_weekly" in action_ids
        assert "mercury_monthly" in action_ids
        assert "mercury_custom_report" in action_ids
        assert "mercury_last_hours" in action_ids
        assert "mercury_date_range" in action_ids

    def test_has_feedback_section_with_buttons(self) -> None:
        blocks = build_help_page()["blocks"]
        actions_blocks = [b for b in blocks if b["type"] == "actions"]
        feedback_actions = actions_blocks[1]
        action_ids = [e["action_id"] for e in feedback_actions["elements"]]
        assert "mercury_feedback_all" in action_ids
        assert "mercury_feedback_lookup" in action_ids

    def test_has_camera_section_with_buttons(self) -> None:
        blocks = build_help_page()["blocks"]
        actions_blocks = [b for b in blocks if b["type"] == "actions"]
        camera_actions = actions_blocks[2]
        action_ids = [e["action_id"] for e in camera_actions["elements"]]
        assert "mercury_camera_all" in action_ids
        assert "mercury_camera_filter" in action_ids

    def test_has_subscription_section(self) -> None:
        blocks = build_help_page()["blocks"]
        actions_blocks = [b for b in blocks if b["type"] == "actions"]
        subscription_actions = actions_blocks[3]
        action_ids = [e["action_id"] for e in subscription_actions["elements"]]
        assert "mercury_subscription" in action_ids

    def test_has_internal_tools_section_with_both_buttons(self) -> None:
        blocks = build_help_page()["blocks"]
        actions_blocks = [b for b in blocks if b["type"] == "actions"]
        tools_actions = actions_blocks[5]
        action_ids = [e["action_id"] for e in tools_actions["elements"]]
        assert "mercury_tool_feedback" in action_ids
        assert "mercury_tool_request" in action_ids

    def test_submit_feedback_button_has_primary_style(self) -> None:
        blocks = build_help_page()["blocks"]
        actions_blocks = [b for b in blocks if b["type"] == "actions"]
        tools_actions = actions_blocks[5]
        feedback_btn = next(
            e
            for e in tools_actions["elements"]
            if e["action_id"] == "mercury_tool_feedback"
        )
        assert feedback_btn.get("style") == "primary"

    def test_request_new_tool_button_exists(self) -> None:
        blocks = build_help_page()["blocks"]
        actions_blocks = [b for b in blocks if b["type"] == "actions"]
        tools_actions = actions_blocks[5]
        request_btn = next(
            e
            for e in tools_actions["elements"]
            if e["action_id"] == "mercury_tool_request"
        )
        assert request_btn["text"]["text"] == "Request New Tool..."

    def test_internal_tools_section_title(self) -> None:
        blocks = build_help_page()["blocks"]
        section_blocks = [b for b in blocks if b["type"] == "section"]
        tools_section = next(
            b for b in section_blocks if "Internal Tools" in b["text"]["text"]
        )
        assert "Submit feedback or request a new tool" in tools_section["text"]["text"]

    def test_block_count_under_slack_limit(self) -> None:
        blocks = build_help_page()["blocks"]
        assert len(blocks) <= 50

    def test_all_action_ids_have_mercury_prefix(self) -> None:
        blocks = build_help_page()["blocks"]
        for block in blocks:
            if block["type"] == "actions":
                for element in block["elements"]:
                    assert element["action_id"].startswith("mercury_")
