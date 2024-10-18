from sqlalchemy.engine import Engine, create_engine
from sqlalchemy.orm import sessionmaker

from db.settings import db_settings

# Create SQLAlchemy Engine using a database URL
db_url = db_settings.get_db_url()
db_engine: Engine = create_engine(
    db_url,
    pool_size=30,  # The number of connections to keep open in the pool
    max_overflow=50,  # The maximum number of connections to allow in overflow (beyond pool_size)
    pool_timeout=30,  # The number of seconds to wait before giving up on getting a connection from the pool
    pool_recycle=1800,  # The number of seconds to recycle (close and reopen) connections to avoid stale connections
    pool_pre_ping=True,  # Check the connection before using it to avoid stale connections
)
# Create a SessionLocal class
# https://fastapi.tiangolo.com/tutorial/sql-databases/#create-a-sessionlocal-class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)


def get_db():
    """
    Dependency to get a database session.

    https://fastapi.tiangolo.com/tutorial/sql-databases/#create-a-dependency
    """

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
