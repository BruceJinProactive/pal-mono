from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import case, or_, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from db.tables import (
    ClientOnboardingActivity,
    ClientOnboardingActivitySource,
    ClientOnboardingActorType,
    ClientOnboardingContractType,
    ClientOnboardingLifecycle,
    ClientOnboardingStatus,
)
from utils.log import logger

ACTIVE_LIFECYCLE_STATUSES = [
    status
    for status in ClientOnboardingStatus
    if status not in {ClientOnboardingStatus.blocked, ClientOnboardingStatus.cancelled}
]

_TRANSITION_CHANGED_ATTR = "_client_onboarding_transition_changed"
_TRANSITION_PREVIOUS_STATUS_ATTR = "_client_onboarding_transition_previous_status"


def client_onboarding_transition_changed(
    lifecycle: ClientOnboardingLifecycle,
) -> bool:
    return getattr(lifecycle, _TRANSITION_CHANGED_ATTR, False) is True


def client_onboarding_transition_previous_status(
    lifecycle: ClientOnboardingLifecycle,
) -> ClientOnboardingStatus | None:
    previous_status = getattr(lifecycle, _TRANSITION_PREVIOUS_STATUS_ATTR, None)
    if isinstance(previous_status, ClientOnboardingStatus):
        return previous_status
    return None


class ClientOnboardingRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_idempotency_key(
        self, idempotency_key: str
    ) -> ClientOnboardingLifecycle | None:
        try:
            return (
                self.session.query(ClientOnboardingLifecycle)
                .filter(ClientOnboardingLifecycle.idempotency_key == idempotency_key)
                .first()
            )
        except SQLAlchemyError as exc:
            self.session.rollback()
            logger.exception(
                f"Error retrieving client onboarding by idempotency key: {exc}"
            )
            raise

    def get_active_for_account_signer(
        self, account_id: uuid.UUID, signer_email: str
    ) -> ClientOnboardingLifecycle | None:
        try:
            return (
                self.session.query(ClientOnboardingLifecycle)
                .filter(
                    ClientOnboardingLifecycle.account_id == account_id,
                    ClientOnboardingLifecycle.signer_email
                    == _normalize_email(signer_email),
                    ClientOnboardingLifecycle.status.in_(ACTIVE_LIFECYCLE_STATUSES),
                )
                .first()
            )
        except SQLAlchemyError as exc:
            self.session.rollback()
            logger.exception(
                f"Error retrieving active client onboarding by signer: {exc}"
            )
            raise

    def get_active_by_docusign_reference(
        self,
        *,
        docusign_contract_id: str | None = None,
        docusign_envelope_id: str | None = None,
        docusign_contract_url: str | None = None,
    ) -> ClientOnboardingLifecycle | None:
        conditions = _docusign_reference_conditions(
            docusign_contract_id=docusign_contract_id,
            docusign_envelope_id=docusign_envelope_id,
            docusign_contract_url=docusign_contract_url,
        )
        if not conditions:
            return None

        try:
            return (
                self.session.query(ClientOnboardingLifecycle)
                .filter(
                    or_(*conditions),
                    ClientOnboardingLifecycle.status.in_(ACTIVE_LIFECYCLE_STATUSES),
                )
                .first()
            )
        except SQLAlchemyError as exc:
            self.session.rollback()
            logger.exception(
                f"Error retrieving active client onboarding by DocuSign reference: {exc}"
            )
            raise

    def get_by_invite_id(
        self, invite_id: uuid.UUID
    ) -> ClientOnboardingLifecycle | None:
        try:
            return (
                self.session.query(ClientOnboardingLifecycle)
                .filter(ClientOnboardingLifecycle.invite_id == invite_id)
                .first()
            )
        except SQLAlchemyError as exc:
            self.session.rollback()
            logger.exception(f"Error retrieving client onboarding by invite id: {exc}")
            raise

    def create_lifecycle(
        self,
        *,
        idempotency_key: str | None,
        account_id: uuid.UUID,
        manage_app_account_name: str,
        order_form_id: str | None,
        client_company_name: str,
        signer_name: str | None,
        signer_email: str,
        contract_type: ClientOnboardingContractType,
        docusign_contract_id: str | None,
        docusign_envelope_id: str | None,
        docusign_contract_url: str | None,
        ae_owner_user_id: uuid.UUID,
        fde_owner_user_id: uuid.UUID | None,
        folk_company_id: str | None,
        folk_contact_id: str | None,
        scoping_doc_url: str | None,
        occurred_at: datetime | None = None,
    ) -> ClientOnboardingLifecycle:
        try:
            lifecycle = _build_lifecycle(
                idempotency_key=idempotency_key,
                account_id=account_id,
                manage_app_account_name=manage_app_account_name,
                order_form_id=order_form_id,
                client_company_name=client_company_name,
                signer_name=signer_name,
                signer_email=signer_email,
                contract_type=contract_type,
                docusign_contract_id=docusign_contract_id,
                docusign_envelope_id=docusign_envelope_id,
                docusign_contract_url=docusign_contract_url,
                ae_owner_user_id=ae_owner_user_id,
                fde_owner_user_id=fde_owner_user_id,
                folk_company_id=folk_company_id,
                folk_contact_id=folk_contact_id,
                scoping_doc_url=scoping_doc_url,
                occurred_at=occurred_at,
            )
            self.session.add(lifecycle)
            self.session.flush()
            self.session.refresh(lifecycle)
            return lifecycle
        except SQLAlchemyError as exc:
            self.session.rollback()
            logger.exception(f"Error creating client onboarding lifecycle: {exc}")
            raise

    def mark_invite_sent(
        self,
        lifecycle_id: uuid.UUID,
        *,
        invite_id: uuid.UUID,
        occurred_at: datetime | None = None,
    ) -> ClientOnboardingLifecycle:
        try:
            lifecycle = self._require_lifecycle(lifecycle_id)
            lifecycle.invite_id = invite_id
            lifecycle.status = ClientOnboardingStatus.invite_sent
            lifecycle.invite_sent_at = occurred_at or datetime.now(timezone.utc)
            self.session.flush()
            self.session.refresh(lifecycle)
            return lifecycle
        except SQLAlchemyError as exc:
            self.session.rollback()
            logger.exception(f"Error marking client onboarding invite sent: {exc}")
            raise

    def mark_invite_opened(
        self,
        lifecycle_id: uuid.UUID,
        *,
        occurred_at: datetime | None = None,
    ) -> ClientOnboardingLifecycle:
        try:
            opened_at = occurred_at or datetime.now(timezone.utc)
            result = self.session.execute(
                update(ClientOnboardingLifecycle)
                .where(
                    ClientOnboardingLifecycle.id == lifecycle_id,
                    ClientOnboardingLifecycle.status
                    == ClientOnboardingStatus.invite_sent,
                )
                .values(
                    status=ClientOnboardingStatus.invite_opened,
                    invite_opened_at=opened_at,
                    updated_at=opened_at,
                )
                .execution_options(synchronize_session="fetch")
            )
            transition_changed = _rowcount_changed(result)
            lifecycle = self._require_lifecycle(lifecycle_id)
            if transition_changed:
                lifecycle.status = ClientOnboardingStatus.invite_opened
                lifecycle.invite_opened_at = opened_at
            self.session.flush()
            self.session.refresh(lifecycle)
            _annotate_transition(
                lifecycle,
                changed=transition_changed,
                previous_status=(
                    ClientOnboardingStatus.invite_sent if transition_changed else None
                ),
            )
            return lifecycle
        except SQLAlchemyError as exc:
            self.session.rollback()
            logger.exception(f"Error marking client onboarding invite opened: {exc}")
            raise

    def mark_docusign_viewed(
        self,
        lifecycle_id: uuid.UUID,
        *,
        occurred_at: datetime | None = None,
    ) -> ClientOnboardingLifecycle:
        try:
            viewed_at = occurred_at or datetime.now(timezone.utc)
            previous_status = self._mark_docusign_viewed_from_status(
                lifecycle_id,
                previous_status=ClientOnboardingStatus.invite_opened,
                occurred_at=viewed_at,
            )
            if previous_status is None:
                previous_status = self._mark_docusign_viewed_from_status(
                    lifecycle_id,
                    previous_status=ClientOnboardingStatus.invite_sent,
                    occurred_at=viewed_at,
                )
            transition_changed = previous_status is not None
            lifecycle = self._require_lifecycle(lifecycle_id)
            if transition_changed:
                lifecycle.status = ClientOnboardingStatus.docusign_viewed
                lifecycle.docusign_viewed_at = viewed_at
                if lifecycle.invite_opened_at is None:
                    lifecycle.invite_opened_at = viewed_at
            self.session.flush()
            self.session.refresh(lifecycle)
            _annotate_transition(
                lifecycle,
                changed=transition_changed,
                previous_status=previous_status,
            )
            return lifecycle
        except SQLAlchemyError as exc:
            self.session.rollback()
            logger.exception(f"Error marking client onboarding DocuSign viewed: {exc}")
            raise

    def mark_docusign_signed(
        self,
        lifecycle_id: uuid.UUID,
        *,
        occurred_at: datetime | None = None,
    ) -> ClientOnboardingLifecycle:
        try:
            signed_at = occurred_at or datetime.now(timezone.utc)
            previous_status = None
            for candidate_status in (
                ClientOnboardingStatus.docusign_viewed,
                ClientOnboardingStatus.invite_opened,
                ClientOnboardingStatus.invite_sent,
            ):
                previous_status = self._mark_docusign_signed_from_status(
                    lifecycle_id,
                    previous_status=candidate_status,
                    occurred_at=signed_at,
                )
                if previous_status is not None:
                    break

            transition_changed = previous_status is not None
            lifecycle = self._require_lifecycle(lifecycle_id)
            if transition_changed:
                lifecycle.status = ClientOnboardingStatus.docusign_signed
                lifecycle.docusign_signed_at = signed_at
                if lifecycle.invite_opened_at is None:
                    lifecycle.invite_opened_at = signed_at
                if lifecycle.docusign_viewed_at is None:
                    lifecycle.docusign_viewed_at = signed_at
            self.session.flush()
            self.session.refresh(lifecycle)
            _annotate_transition(
                lifecycle,
                changed=transition_changed,
                previous_status=previous_status,
            )
            return lifecycle
        except SQLAlchemyError as exc:
            self.session.rollback()
            logger.exception(f"Error marking client onboarding DocuSign signed: {exc}")
            raise

    def mark_blocked(
        self,
        lifecycle_id: uuid.UUID,
        *,
        status_reason: str,
        occurred_at: datetime | None = None,
    ) -> ClientOnboardingLifecycle:
        try:
            lifecycle = self._require_lifecycle(lifecycle_id)
            lifecycle.status = ClientOnboardingStatus.blocked
            lifecycle.status_reason = status_reason
            lifecycle.updated_at = occurred_at or datetime.now(timezone.utc)
            self.session.flush()
            self.session.refresh(lifecycle)
            return lifecycle
        except SQLAlchemyError as exc:
            self.session.rollback()
            logger.exception(f"Error marking client onboarding blocked: {exc}")
            raise

    def append_activity(
        self,
        *,
        lifecycle_id: uuid.UUID,
        activity_type: str,
        actor_type: ClientOnboardingActorType,
        source: ClientOnboardingActivitySource,
        previous_status: ClientOnboardingStatus | None = None,
        next_status: ClientOnboardingStatus | None = None,
        actor_id: uuid.UUID | None = None,
        actor_display_name: str | None = None,
        description: str | None = None,
        payload_diff: dict[str, Any] | None = None,
        activity_metadata: dict[str, Any] | None = None,
        occurred_at: datetime | None = None,
    ) -> ClientOnboardingActivity:
        try:
            activity = _build_activity(
                lifecycle_id=lifecycle_id,
                activity_type=activity_type,
                actor_type=actor_type,
                source=source,
                previous_status=previous_status,
                next_status=next_status,
                actor_id=actor_id,
                actor_display_name=actor_display_name,
                description=description,
                payload_diff=payload_diff,
                activity_metadata=activity_metadata,
                occurred_at=occurred_at,
            )
            self.session.add(activity)
            self.session.flush()
            self.session.refresh(activity)
            return activity
        except SQLAlchemyError as exc:
            self.session.rollback()
            logger.exception(f"Error appending client onboarding activity: {exc}")
            raise

    def _require_lifecycle(self, lifecycle_id: uuid.UUID) -> ClientOnboardingLifecycle:
        try:
            lifecycle = self.session.get(ClientOnboardingLifecycle, lifecycle_id)
        except SQLAlchemyError as exc:
            self.session.rollback()
            logger.exception(f"Error retrieving client onboarding lifecycle: {exc}")
            raise

        if not lifecycle:
            raise ValueError(f"Client onboarding lifecycle {lifecycle_id} not found")
        return lifecycle

    def _mark_docusign_viewed_from_status(
        self,
        lifecycle_id: uuid.UUID,
        *,
        previous_status: ClientOnboardingStatus,
        occurred_at: datetime,
    ) -> ClientOnboardingStatus | None:
        result = self.session.execute(
            update(ClientOnboardingLifecycle)
            .where(
                ClientOnboardingLifecycle.id == lifecycle_id,
                ClientOnboardingLifecycle.status == previous_status,
            )
            .values(
                status=ClientOnboardingStatus.docusign_viewed,
                docusign_viewed_at=occurred_at,
                invite_opened_at=case(
                    (
                        ClientOnboardingLifecycle.invite_opened_at.is_(None),
                        occurred_at,
                    ),
                    else_=ClientOnboardingLifecycle.invite_opened_at,
                ),
                updated_at=occurred_at,
            )
            .execution_options(synchronize_session="fetch")
        )
        return previous_status if _rowcount_changed(result) else None

    def _mark_docusign_signed_from_status(
        self,
        lifecycle_id: uuid.UUID,
        *,
        previous_status: ClientOnboardingStatus,
        occurred_at: datetime,
    ) -> ClientOnboardingStatus | None:
        result = self.session.execute(
            update(ClientOnboardingLifecycle)
            .where(
                ClientOnboardingLifecycle.id == lifecycle_id,
                ClientOnboardingLifecycle.status == previous_status,
            )
            .values(
                status=ClientOnboardingStatus.docusign_signed,
                docusign_signed_at=occurred_at,
                docusign_viewed_at=case(
                    (
                        ClientOnboardingLifecycle.docusign_viewed_at.is_(None),
                        occurred_at,
                    ),
                    else_=ClientOnboardingLifecycle.docusign_viewed_at,
                ),
                invite_opened_at=case(
                    (
                        ClientOnboardingLifecycle.invite_opened_at.is_(None),
                        occurred_at,
                    ),
                    else_=ClientOnboardingLifecycle.invite_opened_at,
                ),
                updated_at=occurred_at,
            )
            .execution_options(synchronize_session="fetch")
        )
        return previous_status if _rowcount_changed(result) else None


class ClientOnboardingRepositoryAsync:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_idempotency_key(
        self, idempotency_key: str
    ) -> ClientOnboardingLifecycle | None:
        try:
            result = await self.session.execute(
                select(ClientOnboardingLifecycle).filter(
                    ClientOnboardingLifecycle.idempotency_key == idempotency_key
                )
            )
            return result.scalars().first()
        except SQLAlchemyError as exc:
            await self.session.rollback()
            logger.exception(
                f"Error retrieving client onboarding by idempotency key: {exc}"
            )
            raise

    async def get_active_for_account_signer(
        self, account_id: uuid.UUID, signer_email: str
    ) -> ClientOnboardingLifecycle | None:
        try:
            result = await self.session.execute(
                select(ClientOnboardingLifecycle).filter(
                    ClientOnboardingLifecycle.account_id == account_id,
                    ClientOnboardingLifecycle.signer_email
                    == _normalize_email(signer_email),
                    ClientOnboardingLifecycle.status.in_(ACTIVE_LIFECYCLE_STATUSES),
                )
            )
            return result.scalars().first()
        except SQLAlchemyError as exc:
            await self.session.rollback()
            logger.exception(
                f"Error retrieving active client onboarding by signer: {exc}"
            )
            raise

    async def get_active_by_docusign_reference(
        self,
        *,
        docusign_contract_id: str | None = None,
        docusign_envelope_id: str | None = None,
        docusign_contract_url: str | None = None,
    ) -> ClientOnboardingLifecycle | None:
        conditions = _docusign_reference_conditions(
            docusign_contract_id=docusign_contract_id,
            docusign_envelope_id=docusign_envelope_id,
            docusign_contract_url=docusign_contract_url,
        )
        if not conditions:
            return None

        try:
            result = await self.session.execute(
                select(ClientOnboardingLifecycle).filter(
                    or_(*conditions),
                    ClientOnboardingLifecycle.status.in_(ACTIVE_LIFECYCLE_STATUSES),
                )
            )
            return result.scalars().first()
        except SQLAlchemyError as exc:
            await self.session.rollback()
            logger.exception(
                f"Error retrieving active client onboarding by DocuSign reference: {exc}"
            )
            raise

    async def get_by_invite_id(
        self, invite_id: uuid.UUID
    ) -> ClientOnboardingLifecycle | None:
        try:
            result = await self.session.execute(
                select(ClientOnboardingLifecycle).filter(
                    ClientOnboardingLifecycle.invite_id == invite_id
                )
            )
            return result.scalars().first()
        except SQLAlchemyError as exc:
            await self.session.rollback()
            logger.exception(f"Error retrieving client onboarding by invite id: {exc}")
            raise

    async def create_lifecycle(
        self,
        *,
        idempotency_key: str | None,
        account_id: uuid.UUID,
        manage_app_account_name: str,
        order_form_id: str | None,
        client_company_name: str,
        signer_name: str | None,
        signer_email: str,
        contract_type: ClientOnboardingContractType,
        docusign_contract_id: str | None,
        docusign_envelope_id: str | None,
        docusign_contract_url: str | None,
        ae_owner_user_id: uuid.UUID,
        fde_owner_user_id: uuid.UUID | None,
        folk_company_id: str | None,
        folk_contact_id: str | None,
        scoping_doc_url: str | None,
        occurred_at: datetime | None = None,
    ) -> ClientOnboardingLifecycle:
        try:
            lifecycle = _build_lifecycle(
                idempotency_key=idempotency_key,
                account_id=account_id,
                manage_app_account_name=manage_app_account_name,
                order_form_id=order_form_id,
                client_company_name=client_company_name,
                signer_name=signer_name,
                signer_email=signer_email,
                contract_type=contract_type,
                docusign_contract_id=docusign_contract_id,
                docusign_envelope_id=docusign_envelope_id,
                docusign_contract_url=docusign_contract_url,
                ae_owner_user_id=ae_owner_user_id,
                fde_owner_user_id=fde_owner_user_id,
                folk_company_id=folk_company_id,
                folk_contact_id=folk_contact_id,
                scoping_doc_url=scoping_doc_url,
                occurred_at=occurred_at,
            )
            self.session.add(lifecycle)
            await self.session.flush()
            await self.session.refresh(lifecycle)
            return lifecycle
        except SQLAlchemyError as exc:
            await self.session.rollback()
            logger.exception(f"Error creating client onboarding lifecycle: {exc}")
            raise

    async def mark_invite_sent(
        self,
        lifecycle_id: uuid.UUID,
        *,
        invite_id: uuid.UUID,
        occurred_at: datetime | None = None,
    ) -> ClientOnboardingLifecycle:
        try:
            lifecycle = await self._require_lifecycle(lifecycle_id)
            lifecycle.invite_id = invite_id
            lifecycle.status = ClientOnboardingStatus.invite_sent
            lifecycle.invite_sent_at = occurred_at or datetime.now(timezone.utc)
            await self.session.flush()
            await self.session.refresh(lifecycle)
            return lifecycle
        except SQLAlchemyError as exc:
            await self.session.rollback()
            logger.exception(f"Error marking client onboarding invite sent: {exc}")
            raise

    async def mark_invite_opened(
        self,
        lifecycle_id: uuid.UUID,
        *,
        occurred_at: datetime | None = None,
    ) -> ClientOnboardingLifecycle:
        try:
            opened_at = occurred_at or datetime.now(timezone.utc)
            result = await self.session.execute(
                update(ClientOnboardingLifecycle)
                .where(
                    ClientOnboardingLifecycle.id == lifecycle_id,
                    ClientOnboardingLifecycle.status
                    == ClientOnboardingStatus.invite_sent,
                )
                .values(
                    status=ClientOnboardingStatus.invite_opened,
                    invite_opened_at=opened_at,
                    updated_at=opened_at,
                )
                .execution_options(synchronize_session="fetch")
            )
            transition_changed = _rowcount_changed(result)
            lifecycle = await self._require_lifecycle(lifecycle_id)
            if transition_changed:
                lifecycle.status = ClientOnboardingStatus.invite_opened
                lifecycle.invite_opened_at = opened_at
            await self.session.flush()
            await self.session.refresh(lifecycle)
            _annotate_transition(
                lifecycle,
                changed=transition_changed,
                previous_status=(
                    ClientOnboardingStatus.invite_sent if transition_changed else None
                ),
            )
            return lifecycle
        except SQLAlchemyError as exc:
            await self.session.rollback()
            logger.exception(f"Error marking client onboarding invite opened: {exc}")
            raise

    async def mark_docusign_viewed(
        self,
        lifecycle_id: uuid.UUID,
        *,
        occurred_at: datetime | None = None,
    ) -> ClientOnboardingLifecycle:
        try:
            viewed_at = occurred_at or datetime.now(timezone.utc)
            previous_status = await self._mark_docusign_viewed_from_status(
                lifecycle_id,
                previous_status=ClientOnboardingStatus.invite_opened,
                occurred_at=viewed_at,
            )
            if previous_status is None:
                previous_status = await self._mark_docusign_viewed_from_status(
                    lifecycle_id,
                    previous_status=ClientOnboardingStatus.invite_sent,
                    occurred_at=viewed_at,
                )
            transition_changed = previous_status is not None
            lifecycle = await self._require_lifecycle(lifecycle_id)
            if transition_changed:
                lifecycle.status = ClientOnboardingStatus.docusign_viewed
                lifecycle.docusign_viewed_at = viewed_at
                if lifecycle.invite_opened_at is None:
                    lifecycle.invite_opened_at = viewed_at
            await self.session.flush()
            await self.session.refresh(lifecycle)
            _annotate_transition(
                lifecycle,
                changed=transition_changed,
                previous_status=previous_status,
            )
            return lifecycle
        except SQLAlchemyError as exc:
            await self.session.rollback()
            logger.exception(f"Error marking client onboarding DocuSign viewed: {exc}")
            raise

    async def mark_docusign_signed(
        self,
        lifecycle_id: uuid.UUID,
        *,
        occurred_at: datetime | None = None,
    ) -> ClientOnboardingLifecycle:
        try:
            signed_at = occurred_at or datetime.now(timezone.utc)
            previous_status = None
            for candidate_status in (
                ClientOnboardingStatus.docusign_viewed,
                ClientOnboardingStatus.invite_opened,
                ClientOnboardingStatus.invite_sent,
            ):
                previous_status = await self._mark_docusign_signed_from_status(
                    lifecycle_id,
                    previous_status=candidate_status,
                    occurred_at=signed_at,
                )
                if previous_status is not None:
                    break

            transition_changed = previous_status is not None
            lifecycle = await self._require_lifecycle(lifecycle_id)
            if transition_changed:
                lifecycle.status = ClientOnboardingStatus.docusign_signed
                lifecycle.docusign_signed_at = signed_at
                if lifecycle.invite_opened_at is None:
                    lifecycle.invite_opened_at = signed_at
                if lifecycle.docusign_viewed_at is None:
                    lifecycle.docusign_viewed_at = signed_at
            await self.session.flush()
            await self.session.refresh(lifecycle)
            _annotate_transition(
                lifecycle,
                changed=transition_changed,
                previous_status=previous_status,
            )
            return lifecycle
        except SQLAlchemyError as exc:
            await self.session.rollback()
            logger.exception(f"Error marking client onboarding DocuSign signed: {exc}")
            raise

    async def mark_blocked(
        self,
        lifecycle_id: uuid.UUID,
        *,
        status_reason: str,
        occurred_at: datetime | None = None,
    ) -> ClientOnboardingLifecycle:
        try:
            lifecycle = await self._require_lifecycle(lifecycle_id)
            lifecycle.status = ClientOnboardingStatus.blocked
            lifecycle.status_reason = status_reason
            lifecycle.updated_at = occurred_at or datetime.now(timezone.utc)
            await self.session.flush()
            await self.session.refresh(lifecycle)
            return lifecycle
        except SQLAlchemyError as exc:
            await self.session.rollback()
            logger.exception(f"Error marking client onboarding blocked: {exc}")
            raise

    async def append_activity(
        self,
        *,
        lifecycle_id: uuid.UUID,
        activity_type: str,
        actor_type: ClientOnboardingActorType,
        source: ClientOnboardingActivitySource,
        previous_status: ClientOnboardingStatus | None = None,
        next_status: ClientOnboardingStatus | None = None,
        actor_id: uuid.UUID | None = None,
        actor_display_name: str | None = None,
        description: str | None = None,
        payload_diff: dict[str, Any] | None = None,
        activity_metadata: dict[str, Any] | None = None,
        occurred_at: datetime | None = None,
    ) -> ClientOnboardingActivity:
        try:
            activity = _build_activity(
                lifecycle_id=lifecycle_id,
                activity_type=activity_type,
                actor_type=actor_type,
                source=source,
                previous_status=previous_status,
                next_status=next_status,
                actor_id=actor_id,
                actor_display_name=actor_display_name,
                description=description,
                payload_diff=payload_diff,
                activity_metadata=activity_metadata,
                occurred_at=occurred_at,
            )
            self.session.add(activity)
            await self.session.flush()
            await self.session.refresh(activity)
            return activity
        except SQLAlchemyError as exc:
            await self.session.rollback()
            logger.exception(f"Error appending client onboarding activity: {exc}")
            raise

    async def _require_lifecycle(
        self, lifecycle_id: uuid.UUID
    ) -> ClientOnboardingLifecycle:
        try:
            lifecycle = await self.session.get(ClientOnboardingLifecycle, lifecycle_id)
        except SQLAlchemyError as exc:
            await self.session.rollback()
            logger.exception(f"Error retrieving client onboarding lifecycle: {exc}")
            raise

        if not lifecycle:
            raise ValueError(f"Client onboarding lifecycle {lifecycle_id} not found")
        return lifecycle

    async def _mark_docusign_viewed_from_status(
        self,
        lifecycle_id: uuid.UUID,
        *,
        previous_status: ClientOnboardingStatus,
        occurred_at: datetime,
    ) -> ClientOnboardingStatus | None:
        result = await self.session.execute(
            update(ClientOnboardingLifecycle)
            .where(
                ClientOnboardingLifecycle.id == lifecycle_id,
                ClientOnboardingLifecycle.status == previous_status,
            )
            .values(
                status=ClientOnboardingStatus.docusign_viewed,
                docusign_viewed_at=occurred_at,
                invite_opened_at=case(
                    (
                        ClientOnboardingLifecycle.invite_opened_at.is_(None),
                        occurred_at,
                    ),
                    else_=ClientOnboardingLifecycle.invite_opened_at,
                ),
                updated_at=occurred_at,
            )
            .execution_options(synchronize_session="fetch")
        )
        return previous_status if _rowcount_changed(result) else None

    async def _mark_docusign_signed_from_status(
        self,
        lifecycle_id: uuid.UUID,
        *,
        previous_status: ClientOnboardingStatus,
        occurred_at: datetime,
    ) -> ClientOnboardingStatus | None:
        result = await self.session.execute(
            update(ClientOnboardingLifecycle)
            .where(
                ClientOnboardingLifecycle.id == lifecycle_id,
                ClientOnboardingLifecycle.status == previous_status,
            )
            .values(
                status=ClientOnboardingStatus.docusign_signed,
                docusign_signed_at=occurred_at,
                docusign_viewed_at=case(
                    (
                        ClientOnboardingLifecycle.docusign_viewed_at.is_(None),
                        occurred_at,
                    ),
                    else_=ClientOnboardingLifecycle.docusign_viewed_at,
                ),
                invite_opened_at=case(
                    (
                        ClientOnboardingLifecycle.invite_opened_at.is_(None),
                        occurred_at,
                    ),
                    else_=ClientOnboardingLifecycle.invite_opened_at,
                ),
                updated_at=occurred_at,
            )
            .execution_options(synchronize_session="fetch")
        )
        return previous_status if _rowcount_changed(result) else None


def _docusign_reference_conditions(
    *,
    docusign_contract_id: str | None,
    docusign_envelope_id: str | None,
    docusign_contract_url: str | None,
) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []
    if docusign_contract_id:
        conditions.append(
            ClientOnboardingLifecycle.docusign_contract_id == docusign_contract_id
        )
    if docusign_envelope_id:
        conditions.append(
            ClientOnboardingLifecycle.docusign_envelope_id == docusign_envelope_id
        )
    if docusign_contract_url:
        conditions.append(
            ClientOnboardingLifecycle.docusign_contract_url == docusign_contract_url
        )
    return conditions


def _rowcount_changed(result: Any) -> bool:
    rowcount = getattr(result, "rowcount", 0)
    return isinstance(rowcount, int) and rowcount > 0


def _annotate_transition(
    lifecycle: ClientOnboardingLifecycle,
    *,
    changed: bool,
    previous_status: ClientOnboardingStatus | None,
) -> None:
    setattr(lifecycle, _TRANSITION_CHANGED_ATTR, changed)
    setattr(lifecycle, _TRANSITION_PREVIOUS_STATUS_ATTR, previous_status)


def _build_lifecycle(
    *,
    idempotency_key: str | None,
    account_id: uuid.UUID,
    manage_app_account_name: str,
    order_form_id: str | None,
    client_company_name: str,
    signer_name: str | None,
    signer_email: str,
    contract_type: ClientOnboardingContractType,
    docusign_contract_id: str | None,
    docusign_envelope_id: str | None,
    docusign_contract_url: str | None,
    ae_owner_user_id: uuid.UUID,
    fde_owner_user_id: uuid.UUID | None,
    folk_company_id: str | None,
    folk_contact_id: str | None,
    scoping_doc_url: str | None,
    occurred_at: datetime | None,
) -> ClientOnboardingLifecycle:
    now = occurred_at or datetime.now(timezone.utc)
    return ClientOnboardingLifecycle(
        id=uuid.uuid4(),
        idempotency_key=idempotency_key,
        account_id=account_id,
        manage_app_account_name=manage_app_account_name,
        order_form_id=order_form_id,
        client_company_name=client_company_name,
        signer_name=signer_name,
        signer_email=_normalize_email(signer_email),
        contract_type=contract_type,
        docusign_contract_id=docusign_contract_id,
        docusign_envelope_id=docusign_envelope_id,
        docusign_contract_url=docusign_contract_url,
        ae_owner_user_id=ae_owner_user_id,
        fde_owner_user_id=fde_owner_user_id,
        folk_company_id=folk_company_id,
        folk_contact_id=folk_contact_id,
        scoping_doc_url=scoping_doc_url,
        status=ClientOnboardingStatus.account_created,
        contract_prepared_at=now,
        account_created_at=now,
    )


def _build_activity(
    *,
    lifecycle_id: uuid.UUID,
    activity_type: str,
    actor_type: ClientOnboardingActorType,
    source: ClientOnboardingActivitySource,
    previous_status: ClientOnboardingStatus | None,
    next_status: ClientOnboardingStatus | None,
    actor_id: uuid.UUID | None,
    actor_display_name: str | None,
    description: str | None,
    payload_diff: dict[str, Any] | None,
    activity_metadata: dict[str, Any] | None,
    occurred_at: datetime | None,
) -> ClientOnboardingActivity:
    return ClientOnboardingActivity(
        id=uuid.uuid4(),
        lifecycle_id=lifecycle_id,
        activity_type=activity_type,
        previous_status=previous_status,
        next_status=next_status,
        actor_type=actor_type,
        actor_id=actor_id,
        actor_display_name=actor_display_name,
        source=source,
        description=description,
        payload_diff=payload_diff or {},
        activity_metadata=activity_metadata or {},
        occurred_at=occurred_at or datetime.now(timezone.utc),
    )


def _normalize_email(email: str) -> str:
    return email.strip().lower()
