"""AgentDriver factory for evaluation runs.

Creates the appropriate driver based on driver_mode configuration.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

from pal_agents.spec import Spec

from services.eval_service._inprocess_driver import InProcessDriver
from utils.log import logger


def create_driver(
    driver_mode: str,
    project_identifier: str,
    channel: str = "api",
    scenario_id: str | None = None,
    customer_phone: str | None = None,
    spec_modifier: Callable[[Spec], None] | None = None,
) -> InProcessDriver:
    """Create an AgentDriver for the given mode.

    Each call generates a unique ``sender_identifier`` so the chat service
    creates a fresh conversation (user + conversation) per scenario,
    preventing tool-call bleed between scenarios.

    Args:
        driver_mode: One of "http" or "direct".
        project_identifier: Channel-specific identifier for routing messages.
        channel: Channel type (e.g. "api", "voice"). Defaults to "api".
        scenario_id: Optional scenario ID included in the sender for traceability.
        customer_phone: Optional phone number to inject into ``RuntimeContext``
            for the scenario.
        spec_modifier: Optional ``Spec`` mutator. If ``None``, the driver
            installs ``apply_eval_safety`` by default so real orders are never
            placed from an eval run.

    Returns:
        An AgentDriver instance.

    Raises:
        ValueError: If driver_mode is not recognized.
    """
    if driver_mode == "http":
        unique_id = uuid.uuid4().hex[:12]
        sender = f"eval-{scenario_id or 'anon'}-{unique_id}@test.com"
        logger.info(
            "Creating InProcessDriver",
            extra={
                "project": project_identifier,
                "channel": channel,
                "sender": sender,
            },
        )
        return InProcessDriver(
            recipient_identifier=project_identifier,
            sender_identifier=sender,
            channel=channel,
            customer_phone=customer_phone,
            spec_modifier=spec_modifier,
        )

    if driver_mode == "direct":
        raise NotImplementedError(
            "DirectDriver requires agent Spec construction — not yet wired. "
            "Use driver_mode='http' with InProcessDriver."
        )

    raise ValueError(
        f"Unknown driver_mode: {driver_mode!r}. "
        "Expected 'http' or 'direct'. Voice mode is handled by _run_scenario_for_mode."
    )
