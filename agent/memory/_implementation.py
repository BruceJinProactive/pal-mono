from phi.memory.agent import AgentMemory
from phi.memory.classifier import MemoryClassifier
from phi.memory.db.postgres import PgMemoryDb
from phi.model.message import Message

import db
from agent.model import ModelName, get_model
from utils.log import logger

from . import _config


def get_memory(config: _config.MemoryConfig) -> AgentMemory:
    memory_table_name = f"{config.identifier}_memory"
    memory = AgentMemory(
        db=PgMemoryDb(
            db_url=db.db_url,
            table_name=memory_table_name,
        ),
        create_user_memories=True,
    )

    # Set the memory classifier
    if config.instruction:
        memory.classifier = CustomMemoryClassifier(instruction=config.instruction)

    return memory


class CustomMemoryClassifier(MemoryClassifier):
    instruction: str = ""

    # Overridden to utilize our model router
    def update_model(self) -> None:
        if self.model is None:
            self.model = get_model(model_name=ModelName.MEDIUM, stream=False)

    # Inject memory instruction
    # TODO: Not working well now, need prompt engineering
    def get_system_message(self) -> Message:
        original_message = super().get_system_message()
        message_content = original_message.get_content_string() + self.instruction
        original_message.content = message_content
        logger.info(f"System message: {message_content}")
        return original_message
