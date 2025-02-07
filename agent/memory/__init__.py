from typing import Any

from phi.memory.agent import AgentMemory
from phi.memory.memory import Memory

from . import _config, _implementation

MemoryConfig = _config.MemoryConfig
MemoryProvider = _config.MemoryProvider

get_memory = _implementation.get_memory
