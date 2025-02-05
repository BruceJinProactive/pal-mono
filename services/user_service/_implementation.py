import uuid
from typing import List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

import db as db
from api.schemas.chat.message import Channel, Message


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
) -> List[db.User]:
    user_repository = db.UserRepository(session)
    users = user_repository.get_users_by_account_id(account_id=account_id)

    return users


async def get_user_async(
    session: AsyncSession, project: db.Project, message: Message
) -> Tuple[Optional[db.User], bool]:
    user_repo = db.UserRepositoryAsync(session)
    user = None

    sender_identifier = message.sender_identifier
    new_channel_identifier = f"{message.channel.value}:{sender_identifier}"

    # Treat SMS and VOICE channels as the same user
    if message.channel == Channel.SMS or message.channel == Channel.VOICE:
        # Check for existing user with SMS or VOICE channel identifier
        sms_channel_identifier = f"{Channel.SMS.value}:{sender_identifier}"
        voice_channel_identifier = f"{Channel.VOICE.value}:{sender_identifier}"

        user_sms = await user_repo.get_user_by_channel_identifier(
            account_id=project.account_id,
            channel_identifier=sms_channel_identifier,
        )
        user_voice = await user_repo.get_user_by_channel_identifier(
            account_id=project.account_id,
            channel_identifier=voice_channel_identifier,
        )

        # Determine if user exists
        user = user_sms or user_voice

        # If current channel is SMS
        if message.channel == Channel.SMS:
            if user_voice and not user_sms:
                # If VOICE already exists for the user and SMS doesn't, add SMS to the user channel identifiers
                if (
                    user_voice.channel_identifiers
                    and new_channel_identifier not in user_voice.channel_identifiers
                ):
                    user_voice.channel_identifiers.append(new_channel_identifier)
                    await session.commit()
                    return user_voice, True  # Indicate that opt-in message is needed
            elif not user:
                # User is SMS, Indicate that opt-in message is needed
                return user, True
        # If current channel is VOICE
        elif message.channel == Channel.VOICE:
            if user_sms and not user_voice:
                # If SMS already exists for the user but VOICE doesn't, add VOICE to the user channel identifiers
                if (
                    user_sms.channel_identifiers
                    and new_channel_identifier not in user_sms.channel_identifiers
                ):
                    user_sms.channel_identifiers.append(new_channel_identifier)
                    await session.commit()
                return user_sms, False

    else:
        # Check for existing user with the given channel identifier
        user = await user_repo.get_user_by_channel_identifier(
            account_id=project.account_id,
            channel_identifier=new_channel_identifier,
        )

    return user, False
