import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.routes.admin import _faq
from api.schemas.admin.faq import FAQ, CreateFAQRequest, UpdateFAQRequest
from db.pal_repository.data_classes.faq import FAQData
from services.auth_types import UserContext, UserRole


@pytest.fixture
def mock_context() -> UserContext:
    return UserContext(
        username=str(uuid.uuid4()),
        email="test@example.com",
        groups=[],
        display_name="Test User",
        role=UserRole.Admin,
    )


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def account() -> MagicMock:
    mock_account = MagicMock()
    mock_account.id = uuid.uuid4()
    return mock_account


@pytest.fixture
def faq_data(account: MagicMock) -> FAQData:
    return FAQData(
        id=uuid.uuid4(),
        account_id=account.id,
        project_id=uuid.uuid4(),
        question="What are your hours?",
        answer="9am to 5pm",
        created_at=datetime(2026, 5, 14, tzinfo=timezone.utc),
    )


@pytest.fixture
def faq_response(faq_data: FAQData) -> FAQ:
    return FAQ(
        id=str(faq_data.id),
        account_id=str(faq_data.account_id),
        project_id=str(faq_data.project_id),
        question=faq_data.question,
        answer=faq_data.answer,
        created_at=faq_data.created_at.isoformat(),
        updated_at=faq_data.created_at.isoformat(),
    )


@pytest.mark.asyncio
async def test_create_faq_success(
    mock_context: UserContext,
    mock_session: AsyncMock,
    account: MagicMock,
    faq_data: FAQData,
    faq_response: FAQ,
) -> None:
    request = CreateFAQRequest(
        question="What are your hours?",
        answer="9am to 5pm",
        project_id=str(faq_data.project_id),
    )

    with (
        patch(
            "api.routes.admin._faq.account_service.get_account_async",
            new_callable=AsyncMock,
            return_value=account,
        ),
        patch(
            "api.routes.admin._faq.faq_service.create_faq",
            new_callable=AsyncMock,
            return_value=faq_data,
        ) as mock_create,
        patch("api.routes.admin._faq._builder.build_faq", return_value=faq_response),
    ):
        result = await _faq.create_faq(
            "test-account", request, mock_context, mock_session
        )

    assert result == faq_response
    mock_create.assert_awaited_once_with(
        mock_session,
        account_id=account.id,
        project_id=faq_data.project_id,
        question="What are your hours?",
        answer="9am to 5pm",
    )


@pytest.mark.asyncio
async def test_get_faqs_success(
    mock_context: UserContext,
    mock_session: AsyncMock,
    account: MagicMock,
    faq_data: FAQData,
    faq_response: FAQ,
) -> None:
    with (
        patch(
            "api.routes.admin._faq.account_service.get_account_async",
            new_callable=AsyncMock,
            return_value=account,
        ),
        patch(
            "api.routes.admin._faq.faq_service.get_faqs_by_account_id",
            new_callable=AsyncMock,
            return_value=[faq_data],
        ) as mock_list,
        patch("api.routes.admin._faq._builder.build_faq", return_value=faq_response),
    ):
        result = await _faq.get_faqs(
            "test-account",
            mock_context,
            mock_session,
            project_id=str(faq_data.project_id),
        )

    assert result.faqs == [faq_response]
    assert result.total == 1
    mock_list.assert_awaited_once_with(mock_session, account.id, faq_data.project_id)


@pytest.mark.asyncio
async def test_update_faq_success_converts_project_id(
    mock_context: UserContext,
    mock_session: AsyncMock,
    account: MagicMock,
    faq_data: FAQData,
    faq_response: FAQ,
) -> None:
    new_project_id = uuid.uuid4()
    request = UpdateFAQRequest(question="Updated?", project_id=str(new_project_id))

    with (
        patch(
            "api.routes.admin._faq.account_service.get_account_async",
            new_callable=AsyncMock,
            return_value=account,
        ),
        patch(
            "api.routes.admin._faq.faq_service.get_faq_by_id",
            new_callable=AsyncMock,
            return_value=faq_data,
        ),
        patch(
            "api.routes.admin._faq.faq_service.update_faq",
            new_callable=AsyncMock,
            return_value=faq_data,
        ) as mock_update,
        patch("api.routes.admin._faq._builder.build_faq", return_value=faq_response),
    ):
        result = await _faq.update_faq(
            "test-account", faq_data.id, request, mock_context, mock_session
        )

    assert result == faq_response
    mock_update.assert_awaited_once_with(
        mock_session,
        faq_data.id,
        {"question": "Updated?", "project_id": new_project_id},
    )


@pytest.mark.asyncio
async def test_delete_faq_success(
    mock_context: UserContext,
    mock_session: AsyncMock,
    account: MagicMock,
    faq_data: FAQData,
) -> None:
    with (
        patch(
            "api.routes.admin._faq.account_service.get_account_async",
            new_callable=AsyncMock,
            return_value=account,
        ),
        patch(
            "api.routes.admin._faq.faq_service.get_faq_by_id",
            new_callable=AsyncMock,
            return_value=faq_data,
        ),
        patch(
            "api.routes.admin._faq.faq_service.delete_faq",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_delete,
    ):
        await _faq.delete_faq("test-account", faq_data.id, mock_context, mock_session)

    mock_delete.assert_awaited_once_with(mock_session, faq_data.id)


@pytest.mark.asyncio
async def test_create_faq_raises_when_account_missing(
    mock_context: UserContext,
    mock_session: AsyncMock,
) -> None:
    request = CreateFAQRequest(question="Q?", answer="A")

    with patch(
        "api.routes.admin._faq.account_service.get_account_async",
        new_callable=AsyncMock,
        return_value=None,
    ):
        with pytest.raises(HTTPException) as exc_info:
            await _faq.create_faq("missing", request, mock_context, mock_session)

    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_update_faq_raises_when_existing_faq_missing(
    mock_context: UserContext,
    mock_session: AsyncMock,
    account: MagicMock,
) -> None:
    faq_id = uuid.uuid4()
    request = UpdateFAQRequest(question="Updated?")

    with (
        patch(
            "api.routes.admin._faq.account_service.get_account_async",
            new_callable=AsyncMock,
            return_value=account,
        ),
        patch(
            "api.routes.admin._faq.faq_service.get_faq_by_id",
            new_callable=AsyncMock,
            return_value=None,
        ),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await _faq.update_faq(
                "test-account", faq_id, request, mock_context, mock_session
            )

    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_delete_faq_raises_when_delete_fails(
    mock_context: UserContext,
    mock_session: AsyncMock,
    account: MagicMock,
    faq_data: FAQData,
) -> None:
    with (
        patch(
            "api.routes.admin._faq.account_service.get_account_async",
            new_callable=AsyncMock,
            return_value=account,
        ),
        patch(
            "api.routes.admin._faq.faq_service.get_faq_by_id",
            new_callable=AsyncMock,
            return_value=faq_data,
        ),
        patch(
            "api.routes.admin._faq.faq_service.delete_faq",
            new_callable=AsyncMock,
            return_value=False,
        ),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await _faq.delete_faq(
                "test-account", faq_data.id, mock_context, mock_session
            )

    assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
