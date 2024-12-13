from pathlib import Path

from phi.workspace.settings import WorkspaceSettings

from workspace.configs import current_config

#
# -*- Define workspace settings using a WorkspaceSettings object
# these values can also be set using environment variables or a .env file
#
ws_settings = WorkspaceSettings(
    # Workspace name: used for naming resources
    ws_name="pal-mono",
    # Path to the workspace root
    ws_root=Path(__file__).parent.parent.resolve(),
    # -*- Dev settings
    dev_env="dev",
    dev_app_enabled=True,
    dev_api_enabled=True,
    dev_db_enabled=True,
    # -*- Production settings
    prd_env=current_config.prd_env,
    prd_app_enabled=True,
    prd_api_enabled=True,
    prd_db_enabled=True,
    # -*- AWS settings
    # Region for AWS resources
    aws_region=current_config.aws_region,
    # Availability Zones for AWS resources
    aws_az1=current_config.aws_az1,
    aws_az2=current_config.aws_az2,
    # Subnet IDs in the aws_region
    subnet_ids=current_config.subnet_ids,
    # -*- Image Settings
    # Name of the image
    image_name="pal-mono",
    # Repository for the image
    image_repo=f"{current_config.account_id}.dkr.ecr.{current_config.aws_region}.amazonaws.com",
    # Build images locally
    build_images=True,
    # Push images after building
    push_images=False,
)
