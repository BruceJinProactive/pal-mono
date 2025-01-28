from enum import StrEnum

from agent.framework.phidata import PhiDataAgent


class Framework(StrEnum):
    PHIDATA = "phidata"
    CREWAI = "crewai"
