from pydantic import BaseModel, Field


class BackfillRoleAssignmentsRequest(BaseModel):
    """Request model for backfilling role assignments from Cognito"""

    dry_run: bool = Field(
        default=True,
        description="Preview changes without applying them (safe default)",
    )
    email_filter: str | None = Field(
        default=None,
        description="Optional email filter to test on specific user (e.g., 'jacob@palona.com')",
    )


class BackfillUserResult(BaseModel):
    """Result for a single user's backfill operation"""

    email: str
    user_id: str = Field(description="Cognito username (UUID)")
    account_names: list[str] = Field(
        description="Account names from custom:account_names attribute"
    )
    roles_created: int = Field(description="Number of role assignments created")
    memberships_created: int = Field(
        description="Number of AccountUser records created"
    )
    skipped_accounts: list[str] = Field(
        default_factory=list,
        description="Account names that were not found in database",
    )
    errors: list[str] = Field(
        default_factory=list, description="Error messages encountered"
    )


class BackfillRoleAssignmentsResponse(BaseModel):
    """Response model for backfilling role assignments from Cognito"""

    dry_run: bool = Field(description="Whether this was a dry run (no changes applied)")
    total_users_processed: int = Field(
        description="Total number of Cognito users processed"
    )
    total_roles_created: int = Field(description="Total role assignments created")
    total_memberships_created: int = Field(
        description="Total AccountUser records created"
    )
    total_accounts_skipped: int = Field(
        description="Total accounts not found in database"
    )
    total_errors: int = Field(description="Total errors encountered")
    user_results: list[BackfillUserResult] = Field(
        default_factory=list,
        description="Detailed results for each user processed",
    )
