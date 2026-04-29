"""TOS (Terms of Service) acceptance service methods."""

import uuid
from datetime import datetime, timezone
from typing import TypedDict

from sqlalchemy.orm import Session

from db.repositories.tos_acceptance_repository import TosAcceptanceRepository
from utils.log import logger
from utils.otel import increment_counter, record_duration

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
    # METRIC: Track compliance check attempts
    increment_counter("tos.compliance.check")

    start_time = datetime.now(timezone.utc)

    try:
        tos_repo = TosAcceptanceRepository(session)
        acceptance = tos_repo.get_tos_acceptance_by_version(
            account_id, required_tos_version
        )

        is_compliant = acceptance is not None

        # METRIC: Track compliance result
        if is_compliant:
            increment_counter(
                "tos.compliance.passed", attributes={"version": acceptance.tos_version}
            )

            logger.info(
                f"TOS compliance check passed for account {account_id} "
                f"(version: {acceptance.tos_version})"
            )
        else:
            increment_counter("tos.compliance.failed")

            logger.info(
                f"TOS compliance check failed for account {account_id} - no acceptance found"
            )

        return is_compliant

    except Exception as e:
        # METRIC: Track query errors (don't mask original exception)
        increment_counter(
            "tos.query.error",
            attributes={"error": type(e).__name__, "operation": "check_compliance"},
        )

        logger.error(
            f"Error checking TOS compliance for account {account_id}: {e}",
            exc_info=True,
        )
        raise
    finally:
        # METRIC: Track query latency
        record_duration(
            "tos.query.duration",
            start_time,
            attributes={"operation": "check_compliance"},
        )


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
    # METRIC: Track status query attempts
    increment_counter("tos.status.query")

    start_time = datetime.now(timezone.utc)

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
        # METRIC: Track query errors
        increment_counter(
            "tos.query.error",
            attributes={"error": type(e).__name__, "operation": "get_status"},
        )

        logger.error(
            f"Error retrieving TOS status for account {account_id}: {e}",
            exc_info=True,
        )
        raise
    finally:
        # METRIC: Track query latency
        record_duration(
            "tos.query.duration",
            start_time,
            attributes={"operation": "get_status"},
        )
