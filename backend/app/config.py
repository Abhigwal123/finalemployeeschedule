import os
from datetime import timedelta


def _env_bool(var_name: str, default: bool = False) -> bool:
    value = os.getenv(var_name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


# Get absolute path to backend directory (parent of app/)
# This ensures the path is always correct regardless of where Flask is launched from
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, os.pardir))

# Database location: Use instance folder (as requested)
INSTANCE_DIR = os.path.join(BASE_DIR, 'instance')
# Create instance directory with error handling for permission issues
try:
    os.makedirs(INSTANCE_DIR, exist_ok=True)
except PermissionError:
    # If permission denied, try to use /app/instance as fallback (for Docker)
    INSTANCE_DIR = os.getenv('INSTANCE_DIR', '/app/instance')
    try:
        os.makedirs(INSTANCE_DIR, exist_ok=True)
    except PermissionError:
        # Last resort: use /tmp/instance
        INSTANCE_DIR = '/tmp/instance'
        os.makedirs(INSTANCE_DIR, exist_ok=True)

# Database file path - always absolute, in instance folder
DEFAULT_DB_PATH = os.path.join(INSTANCE_DIR, 'scheduling_system.db')
DEFAULT_DB_PATH = os.path.abspath(DEFAULT_DB_PATH)

# Default Google credentials path (absolute, project root)
DEFAULT_GOOGLE_CREDENTIALS_PATH = os.path.abspath(
    os.path.join(PROJECT_ROOT, 'service-account-creds.json')
)

# Ensure GOOGLE_APPLICATION_CREDENTIALS env var is set to absolute path for all processes
if os.path.exists(DEFAULT_GOOGLE_CREDENTIALS_PATH):
    os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", DEFAULT_GOOGLE_CREDENTIALS_PATH)

# Verify instance directory is writable
if not os.access(INSTANCE_DIR, os.W_OK):
    import logging
    logging.getLogger(__name__).warning(f"Instance directory is not writable: {INSTANCE_DIR}")


class Config:
    """Base configuration class"""
    
    # Security
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-jwt-secret-change-in-production")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=24)
    JWT_BLACKLIST_ENABLED = True
    JWT_BLACKLIST_TOKEN_CHECKS = ['access']
    
    # Database (MySQL)
    # Format: mysql+pymysql://user:password@host:port/database_name?charset=utf8mb4 (using PyMySQL)
    # CRITICAL: charset=utf8mb4 is required for Chinese character support
    # Or: mysql://user:password@host:port/database_name?charset=utf8mb4 (if using mysqlclient)
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "mysql+pymysql://scheduling_user:scheduling_password@localhost:3306/scheduling_system?charset=utf8mb4"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 10,
        'max_overflow': 20,
        'pool_recycle': 3600,
        'pool_pre_ping': True,  # Verify connections before using
    }
    
    # CORS - Include all common development ports
    BACKEND_CORS_ORIGINS = os.getenv(
        "BACKEND_CORS_ORIGINS", 
        "http://localhost:3000,http://localhost:3001,http://localhost:5173,http://localhost:5174,http://127.0.0.1:5173,http://127.0.0.1:5174"
    ).split(",")
    
    # Celery / Redis
    # Use Redis database 0 for broker and database 1 for result backend
    CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")
    ENABLE_TEST_CELERY_TASKS = _env_bool("ENABLE_TEST_CELERY_TASKS", default=False)
    
    # Google credentials and Sheets
    GOOGLE_APPLICATION_CREDENTIALS = os.getenv(
        "GOOGLE_APPLICATION_CREDENTIALS",
        DEFAULT_GOOGLE_CREDENTIALS_PATH
    )
    GOOGLE_INPUT_URL = os.getenv(
        "GOOGLE_INPUT_URL",
        "https://docs.google.com/spreadsheets/d/1hEr8XD3ThVQQAFWi-Q0owRYxYnBRkwyqiOdbmp6zafg/edit?gid=0#gid=0",
    )
    GOOGLE_OUTPUT_URL = os.getenv(
        "GOOGLE_OUTPUT_URL",
        "https://docs.google.com/spreadsheets/d/16K1AyhmOWWW1pDbWEIOyNB5td32sXxqsKCyO06pjUSw/edit?gid=0#gid=0",
    )
    GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "YOUR_SHEET_ID_HERE")
    GOOGLE_INPUT_TAB = os.getenv("GOOGLE_INPUT_TAB", "Input")
    GOOGLE_OUTPUT_TAB = os.getenv("GOOGLE_OUTPUT_TAB", "Output")
    
    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    
    # Pagination
    DEFAULT_PAGE_SIZE = 20
    MAX_PAGE_SIZE = 100


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "mysql+pymysql://scheduling_user:scheduling_password@localhost:3306/scheduling_system?charset=utf8mb4"
    )


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "mysql+pymysql://scheduling_user:scheduling_password@mysql:3306/scheduling_system?charset=utf8mb4"
    )


class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False


# Configuration mapping
config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig
}






