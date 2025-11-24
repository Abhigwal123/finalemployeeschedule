# Environment File (.env) Configuration Guide

## Current Setup

### Two Possible .env Locations

1. **Root `.env`** (Project root: `/Project_Up/.env`)
   - Used by Docker Compose
   - Referenced in `docker-compose.yml`: `env_file: - .env`
   - Used in production: `docker-compose.prod.yml`: `env_file: - .env.prod`

2. **Backend `.env`** (Backend directory: `/Project_Up/backend/.env`)
   - Could be used by Flask app when running locally
   - `load_dotenv()` looks in current working directory

## Recommendation: Use Root .env Only

**Best Practice**: Use **only the root `.env`** file for consistency.

### Why Root .env?

1. **Docker Compose** reads from project root
2. **Single source of truth** for all environment variables
3. **Easier to manage** - one file instead of two
4. **Consistent** across Docker and local development

## How It Works

### In Docker
- Docker Compose reads `.env` from project root
- Variables are injected into containers via `env_file: - .env`
- Flask app receives variables from environment (set by Docker)

### Local Development
- Flask app's `load_dotenv()` should explicitly load from project root
- This ensures consistency with Docker setup

## Current Code Behavior

### Flask App (`backend/app/__init__.py`)
```python
load_dotenv()  # Looks in current working directory
```

**Problem**: If you run from `backend/` directory, it looks for `backend/.env`
**Solution**: Explicitly load from project root

## Recommended Fix

Update Flask app to load `.env` from project root:

```python
import os
from pathlib import Path
from dotenv import load_dotenv

# Get project root (parent of backend/)
backend_dir = Path(__file__).parent.parent.parent  # Goes up to project root
env_path = backend_dir / '.env'
load_dotenv(env_path)
```

## Environment File Structure

### Development (.env at root)
```bash
# Database
MYSQL_ROOT_PASSWORD=rootpassword
MYSQL_DATABASE=scheduling_system
MYSQL_USER=scheduling_user
MYSQL_PASSWORD=scheduling_password
DATABASE_URL=mysql+pymysql://scheduling_user:scheduling_password@localhost:3306/scheduling_system?charset=utf8mb4

# Redis
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1

# Flask
FLASK_ENV=development
SECRET_KEY=dev-secret-key-change-in-production
JWT_SECRET_KEY=dev-jwt-secret-change-in-production

# CORS
BACKEND_CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

# Google Sheets
GOOGLE_APPLICATION_CREDENTIALS=service-account-creds.json
```

### Production (.env.prod at root)
```bash
# Database (use strong passwords!)
MYSQL_ROOT_PASSWORD=<strong-password>
MYSQL_DATABASE=scheduling_system
MYSQL_USER=scheduling_user
MYSQL_PASSWORD=<strong-password>
DATABASE_URL=mysql+pymysql://scheduling_user:<password>@mysql:3306/scheduling_system?charset=utf8mb4

# Redis
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/1

# Flask
FLASK_ENV=production
DEBUG=False
SECRET_KEY=<generate-strong-secret>
JWT_SECRET_KEY=<generate-strong-secret>

# CORS (update with your domain)
BACKEND_CORS_ORIGINS=https://yourdomain.com

# Google Sheets
GOOGLE_APPLICATION_CREDENTIALS=/app/service-account-creds.json
```

## Action Items

1. ✅ **Keep `.env` at project root** (for Docker Compose)
2. ✅ **Update Flask app** to load `.env` from project root explicitly
3. ✅ **Remove `backend/.env`** if it exists (use root one instead)
4. ✅ **Add `.env` to `.gitignore`** (already done)

## Verification

After fixing, verify:
- Docker Compose reads from root `.env`
- Flask app loads from root `.env` when running locally
- No duplicate `.env` files causing confusion

