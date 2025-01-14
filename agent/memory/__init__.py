from typing import Any

from phi.memory.agent import AgentMemory
from phi.memory.memory import Memory

from agent.config import MemoryConfig

from . import _implementation


def get_memory(config: MemoryConfig) -> AgentMemory:
    return _implementation.get_memory(config)
