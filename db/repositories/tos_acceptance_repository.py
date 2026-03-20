import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.tables import Account, TosAcceptance


class TosAcceptanceRepository:
    """Repository for TOS acceptance operations."""

    def __init__(self, session: Session):
        self.session = session

    def create_tos_acceptance(
        self,
        account_id: uuid.UUID,
        display_name: str,
        tos_version: str,
        user_id: uuid.UUID,
        user_email: str,
        accepted_at: datetime,
    ) -> TosAcceptance:
        """
        Create a new TOS acceptance record.

        Args:
            account_id: The account ID accepting the TOS
            display_name: Display name of the account at time of acceptance
            tos_version: Version of the TOS being accepted
            user_id: ID of the user accepting the TOS
            user_email: Email of the user accepting the TOS
            accepted_at: Timestamp when the TOS was accepted

        Returns:
            TosAcceptance: The newly created TOS acceptance record

        Raises:
            IntegrityError: If the account/version combination already exists
            SQLAlchemyError: If database operation fails
        """
        tos_acceptance = TosAcceptance(
            account_id=account_id,
            display_name=display_name,
            tos_version=tos_version,
            user_id=user_id,
            user_email=user_email,
            accepted_at=accepted_at,
        )
        self.session.add(tos_acceptance)
        self.session.flush()
        self.session.refresh(tos_acceptance)
        return tos_acceptance

    def get_latest_tos_acceptance(self, account_id: uuid.UUID) -> TosAcceptance | None:
        """
        Get the most recent TOS acceptance for an account.

        Args:
            account_id: The account ID

        Returns:
            TosAcceptance: The most recent TOS acceptance record, or None if not found

        Raises:
            SQLAlchemyError: If database query fails
        """
        return (
            self.session.query(TosAcceptance)
            .filter(TosAcceptance.account_id == account_id)
            .order_by(TosAcceptance.accepted_at.desc())
            .first()
        )

    def get_tos_acceptance_by_version(
        self, account_id: uuid.UUID, tos_version: str
    ) -> TosAcceptance | None:
        """
        Get TOS acceptance for a specific version and account.

        Args:
            account_id: The account ID
            tos_version: The TOS version

        Returns:
            TosAcceptance: The TOS acceptance record, or None if not found

        Raises:
            SQLAlchemyError: If database query fails
        """
        return (
            self.session.query(TosAcceptance)
            .filter(
                TosAcceptance.account_id == account_id,
                TosAcceptance.tos_version == tos_version,
            )
            .first()
        )

    def get_accounts_without_version(self, tos_version: str) -> list[Account]:
        """
        Future use - when we support multiple versions.
        Get all accounts that have not accepted a specific TOS version.

        Args:
            tos_version: The TOS version to check

        Returns:
            list[Account]: List of Account objects that have not accepted the version

        Raises:
            SQLAlchemyError: If database query fails
        """
        # Subquery to find account IDs that have accepted this version
        accepted_account_ids = select(TosAcceptance.account_id).where(
            TosAcceptance.tos_version == tos_version
        )

        # Find all accounts NOT in the accepted list
        return list(
            self.session.query(Account)
            .filter(Account.id.notin_(accepted_account_ids))
            .all()
        )
