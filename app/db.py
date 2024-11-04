import streamlit as st
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from db.session import get_async_db, get_db


def get_app_db() -> Session:
    """
    Streamlit dependency to get a synchronous database session.

    Returns:
        Session: SQLAlchemy database session

    Raises:
        RuntimeError: If database connection fails
    """
    if "db" not in st.session_state:
        try:
            session = next(get_db(), None)
            if session is None:
                raise RuntimeError("Failed to establish database connection")
            st.session_state.db = session
        except Exception as e:
            st.error("Database connection error")
            raise RuntimeError(f"Failed to connect to database: {str(e)}")
    return st.session_state.db


async def get_app_db_async() -> AsyncSession:
    """
    Streamlit dependency to get an asynchronous database session.

    Returns:
        AsyncSession: SQLAlchemy async database session

    Raises:
        RuntimeError: If database connection fails
    """
    if "async_db" not in st.session_state:
        try:
            async_gen = get_async_db()
            session = await anext(async_gen, None)
            if session is None:
                raise RuntimeError("Failed to establish async database connection")
            st.session_state.async_db = session
        except Exception as e:
            st.error("Async database connection error")
            raise RuntimeError(f"Failed to connect to async database: {str(e)}")
    return st.session_state.async_db
