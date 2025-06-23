# syntax=docker/dockerfile:1
# forces BuildKit to fetch and use the latest syntax features 1.x.x

#
# Build stage
#
FROM python:3.11-slim AS builder

ARG PACKER_VERSION=1.8.6
ARG POETRY_VERSION=1.8.2
ARG GIT_USERNAME=wenzel

SHELL ["/bin/bash", "-o", "pipefail", "-o", "errexit", "-c"]

# Set working directory
WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y \
    pkg-config libvirt-dev build-essential libguestfs-dev unzip wget && \
    apt-get autoremove && apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install poetry==${POETRY_VERSION}

# Configure Poetry to create virtualenvs in the project directory
RUN poetry config virtualenvs.in-project true

# Copy dependency files
COPY pyproject.toml poetry.lock* ./

# Configure poetry to use github token and install dependencies
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
poetry install --only main --no-root
EOF

# Copy application code and install
COPY . .
RUN poetry install --only main

# Download and verify Packer binary
RUN PACKER_SHA256="57d0411e578aea62918d36ed186951139d5d49d44b76e5666d1fbf2427b385ae" && \
    wget https://releases.hashicorp.com/packer/${PACKER_VERSION}/packer_${PACKER_VERSION}_linux_amd64.zip && \
    echo "${PACKER_SHA256} packer_${PACKER_VERSION}_linux_amd64.zip" | sha256sum -c - && \
    unzip packer_${PACKER_VERSION}_linux_amd64.zip && \
    chmod +x packer

#
# Runtime stage
#
FROM python:3.11-slim AS runtime

# Install only runtime dependencies
RUN apt-get update && apt-get install -y \
    libvirt0 libguestfs0 && \
    apt-get autoremove && apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid appuser --shell /bin/bash --create-home appuser

# Set working directory
WORKDIR /app

# Copy built virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application code
COPY --from=builder /app /app

# Copy Packer binary
COPY --from=builder /app/packer /usr/local/bin/packer

# Change ownership to appuser
RUN chown -R appuser:appuser /app

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PATH="/app/.venv/bin:$PATH"
ENV PACKER_CACHE_DIR="/packer_cache"

# Switch to non-root user
USER appuser

# Command to run the application
ENTRYPOINT ["osw-builder"]
