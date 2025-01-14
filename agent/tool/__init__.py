from typing import List

from phi.tools.toolkit import Toolkit
from pydantic import BaseModel, Field, create_model

from agent.config import ToolConfig

from . import _implementation


def get_tools(config: ToolConfig) -> List[Toolkit]:
    return _implementation.get_tools(config)
