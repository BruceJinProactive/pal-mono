from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_, select
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
