from enum import Enum

from agent.framework.phidata import PhiDataAgent


class Framework(str, Enum):
    PHIDATA = "phidata"
    CREWAI = "crewai"
