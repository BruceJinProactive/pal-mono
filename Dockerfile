FROM phidata/python:3.11.5

ARG USER=app
ARG APP_DIR=${USER_LOCAL_DIR}/${USER}
ENV APP_DIR=${APP_DIR}
# Add APP_DIR to PYTHONPATH
ENV PYTHONPATH="${APP_DIR}:${PYTHONPATH}"

# Create user and home directory
RUN groupadd -g 61000 ${USER} \
  && useradd -g 61000 -u 61000 -ms /bin/bash -d ${APP_DIR} ${USER}

WORKDIR ${APP_DIR}

# Update pip
RUN pip install --upgrade pip
# Copy pinned requirements
COPY requirements.txt .
# Install pinned requirements
RUN pip install -r requirements.txt

# Copy project files
COPY . .

COPY scripts /scripts

# Add ARGs for image definition files
ARG IMAGEDEFINITIONS_LAT_APP_FILE
ARG IMAGEDEFINITIONS_LAT_API_FILE
ARG IMAGEDEFINITIONS_STG_APP_FILE
ARG IMAGEDEFINITIONS_STG_API_FILE
ARG IMAGEDEFINITIONS_PRD_APP_FILE
ARG IMAGEDEFINITIONS_PRD_API_FILE

# Copy image definition files
COPY ${IMAGEDEFINITIONS_LAT_APP_FILE} /imagedefinitions_lat_app.json
COPY ${IMAGEDEFINITIONS_LAT_API_FILE} /imagedefinitions_lat_api.json
COPY ${IMAGEDEFINITIONS_STG_APP_FILE} /imagedefinitions_stg_app.json
COPY ${IMAGEDEFINITIONS_STG_API_FILE} /imagedefinitions_stg_api.json
COPY ${IMAGEDEFINITIONS_PRD_APP_FILE} /imagedefinitions_prd_app.json
COPY ${IMAGEDEFINITIONS_PRD_API_FILE} /imagedefinitions_prd_api.json

ENTRYPOINT ["/scripts/entrypoint.sh"]
CMD ["chill"]
