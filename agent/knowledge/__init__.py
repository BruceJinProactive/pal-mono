from typing import Any

from agno.document.base import Document
from agno.knowledge.agent import AgentKnowledge

from . import _config, _implementation

# General knowledge configs
KnowledgeConfig = _config.KnowledgeConfig
KnowledgeProvider = _config.KnowledgeProvider

### Provider specific configs ###
LlamaIndexSettings = _config.LlamaIndexSettings

# Vector store configs
VectorStoreProvider = _config.VectorStoreProvider
VectorStoreModality = _config.VectorStoreModality


get_knowledge = _implementation.get_knowledge
