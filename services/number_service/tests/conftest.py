"""conftest for number_service tests.

Sets required environment variables before any package imports trigger
db.settings validation.
"""

import os

os.environ.setdefault("db_host", "localhost")
os.environ.setdefault("db_port", "5432")
os.environ.setdefault("db_user", "test")
os.environ.setdefault("db_pass", "test")
os.environ.setdefault("db_database", "test")
os.environ.setdefault("AWS_ASSET_BUCKET_NAME", "test-bucket")
os.environ.setdefault("TWILIO_ACCOUNT_SID", "ACtest123")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "test_auth_token")
os.environ.setdefault("VAPI_API_KEY", "test_vapi_key")
