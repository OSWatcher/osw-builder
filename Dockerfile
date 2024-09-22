# syntax=docker/dockerfile:1
# forces BuildKit to fetch and use the latest syntax features 1.x.x

# Use the official Python image as a base
FROM python:3.10-slim

ARG PACKER_VERSION=1.8.6
ARG POETRY_VERSION=1.8.2

SHELL ["/bin/bash", "-o", "pipefail", "-o", "errexit", "-c"]

# Create and set the working directory
WORKDIR /app

# Copy the pyproject.toml and poetry.lock (if available) to the working directory
COPY pyproject.toml poetry.lock* ./

# Install Poetry
RUN pip install poetry==${POETRY_VERSION}

# Configure Poetry to create virtualenvs in the project directory
RUN poetry config virtualenvs.in-project true
# configure poetry to use github token
RUN --mount=type=secret,id=GIT_AUTH_TOKEN,env=GIT_AUTH_TOKEN <<EOF
# ensure not empty
if [ -z "$GIT_AUTH_TOKEN" ]; then
    echo "GIT_AUTH_TOKEN is not set"
    exit 1
fi
poetry config repositories.neogit "https://github.com/OSWatcher/neogit.git"
poetry config repositories.pywinupdate "https://github.com/OSWatcher/pywinupdate.git"
poetry config http-basic.neogit "wenzel" $GIT_AUTH_TOKEN
poetry config http-basic.pywinupdate "wenzel" $GIT_AUTH_TOKEN
EOF

# install libs dependencies
RUN apt-get update && apt-get install -y \
    pkg-config libvirt-dev build-essential libguestfs-dev unzip && \
    apt-get autoremove && apt-get clean

# Install Packer using the build-time argument
RUN wget https://releases.hashicorp.com/packer/${PACKER_VERSION}/packer_${PACKER_VERSION}_linux_amd64.zip && \
    unzip packer_${PACKER_VERSION}_linux_amd64.zip && \
    mv packer /usr/local/bin/ && \
    rm packer_${PACKER_VERSION}_linux_amd64.zip

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
ENV PACKER_CACHE_DIR="/packer_cache"

# Command to run the application
CMD ["poetry", "run", "osw-builder"]
