from fastapi import HTTPException, status
from sqlalchemy.engine import Engine, create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker

from utils.log import logger

from .settings import db_settings

# Sync database URL
db_url = db_settings.get_db_url()
logger.info(f"Database URL: {db_url}")

# Synchronous engine
sync_db_engine: Engine = create_engine(
    db_url,
    pool_size=30,
    max_overflow=50,
    pool_timeout=30,
    pool_recycle=1800,
    pool_pre_ping=True,
)


# Synchronous SessionLocal
SyncSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_db_engine)


def get_db():
    """
    Dependency to get a synchronous database session.
    """

    db = SyncSessionLocal()
    try:
        yield db
    finally:
        db.close()


# Async database URL
db_url_async = db_settings.get_db_url_async()
logger.info(f"Database URL Async: {db_url_async}")

# Asynchronous engine
db_engin_asynce: AsyncEngine = create_async_engine(
    db_url_async,
    pool_size=30,
    max_overflow=50,
    pool_timeout=30,
    pool_recycle=1800,
    pool_pre_ping=True,
)


# Asynchronous SessionLocal
AsyncSessionLocal = async_sessionmaker(
    autocommit=False, autoflush=False, bind=db_engin_asynce
)


async def get_db_async():
    """
    Async dependency to get an asynchronous database session.
    """
    logger.info("Get db_async")
    async with AsyncSessionLocal() as db:
        try:
            yield db

            await db.commit()  # Commit if no exception occurred
        except SQLAlchemyError as e:
            await db.rollback()  # Rollback on database errors
            logger.error(f"Database error occurred: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database error occurred",
            )
        except Exception as e:
            await db.rollback()
            logger.error(f"Unexpected error occurred: {str(e)}")
            raise
        finally:
            await db.close()
