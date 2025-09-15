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


class Language(str, enum.Enum):
    english = "english"
    multilingual = "multilingual"


class CallLanguage(str, enum.Enum):
    english = "english"
    french = "french"
    spanish = "spanish"
    chinese = "chinese"


class CallEndedReason(str, enum.Enum):
    customer_ended = "customer_ended"
    assistant_forwarded = "assistant_forwarded"
    misdialed = "misdialed"
    silence_timeout = "silence_timeout"
    max_duration_exceeded = "max_duration_exceeded"
    other = "other"


class CallPurpose(str, enum.Enum):
    """User call purposes (for routing & escalation rules)."""

    # Basic info
    store_info = "store_info"  # hours location/directions, parking, policies
    menu_info = "menu_info"  # menu questions (items, ingredients, pricing)

    # Orders & reservations
    ordering = "ordering"  # user placed order
    reservation = "reservation"  # making new reservations
    waitlist = "waitlist"  # waitlist inquiries
    takeout_issue = "takeout_issue"  # missing pickup items, wrong location
    third_party_order = "third_party_order"  # DoorDash/other app order updates

    # Complaints & service
    customer_service = "customer_service"  # non-urgent management / general service
    complaint_service = "complaint_service"  # dine-in or service complaints
    complaint_food_safety = (
        "complaint_food_safety"  # food safety / food poisoning issues
    )

    # Special cases
    dietary_specific = (
        "dietary_specific"  # allergy/dietary restriction beyond website info
    )
    lost_and_found = "lost_and_found"  # lost items at the restaurant
    reservation_change = "reservation_change"  # unsupported resv. changes
    other = "other"  # any other call purpose


class UserSatisfaction(str, enum.Enum):
    positive = "positive"  # customer satisfied, polite close, needs resolved
    neutral = "neutral"  # mixed signals, partially resolved, or indifferent
    negative = "negative"  # dissatisfied, frustrated, or issue not resolved


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


class SpeechRate(str, enum.Enum):
    """Speech rate enum for voice configuration."""

    slowest = "slowest"
    slower = "slower"
    normal = "normal"
    faster = "faster"
    fastest = "fastest"
