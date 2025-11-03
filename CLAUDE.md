# CLAUDE.md

This file contains information for Claude to help with the pal-mono repository.

## Overview

The pal-mono service is a Python monolith that serves 2 artifacts:
- api - a RESTful API that serves the main functionality of the service
- app - a web app that demos the functionalities of the service

## Commands

### Running Services

```bash
# Build and run both API and web app locally
ag ws up

# Force rebuild from scratch
ag ws up -f
```

### Local Environment Setup

```bash
# Install dependencies using uv (creates virtual environment automatically)
./scripts/install.sh

# Or directly with uv:
uv sync --all-extras
```

### Dependency Management

```bash
# Update lock file after adding new dependencies to pyproject.toml
./scripts/upgrade.sh
# or: uv lock

# Upgrade all dependencies to latest compatible versions
./scripts/upgrade.sh all
# or: uv lock --upgrade
```

### Validation

```bash
# Run all validation checks
./scripts/validate.sh

# Format with black
black .

# Sort imports
isort .

# Lint with ruff
ruff check . --fix

# Type check with pyright
pyright .
```

### Testing

```bash
# Start the containers first
ag ws up

# Run tests
./scripts/test.sh
```

### API and App Access

- API documentation: http://localhost:8000/docs#/
- Web app: http://localhost:8501/