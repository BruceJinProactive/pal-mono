from pydantic_settings import BaseSettings


class InfrastructureConfig(BaseSettings):
    # settings.py
    prd_env: str
    subnet_ids: list
    account_id: str
    # prd_resources.py
    db_instance_class: str
    allocated_storage: int


prd_config = InfrastructureConfig(
    # settings.py
    prd_env="prd",
    subnet_ids=[
        "subnet-03014112402dbaf96",  # us-east-1a
        "subnet-03b7a86b16b84c22b",  # us-east-1b
    ],
    account_id="677276080962",
    # prd_resources.py
    db_instance_class="db.r6g.xlarge",
    allocated_storage=500,
)

current_config = prd_config
