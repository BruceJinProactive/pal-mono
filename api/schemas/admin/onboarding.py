from typing import Optional

from pydantic import BaseModel, Field

from api.schemas.admin.account import AccountStatusResponse, CreateAccountRequest
from api.schemas.admin.agent import CreateAgentRequest
from api.schemas.admin.project import CreateProjectRequest
from db.tables.accounts import OnboardingMethod


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


class OnboardingProjectInfo(BaseModel):
    """Project information returned from onboarding"""

    project_id: str = Field(..., description="UUID of the created project")
    project_name: str = Field(..., description="Name of the project")
    agent_id: str = Field(..., description="UUID of the associated agent")
    enable_web_widget: bool = Field(..., description="Whether web widget is enabled")


class OnboardingResponse(BaseModel):
    """Response model for onboarding request"""

    account_name: str = Field(..., description="Name of the created account")
    projects: list[OnboardingProjectInfo] = Field(
        ..., description="List of created projects"
    )


class SelfOnboardingRequest(BaseModel):
    """Self Onboarding Request"""

    # Account parameters
    account_name: str = Field(..., description="Name of the created account")
    account_display_name: str = Field(
        ..., description="Display name of the created account"
    )
    phone_number: str = Field(..., description="Phone number of the created account")
    account_onboarding_method: OnboardingMethod = Field(
        ..., description="Onboarding method of the created account"
    )

    # User parameters
    user_name: str = Field(..., description="Name of the created user")
    email: str = Field(..., description="Email of the created user")
    password: str = Field(..., description="Password of the created user")

    # Agent parameters
    agent_name: str = Field(..., description="Name of the created agent")
    agent_communication_style: str
    agent_interaction_guidelines: str = Field(
        ..., description="Interaction guidelines of the created agent"
    )
    agent_voice_id: str = Field(..., description="Voice id of the created agent")
    agent_background_noise: bool = Field(
        ..., description="Background noise of the created agent"
    )

    project_name: str = Field(..., description="Name of the created project")
    project_display_name: str = Field(
        ..., description="Display name of the created project"
    )
    project_store_hours: str = Field(
        ..., description="Store hours of the created project"
    )
    project_address: str = Field(..., description="Address of the created project")


class SelfOnboardingResponse(BaseModel):
    """Self Onboarding Response"""

    success: bool = Field(..., description="Whether the onboarding was successful")
    account_response: AccountStatusResponse
