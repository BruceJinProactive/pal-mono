import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.data_classes.faq import FAQData
from services.faq_service import _implementation as faq_service


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def sample_faq_data() -> FAQData:
    return FAQData(
        id=uuid.uuid4(),
        account_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        question="What are your hours?",
        answer="9am to 5pm",
        created_at=datetime(2026, 5, 14, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_create_faq_builds_data_and_calls_repository(
    mock_session: AsyncMock,
    sample_faq_data: FAQData,
) -> None:
    account_id = uuid.uuid4()
    project_id = uuid.uuid4()
    mock_repo = MagicMock()
    mock_repo.create = AsyncMock(return_value=sample_faq_data)

    with patch(
        "services.faq_service._implementation.FAQRepository",
        return_value=mock_repo,
    ) as mock_repo_cls:
        result = await faq_service.create_faq(
            mock_session,
            account_id=account_id,
            project_id=project_id,
            question="What are your hours?",
            answer="9am to 5pm",
        )

    assert result == sample_faq_data
    mock_repo_cls.assert_called_once_with(mock_session)
    mock_repo.create.assert_awaited_once()
    record = mock_repo.create.await_args.args[0]
    assert isinstance(record, FAQData)
    assert record.account_id == account_id
    assert record.project_id == project_id
    assert record.question == "What are your hours?"
    assert record.answer == "9am to 5pm"


@pytest.mark.asyncio
async def test_get_faq_by_id_calls_repository(
    mock_session: AsyncMock,
    sample_faq_data: FAQData,
) -> None:
    faq_id = uuid.uuid4()
    mock_repo = MagicMock()
    mock_repo.get_by_id = AsyncMock(return_value=sample_faq_data)

    with patch(
        "services.faq_service._implementation.FAQRepository",
        return_value=mock_repo,
    ):
        result = await faq_service.get_faq_by_id(mock_session, faq_id)

    assert result == sample_faq_data
    mock_repo.get_by_id.assert_awaited_once_with(faq_id)


@pytest.mark.asyncio
async def test_get_faqs_by_account_id_calls_repository(
    mock_session: AsyncMock,
    sample_faq_data: FAQData,
) -> None:
    account_id = uuid.uuid4()
    project_id = uuid.uuid4()
    mock_repo = MagicMock()
    mock_repo.get_by_account_id = AsyncMock(return_value=[sample_faq_data])

    with patch(
        "services.faq_service._implementation.FAQRepository",
        return_value=mock_repo,
    ):
        result = await faq_service.get_faqs_by_account_id(
            mock_session, account_id, project_id
        )

    assert result == [sample_faq_data]
    mock_repo.get_by_account_id.assert_awaited_once_with(account_id, project_id)


@pytest.mark.asyncio
async def test_update_faq_calls_repository(
    mock_session: AsyncMock,
    sample_faq_data: FAQData,
) -> None:
    faq_id = uuid.uuid4()
    updates: dict[str, object] = {"question": "Updated?", "project_id": None}
    mock_repo = MagicMock()
    mock_repo.update = AsyncMock(return_value=sample_faq_data)

    with patch(
        "services.faq_service._implementation.FAQRepository",
        return_value=mock_repo,
    ):
        result = await faq_service.update_faq(mock_session, faq_id, updates)

    assert result == sample_faq_data
    mock_repo.update.assert_awaited_once_with(faq_id, **updates)


@pytest.mark.asyncio
async def test_delete_faq_calls_repository(mock_session: AsyncMock) -> None:
    faq_id = uuid.uuid4()
    mock_repo = MagicMock()
    mock_repo.delete = AsyncMock(return_value=True)

    with patch(
        "services.faq_service._implementation.FAQRepository",
        return_value=mock_repo,
    ):
        result = await faq_service.delete_faq(mock_session, faq_id)

    assert result is True
    mock_repo.delete.assert_awaited_once_with(faq_id)
