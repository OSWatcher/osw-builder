# syntax=docker/dockerfile:1
# forces BuildKit to fetch and use the latest syntax features 1.x.x

# Use the official Python image as a base
FROM python:3.10-slim

ARG PACKER_VERSION=1.8.6
ARG POETRY_VERSION=1.8.2
ARG GIT_USERNAME=wenzel

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
poetry config repositories.plugins "https://github.com/OSWatcher/grapheos-plugins.git"
poetry config http-basic.neogit "$GIT_USERNAME" $GIT_AUTH_TOKEN
poetry config http-basic.pywinupdate "$GIT_USERNAME" $GIT_AUTH_TOKEN
poetry config http-basic.plugins "$GIT_USERNAME" $GIT_AUTH_TOKEN
EOF

# install libs dependencies
RUN apt-get update && apt-get install -y \
    pkg-config libvirt-dev build-essential libguestfs-dev unzip && \
    apt-get autoremove && apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install Packer using the build-time argument with checksum verification
RUN PACKER_SHA256="f937521367401ad374690c6b5cc73649a98e435c2b0a36e6a0eabfe89e6f27dd" && \
    wget https://releases.hashicorp.com/packer/${PACKER_VERSION}/packer_${PACKER_VERSION}_linux_amd64.zip && \
    echo "${PACKER_SHA256} packer_${PACKER_VERSION}_linux_amd64.zip" | sha256sum -c - && \
    unzip packer_${PACKER_VERSION}_linux_amd64.zip && \
    mv packer /usr/local/bin/ && \
    rm packer_${PACKER_VERSION}_linux_amd64.zip

# Install dependencies
RUN poetry install --only main --no-root

# Copy the rest of the application code to the working directory
COPY . .

# Install the application itself
RUN poetry install --only main

# Create non-root user and change ownership
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid appuser --shell /bin/bash --create-home appuser && \
    chown -R appuser:appuser /app

# Set environment variables to ensure output is sent straight to the terminal without buffering
ENV PYTHONUNBUFFERED=1
# Set PATH to include Poetry's virtualenv
ENV PATH="/app/.venv/bin:$PATH"
ENV PACKER_CACHE_DIR="/packer_cache"

# Switch to non-root user
USER appuser

# Command to run the application
CMD ["poetry", "run", "osw-builder"]
