"""Root conftest for pytest.

Sets required environment variables before any package imports trigger
db.settings validation (services/__init__.py → db → DbSettings).
"""

import os

os.environ.setdefault("db_host", "localhost")
os.environ.setdefault("db_port", "5432")
os.environ.setdefault("db_user", "test")
os.environ.setdefault("db_pass", "test")
os.environ.setdefault("db_database", "test")
os.environ.setdefault("AWS_ASSET_BUCKET_NAME", "test-bucket")
