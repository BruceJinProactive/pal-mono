from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from api.schemas.admin.account import (
    Account,
    CreateAccountRequest,
    ListAccountsResponse,
    UpdateAccountRequest,
)
from services import account_service

from ._builder import build_account
from ._utils import UserContext


def list_accounts(context: UserContext, session: Session) -> ListAccountsResponse:
    accounts = account_service.mget_accounts(
        session, account_names=context.account_names
    )
    response = ListAccountsResponse(
        accounts=[build_account(account) for account in accounts]
    )
    return response


async def create_account(request: Request, session: Session) -> Account:
    account_data = await request.json()
    create_request = CreateAccountRequest(**account_data)
    account_params = account_service.AccountParams(
        display_name=create_request.display_name,
        icon_uri=create_request.icon_uri,
        business_description=create_request.business_description,
        business_faq=create_request.business_faq,
        business_promotions=create_request.business_promotions,
        business_catalog=create_request.business_catalog,
        business_others=create_request.business_others,
    )
    try:
        db_account = account_service.create_account(
            session, create_request.name, account_params
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
            headers={"Content-Type": "application/json"},
        )
    return build_account(db_account)


async def update_account(
    request: Request, account_name: str, session: Session
) -> Account:
    account_data = await request.json()
    update_request = UpdateAccountRequest(**account_data)
    account_params = account_service.AccountParams(
        display_name=update_request.display_name,
        icon_uri=update_request.icon_uri,
        business_description=update_request.business_description,
        business_faq=update_request.business_faq,
        business_promotions=update_request.business_promotions,
        business_catalog=update_request.business_catalog,
        business_others=update_request.business_others,
    )
    try:
        db_account = account_service.update_account(
            session, account_name, account_params
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
            headers={"Content-Type": "application/json"},
        )
    return build_account(db_account)
