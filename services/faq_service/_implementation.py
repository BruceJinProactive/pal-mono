from uuid import UUID

from sqlalchemy.orm import Session

import db


def create_faq(session: Session, faq: db.FAQ) -> db.FAQ:
    faq_repository = db.FAQRepository(session)
    return faq_repository.create_faq(faq)


def get_faq_by_id(session: Session, faq_id: UUID) -> db.FAQ | None:
    faq_repository = db.FAQRepository(session)
    return faq_repository.get_faq_by_id(faq_id)


def get_faqs_by_account_id(session: Session, account_id: UUID) -> list[db.FAQ]:
    faq_repository = db.FAQRepository(session)
    return faq_repository.get_faqs_by_account_id(account_id)


def update_faq(session: Session, faq_id: UUID, updates: dict) -> db.FAQ | None:
    faq_repository = db.FAQRepository(session)
    return faq_repository.update_faq(faq_id, updates)
