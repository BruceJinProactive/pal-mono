from fastapi import HTTPException, status
from sqlalchemy.orm import Session

import db
from api.schemas.admin.faq import FAQ, CreateFAQRequest
from services import account_service, faq_service

from . import UserContext, _builder
from ._auth import authorize_user_account


async def create_faq(
    faq_create: CreateFAQRequest,
    context: UserContext,
    session: Session,
) -> FAQ:
    account = account_service.get_account_by_id(session, faq_create.account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {faq_create.account_id} does not exist.",
        )
    authorize_user_account(context, account.name)

    faq = db.FAQ(
        account_id=faq_create.account_id,
        question=faq_create.question,
        answer=faq_create.answer,
    )
    persisted_faq = faq_service.create_faq(session, faq)
    return _builder.build_faq(persisted_faq)
