from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

import db
from api.schemas.admin.faq import (
    FAQ,
    CreateFAQRequest,
    ListFAQsResponse,
    UpdateFAQRequest,
)
from services import account_service, faq_service

from . import UserContext, _builder


async def create_faq(
    account_name: str,
    faq_create: CreateFAQRequest,
    context: UserContext,
    session: Session,
) -> FAQ:
    """Authorization is handled by require_account_permission in route decorator."""
    account = account_service.get_account(session, account_name)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {account_name} does not exist.",
        )

    project_uuid = UUID(faq_create.project_id) if faq_create.project_id else None

    faq = db.FAQ(
        account_id=account.id,
        project_id=project_uuid,
        question=faq_create.question,
        answer=faq_create.answer,
    )
    persisted_faq = faq_service.create_faq(session, faq)
    return _builder.build_faq(persisted_faq)


async def get_faqs(
    account_name: str,
    context: UserContext,
    session: Session,
    project_id: str | None = None,
) -> ListFAQsResponse:
    """Authorization is handled by require_account_permission in route decorator."""
    account = account_service.get_account(session, account_name)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {account_name} does not exist.",
        )

    project_uuid = UUID(project_id) if project_id else None

    faqs = faq_service.get_faqs_by_account_id(session, account.id, project_uuid)
    return ListFAQsResponse(
        faqs=[_builder.build_faq(faq) for faq in faqs],
        total=len(faqs),
    )


async def update_faq(
    account_name: str,
    faq_id: UUID,
    faq_update: UpdateFAQRequest,
    context: UserContext,
    session: Session,
) -> FAQ:
    """Authorization is handled by require_account_permission in route decorator."""
    account = account_service.get_account(session, account_name)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {account_name} does not exist.",
        )

    existing_faq = faq_service.get_faq_by_id(session, faq_id)
    if not existing_faq:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"FAQ {faq_id} does not exist.",
        )
    if existing_faq.account_id != account.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"FAQ {faq_id} does not belong to account {account_name}.",
        )

    updates = faq_update.model_dump(exclude_unset=True)
    updated_faq = faq_service.update_faq(session, faq_id, updates)
    if not updated_faq:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update FAQ.",
        )

    return _builder.build_faq(updated_faq)


async def delete_faq(
    account_name: str,
    faq_id: UUID,
    context: UserContext,
    session: Session,
) -> None:
    """Authorization is handled by require_account_permission in route decorator."""
    account = account_service.get_account(session, account_name)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {account_name} does not exist.",
        )

    existing_faq = faq_service.get_faq_by_id(session, faq_id)
    if not existing_faq:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"FAQ {faq_id} does not exist.",
        )
    if existing_faq.account_id != account.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"FAQ {faq_id} does not belong to account {account_name}.",
        )

    deleted = faq_service.delete_faq(session, faq_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete FAQ.",
        )
