from typing import Optional

from pydantic import BaseModel, Field

from api.schemas.admin.account import CreateAccountRequest
from api.schemas.admin.agent import CreateAgentRequest
from api.schemas.admin.project import CreateProjectRequest


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


class GenerateAgentPromptsRequest(BaseModel):
    """Request model for generating agent prompts"""

    restaurant_name: str = Field(..., description="Name of the restaurant")
    agent_name: str = Field(default="", description="Name of the agent")
    agent_type: str = Field(
        default="general", description="Type of agent: 'general' or 'ordering'"
    )
    keywords: str = Field(..., description="Personality keywords for the agent")
    specific_instructions: Optional[str] = Field(
        default="", description="Specific instructions for the agent"
    )
    menu_content: Optional[str] = Field(
        default="", description="Menu content for the restaurant"
    )
    additional_urls: Optional[list[str]] = Field(
        default=[], description="Additional URLs to scrape for context"
    )


class GenerateAgentPromptsResponse(BaseModel):
    """Response model for generated agent prompts"""

    persona: str = Field(..., description="Agent persona and voice guidelines")
    interaction_guidelines: str = Field(
        ..., description="Interaction workflows and examples"
    )
