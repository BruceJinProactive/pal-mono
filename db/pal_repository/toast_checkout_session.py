from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from db.tables.toast_checkout_sessions import ToastCheckoutSession
from utils.log import logger


class ToastCheckoutSessionRepository:
    """Async repository for Toast checkout sessions."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        token: uuid.UUID,
        conversation_id: uuid.UUID,
        external_reference_id: str,
        order_external_id: str,
        request_payload: dict[str, Any],
        session_payload: dict[str, Any],
        checkout_url: str,
        expires_at: datetime,
        status: str = "processing",
    ) -> ToastCheckoutSession:
        try:
            row = ToastCheckoutSession(
                token=token,
                conversation_id=conversation_id,
                external_reference_id=external_reference_id,
                order_external_id=order_external_id,
                request_payload=request_payload,
                session_payload=session_payload,
                checkout_url=checkout_url,
                expires_at=expires_at,
                status=status,
            )
            self.session.add(row)
            await self.session.flush()
            return row
        except SQLAlchemyError:
            await self.session.rollback()
            logger.exception("Error creating Toast checkout session")
            raise

    async def get_by_external_reference_id(
        self, external_reference_id: str
    ) -> ToastCheckoutSession | None:
        try:
            result = await self.session.execute(
                select(ToastCheckoutSession).filter(
                    ToastCheckoutSession.external_reference_id == external_reference_id
                )
            )
            return result.scalar_one_or_none()
        except SQLAlchemyError:
            await self.session.rollback()
            logger.exception("Error retrieving Toast checkout session by reference")
            raise

    async def get_by_token(self, token: uuid.UUID) -> ToastCheckoutSession | None:
        try:
            result = await self.session.execute(
                select(ToastCheckoutSession).filter(ToastCheckoutSession.token == token)
            )
            return result.scalar_one_or_none()
        except SQLAlchemyError:
            await self.session.rollback()
            logger.exception("Error retrieving Toast checkout session")
            raise

    async def mark_ready(
        self,
        row: ToastCheckoutSession,
        *,
        session_payload: dict[str, Any],
        expires_at: datetime,
    ) -> ToastCheckoutSession:
        try:
            row.session_payload = session_payload
            row.expires_at = expires_at
            row.status = "ready"
            await self.session.flush()
            return row
        except SQLAlchemyError:
            await self.session.rollback()
            logger.exception("Error marking Toast checkout session ready")
            raise

    async def mark_failed(self, row: ToastCheckoutSession, *, status: str) -> None:
        try:
            row.status = status
            await self.session.flush()
        except SQLAlchemyError:
            await self.session.rollback()
            logger.exception("Error marking Toast checkout session failed")
            raise
