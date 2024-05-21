# Use the official Python image as a base
FROM python:3.10-slim

# Create and set the working directory
WORKDIR /app

# Copy the pyproject.toml and poetry.lock (if available) to the working directory
COPY pyproject.toml poetry.lock* ./
COPY vendor /app/vendor

# Install Poetry
RUN pip install poetry==1.8.2

# Configure Poetry to create virtualenvs in the project directory
RUN poetry config virtualenvs.in-project true

# install libs dependencies
RUN apt-get update && apt-get install -y \
    pkg-config libvirt-dev build-essential libguestfs-dev && \
    apt-get autoremove && apt-get clean

# Install dependencies
RUN poetry install --only main --no-root

# Copy the rest of the application code to the working directory
COPY . .

# Install the application itself
RUN poetry install --only main

# Set environment variables to ensure output is sent straight to the terminal without buffering
ENV PYTHONUNBUFFERED=1
# Set PATH to include Poetry's virtualenv
ENV PATH="/app/.venv/bin:$PATH"

# Command to run the application
CMD ["poetry", "run", "osw-builder"]
