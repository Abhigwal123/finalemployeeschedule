# ==========================================
# Backend Flask Application Dockerfile
# Production Configuration
# ==========================================

# Base image
FROM python:3.11-slim

# ==========================================
# Environment Variables
# ==========================================
# Make Python behave well inside containers
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="/app/backend:/app"

# ==========================================
# System Dependencies
# ==========================================
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    default-libmysqlclient-dev \
    pkg-config \
    libssl-dev \
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ==========================================
# User Creation
# ==========================================
# Create non-root user for security (before copying files)
RUN useradd -m -u 1000 appuser

# ==========================================
# Python Dependencies
# ==========================================
# Copy requirements first for better layer caching
COPY requirements_flask.txt /tmp/requirements_flask.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /tmp/requirements_flask.txt && \
    rm /tmp/requirements_flask.txt

# ==========================================
# Application Code
# ==========================================
# Set working directory
WORKDIR /app/backend

# Copy backend application code (excludes files in .dockerignore)
# This copies backend/ to /app/backend/ in the container
COPY . /app/backend

# ==========================================
# Permissions and User Switch
# ==========================================
# Create logs and instance directories with proper ownership
# These will be used if volumes are not mounted, or as fallback
RUN mkdir -p /app/logs /app/instance /app/backend/logs /app/backend/instance && \
    chown -R appuser:appuser /app && \
    chmod -R 755 /app/logs /app/instance /app/backend/logs /app/backend/instance

# Switch to non-root user for security
USER appuser

# ==========================================
# Port Configuration
# ==========================================
# Expose production backend port (8081)
EXPOSE 8081

# ==========================================
# Health Check
# ==========================================
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD wget --spider -q http://localhost:8081/api/v1/health || exit 1

# ==========================================
# Default Command
# ==========================================
# Run migrations then start Gunicorn on port 8081
# WORKDIR is already /app/backend, so no cd needed
CMD ["sh", "-c", "alembic upgrade head && gunicorn --bind 0.0.0.0:8081 --workers=4 --threads=4 --timeout=120 --access-logfile - --error-logfile - --log-level info wsgi:application"]
