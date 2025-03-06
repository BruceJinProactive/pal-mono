from sqlalchemy.orm import declarative_base

Base = declarative_base()

# By default, all tables are created in the public schema, when it is specified
# explicitly and passed to alembic, it will limit the search path to only look
# at public schema, but somehow omit the schema name. The include_name handler
# in db/migrations/env.py selects which table to run migration on (e.g. filters
# out the alembic_version table). It does so by checking if the passed in table
# name is defined in our models. When the schema name is missing, the name it passes
# in is just the table name, however, the target_metadata.tables map uses the fully
# qualified table name with schema info. Thus, it returns false for every table,
# which results in each table getting recreated on every migration.
# I tried modifying the include_name function to append the "public" schema which
# fixes the problem for recreating all the tables, but the index name still has public
# keyword in them and causes them to be recreated in each migration. I wasn't able to
# fix that, unfortunately.
# The simplest fix is to drop the public schema here. And because we don't need
# to overwrite the schema information, we can just use the standard Base by calling
# declarative_base().
#
# class Base(DeclarativeBase):
#     """
#     Base class for SQLAlchemy model definitions.
#
#     https://fastapi.tiangolo.com/tutorial/sql-databases/#create-a-base-class
#     https://docs.sqlalchemy.org/en/20/orm/mapping_api.html#sqlalchemy.orm.DeclarativeBase
#     """
#
#     metadata = MetaData(schema="public")
