from fastapi import APIRouter

from api.routes.endpoints import endpoints
from api.routes.telephony.twilio import twilio_router

telephony_router = APIRouter(prefix=endpoints.TELEPHONY, tags=["Telephony"])

# Include the Twilio router
telephony_router.include_router(twilio_router)
