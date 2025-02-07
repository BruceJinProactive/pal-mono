from typing import Any

from phi.document.base import Document
from phi.knowledge.agent import AgentKnowledge

from . import _config, _implementation

KnowledgeConfig = _config.KnowledgeConfig
KnowledgeProvider = _config.KnowledgeProvider
VectorStoreProvider = _config.VectorStoreProvider
VectorStoreModality = _config.VectorStoreModality

get_knowledge = _implementation.get_knowledge
