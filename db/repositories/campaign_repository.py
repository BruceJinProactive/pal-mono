import uuid

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from db import Campaign, CampaignMessage
from utils.log import logger


class CampaignRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_campaign(self, campaign: Campaign) -> Campaign:
        try:
            self.session.add(campaign)
            self.session.commit()
            self.session.refresh(campaign)
            return campaign
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error creating campaign: {e}")
            raise

    def get_campaign(self, campaign_id: uuid.UUID) -> Campaign | None:
        try:
            return (
                self.session.query(Campaign).filter(Campaign.id == campaign_id).first()
            )
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving campaign: {e}")
            return None

    def get_campaigns_by_account_id(self, account_id: uuid.UUID) -> list[Campaign]:
        try:
            return (
                self.session.query(Campaign)
                .filter(Campaign.account_id == account_id)
                .all()
            )
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving campaigns by account: {e}")
            return []


class CampaignMessageRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_campaign_message(self, message: CampaignMessage) -> CampaignMessage:
        try:
            self.session.add(message)
            self.session.commit()
            self.session.refresh(message)
            return message
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error creating campaign message: {e}")
            raise

    def get_campaign_message(self, message_id: uuid.UUID) -> CampaignMessage | None:
        try:
            return (
                self.session.query(CampaignMessage)
                .filter(CampaignMessage.id == message_id)
                .first()
            )
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving campaign: {e}")
            return None
