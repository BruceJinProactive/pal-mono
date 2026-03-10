"""TOS (Terms of Service) acceptance service methods."""

import uuid
from datetime import datetime
from typing import TypedDict

from sqlalchemy.orm import Session

from db.repositories.tos_acceptance_repository import TosAcceptanceRepository

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
    tos_repo = TosAcceptanceRepository(session)
    acceptance = tos_repo.get_tos_acceptance_by_version(
        account_id, required_tos_version
    )
    return acceptance is not None


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
    tos_repo = TosAcceptanceRepository(session)
    acceptance = tos_repo.get_tos_acceptance_by_version(
        account_id, required_tos_version
    )

    if acceptance:
        return TOSStatus(
            accepted_tos_version=acceptance.tos_version,
            is_compliant=True,
            accepted_at=acceptance.accepted_at,
        )

    # No acceptance found for required version
    return TOSStatus(
        accepted_tos_version=None,
        is_compliant=False,
        accepted_at=None,
    )
