from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.operations.vision_rule import (
    CreateVisionRuleRequest,
    ListVisionRulesResponse,
    UpdateVisionRuleRequest,
    VisionRuleResponse,
)
from db.pal_repository import VisionRuleRepository
from db.pal_repository.data_classes.vision_rule import VisionRuleData
from services import account_service
from utils.log import logger


def _build_response(data: VisionRuleData) -> VisionRuleResponse:
    return VisionRuleResponse(
        id=data.id,
        project_id=data.project_id,
        name=data.name,
        description=data.description,
        type=data.type,
        severity=data.severity,
        is_active=data.is_active,
        rule_metadata=data.rule_metadata,
        created_at=data.created_at,
        updated_at=data.updated_at,
    )


async def create_vision_rule(
    session: AsyncSession,
    request: CreateVisionRuleRequest,
    account_name: str,
) -> VisionRuleResponse:
    account = await account_service.get_account_async(session, account_name)
    if not account:
        raise ValueError(f"Account {account_name} not found")

    repo = VisionRuleRepository(session)

    owns_project = await repo.verify_project_belongs_to_account(
        request.project_id, account.id
    )
    if not owns_project:
        raise ValueError(
            f"Project {request.project_id} does not belong to account {account_name}"
        )

    record = VisionRuleData(
        id=uuid.uuid4(),
        project_id=request.project_id,
        name=request.name,
        type=request.type,
        severity=request.severity,
        is_active=request.is_active,
        rule_metadata=request.rule_metadata,
        description=request.description,
    )

    await repo.create(record)
    logger.info(
        "[Vision Rule] Created rule",
        extra={"rule_id": str(record.id), "project_id": str(record.project_id)},
    )
    return _build_response(record)


async def get_vision_rule(
    session: AsyncSession,
    rule_id: uuid.UUID,
    account_name: str,
) -> VisionRuleResponse:
    account = await account_service.get_account_async(session, account_name)
    if not account:
        raise ValueError(f"Account {account_name} not found")

    repo = VisionRuleRepository(session)
    data = await repo.get_by_id_for_account(rule_id, account.id)
    if not data:
        raise ValueError(f"Vision rule {rule_id} not found")
    return _build_response(data)


async def list_vision_rules(
    session: AsyncSession,
    account_name: str,
    project_id: uuid.UUID | None = None,
    is_active: bool | None = None,
    limit: int = 100,
) -> ListVisionRulesResponse:
    account = await account_service.get_account_async(session, account_name)
    if not account:
        raise ValueError(f"Account {account_name} not found")

    repo = VisionRuleRepository(session)
    rules = await repo.list_by_account(
        account_id=account.id,
        project_id=project_id,
        is_active=is_active,
        limit=limit,
    )
    items = [_build_response(r) for r in rules]
    return ListVisionRulesResponse(items=items, total=len(items))


async def update_vision_rule(
    session: AsyncSession,
    rule_id: uuid.UUID,
    request: UpdateVisionRuleRequest,
    account_name: str,
) -> VisionRuleResponse:
    account = await account_service.get_account_async(session, account_name)
    if not account:
        raise ValueError(f"Account {account_name} not found")

    repo = VisionRuleRepository(session)
    data = await repo.get_by_id_for_account(rule_id, account.id)
    if not data:
        raise ValueError(f"Vision rule {rule_id} not found")

    update_fields: dict[str, object] = {}
    if request.name is not None:
        update_fields["name"] = request.name
    if request.description is not None:
        update_fields["description"] = request.description
    if request.severity is not None:
        update_fields["severity"] = request.severity
    if request.is_active is not None:
        update_fields["is_active"] = request.is_active
    if request.rule_metadata is not None:
        merged = dict(data.rule_metadata)
        merged.update(request.rule_metadata)
        update_fields["rule_metadata"] = merged

    if not update_fields:
        return _build_response(data)

    updated = await repo.update(rule_id, **update_fields)
    if not updated:
        raise ValueError(f"Vision rule {rule_id} not found after update")

    logger.info(
        "[Vision Rule] Updated rule",
        extra={"rule_id": str(rule_id)},
    )
    return _build_response(updated)


async def delete_vision_rule(
    session: AsyncSession,
    rule_id: uuid.UUID,
    account_name: str,
) -> None:
    account = await account_service.get_account_async(session, account_name)
    if not account:
        raise ValueError(f"Account {account_name} not found")

    repo = VisionRuleRepository(session)
    deleted = await repo.delete_for_account(rule_id, account.id)
    if not deleted:
        raise ValueError(f"Vision rule {rule_id} not found")
    logger.info(
        "[Vision Rule] Deleted rule",
        extra={"rule_id": str(rule_id)},
    )
