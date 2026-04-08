"""Tests for services/eval_service/_user_simulator.py.

The UserSimulator implementation lives in pal-agents (evals.simulator).
These tests verify the re-export and the END_SENTINEL constant used by
the runner to detect conversation termination.
"""

from __future__ import annotations

from pal_agents.evals.simulator import UserSimulator as SDKUserSimulator

from services.eval_service._user_simulator import END_SENTINEL, UserSimulator


class TestReExports:
    def test_user_simulator_is_sdk_class(self) -> None:
        """UserSimulator re-exported from pal-agents SDK."""
        assert UserSimulator is SDKUserSimulator

    def test_end_sentinel_value(self) -> None:
        assert END_SENTINEL == "[END]"
