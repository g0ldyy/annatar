# --- Build Stage ---
# Use the official Python 3.11 image as a base
FROM python:3.11-slim as builder

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV POETRY_VERSION 1.7.1
ENV NUM_WORKERS 1

# Install Poetry
RUN pip install "poetry==$POETRY_VERSION"

# Set the working directory in the builder stage
WORKDIR /app

# Copy the pyproject.toml and poetry.lock files
COPY pyproject.toml poetry.lock* /app/

# Install runtime dependencies using Poetry
# --no-dev: Skip installing development dependencies
# --no-root: Skip installing the root package (your package) at this stage
# --no-interaction: Do not prompt for input
# --no-ansi: Disable ANSI output
RUN poetry config virtualenvs.create false \
    && poetry install --no-dev --no-root --no-interaction --no-ansi

# Copy the rest of your application's code
COPY annatar /app/annatar

# Build your application using Poetry
RUN poetry build

# --- Final Stage ---
FROM python:3.11-slim as final

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV DB_PATH /app/data/annatar.db

ARG BUILD_VERSION=UNKNOWN
ENV BUILD_VERSION=${BUILD_VERSION}

VOLUME /app/data
# Set the working directory in the container
WORKDIR /app

# Copy only the built wheel from the builder stage
COPY --from=builder /app/dist/*.whl /app/
# Install the application package
RUN pip install *.whl && rm *.whl

# Copy static website files
COPY ./static /app/static
COPY ./templates /app/templates

COPY run.py /app/run.py
# Your application's default command, adjust as needed
CMD ["python", "run.py"]
