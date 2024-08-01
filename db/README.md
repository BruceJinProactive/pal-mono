# Database Management

## WARNING: This directory is for managing database migrations and should not be used for any other purpose.

---

## Migrate development database [dev]

1.  Add/update SqlAlchemy tables in the `db/tables` directory.
2.  Import the SqlAlchemy class in the `db/tables/__init__.py` file.
3.  Create a database revision using the command below:

> `alembic autogenerate` is often very wrong. Review the migration file, ask ChatGPT to regenerate the file, then run the upgrade command.

```bash
docker exec -it pal-mono-api alembic -c db/alembic.ini revision --autogenerate -m "<db-change-message>"
```

4. Migrate database using the command below:

```bash
docker exec -it pal-mono-api alembic -c db/alembic.ini upgrade head
```

5. Connect to the database using pgAdmin or any other database management tool to verify the changes.

6. Create a Pull Request and merge the changes to the `main` branch. The tile of the PR should be `[DB UPDATE] <db-change-message>`.

---

## Migrate staging database [stg]

1. Uncomment Env Var `MIGRATE_DB = True` under `workspace/stg_resources.py`.

```bash
# -*- Build container environment
container_env = {
...
    # Migrate database on startup using alembic
    "MIGRATE_DB": ws_settings.stg_db_enabled,
}
```

2. Create a Pull Request and merge the changes to the `main` branch. The tile of the PR should be `[DB UPDATE] Staging db update`.

3. Update the ECS task definition to use the new environment variable.

```bash
phi ws patch --env stg --infra aws --name td
```

5. Update the ECS task definition to use the new environment variable.

```bash
phi ws patch --env stg --infra aws --name service
```

6. Connect to the database using pgAdmin or any other database management tool to verify the changes.

7. Create a Pull Request and merge the changes to the `main` branch. The tile of the PR should be `[DB UPDATE] Staging db update done`.

---

## Migrate production database [prd]

TODO

---

## DB migration history

https://www.notion.so/proactiveailab/6f15cf28565a4ba784eb9c605fa12a47?v=78b57bee60a54f409a47461b1d52881b&pvs=4
