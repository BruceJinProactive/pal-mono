from os import getenv
from typing import Optional

from pydantic_settings import BaseSettings

from utils.log import logger


class DbSettings(BaseSettings):
    """Database settings that can be set using environment variables.

    Reference: https://docs.pydantic.dev/latest/usage/pydantic_settings/
    """

    # Database configuration
    db_host: Optional[str] = None
    db_port: Optional[int] = None
    db_user: Optional[str] = None
    db_pass: Optional[str] = None
    db_database: Optional[str] = None
    db_driver: str = "postgresql+psycopg"
    # Create/Upgrade database on startup using alembic
    migrate_db: bool = False

    def get_db_url(self) -> str:
        db_url = "{}://{}{}@{}:{}/{}".format(
            self.db_driver,
            self.db_user,
            f":{self.db_pass}" if self.db_pass else "",
            self.db_host,
            self.db_port,
            self.db_database,
        )
        # Use local database if RUNTIME_ENV is not set
        if "None" in db_url and getenv("RUNTIME_ENV") is None:
            from workspace.dev_resources import dev_db

            logger.debug("Using local connection")
            local_db_url = dev_db.get_db_connection_local()
            if local_db_url:
                db_url = local_db_url

        # Validate database connection
        if "None" in db_url or db_url is None:
            raise ValueError("Could not build database connection")
        return db_url

    def get_db_url_async(self) -> str:
        """
        Generates the database URL using an asynchronous driver.
        """
        # Map synchronous drivers to their async counterparts
        driver_mapping_async = {
            "postgresql+psycopg": "postgresql+asyncpg",
            "postgresql+psycopg2": "postgresql+asyncpg",
            "mysql+mysqldb": "mysql+aiomysql",
            "sqlite": "sqlite+aiosqlite",
            # Add more mappings as needed
        }

        # Get the async driver
        if self.db_driver in driver_mapping_async:
            db_driver_async = driver_mapping_async[self.db_driver]
        else:
            # If no mapping is found, default to the original driver
            # or raise an error if necessary
            raise ValueError(
                f"No async driver mapping for db_driver '{self.db_driver}'"
            )

        # Build the async database URL
        db_url = "{}://{}{}@{}:{}/{}".format(
            db_driver_async,
            self.db_user,
            f":{self.db_pass}" if self.db_pass else "",
            self.db_host,
            self.db_port,
            self.db_database,
        )

        # Use local database if RUNTIME_ENV is not set
        if "None" in db_url and getenv("RUNTIME_ENV") is None:
            from workspace.dev_resources import dev_db

            logger.debug("Using local connection")
            local_db_url = dev_db.get_db_connection_local()
            if local_db_url:
                db_url = local_db_url

        # Validate database connection
        if "None" in db_url or db_url is None:
            raise ValueError("Could not build database connection")
        return db_url


# Create DbSettings object
db_settings = DbSettings()
