FROM public.ecr.aws/docker/library/python:3.11-slim

# Install uv using official binary (faster and no pip dependency)
COPY --from=ghcr.io/astral-sh/uv:0.9.7 /uv /uvx /bin/

# Update system packages for security patches
RUN apt-get update && apt-get upgrade -y && apt-get clean && rm -rf /var/lib/apt/lists/*

ARG USER=app
ARG APP_DIR=/${USER}
ENV APP_DIR=${APP_DIR}
# Add APP_DIR to PYTHONPATH
ENV PYTHONPATH="${APP_DIR}"

# Create user and home directory
RUN groupadd -g 61000 ${USER} \
  && useradd -g 61000 -u 61000 -ms /bin/bash -d ${APP_DIR} ${USER}

# Copy scripts to root-level directory and set ownership/permissions
COPY scripts /scripts
RUN chown -R ${USER}:${USER} /scripts && chmod +x /scripts/*.sh

# Switch to non-root user for security
USER ${USER}
WORKDIR ${APP_DIR}

# Copy dependency files
COPY pyproject.toml uv.lock ./
# Install dependencies using uv
RUN uv sync --frozen

# Copy project files
COPY . .

ENTRYPOINT ["/scripts/entrypoint.sh"]
CMD ["chill"]
