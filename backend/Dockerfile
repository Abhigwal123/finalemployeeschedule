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
    gosu \
    && rm -rf /var/lib/apt/lists/*

# ==========================================
# Python Dependencies
# ==========================================
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements_flask.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements_flask.txt

# ==========================================
# Application Code
# ==========================================
# Copy entrypoint script first (before copying code)
COPY docker-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Copy backend application code (excludes files in .dockerignore)
# This copies backend/ to /app/backend/ in the container
COPY . /app/backend

# ==========================================
# User and Permissions
# ==========================================
# Create non-root user for security
RUN useradd -m -u 1000 appuser

# Create logs and instance directories with proper ownership
# These will be used if volumes are not mounted, or as fallback
RUN mkdir -p /app/logs /app/instance /app/backend/logs /app/backend/instance && \
    chown -R appuser:appuser /app/logs /app/instance /app/backend/logs /app/backend/instance && \
    chmod -R 755 /app/logs /app/instance /app/backend/logs /app/backend/instance

# Change ownership of entire /app directory
RUN chown -R appuser:appuser /app

# Note: Keep as root for entrypoint (will switch to appuser in entrypoint)
# USER appuser

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
# Entrypoint and Command
# ==========================================
# Set entrypoint script (handles user switching and initialization)
ENTRYPOINT ["/entrypoint.sh"]

# Default command - run migrations then start Gunicorn on port 8081
WORKDIR /app/backend
CMD ["sh", "-c", "cd /app/backend && alembic upgrade head && gunicorn --bind 0.0.0.0:8081 --workers=4 --threads=4 --timeout=120 --access-logfile - --error-logfile - --log-level info wsgi:application"]
