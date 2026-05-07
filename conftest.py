"""Root conftest for pytest.

Sets required environment variables before any package imports trigger
db.settings validation (monitoring_service/_implementation.py → db → DbSettings).
"""

import os

os.environ.setdefault("db_host", "localhost")
os.environ.setdefault("db_port", "5432")
os.environ.setdefault("db_user", "test")
os.environ.setdefault("db_pass", "test")
os.environ.setdefault("db_database", "test")
os.environ.setdefault("AWS_ASSET_BUCKET_NAME", "test-bucket")
os.environ.setdefault("AWS_IMAGE_BUCKET_NAME", "test-images-bucket")
os.environ.setdefault("EVENT_BUS_NAME", "test-bus")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault("AWS_ADMIN_CONSOLE_USER_POOL_ID", "us-east-1_test")
os.environ.setdefault("AWS_ADMIN_CONSOLE_APP_CLIENT_ID", "test-client-id")
