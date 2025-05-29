from enum import Enum

from pydantic import BaseModel


class OrderProtocol(str, Enum):
    SMS = "sms"
    POS = "pos"


class OrderIntegrationVendor(str, Enum):
    OLO = "olo"
    TOAST = "toast"
    ADORA = "adora"


class CreateOrderIntegrationRequest(BaseModel):
    order_protocol: OrderProtocol
    vendor: OrderIntegrationVendor | None
    destination: str
