"""Tests for team invitation temporary-password handling."""

from unittest.mock import MagicMock
from uuid import UUID

import pytest
from botocore.exceptions import ClientError
from pytest_mock import MockerFixture

from services.auth_types import UserContext, UserRole
from services.team_service import _implementation as svc
from services.team_service.schema import InvitationParams, UpdateMemberRoleParams

ACCOUNT_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
INVITER_ID = UUID("11111111-2222-3333-4444-555555555555")
INVITATION_ID = UUID("99999999-8888-7777-6666-555555555555")
ACCOUNT_NAME = "acme_test"
ACCOUNT_DISPLAY_NAME = "Acme Test"
INVITEE_EMAIL = "invitee@example.com"
INVITATION_TOKEN = "db-invitation-token"
PROJECT_ID = UUID("22222222-3333-4444-5555-666666666666")


@pytest.fixture
def user_context() -> UserContext:
    """Build an inviter context with a UUID username for audit fields."""
    return UserContext(
        username=str(INVITER_ID),
        email="owner@example.com",
        groups=[],
        display_name="Owner User",
        role=UserRole.AccountManager,
    )


@pytest.fixture
def repositories(mocker: MockerFixture) -> dict[str, MagicMock]:
    """Patch repositories used by create_invitation."""
    account = MagicMock()
    account.id = ACCOUNT_ID
    account.name = ACCOUNT_NAME
    account.display_name = ACCOUNT_DISPLAY_NAME

    invitation = MagicMock()
    invitation.id = INVITATION_ID
    invitation.account_id = ACCOUNT_ID
    invitation.email = INVITEE_EMAIL
    invitation.invitation_token = INVITATION_TOKEN

    account_repo = mocker.patch.object(svc, "AccountRepository").return_value
    account_repo.get_account.return_value = account

    account_user_repo = mocker.patch.object(svc, "AccountUserRepository").return_value
    account_user_repo.get_by_email_and_account.return_value = None

    invitation_repo = mocker.patch.object(svc, "UserInvitationRepository").return_value
    invitation_repo.has_pending_for_email.return_value = False
    invitation_repo.create.return_value = invitation

    return {
        "account": account,
        "account_repo": account_repo,
        "account_user_repo": account_user_repo,
        "invitation": invitation,
        "invitation_repo": invitation_repo,
    }


def _patch_external_dependencies(
    mocker: MockerFixture,
    *,
    user_exists: bool,
    user_status: str | None,
    passwords: list[str],
) -> dict[str, MagicMock]:
    """Patch Cognito, password generation, JWT generation, and email sending."""
    cognito_client = MagicMock()
    boto3_client = mocker.patch.object(
        svc.boto3,
        "client",
        return_value=cognito_client,
    )
    get_status = mocker.patch.object(
        svc,
        "get_cognito_user_status",
        return_value=(user_exists, user_status),
    )
    generate_password = mocker.patch.object(
        svc,
        "generate_password",
        side_effect=passwords,
    )
    generate_jwt = mocker.patch.object(
        svc,
        "generate_invitation_jwt",
        return_value="encoded-invitation-jwt",
    )
    send_email = mocker.patch.object(svc.email_service, "send_email_with_template")
    token_urlsafe = mocker.patch.object(
        svc.secrets,
        "token_urlsafe",
        return_value=INVITATION_TOKEN,
    )

    return {
        "boto3_client": boto3_client,
        "cognito_client": cognito_client,
        "generate_jwt": generate_jwt,
        "generate_password": generate_password,
        "get_status": get_status,
        "send_email": send_email,
        "token_urlsafe": token_urlsafe,
    }


def _create_invitation(user_context: UserContext) -> object:
    """Call the service with the standard account-level Admin invite."""
    return svc.create_invitation(
        session=MagicMock(),
        context=user_context,
        account_name=ACCOUNT_NAME,
        params=InvitationParams(email=INVITEE_EMAIL, account_role="account_admin"),
    )


@pytest.mark.parametrize("legacy_role", ["owner", "manager", "viewer", "staff"])
def test_create_invitation_rejects_legacy_customer_roles(
    legacy_role: str,
    user_context: UserContext,
) -> None:
    with pytest.raises(ValueError, match="Unsupported customer role"):
        svc.create_invitation(
            session=MagicMock(),
            context=user_context,
            account_name=ACCOUNT_NAME,
            params=InvitationParams(email=INVITEE_EMAIL, account_role=legacy_role),
        )


@pytest.mark.parametrize("store_role", ["store_owner", "store_member"])
def test_create_invitation_rejects_store_roles_without_project_ids(
    store_role: str,
    user_context: UserContext,
) -> None:
    with pytest.raises(ValueError, match="invitations require project_ids"):
        svc.create_invitation(
            session=MagicMock(),
            context=user_context,
            account_name=ACCOUNT_NAME,
            params=InvitationParams(email=INVITEE_EMAIL, account_role=store_role),
        )


@pytest.mark.parametrize("store_role", ["store_owner", "store_member"])
def test_create_invitation_rejects_store_roles_with_empty_project_ids(
    store_role: str,
    user_context: UserContext,
) -> None:
    with pytest.raises(ValueError, match="invitations require project_ids"):
        svc.create_invitation(
            session=MagicMock(),
            context=user_context,
            account_name=ACCOUNT_NAME,
            params=InvitationParams(
                email=INVITEE_EMAIL,
                account_role=store_role,
                project_ids=[],
            ),
        )


def test_create_invitation_rejects_account_admin_project_ids(
    user_context: UserContext,
) -> None:
    with pytest.raises(ValueError, match="account_admin invitations must omit"):
        svc.create_invitation(
            session=MagicMock(),
            context=user_context,
            account_name=ACCOUNT_NAME,
            params=InvitationParams(
                email=INVITEE_EMAIL,
                account_role="account_admin",
                project_ids=[PROJECT_ID],
            ),
        )


@pytest.mark.parametrize("store_role", ["store_owner", "store_member"])
def test_update_member_role_rejects_store_roles_without_project_scope(
    store_role: str,
    user_context: UserContext,
) -> None:
    with pytest.raises(ValueError, match="updates require explicit project scope"):
        svc.update_member_role(
            session=MagicMock(),
            context=user_context,
            account_name=ACCOUNT_NAME,
            user_email=INVITEE_EMAIL,
            params=UpdateMemberRoleParams(account_role=store_role),
        )


def test_create_invitation_new_cognito_user_embeds_temporary_password(
    mocker: MockerFixture,
    repositories: dict[str, MagicMock],
    user_context: UserContext,
) -> None:
    mocks = _patch_external_dependencies(
        mocker,
        user_exists=False,
        user_status=None,
        passwords=["TempPass123!"],
    )

    result = _create_invitation(user_context)

    assert result == repositories["invitation"]
    mocks["cognito_client"].admin_create_user.assert_called_once()
    create_kwargs = mocks["cognito_client"].admin_create_user.call_args.kwargs
    assert create_kwargs["TemporaryPassword"] == "TempPass123!"
    mocks["cognito_client"].admin_set_user_password.assert_not_called()
    assert mocks["generate_jwt"].call_args.kwargs["temporary_password"] == (
        "TempPass123!"
    )
    assert mocks["send_email"].call_args.kwargs["template_id"] == (
        svc.TEAM_INVITATION_NEW_USER_TEMPLATE_ID
    )


def test_create_invitation_pending_cognito_user_resets_and_embeds_password(
    mocker: MockerFixture,
    repositories: dict[str, MagicMock],
    user_context: UserContext,
) -> None:
    mocks = _patch_external_dependencies(
        mocker,
        user_exists=True,
        user_status="FORCE_CHANGE_PASSWORD",
        passwords=["UnusedInitial123!", "ResetTemp123!"],
    )

    result = _create_invitation(user_context)

    assert result == repositories["invitation"]
    mocks["cognito_client"].admin_create_user.assert_not_called()
    mocks["cognito_client"].admin_set_user_password.assert_called_once_with(
        UserPoolId=svc.AWS_ADMIN_CONSOLE_USER_POOL_ID,
        Username=INVITEE_EMAIL,
        Password="ResetTemp123!",
        Permanent=False,
    )
    assert mocks["generate_password"].call_count == 2
    assert mocks["generate_jwt"].call_args.kwargs["temporary_password"] == (
        "ResetTemp123!"
    )

    email_kwargs = mocks["send_email"].call_args.kwargs
    assert email_kwargs["template_id"] == svc.TEAM_INVITATION_NEW_USER_TEMPLATE_ID
    invitation_url = email_kwargs["template_model"]["invitation_url"]
    assert invitation_url.startswith("https://")
    assert invitation_url.endswith("/accept-invitation?token=encoded-invitation-jwt")
    assert "reset_password_url" not in email_kwargs["template_model"]


def test_create_invitation_pending_cognito_user_skips_email_when_reset_fails(
    mocker: MockerFixture,
    repositories: dict[str, MagicMock],
    user_context: UserContext,
) -> None:
    mocks = _patch_external_dependencies(
        mocker,
        user_exists=True,
        user_status="FORCE_CHANGE_PASSWORD",
        passwords=["UnusedInitial123!", "ResetTemp123!"],
    )
    reset_error = ClientError(
        {
            "Error": {
                "Code": "InvalidPasswordException",
                "Message": "Password does not conform to policy",
            }
        },
        "AdminSetUserPassword",
    )
    mocks["cognito_client"].admin_set_user_password.side_effect = reset_error

    result = _create_invitation(user_context)

    assert result == repositories["invitation"]
    mocks["cognito_client"].admin_set_user_password.assert_called_once_with(
        UserPoolId=svc.AWS_ADMIN_CONSOLE_USER_POOL_ID,
        Username=INVITEE_EMAIL,
        Password="ResetTemp123!",
        Permanent=False,
    )
    mocks["generate_jwt"].assert_not_called()
    mocks["send_email"].assert_not_called()


def test_create_invitation_confirmed_cognito_user_does_not_embed_password(
    mocker: MockerFixture,
    repositories: dict[str, MagicMock],
    user_context: UserContext,
) -> None:
    mocks = _patch_external_dependencies(
        mocker,
        user_exists=True,
        user_status="CONFIRMED",
        passwords=["UnusedInitial123!"],
    )

    result = _create_invitation(user_context)

    assert result == repositories["invitation"]
    mocks["boto3_client"].assert_not_called()
    assert mocks["generate_jwt"].call_args.kwargs["temporary_password"] is None
    assert mocks["send_email"].call_args.kwargs["template_id"] == (
        svc.TEAM_INVITATION_EXISTING_USER_TEMPLATE_ID
    )
