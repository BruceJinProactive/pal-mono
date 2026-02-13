"""Conftest for monitoring service tests.

Sets required environment variables before any module imports trigger
the db.settings validation chain (services/__init__.py → db → DbSettings).
"""

import os

# Must be set before any services.* import triggers db settings validation
os.environ.setdefault("db_host", "localhost")
os.environ.setdefault("db_port", "5432")
os.environ.setdefault("db_user", "test")
os.environ.setdefault("db_pass", "test")
os.environ.setdefault("db_database", "test")
os.environ.setdefault("AWS_ASSET_BUCKET_NAME", "test-bucket")
