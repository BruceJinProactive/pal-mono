import uuid

from sqlalchemy import func, select
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

    def get_campaigns_by_account_id(
        self, account_id: uuid.UUID, skip: int = 0, limit: int = 20
    ) -> tuple[list[Campaign], int]:
        try:
            query = self.session.query(Campaign).filter(
                Campaign.account_id == account_id
            )
            total = query.count()
            campaigns = (
                query.order_by(Campaign.created_at.desc())
                .offset(skip)
                .limit(limit)
                .all()
            )
            return campaigns, total
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(
                f"Error retrieving campaigns by account: {e}",
                extra={"account_id": account_id},
            )
            return [], 0

    def get_campaign_recipients(self, campaign_id: uuid.UUID) -> list[str]:
        """
        Returns a list of all campaign recipients
        """
        try:
            query = select(CampaignMessage.recipient).filter(
                CampaignMessage.campaign_id == campaign_id
            )
            result = self.session.execute(query)
            recipients = [str(r) for r in result.scalars().all()]
            return recipients
        except SQLAlchemyError as e:
            logger.error(
                f"Error fetching campaign recipients: {e}",
                extra={"campaign_id": campaign_id},
            )
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

    def update_campaign_message(self, message: CampaignMessage) -> CampaignMessage:
        try:
            self.session.add(message)
            self.session.commit()
            return message
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(
                f"Error updating campaign message: {e}",
                extra={"message_id": message.id},
            )
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
            logger.error(
                f"Error retrieving campaign message: {e}",
                extra={"message_id": message_id},
            )
            return None

    def get_message_status_counts_for_campaign(self, campaign_id: uuid.UUID):
        """
        Returns a map of status value and their corresponding counts.
        """
        try:
            return (
                self.session.query(
                    CampaignMessage.status,
                    func.count(CampaignMessage.id).label("count"),
                )
                .filter(CampaignMessage.campaign_id == campaign_id)
                .group_by(CampaignMessage.status)
                .all()
            )
        except SQLAlchemyError as e:
            logger.error(
                f"Error computing message status counts: {e}",
                extra={"campaign_id": campaign_id},
            )
            return None
