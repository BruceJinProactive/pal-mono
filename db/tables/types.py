from __future__ import annotations

import enum


# This is widely used, so keeping the capitalized cases, will need to tweak the alembic
# migration file if this gets created in the database as a type.
class Channel(str, enum.Enum):
    API = "api"
    INSTAGRAM = "instagram"
    INTERNAL_APP = "internal_app"
    SMS = "sms"
    VOICE = "voice"
    WHATSAPP = "whatsapp"


class AgentType(str, enum.Enum):
    general = "general"
    ordering = "ordering"
    sales = "sales"


class TargetTier(str, enum.Enum):
    t1 = "t1"
    t2 = "t2"
    enterprise = "enterprise"


class SubscriptionStatus(str, enum.Enum):
    pending = "pending"  # unpaid
    active = "active"  # paid
    expired = "expired"
    cancelled = "cancelled"
    deleted = "deleted"


# Do not use this, it is deprecated
class OrderIntegrationVendor(str, enum.Enum):
    olo = "olo"
    toast = "toast"
    adora = "adora"


class Language(str, enum.Enum):
    english = "english"
    multilingual = "multilingual"


class IntegrationProvider(str, enum.Enum):
    yelp = "yelp"
    toast = "toast"
    olo = "olo"
    adora = "adora"
    square = "square"
    opentable = "opentable"


class IntegrationType(str, enum.Enum):
    pos = "pos"
    loyalty = "loyalty"
    reservation = "reservation"


class AuthType(str, enum.Enum):
    oauth = "oauth"
    client_secret = "client_secret"
    api_key = "api_key"
    basic_auth = "basic_auth"


class PaymentMethod(str, enum.Enum):
    autopay = "autopay"
    invoice = "invoice"
