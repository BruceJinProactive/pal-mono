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


class SubscriptionType(str, enum.Enum):
    trial = "trial"
    monthly = "monthly"
    contract = "contract"


class SubscriptionStatus(str, enum.Enum):
    pending = "pending"
    active = "active"
    expired = "expired"
    cancelled = "cancelled"


class OrderIntegrationVendor(str, enum.Enum):
    olo = "olo"
    toast = "toast"
    adora = "adora"


class Language(str, enum.Enum):
    english = "english"
    multilingual = "multilingual"
