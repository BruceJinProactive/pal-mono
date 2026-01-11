from __future__ import annotations

import enum


# This is widely used, so keeping the capitalized cases, will need to tweak the alembic
# migration file if this gets created in the database as a type.
class Channel(str, enum.Enum):
    API = "api"
    EMAIL = "email"
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
    t3 = "t3"
    enterprise = "enterprise"


class SubscriptionStatus(str, enum.Enum):
    # Stripe mapping: 'incomplete', 'paused' → awaiting initial payment or paused
    pending = "pending"
    # Stripe mapping: 'active' → subscription active and paid
    active = "active"
    # Stripe mapping: 'trialing' → in free trial period
    trialing = "trialing"
    # Stripe mapping: 'past_due' → payment failed, in grace/dunning period
    past_due = "past_due"
    # Stripe mapping: 'unpaid' → all payment retries failed, subscription suspended
    unpaid = "unpaid"
    # Stripe mapping: 'incomplete_expired' → checkout expired before payment
    expired = "expired"
    # Stripe mapping: 'canceled' → subscription ended
    cancelled = "cancelled"
    # Internal only (soft delete, no Stripe mapping)
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
    resy = "resy"
    minitable = "minitable"


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


class CheckStatus(str, enum.Enum):
    """Status enum for check results."""

    processing = "processing"
    active = "active"
    failed = "failed"
    error = "error"
    overdue = "overdue"


# RBAC Enums


class AccountUserStatus(str, enum.Enum):
    """Status of user membership in an account."""

    pending = "pending"
    active = "active"
    deactivated = "deactivated"


class InvitationStatus(str, enum.Enum):
    """Status of user invitation."""

    pending = "pending"
    accepted = "accepted"
    expired = "expired"
    revoked = "revoked"


class CreditGrantStatus(str, enum.Enum):
    """Status of recurring credit grant."""

    pending = "pending"  # Credit grant scheduled but not yet applied
    granted = "granted"  # Credit successfully applied to account
    failed = "failed"  # Credit grant failed to apply
    cancelled = "cancelled"  # Credit grant cancelled (e.g., subscription ended)


class RecurringCreditFrequency(str, enum.Enum):
    """Frequency for recurring credit grants."""

    weekly = "weekly"
    monthly = "monthly"
    yearly = "yearly"


# Signal Sources Enums


class SignalType(str, enum.Enum):
    """Type of signal source (V1: camera only)."""

    camera = "camera"


class CameraSubtype(str, enum.Enum):
    """Subtype for camera signals."""

    rtsp = "rtsp"
    cloud = "cloud"
    s3 = "s3"


class CloudCameraProvider(str, enum.Enum):
    """Supported cloud camera providers."""

    verkada = "verkada"
    rhombus = "rhombus"
    ring = "ring"


class SignalSourceStatus(str, enum.Enum):
    """Status of a signal source."""

    active = "active"
    inactive = "inactive"
    error = "error"


class SignalFeedStatus(str, enum.Enum):
    """Status of a signal feed."""

    active = "active"
    paused = "paused"
    error = "error"


class FeedType(str, enum.Enum):
    """Type of data produced by a feed."""

    image_snapshot = "image_snapshot"
    video_stream = "video_stream"


class CaptureMode(str, enum.Enum):
    """How feed data is obtained."""

    pull = "pull"
    push = "push"


# Routines Enums


class RoutineCategory(str, enum.Enum):
    """Category of routine."""

    opening = "opening"
    closing = "closing"
    food_safety = "food_safety"
    cleaning = "cleaning"
    compliance = "compliance"
    custom = "custom"


class RoutineInputType(str, enum.Enum):
    """Type of input for routine items (V1: photo only)."""

    photo = "photo"
    # Future:
    # checkbox = "checkbox"
    # number = "number"
    # text = "text"
    # multi_select = "multi_select"


class RoutineFrequency(str, enum.Enum):
    """Frequency of routine schedules."""

    once = "once"
    daily = "daily"
    weekly = "weekly"
    monthly = "monthly"
    custom = "custom"


class ExecutionStatus(str, enum.Enum):
    """Status of routine executions."""

    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    missed = "missed"


class SubmissionStatus(str, enum.Enum):
    """Status of routine submissions."""

    draft = "draft"
    submitted = "submitted"
    approved = "approved"
    rejected = "rejected"


class ItemResponseStatus(str, enum.Enum):
    """Status of individual item responses."""

    pending = "pending"
    passed = "passed"
    failed = "failed"
    skipped = "skipped"


class IdentifierType(str, enum.Enum):
    """Type of identifier for feature flags in gatekeeper service."""

    agent = "agent"
    account = "account"
    project = "project"
    user = "user"
