"""Tests for E1: Tool Call Verification evaluator."""

from services.eval_service.evaluators.tool_call import evaluate_tool_calls


class TestEvaluateToolCalls:
    def test_exact_match_all_tools(self) -> None:
        expected = [{"tool": "query_hours"}, {"tool": "query_menu"}]
        actual = [{"tool_name": "query_hours"}, {"tool_name": "query_menu"}]

        result = evaluate_tool_calls(expected, actual)

        assert result.score == 1.0
        assert result.passed is True
        assert result.metric_name == "tool_call_verification"

    def test_partial_match(self) -> None:
        expected = [{"tool": "query_hours"}, {"tool": "query_menu"}]
        actual = [{"tool_name": "query_hours"}]

        result = evaluate_tool_calls(expected, actual)

        assert result.score == 0.5
        assert result.passed is False
        assert "Missing" in result.reason

    def test_no_expected_tools(self) -> None:
        result = evaluate_tool_calls([], [{"tool_name": "some_tool"}])

        assert result.score == 1.0
        assert result.passed is True
        assert "No tool calls expected" in result.reason

    def test_missing_all_tools(self) -> None:
        expected = [{"tool": "query_hours"}]
        actual: list[dict[str, object]] = []

        result = evaluate_tool_calls(expected, actual)

        assert result.score == 0.0
        assert result.passed is False

    def test_unexpected_tools_noted(self) -> None:
        expected = [{"tool": "query_hours"}]
        actual = [{"tool_name": "query_hours"}, {"tool_name": "unexpected_tool"}]

        result = evaluate_tool_calls(expected, actual)

        assert result.score == 1.0
        assert result.passed is True
        assert "Unexpected" in result.reason

    def test_tool_key_fallback(self) -> None:
        """Actual tool calls can use 'tool' key instead of 'tool_name'."""
        expected = [{"tool": "query_hours"}]
        actual = [{"tool": "query_hours"}]

        result = evaluate_tool_calls(expected, actual)

        assert result.score == 1.0
        assert result.passed is True

    def test_empty_expected_and_actual(self) -> None:
        result = evaluate_tool_calls([], [])

        assert result.score == 1.0
        assert result.passed is True

    def test_multiplicity_partial_match(self) -> None:
        """Counter-based matching: expected twice, actual once => 1/2."""
        expected = [{"tool": "query_hours"}, {"tool": "query_hours"}]
        actual = [{"tool_name": "query_hours"}]

        result = evaluate_tool_calls(expected, actual)

        assert result.score == 0.5
        assert result.passed is False
        assert "Missing" in result.reason

    def test_multiplicity_exact_match(self) -> None:
        """Counter-based matching: expected twice, actual twice => 2/2."""
        expected = [{"tool": "query_hours"}, {"tool": "query_hours"}]
        actual = [{"tool_name": "query_hours"}, {"tool_name": "query_hours"}]

        result = evaluate_tool_calls(expected, actual)

        assert result.score == 1.0
        assert result.passed is True

    def test_multiplicity_extra_actual(self) -> None:
        """Counter-based matching: expected once, actual twice => 1/1 with unexpected."""
        expected = [{"tool": "query_hours"}]
        actual = [{"tool_name": "query_hours"}, {"tool_name": "query_hours"}]

        result = evaluate_tool_calls(expected, actual)

        assert result.score == 1.0
        assert result.passed is True
        assert "Unexpected" in result.reason
