"""Re-exports UserSimulator from pal-agents SDK.

The SDK's UserSimulator (pal_agents.evals.simulator) handles LLM-based
user simulation for ai_driven eval turns. This module re-exports it
along with the END_SENTINEL constant used by the runner.
"""

from __future__ import annotations

from pal_agents.evals.simulator import UserSimulator

# Sentinel value indicating conversation should end
END_SENTINEL = "[END]"

__all__ = ["END_SENTINEL", "UserSimulator"]
