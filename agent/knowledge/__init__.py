from typing import Any

from agno.document.base import Document
from agno.knowledge.agent import AgentKnowledge

from . import _config, _implementation

KnowledgeConfig = _config.KnowledgeConfig
KnowledgeProvider = _config.KnowledgeProvider
VectorStoreProvider = _config.VectorStoreProvider
VectorStoreModality = _config.VectorStoreModality

get_knowledge = _implementation.get_knowledge
