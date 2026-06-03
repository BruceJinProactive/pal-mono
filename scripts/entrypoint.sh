#!/bin/bash

############################################################################
#
# Entrypoint script
#
############################################################################

if [[ "$PRINT_ENV_ON_LOAD" = true || "$PRINT_ENV_ON_LOAD" = True ]]; then
  echo "=================================================="
  printenv
  echo "=================================================="
fi

############################################################################
# Wait for Services
############################################################################

if [[ "$WAIT_FOR_DB" = true || "$WAIT_FOR_DB" = True ]]; then
  dockerize \
    -wait tcp://$DB_HOST:$DB_PORT \
    -timeout 300s
fi

if [[ "$WAIT_FOR_REDIS" = true || "$WAIT_FOR_REDIS" = True ]]; then
  REDIS_WAIT_HOST="${REDIS_HOST:-$REDIS_CACHE_HOST}"
  REDIS_WAIT_PORT="${REDIS_PORT:-${REDIS_CACHE_PORT:-6379}}"

  if [[ -z "$REDIS_WAIT_HOST" ]]; then
    echo "ERROR: WAIT_FOR_REDIS requires REDIS_HOST or REDIS_CACHE_HOST" >&2
    exit 1
  fi

  dockerize \
    -wait "tcp://$REDIS_WAIT_HOST:$REDIS_WAIT_PORT" \
    -timeout 300s
fi

############################################################################
# Install dependencies
############################################################################

if [[ "$INSTALL_REQUIREMENTS" = true || "$INSTALL_REQUIREMENTS" = True ]]; then
  echo "++++++++++++++++++++++++++++++++++++++++++++++++++++++++"
  echo "Installing requirements: $REQUIREMENTS_FILE_PATH"
  pip3 install -r $REQUIREMENTS_FILE_PATH
  echo "++++++++++++++++++++++++++++++++++++++++++++++++++++++++"
fi

############################################################################
# Migrate database (version-aware: supports both upgrade and downgrade)
############################################################################

if [[ "$MIGRATE_DB" = true || "$MIGRATE_DB" = True ]]; then
  echo "++++++++++++++++++++++++++++++++++++++++++++++++++++++++"
  echo "Running version-aware migration"

  # Get target version from migration files (the HEAD revision this build expects)
  TARGET_VERSION=$(alembic -c db/alembic.ini heads --resolve-dependencies 2>/dev/null | head -1 | awk '{print $1}')

  if [[ -z "$TARGET_VERSION" ]]; then
    echo "ERROR: Failed to determine migration head from alembic" >&2
    exit 1
  fi

  # Get current database version
  CURRENT_VERSION=$(alembic -c db/alembic.ini current 2>/dev/null | awk '{print $1}' | head -1)

  echo "Current DB version: ${CURRENT_VERSION:-none}"
  echo "Target version: $TARGET_VERSION"

  if [[ "$CURRENT_VERSION" == "$TARGET_VERSION" ]]; then
    echo "Database already at target version, skipping migration"
  elif [[ -z "$CURRENT_VERSION" ]]; then
    # Fresh database - just upgrade
    echo "Fresh database, upgrading to $TARGET_VERSION"
    if ! alembic -c db/alembic.ini upgrade "$TARGET_VERSION"; then
      echo "ERROR: Database migration failed!"
      exit 1
    fi
  else
    # Database has a version - determine direction and migrate
    echo "Migrating database to $TARGET_VERSION"

    # Check if target is reachable via upgrade path
    if alembic -c db/alembic.ini history -r "$CURRENT_VERSION:$TARGET_VERSION" 2>/dev/null | grep -q .; then
      echo "Upgrading to $TARGET_VERSION"
      if ! alembic -c db/alembic.ini upgrade "$TARGET_VERSION"; then
        echo "ERROR: Database upgrade failed!"
        exit 1
      fi
      echo "Successfully upgraded to $TARGET_VERSION"
    else
      echo "Downgrading to $TARGET_VERSION"
      if ! alembic -c db/alembic.ini downgrade "$TARGET_VERSION"; then
        echo "ERROR: Database downgrade failed!"
        exit 1
      fi
      echo "Successfully downgraded to $TARGET_VERSION"
    fi
  fi

  echo "++++++++++++++++++++++++++++++++++++++++++++++++++++++++"
fi

############################################################################
# Start App
############################################################################

case "$1" in
  chill)
    ;;
  *)
    echo "Running: $@"
    exec "$@"
    ;;
esac

echo ">>> Hello World!"
while true; do sleep 18000; done
