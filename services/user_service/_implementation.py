import os
import uuid
from datetime import datetime
from typing import List, Optional, Tuple

from mixpanel import Mixpanel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

import db as db
from api.schemas.chat.message import Channel, Message
from utils.log import logger


# TODO: get_user_by_channel_identifier in user_service is deprecated, remove it once Streamlit internal_app is replaced with new one
def get_user_by_channel_identifier(
    session: Session,
    account_id: uuid.UUID,
    channel_identifier: str,
    create_new_user: bool = False,
) -> db.User | None:
    user_repository = db.UserRepository(session)
    user = user_repository.get_user_by_channel_identifier(
        account_id=account_id,
        channel_identifier=channel_identifier,
    )

    if user:
        return user

    if create_new_user:
        new_user = user_repository.create_user(
            account_id=account_id, channel_identifier=channel_identifier
        )
        return new_user

    return None


def get_users_by_account_id(
    session: Session,
    account_id: uuid.UUID,
    min_create_time: datetime | None,
) -> List[db.User]:
    user_repository = db.UserRepository(session)
    users = user_repository.get_users_by_account_id(account_id, min_create_time)

    return users


async def get_user_async(
    session: AsyncSession, project: db.Project, message: Message
) -> Tuple[Optional[db.User], bool]:
    user_repo = db.UserRepositoryAsync(session)
    sender_identifier = message.sender_identifier
    channel_identifier = f"{message.channel.value}:{sender_identifier}"
    user = None
    needs_opt_in = False

    # For SMS and VOICE channels, try to find user by either identifier
    if message.channel in [Channel.SMS, Channel.VOICE]:
        # Try to find user with the current channel identifier
        user = await user_repo.get_user_by_channel_identifier(
            account_id=project.account_id, channel_identifier=channel_identifier
        )
        logger.info(f"Looking for user with channel_identifier: {channel_identifier}")

        # If not found, try the other phone-based channel
        if not user:
            other_channel = (
                Channel.VOICE if message.channel == Channel.SMS else Channel.SMS
            )
            other_channel_identifier = f"{other_channel.value}:{sender_identifier}"
            logger.info(
                f"Looking for user with other_channel_identifier: {other_channel_identifier}"
            )
            user = await user_repo.get_user_by_channel_identifier(
                account_id=project.account_id,
                channel_identifier=other_channel_identifier,
            )

            # If found with other channel, add the other channel identifier
            if user:
                logger.info(
                    f"Found user with other channel. Current identifiers: {user.channel_identifiers}"
                )

                # Create a new list with both identifiers
                # The channel_identifiers list has to be updated this way, otherwise the channel_identifier won't be inserted. Need more investigation.
                updated_identifiers = list(user.channel_identifiers or [])
                if channel_identifier not in updated_identifiers:
                    updated_identifiers.append(channel_identifier)
                    logger.info(f"Adding channel_identifier: {channel_identifier}")

                    # Update the user directly in the database
                    try:
                        # Update the user's channel_identifiers
                        user.channel_identifiers = updated_identifiers
                        await session.commit()

                        # Refresh the user to verify the update
                        await session.refresh(user)
                        logger.info(
                            f"Updated user channel identifiers: {user.channel_identifiers}"
                        )
                    except Exception as e:
                        logger.error(f"Error updating user channel identifiers: {e}")
                        await session.rollback()

                # SMS opt-in needed when switching from VOICE to SMS
                if message.channel == Channel.SMS:
                    needs_opt_in = True

        # New SMS users need opt-in
        elif message.channel == Channel.SMS:
            needs_opt_in = True
    else:
        # For other channels, just look for exact match
        user = await user_repo.get_user_by_channel_identifier(
            account_id=project.account_id, channel_identifier=channel_identifier
        )

    return user, needs_opt_in


async def create_user_async(
    session: AsyncSession, project: db.Project, message: Message
) -> db.User:
    user_repo = db.UserRepositoryAsync(session)
    user = await user_repo.create_user(
        project.account_id,
        f"{message.channel.value}:{message.sender_identifier}",
    )
    MIXPANEL_PROJECT_TOKEN = os.getenv("MIXPANEL_PROJECT_TOKEN")
    mp = None
    if MIXPANEL_PROJECT_TOKEN:
        mp = Mixpanel(MIXPANEL_PROJECT_TOKEN)

    user_id = str(user.id)
    await session.refresh(project, attribute_names=["account"])
    account_name = project.account.name

    properties = {
        "account_name": account_name,
        "channel": message.channel.value,
    }
    if mp:
        mp.people_set(user_id, properties)

    return user
