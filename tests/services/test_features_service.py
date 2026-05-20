import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.data_classes.feature import FeatureData
from db.tables.types import IdentifierType
from services.features_service import _implementation as features_service


@pytest.fixture(autouse=True)
def clear_feature_cache() -> None:
    features_service._feature_cache.clear()


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def sample_feature_data() -> FeatureData:
    return FeatureData(
        id=uuid.uuid4(),
        feature="dark_mode",
        identifier_type="account",
        identifier="acct_123",
        enabled=True,
        created_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
        updated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_check_feature_enabled_uses_pal_repository(
    mock_session: AsyncMock,
) -> None:
    mock_repo = MagicMock()
    mock_repo.check_enablement = AsyncMock(return_value=True)

    with patch(
        "services.features_service._implementation.FeatureRepository",
        return_value=mock_repo,
    ) as mock_repo_cls:
        result = await features_service.check_feature_enabled(
            mock_session,
            feature="dark_mode",
            identifier_type=IdentifierType.account,
            identifier="acct_123",
        )

    assert result is True
    mock_repo_cls.assert_called_once_with(mock_session)
    mock_repo.check_enablement.assert_awaited_once_with(
        feature="dark_mode",
        identifier_type="account",
        identifier="acct_123",
    )


@pytest.mark.asyncio
async def test_check_feature_enabled_uses_cached_value(
    mock_session: AsyncMock,
) -> None:
    cache_key = ("dark_mode", IdentifierType.account, "acct_123")
    features_service._set_cached(cache_key, True)

    with patch(
        "services.features_service._implementation.FeatureRepository"
    ) as mock_repo_cls:
        result = await features_service.check_feature_enabled(
            mock_session,
            feature="dark_mode",
            identifier_type=IdentifierType.account,
            identifier="acct_123",
        )

    assert result is True
    mock_repo_cls.assert_not_called()


@pytest.mark.asyncio
async def test_check_feature_enabled_defaults_false_on_error(
    mock_session: AsyncMock,
) -> None:
    mock_repo = MagicMock()
    mock_repo.check_enablement = AsyncMock(side_effect=RuntimeError("db error"))

    with patch(
        "services.features_service._implementation.FeatureRepository",
        return_value=mock_repo,
    ):
        result = await features_service.check_feature_enabled(
            mock_session,
            feature="dark_mode",
            identifier_type=IdentifierType.account,
            identifier="acct_123",
        )

    assert result is False


@pytest.mark.asyncio
async def test_upsert_feature_uses_pal_repository(
    mock_session: AsyncMock,
    sample_feature_data: FeatureData,
) -> None:
    features_service._set_cached(
        ("dark_mode", IdentifierType.account, "acct_123"), True
    )
    mock_repo = MagicMock()
    mock_repo.upsert = AsyncMock(return_value=sample_feature_data)

    with patch(
        "services.features_service._implementation.FeatureRepository",
        return_value=mock_repo,
    ) as mock_repo_cls:
        result = await features_service.upsert_feature(
            mock_session,
            feature="dark_mode",
            identifier_type=IdentifierType.account,
            identifier="acct_123",
            enabled=False,
        )

    assert result == sample_feature_data
    assert ("dark_mode", IdentifierType.account, "acct_123") not in (
        features_service._feature_cache
    )
    mock_repo_cls.assert_called_once_with(mock_session)
    mock_repo.upsert.assert_awaited_once_with(
        feature="dark_mode",
        identifier_type="account",
        identifier="acct_123",
        enabled=False,
    )


@pytest.mark.asyncio
async def test_upsert_feature_returns_none_on_error(mock_session: AsyncMock) -> None:
    mock_repo = MagicMock()
    mock_repo.upsert = AsyncMock(side_effect=RuntimeError("db error"))

    with patch(
        "services.features_service._implementation.FeatureRepository",
        return_value=mock_repo,
    ):
        result = await features_service.upsert_feature(
            mock_session,
            feature="dark_mode",
            identifier_type=IdentifierType.account,
            identifier="acct_123",
            enabled=True,
        )

    assert result is None
