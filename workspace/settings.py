from pathlib import Path

from agno.workspace.settings import WorkspaceSettings

#
# -*- Define workspace settings using a WorkspaceSettings object
# these values can also be set using environment variables or a .env file
#
ws_settings = WorkspaceSettings(
    # Workspace name: used for naming resources
    ws_name="pal-mono",
    # Path to the workspace root
    ws_root=Path(__file__).parent.parent.resolve(),
    # Dev settings
    dev_env="dev",
    dev_app_enabled=True,
    dev_api_enabled=True,
    dev_db_enabled=True,
    # Region for AWS resources
    aws_region="us-west-1",
    # Image Settings
    image_name="pal-mono",
    image_repo="pal-mono",
    build_images=True,
    push_images=False,
)
