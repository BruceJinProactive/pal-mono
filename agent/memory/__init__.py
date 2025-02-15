from typing import Any

from agno.memory.agent import AgentMemory
from agno.memory.memory import Memory

from . import _config, _implementation

MemoryConfig = _config.MemoryConfig
MemoryProvider = _config.MemoryProvider

update_memory = _implementation.update_memory
get_memory_context = _implementation.get_memory_context
