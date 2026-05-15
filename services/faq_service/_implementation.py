import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.data_classes.faq import FAQData
from db.pal_repository.faq import FAQRepository


async def create_faq(
    session: AsyncSession,
    account_id: uuid.UUID,
    question: str,
    answer: str,
    project_id: uuid.UUID | None = None,
) -> FAQData:
    faq_repository = FAQRepository(session)
    record = FAQData(
        id=uuid.uuid4(),
        account_id=account_id,
        project_id=project_id,
        question=question,
        answer=answer,
        created_at=datetime.now(UTC),
    )
    return await faq_repository.create(record)


async def get_faq_by_id(session: AsyncSession, faq_id: uuid.UUID) -> FAQData | None:
    faq_repository = FAQRepository(session)
    return await faq_repository.get_by_id(faq_id)


async def get_faqs_by_account_id(
    session: AsyncSession, account_id: uuid.UUID, project_id: uuid.UUID | None = None
) -> list[FAQData]:
    faq_repository = FAQRepository(session)
    return await faq_repository.get_by_account_id(account_id, project_id)


async def update_faq(
    session: AsyncSession, faq_id: uuid.UUID, updates: dict[str, object]
) -> FAQData | None:
    faq_repository = FAQRepository(session)
    return await faq_repository.update(faq_id, **updates)


async def delete_faq(session: AsyncSession, faq_id: uuid.UUID) -> bool:
    faq_repository = FAQRepository(session)
    return await faq_repository.delete(faq_id)
