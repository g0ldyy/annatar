# --- Build Stage ---
FROM python:3.11 as builder

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV POETRY_VERSION=1.7.1

# Install Poetry
RUN pip install "poetry==$POETRY_VERSION"

# Set the working directory in the builder stage
WORKDIR /app

# Copy the pyproject.toml and poetry.lock files
COPY pyproject.toml poetry.lock* /app/

# Install runtime dependencies using Poetry and create wheels for them
RUN poetry config virtualenvs.create false \
    && poetry install --no-dev --no-root --no-interaction --no-ansi \
    && poetry export -f requirements.txt --output requirements.txt --without-hashes \
    && pip wheel --no-cache-dir --no-deps --wheel-dir /tmp/wheels -r requirements.txt

# Copy the rest of your application's code
COPY annatar /app/annatar

# Build your application using Poetry
RUN poetry build

# --- Final Stage ---
FROM python:3.11-slim-bullseye as final

# Setup s6-overlay
RUN apt-get update && apt-get install -y nginx xz-utils
ARG S6_OVERLAY_VERSION=3.1.6.2
ADD https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-noarch.tar.xz /tmp
RUN tar -C / -Jxpf /tmp/s6-overlay-noarch.tar.xz
ADD https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-x86_64.tar.xz /tmp
RUN tar -C / -Jxpf /tmp/s6-overlay-x86_64.tar.xz

COPY s6/services.d/annatar /etc/services.d/annatar
COPY s6/services.d/annatar-workers /etc/services.d/annatar-workers
RUN chmod a+x /etc/services.d/annatar/run && \
	chmod a+x /etc/services.d/annatar-workers/run

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DB_PATH=/app/data/annatar.db
ENV NUM_WORKERS 4
ENV CONFIG_FILE=/config/annatar.yaml

VOLUME /app/data
WORKDIR /app

# Copy wheels and built wheel from the builder stage
COPY --from=builder /app/dist/*.whl /tmp/wheels/
COPY --from=builder /tmp/wheels/*.whl /tmp/wheels/

# # Install the application package along with all dependencies
RUN pip install /tmp/wheels/*.whl && rm -rf /tmp/wheels

# # Copy static and template files
COPY ./static /app/static
COPY ./templates /app/templates

COPY run.py /app/run.py

ARG BUILD_VERSION=UNKNOWN
ENV BUILD_VERSION=${BUILD_VERSION}

ENTRYPOINT ["/init"]
CMD []
