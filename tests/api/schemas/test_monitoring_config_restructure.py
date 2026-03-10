"""Tests for monitoring config restructure — schema validation.

Validates business requirements for the new context/criteria/flag fields
in AIAnalysisRules, ReferenceImage, and UpdateMonitoringConfigRequest.
"""

import pytest
from pydantic import ValidationError

from api.schemas.operations.monitoring import (
    AIAnalysisRules,
    ReferenceImage,
    UpdateMonitoringConfigRequest,
)


class TestAIAnalysisRulesSchema:
    """Test AIAnalysisRules Pydantic model validation."""

    def test_context_field_accepted(self) -> None:
        """New configs should accept context as the primary description field."""
        rules = AIAnalysisRules(
            context="Kitchen area during business hours",
            prompt=None,
            structured_output=None,
            monitoring_time_window=None,
        )
        assert rules.context == "Kitchen area during business hours"

    def test_prompt_field_accepted_for_backward_compat(self) -> None:
        """Legacy configs using prompt should still be accepted."""
        rules = AIAnalysisRules(
            prompt="Check if kitchen is clean",
            context=None,
            structured_output=None,
            monitoring_time_window=None,
        )
        assert rules.prompt == "Check if kitchen is clean"

    def test_prompt_only_copies_to_context(self) -> None:
        """When only prompt is provided, it should be copied to context."""
        rules = AIAnalysisRules(
            prompt="Check if kitchen is clean",
            context=None,
            structured_output=None,
            monitoring_time_window=None,
        )
        assert rules.context == "Check if kitchen is clean"

    def test_neither_context_nor_prompt_raises_validation_error(self) -> None:
        """Must provide at least one of context or prompt."""
        with pytest.raises(ValidationError, match="context.*prompt"):
            AIAnalysisRules(
                context=None,
                prompt=None,
                structured_output=None,
                monitoring_time_window=None,
            )

    def test_context_takes_precedence_when_both_provided(self) -> None:
        """When both provided, context keeps its own value."""
        rules = AIAnalysisRules(
            context="New context",
            prompt="Old prompt",
            structured_output=None,
            monitoring_time_window=None,
        )
        assert rules.context == "New context"
        assert rules.prompt == "Old prompt"

    def test_pass_criteria_defaults_to_empty_list(self) -> None:
        """pass_criteria should default to empty list for legacy configs."""
        rules = AIAnalysisRules(
            context="test",
            prompt=None,
            structured_output=None,
            monitoring_time_window=None,
        )
        assert rules.pass_criteria == []

    def test_fail_criteria_defaults_to_empty_list(self) -> None:
        """fail_criteria should default to empty list for legacy configs."""
        rules = AIAnalysisRules(
            context="test",
            prompt=None,
            structured_output=None,
            monitoring_time_window=None,
        )
        assert rules.fail_criteria == []

    def test_pass_criteria_accepts_string_list(self) -> None:
        """pass_criteria should accept a list of criterion strings."""
        rules = AIAnalysisRules(
            context="test",
            prompt=None,
            structured_output=None,
            monitoring_time_window=None,
            pass_criteria=["All surfaces clean", "Equipment stored"],
        )
        assert len(rules.pass_criteria) == 2
        assert "All surfaces clean" in rules.pass_criteria

    def test_fail_criteria_accepts_string_list(self) -> None:
        """fail_criteria should accept a list of criterion strings."""
        rules = AIAnalysisRules(
            context="test",
            prompt=None,
            structured_output=None,
            monitoring_time_window=None,
            fail_criteria=["Visible debris", "Equipment left out"],
        )
        assert len(rules.fail_criteria) == 2
        assert "Visible debris" in rules.fail_criteria

    def test_criteria_item_max_length_500(self) -> None:
        """Each criterion must be at most 500 characters."""
        with pytest.raises(ValidationError, match="500"):
            AIAnalysisRules(
                context="test",
                prompt=None,
                structured_output=None,
                monitoring_time_window=None,
                pass_criteria=["x" * 501],
            )

    def test_criteria_item_min_length_1(self) -> None:
        """Each criterion must be at least 1 character."""
        with pytest.raises(ValidationError, match="1 character"):
            AIAnalysisRules(
                context="test",
                prompt=None,
                structured_output=None,
                monitoring_time_window=None,
                pass_criteria=[""],
            )

    def test_context_whitespace_only_raises_validation_error(self) -> None:
        """Whitespace-only context should be rejected."""
        with pytest.raises(ValidationError):
            AIAnalysisRules(
                context="   ",
                prompt=None,
                structured_output=None,
                monitoring_time_window=None,
            )

    def test_pass_criteria_whitespace_only_rejected(self) -> None:
        """Whitespace-only pass_criteria items should be rejected."""
        with pytest.raises(ValidationError):
            AIAnalysisRules(
                context="test",
                prompt=None,
                structured_output=None,
                monitoring_time_window=None,
                pass_criteria=["   "],
            )

    def test_fail_criteria_whitespace_only_rejected(self) -> None:
        """Whitespace-only fail_criteria items should be rejected."""
        with pytest.raises(ValidationError):
            AIAnalysisRules(
                context="test",
                prompt=None,
                structured_output=None,
                monitoring_time_window=None,
                fail_criteria=["   "],
            )

    def test_reference_images_optional_can_be_empty(self) -> None:
        """Reference images should be optional (empty list allowed)."""
        rules = AIAnalysisRules(
            context="test",
            prompt=None,
            structured_output=None,
            monitoring_time_window=None,
            reference_images=[],
        )
        assert rules.reference_images == []

    def test_model_dump_includes_all_new_fields(self) -> None:
        """model_dump should include context, pass_criteria, fail_criteria."""
        rules = AIAnalysisRules(
            context="Kitchen check",
            prompt=None,
            structured_output=None,
            monitoring_time_window=None,
            pass_criteria=["Clean"],
            fail_criteria=["Dirty"],
        )
        dumped = rules.model_dump()
        assert "context" in dumped
        assert "pass_criteria" in dumped
        assert "fail_criteria" in dumped


class TestReferenceImageSchema:
    """Test ReferenceImage flag field."""

    def test_flag_defaults_to_pass(self) -> None:
        """Flag should default to 'pass' when not specified."""
        img = ReferenceImage(id="uuid-1", url="s3://test", description="Clean kitchen")
        assert img.flag == "pass"

    def test_flag_accepts_pass(self) -> None:
        """Should accept 'pass' flag value."""
        img = ReferenceImage(
            id="uuid-1", url="s3://test", description="Clean", flag="pass"
        )
        assert img.flag == "pass"

    def test_flag_accepts_fail(self) -> None:
        """Should accept 'fail' flag value."""
        img = ReferenceImage(
            id="uuid-1", url="s3://test", description="Dirty", flag="fail"
        )
        assert img.flag == "fail"

    def test_flag_rejects_invalid_value(self) -> None:
        """Should reject flag values other than 'pass' or 'fail'."""
        with pytest.raises(ValidationError):
            ReferenceImage(
                id="uuid-1",
                url="s3://test",
                description="test",
                flag="warning",  # type: ignore[arg-type]
            )

    def test_flag_included_in_model_dump(self) -> None:
        """model_dump should include flag field."""
        img = ReferenceImage(
            id="uuid-1", url="s3://test", description="test", flag="fail"
        )
        dumped = img.model_dump()
        assert dumped["flag"] == "fail"


class TestUpdateMonitoringConfigRequest:
    """Test update request schema with new fields."""

    def test_context_field_optional(self) -> None:
        """context should be optional on update."""
        req = UpdateMonitoringConfigRequest(
            context="Updated context",
            name=None,
            description=None,
            prompt=None,
            pass_criteria=None,
            fail_criteria=None,
            structured_output=None,
            model=None,
            enabled=None,
            monitoring_time_window=None,
        )
        assert req.context == "Updated context"

    def test_pass_criteria_optional(self) -> None:
        """pass_criteria should be optional on update."""
        req = UpdateMonitoringConfigRequest(
            pass_criteria=["New criterion"],
            name=None,
            description=None,
            context=None,
            prompt=None,
            fail_criteria=None,
            structured_output=None,
            model=None,
            enabled=None,
            monitoring_time_window=None,
        )
        assert req.pass_criteria == ["New criterion"]

    def test_fail_criteria_optional(self) -> None:
        """fail_criteria should be optional on update."""
        req = UpdateMonitoringConfigRequest(
            fail_criteria=["New fail criterion"],
            name=None,
            description=None,
            context=None,
            prompt=None,
            pass_criteria=None,
            structured_output=None,
            model=None,
            enabled=None,
            monitoring_time_window=None,
        )
        assert req.fail_criteria == ["New fail criterion"]

    def test_all_fields_none_by_default(self) -> None:
        """All fields should default to None."""
        req = UpdateMonitoringConfigRequest(
            name=None,
            description=None,
            context=None,
            prompt=None,
            pass_criteria=None,
            fail_criteria=None,
            structured_output=None,
            model=None,
            enabled=None,
            monitoring_time_window=None,
        )
        assert req.context is None
        assert req.prompt is None
        assert req.pass_criteria is None
        assert req.fail_criteria is None

    def test_criteria_validation_on_update(self) -> None:
        """Criteria items on update should also respect length limits."""
        with pytest.raises(ValidationError, match="500"):
            UpdateMonitoringConfigRequest(
                pass_criteria=["x" * 501],
                name=None,
                description=None,
                context=None,
                prompt=None,
                fail_criteria=None,
                structured_output=None,
                model=None,
                enabled=None,
                monitoring_time_window=None,
            )

    def test_empty_criteria_item_rejected_on_update(self) -> None:
        """Empty string criteria should be rejected on update."""
        with pytest.raises(ValidationError, match="1 character"):
            UpdateMonitoringConfigRequest(
                fail_criteria=[""],
                name=None,
                description=None,
                context=None,
                prompt=None,
                pass_criteria=None,
                structured_output=None,
                model=None,
                enabled=None,
                monitoring_time_window=None,
            )

    def test_context_whitespace_only_rejected_on_update(self) -> None:
        """Whitespace-only context should be rejected on update."""
        with pytest.raises(ValidationError):
            UpdateMonitoringConfigRequest(
                context="   ",
                name=None,
                description=None,
                prompt=None,
                pass_criteria=None,
                fail_criteria=None,
                structured_output=None,
                model=None,
                enabled=None,
                monitoring_time_window=None,
            )

    def test_pass_criteria_whitespace_only_rejected_on_update(self) -> None:
        """Whitespace-only pass_criteria should be rejected on update."""
        with pytest.raises(ValidationError):
            UpdateMonitoringConfigRequest(
                pass_criteria=["   "],
                name=None,
                description=None,
                context=None,
                prompt=None,
                fail_criteria=None,
                structured_output=None,
                model=None,
                enabled=None,
                monitoring_time_window=None,
            )

    def test_fail_criteria_whitespace_only_rejected_on_update(self) -> None:
        """Whitespace-only fail_criteria should be rejected on update."""
        with pytest.raises(ValidationError):
            UpdateMonitoringConfigRequest(
                fail_criteria=["   "],
                name=None,
                description=None,
                context=None,
                prompt=None,
                pass_criteria=None,
                structured_output=None,
                model=None,
                enabled=None,
                monitoring_time_window=None,
            )
