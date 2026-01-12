# Multi-stage build for MudaleTunnel using uv
FROM python:3.11-slim as base

# Install system dependencies
RUN apt-get update && apt-get install -y \
    nmap \
    openssh-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv from official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
RUN chmod +x /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Copy all application files first (needed for package build)
# uv sync will build the package, so all source files must be present
COPY pyproject.toml uv.lock* README.md LICENSE ./
COPY *.py ./
COPY templates/ ./templates/
COPY static/ ./static/

# Install Python dependencies using uv
# If uv.lock doesn't exist, uv will generate it
RUN if [ -f uv.lock ]; then \
        uv sync --frozen --no-dev; \
    else \
        uv sync --no-dev; \
    fi

# Expose port for web interface
EXPOSE 8000

# Default command (can be overridden)
# Use uv run to execute with the correct environment
CMD ["uv", "run", "python", "main.py", "web", "--host", "0.0.0.0", "--port", "8000"]
