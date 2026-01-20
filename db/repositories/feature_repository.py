import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.exc import TimeoutError as DBTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from db.tables import Feature
from db.tables.types import IdentifierType
from utils.log import logger


class FeatureRepositoryAsync:
    """Repository for managing feature flags in the gatekeeper service."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def check_enablement(
        self,
        feature: str,
        identifier_type: IdentifierType,
        identifier: str,
    ) -> bool:
        """
        Check if a feature is enabled for a specific identifier.

        Args:
            feature: The feature name to check
            identifier_type: The type of identifier (agent, account, project, user)
            identifier: The identifier value (UUID or string ID)

        Returns:
            bool: True if the feature is enabled, False otherwise (including if not found)
        """
        try:
            result = await self.session.execute(
                select(Feature.enabled).where(
                    Feature.feature == feature,
                    Feature.identifier_type == identifier_type,
                    Feature.identifier == identifier,
                )
            )
            enabled = result.scalar_one_or_none()
            return enabled if enabled is not None else False
        except DBTimeoutError as e:
            # Pool exhaustion/timeout errors must propagate for proper cleanup
            logger.error(
                f"Connection pool timeout checking feature {feature}/{identifier_type}/{identifier}: {e}"
            )
            raise
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(
                f"Error checking feature enablement for {feature}/{identifier_type}/{identifier}: {e}"
            )
            return False

    async def upsert(
        self,
        feature: str,
        identifier_type: IdentifierType,
        identifier: str,
        enabled: bool,
    ) -> Optional[Feature]:
        """
        Create or update a feature flag entry.

        Args:
            feature: The feature name
            identifier_type: The type of identifier (agent, account, project, user)
            identifier: The identifier value (UUID or string ID)
            enabled: Whether the feature should be enabled

        Returns:
            Feature: The created or updated feature entry, or None if operation failed
        """
        try:
            # First, try to get the existing feature
            result = await self.session.execute(
                select(Feature).where(
                    Feature.feature == feature,
                    Feature.identifier_type == identifier_type,
                    Feature.identifier == identifier,
                )
            )
            existing_feature = result.scalar_one_or_none()

            if existing_feature:
                # Update existing feature
                existing_feature.enabled = enabled
                await self.session.commit()
                await self.session.refresh(existing_feature)
                return existing_feature
            else:
                # Create new feature
                new_feature = Feature(
                    id=uuid.uuid4(),
                    feature=feature,
                    identifier_type=identifier_type,
                    identifier=identifier,
                    enabled=enabled,
                )
                self.session.add(new_feature)
                await self.session.commit()
                await self.session.refresh(new_feature)
                return new_feature

        except DBTimeoutError as e:
            # Pool exhaustion/timeout errors must propagate for proper cleanup
            logger.error(
                f"Connection pool timeout upserting feature {feature}/{identifier_type}/{identifier}: {e}"
            )
            raise
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(
                f"Error upserting feature {feature}/{identifier_type}/{identifier}: {e}"
            )
            return None
