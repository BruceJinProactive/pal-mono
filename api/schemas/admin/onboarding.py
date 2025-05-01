from pydantic import BaseModel

from api.schemas.admin.account import Account, CreateAccountRequest
from api.schemas.admin.agent import Agent, CreateAgentRequest
from api.schemas.admin.project import CreateProjectRequest, Project


class OnboardingAgentProject(BaseModel):
    """Project configuration for an agent during onboarding"""

    agent: CreateAgentRequest
    projects: list[CreateProjectRequest]


class UserInfo(BaseModel):
    """User information for creating Cognito accounts during onboarding"""

    email: str
    name: str


class OnboardingRequest(BaseModel):
    """Onboarding request model for creating account, agents, and projects in a single transaction"""

    account: CreateAccountRequest
    agent_projects: list[OnboardingAgentProject]
    users: list[UserInfo] = []


class OnboardingResponse(BaseModel):
    """Onboarding response model with created IDs"""

    account: Account
    agents: list[Agent] = []
    projects: list[Project] = []
    cognito_users: list[dict] = []
