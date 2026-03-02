# ADR-012: UV as Package Manager

> **Status:** Accepted
> **Date:** 2024-06-01
> **Decision makers:** Jun Lee

## Context

The team needed a faster, more reliable package manager for Python. Traditional tools like pip and poetry have slower dependency resolution and install times, especially important in a project with many dependencies.

## Decision

The platform uses uv as the package manager. This is configured in `scripts/install.sh` and `pyproject.toml` with `[tool.uv]` section.

## Alternatives Considered

- **pip + pip-tools** — Slow dependency resolution, no built-in lock file management
- **Poetry** — Slower than uv, less compatible with pyproject.toml standards
- **PDM** — Less mainstream adoption; uv has better performance and Astral backing

## Consequences

- **Easier:** Significantly faster installs and better dependency resolution; modern tooling
- **Harder:** Less mainstream than pip/poetry; team needs to be familiar with uv-specific commands
