"""Tests for the sync order repository."""

import uuid
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from db.repositories.order_repository import OrderRepository
from db.tables.types import IntegrationProvider


def _session_with_idempotency_lookup(
    *lookup_results: object | None,
) -> tuple[MagicMock, MagicMock]:
    """Create a mock session whose order idempotency lookup returns values."""
    session = MagicMock()
    filter_result = MagicMock()
    if len(lookup_results) == 1:
        filter_result.first.return_value = lookup_results[0]
    else:
        filter_result.first.side_effect = list(lookup_results)

    query = MagicMock()
    query.filter.return_value = filter_result
    session.query.return_value = query
    return session, filter_result


class TestOrderIdempotencyKey:
    def test_builds_key_from_external_order_identity(self) -> None:
        key = OrderRepository.build_external_idempotency_key(
            vendor=IntegrationProvider.adora,
            store_id=" STORE-1 ",
            order_id=" ORDER-123 ",
        )

        assert key == "order:external:v1:adora:STORE-1:ORDER-123"

    def test_escapes_key_separators_inside_external_identifiers(self) -> None:
        key = OrderRepository.build_external_idempotency_key(
            vendor=IntegrationProvider.toast,
            store_id=r"STORE:1\A",
            order_id=r"ORDER:123\B",
        )

        assert key == r"order:external:v1:toast:STORE\:1\\A:ORDER\:123\\B"

    @pytest.mark.parametrize(
        ("vendor", "store_id", "order_id"),
        [
            (None, "STORE-1", "ORDER-123"),
            (IntegrationProvider.adora, None, "ORDER-123"),
            (IntegrationProvider.adora, "STORE-1", None),
            (IntegrationProvider.adora, "   ", "ORDER-123"),
            (IntegrationProvider.adora, "STORE-1", "   "),
        ],
    )
    def test_returns_none_when_external_identity_is_incomplete(
        self,
        vendor: IntegrationProvider | None,
        store_id: str | None,
        order_id: str | None,
    ) -> None:
        key = OrderRepository.build_external_idempotency_key(
            vendor=vendor,
            store_id=store_id,
            order_id=order_id,
        )

        assert key is None


class TestCreateOrderIdempotency:
    def test_returns_existing_order_for_external_identity(self) -> None:
        existing_order = MagicMock()
        session, _ = _session_with_idempotency_lookup(existing_order)
        repository = OrderRepository(session)

        result = repository.create_order(
            conversation_id=uuid.uuid4(),
            vendor=IntegrationProvider.adora,
            order_id="ORDER-123",
            store_id="STORE-1",
        )

        assert result is existing_order
        session.add.assert_not_called()
        session.commit.assert_not_called()

    def test_inserts_external_order_with_idempotency_key(self) -> None:
        session, _ = _session_with_idempotency_lookup(None)
        repository = OrderRepository(session)

        order = repository.create_order(
            conversation_id=uuid.uuid4(),
            vendor=IntegrationProvider.adora,
            order_id="ORDER-123",
            store_id="STORE-1",
        )

        assert order.idempotency_key == "order:external:v1:adora:STORE-1:ORDER-123"
        session.begin_nested.assert_called_once()
        session.add.assert_called_once_with(order)
        session.flush.assert_called_once()
        session.commit.assert_called_once()

    def test_returns_existing_order_after_unique_conflict(self) -> None:
        existing_order = MagicMock()
        session, _ = _session_with_idempotency_lookup(None, existing_order)
        session.flush.side_effect = IntegrityError(
            statement="INSERT INTO orders",
            params={},
            orig=Exception("duplicate key"),
        )
        session.begin_nested.return_value.__exit__.return_value = False
        repository = OrderRepository(session)

        result = repository.create_order(
            conversation_id=uuid.uuid4(),
            vendor=IntegrationProvider.adora,
            order_id="ORDER-123",
            store_id="STORE-1",
        )

        assert result is existing_order
        session.add.assert_called_once()
        session.flush.assert_called_once()
        session.commit.assert_not_called()

    def test_inserts_order_without_idempotency_when_external_identity_missing(
        self,
    ) -> None:
        session = MagicMock()
        repository = OrderRepository(session)

        order = repository.create_order(
            conversation_id=uuid.uuid4(),
            vendor=IntegrationProvider.adora,
            order_id=None,
            store_id="STORE-1",
        )

        assert order.idempotency_key is None
        session.query.assert_not_called()
        session.begin_nested.assert_not_called()
        session.add.assert_called_once_with(order)
        session.commit.assert_called_once()
