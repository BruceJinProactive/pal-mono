from pydantic_settings import BaseSettings


class InfrastructureConfig(BaseSettings):
    # settings.py
    prd_env: str
    account_id: str
    aws_region: str
    aws_az1: str
    aws_az2: str
    subnet_ids: list
    # prd_resources.py
    db_instance_class: str
    allocated_storage: int


dev_config = InfrastructureConfig(
    # settings.py
    prd_env="",
    account_id="767398151610",
    aws_region="us-west-1",
    aws_az1="us-west-1a",
    aws_az2="us-west-1b",
    subnet_ids=[
        "subnet-0de9d04f262744f09",  # us-west-1a
        "subnet-031217b631485686d",  # us-west-1b
    ],
    # dev_resources.py
    db_instance_class="",
    allocated_storage=0,
)


prd_config = InfrastructureConfig(
    # settings.py
    prd_env="prd",
    account_id="677276080962",
    aws_region="us-east-1",
    aws_az1="us-east-1a",
    aws_az2="us-east-1b",
    subnet_ids=[
        "subnet-03014112402dbaf96",  # us-east-1a
        "subnet-03b7a86b16b84c22b",  # us-east-1b
    ],
    # prd_resources.py
    db_instance_class="db.r6g.xlarge",
    allocated_storage=500,
)

current_config = prd_config
