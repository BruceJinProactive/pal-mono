# Database Management

[WARNING] This directory is for managing database migrations and should not be used for any other purpose.

## Migrate development database

1.  Add/update SqlAlchemy tables in the `db/tables` directory.
2.  Import the SqlAlchemy class in the `db/tables/__init__.py` file.
3.  Create a database revision using the command below:

> [WARNING] alembic autogenerate is often wrong. Review the migration file before running the upgrade command.

```bash
docker exec -it pal-mono-api alembic -c db/alembic.ini revision --autogenerate -m "<replace-with-your-change-message>"
```

1. Migrate database using the command below:

```bash
docker exec -it pal-mono-api alembic -c db/alembic.ini upgrade head
```

5. Connect to the database using pgAdmin or any other database management tool to verify the changes.

## Migrate staging database

1. Uncomment Env Var `MIGRATE_DB = True` under `workspace/stg_resources.py`.

```bash
# -*- Build container environment
container_env = {
...
    # Migrate database on startup using alembic
    "MIGRATE_DB": ws_settings.stg_db_enabled,
}
```

2. Create a Pull Request to merge the changes to the `main` branch. The tile of the PR should start with `[DB UPDATE]`.

3. Submit the PR and merge it to the `main` branch.

4. Update the ECS task definition to use the new environment variable.

```bash
phi ws patch --env stg --infra aws --name td
```

5. Update the ECS task definition to use the new environment variable.

```bash
phi ws patch --env stg --infra aws --name service
```

6. Connect to the database using pgAdmin or any other database management tool to verify the changes.

## Migrate production database

TODO

## DB migration history

| Link to migration version                                                                                                                                                                 | Tested on dev? | Deployed to staging? | Deployed to production? |
| ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------- | -------------------- | ----------------------- |
| [Initialize DB](https://github.com/Proactive-AI-Lab/pal-mono/blob/main/db/migrations/versions/038100802b26_initialize_db.py)                                                              | YES            | YES                  | NO                      |
| [Rename and add unique constraint to account_name](https://github.com/Proactive-AI-Lab/pal-mono/blob/main/db/migrations/versions/d4c296cb1ca6_rename_and_add_unique_constraint_to_.py)    | YES            | YES                  | NO                      |
| [Change column account names](https://github.com/Proactive-AI-Lab/pal-mono/blob/main/db/migrations/versions/541b23a8e944_change_column_account_names.py)                                  | YES            | YES                  | NO                      |
| [Add projects table](https://github.com/Proactive-AI-Lab/pal-mono/blob/main/db/migrations/versions/c40b5a6e029d_add_projects_table.py)                                                    | YES            | YES                  | NO                      |
| [Add assistants table and relationship in projects](https://github.com/Proactive-AI-Lab/pal-mono/blob/main/db/migrations/versions/f29d88d5d714_add_assistants_table_and_relationship_.py) | YES            | YES                  | NO                      |
| [Update updated_at to auto-update](https://github.com/Proactive-AI-Lab/pal-mono/blob/main/db/migrations/versions/fe5c96e5148a_update_updated_at_to_auto_update.py)                        | YES            | YES                  | NO                      |
| Placehold                                                                                                                                                                                 | NO             | NO                   | NO                      |
