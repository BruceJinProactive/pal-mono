from typing import Any

from phi.document.base import Document
from phi.knowledge.agent import AgentKnowledge

from agent.config import KnowledgeConfig

from . import _implementation


def get_knowledge(config: KnowledgeConfig) -> AgentKnowledge:
    return _implementation.get_knowledge(config)
