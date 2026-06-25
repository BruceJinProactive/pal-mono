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
    ClientOnboardingSyncJobStatus,
    ClientOnboardingSyncTarget,
)
from db.tables.accounts import AccountStatus, OnboardingMethod
from db.tables.types import AccountUserStatus, InvitationStatus
from services.auth_types import UserContext, UserRole
from services.client_onboarding_service import _implementation as svc
from services.client_onboarding_service.schema import (
    ClientOnboardingFdeOwnerAssignmentResult,
    ClientOnboardingFolkSyncResult,
    ClientOnboardingHandoffCompletionResult,
    ClientOnboardingInviteInvalidError,
    ClientOnboardingInviteNotFoundError,
    ClientOnboardingInviteStepResult,
    ClientOnboardingNotionSyncResult,
    ClientOnboardingSlackHandoffResult,
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
    docusign_envelope_id: str | None = "envelope-123",
    invitation_status: InvitationStatus = InvitationStatus.pending,
) -> dict[str, MagicMock]:
    invitation = MagicMock()
    invitation.id = INVITATION_ID
    invitation.email = "signer@example.com"
    invitation.status = invitation_status

    lifecycle = MagicMock()
    lifecycle.id = LIFECYCLE_ID
    lifecycle.status = lifecycle_status
    lifecycle.account_id = ACCOUNT_ID
    lifecycle.client_company_name = "Acme Inc."
    lifecycle.signer_name = "Client Signer"
    lifecycle.signer_email = "signer@example.com"
    lifecycle.docusign_contract_url = docusign_contract_url
    lifecycle.docusign_contract_id = "contract-123"
    lifecycle.docusign_envelope_id = docusign_envelope_id
    lifecycle.invite_id = INVITATION_ID

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

    def mark_password_set(*args: object, **kwargs: object) -> MagicMock:
        previous_status = lifecycle.status
        lifecycle._client_onboarding_transition_changed = True
        lifecycle._client_onboarding_transition_previous_status = previous_status
        lifecycle.password_set_at = kwargs["occurred_at"]
        if previous_status == ClientOnboardingStatus.docusign_signed:
            lifecycle.status = ClientOnboardingStatus.password_set
        return lifecycle

    onboarding_repo.mark_invite_opened.side_effect = mark_invite_opened
    onboarding_repo.mark_docusign_viewed.side_effect = mark_docusign_viewed
    onboarding_repo.mark_password_set.side_effect = mark_password_set
    docusign_client = MagicMock()
    docusign_client.create_recipient_view.return_value = (
        "https://docusign.example/embed/123"
    )
    build_docusign_client = mocker.patch.object(
        svc,
        "_build_docusign_embedded_signing_client",
        return_value=docusign_client,
    )
    docusign_admin_base_url = mocker.patch.object(
        svc,
        "_docusign_admin_console_base_url",
        return_value="https://admin.palona.ai",
    )
    handoff_completion = mocker.patch.object(
        svc,
        "orchestrate_client_onboarding_handoff_completion",
    )

    def complete_handoff(*args: object, **kwargs: object) -> Any:
        return ClientOnboardingHandoffCompletionResult(
            lifecycle_id=LIFECYCLE_ID,
            lifecycle_status=lifecycle.status,
            handoff_created=lifecycle.status
            in {
                ClientOnboardingStatus.handoff_created,
                ClientOnboardingStatus.activation_ready,
            },
            activation_ready=lifecycle.status
            == ClientOnboardingStatus.activation_ready,
            pending_sync_jobs=[],
        )

    handoff_completion.side_effect = complete_handoff

    return {
        "invitation": invitation,
        "lifecycle": lifecycle,
        "onboarding_repo": onboarding_repo,
        "docusign_client": docusign_client,
        "build_docusign_client": build_docusign_client,
        "docusign_admin_base_url": docusign_admin_base_url,
        "handoff_completion": handoff_completion,
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
    assert result.docusign_embed_url == "https://docusign.example/embed/123"
    assert result.password_setup_available is False
    assert result.fallback_message == (
        "Please check your email for a contract from AE User via DocuSign."
    )
    deps["docusign_client"].create_recipient_view.assert_called_once_with(
        envelope_id="envelope-123",
        signer_email="signer@example.com",
        signer_name="Client Signer",
        client_user_id=str(INVITATION_ID),
        return_url=(
            "https://admin.palona.ai/accept-invitation"
            "?invitation_token=invite-token&docusign_return=1"
        ),
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
    deps["build_docusign_client"].assert_not_called()
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


def test_get_client_onboarding_invite_step_falls_back_without_embed_url(
    mocker: Any,
    monkeypatch: Any,
) -> None:
    session = MagicMock()
    deps = _client_onboarding_invite_dependencies(mocker, monkeypatch)
    deps["build_docusign_client"].return_value = None

    result = svc.get_client_onboarding_invite_step(session, "invite-token")

    assert result.docusign_required is True
    assert result.docusign_embed_url is None
    assert result.docusign_contract_url == "https://docusign.example/sign/123"


def test_create_docusign_embed_url_skips_without_envelope_id() -> None:
    lifecycle = MagicMock()
    lifecycle.docusign_envelope_id = " "

    result = svc._create_docusign_embed_url(lifecycle, "invite-token")

    assert result is None


def test_create_docusign_embed_url_skips_without_admin_console_url(
    mocker: Any,
) -> None:
    lifecycle = MagicMock()
    lifecycle.docusign_envelope_id = "envelope-123"
    docusign_client = MagicMock()
    mocker.patch.object(
        svc,
        "_build_docusign_embedded_signing_client",
        return_value=docusign_client,
    )
    mocker.patch.object(svc, "_docusign_admin_console_base_url", return_value=None)

    result = svc._create_docusign_embed_url(lifecycle, "invite-token")

    assert result is None
    docusign_client.create_recipient_view.assert_not_called()


def test_create_docusign_embed_url_returns_none_when_docusign_fails(
    mocker: Any,
) -> None:
    lifecycle = MagicMock()
    lifecycle.id = LIFECYCLE_ID
    lifecycle.invite_id = INVITATION_ID
    lifecycle.docusign_envelope_id = "envelope-123"
    lifecycle.signer_email = "signer@example.com"
    lifecycle.signer_name = None
    docusign_client = MagicMock()
    docusign_client.create_recipient_view.side_effect = RuntimeError("boom")
    mocker.patch.object(
        svc,
        "_build_docusign_embedded_signing_client",
        return_value=docusign_client,
    )
    mocker.patch.object(
        svc,
        "_docusign_admin_console_base_url",
        return_value="https://admin.palona.ai",
    )

    result = svc._create_docusign_embed_url(lifecycle, "invite-token")

    assert result is None
    docusign_client.create_recipient_view.assert_called_once()


def test_load_docusign_embedded_signing_config_cleans_values(
    mocker: Any,
) -> None:
    values = {
        "DOCUSIGN_ACCOUNT_ID": "account-123",
        "DOCUSIGN_INTEGRATION_KEY": "integration-key",
        "DOCUSIGN_IMPERSONATED_USER_ID": "user-123",
        "DOCUSIGN_PRIVATE_KEY": "line-one\\nline-two",
        "DOCUSIGN_AUTH_SERVER": "account-d.docusign.com",
        "DOCUSIGN_REST_API_BASE_URL": "https://demo.docusign.net/restapi/",
        "PAL_ADMIN_CONSOLE_BASE_URL": "https://admin.palona.ai/",
    }
    mocker.patch.object(svc, "_docusign_secret_value", side_effect=values.get)

    config = svc._load_docusign_embedded_signing_config()

    assert config == svc._DocusignEmbeddedSigningConfig(
        account_id="account-123",
        integration_key="integration-key",
        impersonated_user_id="user-123",
        private_key="line-one\nline-two",
        auth_server="account-d.docusign.com",
        rest_api_base_url="https://demo.docusign.net/restapi",
    )


def test_load_docusign_embedded_signing_config_returns_none_when_missing(
    mocker: Any,
) -> None:
    mocker.patch.object(svc, "_docusign_secret_value", return_value=None)

    assert svc._load_docusign_embedded_signing_config() is None


def test_build_docusign_embedded_signing_client_returns_none_without_config(
    mocker: Any,
) -> None:
    mocker.patch.object(
        svc, "_load_docusign_embedded_signing_config", return_value=None
    )

    assert svc._build_docusign_embedded_signing_client() is None


def test_docusign_secret_value_returns_cleaned_secret(
    mocker: Any,
) -> None:
    get_secret = mocker.patch.object(
        svc,
        "get_server_secret_with_fallback",
        return_value=" secret-value ",
    )

    assert svc._docusign_secret_value("DOCUSIGN_ACCOUNT_ID") == "secret-value"
    get_secret.assert_called_once_with("DOCUSIGN_ACCOUNT_ID")


def test_docusign_secret_value_returns_none_for_missing_secret(
    mocker: Any,
) -> None:
    mocker.patch.object(
        svc,
        "get_server_secret_with_fallback",
        side_effect=ValueError("missing"),
    )

    assert svc._docusign_secret_value("DOCUSIGN_ACCOUNT_ID") is None


def test_docusign_admin_console_base_url_falls_back_to_console_base(
    mocker: Any,
) -> None:
    mocker.patch.object(
        svc,
        "_docusign_secret_value",
        side_effect=[None, "https://console.palona.ai"],
    )

    assert svc._docusign_admin_console_base_url() == "https://console.palona.ai"


def test_build_docusign_return_url_encodes_invite_token() -> None:
    assert svc._build_docusign_return_url(
        "https://admin.palona.ai/",
        "invite token+123",
    ) == (
        "https://admin.palona.ai/accept-invitation"
        "?invitation_token=invite+token%2B123&docusign_return=1"
    )


def _docusign_config() -> Any:
    return svc._DocusignEmbeddedSigningConfig(
        account_id="account-123",
        integration_key="integration-key",
        impersonated_user_id="user-123",
        private_key="private-key",
        auth_server="account-d.docusign.com",
        rest_api_base_url="https://demo.docusign.net/restapi",
    )


def test_docusign_http_client_creates_recipient_view(
    mocker: Any,
    monkeypatch: Any,
) -> None:
    client = svc._DocusignEmbeddedSigningHttpClient(_docusign_config())
    create_access_token = mocker.patch.object(
        client,
        "_create_access_token",
        return_value="access-token",
    )
    requests_module = ModuleType("requests")
    response = MagicMock()
    response.json.return_value = {"url": "https://docusign.example/embed"}
    post_mock = MagicMock(return_value=response)
    setattr(requests_module, "post", post_mock)
    monkeypatch.setitem(sys.modules, "requests", requests_module)
    monkeypatch.setitem(sys.modules, "jwt", ModuleType("jwt"))

    result = client.create_recipient_view(
        envelope_id="envelope-123",
        signer_email="signer@example.com",
        signer_name="Client Signer",
        client_user_id="invite-id",
        return_url="https://admin.palona.ai/accept-invitation",
    )

    assert result == "https://docusign.example/embed"
    create_access_token.assert_called_once()
    request_kwargs = post_mock.call_args.kwargs
    assert request_kwargs["json"] == {
        "returnUrl": "https://admin.palona.ai/accept-invitation",
        "authenticationMethod": "none",
        "email": "signer@example.com",
        "userName": "Client Signer",
        "clientUserId": "invite-id",
    }
    assert request_kwargs["headers"]["Authorization"] == "Bearer access-token"
    assert request_kwargs["timeout"] == svc.DOCUSIGN_EMBED_HTTP_TIMEOUT_SECONDS


def test_docusign_http_client_rejects_missing_recipient_view_url(
    mocker: Any,
    monkeypatch: Any,
) -> None:
    client = svc._DocusignEmbeddedSigningHttpClient(_docusign_config())
    mocker.patch.object(client, "_create_access_token", return_value="access-token")
    requests_module = ModuleType("requests")
    response = MagicMock()
    response.json.return_value = {"url": " "}
    post_mock = MagicMock(return_value=response)
    setattr(requests_module, "post", post_mock)
    monkeypatch.setitem(sys.modules, "requests", requests_module)
    monkeypatch.setitem(sys.modules, "jwt", ModuleType("jwt"))

    with pytest.raises(
        RuntimeError,
        match="DocuSign recipient view response did not include url",
    ):
        client.create_recipient_view(
            envelope_id="envelope-123",
            signer_email="signer@example.com",
            signer_name="Client Signer",
            client_user_id="invite-id",
            return_url="https://admin.palona.ai/accept-invitation",
        )


def test_docusign_http_client_creates_access_token() -> None:
    client = svc._DocusignEmbeddedSigningHttpClient(_docusign_config())
    jwt_module = MagicMock()
    jwt_module.encode.return_value = "assertion"
    requests_module = MagicMock()
    response = MagicMock()
    response.json.return_value = {"access_token": "access-token"}
    requests_module.post.return_value = response

    result = client._create_access_token(jwt_module, requests_module)

    assert result == "access-token"
    jwt_module.encode.assert_called_once()
    requests_module.post.assert_called_once_with(
        "https://account-d.docusign.com/oauth/token",
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": "assertion",
        },
        timeout=svc.DOCUSIGN_EMBED_HTTP_TIMEOUT_SECONDS,
    )


def test_docusign_http_client_rejects_missing_access_token() -> None:
    client = svc._DocusignEmbeddedSigningHttpClient(_docusign_config())
    jwt_module = MagicMock()
    jwt_module.encode.return_value = "assertion"
    requests_module = MagicMock()
    response = MagicMock()
    response.json.return_value = {"access_token": ""}
    requests_module.post.return_value = response

    with pytest.raises(
        RuntimeError,
        match="DocuSign OAuth response did not include access_token",
    ):
        client._create_access_token(jwt_module, requests_module)


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
        docusign_envelope_id=None,
    )

    with pytest.raises(ClientOnboardingInviteInvalidError):
        svc.mark_client_onboarding_docusign_viewed(session, "invite-token")

    deps["onboarding_repo"].mark_docusign_viewed.assert_not_called()
    deps["onboarding_repo"].append_activity.assert_not_called()
    session.commit.assert_not_called()


def test_mark_client_onboarding_password_set_records_client_completion(
    mocker: Any,
    monkeypatch: Any,
) -> None:
    session = MagicMock()
    context = MagicMock(
        username=str(AE_USER_ID),
        email="signer@example.com",
    )
    deps = _client_onboarding_invite_dependencies(
        mocker,
        monkeypatch,
        lifecycle_status=ClientOnboardingStatus.docusign_signed,
    )

    result = svc.mark_client_onboarding_password_set(
        session,
        context,
        "invite-token",
    )

    assert result.lifecycle_status == ClientOnboardingStatus.password_set
    assert result.password_setup_available is True
    deps["onboarding_repo"].mark_password_set.assert_called_once()
    activity = deps["onboarding_repo"].append_activity.call_args.kwargs
    assert activity["activity_type"] == "password_set"
    assert activity["actor_type"] == ClientOnboardingActorType.client
    assert activity["actor_id"] == AE_USER_ID
    assert activity["actor_display_name"] == "signer@example.com"
    assert activity["source"] == ClientOnboardingActivitySource.admin_console
    assert activity["previous_status"] == ClientOnboardingStatus.docusign_signed
    assert activity["next_status"] == ClientOnboardingStatus.password_set
    assert activity["payload_diff"]["invite_id"] == str(INVITATION_ID)
    session.commit.assert_called_once()


def test_mark_client_onboarding_password_set_allows_accepted_invitation(
    mocker: Any,
    monkeypatch: Any,
) -> None:
    session = MagicMock()
    context = MagicMock(
        username=str(AE_USER_ID),
        email="signer@example.com",
    )
    deps = _client_onboarding_invite_dependencies(
        mocker,
        monkeypatch,
        lifecycle_status=ClientOnboardingStatus.docusign_signed,
        invitation_status=InvitationStatus.accepted,
    )

    result = svc.mark_client_onboarding_password_set(
        session,
        context,
        "invite-token",
    )

    assert result.lifecycle_status == ClientOnboardingStatus.password_set
    deps["onboarding_repo"].mark_password_set.assert_called_once()
    session.commit.assert_called_once()


def test_mark_client_onboarding_password_set_is_idempotent_after_password_set(
    mocker: Any,
    monkeypatch: Any,
) -> None:
    session = MagicMock()
    context = MagicMock(
        username=str(AE_USER_ID),
        email="signer@example.com",
    )
    deps = _client_onboarding_invite_dependencies(
        mocker,
        monkeypatch,
        lifecycle_status=ClientOnboardingStatus.password_set,
    )

    result = svc.mark_client_onboarding_password_set(
        session,
        context,
        "invite-token",
    )

    assert result.lifecycle_status == ClientOnboardingStatus.password_set
    deps["onboarding_repo"].mark_password_set.assert_not_called()
    deps["onboarding_repo"].append_activity.assert_not_called()
    session.commit.assert_not_called()


def test_mark_client_onboarding_password_set_rejects_before_signature(
    mocker: Any,
    monkeypatch: Any,
) -> None:
    session = MagicMock()
    context = MagicMock(
        username=str(AE_USER_ID),
        email="signer@example.com",
    )
    deps = _client_onboarding_invite_dependencies(
        mocker,
        monkeypatch,
        lifecycle_status=ClientOnboardingStatus.docusign_viewed,
    )

    with pytest.raises(ClientOnboardingInviteInvalidError):
        svc.mark_client_onboarding_password_set(
            session,
            context,
            "invite-token",
        )

    deps["onboarding_repo"].mark_password_set.assert_not_called()
    deps["onboarding_repo"].append_activity.assert_not_called()
    session.commit.assert_not_called()


def test_mark_client_onboarding_password_set_rejects_wrong_authenticated_user(
    mocker: Any,
    monkeypatch: Any,
) -> None:
    session = MagicMock()
    context = MagicMock(
        username=str(AE_USER_ID),
        email="other@example.com",
    )
    deps = _client_onboarding_invite_dependencies(
        mocker,
        monkeypatch,
        lifecycle_status=ClientOnboardingStatus.docusign_signed,
    )

    with pytest.raises(ClientOnboardingInviteInvalidError):
        svc.mark_client_onboarding_password_set(
            session,
            context,
            "invite-token",
        )

    deps["onboarding_repo"].mark_password_set.assert_not_called()
    deps["onboarding_repo"].append_activity.assert_not_called()
    session.commit.assert_not_called()


def test_public_mark_client_onboarding_password_set_wrapper_delegates(
    mocker: Any,
) -> None:
    session = MagicMock()
    context = MagicMock()
    expected = ClientOnboardingInviteStepResult(
        lifecycle_id=LIFECYCLE_ID,
        lifecycle_status=ClientOnboardingStatus.password_set,
        account_id=ACCOUNT_ID,
        account_name="acme",
        account_display_name="Acme",
        client_company_name="Acme Inc.",
        signer_name="Client Signer",
        signer_email="signer@example.com",
        docusign_required=False,
        docusign_embed_url=None,
        docusign_contract_url="https://docusign.example/sign/123",
        docusign_contract_id="contract-123",
        docusign_envelope_id="envelope-123",
        docusign_sender_name="AE User",
        fallback_message=(
            "Please check your email for a contract from AE User via DocuSign."
        ),
        password_setup_available=True,
    )
    mark_password_set = mocker.patch(
        "services.client_onboarding_service._implementation.mark_client_onboarding_password_set",
        return_value=expected,
    )

    result = public_svc.mark_client_onboarding_password_set(
        session,
        context,
        "invite-token",
    )

    assert result is expected
    mark_password_set.assert_called_once_with(
        session=session,
        context=context,
        invitation_token="invite-token",
    )


def test_public_orchestrate_client_onboarding_handoff_completion_wrapper_delegates(
    mocker: Any,
) -> None:
    session = MagicMock()
    expected = ClientOnboardingHandoffCompletionResult(
        lifecycle_id=LIFECYCLE_ID,
        lifecycle_status=ClientOnboardingStatus.handoff_created,
        handoff_created=True,
        activation_ready=False,
        pending_sync_jobs=[],
    )
    orchestrate = mocker.patch(
        "services.client_onboarding_service._implementation.orchestrate_client_onboarding_handoff_completion",
        return_value=expected,
    )

    result = public_svc.orchestrate_client_onboarding_handoff_completion(
        session,
        LIFECYCLE_ID,
    )

    assert result is expected
    orchestrate.assert_called_once_with(session=session, lifecycle_id=LIFECYCLE_ID)


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
    lifecycle.account_id = ACCOUNT_ID
    lifecycle.manage_app_account_name = "acme"
    lifecycle.client_company_name = "Acme Inc."
    lifecycle.signer_name = "Client Signer"
    lifecycle.signer_email = signer_email
    lifecycle.contract_type = ClientOnboardingContractType.order_form_tos
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
    lifecycle.ae_owner_user_id = AE_USER_ID
    lifecycle.fde_owner_user_id = FDE_USER_ID
    lifecycle.folk_company_id = "folk-company-123"
    lifecycle.folk_contact_id = "folk-contact-123"
    lifecycle.slack_channel_id = None
    lifecycle.notion_page_id = None
    lifecycle.scoping_doc_url = None

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
    slack_handoff = mocker.patch.object(
        svc,
        "sync_client_onboarding_slack_handoff",
    )
    notion_sync = mocker.patch.object(
        svc,
        "sync_client_onboarding_notion_cmd_entry",
    )
    fde_owner_sync = mocker.patch.object(
        svc,
        "sync_client_onboarding_fde_owner_assignment",
    )
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
    upsert_calls = deps["onboarding_repo"].upsert_sync_job.call_args_list
    assert [call.kwargs["target"] for call in upsert_calls] == [
        ClientOnboardingSyncTarget.database,
        ClientOnboardingSyncTarget.folk,
        ClientOnboardingSyncTarget.slack,
        ClientOnboardingSyncTarget.notion,
        ClientOnboardingSyncTarget.manage_app,
    ]
    assert upsert_calls[0].kwargs["job_type"] == "record_contract_acceptance"
    assert upsert_calls[1].kwargs["job_type"] == "update_contract_acceptance"
    assert upsert_calls[2].kwargs["job_type"] == "create_handoff_channel"
    assert upsert_calls[3].kwargs["job_type"] == "upsert_cmd_entry"
    assert upsert_calls[4].kwargs["job_type"] == "add_fde_owner"
    assert upsert_calls[1].kwargs["payload"]["folk_company_id"] == "folk-company-123"
    deps["onboarding_repo"].mark_sync_job_completed.assert_called_once()
    slack_handoff.assert_called_once_with(session, LIFECYCLE_ID)
    notion_sync.assert_called_once_with(session, LIFECYCLE_ID)
    fde_owner_sync.assert_called_once_with(session, LIFECYCLE_ID)
    session.commit.assert_called_once()


def test_reconcile_client_onboarding_docusign_completion_continues_when_slack_handoff_fails(
    mocker: Any,
) -> None:
    session = MagicMock()
    _docusign_completion_dependencies(mocker)
    slack_handoff = mocker.patch.object(
        svc,
        "sync_client_onboarding_slack_handoff",
        side_effect=RuntimeError("Slack unavailable"),
    )
    notion_sync = mocker.patch.object(
        svc,
        "sync_client_onboarding_notion_cmd_entry",
    )
    fde_owner_sync = mocker.patch.object(
        svc,
        "sync_client_onboarding_fde_owner_assignment",
    )
    logger = mocker.patch.object(svc.logger, "exception")
    params = ReconcileClientOnboardingDocusignCompletionParams(
        docusign_envelope_id="envelope-123",
        completed_at=COMPLETED_AT,
    )

    result = svc.reconcile_client_onboarding_docusign_completion(session, params)

    assert result.lifecycle_status == ClientOnboardingStatus.docusign_signed
    assert result.transition_recorded is True
    slack_handoff.assert_called_once_with(session, LIFECYCLE_ID)
    notion_sync.assert_called_once_with(session, LIFECYCLE_ID)
    fde_owner_sync.assert_called_once_with(session, LIFECYCLE_ID)
    logger.assert_called_once()
    session.commit.assert_called_once()


def test_reconcile_client_onboarding_docusign_completion_continues_when_notion_sync_fails(
    mocker: Any,
) -> None:
    session = MagicMock()
    _docusign_completion_dependencies(mocker)
    slack_handoff = mocker.patch.object(
        svc,
        "sync_client_onboarding_slack_handoff",
    )
    notion_sync = mocker.patch.object(
        svc,
        "sync_client_onboarding_notion_cmd_entry",
        side_effect=RuntimeError("Notion unavailable"),
    )
    fde_owner_sync = mocker.patch.object(
        svc,
        "sync_client_onboarding_fde_owner_assignment",
    )
    logger = mocker.patch.object(svc.logger, "exception")
    params = ReconcileClientOnboardingDocusignCompletionParams(
        docusign_envelope_id="envelope-123",
        completed_at=COMPLETED_AT,
    )

    result = svc.reconcile_client_onboarding_docusign_completion(session, params)

    assert result.lifecycle_status == ClientOnboardingStatus.docusign_signed
    assert result.transition_recorded is True
    slack_handoff.assert_called_once_with(session, LIFECYCLE_ID)
    notion_sync.assert_called_once_with(session, LIFECYCLE_ID)
    fde_owner_sync.assert_called_once_with(session, LIFECYCLE_ID)
    logger.assert_called_once()
    session.commit.assert_called_once()


def test_reconcile_client_onboarding_docusign_completion_continues_when_fde_owner_sync_fails(
    mocker: Any,
) -> None:
    session = MagicMock()
    _docusign_completion_dependencies(mocker)
    slack_handoff = mocker.patch.object(
        svc,
        "sync_client_onboarding_slack_handoff",
    )
    notion_sync = mocker.patch.object(
        svc,
        "sync_client_onboarding_notion_cmd_entry",
    )
    fde_owner_sync = mocker.patch.object(
        svc,
        "sync_client_onboarding_fde_owner_assignment",
        side_effect=RuntimeError("FDE owner unavailable"),
    )
    logger = mocker.patch.object(svc.logger, "exception")
    params = ReconcileClientOnboardingDocusignCompletionParams(
        docusign_envelope_id="envelope-123",
        completed_at=COMPLETED_AT,
    )

    result = svc.reconcile_client_onboarding_docusign_completion(session, params)

    assert result.lifecycle_status == ClientOnboardingStatus.docusign_signed
    assert result.transition_recorded is True
    slack_handoff.assert_called_once_with(session, LIFECYCLE_ID)
    notion_sync.assert_called_once_with(session, LIFECYCLE_ID)
    fde_owner_sync.assert_called_once_with(session, LIFECYCLE_ID)
    logger.assert_called_once()
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
    deps["onboarding_repo"].upsert_sync_job.assert_not_called()
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


def test_sync_client_onboarding_contract_acceptance_to_folk_updates_records(
    mocker: Any,
) -> None:
    session = MagicMock()
    lifecycle = _signed_lifecycle()
    job = MagicMock()
    job.id = UUID("cccccccc-dddd-eeee-ffff-000000000000")
    onboarding_repo = mocker.patch.object(
        svc, "ClientOnboardingRepository"
    ).return_value
    onboarding_repo.get_by_id.return_value = lifecycle
    onboarding_repo.upsert_sync_job.return_value = job
    folk_client = _FakeFolkContractAcceptanceClient()
    handoff_completion = mocker.patch.object(
        svc,
        "orchestrate_client_onboarding_handoff_completion",
    )

    result = svc.sync_client_onboarding_contract_acceptance_to_folk(
        session,
        LIFECYCLE_ID,
        folk_client=folk_client,
    )

    assert result == ClientOnboardingFolkSyncResult(
        lifecycle_id=LIFECYCLE_ID,
        folk_company_id="folk-company-123",
        folk_contact_id="folk-contact-123",
        updated_company=True,
        updated_contact=True,
    )
    assert folk_client.company_updates[0][0] == "folk-company-123"
    company_payload = folk_client.company_updates[0][1]
    field_values = company_payload["customFieldValues"][
        "grp_3454c312-a64a-47c7-af0c-098c5fa9e9f9"
    ]
    assert field_values["Contract Signed Date"] == "2026-06-19"
    assert field_values["Contract Accepted By"] == "signer@example.com"
    assert field_values["DocuSign Envelope ID"] == "envelope-123"
    assert field_values["Manage App Account ID"] == str(ACCOUNT_ID)
    assert folk_client.contact_updates[0][0] == "folk-contact-123"
    onboarding_repo.mark_sync_job_completed.assert_called_once_with(
        job.id,
        result_payload={"updated_company": True, "updated_contact": True},
    )
    activity = onboarding_repo.append_activity.call_args.kwargs
    assert activity["activity_type"] == "folk_contract_acceptance_synced"
    session.commit.assert_called_once()
    handoff_completion.assert_called_once_with(session, LIFECYCLE_ID)


def test_sync_client_onboarding_contract_acceptance_to_folk_skips_completed_job(
    mocker: Any,
) -> None:
    session = MagicMock()
    lifecycle = _signed_lifecycle()
    job = MagicMock()
    job.status = ClientOnboardingSyncJobStatus.completed
    job.result_payload = {"updated_company": True, "updated_contact": False}
    onboarding_repo = mocker.patch.object(
        svc, "ClientOnboardingRepository"
    ).return_value
    onboarding_repo.get_by_id.return_value = lifecycle
    onboarding_repo.upsert_sync_job.return_value = job
    folk_client = _FakeFolkContractAcceptanceClient()
    handoff_completion = mocker.patch.object(
        svc,
        "orchestrate_client_onboarding_handoff_completion",
    )

    result = svc.sync_client_onboarding_contract_acceptance_to_folk(
        session,
        LIFECYCLE_ID,
        folk_client=folk_client,
    )

    assert result == ClientOnboardingFolkSyncResult(
        lifecycle_id=LIFECYCLE_ID,
        folk_company_id="folk-company-123",
        folk_contact_id="folk-contact-123",
        updated_company=True,
        updated_contact=False,
    )
    assert folk_client.company_updates == []
    assert folk_client.contact_updates == []
    onboarding_repo.mark_sync_job_completed.assert_not_called()
    onboarding_repo.mark_sync_job_failed.assert_not_called()
    onboarding_repo.append_activity.assert_not_called()
    handoff_completion.assert_called_once_with(session, LIFECYCLE_ID)
    session.commit.assert_not_called()


def test_sync_client_onboarding_contract_acceptance_to_folk_marks_missing_ids_skipped(
    mocker: Any,
) -> None:
    session = MagicMock()
    lifecycle = _signed_lifecycle()
    lifecycle.folk_company_id = None
    lifecycle.folk_contact_id = None
    job = MagicMock()
    job.id = UUID("cccccccc-dddd-eeee-ffff-000000000000")
    onboarding_repo = mocker.patch.object(
        svc, "ClientOnboardingRepository"
    ).return_value
    onboarding_repo.get_by_id.return_value = lifecycle
    onboarding_repo.upsert_sync_job.return_value = job

    result = svc.sync_client_onboarding_contract_acceptance_to_folk(
        session,
        LIFECYCLE_ID,
        folk_client=_FakeFolkContractAcceptanceClient(),
    )

    assert result.updated_company is False
    assert result.updated_contact is False
    assert result.skipped_reason == (
        "No Folk company or contact ID is linked to this lifecycle"
    )
    onboarding_repo.mark_sync_job_completed.assert_called_once_with(
        job.id,
        result_payload={
            "skipped_reason": "No Folk company or contact ID is linked to this lifecycle"
        },
    )
    onboarding_repo.mark_sync_job_failed.assert_not_called()
    activity = onboarding_repo.append_activity.call_args.kwargs
    assert activity["activity_type"] == "folk_contract_acceptance_sync_skipped"
    session.commit.assert_called_once()


def test_sync_client_onboarding_contract_acceptance_to_folk_rejects_missing_lifecycle(
    mocker: Any,
) -> None:
    session = MagicMock()
    onboarding_repo = mocker.patch.object(
        svc, "ClientOnboardingRepository"
    ).return_value
    onboarding_repo.get_by_id.return_value = None

    with pytest.raises(ClientOnboardingInviteNotFoundError):
        svc.sync_client_onboarding_contract_acceptance_to_folk(
            session,
            LIFECYCLE_ID,
            folk_client=_FakeFolkContractAcceptanceClient(),
        )

    onboarding_repo.upsert_sync_job.assert_not_called()
    session.commit.assert_not_called()


def test_sync_client_onboarding_contract_acceptance_to_folk_rejects_before_signature(
    mocker: Any,
) -> None:
    session = MagicMock()
    lifecycle = _signed_lifecycle()
    lifecycle.status = ClientOnboardingStatus.docusign_viewed
    onboarding_repo = mocker.patch.object(
        svc, "ClientOnboardingRepository"
    ).return_value
    onboarding_repo.get_by_id.return_value = lifecycle

    with pytest.raises(ClientOnboardingInviteInvalidError):
        svc.sync_client_onboarding_contract_acceptance_to_folk(
            session,
            LIFECYCLE_ID,
            folk_client=_FakeFolkContractAcceptanceClient(),
        )

    onboarding_repo.upsert_sync_job.assert_not_called()
    session.commit.assert_not_called()


def test_sync_client_onboarding_contract_acceptance_to_folk_records_folk_failure(
    mocker: Any,
) -> None:
    session = MagicMock()
    lifecycle = _signed_lifecycle()
    job = MagicMock()
    job.id = UUID("cccccccc-dddd-eeee-ffff-000000000000")
    onboarding_repo = mocker.patch.object(
        svc, "ClientOnboardingRepository"
    ).return_value
    onboarding_repo.get_by_id.return_value = lifecycle
    onboarding_repo.upsert_sync_job.return_value = job

    with pytest.raises(RuntimeError, match="Folk unavailable"):
        svc.sync_client_onboarding_contract_acceptance_to_folk(
            session,
            LIFECYCLE_ID,
            folk_client=_FailingFolkContractAcceptanceClient(),
        )

    onboarding_repo.mark_sync_job_failed.assert_called_once()
    activity = onboarding_repo.append_activity.call_args.kwargs
    assert activity["activity_type"] == "folk_contract_acceptance_sync_failed"
    assert activity["payload_diff"]["error"] == "Folk unavailable"
    session.commit.assert_called_once()


def test_sync_client_onboarding_slack_handoff_creates_channel_invites_and_posts(
    mocker: Any,
) -> None:
    session = MagicMock()
    lifecycle = _signed_lifecycle()
    job = MagicMock()
    job.id = UUID("cccccccc-dddd-eeee-ffff-000000000000")
    job.status = ClientOnboardingSyncJobStatus.pending
    onboarding_repo = mocker.patch.object(
        svc, "ClientOnboardingRepository"
    ).return_value
    onboarding_repo.get_by_id.return_value = lifecycle
    onboarding_repo.upsert_sync_job.return_value = job

    def set_slack_channel_id(*args: object, **kwargs: object) -> MagicMock:
        lifecycle.slack_channel_id = kwargs["slack_channel_id"]
        return lifecycle

    onboarding_repo.set_slack_channel_id.side_effect = set_slack_channel_id
    _patch_handoff_owner_contacts(mocker)
    sdk_client = _FakeSlackSdkClient(
        {"ae@palona.ai": "UAE123", "fde@palona.ai": "UFDE456"}
    )

    result = svc.sync_client_onboarding_slack_handoff(
        session,
        LIFECYCLE_ID,
        slack_client=svc._SlackHandoffClientAdapter(sdk_client),
    )

    assert result == ClientOnboardingSlackHandoffResult(
        lifecycle_id=LIFECYCLE_ID,
        slack_channel_id="C123",
        slack_channel_name="client-acme",
        created_channel=True,
        invited_user_ids=["UAE123", "UFDE456"],
        posted_message=True,
        message_ts="1718820000.000100",
    )
    assert sdk_client.created_channels == [{"name": "client-acme", "is_private": False}]
    assert sdk_client.invites == [
        {"channel_id": "C123", "user_ids": ["UAE123", "UFDE456"]}
    ]
    assert sdk_client.messages[0]["channel_id"] == "C123"
    message_blocks = str(sdk_client.messages[0]["blocks"])
    assert "<@UAE123>" in message_blocks
    assert "<@UFDE456>" in message_blocks
    assert "https://app.folk.app/apps/contacts/companies/folk-company-123" in (
        message_blocks
    )
    assert "https://www.notion.so/notion-page-123" in message_blocks
    onboarding_repo.set_slack_channel_id.assert_called_once_with(
        LIFECYCLE_ID,
        slack_channel_id="C123",
    )
    onboarding_repo.mark_sync_job_completed.assert_called_once()
    result_payload = onboarding_repo.mark_sync_job_completed.call_args.kwargs[
        "result_payload"
    ]
    assert result_payload["slack_channel_id"] == "C123"
    assert result_payload["created_channel"] is True
    assert result_payload["invited_user_ids"] == ["UAE123", "UFDE456"]
    assert result_payload["unresolved_owner_user_ids"] == []
    activity = onboarding_repo.append_activity.call_args.kwargs
    assert activity["activity_type"] == "slack_handoff_created"
    assert session.commit.call_count == 2


def test_sync_client_onboarding_slack_handoff_reuses_completed_job(
    mocker: Any,
) -> None:
    session = MagicMock()
    lifecycle = _signed_lifecycle()
    job = MagicMock()
    job.status = ClientOnboardingSyncJobStatus.completed
    job.result_payload = {
        "slack_channel_id": "C123",
        "slack_channel_name": "client-acme",
        "created_channel": True,
        "invited_user_ids": ["UAE123"],
        "posted_message": True,
        "message_ts": "1718820000.000100",
    }
    onboarding_repo = mocker.patch.object(
        svc, "ClientOnboardingRepository"
    ).return_value
    onboarding_repo.get_by_id.return_value = lifecycle
    onboarding_repo.upsert_sync_job.return_value = job
    account_user_repo = mocker.patch.object(svc, "AccountUserRepository")
    handoff_completion = mocker.patch.object(
        svc,
        "orchestrate_client_onboarding_handoff_completion",
    )

    result = svc.sync_client_onboarding_slack_handoff(
        session,
        LIFECYCLE_ID,
        slack_client=_FailingSlackHandoffClient(),
    )

    assert result == ClientOnboardingSlackHandoffResult(
        lifecycle_id=LIFECYCLE_ID,
        slack_channel_id="C123",
        slack_channel_name="client-acme",
        created_channel=True,
        invited_user_ids=["UAE123"],
        posted_message=True,
        message_ts="1718820000.000100",
    )
    account_user_repo.assert_not_called()
    onboarding_repo.mark_sync_job_completed.assert_not_called()
    onboarding_repo.append_activity.assert_not_called()
    handoff_completion.assert_called_once_with(session, LIFECYCLE_ID)
    session.commit.assert_not_called()


def test_sync_client_onboarding_slack_handoff_reuses_existing_channel(
    mocker: Any,
) -> None:
    session = MagicMock()
    lifecycle = _signed_lifecycle()
    lifecycle.slack_channel_id = "CEXISTING"
    job = MagicMock()
    job.id = UUID("cccccccc-dddd-eeee-ffff-000000000000")
    job.status = ClientOnboardingSyncJobStatus.pending
    onboarding_repo = mocker.patch.object(
        svc, "ClientOnboardingRepository"
    ).return_value
    onboarding_repo.get_by_id.return_value = lifecycle
    onboarding_repo.upsert_sync_job.return_value = job
    _patch_handoff_owner_contacts(mocker)
    sdk_client = _FakeSlackSdkClient(
        {"ae@palona.ai": "UAE123", "fde@palona.ai": "UFDE456"}
    )

    result = svc.sync_client_onboarding_slack_handoff(
        session,
        LIFECYCLE_ID,
        slack_client=svc._SlackHandoffClientAdapter(sdk_client),
    )

    assert result.slack_channel_id == "CEXISTING"
    assert result.created_channel is False
    assert sdk_client.created_channels == []
    assert sdk_client.messages[0]["channel_id"] == "CEXISTING"
    onboarding_repo.set_slack_channel_id.assert_not_called()
    session.commit.assert_called_once()


def test_sync_client_onboarding_slack_handoff_recovers_name_taken_channel(
    mocker: Any,
) -> None:
    session = MagicMock()
    lifecycle = _signed_lifecycle()
    job = MagicMock()
    job.id = UUID("cccccccc-dddd-eeee-ffff-000000000000")
    job.status = ClientOnboardingSyncJobStatus.pending
    onboarding_repo = mocker.patch.object(
        svc, "ClientOnboardingRepository"
    ).return_value
    onboarding_repo.get_by_id.return_value = lifecycle
    onboarding_repo.upsert_sync_job.return_value = job

    def set_slack_channel_id(*args: object, **kwargs: object) -> MagicMock:
        lifecycle.slack_channel_id = kwargs["slack_channel_id"]
        return lifecycle

    onboarding_repo.set_slack_channel_id.side_effect = set_slack_channel_id
    _patch_handoff_owner_contacts(mocker)
    sdk_client = _FakeSlackSdkClient(
        {"ae@palona.ai": "UAE123", "fde@palona.ai": "UFDE456"},
        create_error="name_taken",
        channels_by_name={"client-acme": "CEXISTING"},
    )

    result = svc.sync_client_onboarding_slack_handoff(
        session,
        LIFECYCLE_ID,
        slack_client=svc._SlackHandoffClientAdapter(sdk_client),
    )

    assert result.slack_channel_id == "CEXISTING"
    assert result.created_channel is False
    assert sdk_client.channel_list_requests == [None]
    assert sdk_client.messages[0]["channel_id"] == "CEXISTING"
    onboarding_repo.set_slack_channel_id.assert_called_once_with(
        LIFECYCLE_ID,
        slack_channel_id="CEXISTING",
    )
    result_payload = onboarding_repo.mark_sync_job_completed.call_args.kwargs[
        "result_payload"
    ]
    assert result_payload["slack_channel_id"] == "CEXISTING"
    assert result_payload["created_channel"] is False
    assert session.commit.call_count == 2


def test_sync_client_onboarding_slack_handoff_records_slack_failure(
    mocker: Any,
) -> None:
    session = MagicMock()
    lifecycle = _signed_lifecycle()
    job = MagicMock()
    job.id = UUID("cccccccc-dddd-eeee-ffff-000000000000")
    job.status = ClientOnboardingSyncJobStatus.pending
    onboarding_repo = mocker.patch.object(
        svc, "ClientOnboardingRepository"
    ).return_value
    onboarding_repo.get_by_id.return_value = lifecycle
    onboarding_repo.upsert_sync_job.return_value = job
    _patch_handoff_owner_contacts(mocker)

    with pytest.raises(RuntimeError, match="missing_scope"):
        svc.sync_client_onboarding_slack_handoff(
            session,
            LIFECYCLE_ID,
            slack_client=_FailingSlackHandoffClient(),
        )

    onboarding_repo.mark_sync_job_failed.assert_called_once()
    activity = onboarding_repo.append_activity.call_args.kwargs
    assert activity["activity_type"] == "slack_handoff_sync_failed"
    assert activity["payload_diff"]["error"].endswith("missing_scope")
    session.commit.assert_called_once()


def test_sync_client_onboarding_slack_handoff_rejects_before_signature(
    mocker: Any,
) -> None:
    session = MagicMock()
    lifecycle = _signed_lifecycle()
    lifecycle.status = ClientOnboardingStatus.docusign_viewed
    onboarding_repo = mocker.patch.object(
        svc, "ClientOnboardingRepository"
    ).return_value
    onboarding_repo.get_by_id.return_value = lifecycle

    with pytest.raises(ClientOnboardingInviteInvalidError):
        svc.sync_client_onboarding_slack_handoff(
            session,
            LIFECYCLE_ID,
            slack_client=_FakeSlackHandoffClient(),
        )

    onboarding_repo.upsert_sync_job.assert_not_called()
    session.commit.assert_not_called()


def test_sync_client_onboarding_notion_cmd_entry_creates_page_and_links_lifecycle(
    mocker: Any,
) -> None:
    session = MagicMock()
    lifecycle = _signed_lifecycle()
    lifecycle.notion_page_id = None
    lifecycle.slack_channel_id = "C123"
    job = MagicMock()
    job.id = UUID("cccccccc-dddd-eeee-ffff-000000000000")
    job.status = ClientOnboardingSyncJobStatus.pending
    onboarding_repo = mocker.patch.object(
        svc, "ClientOnboardingRepository"
    ).return_value
    onboarding_repo.get_by_id.return_value = lifecycle
    onboarding_repo.upsert_sync_job.return_value = job

    def set_notion_page_id(*args: object, **kwargs: object) -> MagicMock:
        lifecycle.notion_page_id = kwargs["notion_page_id"]
        return lifecycle

    onboarding_repo.set_notion_page_id.side_effect = set_notion_page_id
    _patch_handoff_owner_contacts(mocker)
    notion_client = _FakeNotionCmdEntryClient(created_page_id="notion-page-new")

    result = svc.sync_client_onboarding_notion_cmd_entry(
        session,
        LIFECYCLE_ID,
        notion_client=notion_client,
    )

    assert result == ClientOnboardingNotionSyncResult(
        lifecycle_id=LIFECYCLE_ID,
        notion_page_id="notion-page-new",
        created_page=True,
        updated_page=False,
    )
    assert notion_client.find_page_requests[0].name == "Acme Inc."
    created_page = notion_client.created_pages[0]
    assert created_page["properties"]["Name"]["title"][0]["text"]["content"] == (
        "Acme Inc."
    )
    assert created_page["properties"]["account_name"]["select"]["name"] == "acme"
    summary = created_page["children"][1]["paragraph"]["rich_text"][0]["text"][
        "content"
    ]
    assert "DocuSign envelope: envelope-123" in summary
    assert "Slack channel ID: C123" in summary
    assert "Folk company ID: folk-company-123" in summary
    onboarding_repo.set_notion_page_id.assert_called_once_with(
        LIFECYCLE_ID,
        notion_page_id="notion-page-new",
    )
    result_payload = onboarding_repo.mark_sync_job_completed.call_args.kwargs[
        "result_payload"
    ]
    assert result_payload == {
        "notion_page_id": "notion-page-new",
        "created_page": True,
        "updated_page": False,
    }
    activity = onboarding_repo.append_activity.call_args.kwargs
    assert activity["activity_type"] == "notion_cmd_entry_synced"
    assert session.commit.call_count == 1


def test_sync_client_onboarding_notion_cmd_entry_updates_matched_page(
    mocker: Any,
) -> None:
    session = MagicMock()
    lifecycle = _signed_lifecycle()
    lifecycle.notion_page_id = None
    job = MagicMock()
    job.id = UUID("cccccccc-dddd-eeee-ffff-000000000000")
    job.status = ClientOnboardingSyncJobStatus.pending
    onboarding_repo = mocker.patch.object(
        svc, "ClientOnboardingRepository"
    ).return_value
    onboarding_repo.get_by_id.return_value = lifecycle
    onboarding_repo.upsert_sync_job.return_value = job

    def set_notion_page_id(*args: object, **kwargs: object) -> MagicMock:
        lifecycle.notion_page_id = kwargs["notion_page_id"]
        return lifecycle

    onboarding_repo.set_notion_page_id.side_effect = set_notion_page_id
    _patch_handoff_owner_contacts(mocker)
    notion_client = _FakeNotionCmdEntryClient(found_page={"id": "notion-page-existing"})

    result = svc.sync_client_onboarding_notion_cmd_entry(
        session,
        LIFECYCLE_ID,
        notion_client=notion_client,
    )

    assert result == ClientOnboardingNotionSyncResult(
        lifecycle_id=LIFECYCLE_ID,
        notion_page_id="notion-page-existing",
        created_page=False,
        updated_page=True,
    )
    assert notion_client.created_pages == []
    assert notion_client.updated_pages[0]["page_id"] == "notion-page-existing"
    assert "Name" not in notion_client.updated_pages[0]["properties"]
    onboarding_repo.set_notion_page_id.assert_called_once_with(
        LIFECYCLE_ID,
        notion_page_id="notion-page-existing",
    )
    session.commit.assert_called_once()


def test_sync_client_onboarding_notion_cmd_entry_reuses_completed_job(
    mocker: Any,
) -> None:
    session = MagicMock()
    lifecycle = _signed_lifecycle()
    job = MagicMock()
    job.status = ClientOnboardingSyncJobStatus.completed
    job.result_payload = {
        "notion_page_id": "notion-page-123",
        "created_page": True,
        "updated_page": False,
    }
    onboarding_repo = mocker.patch.object(
        svc, "ClientOnboardingRepository"
    ).return_value
    onboarding_repo.get_by_id.return_value = lifecycle
    onboarding_repo.upsert_sync_job.return_value = job
    account_user_repo = mocker.patch.object(svc, "AccountUserRepository")
    handoff_completion = mocker.patch.object(
        svc,
        "orchestrate_client_onboarding_handoff_completion",
    )

    result = svc.sync_client_onboarding_notion_cmd_entry(
        session,
        LIFECYCLE_ID,
        notion_client=_FailingNotionCmdEntryClient(),
    )

    assert result == ClientOnboardingNotionSyncResult(
        lifecycle_id=LIFECYCLE_ID,
        notion_page_id="notion-page-123",
        created_page=True,
        updated_page=False,
    )
    account_user_repo.assert_not_called()
    onboarding_repo.mark_sync_job_completed.assert_not_called()
    onboarding_repo.append_activity.assert_not_called()
    handoff_completion.assert_called_once_with(session, LIFECYCLE_ID)
    session.commit.assert_not_called()


def test_sync_client_onboarding_notion_cmd_entry_records_notion_failure(
    mocker: Any,
) -> None:
    session = MagicMock()
    lifecycle = _signed_lifecycle()
    lifecycle.notion_page_id = None
    job = MagicMock()
    job.id = UUID("cccccccc-dddd-eeee-ffff-000000000000")
    job.status = ClientOnboardingSyncJobStatus.pending
    onboarding_repo = mocker.patch.object(
        svc, "ClientOnboardingRepository"
    ).return_value
    onboarding_repo.get_by_id.return_value = lifecycle
    onboarding_repo.upsert_sync_job.return_value = job
    _patch_handoff_owner_contacts(mocker)

    with pytest.raises(RuntimeError, match="Notion unavailable"):
        svc.sync_client_onboarding_notion_cmd_entry(
            session,
            LIFECYCLE_ID,
            notion_client=_FailingNotionCmdEntryClient(),
        )

    onboarding_repo.mark_sync_job_failed.assert_called_once()
    activity = onboarding_repo.append_activity.call_args.kwargs
    assert activity["activity_type"] == "notion_cmd_entry_sync_failed"
    assert activity["payload_diff"]["error"] == "Notion unavailable"
    session.commit.assert_called_once()


def test_sync_client_onboarding_notion_cmd_entry_records_owner_resolution_failure(
    mocker: Any,
) -> None:
    session = MagicMock()
    lifecycle = _signed_lifecycle()
    lifecycle.notion_page_id = None
    job = MagicMock()
    job.id = UUID("cccccccc-dddd-eeee-ffff-000000000000")
    job.status = ClientOnboardingSyncJobStatus.pending
    onboarding_repo = mocker.patch.object(
        svc, "ClientOnboardingRepository"
    ).return_value
    onboarding_repo.get_by_id.return_value = lifecycle
    onboarding_repo.upsert_sync_job.return_value = job
    account_user_repo = mocker.patch.object(svc, "AccountUserRepository")
    account_user_repo.side_effect = RuntimeError("owner lookup failed")

    with pytest.raises(RuntimeError, match="owner lookup failed"):
        svc.sync_client_onboarding_notion_cmd_entry(
            session,
            LIFECYCLE_ID,
            notion_client=_FakeNotionCmdEntryClient(),
        )

    onboarding_repo.mark_sync_job_failed.assert_called_once()
    activity = onboarding_repo.append_activity.call_args.kwargs
    assert activity["activity_type"] == "notion_cmd_entry_sync_failed"
    assert activity["payload_diff"]["error"] == "owner lookup failed"
    session.commit.assert_called_once()


def test_sync_client_onboarding_notion_cmd_entry_rejects_before_signature(
    mocker: Any,
) -> None:
    session = MagicMock()
    lifecycle = _signed_lifecycle()
    lifecycle.status = ClientOnboardingStatus.docusign_viewed
    onboarding_repo = mocker.patch.object(
        svc, "ClientOnboardingRepository"
    ).return_value
    onboarding_repo.get_by_id.return_value = lifecycle

    with pytest.raises(ClientOnboardingInviteInvalidError):
        svc.sync_client_onboarding_notion_cmd_entry(
            session,
            LIFECYCLE_ID,
            notion_client=_FakeNotionCmdEntryClient(),
        )

    onboarding_repo.upsert_sync_job.assert_not_called()
    session.commit.assert_not_called()


def test_sync_client_onboarding_fde_owner_assignment_creates_membership_and_owner_role(
    mocker: Any,
) -> None:
    session = MagicMock()
    lifecycle = _signed_lifecycle()
    job = MagicMock()
    job.id = UUID("cccccccc-dddd-eeee-ffff-000000000000")
    job.status = ClientOnboardingSyncJobStatus.pending
    onboarding_repo = mocker.patch.object(
        svc, "ClientOnboardingRepository"
    ).return_value
    onboarding_repo.get_by_id.return_value = lifecycle
    onboarding_repo.upsert_sync_job.return_value = job
    account_user_repo = mocker.patch.object(svc, "AccountUserRepository").return_value
    account_user_repo.get_by_user_and_account.return_value = None
    account_user_repo.get_by_user_id.return_value = None
    role_repo = mocker.patch.object(
        svc, "ResourceRoleAssignmentRepository"
    ).return_value
    role_repo.has_role.return_value = False

    result = svc.sync_client_onboarding_fde_owner_assignment(
        session,
        LIFECYCLE_ID,
        identity_provider=_FakeFdeOwnerIdentityProvider(
            email="fde@palona.ai",
            name="FDE User",
        ),
    )

    assert result == ClientOnboardingFdeOwnerAssignmentResult(
        lifecycle_id=LIFECYCLE_ID,
        account_id=ACCOUNT_ID,
        fde_owner_user_id=FDE_USER_ID,
        membership_created=True,
        membership_reactivated=False,
        owner_role_assigned=True,
    )
    account_user_repo.create.assert_called_once_with(
        account_id=ACCOUNT_ID,
        user_id=FDE_USER_ID,
        email="fde@palona.ai",
        name="FDE User",
        added_by=AE_USER_ID,
        status=AccountUserStatus.active,
    )
    role_repo.add_role.assert_called_once_with(
        user_id=FDE_USER_ID,
        resource_type=ResourceType.ACCOUNT,
        resource_id=ACCOUNT_ID,
        role="owner",
        assigned_by=AE_USER_ID,
        reason="Client onboarding post-signature FDE ownership",
    )
    onboarding_repo.mark_sync_job_completed.assert_called_once()
    result_payload = onboarding_repo.mark_sync_job_completed.call_args.kwargs[
        "result_payload"
    ]
    assert result_payload["membership_created"] is True
    assert result_payload["owner_role_assigned"] is True
    activity = onboarding_repo.append_activity.call_args.kwargs
    assert activity["activity_type"] == "fde_owner_assigned"
    assert session.commit.call_count == 1


def test_sync_client_onboarding_fde_owner_assignment_reactivates_existing_member(
    mocker: Any,
) -> None:
    session = MagicMock()
    lifecycle = _signed_lifecycle()
    existing_member = MagicMock()
    existing_member.status = AccountUserStatus.deactivated
    job = MagicMock()
    job.id = UUID("cccccccc-dddd-eeee-ffff-000000000000")
    job.status = ClientOnboardingSyncJobStatus.pending
    onboarding_repo = mocker.patch.object(
        svc, "ClientOnboardingRepository"
    ).return_value
    onboarding_repo.get_by_id.return_value = lifecycle
    onboarding_repo.upsert_sync_job.return_value = job
    account_user_repo = mocker.patch.object(svc, "AccountUserRepository").return_value
    account_user_repo.get_by_user_and_account.return_value = existing_member
    role_repo = mocker.patch.object(
        svc, "ResourceRoleAssignmentRepository"
    ).return_value
    role_repo.has_role.return_value = True

    result = svc.sync_client_onboarding_fde_owner_assignment(
        session,
        LIFECYCLE_ID,
        identity_provider=_FailingFdeOwnerIdentityProvider(),
    )

    assert result.membership_created is False
    assert result.membership_reactivated is True
    assert result.owner_role_assigned is False
    account_user_repo.update_status.assert_called_once_with(
        FDE_USER_ID,
        ACCOUNT_ID,
        AccountUserStatus.active,
    )
    account_user_repo.create.assert_not_called()
    role_repo.add_role.assert_not_called()
    session.commit.assert_called_once()


def test_sync_client_onboarding_fde_owner_assignment_reuses_completed_job(
    mocker: Any,
) -> None:
    session = MagicMock()
    lifecycle = _signed_lifecycle()
    job = MagicMock()
    job.status = ClientOnboardingSyncJobStatus.completed
    job.result_payload = {
        "membership_created": True,
        "membership_reactivated": False,
        "owner_role_assigned": True,
    }
    onboarding_repo = mocker.patch.object(
        svc, "ClientOnboardingRepository"
    ).return_value
    onboarding_repo.get_by_id.return_value = lifecycle
    onboarding_repo.upsert_sync_job.return_value = job
    account_user_repo = mocker.patch.object(svc, "AccountUserRepository")
    role_repo = mocker.patch.object(svc, "ResourceRoleAssignmentRepository")
    handoff_completion = mocker.patch.object(
        svc,
        "orchestrate_client_onboarding_handoff_completion",
    )

    result = svc.sync_client_onboarding_fde_owner_assignment(
        session,
        LIFECYCLE_ID,
        identity_provider=_FailingFdeOwnerIdentityProvider(),
    )

    assert result == ClientOnboardingFdeOwnerAssignmentResult(
        lifecycle_id=LIFECYCLE_ID,
        account_id=ACCOUNT_ID,
        fde_owner_user_id=FDE_USER_ID,
        membership_created=True,
        membership_reactivated=False,
        owner_role_assigned=True,
    )
    account_user_repo.assert_not_called()
    role_repo.assert_not_called()
    onboarding_repo.mark_sync_job_completed.assert_not_called()
    onboarding_repo.append_activity.assert_not_called()
    handoff_completion.assert_called_once_with(session, LIFECYCLE_ID)
    session.commit.assert_not_called()


def test_sync_client_onboarding_fde_owner_assignment_skips_missing_fde_owner(
    mocker: Any,
) -> None:
    session = MagicMock()
    lifecycle = _signed_lifecycle()
    lifecycle.fde_owner_user_id = None
    job = MagicMock()
    job.id = UUID("cccccccc-dddd-eeee-ffff-000000000000")
    job.status = ClientOnboardingSyncJobStatus.pending
    onboarding_repo = mocker.patch.object(
        svc, "ClientOnboardingRepository"
    ).return_value
    onboarding_repo.get_by_id.return_value = lifecycle
    onboarding_repo.upsert_sync_job.return_value = job
    account_user_repo = mocker.patch.object(svc, "AccountUserRepository")

    result = svc.sync_client_onboarding_fde_owner_assignment(
        session,
        LIFECYCLE_ID,
        identity_provider=_FailingFdeOwnerIdentityProvider(),
    )

    assert result.membership_created is False
    assert result.owner_role_assigned is False
    assert result.skipped_reason == "No FDE owner user ID is linked to this lifecycle"
    account_user_repo.assert_not_called()
    onboarding_repo.mark_sync_job_completed.assert_called_once()
    activity = onboarding_repo.append_activity.call_args.kwargs
    assert activity["activity_type"] == "fde_owner_assignment_skipped"
    session.commit.assert_called_once()


def test_sync_client_onboarding_fde_owner_assignment_records_failure(
    mocker: Any,
) -> None:
    session = MagicMock()
    lifecycle = _signed_lifecycle()
    job = MagicMock()
    job.id = UUID("cccccccc-dddd-eeee-ffff-000000000000")
    job.status = ClientOnboardingSyncJobStatus.pending
    onboarding_repo = mocker.patch.object(
        svc, "ClientOnboardingRepository"
    ).return_value
    onboarding_repo.get_by_id.return_value = lifecycle
    onboarding_repo.upsert_sync_job.return_value = job
    account_user_repo = mocker.patch.object(svc, "AccountUserRepository").return_value
    account_user_repo.get_by_user_and_account.return_value = None
    account_user_repo.get_by_user_id.return_value = None
    role_repo = mocker.patch.object(
        svc, "ResourceRoleAssignmentRepository"
    ).return_value
    role_repo.has_role.return_value = False

    with pytest.raises(RuntimeError, match="Identity lookup failed"):
        svc.sync_client_onboarding_fde_owner_assignment(
            session,
            LIFECYCLE_ID,
            identity_provider=_FailingFdeOwnerIdentityProvider(),
        )

    onboarding_repo.mark_sync_job_failed.assert_called_once()
    activity = onboarding_repo.append_activity.call_args.kwargs
    assert activity["activity_type"] == "fde_owner_assignment_failed"
    assert activity["payload_diff"]["error"] == "Identity lookup failed"
    session.commit.assert_called_once()


def test_sync_client_onboarding_fde_owner_assignment_rejects_before_signature(
    mocker: Any,
) -> None:
    session = MagicMock()
    lifecycle = _signed_lifecycle()
    lifecycle.status = ClientOnboardingStatus.docusign_viewed
    onboarding_repo = mocker.patch.object(
        svc, "ClientOnboardingRepository"
    ).return_value
    onboarding_repo.get_by_id.return_value = lifecycle

    with pytest.raises(ClientOnboardingInviteInvalidError):
        svc.sync_client_onboarding_fde_owner_assignment(
            session,
            LIFECYCLE_ID,
            identity_provider=_FakeFdeOwnerIdentityProvider(
                email="fde@palona.ai",
                name="FDE User",
            ),
        )

    onboarding_repo.upsert_sync_job.assert_not_called()
    session.commit.assert_not_called()


def test_orchestrate_client_onboarding_handoff_completion_waits_for_pending_jobs(
    mocker: Any,
) -> None:
    session = MagicMock()
    lifecycle = _signed_lifecycle()
    onboarding_repo = mocker.patch.object(
        svc, "ClientOnboardingRepository"
    ).return_value
    onboarding_repo.get_by_id.return_value = lifecycle
    onboarding_repo.get_sync_jobs_for_lifecycle.return_value = [
        *_completed_handoff_jobs()[:-1],
        _handoff_job(
            ClientOnboardingSyncTarget.manage_app,
            "add_fde_owner",
            ClientOnboardingSyncJobStatus.pending,
        ),
    ]

    result = svc.orchestrate_client_onboarding_handoff_completion(
        session,
        LIFECYCLE_ID,
    )

    assert result == ClientOnboardingHandoffCompletionResult(
        lifecycle_id=LIFECYCLE_ID,
        lifecycle_status=ClientOnboardingStatus.docusign_signed,
        handoff_created=False,
        activation_ready=False,
        pending_sync_jobs=["manage_app:add_fde_owner"],
    )
    onboarding_repo.mark_handoff_created.assert_not_called()
    onboarding_repo.mark_activation_ready.assert_not_called()
    session.commit.assert_not_called()


def test_orchestrate_client_onboarding_handoff_completion_rejects_missing_lifecycle(
    mocker: Any,
) -> None:
    session = MagicMock()
    onboarding_repo = mocker.patch.object(
        svc, "ClientOnboardingRepository"
    ).return_value
    onboarding_repo.get_by_id.return_value = None

    with pytest.raises(ClientOnboardingInviteNotFoundError):
        svc.orchestrate_client_onboarding_handoff_completion(session, LIFECYCLE_ID)

    onboarding_repo.get_sync_jobs_for_lifecycle.assert_not_called()


def test_orchestrate_client_onboarding_handoff_completion_rejects_before_signature(
    mocker: Any,
) -> None:
    session = MagicMock()
    lifecycle = _signed_lifecycle()
    lifecycle.status = ClientOnboardingStatus.docusign_viewed
    onboarding_repo = mocker.patch.object(
        svc, "ClientOnboardingRepository"
    ).return_value
    onboarding_repo.get_by_id.return_value = lifecycle

    with pytest.raises(ClientOnboardingInviteInvalidError):
        svc.orchestrate_client_onboarding_handoff_completion(session, LIFECYCLE_ID)

    onboarding_repo.get_sync_jobs_for_lifecycle.assert_not_called()


def test_orchestrate_client_onboarding_handoff_completion_rejects_missing_signed_time(
    mocker: Any,
) -> None:
    session = MagicMock()
    lifecycle = _signed_lifecycle()
    lifecycle.docusign_signed_at = None
    onboarding_repo = mocker.patch.object(
        svc, "ClientOnboardingRepository"
    ).return_value
    onboarding_repo.get_by_id.return_value = lifecycle

    with pytest.raises(ClientOnboardingInviteInvalidError):
        svc.orchestrate_client_onboarding_handoff_completion(session, LIFECYCLE_ID)

    onboarding_repo.get_sync_jobs_for_lifecycle.assert_not_called()


def test_orchestrate_client_onboarding_handoff_completion_marks_handoff_created(
    mocker: Any,
) -> None:
    session = MagicMock()
    lifecycle = _signed_lifecycle()
    onboarding_repo = mocker.patch.object(
        svc, "ClientOnboardingRepository"
    ).return_value
    onboarding_repo.get_by_id.return_value = lifecycle
    onboarding_repo.get_sync_jobs_for_lifecycle.return_value = _completed_handoff_jobs()

    def mark_handoff_created(*args: object, **kwargs: object) -> MagicMock:
        lifecycle._client_onboarding_transition_changed = True
        lifecycle._client_onboarding_transition_previous_status = (
            ClientOnboardingStatus.docusign_signed
        )
        lifecycle.status = ClientOnboardingStatus.handoff_created
        lifecycle.handoff_created_at = kwargs["occurred_at"]
        return lifecycle

    onboarding_repo.mark_handoff_created.side_effect = mark_handoff_created

    result = svc.orchestrate_client_onboarding_handoff_completion(
        session,
        LIFECYCLE_ID,
    )

    assert result.lifecycle_status == ClientOnboardingStatus.handoff_created
    assert result.handoff_created is True
    assert result.activation_ready is False
    onboarding_repo.mark_handoff_created.assert_called_once()
    onboarding_repo.mark_activation_ready.assert_not_called()
    activity = onboarding_repo.append_activity.call_args.kwargs
    assert activity["activity_type"] == "handoff_created"
    assert activity["previous_status"] == ClientOnboardingStatus.docusign_signed
    assert activity["next_status"] == ClientOnboardingStatus.handoff_created
    assert session.commit.call_count == 1


def test_orchestrate_client_onboarding_handoff_completion_marks_activation_ready(
    mocker: Any,
) -> None:
    session = MagicMock()
    lifecycle = _signed_lifecycle()
    lifecycle.status = ClientOnboardingStatus.password_set
    lifecycle.password_set_at = COMPLETED_AT
    onboarding_repo = mocker.patch.object(
        svc, "ClientOnboardingRepository"
    ).return_value
    onboarding_repo.get_by_id.return_value = lifecycle
    onboarding_repo.get_sync_jobs_for_lifecycle.return_value = _completed_handoff_jobs()

    def mark_handoff_created(*args: object, **kwargs: object) -> MagicMock:
        lifecycle._client_onboarding_transition_changed = True
        lifecycle._client_onboarding_transition_previous_status = (
            ClientOnboardingStatus.password_set
        )
        lifecycle.status = ClientOnboardingStatus.handoff_created
        lifecycle.handoff_created_at = kwargs["occurred_at"]
        return lifecycle

    def mark_activation_ready(*args: object, **kwargs: object) -> MagicMock:
        lifecycle._client_onboarding_transition_changed = True
        lifecycle._client_onboarding_transition_previous_status = (
            ClientOnboardingStatus.handoff_created
        )
        lifecycle.status = ClientOnboardingStatus.activation_ready
        lifecycle.activation_ready_at = kwargs["occurred_at"]
        return lifecycle

    onboarding_repo.mark_handoff_created.side_effect = mark_handoff_created
    onboarding_repo.mark_activation_ready.side_effect = mark_activation_ready

    result = svc.orchestrate_client_onboarding_handoff_completion(
        session,
        LIFECYCLE_ID,
    )

    assert result.lifecycle_status == ClientOnboardingStatus.activation_ready
    assert result.handoff_created is True
    assert result.activation_ready is True
    assert [
        call.kwargs["activity_type"]
        for call in onboarding_repo.append_activity.call_args_list
    ] == [
        "handoff_created",
        "activation_ready",
    ]
    assert session.commit.call_count == 2


def test_attempt_handoff_completion_logs_failure(mocker: Any) -> None:
    session = MagicMock()
    orchestrate = mocker.patch.object(
        svc,
        "orchestrate_client_onboarding_handoff_completion",
        side_effect=RuntimeError("orchestration failed"),
    )
    logger = mocker.patch.object(svc.logger, "exception")

    svc._attempt_handoff_completion(session, LIFECYCLE_ID)

    orchestrate.assert_called_once_with(session, LIFECYCLE_ID)
    logger.assert_called_once()


def test_mark_client_onboarding_password_set_after_handoff_marks_activation_ready(
    mocker: Any,
    monkeypatch: Any,
) -> None:
    session = MagicMock()
    context = MagicMock(
        username=str(AE_USER_ID),
        email="signer@example.com",
    )
    deps = _client_onboarding_invite_dependencies(
        mocker,
        monkeypatch,
        lifecycle_status=ClientOnboardingStatus.handoff_created,
    )
    lifecycle = deps["lifecycle"]
    lifecycle.handoff_created_at = COMPLETED_AT

    def complete_handoff(*args: object, **kwargs: object) -> Any:
        lifecycle.status = ClientOnboardingStatus.activation_ready
        return ClientOnboardingHandoffCompletionResult(
            lifecycle_id=LIFECYCLE_ID,
            lifecycle_status=ClientOnboardingStatus.activation_ready,
            handoff_created=True,
            activation_ready=True,
            pending_sync_jobs=[],
        )

    deps["handoff_completion"].side_effect = complete_handoff

    result = svc.mark_client_onboarding_password_set(
        session,
        context,
        "invite-token",
    )

    assert result.lifecycle_status == ClientOnboardingStatus.activation_ready
    deps["onboarding_repo"].mark_password_set.assert_called_once()
    deps["handoff_completion"].assert_called_once_with(session, LIFECYCLE_ID)
    activity = deps["onboarding_repo"].append_activity.call_args.kwargs
    assert activity["activity_type"] == "password_set"
    assert activity["previous_status"] == ClientOnboardingStatus.handoff_created
    assert activity["next_status"] == ClientOnboardingStatus.handoff_created


def test_sync_client_onboarding_fde_owner_assignment_rejects_missing_lifecycle(
    mocker: Any,
) -> None:
    session = MagicMock()
    onboarding_repo = mocker.patch.object(
        svc, "ClientOnboardingRepository"
    ).return_value
    onboarding_repo.get_by_id.return_value = None

    with pytest.raises(
        ClientOnboardingInviteNotFoundError,
        match="Client onboarding lifecycle not found",
    ):
        svc.sync_client_onboarding_fde_owner_assignment(
            session,
            LIFECYCLE_ID,
            identity_provider=_FakeFdeOwnerIdentityProvider(
                email="fde@palona.ai",
                name="FDE User",
            ),
        )

    onboarding_repo.upsert_sync_job.assert_not_called()
    session.commit.assert_not_called()


def test_sync_client_onboarding_fde_owner_assignment_rejects_missing_signed_time(
    mocker: Any,
) -> None:
    session = MagicMock()
    lifecycle = _signed_lifecycle()
    lifecycle.docusign_signed_at = None
    onboarding_repo = mocker.patch.object(
        svc, "ClientOnboardingRepository"
    ).return_value
    onboarding_repo.get_by_id.return_value = lifecycle

    with pytest.raises(
        ClientOnboardingInviteInvalidError,
        match="missing DocuSign signed timestamp",
    ):
        svc.sync_client_onboarding_fde_owner_assignment(
            session,
            LIFECYCLE_ID,
            identity_provider=_FakeFdeOwnerIdentityProvider(
                email="fde@palona.ai",
                name="FDE User",
            ),
        )

    onboarding_repo.upsert_sync_job.assert_not_called()
    session.commit.assert_not_called()


def test_add_fde_owner_to_manage_app_account_requires_account_id() -> None:
    lifecycle = _signed_lifecycle()
    lifecycle.account_id = None

    with pytest.raises(
        ClientOnboardingInviteInvalidError,
        match="missing account id",
    ):
        svc._add_fde_owner_to_manage_app_account(
            MagicMock(),
            lifecycle,
            identity_provider=_FakeFdeOwnerIdentityProvider(
                email="fde@palona.ai",
                name="FDE User",
            ),
        )


def test_add_fde_owner_to_manage_app_account_requires_fde_owner() -> None:
    lifecycle = _signed_lifecycle()
    lifecycle.fde_owner_user_id = None

    with pytest.raises(
        ClientOnboardingInviteInvalidError,
        match="missing FDE owner user id",
    ):
        svc._add_fde_owner_to_manage_app_account(
            MagicMock(),
            lifecycle,
            identity_provider=_FakeFdeOwnerIdentityProvider(
                email="fde@palona.ai",
                name="FDE User",
            ),
        )


def test_resolve_fde_owner_identity_reuses_existing_membership() -> None:
    account_user_repo = MagicMock()
    existing_member = MagicMock()
    existing_member.email = " fde@palona.ai "
    existing_member.name = " FDE User "
    account_user_repo.get_by_user_id.return_value = existing_member

    identity = svc._resolve_fde_owner_identity(
        account_user_repo,
        FDE_USER_ID,
        identity_provider=_FailingFdeOwnerIdentityProvider(),
    )

    assert identity == svc._FdeOwnerIdentity(
        email="fde@palona.ai",
        name="FDE User",
    )


def test_resolve_fde_owner_identity_rejects_missing_email() -> None:
    account_user_repo = MagicMock()
    account_user_repo.get_by_user_id.return_value = None

    with pytest.raises(ValueError, match=f"FDE owner {FDE_USER_ID} does not have"):
        svc._resolve_fde_owner_identity(
            account_user_repo,
            FDE_USER_ID,
            identity_provider=_FakeFdeOwnerIdentityProvider(email="   ", name=None),
        )


def test_build_fde_owner_identity_provider_returns_cognito_provider() -> None:
    assert isinstance(
        svc._build_fde_owner_identity_provider(),
        svc._CognitoFdeOwnerIdentityProvider,
    )


def test_cognito_fde_owner_identity_provider_reads_user(monkeypatch: Any) -> None:
    fake_client = MagicMock()
    fake_client.list_users.return_value = {
        "Users": [
            {
                "Attributes": [
                    {"Name": "email", "Value": "fde@palona.ai"},
                    {"Name": "name", "Value": "FDE User"},
                ]
            }
        ]
    }
    boto3_module = _install_fake_boto3(monkeypatch, fake_client)
    monkeypatch.setattr(
        svc,
        "get_client_secret_with_fallback",
        MagicMock(return_value="pool-123"),
    )
    monkeypatch.setenv("AWS_REGION", "us-west-2")

    identity = svc._CognitoFdeOwnerIdentityProvider().get_identity(FDE_USER_ID)

    assert identity == svc._FdeOwnerIdentity(
        email="fde@palona.ai",
        name="FDE User",
    )
    client_config = boto3_module.client.call_args.kwargs["config"]
    boto3_module.client.assert_called_once_with(
        "cognito-idp",
        region_name="us-west-2",
        config=client_config,
    )
    assert (
        client_config.connect_timeout == svc.COGNITO_FDE_OWNER_CONNECT_TIMEOUT_SECONDS
    )
    assert client_config.read_timeout == svc.COGNITO_FDE_OWNER_READ_TIMEOUT_SECONDS
    assert client_config.retries == {
        "max_attempts": svc.COGNITO_FDE_OWNER_MAX_ATTEMPTS,
        "mode": "standard",
    }
    fake_client.list_users.assert_called_once_with(
        UserPoolId="pool-123",
        Filter=f'sub="{FDE_USER_ID}"',
    )


def test_cognito_fde_owner_identity_provider_requires_user_pool(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(
        svc,
        "get_client_secret_with_fallback",
        MagicMock(side_effect=ValueError("missing secret")),
    )

    with pytest.raises(
        RuntimeError,
        match="AWS_ADMIN_CONSOLE_USER_POOL_ID is not configured",
    ):
        svc._CognitoFdeOwnerIdentityProvider().get_identity(FDE_USER_ID)


def test_cognito_fde_owner_identity_provider_rejects_blank_user_pool(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(
        svc,
        "get_client_secret_with_fallback",
        MagicMock(return_value=""),
    )

    with pytest.raises(
        RuntimeError,
        match="AWS_ADMIN_CONSOLE_USER_POOL_ID is not configured",
    ):
        svc._CognitoFdeOwnerIdentityProvider().get_identity(FDE_USER_ID)


def test_cognito_fde_owner_identity_provider_rejects_missing_user(
    monkeypatch: Any,
) -> None:
    fake_client = MagicMock()
    fake_client.list_users.return_value = {"Users": []}
    _install_fake_boto3(monkeypatch, fake_client)
    monkeypatch.setattr(
        svc,
        "get_client_secret_with_fallback",
        MagicMock(return_value="pool-123"),
    )

    with pytest.raises(ValueError, match=f"FDE owner {FDE_USER_ID} was not found"):
        svc._CognitoFdeOwnerIdentityProvider().get_identity(FDE_USER_ID)


def test_cognito_fde_owner_identity_provider_rejects_missing_email(
    monkeypatch: Any,
) -> None:
    fake_client = MagicMock()
    fake_client.list_users.return_value = {
        "Users": [{"Attributes": [{"Name": "name", "Value": "FDE User"}]}]
    }
    _install_fake_boto3(monkeypatch, fake_client)
    monkeypatch.setattr(
        svc,
        "get_client_secret_with_fallback",
        MagicMock(return_value="pool-123"),
    )

    with pytest.raises(ValueError, match="does not have an email in Cognito"):
        svc._CognitoFdeOwnerIdentityProvider().get_identity(FDE_USER_ID)


def test_cognito_attribute_handles_invalid_values() -> None:
    assert svc._cognito_attribute("not-a-list", "email") is None
    assert (
        svc._cognito_attribute(
            [
                object(),
                {"Name": "name", "Value": "FDE User"},
            ],
            "email",
        )
        is None
    )
    assert svc._cognito_attribute([{"Name": "email", "Value": ""}], "email") is None


def test_public_sync_client_onboarding_slack_handoff_wrapper_delegates(
    mocker: Any,
) -> None:
    session = MagicMock()
    expected = ClientOnboardingSlackHandoffResult(
        lifecycle_id=LIFECYCLE_ID,
        slack_channel_id="C123",
        slack_channel_name="client-acme",
        created_channel=True,
        invited_user_ids=["UAE123"],
        posted_message=True,
        message_ts="1718820000.000100",
    )
    sync = mocker.patch(
        "services.client_onboarding_service._implementation.sync_client_onboarding_slack_handoff",
        return_value=expected,
    )

    result = public_svc.sync_client_onboarding_slack_handoff(
        session,
        LIFECYCLE_ID,
    )

    assert result is expected
    sync.assert_called_once_with(session=session, lifecycle_id=LIFECYCLE_ID)


def test_public_sync_client_onboarding_notion_cmd_entry_wrapper_delegates(
    mocker: Any,
) -> None:
    session = MagicMock()
    expected = ClientOnboardingNotionSyncResult(
        lifecycle_id=LIFECYCLE_ID,
        notion_page_id="notion-page-123",
        created_page=True,
        updated_page=False,
    )
    sync = mocker.patch(
        "services.client_onboarding_service._implementation.sync_client_onboarding_notion_cmd_entry",
        return_value=expected,
    )

    result = public_svc.sync_client_onboarding_notion_cmd_entry(
        session,
        LIFECYCLE_ID,
    )

    assert result is expected
    sync.assert_called_once_with(session=session, lifecycle_id=LIFECYCLE_ID)


def test_public_sync_client_onboarding_fde_owner_assignment_wrapper_delegates(
    mocker: Any,
) -> None:
    session = MagicMock()
    expected = ClientOnboardingFdeOwnerAssignmentResult(
        lifecycle_id=LIFECYCLE_ID,
        account_id=ACCOUNT_ID,
        fde_owner_user_id=FDE_USER_ID,
        membership_created=True,
        membership_reactivated=False,
        owner_role_assigned=True,
    )
    sync = mocker.patch(
        "services.client_onboarding_service._implementation.sync_client_onboarding_fde_owner_assignment",
        return_value=expected,
    )

    result = public_svc.sync_client_onboarding_fde_owner_assignment(
        session,
        LIFECYCLE_ID,
    )

    assert result is expected
    sync.assert_called_once_with(session=session, lifecycle_id=LIFECYCLE_ID)


def test_public_sync_client_onboarding_contract_acceptance_to_folk_wrapper_delegates(
    mocker: Any,
) -> None:
    session = MagicMock()
    expected = ClientOnboardingFolkSyncResult(
        lifecycle_id=LIFECYCLE_ID,
        folk_company_id="folk-company-123",
        folk_contact_id="folk-contact-123",
        updated_company=True,
        updated_contact=True,
    )
    sync = mocker.patch(
        "services.client_onboarding_service._implementation.sync_client_onboarding_contract_acceptance_to_folk",
        return_value=expected,
    )

    result = public_svc.sync_client_onboarding_contract_acceptance_to_folk(
        session,
        LIFECYCLE_ID,
    )

    assert result is expected
    sync.assert_called_once_with(session=session, lifecycle_id=LIFECYCLE_ID)


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


def _signed_lifecycle() -> MagicMock:
    lifecycle = MagicMock()
    lifecycle.id = LIFECYCLE_ID
    lifecycle.status = ClientOnboardingStatus.docusign_signed
    lifecycle.account_id = ACCOUNT_ID
    lifecycle.manage_app_account_name = "acme"
    lifecycle.client_company_name = "Acme Inc."
    lifecycle.signer_name = "Client Signer"
    lifecycle.signer_email = "signer@example.com"
    lifecycle.contract_type = ClientOnboardingContractType.order_form_tos
    lifecycle.docusign_contract_id = "contract-123"
    lifecycle.docusign_envelope_id = "envelope-123"
    lifecycle.docusign_contract_url = "https://docusign.example/sign/123"
    lifecycle.docusign_signed_at = COMPLETED_AT
    lifecycle.password_set_at = None
    lifecycle.ae_owner_user_id = AE_USER_ID
    lifecycle.fde_owner_user_id = FDE_USER_ID
    lifecycle.folk_company_id = "folk-company-123"
    lifecycle.folk_contact_id = "folk-contact-123"
    lifecycle.slack_channel_id = None
    lifecycle.notion_page_id = "notion-page-123"
    lifecycle.scoping_doc_url = "https://notion.example/scoping"
    lifecycle.handoff_created_at = None
    lifecycle.activation_ready_at = None
    return lifecycle


def _handoff_job(
    target: ClientOnboardingSyncTarget,
    job_type: str,
    status: ClientOnboardingSyncJobStatus = ClientOnboardingSyncJobStatus.completed,
) -> MagicMock:
    job = MagicMock()
    job.target = target
    job.job_type = job_type
    job.status = status
    return job


def _completed_handoff_jobs() -> list[MagicMock]:
    return [
        _handoff_job(
            ClientOnboardingSyncTarget.database,
            "record_contract_acceptance",
        ),
        _handoff_job(
            ClientOnboardingSyncTarget.folk,
            "update_contract_acceptance",
        ),
        _handoff_job(
            ClientOnboardingSyncTarget.slack,
            "create_handoff_channel",
        ),
        _handoff_job(
            ClientOnboardingSyncTarget.notion,
            "upsert_cmd_entry",
        ),
        _handoff_job(
            ClientOnboardingSyncTarget.manage_app,
            "add_fde_owner",
        ),
    ]


def _patch_handoff_owner_contacts(mocker: Any) -> MagicMock:
    ae_account_user = MagicMock()
    ae_account_user.email = "ae@palona.ai"
    ae_account_user.name = "AE User"
    fde_account_user = MagicMock()
    fde_account_user.email = "fde@palona.ai"
    fde_account_user.name = "FDE User"
    account_users = {
        AE_USER_ID: ae_account_user,
        FDE_USER_ID: fde_account_user,
    }
    account_user_repo = mocker.patch.object(svc, "AccountUserRepository").return_value
    account_user_repo.get_by_user_and_account.side_effect = (
        lambda user_id, account_id: account_users.get(user_id)
    )
    account_user_repo.get_by_user_id.return_value = None
    return account_user_repo


class _SlackResponse:
    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data


class _FakeSlackSdkClient:
    def __init__(
        self,
        user_ids_by_email: dict[str, str],
        *,
        create_error: str | None = None,
        channels_by_name: dict[str, str] | None = None,
    ) -> None:
        self.user_ids_by_email = user_ids_by_email
        self.create_error = create_error
        self.channels_by_name = channels_by_name or {}
        self.created_channels: list[dict[str, Any]] = []
        self.channel_list_requests: list[str | None] = []
        self.invites: list[dict[str, Any]] = []
        self.messages: list[dict[str, Any]] = []
        setattr(self, "chat_postMessage", self._chat_post_message)
        setattr(self, "users_lookupByEmail", self._users_lookup_by_email)

    async def conversations_create(
        self,
        *,
        name: str,
        is_private: bool,
    ) -> _SlackResponse:
        self.created_channels.append({"name": name, "is_private": is_private})
        if self.create_error:
            return _SlackResponse({"ok": False, "error": self.create_error})
        return _SlackResponse({"ok": True, "channel": {"id": "C123", "name": name}})

    async def conversations_list(
        self,
        *,
        exclude_archived: bool,
        limit: int,
        types: str,
        cursor: str | None,
    ) -> dict[str, Any]:
        self.channel_list_requests.append(cursor)
        return {
            "ok": True,
            "channels": [
                {"id": channel_id, "name": channel_name}
                for channel_name, channel_id in self.channels_by_name.items()
            ],
            "response_metadata": {"next_cursor": ""},
        }

    async def conversations_invite(
        self,
        *,
        channel: str,
        users: list[str],
    ) -> dict[str, Any]:
        self.invites.append({"channel_id": channel, "user_ids": users})
        return {"ok": True}

    async def _chat_post_message(
        self,
        *,
        channel: str,
        text: str,
        blocks: list[dict[str, Any]],
        mrkdwn: bool,
    ) -> dict[str, Any]:
        self.messages.append(
            {
                "channel_id": channel,
                "text": text,
                "blocks": blocks,
                "mrkdwn": mrkdwn,
            }
        )
        return {"ok": True, "ts": "1718820000.000100"}

    async def _users_lookup_by_email(self, *, email: str) -> dict[str, Any]:
        slack_user_id = self.user_ids_by_email.get(email)
        if slack_user_id is None:
            return {"ok": False, "error": "users_not_found"}
        return {"ok": True, "user": {"id": slack_user_id}}


class _FakeSlackHandoffClient:
    async def create_channel(
        self,
        *,
        name: str,
        is_private: bool,
    ) -> dict[str, Any]:
        return {"ok": True, "channel": {"id": "C123", "name": name}}

    async def invite_users(
        self,
        *,
        channel_id: str,
        user_ids: list[str],
    ) -> dict[str, Any]:
        return {"ok": True}

    async def post_message(
        self,
        *,
        channel_id: str,
        text: str,
        blocks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {"ok": True, "ts": "1718820000.000100"}

    async def lookup_user_id_by_email(self, *, email: str) -> str | None:
        return None

    async def find_channel_id_by_name(self, *, name: str) -> str | None:
        return None


class _FailingSlackHandoffClient(_FakeSlackHandoffClient):
    async def create_channel(
        self,
        *,
        name: str,
        is_private: bool,
    ) -> dict[str, Any]:
        return {"ok": False, "error": "missing_scope"}


class _FakeNotionCmdEntryClient:
    def __init__(
        self,
        *,
        found_page: dict[str, Any] | None = None,
        created_page_id: str = "notion-page-123",
    ) -> None:
        self.found_page = found_page
        self.created_page_id = created_page_id
        self.find_page_requests: list[Any] = []
        self.created_pages: list[dict[str, Any]] = []
        self.updated_pages: list[dict[str, Any]] = []

    async def find_page(self, company: Any) -> dict[str, Any] | None:
        self.find_page_requests.append(company)
        return self.found_page

    async def create_page(
        self,
        properties: dict[str, Any],
        children: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        self.created_pages.append(
            {"properties": properties, "children": children or []}
        )
        return {"id": self.created_page_id}

    async def update_page(
        self,
        page_id: str,
        properties: dict[str, Any],
    ) -> dict[str, Any]:
        self.updated_pages.append({"page_id": page_id, "properties": properties})
        return {"id": page_id}


class _FailingNotionCmdEntryClient(_FakeNotionCmdEntryClient):
    async def find_page(self, company: Any) -> dict[str, Any] | None:
        raise RuntimeError("Notion unavailable")


class _FakeFdeOwnerIdentityProvider:
    def __init__(self, *, email: str, name: str | None) -> None:
        self.email = email
        self.name = name

    def get_identity(self, user_id: UUID) -> svc._FdeOwnerIdentity:
        return svc._FdeOwnerIdentity(email=self.email, name=self.name)


class _FailingFdeOwnerIdentityProvider:
    def get_identity(self, user_id: UUID) -> svc._FdeOwnerIdentity:
        raise RuntimeError("Identity lookup failed")


def _install_fake_boto3(monkeypatch: Any, fake_client: MagicMock) -> Any:
    boto3_module: Any = ModuleType("boto3")
    boto3_module.client = MagicMock(return_value=fake_client)
    monkeypatch.setitem(sys.modules, "boto3", boto3_module)
    return boto3_module


class _FakeFolkContractAcceptanceClient:
    def __init__(self) -> None:
        self.company_updates: list[tuple[str, dict[str, Any]]] = []
        self.contact_updates: list[tuple[str, dict[str, Any]]] = []

    async def update_company(
        self,
        company_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self.company_updates.append((company_id, payload))
        return {"id": company_id}

    async def update_contact(
        self,
        contact_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self.contact_updates.append((contact_id, payload))
        return {"id": contact_id}


class _FailingFolkContractAcceptanceClient:
    async def update_company(
        self,
        company_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        raise RuntimeError("Folk unavailable")

    async def update_contact(
        self,
        contact_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        raise RuntimeError("Folk unavailable")
