
from phi.aws.app.fastapi import FastApi
from phi.aws.app.streamlit import Streamlit
from phi.aws.resource.ec2 import InboundRule, SecurityGroup
from phi.aws.resource.ecs import EcsCluster
from phi.aws.resource.rds import DbInstance, DbSubnetGroup
from phi.aws.resource.reference import AwsReference
from phi.aws.resource.s3 import S3Bucket
from phi.aws.resource.secret import SecretsManager
from phi.aws.resources import AwsResources
from phi.docker.resource.image import DockerImage
from phi.docker.resources import DockerResources

from workspace.settings import ws_settings
from workspace.common_resources import common_container_env

#
# -*- Resources for the Production Environment
#
# Skip resource deletion when running `phi ws down` (set to True after initial deployment)
skip_delete: bool = False
# Save resource outputs to workspace/outputs
save_output: bool = True
# Create load balancer for the application
create_load_balancer: bool = True

# -*- Production image
stg_image = DockerImage(
    name=f"{ws_settings.image_repo}/{ws_settings.image_name}",
    tag=ws_settings.stg_env,
    enabled=ws_settings.build_images,
    path=str(ws_settings.ws_root),
    platforms=["linux/amd64", "linux/arm64"],
    push_image=True,
)

# -*- S3 bucket for production data (set enabled=True when needed)
stg_bucket = S3Bucket(
    name=f"{ws_settings.stg_key}-data",
    enabled=False,
    acl="private",
    skip_delete=skip_delete,
    save_output=save_output,
)

# -*- Secrets for production application
stg_secret = SecretsManager(
    name=f"{ws_settings.stg_key}-secret",
    group="app",
    # Create secret from workspace/secrets/stg_app_secrets.yml
    secret_files=[
        ws_settings.ws_root.joinpath("workspace/secrets/stg_app_secrets.yml")
    ],
    skip_delete=skip_delete,
    save_output=save_output,
)
# -*- Secrets for production database
stg_db_secret = SecretsManager(
    name=f"{ws_settings.stg_key}-db-secret",
    group="db",
    # Create secret from workspace/secrets/stg_db_secrets.yml
    secret_files=[ws_settings.ws_root.joinpath("workspace/secrets/stg_db_secrets.yml")],
    skip_delete=skip_delete,
    save_output=save_output,
)

# -*- Security Group for the load balancer
stg_lb_sg = SecurityGroup(
    name=f"{ws_settings.stg_key}-lb-security-group",
    enabled=create_load_balancer,
    group="app",
    description="Security group for the load balancer",
    inbound_rules=[
        InboundRule(
            description="Allow HTTP traffic from the internet",
            port=80,
            cidr_ip="0.0.0.0/0",
        ),
        InboundRule(
            description="Allow HTTPS traffic from the internet",
            port=443,
            cidr_ip="0.0.0.0/0",
        ),
    ],
    skip_delete=skip_delete,
    save_output=save_output,
)
# -*- Security Group for the application
stg_sg = SecurityGroup(
    name=f"{ws_settings.stg_key}-security-group",
    enabled=ws_settings.stg_api_enabled or ws_settings.stg_app_enabled,
    group="app",
    description="Security group for the production application",
    inbound_rules=[
        InboundRule(
            description="Allow traffic from LB to the FastAPI server",
            port=8000,
            security_group_id=AwsReference(stg_lb_sg.get_security_group_id),
        ),
        InboundRule(
            description="Allow traffic from LB to the Streamlit app",
            port=8501,
            security_group_id=AwsReference(stg_lb_sg.get_security_group_id),
        ),
    ],
    depends_on=[stg_lb_sg],
    skip_delete=skip_delete,
    save_output=save_output,
)
# -*- Security Group for the database
stg_db_port = 5432
stg_db_sg = SecurityGroup(
    name=f"{ws_settings.stg_key}-db-security-group",
    enabled=ws_settings.stg_db_enabled,
    group="db",
    description="Security group for the production database",
    inbound_rules=[
        InboundRule(
            description="Allow traffic from apps to the database",
            port=stg_db_port,
            security_group_id=AwsReference(stg_sg.get_security_group_id),
        ),
    ],
    depends_on=[stg_sg],
    skip_delete=skip_delete,
    save_output=save_output,
)

# -*- RDS Database Subnet Group
stg_db_subnet_group = DbSubnetGroup(
    name=f"{ws_settings.stg_key}-db-sg",
    enabled=ws_settings.stg_db_enabled,
    group="db",
    subnet_ids=ws_settings.subnet_ids,
    skip_delete=skip_delete,
    save_output=save_output,
)

# -*- RDS Database Instance
stg_db = DbInstance(
    name=f"{ws_settings.stg_key}-db",
    enabled=ws_settings.stg_db_enabled,
    group="db",
    db_name="app",
    port=stg_db_port,
    engine="postgres",
    engine_version="16.1",
    allocated_storage=64,
    # NOTE: For production, use a larger instance type.
    # Last checked price: ~$25 per month
    db_instance_class="db.t4g.small",
    db_security_groups=[stg_db_sg],
    db_subnet_group=stg_db_subnet_group,
    availability_zone=ws_settings.aws_az1,
    publicly_accessible=False,
    enable_performance_insights=True,
    aws_secret=stg_db_secret,
    skip_delete=skip_delete,
    save_output=save_output,
    # Do not wait for the db to be deleted
    wait_for_delete=False,
)

# -*- ECS cluster
launch_type = "FARGATE"
stg_ecs_cluster = EcsCluster(
    name=f"{ws_settings.stg_key}-cluster",
    ecs_cluster_name=ws_settings.stg_key,
    capacity_providers=[launch_type],
    skip_delete=skip_delete,
    save_output=save_output,
)

# -*- Build container environment
container_env = {
    "RUNTIME_ENV": "stg",

    # Database configuration
    "DB_HOST": AwsReference(stg_db.get_db_endpoint),
    "DB_PORT": AwsReference(stg_db.get_db_port),
    "DB_USER": AwsReference(stg_db.get_master_username),
    "DB_PASS": AwsReference(stg_db.get_master_user_password),
    "DB_DATABASE": AwsReference(stg_db.get_db_name),
    # Wait for database to be available before starting the application
    "WAIT_FOR_DB": ws_settings.stg_db_enabled,
    # Migrate database on startup using alembic
    # "MIGRATE_DB": ws_settings.stg_db_enabled,
}

container_env.update(common_container_env)

# -*- Streamlit running on ECS
stg_streamlit = Streamlit(
    name=f"{ws_settings.stg_key}-app",
    enabled=ws_settings.stg_app_enabled,
    group="app",
    image=stg_image,
    command="streamlit run app/Home.py",
    port_number=8501,
    ecs_task_cpu="2048",
    ecs_task_memory="4096",
    ecs_service_count=1,
    ecs_cluster=stg_ecs_cluster,
    aws_secrets=[stg_secret],
    subnets=ws_settings.subnet_ids,
    security_groups=[stg_sg],
    # To enable HTTPS, create an ACM certificate and add the ARN below:
    # load_balancer_enable_https=True,
    # load_balancer_certificate_arn="LOAD_BALANCER_CERTIFICATE_ARN",
    load_balancer_security_groups=[stg_lb_sg],
    create_load_balancer=create_load_balancer,
    env_vars=container_env,
    use_cache=ws_settings.use_cache,
    skip_delete=skip_delete,
    save_output=save_output,
    # Do not wait for the service to stabilize
    wait_for_create=False,
    # Do not wait for the service to be deleted
    wait_for_delete=False,
)

# -*- FastApi running on ECS
stg_fastapi = FastApi(
    name=f"{ws_settings.stg_key}-api",
    enabled=ws_settings.stg_api_enabled,
    group="api",
    image=stg_image,
    command="uvicorn api.main:app",
    port_number=8000,
    ecs_task_cpu="2048",
    ecs_task_memory="4096",
    ecs_service_count=1,
    ecs_cluster=stg_ecs_cluster,
    aws_secrets=[stg_secret],
    subnets=ws_settings.subnet_ids,
    security_groups=[stg_sg],
    # To enable HTTPS, create an ACM certificate and add the ARN below:
    # load_balancer_enable_https=True,
    # load_balancer_certificate_arn="LOAD_BALANCER_CERTIFICATE_ARN",
    load_balancer_security_groups=[stg_lb_sg],
    create_load_balancer=create_load_balancer,
    health_check_path="/v1/health",
    env_vars=container_env,
    use_cache=ws_settings.use_cache,
    skip_delete=skip_delete,
    save_output=save_output,
    # Do not wait for the service to stabilize
    wait_for_create=False,
    # Do not wait for the service to be deleted
    wait_for_delete=False,
)

# -*- Production DockerResources
stg_docker_resources = DockerResources(
    env=ws_settings.stg_env,
    network=ws_settings.ws_name,
    resources=[stg_image],
)

# -*- Production AwsResources
stg_aws_resources = AwsResources(
    env=ws_settings.stg_env,
    apps=[stg_streamlit, stg_fastapi],
    resources=[
        stg_lb_sg,
        stg_sg,
        stg_db_sg,
        stg_secret,
        stg_db_secret,
        stg_db_subnet_group,
        stg_db,
        stg_ecs_cluster,
        stg_bucket,
    ],
)
