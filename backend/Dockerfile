# Backend Flask Application Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Make Python behave well inside containers
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    default-libmysqlclient-dev \
    pkg-config \
    libssl-dev \
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements_flask.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements_flask.txt

# Copy backend application code (excludes files in .dockerignore)
# This copies backend/ to /app/backend/ in the container
COPY . /app/backend

# Set PYTHONPATH to allow:
# - /app/backend for "from backend.app import ...", "from backend import ...", and "from refactor import ..."
# - /app for project root access
ENV PYTHONPATH="/app/backend:/app"

# Create logs and instance directories
RUN mkdir -p /app/logs /app/instance /app/backend/logs /app/backend/instance

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD wget --spider -q http://localhost:8000/api/v1/health || exit 1

# Default command - run from backend directory
WORKDIR /app/backend
CMD ["python", "main.py", "--host", "0.0.0.0", "--port", "8000"]
