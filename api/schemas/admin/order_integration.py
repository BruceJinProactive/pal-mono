import uuid

from pydantic import BaseModel

from db.tables.order_integration import OrderIntegrationVendor, OrderProtocol


class CreateOrderIntegrationRequest(BaseModel):
    order_protocol: OrderProtocol
    vendor: OrderIntegrationVendor | None
    destination: str


class SetupProjectOrderIntegrationRequest(BaseModel):
    """Request to setup order integration for a project"""

    project_id: uuid.UUID
    order_protocol: OrderProtocol
    vendor: OrderIntegrationVendor | None
    destination: str
