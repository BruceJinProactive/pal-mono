import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, selectinload

from db.tables import Agent
from utils.log import logger


class AgentRepositoryAsync:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_agent(self, agent_id: uuid.UUID) -> Optional[Agent]:
        result = await self.session.execute(
            select(Agent)
            # [IMPORTANT] The next fixes the following error: 2024-10-21 00:17:10 {"asctime": "2024-10-21 07:17:10,747", "name": "pal-mono", "levelname": "ERROR", "message": "Error in get_chat_response: greenlet_spawn has not been called; can't call await_only() here. Was IO attempted in an unexpected place? (Background on this error at: https://sqlalche.me/e/20/xd2s)"}
            .options(selectinload(Agent.account)).where(Agent.id == agent_id)
        )
        return result.scalars().first()


class AgentRepository:
    def __init__(self, session: Session, auto_commit: bool = True):
        self.session = session
        self.auto_commit = auto_commit

    def get_agents(self, skip: int = 0, limit: int = 100) -> List[Agent]:
        """Retrieve a list of agents with pagination."""
        try:
            return self.session.query(Agent).offset(skip).limit(limit).all()
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving agents: {e}")
            return []

    def get_agent(self, agent_id: uuid.UUID) -> Optional[Agent]:
        """Retrieve a single agent by its ID."""
        try:
            return self.session.query(Agent).filter(Agent.id == agent_id).first()
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving agent: {e}")
            return None

    def create_agent(self, account_id: uuid.UUID, **kwargs) -> Agent:
        """Create a new agent with a unique UUID."""
        try:
            db_agent = Agent(id=uuid.uuid4(), account_id=account_id)
            for key, value in kwargs.items():
                if value is not None and hasattr(db_agent, key):
                    setattr(db_agent, key, value)
            self.session.add(db_agent)

            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()

            self.session.refresh(db_agent)
            return db_agent
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error creating agent: {e}")
            raise

    def update_agent(self, agent_id: uuid.UUID, **kwargs) -> Agent | None:
        """Update an agent's details based on the agent ID and provided fields."""
        try:
            db_agent = self.session.query(Agent).filter(Agent.id == agent_id).first()
            if not db_agent:
                return None
            for key, value in kwargs.items():
                if value is not None and hasattr(db_agent, key):
                    setattr(db_agent, key, value)

            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()

            self.session.refresh(db_agent)
            return db_agent
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error updating agent: {e}")
            raise

    def replace_agent_config(self, agent_id: uuid.UUID, config: Dict[str, Any]) -> None:
        """Replace an agent's config in the database.

        This function replaces the entire `raw_config` for the specified agent.

        Args:
            agent_id (uuid.UUID): The unique identifier of the agent.
            config (Dict[str, Any]): The new `raw_config` to replace the existing one.

        Raises:
            ValueError: If the agent with the given ID is not found.
            SQLAlchemyError: If there is an error committing the transaction to the database.
        """
        try:
            agent = self.get_agent(agent_id)
            if agent is None:
                raise ValueError(f"Agent {agent_id} not found")

            agent.raw_config = config

            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()

        except (SQLAlchemyError, ValueError) as e:
            self.session.rollback()
            logger.error(f"Error replacing agent config: {e}")
            raise

    def delete_agent(self, agent_id: uuid.UUID):
        """
        Delete the referenced agent. No-op if agent id does not exist.
        """
        try:
            agent = self.get_agent(agent_id)
            if agent:
                self.session.delete(agent)
                if self.auto_commit:
                    self.session.commit()
                else:
                    self.session.flush()
        except (SQLAlchemyError, ValueError) as e:
            self.session.rollback()
            logger.error(f"Error deleting agent: {e}")
            raise
