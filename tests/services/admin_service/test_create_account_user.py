"""Tests for admin_service.create_account_user (PAL-10487 phase 2)."""

from unittest.mock import MagicMock
from uuid import UUID

import pytest
from botocore.exceptions import ClientError
from pytest_mock import MockerFixture

from services.admin_service import _implementation as svc

# A deterministic uuid so we can assert on AccountUserRepository.create kwargs.
FAKE_USER_SUB = "11111111-2222-3333-4444-555555555555"
FAKE_ACCOUNT_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
ACCOUNT_NAME = "acme_test"
EMAIL = "new@example.com"
NAME = "New User"


def _make_cognito_client(
    *,
    create_raises: Exception | None = None,
) -> MagicMock:
    """Build a stubbed boto3 cognito-idp client."""
    client = MagicMock()
    if create_raises is not None:
        client.admin_create_user.side_effect = create_raises
    client.admin_get_user.return_value = {
        "UserAttributes": [
            {"Name": "sub", "Value": FAKE_USER_SUB},
            {"Name": "email", "Value": EMAIL},
        ],
    }
    return client


def _username_exists_error() -> ClientError:
    return ClientError(
        error_response={
            "Error": {
                "Code": "UsernameExistsException",
                "Message": "User account already exists",
            }
        },
        operation_name="AdminCreateUser",
    )


def _other_cognito_error() -> ClientError:
    return ClientError(
        error_response={
            "Error": {
                "Code": "InvalidParameterException",
                "Message": "bad param",
            }
        },
        operation_name="AdminCreateUser",
    )


@pytest.fixture
def patch_boto3(mocker: MockerFixture) -> MagicMock:
    """Patch boto3.client inside the service to return our stub."""
    client = _make_cognito_client()
    mocker.patch.object(svc.boto3, "client", return_value=client)
    return client


@pytest.fixture
def patch_repos(mocker: MockerFixture) -> dict[str, MagicMock]:
    """Patch AccountRepository + AccountUserRepository used inside _attach_user_to_account."""
    account = MagicMock()
    account.id = FAKE_ACCOUNT_ID
    account.name = ACCOUNT_NAME

    account_repo_cls = mocker.patch.object(svc, "AccountRepository")
    account_repo_cls.return_value.get_account.return_value = account

    account_user_repo_cls = mocker.patch.object(svc, "AccountUserRepository")
    account_user_repo_cls.return_value.get_by_email_and_account.return_value = None
    account_user_repo_cls.return_value.create.return_value = MagicMock()

    return {
        "account_repo": account_repo_cls.return_value,
        "account_user_repo": account_user_repo_cls.return_value,
    }


@pytest.fixture
def patch_email(mocker: MockerFixture) -> MagicMock:
    """Patch email_service.send_email_with_template."""
    return mocker.patch.object(svc.email_service, "send_email_with_template")


# ─── happy path: brand-new Cognito user ─────────────────────────────────────


def test_create_account_user_new_cognito_user_creates_row_and_sends_email(
    patch_boto3: MagicMock,
    patch_repos: dict[str, MagicMock],
    patch_email: MagicMock,
) -> None:
    session = MagicMock()
    result = svc.create_account_user(ACCOUNT_NAME, EMAIL, NAME, session)

    # Cognito user was created
    patch_boto3.admin_create_user.assert_called_once()

    # account_user row was created with the sub returned by admin_get_user
    patch_repos["account_user_repo"].create.assert_called_once()
    kwargs = patch_repos["account_user_repo"].create.call_args.kwargs
    assert kwargs["user_id"] == UUID(FAKE_USER_SUB)
    assert kwargs["email"] == EMAIL
    assert kwargs["account_id"] == FAKE_ACCOUNT_ID

    # Welcome email WAS sent (path 1)
    patch_email.assert_called_once()

    assert result.email == EMAIL
    assert result.name == NAME


# ─── path 2: existing Cognito user → attach, no email ───────────────────────


def test_create_account_user_existing_cognito_attaches_without_email(
    mocker: MockerFixture,
    patch_repos: dict[str, MagicMock],
    patch_email: MagicMock,
) -> None:
    """Regression for PAL-10487: UsernameExistsException must not abort onboarding."""
    client = _make_cognito_client(create_raises=_username_exists_error())
    mocker.patch.object(svc.boto3, "client", return_value=client)

    session = MagicMock()
    result = svc.create_account_user(ACCOUNT_NAME, EMAIL, NAME, session)

    # Creation was attempted (and raised) — we recovered.
    client.admin_create_user.assert_called_once()
    client.admin_get_user.assert_called()  # used to fetch existing sub

    # account_user row was still created, pointing at the existing sub.
    patch_repos["account_user_repo"].create.assert_called_once()
    assert patch_repos["account_user_repo"].create.call_args.kwargs["user_id"] == UUID(
        FAKE_USER_SUB
    )

    # CRITICAL: no welcome-with-temp-password email to an existing user.
    patch_email.assert_not_called()

    assert result.email == EMAIL


# ─── path 3: already an active member of this account → no-op ───────────────


def test_create_account_user_already_member_is_idempotent(
    mocker: MockerFixture,
    patch_boto3: MagicMock,
    patch_email: MagicMock,
) -> None:
    account = MagicMock()
    account.id = FAKE_ACCOUNT_ID
    account.name = ACCOUNT_NAME
    mocker.patch.object(
        svc, "AccountRepository"
    ).return_value.get_account.return_value = account

    account_user_repo = mocker.patch.object(svc, "AccountUserRepository").return_value
    account_user_repo.get_by_email_and_account.return_value = MagicMock()  # exists

    session = MagicMock()
    result = svc.create_account_user(ACCOUNT_NAME, EMAIL, NAME, session)

    # No new row created.
    account_user_repo.create.assert_not_called()
    # No welcome email spam.
    patch_email.assert_not_called()
    assert result.email == EMAIL


# ─── unrelated Cognito errors still fail hard ───────────────────────────────


def test_create_account_user_unknown_cognito_error_raises(
    mocker: MockerFixture,
    patch_repos: dict[str, MagicMock],
    patch_email: MagicMock,
) -> None:
    client = _make_cognito_client(create_raises=_other_cognito_error())
    mocker.patch.object(svc.boto3, "client", return_value=client)

    session = MagicMock()
    with pytest.raises(ValueError, match="Failed to create Cognito user account"):
        svc.create_account_user(ACCOUNT_NAME, EMAIL, NAME, session)

    patch_repos["account_user_repo"].create.assert_not_called()
    patch_email.assert_not_called()


# ─── account not found → ValueError, no cognito side-effects on DB ──────────


def test_create_account_user_account_not_found_raises(
    mocker: MockerFixture,
    patch_boto3: MagicMock,
    patch_email: MagicMock,
) -> None:
    mocker.patch.object(
        svc, "AccountRepository"
    ).return_value.get_account.return_value = None
    account_user_repo = mocker.patch.object(svc, "AccountUserRepository").return_value

    session = MagicMock()
    with pytest.raises(ValueError, match="not found"):
        svc.create_account_user(ACCOUNT_NAME, EMAIL, NAME, session)

    account_user_repo.create.assert_not_called()
    patch_email.assert_not_called()


# ─── missing sub in Cognito response ────────────────────────────────────────


def test_create_account_user_missing_sub_raises(
    mocker: MockerFixture,
    patch_repos: dict[str, MagicMock],
    patch_email: MagicMock,
) -> None:
    client = MagicMock()
    client.admin_create_user.return_value = {}
    client.admin_get_user.return_value = {"UserAttributes": []}  # no sub
    mocker.patch.object(svc.boto3, "client", return_value=client)

    session = MagicMock()
    with pytest.raises(ValueError, match="sub not found"):
        svc.create_account_user(ACCOUNT_NAME, EMAIL, NAME, session)

    patch_repos["account_user_repo"].create.assert_not_called()
    patch_email.assert_not_called()
