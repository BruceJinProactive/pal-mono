"""AgentDriver factory for evaluation runs.

Creates the appropriate driver based on driver_mode configuration.
"""

from __future__ import annotations

import os

from pal_agents.evals.drivers import AgentDriver, HTTPDriver

from utils.log import logger

_DEFAULT_BASE_URL = "http://localhost:8000"


def create_driver(
    driver_mode: str,
    project_identifier: str,
) -> AgentDriver:
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
        base_url = os.environ.get("EVAL_API_BASE_URL", _DEFAULT_BASE_URL)
        logger.info(
            "Creating HTTPDriver",
            extra={"base_url": base_url, "project": project_identifier},
        )
        return HTTPDriver(
            base_url=base_url,
            recipient_identifier=project_identifier,
        )

    if driver_mode == "direct":
        raise NotImplementedError(
            "DirectDriver requires agent Spec construction — not yet wired. "
            "Use driver_mode='http' with a running API server."
        )

    raise ValueError(
        f"Unknown driver_mode: {driver_mode!r}. Expected 'http' or 'direct'."
    )
