from fastapi import HTTPException, status
from sqlalchemy.orm import Session

import db
from api.schemas.admin.faq import FAQ, CreateFAQRequest, ListFAQsResponse
from services import account_service, faq_service

from . import UserContext, _builder
from ._auth import authorize_user_account


async def create_faq(
    account_name: str,
    faq_create: CreateFAQRequest,
    context: UserContext,
    session: Session,
) -> FAQ:
    account = account_service.get_account(session, account_name)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {account_name} does not exist.",
        )
    authorize_user_account(context, account.name)

    faq = db.FAQ(
        account_id=account.id,
        question=faq_create.question,
        answer=faq_create.answer,
    )
    persisted_faq = faq_service.create_faq(session, faq)
    return _builder.build_faq(persisted_faq)


async def get_faqs(
    account_name: str,
    context: UserContext,
    session: Session,
) -> ListFAQsResponse:
    account = account_service.get_account(session, account_name)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {account_name} does not exist.",
        )
    authorize_user_account(context, account.name)

    faqs = faq_service.get_faqs_by_account_id(session, account.id)
    return ListFAQsResponse(
        faqs=[_builder.build_faq(faq) for faq in faqs],
        total=len(faqs),
    )
