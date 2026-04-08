"""AgentDriver factory for evaluation runs.

Creates the appropriate driver based on driver_mode configuration.
"""

from __future__ import annotations

from services.eval_service._inprocess_driver import InProcessDriver
from utils.log import logger


def create_driver(
    driver_mode: str,
    project_identifier: str,
) -> InProcessDriver:
    """Create an AgentDriver for the given mode.

    Args:
        driver_mode: One of "http" or "direct".
        project_identifier: Project identifier for routing messages.

    Returns:
        An AgentDriver instance.

    Raises:
        ValueError: If driver_mode is not recognized.
    """
    if driver_mode == "http":
        logger.info(
            "Creating InProcessDriver",
            extra={"project": project_identifier},
        )
        return InProcessDriver(
            recipient_identifier=project_identifier,
        )

    if driver_mode == "direct":
        raise NotImplementedError(
            "DirectDriver requires agent Spec construction — not yet wired. "
            "Use driver_mode='http' with InProcessDriver."
        )

    raise ValueError(
        f"Unknown driver_mode: {driver_mode!r}. Expected 'http' or 'direct'."
    )
