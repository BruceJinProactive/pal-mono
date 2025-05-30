import uuid
from typing import Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from db.tables.change_log import ChangeResourceType
from db.tables.order_integration import (
    OrderIntegration,
    OrderIntegrationVendor,
    OrderProtocol,
)
from services.history_service import change_log_context
from utils.log import logger


class OrderIntegrationRepository:
    def __init__(self, session: Session, auto_commit: bool = True):
        self.session = session
        self.auto_commit = auto_commit

    def create_order_integration(
        self,
        created_by: str,
        account_id: uuid.UUID,
        protocol: OrderProtocol,
        destination: str,
        vendor: Optional[OrderIntegrationVendor] = None,
    ) -> OrderIntegration:
        """
        Create a new order integration.

        Args:
            created_by: The username or identifier of who created the order integration
            account_id: The UUID of the account this integration belongs to
            protocol: The order protocol (SMS, POS, etc.)
            destination: The destination for the order (phone number, endpoint, etc.)
            vendor: Optional vendor for the integration (OLO, TOAST, ADORA)

        Returns:
            OrderIntegration: The created order integration

        Raises:
            SQLAlchemyError: If there's an error creating the order integration
        """
        with change_log_context(
            session=self.session,
            resource_type=ChangeResourceType.OrderIntegration,
            author=created_by,
            account_id=account_id,
            auto_commit=self.auto_commit,
        ) as ctx:
            order_integration = self._create_order_integration(
                account_id, protocol, destination, vendor
            )
            ctx.resource_id = str(order_integration.id)
            ctx.new_record = order_integration
            return order_integration

    def get_order_integration_by_id(
        self, integration_id: uuid.UUID
    ) -> Optional[OrderIntegration]:
        """
        Retrieve an order integration by its ID.

        Args:
            integration_id: The UUID of the order integration to retrieve

        Returns:
            OrderIntegration: The order integration if found, None otherwise
        """
        try:
            return (
                self.session.query(OrderIntegration)
                .filter(OrderIntegration.id == integration_id)
                .first()
            )
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving order integration by ID: {e}")
            return None

    def _create_order_integration(
        self,
        account_id: uuid.UUID,
        protocol: OrderProtocol,
        destination: str,
        vendor: Optional[OrderIntegrationVendor] = None,
    ) -> OrderIntegration:
        try:
            db_order_integration = OrderIntegration(
                id=uuid.uuid4(),
                account_id=account_id,
                protocol=protocol,
                destination=destination,
                vendor=vendor,
            )
            self.session.add(db_order_integration)

            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()

            self.session.refresh(db_order_integration)
            return db_order_integration
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error creating order integration: {e}")
            raise
