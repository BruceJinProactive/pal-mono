# syntax=docker/dockerfile:1
FROM public.ecr.aws/docker/library/python:3.11-slim

# Install uv using official binary (faster and no pip dependency)
COPY --from=ghcr.io/astral-sh/uv:0.9.7 /uv /uvx /bin/

# Install git for private dependency installation and update system packages
RUN apt-get update && apt-get upgrade -y \
    && apt-get install -y git \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

ARG USER=app
ARG APP_DIR=/${USER}
ENV APP_DIR=${APP_DIR}
# Add APP_DIR to PYTHONPATH
ENV PYTHONPATH="${APP_DIR}"

# Create user and prepare directories with proper ownership
RUN groupadd -g 61000 ${USER} \
  && useradd -g 61000 -u 61000 -ms /bin/bash -d ${APP_DIR} ${USER} \
  && mkdir -p /scripts /opt/venv \
  && chown ${USER}:${USER} /scripts /opt/venv

# Stay as root for secret operations
# TODO Check security implications of this
WORKDIR ${APP_DIR}

# Copy and install dependencies FIRST (best cache layer)
# Install to /opt/venv to avoid being overwritten by workspace mount
COPY pyproject.toml uv.lock ./
ENV UV_PROJECT_ENVIRONMENT="/opt/venv"

# Install dependencies with optional GitHub token for private repos
# Uses BuildKit secret to avoid exposing token in image layers
# MUST run as root to access BuildKit secrets
RUN --mount=type=secret,id=github_token \
    if [ -f /run/secrets/github_token ]; then \
      GITHUB_TOKEN=$(cat /run/secrets/github_token); \
      git config --global url."https://${GITHUB_TOKEN}@github.com/".insteadOf "https://github.com/"; \
    fi && \
    uv sync --frozen && \
    if [ -n "$GITHUB_TOKEN" ]; then \
      git config --global --unset-all url."https://${GITHUB_TOKEN}@github.com/".insteadOf || true; \
    fi

# Fix ownership of installed files before switching to non-root user
RUN chown -R ${USER}:${USER} ${APP_DIR} /opt/venv

# Switch to non-root user for security
USER ${USER}

# Add virtual environment to PATH for direct command execution
ENV PATH="/opt/venv/bin:$PATH"

# Copy scripts AFTER dependencies (less frequently changed)
COPY --chown=${USER}:${USER} scripts /scripts
RUN chmod +x /scripts/*.sh

# Copy project files LAST (most frequently changed)
COPY --chown=${USER}:${USER} . .

ENTRYPOINT ["/scripts/entrypoint.sh"]
CMD ["chill"]
