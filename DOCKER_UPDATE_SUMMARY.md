# Docker Configuration Update Summary

## Overview
Docker assets were updated to reflect the current `backend/` + `frontend/` layout and to make production deploys reproducible. Highlights:

1. Backend image now sets sane Python defaults for streaming logs.
2. Compose spins up MySQL/Redis/back-end/Celery/Frontend with consistent env + volume conventions.
3. Containers run database migrations automatically before exposing the API.

## Updated Files

### 1. `backend/Dockerfile`
- Added `PYTHONUNBUFFERED` and `PYTHONDONTWRITEBYTECODE` so logs stream directly and `.pyc` files are not written.
- Still installs from `requirements_flask.txt` inside `/app/backend`, so no path tweaks needed after the rename.

### 2. `docker-compose.yml` (dev/default)
- Backend service now executes `alembic upgrade head && python main.py --host 0.0.0.0 --port 8000`.
- Source tree is bind-mounted read/write (`./backend:/app/backend`) for live reload plus shared `logs` and `instance` directories.
- Celery worker/beat import the same `.env` as the API (so secrets/JWT values stay in sync) and depend on healthy MySQL/Redis.
- Added `init: true` to long-lived containers for reliable signal handling and shutdown.

### 3. `docker-compose.prod.yml`
- Production backend uses the same migration-first command and no longer bind-mounts the application code (runs from the built image).
- Celery services run from the image as well; only credentials/logs/instance folders remain mounted.
- Added `init: true` across services and kept Redis internal-only.

### 4. Frontend Docker/Nginx
- No path changes were required; multi-stage build still reads from `frontend/`.

## Key Changes

### Path & PYTHONPATH Behaviour
- All containers export `PYTHONPATH=/app/backend:/app`, guaranteeing that imports like `from app.routes import ...` hit the renamed backend package.

### Volume Strategy
- **Development:** bind mounts for source (`./backend`), credentials, logs, and instance data so you can iterate locally.
- **Production:** containers run from the immutable image; only credentials and persistent data directories are mounted.

### Auto-migrations
- Backend entrypoint runs Alembic before starting the API. If migrations fail the container exits early, keeping the stack in a safe state.

## Usage

### Development
```bash
docker compose up -d --build
```

### Production
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

## Operational Notes

1. **Secrets:**  
   - `.env` for development, `.env.prod` for production (consumed by backend + Celery).
2. **Google credentials:** keep `service-account-creds.json` at the project root; Compose mounts it into each backend/Celery container.
3. **Database:** MySQL 8 runs with UTF8MB4 charset/collation and exposes no ports in production.
4. **Logs & instance data:** bind-mounted to `./logs` and `./instance` (or the equivalent server directories) so uploads/logs survive restarts.
5. **Healthchecks:** Back-end `/api/v1/health`, Front-end `/health`, Redis `redis-cli ping`, MySQL `mysqladmin ping`.



