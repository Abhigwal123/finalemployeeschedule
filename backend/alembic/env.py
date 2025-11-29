"""
Alembic environment configuration
"""

from logging.config import fileConfig
from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context
import os
import sys

# Get the backend directory (parent of alembic/)
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Get the project root (parent of backend/)
project_root = os.path.dirname(backend_dir)

# Add project root to Python path so we can import 'backend.app'
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Also add backend directory for refactor.* imports if needed
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# Import Flask app and get metadata from Flask-SQLAlchemy
from backend.app import create_app
from backend.app.extensions import db

# Create Flask app WITHOUT Celery for migrations (faster, no Redis dependency)
# This creates the app in the current process context
app = create_app(with_celery=False)

# Import all models to register them with SQLAlchemy
# This ensures all models are registered with Flask-SQLAlchemy metadata
from backend.app.models import (
    Tenant, User, Department, ScheduleDefinition,
    SchedulePermission, ScheduleJobLog, EmployeeMapping,
    CachedSheetData, CachedSchedule, SyncLog, ScheduleTask
)

# Use Flask-SQLAlchemy's metadata for Alembic
target_metadata = db.metadata

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def get_url():
    """Get database URL from Flask app config, environment variable, or alembic.ini"""
    # First try to get from Flask app config (most reliable)
    try:
        with app.app_context():
            flask_db_url = app.config.get('SQLALCHEMY_DATABASE_URI')
            if flask_db_url:
                return flask_db_url
    except Exception:
        pass
    
    # Fall back to environment variable
    env_db_url = os.getenv("DATABASE_URL")
    if env_db_url:
        return env_db_url
    
    # Finally fall back to alembic.ini
    return config.get_main_option("sqlalchemy.url")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = get_url()
    # SQLite-specific configuration
    dialect_opts = {}
    if "sqlite" in url.lower():
        dialect_opts = {"paramstyle": "named"}
    
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts=dialect_opts,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.
    
    Uses Flask-SQLAlchemy's engine for consistency with the app.

    """
    # Try to use Flask-SQLAlchemy's engine (preferred for consistency)
    try:
        with app.app_context():
            connectable = db.engine
            with connectable.connect() as connection:
                context.configure(
                    connection=connection, 
                    target_metadata=target_metadata
                )
                with context.begin_transaction():
                    context.run_migrations()
            return
    except Exception as e:
        # Fallback to creating engine from config if Flask engine fails
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Could not use Flask-SQLAlchemy engine, falling back to config: {e}")
    
    # Fallback: Create engine from configuration
    configuration = config.get_section(config.config_ini_section)
    url = get_url()
    configuration["sqlalchemy.url"] = url
    
    # Use NullPool for SQLite to avoid connection issues
    pool_class = pool.NullPool if "sqlite" in url.lower() else pool.StaticPool
    
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool_class,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
