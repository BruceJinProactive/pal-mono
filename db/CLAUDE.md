# CLAUDE.md - Database Layer

## Structure

```tree
db/
├── session.py        # get_db() and get_db_async() for FastAPI Depends()
├── settings.py       # DbSettings with connection URLs
├── tables/           # SQLAlchemy models (inherit from tables/base.py)
├── repositories/     # Data access layer (sync + async variants)
└── migrations/       # Alembic migrations
```

## Critical Patterns

### Dual Sync/Async Support

All repositories should provide async classes. Should try deprecating any sync classes:

```python
# Async: caller manages transactions
repo = AccountRepositoryAsync(session)
```

### Repository Error Handling

All operations must wrap in try-except with rollback:

```python
try:
    result = await self.session.execute(select(Item).filter(...))
    return result.scalar_one_or_none()
except SQLAlchemyError as e:
    await self.session.rollback()
    logger.error(f"Error: {e}")
    return None
```

### Indexed References vs Foreign Keys

Prefer tables to use indexed columns without FK constraints for flexibility. Relationships are managed by code:

```python
# No FK - just indexed for queries
project_id: Mapped[UUID] = mapped_column(UUID, index=True)
```

## Key Enums

Enums are stored in tables/types.py

## Migrations

### Commands

```bash
# Generate after modifying tables
docker exec pal-mono-api alembic -c db/alembic.ini revision --autogenerate -m "description"

# Apply
docker exec pal-mono-api alembic -c db/alembic.ini upgrade head

# Rollback
docker exec pal-mono-api alembic -c db/alembic.ini downgrade -1

# View history
docker exec pal-mono-api alembic -c db/alembic.ini history
```

### Requirements Before Generating

1. **Export new models** in `tables/__init__.py` - autogenerate only detects models imported into `Base.metadata`
2. **Docker must be running** - migrations run inside the container
3. **Database must be accessible** - env.py connects to DB to compare schema

### Key Behaviors

- **Migration files location**: Must be stored in `db/migrations/versions/`
- **Advisory lock** (`MIGRATION_LOCK_KEY = 20250325`): Prevents concurrent migrations across multiple nodes
- **File naming**: `YYYY-MM-DD_hash_description.py` (configured in alembic.ini)
- **Table filtering**: `include_name()` in env.py only tracks tables registered in `Base.metadata`
- **Correctness check**: `autogenerate` can be error-prone, always check forward and backward migration application

### Common Issues

- **Empty migration generated**: Model not exported in `tables/__init__.py`
- **Migration conflicts**: Two developers created migrations from same base - one must rebase
- **"Target database is not up to date"**: Run `upgrade head` before generating new migration
