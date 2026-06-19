from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from db.tables import ClientOnboardingContractType, ClientOnboardingStatus


@dataclass
class CreateClientOnboardingAccountParams:
    account_name: str
    client_company_name: str
    signer_email: str
    contract_type: ClientOnboardingContractType
    account_display_name: str | None = None
    signer_name: str | None = None
    order_form_id: str | None = None
    docusign_contract_id: str | None = None
    docusign_envelope_id: str | None = None
    docusign_contract_url: str | None = None
    fde_owner_user_id: UUID | None = None
    folk_company_id: str | None = None
    folk_contact_id: str | None = None
    scoping_doc_url: str | None = None
    idempotency_key: str | None = None


@dataclass
class CreateClientOnboardingAccountResult:
    account_id: UUID
    account_name: str
    account_created: bool
    lifecycle_id: UUID
    lifecycle_status: ClientOnboardingStatus
    invitation_id: UUID
    signer_email: str
    ae_owner_user_id: UUID
    fde_owner_user_id: UUID | None


class DuplicateClientOnboardingError(ValueError):
    pass


class ClientOnboardingInviteNotFoundError(ValueError):
    pass


class ClientOnboardingInviteInvalidError(ValueError):
    pass


@dataclass
class ClientOnboardingInviteStepResult:
    lifecycle_id: UUID
    lifecycle_status: ClientOnboardingStatus
    account_id: UUID
    account_name: str
    account_display_name: str | None
    client_company_name: str
    signer_name: str | None
    signer_email: str
    docusign_required: bool
    docusign_embed_url: str | None
    docusign_contract_url: str | None
    docusign_contract_id: str | None
    docusign_envelope_id: str | None
    docusign_sender_name: str
    fallback_message: str
    password_setup_available: bool


@dataclass
class ReconcileClientOnboardingDocusignCompletionParams:
    docusign_contract_id: str | None = None
    docusign_envelope_id: str | None = None
    docusign_contract_url: str | None = None
    signer_email: str | None = None
    completed_at: datetime | None = None
    docusign_status: str | None = None
    docusign_event_id: str | None = None


@dataclass
class ReconcileClientOnboardingDocusignCompletionResult:
    lifecycle_id: UUID
    lifecycle_status: ClientOnboardingStatus
    docusign_signed_at: datetime | None
    password_setup_available: bool
    transition_recorded: bool
