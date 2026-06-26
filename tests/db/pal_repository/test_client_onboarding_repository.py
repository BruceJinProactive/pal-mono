from __future__ import annotations

import asyncio
import importlib
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError

from db.pal_repository.client_onboarding import (
    ClientOnboardingRepository,
    ClientOnboardingRepositoryAsync,
    client_onboarding_transition_changed,
    client_onboarding_transition_previous_status,
)
from db.tables import (
    ClientOnboardingActivity,
    ClientOnboardingActivitySource,
    ClientOnboardingActorType,
    ClientOnboardingContractType,
    ClientOnboardingLifecycle,
    ClientOnboardingStatus,
    ClientOnboardingSyncJob,
    ClientOnboardingSyncJobStatus,
    ClientOnboardingSyncTarget,
)

ACCOUNT_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
AE_USER_ID = UUID("11111111-2222-3333-4444-555555555555")
FDE_USER_ID = UUID("22222222-3333-4444-5555-666666666666")
LIFECYCLE_ID = UUID("bbbbbbbb-cccc-dddd-eeee-ffffffffffff")
INVITATION_ID = UUID("99999999-8888-7777-6666-555555555555")
OCCURRED_AT = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)
pytest: Any = importlib.import_module("pytest")


def _repository_with_query_result(
    result: ClientOnboardingLifecycle | None,
) -> tuple[ClientOnboardingRepository, MagicMock, MagicMock]:
    session = MagicMock()
    query = session.query.return_value
    query.filter.return_value.first.return_value = result
    return ClientOnboardingRepository(session), session, query


def _async_repository_with_execute_result(
    result: ClientOnboardingLifecycle | None,
) -> tuple[ClientOnboardingRepositoryAsync, MagicMock, MagicMock]:
    session = MagicMock()
    query_result = MagicMock()
    query_result.scalars.return_value.first.return_value = result
    session.execute = AsyncMock(return_value=query_result)
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.rollback = AsyncMock()
    session.get = AsyncMock()
    return ClientOnboardingRepositoryAsync(session), session, query_result


def _lifecycle_kwargs() -> dict[str, Any]:
    return {
        "idempotency_key": "onboarding-key",
        "account_id": ACCOUNT_ID,
        "manage_app_account_name": "acme",
        "order_form_id": "order-123",
        "client_company_name": "Acme Inc.",
        "signer_name": "Client Signer",
        "signer_email": " Signer@Example.COM ",
        "contract_type": ClientOnboardingContractType.order_form_tos,
        "docusign_contract_id": "contract-123",
        "docusign_envelope_id": "envelope-123",
        "docusign_contract_url": "https://docusign.example/contracts/123",
        "ae_owner_user_id": AE_USER_ID,
        "fde_owner_user_id": FDE_USER_ID,
        "folk_company_id": "folk-company",
        "folk_contact_id": "folk-contact",
        "scoping_doc_url": "https://notion.example/scoping",
        "occurred_at": OCCURRED_AT,
    }


def _lifecycle() -> ClientOnboardingLifecycle:
    return ClientOnboardingLifecycle(
        id=LIFECYCLE_ID,
        status=ClientOnboardingStatus.account_created,
    )


def test_get_by_idempotency_key_returns_first_matching_lifecycle() -> None:
    lifecycle = ClientOnboardingLifecycle(id=LIFECYCLE_ID)
    repo, session, query = _repository_with_query_result(lifecycle)

    result = repo.get_by_idempotency_key("onboarding-key")

    assert result is lifecycle
    session.query.assert_called_once_with(ClientOnboardingLifecycle)
    query.filter.assert_called_once()


def test_get_by_idempotency_key_rolls_back_on_sqlalchemy_error() -> None:
    session = MagicMock()
    session.query.side_effect = SQLAlchemyError("database unavailable")
    repo = ClientOnboardingRepository(session)

    with pytest.raises(SQLAlchemyError):
        repo.get_by_idempotency_key("onboarding-key")

    session.rollback.assert_called()


def test_get_active_for_account_signer_normalizes_signer_email() -> None:
    lifecycle = ClientOnboardingLifecycle(id=LIFECYCLE_ID)
    repo, session, query = _repository_with_query_result(lifecycle)

    result = repo.get_active_for_account_signer(ACCOUNT_ID, " Signer@Example.COM ")

    assert result is lifecycle
    session.query.assert_called_once_with(ClientOnboardingLifecycle)
    query.filter.assert_called_once()


def test_get_active_for_account_signer_rolls_back_on_sqlalchemy_error() -> None:
    session = MagicMock()
    session.query.side_effect = SQLAlchemyError("database unavailable")
    repo = ClientOnboardingRepository(session)

    with pytest.raises(SQLAlchemyError):
        repo.get_active_for_account_signer(ACCOUNT_ID, "signer@example.com")

    session.rollback.assert_called_once()


def test_get_active_by_docusign_reference_returns_none_without_reference() -> None:
    session = MagicMock()
    repo = ClientOnboardingRepository(session)

    result = repo.get_active_by_docusign_reference()

    assert result is None
    session.query.assert_not_called()


def test_get_active_by_docusign_reference_matches_any_supplied_reference() -> None:
    lifecycle = ClientOnboardingLifecycle(id=LIFECYCLE_ID)
    repo, session, query = _repository_with_query_result(lifecycle)

    result = repo.get_active_by_docusign_reference(
        docusign_contract_id="contract-123",
        docusign_envelope_id="envelope-123",
        docusign_contract_url="https://docusign.example/contracts/123",
    )

    assert result is lifecycle
    session.query.assert_called_once_with(ClientOnboardingLifecycle)
    query.filter.assert_called_once()


def test_get_active_by_docusign_reference_rolls_back_on_sqlalchemy_error() -> None:
    session = MagicMock()
    session.query.side_effect = SQLAlchemyError("database unavailable")
    repo = ClientOnboardingRepository(session)

    with pytest.raises(SQLAlchemyError):
        repo.get_active_by_docusign_reference(
            docusign_envelope_id="envelope-123",
        )

    session.rollback.assert_called_once()


def test_get_by_invite_id_returns_matching_lifecycle() -> None:
    lifecycle = ClientOnboardingLifecycle(id=LIFECYCLE_ID)
    repo, session, query = _repository_with_query_result(lifecycle)

    result = repo.get_by_invite_id(INVITATION_ID)

    assert result is lifecycle
    session.query.assert_called_once_with(ClientOnboardingLifecycle)
    query.filter.assert_called_once()


def test_get_by_invite_id_rolls_back_on_sqlalchemy_error() -> None:
    session = MagicMock()
    session.query.side_effect = SQLAlchemyError("database unavailable")
    repo = ClientOnboardingRepository(session)

    with pytest.raises(SQLAlchemyError):
        repo.get_by_invite_id(INVITATION_ID)

    session.rollback.assert_called_once()


def test_get_by_id_returns_matching_lifecycle() -> None:
    lifecycle = ClientOnboardingLifecycle(id=LIFECYCLE_ID)
    session = MagicMock()
    session.get.return_value = lifecycle
    repo = ClientOnboardingRepository(session)

    result = repo.get_by_id(LIFECYCLE_ID)

    assert result is lifecycle
    session.get.assert_called_once_with(ClientOnboardingLifecycle, LIFECYCLE_ID)


def test_get_by_id_rolls_back_on_sqlalchemy_error() -> None:
    session = MagicMock()
    session.get.side_effect = SQLAlchemyError("database unavailable")
    repo = ClientOnboardingRepository(session)

    with pytest.raises(SQLAlchemyError):
        repo.get_by_id(LIFECYCLE_ID)

    session.rollback.assert_called_once()


def test_create_lifecycle_persists_account_created_lifecycle() -> None:
    session = MagicMock()
    repo = ClientOnboardingRepository(session)

    lifecycle = repo.create_lifecycle(
        idempotency_key="onboarding-key",
        account_id=ACCOUNT_ID,
        manage_app_account_name="acme",
        order_form_id="order-123",
        client_company_name="Acme Inc.",
        signer_name="Client Signer",
        signer_email=" Signer@Example.COM ",
        contract_type=ClientOnboardingContractType.order_form_tos,
        docusign_contract_id="contract-123",
        docusign_envelope_id="envelope-123",
        docusign_contract_url="https://docusign.example/contracts/123",
        ae_owner_user_id=AE_USER_ID,
        fde_owner_user_id=FDE_USER_ID,
        folk_company_id="folk-company",
        folk_contact_id="folk-contact",
        scoping_doc_url="https://notion.example/scoping",
        occurred_at=OCCURRED_AT,
    )

    assert lifecycle.account_id == ACCOUNT_ID
    assert lifecycle.manage_app_account_name == "acme"
    assert lifecycle.signer_email == "signer@example.com"
    assert lifecycle.status == ClientOnboardingStatus.account_created
    assert lifecycle.contract_prepared_at == OCCURRED_AT
    assert lifecycle.account_created_at == OCCURRED_AT
    session.add.assert_called_once_with(lifecycle)
    session.flush.assert_called_once()
    session.refresh.assert_called_once_with(lifecycle)


def test_create_lifecycle_rolls_back_on_sqlalchemy_error() -> None:
    session = MagicMock()
    session.add.side_effect = SQLAlchemyError("database unavailable")
    repo = ClientOnboardingRepository(session)

    with pytest.raises(SQLAlchemyError):
        repo.create_lifecycle(**_lifecycle_kwargs())

    session.rollback.assert_called_once()


def test_mark_invite_sent_updates_existing_lifecycle() -> None:
    lifecycle = ClientOnboardingLifecycle(
        id=LIFECYCLE_ID,
        status=ClientOnboardingStatus.account_created,
    )
    session = MagicMock()
    session.execute.return_value.rowcount = 1
    session.get.return_value = lifecycle
    repo = ClientOnboardingRepository(session)

    result = repo.mark_invite_sent(
        LIFECYCLE_ID,
        invite_id=INVITATION_ID,
        occurred_at=OCCURRED_AT,
    )

    assert result is lifecycle
    assert lifecycle.invite_id == INVITATION_ID
    assert lifecycle.status == ClientOnboardingStatus.invite_sent
    assert lifecycle.invite_sent_at == OCCURRED_AT
    session.get.assert_called_once_with(ClientOnboardingLifecycle, LIFECYCLE_ID)
    session.flush.assert_called_once()
    session.refresh.assert_called_once_with(lifecycle)


def test_update_folk_ids_persists_ids() -> None:
    lifecycle = ClientOnboardingLifecycle(
        id=LIFECYCLE_ID,
        status=ClientOnboardingStatus.docusign_signed,
    )
    session = MagicMock()
    session.get.return_value = lifecycle
    repo = ClientOnboardingRepository(session)

    result = repo.update_folk_ids(
        LIFECYCLE_ID,
        folk_company_id="folk-company-created",
        folk_contact_id=None,
    )

    assert result is lifecycle
    assert lifecycle.folk_company_id == "folk-company-created"
    assert lifecycle.folk_contact_id is None
    assert lifecycle.updated_at is not None
    session.flush.assert_called_once()
    session.refresh.assert_called_once_with(lifecycle)


def test_mark_invite_opened_advances_from_invite_sent() -> None:
    lifecycle = ClientOnboardingLifecycle(
        id=LIFECYCLE_ID,
        status=ClientOnboardingStatus.invite_sent,
    )
    session = MagicMock()
    session.execute.return_value.rowcount = 1
    session.get.return_value = lifecycle
    repo = ClientOnboardingRepository(session)

    result = repo.mark_invite_opened(
        LIFECYCLE_ID,
        occurred_at=OCCURRED_AT,
    )

    assert result is lifecycle
    assert lifecycle.status == ClientOnboardingStatus.invite_opened
    assert lifecycle.invite_opened_at == OCCURRED_AT
    assert client_onboarding_transition_changed(result) is True
    assert (
        client_onboarding_transition_previous_status(result)
        == ClientOnboardingStatus.invite_sent
    )
    session.execute.assert_called_once()
    session.flush.assert_called_once()
    session.refresh.assert_called_once_with(lifecycle)


def test_mark_invite_opened_does_not_downgrade_later_status() -> None:
    lifecycle = ClientOnboardingLifecycle(
        id=LIFECYCLE_ID,
        status=ClientOnboardingStatus.docusign_signed,
    )
    session = MagicMock()
    session.execute.return_value.rowcount = 0
    session.get.return_value = lifecycle
    repo = ClientOnboardingRepository(session)

    result = repo.mark_invite_opened(
        LIFECYCLE_ID,
        occurred_at=OCCURRED_AT,
    )

    assert result is lifecycle
    assert lifecycle.status == ClientOnboardingStatus.docusign_signed
    assert lifecycle.invite_opened_at is None
    assert client_onboarding_transition_changed(result) is False


def test_mark_docusign_viewed_advances_after_visible_load() -> None:
    lifecycle = ClientOnboardingLifecycle(
        id=LIFECYCLE_ID,
        status=ClientOnboardingStatus.invite_opened,
    )
    session = MagicMock()
    session.execute.return_value.rowcount = 1
    session.get.return_value = lifecycle
    repo = ClientOnboardingRepository(session)

    result = repo.mark_docusign_viewed(
        LIFECYCLE_ID,
        occurred_at=OCCURRED_AT,
    )

    assert result is lifecycle
    assert lifecycle.status == ClientOnboardingStatus.docusign_viewed
    assert lifecycle.docusign_viewed_at == OCCURRED_AT
    assert client_onboarding_transition_changed(result) is True
    assert (
        client_onboarding_transition_previous_status(result)
        == ClientOnboardingStatus.invite_opened
    )
    session.flush.assert_called_once()
    session.refresh.assert_called_once_with(lifecycle)


def test_mark_docusign_viewed_backfills_invite_opened_from_invite_sent() -> None:
    lifecycle = ClientOnboardingLifecycle(
        id=LIFECYCLE_ID,
        status=ClientOnboardingStatus.invite_sent,
    )
    first_update = MagicMock()
    first_update.rowcount = 0
    second_update = MagicMock()
    second_update.rowcount = 1
    session = MagicMock()
    session.execute.side_effect = [first_update, second_update]
    session.get.return_value = lifecycle
    repo = ClientOnboardingRepository(session)

    result = repo.mark_docusign_viewed(
        LIFECYCLE_ID,
        occurred_at=OCCURRED_AT,
    )

    assert result is lifecycle
    assert lifecycle.status == ClientOnboardingStatus.docusign_viewed
    assert lifecycle.docusign_viewed_at == OCCURRED_AT
    assert lifecycle.invite_opened_at == OCCURRED_AT
    assert client_onboarding_transition_changed(result) is True
    assert (
        client_onboarding_transition_previous_status(result)
        == ClientOnboardingStatus.invite_sent
    )
    assert session.execute.call_count == 2
    session.flush.assert_called_once()
    session.refresh.assert_called_once_with(lifecycle)


def test_mark_docusign_signed_advances_from_docusign_viewed() -> None:
    lifecycle = ClientOnboardingLifecycle(
        id=LIFECYCLE_ID,
        status=ClientOnboardingStatus.docusign_viewed,
    )
    session = MagicMock()
    session.execute.return_value.rowcount = 1
    session.get.return_value = lifecycle
    repo = ClientOnboardingRepository(session)

    result = repo.mark_docusign_signed(
        LIFECYCLE_ID,
        occurred_at=OCCURRED_AT,
    )

    assert result is lifecycle
    assert lifecycle.status == ClientOnboardingStatus.docusign_signed
    assert lifecycle.docusign_signed_at == OCCURRED_AT
    assert client_onboarding_transition_changed(result) is True
    assert (
        client_onboarding_transition_previous_status(result)
        == ClientOnboardingStatus.docusign_viewed
    )
    session.execute.assert_called_once()
    session.flush.assert_called_once()
    session.refresh.assert_called_once_with(lifecycle)


def test_mark_docusign_signed_backfills_from_invite_sent() -> None:
    lifecycle = ClientOnboardingLifecycle(
        id=LIFECYCLE_ID,
        status=ClientOnboardingStatus.invite_sent,
    )
    first_update = MagicMock()
    first_update.rowcount = 0
    second_update = MagicMock()
    second_update.rowcount = 0
    third_update = MagicMock()
    third_update.rowcount = 1
    session = MagicMock()
    session.execute.side_effect = [first_update, second_update, third_update]
    session.get.return_value = lifecycle
    repo = ClientOnboardingRepository(session)

    result = repo.mark_docusign_signed(
        LIFECYCLE_ID,
        occurred_at=OCCURRED_AT,
    )

    assert result is lifecycle
    assert lifecycle.status == ClientOnboardingStatus.docusign_signed
    assert lifecycle.docusign_signed_at == OCCURRED_AT
    assert lifecycle.docusign_viewed_at == OCCURRED_AT
    assert lifecycle.invite_opened_at == OCCURRED_AT
    assert client_onboarding_transition_changed(result) is True
    assert (
        client_onboarding_transition_previous_status(result)
        == ClientOnboardingStatus.invite_sent
    )
    assert session.execute.call_count == 3
    session.flush.assert_called_once()
    session.refresh.assert_called_once_with(lifecycle)


def test_mark_docusign_signed_can_skip_client_timestamp_backfill() -> None:
    lifecycle = ClientOnboardingLifecycle(
        id=LIFECYCLE_ID,
        status=ClientOnboardingStatus.invite_sent,
    )
    first_update = MagicMock()
    first_update.rowcount = 0
    second_update = MagicMock()
    second_update.rowcount = 0
    third_update = MagicMock()
    third_update.rowcount = 1
    session = MagicMock()
    session.execute.side_effect = [first_update, second_update, third_update]
    session.get.return_value = lifecycle
    repo = ClientOnboardingRepository(session)

    result = repo.mark_docusign_signed(
        LIFECYCLE_ID,
        occurred_at=OCCURRED_AT,
        backfill_client_timestamps=False,
    )

    assert result is lifecycle
    assert lifecycle.status == ClientOnboardingStatus.docusign_signed
    assert lifecycle.docusign_signed_at == OCCURRED_AT
    assert lifecycle.docusign_viewed_at is None
    assert lifecycle.invite_opened_at is None
    assert client_onboarding_transition_changed(result) is True
    assert (
        client_onboarding_transition_previous_status(result)
        == ClientOnboardingStatus.invite_sent
    )
    assert session.execute.call_count == 3
    session.flush.assert_called_once()
    session.refresh.assert_called_once_with(lifecycle)


def test_mark_docusign_signed_does_not_downgrade_post_signature_status() -> None:
    lifecycle = ClientOnboardingLifecycle(
        id=LIFECYCLE_ID,
        status=ClientOnboardingStatus.password_set,
    )
    session = MagicMock()
    session.execute.return_value.rowcount = 0
    session.get.return_value = lifecycle
    repo = ClientOnboardingRepository(session)

    result = repo.mark_docusign_signed(
        LIFECYCLE_ID,
        occurred_at=OCCURRED_AT,
    )

    assert result is lifecycle
    assert lifecycle.status == ClientOnboardingStatus.password_set
    assert lifecycle.docusign_signed_at is None
    assert client_onboarding_transition_changed(result) is False
    assert session.execute.call_count == 3


def test_mark_password_set_advances_from_docusign_signed() -> None:
    lifecycle = ClientOnboardingLifecycle(
        id=LIFECYCLE_ID,
        status=ClientOnboardingStatus.docusign_signed,
    )
    session = MagicMock()
    session.execute.return_value.rowcount = 1
    session.get.return_value = lifecycle
    repo = ClientOnboardingRepository(session)

    result = repo.mark_password_set(
        LIFECYCLE_ID,
        occurred_at=OCCURRED_AT,
    )

    assert result is lifecycle
    assert lifecycle.status == ClientOnboardingStatus.password_set
    assert lifecycle.password_set_at == OCCURRED_AT
    assert client_onboarding_transition_changed(result) is True
    assert (
        client_onboarding_transition_previous_status(result)
        == ClientOnboardingStatus.docusign_signed
    )
    session.execute.assert_called_once()
    session.flush.assert_called_once()
    session.refresh.assert_called_once_with(lifecycle)


def test_mark_password_set_does_not_advance_before_signature() -> None:
    lifecycle = ClientOnboardingLifecycle(
        id=LIFECYCLE_ID,
        status=ClientOnboardingStatus.docusign_viewed,
    )
    session = MagicMock()
    session.execute.return_value.rowcount = 0
    session.get.return_value = lifecycle
    repo = ClientOnboardingRepository(session)

    result = repo.mark_password_set(
        LIFECYCLE_ID,
        occurred_at=OCCURRED_AT,
    )

    assert result is lifecycle
    assert lifecycle.status == ClientOnboardingStatus.docusign_viewed
    assert lifecycle.password_set_at is None
    assert client_onboarding_transition_changed(result) is False


def test_mark_password_set_records_timestamp_after_handoff_created() -> None:
    lifecycle = ClientOnboardingLifecycle(
        id=LIFECYCLE_ID,
        status=ClientOnboardingStatus.handoff_created,
    )
    session = MagicMock()
    session.execute.side_effect = [
        MagicMock(rowcount=0),
        MagicMock(rowcount=1),
    ]
    session.get.return_value = lifecycle
    repo = ClientOnboardingRepository(session)

    result = repo.mark_password_set(
        LIFECYCLE_ID,
        occurred_at=OCCURRED_AT,
    )

    assert result is lifecycle
    assert lifecycle.status == ClientOnboardingStatus.handoff_created
    assert lifecycle.password_set_at == OCCURRED_AT
    assert client_onboarding_transition_changed(result) is True
    assert (
        client_onboarding_transition_previous_status(result)
        == ClientOnboardingStatus.handoff_created
    )
    assert session.execute.call_count == 2


def test_mark_handoff_created_advances_from_password_set() -> None:
    lifecycle = ClientOnboardingLifecycle(
        id=LIFECYCLE_ID,
        status=ClientOnboardingStatus.password_set,
        password_set_at=OCCURRED_AT,
    )
    session = MagicMock()
    session.execute.return_value.rowcount = 1
    session.get.return_value = lifecycle
    repo = ClientOnboardingRepository(session)

    result = repo.mark_handoff_created(
        LIFECYCLE_ID,
        occurred_at=OCCURRED_AT,
    )

    assert result is lifecycle
    assert lifecycle.status == ClientOnboardingStatus.handoff_created
    assert lifecycle.handoff_created_at == OCCURRED_AT
    assert client_onboarding_transition_changed(result) is True
    assert (
        client_onboarding_transition_previous_status(result)
        == ClientOnboardingStatus.password_set
    )


def test_mark_activation_ready_requires_handoff_and_password() -> None:
    lifecycle = ClientOnboardingLifecycle(
        id=LIFECYCLE_ID,
        status=ClientOnboardingStatus.handoff_created,
        password_set_at=OCCURRED_AT,
    )
    session = MagicMock()
    session.execute.return_value.rowcount = 1
    session.get.return_value = lifecycle
    repo = ClientOnboardingRepository(session)

    result = repo.mark_activation_ready(
        LIFECYCLE_ID,
        occurred_at=OCCURRED_AT,
    )

    assert result is lifecycle
    assert lifecycle.status == ClientOnboardingStatus.activation_ready
    assert lifecycle.activation_ready_at == OCCURRED_AT
    assert client_onboarding_transition_changed(result) is True
    assert (
        client_onboarding_transition_previous_status(result)
        == ClientOnboardingStatus.handoff_created
    )


def test_mark_handoff_created_noops_for_later_status() -> None:
    lifecycle = ClientOnboardingLifecycle(
        id=LIFECYCLE_ID,
        status=ClientOnboardingStatus.activation_ready,
    )
    session = MagicMock()
    session.execute.return_value.rowcount = 0
    session.get.return_value = lifecycle
    repo = ClientOnboardingRepository(session)

    result = repo.mark_handoff_created(
        LIFECYCLE_ID,
        occurred_at=OCCURRED_AT,
    )

    assert result is lifecycle
    assert lifecycle.status == ClientOnboardingStatus.activation_ready
    assert client_onboarding_transition_changed(result) is False
    assert client_onboarding_transition_previous_status(result) is None


def test_mark_password_set_rolls_back_on_sqlalchemy_error() -> None:
    session = MagicMock()
    session.execute.side_effect = SQLAlchemyError("database unavailable")
    repo = ClientOnboardingRepository(session)

    with pytest.raises(SQLAlchemyError):
        repo.mark_password_set(
            LIFECYCLE_ID,
            occurred_at=OCCURRED_AT,
        )

    session.rollback.assert_called_once()


def test_mark_handoff_created_rolls_back_on_sqlalchemy_error() -> None:
    session = MagicMock()
    session.execute.side_effect = SQLAlchemyError("database unavailable")
    repo = ClientOnboardingRepository(session)

    with pytest.raises(SQLAlchemyError):
        repo.mark_handoff_created(
            LIFECYCLE_ID,
            occurred_at=OCCURRED_AT,
        )

    session.rollback.assert_called_once()


def test_mark_activation_ready_rolls_back_on_sqlalchemy_error() -> None:
    session = MagicMock()
    session.execute.side_effect = SQLAlchemyError("database unavailable")
    repo = ClientOnboardingRepository(session)

    with pytest.raises(SQLAlchemyError):
        repo.mark_activation_ready(
            LIFECYCLE_ID,
            occurred_at=OCCURRED_AT,
        )

    session.rollback.assert_called_once()


def test_mark_blocked_updates_status_reason() -> None:
    lifecycle = ClientOnboardingLifecycle(
        id=LIFECYCLE_ID,
        status=ClientOnboardingStatus.account_created,
    )
    session = MagicMock()
    session.get.return_value = lifecycle
    repo = ClientOnboardingRepository(session)

    result = repo.mark_blocked(
        LIFECYCLE_ID,
        status_reason="Signer invite failed",
    )

    assert result is lifecycle
    assert lifecycle.status == ClientOnboardingStatus.blocked
    assert lifecycle.status_reason == "Signer invite failed"
    session.flush.assert_called_once()
    session.refresh.assert_called_once_with(lifecycle)


def test_mark_blocked_rolls_back_on_sqlalchemy_error() -> None:
    session = MagicMock()
    session.get.return_value = _lifecycle()
    session.flush.side_effect = SQLAlchemyError("database unavailable")
    repo = ClientOnboardingRepository(session)

    with pytest.raises(SQLAlchemyError):
        repo.mark_blocked(
            LIFECYCLE_ID,
            status_reason="Signer invite failed",
        )

    session.rollback.assert_called_once()


def test_set_slack_channel_id_updates_existing_lifecycle() -> None:
    lifecycle = ClientOnboardingLifecycle(
        id=LIFECYCLE_ID,
        status=ClientOnboardingStatus.docusign_signed,
    )
    session = MagicMock()
    session.get.return_value = lifecycle
    repo = ClientOnboardingRepository(session)

    result = repo.set_slack_channel_id(
        LIFECYCLE_ID,
        slack_channel_id="C123",
        occurred_at=OCCURRED_AT,
    )

    assert result is lifecycle
    assert lifecycle.slack_channel_id == "C123"
    assert lifecycle.updated_at == OCCURRED_AT
    session.flush.assert_called_once()
    session.refresh.assert_called_once_with(lifecycle)


def test_set_slack_channel_id_rolls_back_on_sqlalchemy_error() -> None:
    session = MagicMock()
    session.get.return_value = _lifecycle()
    session.flush.side_effect = SQLAlchemyError("database unavailable")
    repo = ClientOnboardingRepository(session)

    with pytest.raises(SQLAlchemyError):
        repo.set_slack_channel_id(LIFECYCLE_ID, slack_channel_id="C123")

    session.rollback.assert_called_once()


def test_set_notion_page_id_updates_existing_lifecycle() -> None:
    lifecycle = ClientOnboardingLifecycle(
        id=LIFECYCLE_ID,
        status=ClientOnboardingStatus.docusign_signed,
    )
    session = MagicMock()
    session.get.return_value = lifecycle
    repo = ClientOnboardingRepository(session)

    result = repo.set_notion_page_id(
        LIFECYCLE_ID,
        notion_page_id="notion-page-123",
        occurred_at=OCCURRED_AT,
    )

    assert result is lifecycle
    assert lifecycle.notion_page_id == "notion-page-123"
    assert lifecycle.updated_at == OCCURRED_AT
    session.flush.assert_called_once()
    session.refresh.assert_called_once_with(lifecycle)


def test_set_notion_page_id_rolls_back_on_sqlalchemy_error() -> None:
    session = MagicMock()
    session.get.return_value = _lifecycle()
    session.flush.side_effect = SQLAlchemyError("database unavailable")
    repo = ClientOnboardingRepository(session)

    with pytest.raises(SQLAlchemyError):
        repo.set_notion_page_id(LIFECYCLE_ID, notion_page_id="notion-page-123")

    session.rollback.assert_called_once()


def test_append_activity_defaults_payloads_and_persists_activity() -> None:
    session = MagicMock()
    repo = ClientOnboardingRepository(session)

    activity = repo.append_activity(
        lifecycle_id=LIFECYCLE_ID,
        activity_type="invite_sent",
        actor_type=ClientOnboardingActorType.ae,
        source=ClientOnboardingActivitySource.manage_app,
        previous_status=ClientOnboardingStatus.account_created,
        next_status=ClientOnboardingStatus.invite_sent,
        actor_id=AE_USER_ID,
        actor_display_name="AE User",
        description="Invite sent",
        occurred_at=OCCURRED_AT,
    )

    assert isinstance(activity, ClientOnboardingActivity)
    assert activity.lifecycle_id == LIFECYCLE_ID
    assert activity.activity_type == "invite_sent"
    assert activity.payload_diff == {}
    assert activity.activity_metadata == {}
    assert activity.occurred_at == OCCURRED_AT
    session.add.assert_called_once_with(activity)
    session.flush.assert_called_once()
    session.refresh.assert_called_once_with(activity)


def test_append_activity_rolls_back_on_sqlalchemy_error() -> None:
    session = MagicMock()
    session.add.side_effect = SQLAlchemyError("database unavailable")
    repo = ClientOnboardingRepository(session)

    with pytest.raises(SQLAlchemyError):
        repo.append_activity(
            lifecycle_id=LIFECYCLE_ID,
            activity_type="invite_sent",
            actor_type=ClientOnboardingActorType.ae,
            source=ClientOnboardingActivitySource.manage_app,
        )

    session.rollback.assert_called_once()


def test_status_updates_raise_when_lifecycle_is_missing() -> None:
    session = MagicMock()
    session.get.return_value = None
    repo = ClientOnboardingRepository(session)

    with pytest.raises(ValueError, match=str(LIFECYCLE_ID)):
        repo.mark_invite_sent(LIFECYCLE_ID, invite_id=INVITATION_ID)


def test_status_updates_roll_back_on_lifecycle_lookup_error() -> None:
    session = MagicMock()
    session.get.side_effect = SQLAlchemyError("database unavailable")
    repo = ClientOnboardingRepository(session)

    with pytest.raises(SQLAlchemyError):
        repo.mark_invite_sent(LIFECYCLE_ID, invite_id=INVITATION_ID)

    session.rollback.assert_called()


def test_async_get_by_idempotency_key_returns_first_matching_lifecycle() -> None:
    lifecycle = ClientOnboardingLifecycle(id=LIFECYCLE_ID)
    repo, session, query_result = _async_repository_with_execute_result(lifecycle)

    result = asyncio.run(repo.get_by_idempotency_key("onboarding-key"))

    assert result is lifecycle
    session.execute.assert_awaited_once()
    query_result.scalars.return_value.first.assert_called_once()


def test_async_get_active_for_account_signer_normalizes_signer_email() -> None:
    lifecycle = ClientOnboardingLifecycle(id=LIFECYCLE_ID)
    repo, session, query_result = _async_repository_with_execute_result(lifecycle)

    result = asyncio.run(
        repo.get_active_for_account_signer(ACCOUNT_ID, " Signer@Example.COM ")
    )

    assert result is lifecycle
    session.execute.assert_awaited_once()
    query_result.scalars.return_value.first.assert_called_once()


def test_async_get_active_for_account_signer_rolls_back_on_sqlalchemy_error() -> None:
    session = MagicMock()
    session.execute = AsyncMock(side_effect=SQLAlchemyError("database unavailable"))
    session.rollback = AsyncMock()
    repo = ClientOnboardingRepositoryAsync(session)

    with pytest.raises(SQLAlchemyError):
        asyncio.run(
            repo.get_active_for_account_signer(ACCOUNT_ID, "signer@example.com")
        )

    session.rollback.assert_awaited_once()


def test_async_get_active_by_docusign_reference_returns_none_without_reference() -> (
    None
):
    session = MagicMock()
    session.execute = AsyncMock()
    repo = ClientOnboardingRepositoryAsync(session)

    result = asyncio.run(repo.get_active_by_docusign_reference())

    assert result is None
    session.execute.assert_not_called()


def test_async_get_active_by_docusign_reference_matches_any_supplied_reference() -> (
    None
):
    lifecycle = ClientOnboardingLifecycle(id=LIFECYCLE_ID)
    repo, session, query_result = _async_repository_with_execute_result(lifecycle)

    result = asyncio.run(
        repo.get_active_by_docusign_reference(
            docusign_contract_id="contract-123",
            docusign_envelope_id="envelope-123",
            docusign_contract_url="https://docusign.example/contracts/123",
        )
    )

    assert result is lifecycle
    session.execute.assert_awaited_once()
    query_result.scalars.return_value.first.assert_called_once()


def test_async_get_active_by_docusign_reference_rolls_back_on_sqlalchemy_error() -> (
    None
):
    session = MagicMock()
    session.execute = AsyncMock(side_effect=SQLAlchemyError("database unavailable"))
    session.rollback = AsyncMock()
    repo = ClientOnboardingRepositoryAsync(session)

    with pytest.raises(SQLAlchemyError):
        asyncio.run(
            repo.get_active_by_docusign_reference(
                docusign_envelope_id="envelope-123",
            )
        )

    session.rollback.assert_awaited_once()


def test_async_get_by_invite_id_returns_matching_lifecycle() -> None:
    lifecycle = ClientOnboardingLifecycle(id=LIFECYCLE_ID)
    repo, session, query_result = _async_repository_with_execute_result(lifecycle)

    result = asyncio.run(repo.get_by_invite_id(INVITATION_ID))

    assert result is lifecycle
    session.execute.assert_awaited_once()
    query_result.scalars.return_value.first.assert_called_once()


def test_async_get_by_invite_id_rolls_back_on_sqlalchemy_error() -> None:
    session = MagicMock()
    session.execute = AsyncMock(side_effect=SQLAlchemyError("database unavailable"))
    session.rollback = AsyncMock()
    repo = ClientOnboardingRepositoryAsync(session)

    with pytest.raises(SQLAlchemyError):
        asyncio.run(repo.get_by_invite_id(INVITATION_ID))

    session.rollback.assert_awaited_once()


def test_async_get_by_idempotency_key_rolls_back_on_sqlalchemy_error() -> None:
    session = MagicMock()
    session.execute = AsyncMock(side_effect=SQLAlchemyError("database unavailable"))
    session.rollback = AsyncMock()
    repo = ClientOnboardingRepositoryAsync(session)

    with pytest.raises(SQLAlchemyError):
        asyncio.run(repo.get_by_idempotency_key("onboarding-key"))

    session.rollback.assert_awaited_once()


def test_async_create_lifecycle_persists_account_created_lifecycle() -> None:
    session = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    repo = ClientOnboardingRepositoryAsync(session)

    lifecycle = asyncio.run(
        repo.create_lifecycle(
            idempotency_key="onboarding-key",
            account_id=ACCOUNT_ID,
            manage_app_account_name="acme",
            order_form_id="order-123",
            client_company_name="Acme Inc.",
            signer_name="Client Signer",
            signer_email=" Signer@Example.COM ",
            contract_type=ClientOnboardingContractType.order_form_tos,
            docusign_contract_id="contract-123",
            docusign_envelope_id="envelope-123",
            docusign_contract_url="https://docusign.example/contracts/123",
            ae_owner_user_id=AE_USER_ID,
            fde_owner_user_id=FDE_USER_ID,
            folk_company_id="folk-company",
            folk_contact_id="folk-contact",
            scoping_doc_url="https://notion.example/scoping",
            occurred_at=OCCURRED_AT,
        )
    )

    assert lifecycle.account_id == ACCOUNT_ID
    assert lifecycle.signer_email == "signer@example.com"
    assert lifecycle.status == ClientOnboardingStatus.account_created
    assert lifecycle.contract_prepared_at == OCCURRED_AT
    session.add.assert_called_once_with(lifecycle)
    session.flush.assert_awaited_once()
    session.refresh.assert_awaited_once_with(lifecycle)


def test_async_create_lifecycle_rolls_back_on_sqlalchemy_error() -> None:
    session = MagicMock()
    session.flush = AsyncMock(side_effect=SQLAlchemyError("database unavailable"))
    session.rollback = AsyncMock()
    repo = ClientOnboardingRepositoryAsync(session)

    with pytest.raises(SQLAlchemyError):
        asyncio.run(repo.create_lifecycle(**_lifecycle_kwargs()))

    session.rollback.assert_awaited_once()


def test_async_mark_invite_sent_updates_existing_lifecycle() -> None:
    lifecycle = ClientOnboardingLifecycle(
        id=LIFECYCLE_ID,
        status=ClientOnboardingStatus.account_created,
    )
    session = MagicMock()
    session.get = AsyncMock(return_value=lifecycle)
    execute_result = MagicMock()
    execute_result.rowcount = 1
    session.execute = AsyncMock(return_value=execute_result)
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    repo = ClientOnboardingRepositoryAsync(session)

    result = asyncio.run(
        repo.mark_invite_sent(
            LIFECYCLE_ID,
            invite_id=INVITATION_ID,
            occurred_at=OCCURRED_AT,
        )
    )

    assert result is lifecycle
    assert lifecycle.invite_id == INVITATION_ID
    assert lifecycle.status == ClientOnboardingStatus.invite_sent
    assert lifecycle.invite_sent_at == OCCURRED_AT
    session.get.assert_awaited_once_with(ClientOnboardingLifecycle, LIFECYCLE_ID)
    session.flush.assert_awaited_once()
    session.refresh.assert_awaited_once_with(lifecycle)


def test_async_mark_invite_sent_rolls_back_on_sqlalchemy_error() -> None:
    session = MagicMock()
    session.get = AsyncMock(return_value=_lifecycle())
    session.flush = AsyncMock(side_effect=SQLAlchemyError("database unavailable"))
    session.rollback = AsyncMock()
    repo = ClientOnboardingRepositoryAsync(session)

    with pytest.raises(SQLAlchemyError):
        asyncio.run(
            repo.mark_invite_sent(
                LIFECYCLE_ID,
                invite_id=INVITATION_ID,
            )
        )

    session.rollback.assert_awaited_once()


def test_async_mark_invite_opened_advances_from_invite_sent() -> None:
    lifecycle = ClientOnboardingLifecycle(
        id=LIFECYCLE_ID,
        status=ClientOnboardingStatus.invite_sent,
    )
    session = MagicMock()
    session.get = AsyncMock(return_value=lifecycle)
    execute_result = MagicMock()
    execute_result.rowcount = 1
    session.execute = AsyncMock(return_value=execute_result)
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    repo = ClientOnboardingRepositoryAsync(session)

    result = asyncio.run(
        repo.mark_invite_opened(
            LIFECYCLE_ID,
            occurred_at=OCCURRED_AT,
        )
    )

    assert result is lifecycle
    assert lifecycle.status == ClientOnboardingStatus.invite_opened
    assert lifecycle.invite_opened_at == OCCURRED_AT
    assert client_onboarding_transition_changed(result) is True
    assert (
        client_onboarding_transition_previous_status(result)
        == ClientOnboardingStatus.invite_sent
    )
    session.execute.assert_awaited_once()
    session.flush.assert_awaited_once()
    session.refresh.assert_awaited_once_with(lifecycle)


def test_async_mark_docusign_viewed_advances_after_visible_load() -> None:
    lifecycle = ClientOnboardingLifecycle(
        id=LIFECYCLE_ID,
        status=ClientOnboardingStatus.invite_opened,
    )
    session = MagicMock()
    session.get = AsyncMock(return_value=lifecycle)
    execute_result = MagicMock()
    execute_result.rowcount = 1
    session.execute = AsyncMock(return_value=execute_result)
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    repo = ClientOnboardingRepositoryAsync(session)

    result = asyncio.run(
        repo.mark_docusign_viewed(
            LIFECYCLE_ID,
            occurred_at=OCCURRED_AT,
        )
    )

    assert result is lifecycle
    assert lifecycle.status == ClientOnboardingStatus.docusign_viewed
    assert lifecycle.docusign_viewed_at == OCCURRED_AT
    assert client_onboarding_transition_changed(result) is True
    assert (
        client_onboarding_transition_previous_status(result)
        == ClientOnboardingStatus.invite_opened
    )
    session.flush.assert_awaited_once()
    session.refresh.assert_awaited_once_with(lifecycle)


def test_async_mark_docusign_viewed_backfills_invite_opened_from_invite_sent() -> None:
    lifecycle = ClientOnboardingLifecycle(
        id=LIFECYCLE_ID,
        status=ClientOnboardingStatus.invite_sent,
    )
    first_update = MagicMock()
    first_update.rowcount = 0
    second_update = MagicMock()
    second_update.rowcount = 1
    session = MagicMock()
    session.get = AsyncMock(return_value=lifecycle)
    session.execute = AsyncMock(side_effect=[first_update, second_update])
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    repo = ClientOnboardingRepositoryAsync(session)

    result = asyncio.run(
        repo.mark_docusign_viewed(
            LIFECYCLE_ID,
            occurred_at=OCCURRED_AT,
        )
    )

    assert result is lifecycle
    assert lifecycle.status == ClientOnboardingStatus.docusign_viewed
    assert lifecycle.docusign_viewed_at == OCCURRED_AT
    assert lifecycle.invite_opened_at == OCCURRED_AT
    assert client_onboarding_transition_changed(result) is True
    assert (
        client_onboarding_transition_previous_status(result)
        == ClientOnboardingStatus.invite_sent
    )
    assert session.execute.await_count == 2
    session.flush.assert_awaited_once()
    session.refresh.assert_awaited_once_with(lifecycle)


def test_async_mark_docusign_signed_advances_from_docusign_viewed() -> None:
    lifecycle = ClientOnboardingLifecycle(
        id=LIFECYCLE_ID,
        status=ClientOnboardingStatus.docusign_viewed,
    )
    session = MagicMock()
    session.get = AsyncMock(return_value=lifecycle)
    execute_result = MagicMock()
    execute_result.rowcount = 1
    session.execute = AsyncMock(return_value=execute_result)
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    repo = ClientOnboardingRepositoryAsync(session)

    result = asyncio.run(
        repo.mark_docusign_signed(
            LIFECYCLE_ID,
            occurred_at=OCCURRED_AT,
        )
    )

    assert result is lifecycle
    assert lifecycle.status == ClientOnboardingStatus.docusign_signed
    assert lifecycle.docusign_signed_at == OCCURRED_AT
    assert client_onboarding_transition_changed(result) is True
    assert (
        client_onboarding_transition_previous_status(result)
        == ClientOnboardingStatus.docusign_viewed
    )
    session.execute.assert_awaited_once()
    session.flush.assert_awaited_once()
    session.refresh.assert_awaited_once_with(lifecycle)


def test_async_mark_docusign_signed_backfills_from_invite_sent() -> None:
    lifecycle = ClientOnboardingLifecycle(
        id=LIFECYCLE_ID,
        status=ClientOnboardingStatus.invite_sent,
    )
    first_update = MagicMock()
    first_update.rowcount = 0
    second_update = MagicMock()
    second_update.rowcount = 0
    third_update = MagicMock()
    third_update.rowcount = 1
    session = MagicMock()
    session.get = AsyncMock(return_value=lifecycle)
    session.execute = AsyncMock(side_effect=[first_update, second_update, third_update])
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    repo = ClientOnboardingRepositoryAsync(session)

    result = asyncio.run(
        repo.mark_docusign_signed(
            LIFECYCLE_ID,
            occurred_at=OCCURRED_AT,
        )
    )

    assert result is lifecycle
    assert lifecycle.status == ClientOnboardingStatus.docusign_signed
    assert lifecycle.docusign_signed_at == OCCURRED_AT
    assert lifecycle.docusign_viewed_at == OCCURRED_AT
    assert lifecycle.invite_opened_at == OCCURRED_AT
    assert client_onboarding_transition_changed(result) is True
    assert (
        client_onboarding_transition_previous_status(result)
        == ClientOnboardingStatus.invite_sent
    )
    assert session.execute.await_count == 3
    session.flush.assert_awaited_once()
    session.refresh.assert_awaited_once_with(lifecycle)


def test_async_mark_docusign_signed_does_not_downgrade_post_signature_status() -> None:
    lifecycle = ClientOnboardingLifecycle(
        id=LIFECYCLE_ID,
        status=ClientOnboardingStatus.password_set,
    )
    execute_result = MagicMock()
    execute_result.rowcount = 0
    session = MagicMock()
    session.get = AsyncMock(return_value=lifecycle)
    session.execute = AsyncMock(return_value=execute_result)
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    repo = ClientOnboardingRepositoryAsync(session)

    result = asyncio.run(
        repo.mark_docusign_signed(
            LIFECYCLE_ID,
            occurred_at=OCCURRED_AT,
        )
    )

    assert result is lifecycle
    assert lifecycle.status == ClientOnboardingStatus.password_set
    assert lifecycle.docusign_signed_at is None
    assert client_onboarding_transition_changed(result) is False
    assert session.execute.await_count == 3


def test_async_mark_password_set_advances_from_docusign_signed() -> None:
    lifecycle = ClientOnboardingLifecycle(
        id=LIFECYCLE_ID,
        status=ClientOnboardingStatus.docusign_signed,
    )
    session = MagicMock()
    session.get = AsyncMock(return_value=lifecycle)
    execute_result = MagicMock()
    execute_result.rowcount = 1
    session.execute = AsyncMock(return_value=execute_result)
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    repo = ClientOnboardingRepositoryAsync(session)

    result = asyncio.run(
        repo.mark_password_set(
            LIFECYCLE_ID,
            occurred_at=OCCURRED_AT,
        )
    )

    assert result is lifecycle
    assert lifecycle.status == ClientOnboardingStatus.password_set
    assert lifecycle.password_set_at == OCCURRED_AT
    assert client_onboarding_transition_changed(result) is True
    assert (
        client_onboarding_transition_previous_status(result)
        == ClientOnboardingStatus.docusign_signed
    )
    session.execute.assert_awaited_once()
    session.flush.assert_awaited_once()
    session.refresh.assert_awaited_once_with(lifecycle)


def test_async_mark_password_set_does_not_advance_before_signature() -> None:
    lifecycle = ClientOnboardingLifecycle(
        id=LIFECYCLE_ID,
        status=ClientOnboardingStatus.docusign_viewed,
    )
    execute_result = MagicMock()
    execute_result.rowcount = 0
    session = MagicMock()
    session.get = AsyncMock(return_value=lifecycle)
    session.execute = AsyncMock(return_value=execute_result)
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    repo = ClientOnboardingRepositoryAsync(session)

    result = asyncio.run(
        repo.mark_password_set(
            LIFECYCLE_ID,
            occurred_at=OCCURRED_AT,
        )
    )

    assert result is lifecycle
    assert lifecycle.status == ClientOnboardingStatus.docusign_viewed
    assert lifecycle.password_set_at is None
    assert client_onboarding_transition_changed(result) is False


def test_async_mark_password_set_records_timestamp_after_handoff_created() -> None:
    lifecycle = ClientOnboardingLifecycle(
        id=LIFECYCLE_ID,
        status=ClientOnboardingStatus.handoff_created,
    )
    session = MagicMock()
    session.get = AsyncMock(return_value=lifecycle)
    session.execute = AsyncMock(
        side_effect=[
            MagicMock(rowcount=0),
            MagicMock(rowcount=1),
        ]
    )
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    repo = ClientOnboardingRepositoryAsync(session)

    result = asyncio.run(
        repo.mark_password_set(
            LIFECYCLE_ID,
            occurred_at=OCCURRED_AT,
        )
    )

    assert result is lifecycle
    assert lifecycle.status == ClientOnboardingStatus.handoff_created
    assert lifecycle.password_set_at == OCCURRED_AT
    assert client_onboarding_transition_changed(result) is True
    assert (
        client_onboarding_transition_previous_status(result)
        == ClientOnboardingStatus.handoff_created
    )
    assert session.execute.await_count == 2


def test_async_mark_handoff_created_advances_from_password_set() -> None:
    lifecycle = ClientOnboardingLifecycle(
        id=LIFECYCLE_ID,
        status=ClientOnboardingStatus.password_set,
        password_set_at=OCCURRED_AT,
    )
    session = MagicMock()
    session.get = AsyncMock(return_value=lifecycle)
    session.execute = AsyncMock(return_value=MagicMock(rowcount=1))
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    repo = ClientOnboardingRepositoryAsync(session)

    result = asyncio.run(
        repo.mark_handoff_created(
            LIFECYCLE_ID,
            occurred_at=OCCURRED_AT,
        )
    )

    assert result is lifecycle
    assert lifecycle.status == ClientOnboardingStatus.handoff_created
    assert lifecycle.handoff_created_at == OCCURRED_AT
    assert client_onboarding_transition_changed(result) is True
    assert (
        client_onboarding_transition_previous_status(result)
        == ClientOnboardingStatus.password_set
    )


def test_async_mark_activation_ready_requires_handoff_and_password() -> None:
    lifecycle = ClientOnboardingLifecycle(
        id=LIFECYCLE_ID,
        status=ClientOnboardingStatus.handoff_created,
        password_set_at=OCCURRED_AT,
    )
    session = MagicMock()
    session.get = AsyncMock(return_value=lifecycle)
    session.execute = AsyncMock(return_value=MagicMock(rowcount=1))
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    repo = ClientOnboardingRepositoryAsync(session)

    result = asyncio.run(
        repo.mark_activation_ready(
            LIFECYCLE_ID,
            occurred_at=OCCURRED_AT,
        )
    )

    assert result is lifecycle
    assert lifecycle.status == ClientOnboardingStatus.activation_ready
    assert lifecycle.activation_ready_at == OCCURRED_AT
    assert client_onboarding_transition_changed(result) is True
    assert (
        client_onboarding_transition_previous_status(result)
        == ClientOnboardingStatus.handoff_created
    )


def test_async_mark_handoff_created_noops_for_later_status() -> None:
    lifecycle = ClientOnboardingLifecycle(
        id=LIFECYCLE_ID,
        status=ClientOnboardingStatus.activation_ready,
    )
    session = MagicMock()
    session.get = AsyncMock(return_value=lifecycle)
    session.execute = AsyncMock(return_value=MagicMock(rowcount=0))
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    repo = ClientOnboardingRepositoryAsync(session)

    result = asyncio.run(
        repo.mark_handoff_created(
            LIFECYCLE_ID,
            occurred_at=OCCURRED_AT,
        )
    )

    assert result is lifecycle
    assert lifecycle.status == ClientOnboardingStatus.activation_ready
    assert client_onboarding_transition_changed(result) is False
    assert client_onboarding_transition_previous_status(result) is None


def test_async_mark_password_set_rolls_back_on_sqlalchemy_error() -> None:
    session = MagicMock()
    session.execute = AsyncMock(side_effect=SQLAlchemyError("database unavailable"))
    session.rollback = AsyncMock()
    repo = ClientOnboardingRepositoryAsync(session)

    with pytest.raises(SQLAlchemyError):
        asyncio.run(
            repo.mark_password_set(
                LIFECYCLE_ID,
                occurred_at=OCCURRED_AT,
            )
        )

    session.rollback.assert_awaited_once()


def test_async_mark_handoff_created_rolls_back_on_sqlalchemy_error() -> None:
    session = MagicMock()
    session.execute = AsyncMock(side_effect=SQLAlchemyError("database unavailable"))
    session.rollback = AsyncMock()
    repo = ClientOnboardingRepositoryAsync(session)

    with pytest.raises(SQLAlchemyError):
        asyncio.run(
            repo.mark_handoff_created(
                LIFECYCLE_ID,
                occurred_at=OCCURRED_AT,
            )
        )

    session.rollback.assert_awaited_once()


def test_async_mark_activation_ready_rolls_back_on_sqlalchemy_error() -> None:
    session = MagicMock()
    session.execute = AsyncMock(side_effect=SQLAlchemyError("database unavailable"))
    session.rollback = AsyncMock()
    repo = ClientOnboardingRepositoryAsync(session)

    with pytest.raises(SQLAlchemyError):
        asyncio.run(
            repo.mark_activation_ready(
                LIFECYCLE_ID,
                occurred_at=OCCURRED_AT,
            )
        )

    session.rollback.assert_awaited_once()


def test_async_get_sync_jobs_for_lifecycle_returns_jobs() -> None:
    jobs = [
        ClientOnboardingSyncJob(
            id=UUID("cccccccc-dddd-eeee-ffff-000000000000"),
            lifecycle_id=LIFECYCLE_ID,
            target=ClientOnboardingSyncTarget.database,
            job_type="record_contract_acceptance",
            idempotency_key="sync-key",
            status=ClientOnboardingSyncJobStatus.completed,
            payload={},
        )
    ]
    query_result = MagicMock()
    query_result.scalars.return_value.all.return_value = jobs
    session = MagicMock()
    session.execute = AsyncMock(return_value=query_result)
    repo = ClientOnboardingRepositoryAsync(session)

    result = asyncio.run(repo.get_sync_jobs_for_lifecycle(LIFECYCLE_ID))

    assert result == jobs


def test_async_get_sync_jobs_for_lifecycle_rolls_back_on_sqlalchemy_error() -> None:
    session = MagicMock()
    session.execute = AsyncMock(side_effect=SQLAlchemyError("database unavailable"))
    session.rollback = AsyncMock()
    repo = ClientOnboardingRepositoryAsync(session)

    with pytest.raises(SQLAlchemyError):
        asyncio.run(repo.get_sync_jobs_for_lifecycle(LIFECYCLE_ID))

    session.rollback.assert_awaited_once()


def test_async_mark_blocked_updates_status_reason() -> None:
    lifecycle = ClientOnboardingLifecycle(
        id=LIFECYCLE_ID,
        status=ClientOnboardingStatus.account_created,
    )
    session = MagicMock()
    session.get = AsyncMock(return_value=lifecycle)
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    repo = ClientOnboardingRepositoryAsync(session)

    result = asyncio.run(
        repo.mark_blocked(
            LIFECYCLE_ID,
            status_reason="Signer invite failed",
            occurred_at=OCCURRED_AT,
        )
    )

    assert result is lifecycle
    assert lifecycle.status == ClientOnboardingStatus.blocked
    assert lifecycle.status_reason == "Signer invite failed"
    assert lifecycle.updated_at == OCCURRED_AT
    session.flush.assert_awaited_once()
    session.refresh.assert_awaited_once_with(lifecycle)


def test_async_mark_blocked_rolls_back_on_sqlalchemy_error() -> None:
    session = MagicMock()
    session.get = AsyncMock(return_value=_lifecycle())
    session.flush = AsyncMock(side_effect=SQLAlchemyError("database unavailable"))
    session.rollback = AsyncMock()
    repo = ClientOnboardingRepositoryAsync(session)

    with pytest.raises(SQLAlchemyError):
        asyncio.run(
            repo.mark_blocked(
                LIFECYCLE_ID,
                status_reason="Signer invite failed",
            )
        )

    session.rollback.assert_awaited_once()


def test_async_set_slack_channel_id_updates_existing_lifecycle() -> None:
    lifecycle = ClientOnboardingLifecycle(
        id=LIFECYCLE_ID,
        status=ClientOnboardingStatus.docusign_signed,
    )
    session = MagicMock()
    session.get = AsyncMock(return_value=lifecycle)
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    repo = ClientOnboardingRepositoryAsync(session)

    result = asyncio.run(
        repo.set_slack_channel_id(
            LIFECYCLE_ID,
            slack_channel_id="C123",
            occurred_at=OCCURRED_AT,
        )
    )

    assert result is lifecycle
    assert lifecycle.slack_channel_id == "C123"
    assert lifecycle.updated_at == OCCURRED_AT
    session.flush.assert_awaited_once()
    session.refresh.assert_awaited_once_with(lifecycle)


def test_async_set_slack_channel_id_rolls_back_on_sqlalchemy_error() -> None:
    session = MagicMock()
    session.get = AsyncMock(return_value=_lifecycle())
    session.flush = AsyncMock(side_effect=SQLAlchemyError("database unavailable"))
    session.rollback = AsyncMock()
    repo = ClientOnboardingRepositoryAsync(session)

    with pytest.raises(SQLAlchemyError):
        asyncio.run(repo.set_slack_channel_id(LIFECYCLE_ID, slack_channel_id="C123"))

    session.rollback.assert_awaited_once()


def test_async_set_notion_page_id_updates_existing_lifecycle() -> None:
    lifecycle = ClientOnboardingLifecycle(
        id=LIFECYCLE_ID,
        status=ClientOnboardingStatus.docusign_signed,
    )
    session = MagicMock()
    session.get = AsyncMock(return_value=lifecycle)
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    repo = ClientOnboardingRepositoryAsync(session)

    result = asyncio.run(
        repo.set_notion_page_id(
            LIFECYCLE_ID,
            notion_page_id="notion-page-123",
            occurred_at=OCCURRED_AT,
        )
    )

    assert result is lifecycle
    assert lifecycle.notion_page_id == "notion-page-123"
    assert lifecycle.updated_at == OCCURRED_AT
    session.flush.assert_awaited_once()
    session.refresh.assert_awaited_once_with(lifecycle)


def test_async_set_notion_page_id_rolls_back_on_sqlalchemy_error() -> None:
    session = MagicMock()
    session.get = AsyncMock(return_value=_lifecycle())
    session.flush = AsyncMock(side_effect=SQLAlchemyError("database unavailable"))
    session.rollback = AsyncMock()
    repo = ClientOnboardingRepositoryAsync(session)

    with pytest.raises(SQLAlchemyError):
        asyncio.run(
            repo.set_notion_page_id(LIFECYCLE_ID, notion_page_id="notion-page-123")
        )

    session.rollback.assert_awaited_once()


def test_async_append_activity_defaults_payloads_and_persists_activity() -> None:
    session = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    repo = ClientOnboardingRepositoryAsync(session)

    activity = asyncio.run(
        repo.append_activity(
            lifecycle_id=LIFECYCLE_ID,
            activity_type="invite_sent",
            actor_type=ClientOnboardingActorType.ae,
            source=ClientOnboardingActivitySource.manage_app,
            previous_status=ClientOnboardingStatus.account_created,
            next_status=ClientOnboardingStatus.invite_sent,
            actor_id=AE_USER_ID,
            actor_display_name="AE User",
            description="Invite sent",
            occurred_at=OCCURRED_AT,
        )
    )

    assert isinstance(activity, ClientOnboardingActivity)
    assert activity.lifecycle_id == LIFECYCLE_ID
    assert activity.payload_diff == {}
    assert activity.activity_metadata == {}
    session.add.assert_called_once_with(activity)
    session.flush.assert_awaited_once()
    session.refresh.assert_awaited_once_with(activity)


def test_async_append_activity_rolls_back_on_sqlalchemy_error() -> None:
    session = MagicMock()
    session.add.side_effect = SQLAlchemyError("database unavailable")
    session.rollback = AsyncMock()
    repo = ClientOnboardingRepositoryAsync(session)

    with pytest.raises(SQLAlchemyError):
        asyncio.run(
            repo.append_activity(
                lifecycle_id=LIFECYCLE_ID,
                activity_type="invite_sent",
                actor_type=ClientOnboardingActorType.ae,
                source=ClientOnboardingActivitySource.manage_app,
            )
        )

    session.rollback.assert_awaited_once()


def test_async_status_updates_raise_when_lifecycle_is_missing() -> None:
    session = MagicMock()
    session.get = AsyncMock(return_value=None)
    repo = ClientOnboardingRepositoryAsync(session)

    with pytest.raises(ValueError, match=str(LIFECYCLE_ID)):
        asyncio.run(repo.mark_invite_sent(LIFECYCLE_ID, invite_id=INVITATION_ID))


def test_async_status_updates_roll_back_on_lifecycle_lookup_error() -> None:
    session = MagicMock()
    session.get = AsyncMock(side_effect=SQLAlchemyError("database unavailable"))
    session.rollback = AsyncMock()
    repo = ClientOnboardingRepositoryAsync(session)

    with pytest.raises(SQLAlchemyError):
        asyncio.run(repo.mark_invite_sent(LIFECYCLE_ID, invite_id=INVITATION_ID))

    assert session.rollback.await_count == 2


def test_upsert_sync_job_creates_pending_job() -> None:
    existing = ClientOnboardingSyncJob(
        id=UUID("cccccccc-dddd-eeee-ffff-000000000000"),
        lifecycle_id=LIFECYCLE_ID,
        target=ClientOnboardingSyncTarget.folk,
        job_type="update_contract_acceptance",
        idempotency_key="sync-key",
        status=ClientOnboardingSyncJobStatus.pending,
        payload={"account_id": str(ACCOUNT_ID)},
        result_payload={},
        available_at=OCCURRED_AT,
    )
    session = MagicMock()
    session.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = (
        existing
    )
    repo = ClientOnboardingRepository(session)

    job = repo.upsert_sync_job(
        lifecycle_id=LIFECYCLE_ID,
        target=ClientOnboardingSyncTarget.folk,
        job_type="update_contract_acceptance",
        idempotency_key="sync-key",
        payload={"account_id": str(ACCOUNT_ID)},
        available_at=OCCURRED_AT,
    )

    assert job is existing
    assert job.lifecycle_id == LIFECYCLE_ID
    assert job.target == ClientOnboardingSyncTarget.folk
    assert job.status == ClientOnboardingSyncJobStatus.pending
    assert job.payload == {"account_id": str(ACCOUNT_ID)}
    assert job.available_at == OCCURRED_AT
    session.execute.assert_called_once()
    session.add.assert_not_called()
    session.flush.assert_called_once()
    session.refresh.assert_called_once_with(job)


def test_upsert_sync_job_resets_retryable_existing_job() -> None:
    existing = ClientOnboardingSyncJob(
        id=UUID("cccccccc-dddd-eeee-ffff-000000000000"),
        lifecycle_id=LIFECYCLE_ID,
        target=ClientOnboardingSyncTarget.folk,
        job_type="update_contract_acceptance",
        idempotency_key="sync-key",
        status=ClientOnboardingSyncJobStatus.failed,
        payload={"old": "value"},
        result_payload={"error": "old"},
        last_error="old failure",
        completed_at=OCCURRED_AT,
        locked_at=OCCURRED_AT,
        locked_by="worker-1",
    )
    session = MagicMock()
    session.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = (
        existing
    )
    repo = ClientOnboardingRepository(session)

    job = repo.upsert_sync_job(
        lifecycle_id=LIFECYCLE_ID,
        target=ClientOnboardingSyncTarget.folk,
        job_type="update_contract_acceptance",
        idempotency_key="sync-key",
        payload={"new": "value"},
        available_at=OCCURRED_AT,
    )

    assert job is existing
    assert job.status == ClientOnboardingSyncJobStatus.pending
    assert job.payload == {"new": "value"}
    assert job.result_payload == {}
    assert job.last_error is None
    assert job.completed_at is None
    assert job.locked_at is None
    assert job.locked_by is None
    session.add.assert_not_called()
    session.execute.assert_called_once()
    session.flush.assert_called_once()
    session.refresh.assert_called_once_with(existing)


def test_upsert_sync_job_preserves_terminal_existing_job() -> None:
    existing = ClientOnboardingSyncJob(
        id=UUID("cccccccc-dddd-eeee-ffff-000000000000"),
        lifecycle_id=LIFECYCLE_ID,
        target=ClientOnboardingSyncTarget.folk,
        job_type="update_contract_acceptance",
        idempotency_key="sync-key",
        status=ClientOnboardingSyncJobStatus.completed,
        payload={"old": "value"},
        result_payload={"updated_company": True},
        completed_at=OCCURRED_AT,
    )
    session = MagicMock()
    session.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = (
        existing
    )
    repo = ClientOnboardingRepository(session)

    job = repo.upsert_sync_job(
        lifecycle_id=LIFECYCLE_ID,
        target=ClientOnboardingSyncTarget.folk,
        job_type="update_contract_acceptance",
        idempotency_key="sync-key",
        payload={"new": "value"},
        available_at=OCCURRED_AT,
    )

    assert job is existing
    assert job.status == ClientOnboardingSyncJobStatus.completed
    assert job.payload == {"old": "value"}
    assert job.result_payload == {"updated_company": True}
    assert job.completed_at == OCCURRED_AT
    session.execute.assert_called_once()
    session.flush.assert_called_once()
    session.refresh.assert_called_once_with(existing)


def test_upsert_sync_job_rolls_back_on_sqlalchemy_error() -> None:
    session = MagicMock()
    session.execute.side_effect = SQLAlchemyError("database unavailable")
    repo = ClientOnboardingRepository(session)

    with pytest.raises(SQLAlchemyError):
        repo.upsert_sync_job(
            lifecycle_id=LIFECYCLE_ID,
            target=ClientOnboardingSyncTarget.folk,
            job_type="update_contract_acceptance",
            idempotency_key="sync-key",
            payload={},
        )

    session.rollback.assert_called_once()


def test_mark_sync_job_completed_updates_existing_job() -> None:
    job = ClientOnboardingSyncJob(
        id=UUID("cccccccc-dddd-eeee-ffff-000000000000"),
        lifecycle_id=LIFECYCLE_ID,
        target=ClientOnboardingSyncTarget.database,
        job_type="record_contract_acceptance",
        idempotency_key="sync-key",
        status=ClientOnboardingSyncJobStatus.pending,
        payload={},
        locked_at=OCCURRED_AT,
        locked_by="worker-1",
        last_error="old failure",
    )
    session = MagicMock()
    session.get.return_value = job
    repo = ClientOnboardingRepository(session)

    result = repo.mark_sync_job_completed(
        job.id,
        result_payload={"ok": True},
        occurred_at=OCCURRED_AT,
    )

    assert result is job
    assert job.status == ClientOnboardingSyncJobStatus.completed
    assert job.result_payload == {"ok": True}
    assert job.completed_at == OCCURRED_AT
    assert job.locked_at is None
    assert job.locked_by is None
    assert job.last_error is None
    session.flush.assert_called_once()
    session.refresh.assert_called_once_with(job)


def test_mark_sync_job_completed_raises_when_job_missing() -> None:
    session = MagicMock()
    session.get.return_value = None
    repo = ClientOnboardingRepository(session)

    with pytest.raises(ValueError, match="Client onboarding sync job"):
        repo.mark_sync_job_completed(
            UUID("cccccccc-dddd-eeee-ffff-000000000000"),
        )


def test_mark_sync_job_failed_updates_existing_job() -> None:
    job = ClientOnboardingSyncJob(
        id=UUID("cccccccc-dddd-eeee-ffff-000000000000"),
        lifecycle_id=LIFECYCLE_ID,
        target=ClientOnboardingSyncTarget.folk,
        job_type="update_contract_acceptance",
        idempotency_key="sync-key",
        status=ClientOnboardingSyncJobStatus.pending,
        payload={},
        locked_at=OCCURRED_AT,
        locked_by="worker-1",
    )
    session = MagicMock()
    session.get.return_value = job
    repo = ClientOnboardingRepository(session)

    result = repo.mark_sync_job_failed(
        job.id,
        last_error="Folk unavailable",
        result_payload={"retryable": True},
        available_at=OCCURRED_AT,
    )

    assert result is job
    assert job.status == ClientOnboardingSyncJobStatus.failed
    assert job.result_payload == {"retryable": True}
    assert job.last_error == "Folk unavailable"
    assert job.available_at == OCCURRED_AT
    assert job.locked_at is None
    assert job.locked_by is None


def test_get_sync_jobs_for_lifecycle_returns_jobs() -> None:
    jobs = [
        ClientOnboardingSyncJob(
            id=UUID("cccccccc-dddd-eeee-ffff-000000000000"),
            lifecycle_id=LIFECYCLE_ID,
            target=ClientOnboardingSyncTarget.database,
            job_type="record_contract_acceptance",
            idempotency_key="sync-key",
            status=ClientOnboardingSyncJobStatus.completed,
            payload={},
        )
    ]
    session = MagicMock()
    session.query.return_value.filter.return_value.all.return_value = jobs
    repo = ClientOnboardingRepository(session)

    result = repo.get_sync_jobs_for_lifecycle(LIFECYCLE_ID)

    assert result == jobs


def test_get_sync_jobs_for_lifecycle_rolls_back_on_sqlalchemy_error() -> None:
    session = MagicMock()
    session.query.side_effect = SQLAlchemyError("database unavailable")
    repo = ClientOnboardingRepository(session)

    with pytest.raises(SQLAlchemyError):
        repo.get_sync_jobs_for_lifecycle(LIFECYCLE_ID)

    session.rollback.assert_called_once()
