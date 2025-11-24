# Backend Flask Application Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    default-libmysqlclient-dev \
    pkg-config \
    libssl-dev \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements_flask.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements_flask.txt

# Copy backend application code (excludes files in .dockerignore)
# This copies backend/ to /app/backend/ in the container
COPY . /app/backend

# Set PYTHONPATH to allow:
# - /app/backend for "from backend.app import ..." and "from backend import ..."
# - /app/legacy_app for "from app import ..." (root app folder, mounted as volume)
# - /app for project root access
ENV PYTHONPATH="/app/backend:/app/legacy_app:/app"

# Create logs directory
RUN mkdir -p /app/logs /app/instance

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health')" || exit 1

# Default command - run from backend directory
WORKDIR /app/backend
CMD ["python", "main.py", "--host", "0.0.0.0", "--port", "8000"]
