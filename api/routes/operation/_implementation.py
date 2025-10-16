from sqlalchemy.orm import Session

from api.routes.admin._utils import UserContext


async def health_check(context: UserContext, session: Session):
    """
    Basic health check implementation for operation router.
    """
    return {
        "status": "healthy",
        "router": "operation",
        "user_email": context.email,
    }
