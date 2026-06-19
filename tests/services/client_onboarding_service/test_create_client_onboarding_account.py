from __future__ import annotations

import importlib
import sys
from dataclasses import replace
from datetime import datetime, timezone
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID

import services.client_onboarding_service as public_svc
from db.repositories.resource_role_assignment_repository import ResourceType
from db.tables import (
    ClientOnboardingActivitySource,
    ClientOnboardingActorType,
    ClientOnboardingContractType,
    ClientOnboardingStatus,
)
from db.tables.accounts import AccountStatus, OnboardingMethod
from db.tables.types import AccountUserStatus, InvitationStatus
from services.auth_types import UserContext, UserRole
from services.client_onboarding_service import _implementation as svc
from services.client_onboarding_service.schema import (
    ClientOnboardingInviteInvalidError,
    ClientOnboardingInviteNotFoundError,
    CreateClientOnboardingAccountParams,
    CreateClientOnboardingAccountResult,
    DuplicateClientOnboardingError,
    ReconcileClientOnboardingDocusignCompletionParams,
    ReconcileClientOnboardingDocusignCompletionResult,
)

AE_USER_ID = UUID("11111111-2222-3333-4444-555555555555")
FDE_USER_ID = UUID("22222222-3333-4444-5555-666666666666")
ACCOUNT_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
LIFECYCLE_ID = UUID("bbbbbbbb-cccc-dddd-eeee-ffffffffffff")
INVITATION_ID = UUID("99999999-8888-7777-6666-555555555555")
COMPLETED_AT = datetime(2026, 6, 19, 14, 30, tzinfo=timezone.utc)
pytest: Any = importlib.import_module("pytest")


@pytest.fixture
def context() -> UserContext:
    return UserContext(
        username=str(AE_USER_ID),
        email="ae@palona.ai",
        groups=["pal-admin"],
        display_name="AE User",
        role=UserRole.Admin,
    )


@pytest.fixture
def params() -> CreateClientOnboardingAccountParams:
    return CreateClientOnboardingAccountParams(
        account_name="acme",
        account_display_name="Acme",
        client_company_name="Acme Inc.",
        signer_name="Client Signer",
        signer_email="Signer@Example.com",
        contract_type=ClientOnboardingContractType.order_form_tos,
        docusign_envelope_id="env-123",
        fde_owner_user_id=FDE_USER_ID,
        idempotency_key="PAL-11566-acme",
    )


def _patch_dependencies(
    mocker: Any,
    *,
    existing_account: bool = False,
) -> dict[str, MagicMock]:
    account = MagicMock()
    account.id = ACCOUNT_ID
    account.name = "acme"
    account.display_name = "Acme"

    lifecycle = MagicMock()
    lifecycle.id = LIFECYCLE_ID
    lifecycle.status = ClientOnboardingStatus.account_created

    invitation = MagicMock()
    invitation.id = INVITATION_ID

    get_account = mocker.patch.object(
        svc.account_service,
        "get_account",
        return_value=account if existing_account else None,
    )
    create_account = mocker.patch.object(
        svc.account_service,
        "create_account",
        return_value=account,
    )

    onboarding_repo = mocker.patch.object(
        svc, "ClientOnboardingRepository"
    ).return_value
    onboarding_repo.get_by_idempotency_key.return_value = None
    onboarding_repo.get_active_by_docusign_reference.return_value = None
    onboarding_repo.get_active_for_account_signer.return_value = None
    onboarding_repo.create_lifecycle.return_value = lifecycle

    def mark_invite_sent(*args: object, **kwargs: object) -> MagicMock:
        lifecycle.status = ClientOnboardingStatus.invite_sent
        return lifecycle

    onboarding_repo.mark_invite_sent.side_effect = mark_invite_sent

    account_user_repo = mocker.patch.object(svc, "AccountUserRepository").return_value
    role_repo = mocker.patch.object(
        svc, "ResourceRoleAssignmentRepository"
    ).return_value
    create_invitation = mocker.patch.object(
        svc,
        "_create_signer_invitation",
        return_value=invitation,
    )

    return {
        "account": account,
        "account_user_repo": account_user_repo,
        "create_account": create_account,
        "create_invitation": create_invitation,
        "get_account": get_account,
        "invitation": invitation,
        "lifecycle": lifecycle,
        "onboarding_repo": onboarding_repo,
        "role_repo": role_repo,
    }


def test_create_client_onboarding_account_creates_account_owner_lifecycle_and_invite(
    mocker: Any,
    context: UserContext,
    params: CreateClientOnboardingAccountParams,
) -> None:
    session = MagicMock()
    deps = _patch_dependencies(mocker)

    result = svc.create_client_onboarding_account(session, context, params)

    assert result.account_id == ACCOUNT_ID
    assert result.account_name == "acme"
    assert result.account_created is True
    assert result.lifecycle_id == LIFECYCLE_ID
    assert result.lifecycle_status == ClientOnboardingStatus.invite_sent
    assert result.invitation_id == INVITATION_ID
    assert result.signer_email == "signer@example.com"
    assert result.ae_owner_user_id == AE_USER_ID
    assert result.fde_owner_user_id == FDE_USER_ID

    deps["create_account"].assert_called_once()
    account_params = deps["create_account"].call_args.kwargs["params"]
    assert account_params.display_name == "Acme"
    assert account_params.status == AccountStatus.pending
    assert account_params.owner == "ae@palona.ai"
    assert account_params.contract_signed is False
    assert account_params.onboarding_method == OnboardingMethod.manage_onboarding
    assert deps["create_account"].call_args.kwargs["auto_commit"] is False

    deps["account_user_repo"].create.assert_called_once_with(
        account_id=ACCOUNT_ID,
        user_id=AE_USER_ID,
        email="ae@palona.ai",
        name="AE User",
        added_by=AE_USER_ID,
        status=AccountUserStatus.active,
    )
    deps["role_repo"].add_role.assert_called_once_with(
        user_id=AE_USER_ID,
        resource_type=ResourceType.ACCOUNT,
        resource_id=ACCOUNT_ID,
        role="owner",
        assigned_by=AE_USER_ID,
        reason="AE account creation onboarding",
    )

    deps["onboarding_repo"].create_lifecycle.assert_called_once()
    lifecycle_kwargs = deps["onboarding_repo"].create_lifecycle.call_args.kwargs
    assert lifecycle_kwargs["account_id"] == ACCOUNT_ID
    assert lifecycle_kwargs["signer_email"] == "signer@example.com"
    assert lifecycle_kwargs["ae_owner_user_id"] == AE_USER_ID
    assert lifecycle_kwargs["fde_owner_user_id"] == FDE_USER_ID

    activity_types = [
        call.kwargs["activity_type"]
        for call in deps["onboarding_repo"].append_activity.call_args_list
    ]
    assert activity_types == [
        "contract_prepared",
        "account_created",
        "invite_sent",
    ]

    deps["create_invitation"].assert_called_once()
    invite_kwargs = deps["create_invitation"].call_args.kwargs
    assert invite_kwargs["account_name"] == "acme"
    assert invite_kwargs["signer_email"] == "signer@example.com"

    assert session.commit.call_count == 2


def test_create_client_onboarding_account_links_existing_account(
    mocker: Any,
    context: UserContext,
    params: CreateClientOnboardingAccountParams,
) -> None:
    session = MagicMock()
    deps = _patch_dependencies(mocker, existing_account=True)

    result = svc.create_client_onboarding_account(session, context, params)

    assert result.account_created is False
    deps["create_account"].assert_not_called()
    deps["account_user_repo"].create.assert_called_once()
    deps["role_repo"].add_role.assert_called_once()
    deps["create_invitation"].assert_called_once()


def test_create_client_onboarding_account_rejects_duplicate_docusign_reference(
    mocker: Any,
    context: UserContext,
    params: CreateClientOnboardingAccountParams,
) -> None:
    session = MagicMock()
    deps = _patch_dependencies(mocker)
    deps["onboarding_repo"].get_active_by_docusign_reference.return_value = MagicMock()

    with pytest.raises(DuplicateClientOnboardingError):
        svc.create_client_onboarding_account(session, context, params)

    deps["create_account"].assert_not_called()
    deps["create_invitation"].assert_not_called()
    session.commit.assert_not_called()


def test_create_client_onboarding_account_rejects_duplicate_idempotency_key(
    mocker: Any,
    context: UserContext,
    params: CreateClientOnboardingAccountParams,
) -> None:
    session = MagicMock()
    deps = _patch_dependencies(mocker)
    deps["onboarding_repo"].get_by_idempotency_key.return_value = MagicMock()

    with pytest.raises(DuplicateClientOnboardingError):
        svc.create_client_onboarding_account(session, context, params)

    deps["get_account"].assert_not_called()
    deps["create_invitation"].assert_not_called()
    session.commit.assert_not_called()


def test_create_client_onboarding_account_rejects_duplicate_active_signer(
    mocker: Any,
    context: UserContext,
    params: CreateClientOnboardingAccountParams,
) -> None:
    session = MagicMock()
    deps = _patch_dependencies(mocker, existing_account=True)
    deps["onboarding_repo"].get_active_for_account_signer.return_value = MagicMock()

    with pytest.raises(DuplicateClientOnboardingError):
        svc.create_client_onboarding_account(session, context, params)

    deps["account_user_repo"].create.assert_not_called()
    deps["create_invitation"].assert_not_called()
    session.commit.assert_not_called()


def test_create_client_onboarding_account_allows_missing_idempotency_key(
    mocker: Any,
    context: UserContext,
    params: CreateClientOnboardingAccountParams,
) -> None:
    session = MagicMock()
    deps = _patch_dependencies(mocker)

    result = svc.create_client_onboarding_account(
        session,
        context,
        replace(params, idempotency_key=None),
    )

    assert result.lifecycle_status == ClientOnboardingStatus.invite_sent
    deps["onboarding_repo"].get_by_idempotency_key.assert_not_called()


def test_public_create_client_onboarding_account_wrapper_delegates(
    mocker: Any,
    context: UserContext,
    params: CreateClientOnboardingAccountParams,
) -> None:
    session = MagicMock()
    expected = CreateClientOnboardingAccountResult(
        account_id=ACCOUNT_ID,
        account_name="acme",
        account_created=True,
        lifecycle_id=LIFECYCLE_ID,
        lifecycle_status=ClientOnboardingStatus.invite_sent,
        invitation_id=INVITATION_ID,
        signer_email="signer@example.com",
        ae_owner_user_id=AE_USER_ID,
        fde_owner_user_id=FDE_USER_ID,
    )
    create = mocker.patch(
        "services.client_onboarding_service._implementation.create_client_onboarding_account",
        return_value=expected,
    )

    result = public_svc.create_client_onboarding_account(session, context, params)

    assert result is expected
    create.assert_called_once_with(session=session, context=context, params=params)


def test_create_client_onboarding_account_blocks_lifecycle_when_invite_fails(
    mocker: Any,
    context: UserContext,
    params: CreateClientOnboardingAccountParams,
) -> None:
    session = MagicMock()
    deps = _patch_dependencies(mocker)
    deps["create_invitation"].side_effect = ValueError("Pending invitation exists")

    with pytest.raises(ValueError, match="Pending invitation exists"):
        svc.create_client_onboarding_account(session, context, params)

    deps["onboarding_repo"].mark_blocked.assert_called_once()
    blocked_activity = deps["onboarding_repo"].append_activity.call_args_list[-1]
    assert blocked_activity.kwargs["activity_type"] == "blocked"
    assert blocked_activity.kwargs["next_status"] == ClientOnboardingStatus.blocked
    assert session.commit.call_count == 2


def test_create_client_onboarding_account_rejects_invalid_authenticated_user_id(
    mocker: Any,
    context: UserContext,
    params: CreateClientOnboardingAccountParams,
) -> None:
    session = MagicMock()
    _patch_dependencies(mocker)
    context.username = "not-a-uuid"

    with pytest.raises(ValueError, match="Authenticated AE user id"):
        svc.create_client_onboarding_account(session, context, params)

    session.commit.assert_not_called()


def test_create_signer_invitation_uses_owner_role(
    monkeypatch: Any,
    context: UserContext,
) -> None:
    session = MagicMock()
    invitation = MagicMock()
    create_invitation = MagicMock(return_value=invitation)
    team_service = ModuleType("services.team_service")
    team_service.__dict__["__path__"] = []
    team_service.__dict__["create_invitation"] = create_invitation
    schema_module = ModuleType("services.team_service.schema")
    schema_module.__dict__["InvitationParams"] = _InvitationParams
    monkeypatch.setitem(sys.modules, "services.team_service", team_service)
    monkeypatch.setitem(sys.modules, "services.team_service.schema", schema_module)
    monkeypatch.setattr(
        sys.modules["services"],
        "team_service",
        team_service,
        raising=False,
    )

    result = svc._create_signer_invitation(
        session=session,
        context=context,
        account_name="acme",
        signer_email="signer@example.com",
    )

    assert result is invitation
    invite_params = create_invitation.call_args.kwargs["params"]
    assert invite_params.email == "signer@example.com"
    assert invite_params.account_role == "owner"
    assert invite_params.project_ids is None


def _client_onboarding_invite_dependencies(
    mocker: Any,
    monkeypatch: Any,
    *,
    lifecycle_status: ClientOnboardingStatus = ClientOnboardingStatus.invite_sent,
    docusign_contract_url: str | None = "https://docusign.example/sign/123",
) -> dict[str, MagicMock]:
    invitation = MagicMock()
    invitation.id = INVITATION_ID
    invitation.status = InvitationStatus.pending

    lifecycle = MagicMock()
    lifecycle.id = LIFECYCLE_ID
    lifecycle.status = lifecycle_status
    lifecycle.account_id = ACCOUNT_ID
    lifecycle.client_company_name = "Acme Inc."
    lifecycle.signer_name = "Client Signer"
    lifecycle.signer_email = "signer@example.com"
    lifecycle.docusign_contract_url = docusign_contract_url
    lifecycle.docusign_contract_id = "contract-123"
    lifecycle.docusign_envelope_id = "envelope-123"

    team_service = ModuleType("services.team_service")
    team_service.__dict__["get_invitation_details"] = MagicMock(
        return_value=(invitation, "acme", "Acme", "AE User")
    )
    monkeypatch.setitem(sys.modules, "services.team_service", team_service)
    monkeypatch.setattr(
        sys.modules["services"],
        "team_service",
        team_service,
        raising=False,
    )

    onboarding_repo = mocker.patch.object(
        svc, "ClientOnboardingRepository"
    ).return_value
    onboarding_repo.get_by_invite_id.return_value = lifecycle

    def mark_invite_opened(*args: object, **kwargs: object) -> MagicMock:
        lifecycle._client_onboarding_transition_changed = True
        lifecycle._client_onboarding_transition_previous_status = (
            ClientOnboardingStatus.invite_sent
        )
        lifecycle.status = ClientOnboardingStatus.invite_opened
        return lifecycle

    def mark_docusign_viewed(*args: object, **kwargs: object) -> MagicMock:
        previous_status = lifecycle.status
        lifecycle._client_onboarding_transition_changed = True
        lifecycle._client_onboarding_transition_previous_status = previous_status
        lifecycle.status = ClientOnboardingStatus.docusign_viewed
        return lifecycle

    onboarding_repo.mark_invite_opened.side_effect = mark_invite_opened
    onboarding_repo.mark_docusign_viewed.side_effect = mark_docusign_viewed

    return {
        "invitation": invitation,
        "lifecycle": lifecycle,
        "onboarding_repo": onboarding_repo,
    }


def test_get_client_onboarding_invite_step_marks_invite_opened(
    mocker: Any,
    monkeypatch: Any,
) -> None:
    session = MagicMock()
    deps = _client_onboarding_invite_dependencies(mocker, monkeypatch)

    result = svc.get_client_onboarding_invite_step(session, "invite-token")

    assert result.lifecycle_id == LIFECYCLE_ID
    assert result.lifecycle_status == ClientOnboardingStatus.invite_opened
    assert result.account_name == "acme"
    assert result.account_display_name == "Acme"
    assert result.docusign_required is True
    assert result.docusign_embed_url == "https://docusign.example/sign/123"
    assert result.password_setup_available is False
    assert result.fallback_message == (
        "Please check your email for a contract from AE User via DocuSign."
    )
    deps["onboarding_repo"].mark_invite_opened.assert_called_once()
    activity = deps["onboarding_repo"].append_activity.call_args.kwargs
    assert activity["activity_type"] == "invite_opened"
    assert activity["previous_status"] == ClientOnboardingStatus.invite_sent
    assert activity["next_status"] == ClientOnboardingStatus.invite_opened
    session.commit.assert_called_once()


def test_get_client_onboarding_invite_step_returns_password_setup_when_signed(
    mocker: Any,
    monkeypatch: Any,
) -> None:
    session = MagicMock()
    deps = _client_onboarding_invite_dependencies(
        mocker,
        monkeypatch,
        lifecycle_status=ClientOnboardingStatus.docusign_signed,
    )

    result = svc.get_client_onboarding_invite_step(session, "invite-token")

    assert result.lifecycle_status == ClientOnboardingStatus.docusign_signed
    assert result.docusign_required is False
    assert result.docusign_embed_url is None
    assert result.password_setup_available is True
    deps["onboarding_repo"].mark_invite_opened.assert_not_called()
    deps["onboarding_repo"].append_activity.assert_not_called()
    session.commit.assert_not_called()


def test_get_client_onboarding_invite_step_skips_activity_when_transition_lost(
    mocker: Any,
    monkeypatch: Any,
) -> None:
    session = MagicMock()
    deps = _client_onboarding_invite_dependencies(mocker, monkeypatch)
    lifecycle = deps["lifecycle"]

    def mark_invite_opened(*args: object, **kwargs: object) -> MagicMock:
        lifecycle._client_onboarding_transition_changed = False
        lifecycle.status = ClientOnboardingStatus.invite_opened
        return lifecycle

    deps["onboarding_repo"].mark_invite_opened.side_effect = mark_invite_opened

    result = svc.get_client_onboarding_invite_step(session, "invite-token")

    assert result.lifecycle_status == ClientOnboardingStatus.invite_opened
    deps["onboarding_repo"].append_activity.assert_not_called()
    session.commit.assert_not_called()


def test_mark_client_onboarding_docusign_viewed_records_visible_load(
    mocker: Any,
    monkeypatch: Any,
) -> None:
    session = MagicMock()
    deps = _client_onboarding_invite_dependencies(
        mocker,
        monkeypatch,
        lifecycle_status=ClientOnboardingStatus.invite_opened,
    )

    result = svc.mark_client_onboarding_docusign_viewed(session, "invite-token")

    assert result.lifecycle_status == ClientOnboardingStatus.docusign_viewed
    deps["onboarding_repo"].mark_docusign_viewed.assert_called_once()
    activity = deps["onboarding_repo"].append_activity.call_args.kwargs
    assert activity["activity_type"] == "docusign_viewed"
    assert activity["previous_status"] == ClientOnboardingStatus.invite_opened
    assert activity["next_status"] == ClientOnboardingStatus.docusign_viewed
    session.commit.assert_called_once()


def test_mark_client_onboarding_docusign_viewed_skips_activity_when_transition_lost(
    mocker: Any,
    monkeypatch: Any,
) -> None:
    session = MagicMock()
    deps = _client_onboarding_invite_dependencies(
        mocker,
        monkeypatch,
        lifecycle_status=ClientOnboardingStatus.invite_opened,
    )
    lifecycle = deps["lifecycle"]

    def mark_docusign_viewed(*args: object, **kwargs: object) -> MagicMock:
        lifecycle._client_onboarding_transition_changed = False
        lifecycle.status = ClientOnboardingStatus.docusign_viewed
        return lifecycle

    deps["onboarding_repo"].mark_docusign_viewed.side_effect = mark_docusign_viewed

    result = svc.mark_client_onboarding_docusign_viewed(session, "invite-token")

    assert result.lifecycle_status == ClientOnboardingStatus.docusign_viewed
    deps["onboarding_repo"].append_activity.assert_not_called()
    session.commit.assert_not_called()


def test_mark_client_onboarding_docusign_viewed_rejects_missing_embed_url(
    mocker: Any,
    monkeypatch: Any,
) -> None:
    session = MagicMock()
    deps = _client_onboarding_invite_dependencies(
        mocker,
        monkeypatch,
        lifecycle_status=ClientOnboardingStatus.invite_opened,
        docusign_contract_url=None,
    )

    with pytest.raises(ClientOnboardingInviteInvalidError):
        svc.mark_client_onboarding_docusign_viewed(session, "invite-token")

    deps["onboarding_repo"].mark_docusign_viewed.assert_not_called()
    deps["onboarding_repo"].append_activity.assert_not_called()
    session.commit.assert_not_called()


def test_get_client_onboarding_invite_step_raises_when_no_lifecycle(
    mocker: Any,
    monkeypatch: Any,
) -> None:
    session = MagicMock()
    deps = _client_onboarding_invite_dependencies(mocker, monkeypatch)
    deps["onboarding_repo"].get_by_invite_id.return_value = None

    with pytest.raises(ClientOnboardingInviteNotFoundError):
        svc.get_client_onboarding_invite_step(session, "team-invite-token")


def _docusign_completion_dependencies(
    mocker: Any,
    *,
    lifecycle_status: ClientOnboardingStatus = ClientOnboardingStatus.docusign_viewed,
    signer_email: str = "signer@example.com",
) -> dict[str, MagicMock]:
    lifecycle = MagicMock()
    lifecycle.id = LIFECYCLE_ID
    lifecycle.status = lifecycle_status
    lifecycle.signer_email = signer_email
    lifecycle.docusign_contract_id = "contract-123"
    lifecycle.docusign_envelope_id = "envelope-123"
    lifecycle.docusign_contract_url = "https://docusign.example/sign/123"
    lifecycle.docusign_signed_at = (
        COMPLETED_AT
        if lifecycle_status
        in {
            ClientOnboardingStatus.docusign_signed,
            ClientOnboardingStatus.password_set,
        }
        else None
    )

    onboarding_repo = mocker.patch.object(
        svc, "ClientOnboardingRepository"
    ).return_value
    onboarding_repo.get_active_by_docusign_reference.return_value = lifecycle

    def mark_docusign_signed(*args: object, **kwargs: object) -> MagicMock:
        previous_status = lifecycle.status
        lifecycle._client_onboarding_transition_changed = True
        lifecycle._client_onboarding_transition_previous_status = previous_status
        lifecycle.status = ClientOnboardingStatus.docusign_signed
        lifecycle.docusign_signed_at = kwargs["occurred_at"]
        return lifecycle

    onboarding_repo.mark_docusign_signed.side_effect = mark_docusign_signed

    return {
        "lifecycle": lifecycle,
        "onboarding_repo": onboarding_repo,
    }


def test_reconcile_client_onboarding_docusign_completion_records_signed_event(
    mocker: Any,
) -> None:
    session = MagicMock()
    deps = _docusign_completion_dependencies(mocker)
    params = ReconcileClientOnboardingDocusignCompletionParams(
        docusign_envelope_id=" envelope-123 ",
        signer_email="Signer@Example.com",
        completed_at=COMPLETED_AT,
        docusign_status="completed",
        docusign_event_id="event-123",
    )

    result = svc.reconcile_client_onboarding_docusign_completion(session, params)

    assert result.lifecycle_id == LIFECYCLE_ID
    assert result.lifecycle_status == ClientOnboardingStatus.docusign_signed
    assert result.docusign_signed_at == COMPLETED_AT
    assert result.password_setup_available is True
    assert result.transition_recorded is True
    deps["onboarding_repo"].get_active_by_docusign_reference.assert_called_once_with(
        docusign_contract_id=None,
        docusign_envelope_id="envelope-123",
        docusign_contract_url=None,
    )
    deps["onboarding_repo"].mark_docusign_signed.assert_called_once_with(
        LIFECYCLE_ID,
        occurred_at=COMPLETED_AT,
    )
    activity = deps["onboarding_repo"].append_activity.call_args.kwargs
    assert activity["activity_type"] == "docusign_signed"
    assert activity["actor_type"] == ClientOnboardingActorType.webhook
    assert activity["source"] == ClientOnboardingActivitySource.docusign
    assert activity["previous_status"] == ClientOnboardingStatus.docusign_viewed
    assert activity["next_status"] == ClientOnboardingStatus.docusign_signed
    assert activity["payload_diff"]["docusign_event_id"] == "event-123"
    assert activity["payload_diff"]["docusign_status"] == "completed"
    session.commit.assert_called_once()


def test_reconcile_client_onboarding_docusign_completion_is_idempotent_when_signed(
    mocker: Any,
) -> None:
    session = MagicMock()
    deps = _docusign_completion_dependencies(
        mocker,
        lifecycle_status=ClientOnboardingStatus.docusign_signed,
    )
    params = ReconcileClientOnboardingDocusignCompletionParams(
        docusign_envelope_id="envelope-123",
        completed_at=COMPLETED_AT,
    )

    result = svc.reconcile_client_onboarding_docusign_completion(session, params)

    assert result.lifecycle_status == ClientOnboardingStatus.docusign_signed
    assert result.transition_recorded is False
    assert result.password_setup_available is True
    deps["onboarding_repo"].mark_docusign_signed.assert_not_called()
    deps["onboarding_repo"].append_activity.assert_not_called()
    session.commit.assert_not_called()


def test_reconcile_client_onboarding_docusign_completion_rejects_signer_mismatch(
    mocker: Any,
) -> None:
    session = MagicMock()
    deps = _docusign_completion_dependencies(mocker)
    params = ReconcileClientOnboardingDocusignCompletionParams(
        docusign_envelope_id="envelope-123",
        signer_email="other@example.com",
    )

    with pytest.raises(ClientOnboardingInviteInvalidError):
        svc.reconcile_client_onboarding_docusign_completion(session, params)

    deps["onboarding_repo"].mark_docusign_signed.assert_not_called()
    deps["onboarding_repo"].append_activity.assert_not_called()
    session.commit.assert_not_called()


def test_reconcile_client_onboarding_docusign_completion_rejects_mixed_references(
    mocker: Any,
) -> None:
    session = MagicMock()
    deps = _docusign_completion_dependencies(mocker)
    params = ReconcileClientOnboardingDocusignCompletionParams(
        docusign_envelope_id="envelope-123",
        docusign_contract_id="other-contract",
    )

    with pytest.raises(
        ClientOnboardingInviteInvalidError,
        match="docusign_contract_id",
    ):
        svc.reconcile_client_onboarding_docusign_completion(session, params)

    deps["onboarding_repo"].mark_docusign_signed.assert_not_called()
    deps["onboarding_repo"].append_activity.assert_not_called()
    session.commit.assert_not_called()


def test_reconcile_client_onboarding_docusign_completion_requires_reference() -> None:
    session = MagicMock()

    with pytest.raises(ClientOnboardingInviteInvalidError):
        svc.reconcile_client_onboarding_docusign_completion(
            session,
            ReconcileClientOnboardingDocusignCompletionParams(),
        )

    session.commit.assert_not_called()


def test_public_reconcile_client_onboarding_docusign_completion_wrapper_delegates(
    mocker: Any,
) -> None:
    session = MagicMock()
    params = ReconcileClientOnboardingDocusignCompletionParams(
        docusign_envelope_id="envelope-123",
    )
    expected = ReconcileClientOnboardingDocusignCompletionResult(
        lifecycle_id=LIFECYCLE_ID,
        lifecycle_status=ClientOnboardingStatus.docusign_signed,
        docusign_signed_at=COMPLETED_AT,
        password_setup_available=True,
        transition_recorded=True,
    )
    reconcile = mocker.patch(
        "services.client_onboarding_service._implementation.reconcile_client_onboarding_docusign_completion",
        return_value=expected,
    )

    result = public_svc.reconcile_client_onboarding_docusign_completion(
        session,
        params,
    )

    assert result is expected
    reconcile.assert_called_once_with(session=session, params=params)


class _InvitationParams:
    def __init__(
        self,
        *,
        email: str,
        account_role: str,
        project_ids: list[UUID] | None,
    ) -> None:
        self.email = email
        self.account_role = account_role
        self.project_ids = project_ids
