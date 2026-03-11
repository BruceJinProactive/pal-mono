from typing import Optional

from pydantic import BaseModel, Field

from api.schemas.admin.account import AccountStatusResponse, CreateAccountRequest
from api.schemas.admin.agent import CreateAgentRequest
from api.schemas.admin.project import CreateProjectRequest
from db.tables.accounts import AccountSegment


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
    account_description: str = Field(
        ..., description="Business description of the created account"
    )
    phone_number: str = Field(..., description="Phone number of the created account")
    terms_accepted: bool | None = Field(
        default=None,
        description="User acceptance of Terms of Service. Creates record in tos_acceptances table.",
        deprecated=True,
    )
    segment: AccountSegment | None = Field(
        default=None,
        description="Business segment: smb (small & medium business), mm (mid-market), or ent (enterprise)",
    )

    # User parameters
    user_name: str = Field(..., description="Name of the created user")
    email: str = Field(..., description="Email of the created user")
    password: str = Field(..., description="Password of the created user")

    # Agent parameters
    agent_name: str = Field(..., description="Name of the created agent")
    agent_greeting_message: str = Field(
        ..., description="Greeting message of the created agent"
    )
    agent_communication_style: str = Field(
        ..., description="Communication style of the created agent"
    )
    agent_interaction_guidelines: str = Field(
        ..., description="Interaction guidelines of the created agent"
    )
    agent_voice_id: str = Field(..., description="Voice id of the created agent")
    agent_language: str = Field(
        default="English",
        description="Language for the agent (English, Spanish, Chinese, Multilingual)",
    )

    project_name: str = Field(..., description="Name of the created project")
    project_display_name: str = Field(
        ..., description="Display name of the created project"
    )
    project_store_hours: str = Field(
        ..., description="Store hours of the created project"
    )
    project_address: str = Field(..., description="Address of the created project")
    project_timezone: str = Field(..., description="Timezone of the created project")
    google_place_id: str | None = Field(
        default=None, description="Google Place ID for the project location"
    )
    product_info: str | None = Field(
        default=None, description="Menu/product information for the project"
    )


class SelfOnboardingResponse(BaseModel):
    """Self Onboarding Response"""

    success: bool = Field(..., description="Whether the onboarding was successful")
    account_response: AccountStatusResponse


class BuildMenuRequest(BaseModel):
    """Request model for building menu from URL"""

    url: str = Field(..., description="URL to build menu from")
    use_stealth_proxy: bool = Field(
        default=False, description="Whether to use stealth proxy for protected sites"
    )


class BuildMenuResponse(BaseModel):
    """Response model for built menu data"""

    menu: str = Field(..., description="Menu data formatted as markdown")


class ScrapeBrandFromUrlRequest(BaseModel):
    """Request model for scraping brand from URL"""

    url: str = Field(..., description="URL to scrape brand from")


class ScrapeBrandFromUrlResponse(BaseModel):
    brand_info: str = Field(
        ...,
        description="A short description of the company's brand which is found through the URL provided",
    )


class MenuUploaderResponse(BaseModel):
    """Response model for async menu upload processing"""

    status: str = Field(..., description="Processing status (e.g., 'accepted')")
    message: str = Field(..., description="Status message for the user")
    project_id: str = Field(..., description="UUID of the project being updated")
    job_id: str = Field(..., description="UUID of the background processing job")


class SigninGoogleUserRequest(BaseModel):
    """Request model for signing in a Google user"""

    token: str = Field(..., description="Google OAuth token")


class SigninGoogleUserResponse(BaseModel):
    """Response model for signing in a Google user"""

    is_signed_in: bool = Field(
        ..., description="Whether the user is signed in successfully"
    )
    next_step: str = Field(..., description="Next step for the user after sign-in")
    tokens: Optional[dict] = None
    session: Optional[dict] = None


class MenuProcessingStatusResponse(BaseModel):
    """Response model for menu processing job status"""

    job_id: str = Field(..., description="UUID of the background processing job")
    project_id: str = Field(..., description="UUID of the project being updated")
    status: str = Field(
        ..., description="Job status: 'pending', 'processing', 'completed', 'failed'"
    )
    completed: bool = Field(..., description="Whether the job is completed")
    progress_percent: int = Field(..., description="Progress percentage (0-100)")
    data: dict = Field(default_factory=dict, description="Job result data")
    error: Optional[str] = Field(None, description="Error message if job failed")
    created_at: str = Field(..., description="Job creation timestamp (ISO format)")
    updated_at: str = Field(..., description="Job last update timestamp (ISO format)")
