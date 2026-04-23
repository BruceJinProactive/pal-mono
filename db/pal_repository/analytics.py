from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession


class AnalyticsRepository:
    """Async-only repository for analytics aggregation queries.

    Analytics queries return result-row DTOs defined in
    db.pal_repository.data_classes.analytics. These are aggregation
    queries — no ORM entity mapping is used.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
