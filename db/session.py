import time

from fastapi import HTTPException, status
from sqlalchemy import event
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


# ---- SYNC SQL latency logger ----
@event.listens_for(sync_db_engine, "before_cursor_execute")
def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    context._query_start_time = time.perf_counter()


@event.listens_for(sync_db_engine, "after_cursor_execute")
def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    total = time.perf_counter() - context._query_start_time
    logger.info(f"[SYNC SQL] {statement.strip()} | Latency: {total:.4f} seconds")


# Synchronous SessionLocal
SyncSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_db_engine)


def get_db():
    """
    Dependency to get a synchronous database session.
    """
    start_time = time.perf_counter()
    db = SyncSessionLocal()
    try:
        yield db
    finally:
        db.close()
        total_time = time.perf_counter() - start_time
        logger.info(f"[SYNC DB SESSION] Total latency: {total_time:.4f}s")


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


# ---- ASYNC SQL latency logger ----
@event.listens_for(db_engin_asynce.sync_engine, "before_cursor_execute")
def before_cursor_execute_async(
    conn, cursor, statement, parameters, context, executemany
):
    context._query_start_time = time.perf_counter()


@event.listens_for(db_engin_asynce.sync_engine, "after_cursor_execute")
def after_cursor_execute_async(
    conn, cursor, statement, parameters, context, executemany
):
    total = time.perf_counter() - context._query_start_time
    logger.info(f"[ASYNC SQL] {statement.strip()} | Latency: {total:.4f} seconds")


# Asynchronous SessionLocal
AsyncSessionLocal = async_sessionmaker(
    autocommit=False, autoflush=False, bind=db_engin_asynce
)


async def get_db_async():
    """
    Async dependency to get an asynchronous database session.
    """
    logger.info("Get db_async")
    start_time = time.perf_counter()
    async with AsyncSessionLocal() as db:
        try:
            yield db
            commit_start = time.perf_counter()
            await db.commit()  # Commit if no exception occurred
            logger.info(f"[DB COMMIT] Took {time.perf_counter() - commit_start:.4f}s")
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
            total_time = time.perf_counter() - start_time
            logger.info(f"[ASYNC DB SESSION] Total latency: {total_time:.4f}s")
