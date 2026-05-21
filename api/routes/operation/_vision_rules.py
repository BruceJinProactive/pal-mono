"""Vision Rule API Routes Implementation."""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.operations.vision_rule import (
    CreateVisionRuleRequest,
    ListVisionRulesResponse,
    UpdateVisionRuleRequest,
    VisionRuleResponse,
)
from services import vision_rule_service
from utils.log import logger
from utils.otel import traced


@traced("vision_rule.create")
async def create_vision_rule(
    session: AsyncSession,
    request: CreateVisionRuleRequest,
    account_name: str,
) -> VisionRuleResponse:
    try:
        return await vision_rule_service.create_vision_rule(
            session=session,
            request=request,
            account_name=account_name,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )
    except Exception:
        logger.error("[Vision Rule] Failed to create rule", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create vision rule",
            headers={"Content-Type": "application/json"},
        )


@traced("vision_rule.get")
async def get_vision_rule(
    session: AsyncSession,
    rule_id: uuid.UUID,
    account_name: str,
) -> VisionRuleResponse:
    try:
        return await vision_rule_service.get_vision_rule(
            session=session,
            rule_id=rule_id,
            account_name=account_name,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )
    except Exception:
        logger.error(
            "[Vision Rule] Failed to get rule",
            exc_info=True,
            extra={"rule_id": str(rule_id)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get vision rule",
            headers={"Content-Type": "application/json"},
        )


@traced("vision_rule.list")
async def list_vision_rules(
    session: AsyncSession,
    account_name: str,
    project_id: uuid.UUID | None = None,
    is_active: bool | None = None,
    limit: int = 100,
) -> ListVisionRulesResponse:
    try:
        return await vision_rule_service.list_vision_rules(
            session=session,
            account_name=account_name,
            project_id=project_id,
            is_active=is_active,
            limit=limit,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )
    except Exception:
        logger.error(
            "[Vision Rule] Failed to list rules",
            exc_info=True,
            extra={"account_name": account_name},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list vision rules",
            headers={"Content-Type": "application/json"},
        )


@traced("vision_rule.update")
async def update_vision_rule(
    session: AsyncSession,
    rule_id: uuid.UUID,
    request: UpdateVisionRuleRequest,
    account_name: str,
) -> VisionRuleResponse:
    try:
        return await vision_rule_service.update_vision_rule(
            session=session,
            rule_id=rule_id,
            request=request,
            account_name=account_name,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )
    except Exception:
        logger.error(
            "[Vision Rule] Failed to update rule",
            exc_info=True,
            extra={"rule_id": str(rule_id)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update vision rule",
            headers={"Content-Type": "application/json"},
        )


@traced("vision_rule.delete")
async def delete_vision_rule(
    session: AsyncSession,
    rule_id: uuid.UUID,
    account_name: str,
) -> None:
    try:
        await vision_rule_service.delete_vision_rule(
            session=session,
            rule_id=rule_id,
            account_name=account_name,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )
    except Exception:
        logger.error(
            "[Vision Rule] Failed to delete rule",
            exc_info=True,
            extra={"rule_id": str(rule_id)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete vision rule",
            headers={"Content-Type": "application/json"},
        )
