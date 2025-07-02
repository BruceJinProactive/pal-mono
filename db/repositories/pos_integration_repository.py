import uuid
from typing import Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from db.tables.change_log import ChangeResourceType
from db.tables.pos_integration import POSIntegration, POSState
from db.tables.types import IntegrationProvider
from utils.log import logger


class POSIntegrationRepository:
    def __init__(self, session: Session, auto_commit: bool = True):
        self.session = session
        self.auto_commit = auto_commit

    def create_pos_integration(
        self,
        created_by: str,
        project_id: uuid.UUID,
        store_identifier: str,
        provider: IntegrationProvider,
        state: POSState = POSState.active,
    ) -> POSIntegration:
        """
        Create a new POS integration.

        Args:
            created_by: The username or identifier of who created the POS integration
            project_id: The UUID of the project this integration belongs to
            store_identifier: The store identifier for the POS system
            provider: The POS provider (YELP, TOAST, etc.)
            state: The state of the integration (ACTIVATE or INACTIVATE)

        Returns:
            POSIntegration: The created POS integration

        Raises:
            SQLAlchemyError: If there's an error creating the POS integration
        """
        from services.history_service import change_log_context

        with change_log_context(
            session=self.session,
            resource_type=ChangeResourceType.POSIntegration,
            author=created_by,
            account_id=project_id,
            auto_commit=self.auto_commit,
        ) as ctx:
            pos_integration = self._create_pos_integration(
                project_id, store_identifier, provider, state
            )
            ctx.resource_id = str(pos_integration.id)
            ctx.new_record = pos_integration
            return pos_integration

    def get_pos_integration_by_id(
        self, integration_id: uuid.UUID
    ) -> Optional[POSIntegration]:
        """
        Retrieve a POS integration by its ID.

        Args:
            integration_id: The UUID of the POS integration to retrieve

        Returns:
            POSIntegration: The POS integration if found, None otherwise
        """
        try:
            return (
                self.session.query(POSIntegration)
                .filter(POSIntegration.id == integration_id)
                .first()
            )
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving POS integration by ID: {e}")
            return None

    def get_pos_integration_by_project_id(
        self, project_id: uuid.UUID
    ) -> Optional[POSIntegration]:
        """
        Retrieve a POS integration by project ID.

        Args:
            project_id: The UUID of the project to retrieve the integration for

        Returns:
            POSIntegration: The POS integration if found, None otherwise
        """
        try:
            return (
                self.session.query(POSIntegration)
                .filter(POSIntegration.project_id == project_id)
                .first()
            )
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving POS integration by project ID: {e}")
            return None

    def _create_pos_integration(
        self,
        project_id: uuid.UUID,
        store_identifier: str,
        provider: IntegrationProvider,
        state: POSState,
    ) -> POSIntegration:
        try:
            db_pos_integration = POSIntegration(
                id=uuid.uuid4(),
                project_id=project_id,
                store_identifier=store_identifier,
                provider=provider,
                state=state,
            )
            self.session.add(db_pos_integration)

            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()

            self.session.refresh(db_pos_integration)
            return db_pos_integration
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error creating POS integration: {e}")
            raise
