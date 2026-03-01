"""conftest for number_service tests.

Sets service-specific environment variables. Database and AWS variables
are already configured by the root conftest.py.
"""

import os

os.environ.setdefault("TWILIO_ACCOUNT_SID", "ACtest123")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "test_auth_token")
os.environ.setdefault("VAPI_API_KEY", "test_vapi_key")
