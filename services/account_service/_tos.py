"""TOS (Terms of Service) acceptance service methods."""

import time
import uuid
from datetime import datetime
from typing import TypedDict

from sqlalchemy.orm import Session

from db.repositories.tos_acceptance_repository import TosAcceptanceRepository
from utils.dd import statsd
from utils.log import logger

# Current TOS version - single source of truth
CURRENT_TOS_VERSION = "v1.0"


class TOSStatus(TypedDict):
    """TOS acceptance status information."""

    accepted_tos_version: str | None
    is_compliant: bool
    accepted_at: datetime | None


def check_tos_compliance(
    session: Session,
    account_id: uuid.UUID,
    required_tos_version: str,
) -> bool:
    """
    Check if account has accepted the required TOS version.

    Only checks tos_acceptances table - forces re-acceptance for all users.
    Legacy account.terms_accepted field is ignored.

    Args:
        session: Database session
        account_id: Account UUID
        required_tos_version: Required TOS version (e.g., CURRENT_TOS_VERSION)

    Returns:
        bool: True if account has accepted the required TOS version
    """
    # METRIC: Track compliance check attempts (best-effort)
    try:
        statsd.increment("tos.compliance.check")
    except Exception as metric_err:
        logger.debug(f"Failed to emit tos.compliance.check metric: {metric_err}")

    start_time = time.time()

    try:
        tos_repo = TosAcceptanceRepository(session)
        acceptance = tos_repo.get_tos_acceptance_by_version(
            account_id, required_tos_version
        )

        is_compliant = acceptance is not None

        # METRIC: Track compliance result (best-effort)
        if is_compliant:
            try:
                statsd.increment(
                    "tos.compliance.passed", tags=[f"version:{acceptance.tos_version}"]
                )
            except Exception as metric_err:
                logger.debug(
                    f"Failed to emit tos.compliance.passed metric: {metric_err}"
                )

            logger.info(
                f"TOS compliance check passed for account {account_id} "
                f"(version: {acceptance.tos_version})"
            )
        else:
            try:
                statsd.increment("tos.compliance.failed")
            except Exception as metric_err:
                logger.debug(
                    f"Failed to emit tos.compliance.failed metric: {metric_err}"
                )

            logger.info(
                f"TOS compliance check failed for account {account_id} - no acceptance found"
            )

        return is_compliant

    except Exception as e:
        # METRIC: Track query errors (best-effort, don't mask original exception)
        try:
            statsd.increment(
                "tos.query.error",
                tags=[f"error:{type(e).__name__}", "operation:check_compliance"],
            )
        except Exception as metric_err:
            logger.debug(f"Failed to emit tos.query.error metric: {metric_err}")

        logger.error(
            f"Error checking TOS compliance for account {account_id}: {e}",
            exc_info=True,
        )
        raise
    finally:
        # METRIC: Track query latency (best-effort, always record regardless of success/error)
        try:
            duration_ms = (time.time() - start_time) * 1000
            statsd.histogram(
                "tos.query.latency", duration_ms, tags=["operation:check_compliance"]
            )
        except Exception as metric_err:
            logger.debug(f"Failed to emit tos.query.latency metric: {metric_err}")


def get_tos_status(
    session: Session,
    account_id: uuid.UUID,
    required_tos_version: str,
) -> TOSStatus:
    """
    Get detailed TOS acceptance status for an account.

    Only checks tos_acceptances table - forces re-acceptance for all users.
    Legacy account.terms_accepted field is ignored.

    Args:
        session: Database session
        account_id: Account UUID
        required_tos_version: Required TOS version (e.g., CURRENT_TOS_VERSION)

    Returns:
        TOSStatus: Typed dictionary with:
            - accepted_tos_version: str | None (version accepted if compliant)
            - is_compliant: bool (True if accepted the required version)
            - accepted_at: datetime | None (when accepted, UTC)
    """
    # METRIC: Track status query attempts (best-effort)
    try:
        statsd.increment("tos.status.query")
    except Exception as metric_err:
        logger.debug(f"Failed to emit tos.status.query metric: {metric_err}")

    start_time = time.time()

    try:
        tos_repo = TosAcceptanceRepository(session)
        acceptance = tos_repo.get_tos_acceptance_by_version(
            account_id, required_tos_version
        )

        if acceptance:
            logger.debug(
                f"TOS status retrieved for account {account_id}: "
                f"version={acceptance.tos_version}, "
                f"accepted_at={acceptance.accepted_at}"
            )
            return TOSStatus(
                accepted_tos_version=acceptance.tos_version,
                is_compliant=True,
                accepted_at=acceptance.accepted_at,
            )

        # No acceptance found for required version
        logger.debug(f"No TOS acceptance found for account {account_id}")
        return TOSStatus(
            accepted_tos_version=None,
            is_compliant=False,
            accepted_at=None,
        )

    except Exception as e:
        # METRIC: Track query errors (best-effort, don't mask original exception)
        try:
            statsd.increment(
                "tos.query.error",
                tags=[f"error:{type(e).__name__}", "operation:get_status"],
            )
        except Exception as metric_err:
            logger.debug(f"Failed to emit tos.query.error metric: {metric_err}")

        logger.error(
            f"Error retrieving TOS status for account {account_id}: {e}",
            exc_info=True,
        )
        raise
    finally:
        # METRIC: Track query latency (best-effort, always record regardless of success/error)
        try:
            duration_ms = (time.time() - start_time) * 1000
            statsd.histogram(
                "tos.query.latency", duration_ms, tags=["operation:get_status"]
            )
        except Exception as metric_err:
            logger.debug(f"Failed to emit tos.query.latency metric: {metric_err}")
