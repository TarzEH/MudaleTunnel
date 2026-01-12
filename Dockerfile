# Multi-stage build for MudaleTunnel
FROM python:3.11-slim as base

# Install system dependencies
RUN apt-get update && apt-get install -y \
    nmap \
    openssh-client \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Expose port for web interface
EXPOSE 8000

# Default command (can be overridden)
CMD ["python", "main.py", "web", "--host", "0.0.0.0", "--port", "8000"]
