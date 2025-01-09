import os

LOCAL_BUCKET = "local-bucket"

# AWS s3 bucket env vars
AWS_ASSET_BUCKET_NAME = os.getenv("AWS_ASSET_BUCKET_NAME", default=LOCAL_BUCKET)
AWS_REGION = os.environ["AWS_REGION"]
