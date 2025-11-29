# Multi-Tenant Scheduling System - Flask Backend
# Main Application Factory
from dotenv import load_dotenv
load_dotenv() 
from flask import Flask, jsonify, request, make_response, Response, current_app
from .config import Config
import os
import pymysql
from .extensions import db, jwt, cors, migrate
from .utils.logger import configure_logging
from .utils.cors import get_request_origin, apply_cors_headers as apply_env_cors_headers

# Ensure the package is addressable as both "backend.app" and "app" so that
# imports like "from app.models import ..." and "from backend.app.models import ..."
# resolve to the exact same module objects. Without this alias the package can be
# loaded twice, which causes SQLAlchemy to think tables/models are defined twice.
import sys as _sys
_sys.modules.setdefault("app", _sys.modules[__name__])

pymysql.install_as_MySQLdb()
from .routes.common_routes import common_bp
from .routes.auth import auth_bp
from .routes.sysadmin_routes import sysadmin_bp
from .routes.clientadmin_routes import clientadmin_bp
from .routes.schedulemanager_routes import schedulemanager_bp
from .routes.employee_routes import employee_bp
from .routes.tenant_routes import tenant_bp
from .routes.user_routes import user_bp
from .routes.department_routes import department_bp
from .routes.schedule_definition_routes import schedule_definition_bp
from .routes.schedule_permission_routes import schedule_permission_bp
from .routes.permissions_routes import permissions_bp
from .routes.schedule_job_log_routes import schedule_job_log_bp
from .routes.google_sheets_routes import google_sheets_bp
from .routes.role_routes import role_bp
from .routes.alert_routes import alert_bp
from .routes.diagnostic_routes import diagnostic_bp
from .services.celery_tasks import bind_celery, register_periodic_tasks, register_schedule_execution_task


def register_blueprints(app: Flask) -> None:
    import sys
    import logging
    logger = logging.getLogger(__name__)
    
    # Register more specific routes FIRST to avoid conflicts
    app.register_blueprint(employee_bp, url_prefix="/api/v1/employee")  # Register BEFORE general /api/v1 routes
    app.register_blueprint(auth_bp, url_prefix="/api/v1/auth")
    # Register role-specific blueprints BEFORE common_bp to avoid route conflicts
    # Use full path to include blueprint-specific prefix
    app.register_blueprint(sysadmin_bp, url_prefix="/api/v1/sysadmin")
    app.register_blueprint(clientadmin_bp, url_prefix="/api/v1/clientadmin")
    app.register_blueprint(schedulemanager_bp, url_prefix="/api/v1/schedulemanager")
    # Register common_bp last to avoid conflicts with specific routes
    app.register_blueprint(common_bp, url_prefix="/api/v1")
    # ERD-based routes
    app.register_blueprint(tenant_bp, url_prefix="/api/v1/tenants")
    app.register_blueprint(user_bp, url_prefix="/api/v1/users")
    app.register_blueprint(department_bp, url_prefix="/api/v1/departments")
    app.register_blueprint(schedule_definition_bp, url_prefix="/api/v1/schedule-definitions")
    app.register_blueprint(schedule_permission_bp, url_prefix="/api/v1/schedule-permissions")
    app.register_blueprint(permissions_bp, url_prefix="/api/v1/permissions")
    app.register_blueprint(schedule_job_log_bp, url_prefix="/api/v1/schedule-job-logs")
    app.register_blueprint(google_sheets_bp, url_prefix="/api/v1/sheets")
    app.register_blueprint(role_bp, url_prefix="/api/v1/roles")
    app.register_blueprint(alert_bp, url_prefix="/api/v1/alerts")
    app.register_blueprint(diagnostic_bp, url_prefix="/api/v1/diagnostic")
    
    # Register schedule routes
    # CRITICAL: Wrap in try-except to catch any import-time or registration errors
    try:
        from .routes.schedule_routes import schedule_bp
        app.register_blueprint(schedule_bp, url_prefix="/api/v1/schedule")
        logger.info(f"[BLUEPRINT] Schedule blueprint registered successfully")
        logger.info(f"[BLUEPRINT] Schedule routes: {[str(rule) for rule in app.url_map.iter_rules() if 'schedule' in str(rule)]}")
    except Exception as reg_error:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"[BLUEPRINT] FAILED to register schedule blueprint: {reg_error}")
        logger.error(f"[BLUEPRINT] Traceback:\n{error_trace}")
        print(f"[BLUEPRINT] FAILED to register schedule blueprint: {reg_error}", file=sys.stderr)
        print(f"[BLUEPRINT] Traceback:\n{error_trace}", file=sys.stderr)
        sys.stderr.flush()
        # Don't raise - let app continue, but log the error


def create_app(config_object: type[Config] | None = None, *, with_celery: bool = True):
    configure_logging()

    # Load environment variables from .env if present
    # PROJECT ROOT .env is authoritative - load it first
    # --- FIXED ENV LOADER (PLACE THIS IN create_app BEFORE app = Flask()) ---
    import pathlib
    from dotenv import load_dotenv

    backend_dir = pathlib.Path(__file__).parent.parent        # backend/
    project_root = backend_dir.parent                          # Project root
    project_env = project_root / ".env"                       # PROJECT_ROOT/.env
    backend_env = backend_dir / ".env"                         # backend/.env

    # Load PROJECT_ROOT/.env first (authoritative)
    if project_env.exists():
        print(f"[ENV] Loaded PROJECT_ROOT/.env: {project_env}")
        load_dotenv(project_env, override=True)
    elif backend_env.exists():
        print(f"[ENV] Loaded backend/.env: {backend_env}")
        load_dotenv(backend_env)
    else:
        print(f"[ENV WARNING] No .env file found in PROJECT_ROOT or backend/ → Google Sheets URLs must be set via environment")
        load_dotenv()   # fallback to current directory


    app = Flask(__name__)
    app.config.from_object(config_object or Config)

    # CRITICAL: Load CORS origins from environment variables
    # Support both BACKEND_CORS_ORIGINS (from Config) and CORS_ALLOWED_ORIGINS (from env)
    # BACKEND_CORS_ORIGINS is set in Config class from BACKEND_CORS_ORIGINS env var
    backend_cors_origins = app.config.get("BACKEND_CORS_ORIGINS", [])
    cors_allowed_origins_env = os.getenv("CORS_ALLOWED_ORIGINS", "")
    
    # Parse CORS_ALLOWED_ORIGINS from env if provided (comma-separated)
    if cors_allowed_origins_env:
        cors_origins_from_env = [origin.strip() for origin in cors_allowed_origins_env.split(",") if origin.strip()]
        if cors_origins_from_env:
            app.config["CORS_ALLOWED_ORIGINS"] = cors_origins_from_env
        else:
            # Fallback to BACKEND_CORS_ORIGINS from config
            app.config["CORS_ALLOWED_ORIGINS"] = backend_cors_origins if isinstance(backend_cors_origins, list) else []
    else:
        # Use BACKEND_CORS_ORIGINS from config (already parsed from env in Config class)
        if isinstance(backend_cors_origins, list):
            # Clean up any empty strings from the list
            app.config["CORS_ALLOWED_ORIGINS"] = [origin.strip() for origin in backend_cors_origins if origin.strip()]
        else:
            app.config["CORS_ALLOWED_ORIGINS"] = []
    
    # Log CORS configuration for debugging
    import logging
    logger = logging.getLogger(__name__)
    joined_origins = ", ".join(app.config.get("CORS_ALLOWED_ORIGINS", [])) or "<none>"
    logger.info(f"[CORS INIT] Loaded CORS origins from environment: {joined_origins}")
    print(f"[CORS INIT] Loaded CORS origins from environment: {joined_origins}")
    
    # Phase 1 Diagnostic: Print resolved database URI
    logger.info(f"[DIAGNOSTIC] SQLALCHEMY_DATABASE_URI: {app.config['SQLALCHEMY_DATABASE_URI']}")
    logger.info(f"[DIAGNOSTIC] Flask working directory: {os.getcwd()}")
    print(f"[DIAGNOSTIC] SQLALCHEMY_DATABASE_URI: {app.config['SQLALCHEMY_DATABASE_URI']}")
    print(f"[DIAGNOSTIC] Flask working directory: {os.getcwd()}")

    # Fallbacks to ensure Celery uses Redis
    # Use Redis database 0 for broker and database 1 for result backend
    app.config.setdefault("CELERY_BROKER_URL", os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"))
    app.config.setdefault("CELERY_RESULT_BACKEND", os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1"))
    # Google Sheets URLs - MUST be set via environment variables (no hardcoded defaults)
    app.config["GOOGLE_INPUT_URL"] = os.getenv("GOOGLE_INPUT_URL")
    app.config["GOOGLE_OUTPUT_URL"] = os.getenv("GOOGLE_OUTPUT_URL")
    app.config.setdefault("GOOGLE_APPLICATION_CREDENTIALS", os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "service-account-creds.json"))

    
    # CRITICAL: Verify and fix database path right before initialization
    db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    if db_uri.startswith('sqlite:///'):
        # Extract and verify the database path
        # Handle both 3 slashes (sqlite:///) and 4 slashes (sqlite:////)
        if db_uri.startswith('sqlite:////'):
            # 4 slashes means absolute path (e.g., sqlite:////app/instance/db.db)
            db_path = db_uri.replace('sqlite:////', '/')
        else:
            # 3 slashes - could be relative or absolute
            db_path = db_uri.replace('sqlite:///', '')
            # If it's not an absolute path (doesn't start with /), make it relative to backend
            if not os.path.isabs(db_path):
                # Relative path - resolve relative to backend directory
                backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                db_path = os.path.join(backend_dir, db_path)
        
        # Normalize path separators for current OS
        db_path = os.path.normpath(db_path)
        db_path = os.path.abspath(db_path)
        
        # CRITICAL: If path doesn't contain 'instance', ensure we're using the instance folder
        # Get backend directory
        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        # Use instance folder for database
        instance_dir = os.path.join(backend_dir, 'instance')
        os.makedirs(instance_dir, exist_ok=True)
        
        # If the resolved path is not in instance folder, use instance folder instead
        if 'instance' not in db_path or not db_path.startswith(instance_dir):
            db_path = os.path.join(instance_dir, 'scheduling_system.db')
            db_path = os.path.abspath(db_path)
        logger.info(f"[DB INIT] Using instance folder for database: {db_path}")
        
        # Ensure directory exists
        db_dir = os.path.dirname(db_path)
        os.makedirs(db_dir, exist_ok=True)
        
        # Verify directory is writable
        if not os.access(db_dir, os.W_OK):
            logger.error(f"[DB INIT] Database directory is not writable: {db_dir}")
        else:
            logger.info(f"[DB INIT] Database directory is writable: {db_dir}")
        
        # CRITICAL FIX: Use absolute path with proper URI encoding for Windows paths with spaces
        # SQLite on Windows needs the path to be absolute and properly formatted
        # Convert Windows path to forward slashes for URI
        db_path_normalized = db_path.replace('\\', '/')
        
        # CRITICAL: Store the absolute path in config for use at request time
        # This ensures the path is always resolved correctly regardless of working directory
        app.config['DATABASE_ABSOLUTE_PATH'] = db_path
        app.config['DATABASE_BACKEND_DIR'] = backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        # Use absolute path URI - SQLite can handle spaces in paths when using forward slashes
        # Format: sqlite:///C:/Users/.../instance/scheduling_system.db
        db_uri_normalized = f"sqlite:///{db_path_normalized}"
        
        app.config['SQLALCHEMY_DATABASE_URI'] = db_uri_normalized
        logger.info(f"[DB INIT] Using absolute path URI: {db_uri_normalized}")
        logger.info(f"[DB INIT] Stored absolute path in config: {db_path}")
        
        # CRITICAL: Set SQLite connect_args for Flask-SQLAlchemy
        # SQLite needs check_same_thread=False for multi-threaded Flask apps
        # Also ensure timeout and other connection parameters
        # CRITICAL FIX: Use a custom connection creator that always uses the stored absolute path
        # Store the absolute path in closure - this ensures it's always available
        _db_absolute_path = db_path  # Store in closure for connection creator
        
        def create_connection():
            """Custom connection creator that always uses absolute path from closure"""
            import sqlite3
            
            # Always use the stored absolute path from closure
            # This is set at app initialization time and never changes
            abs_path = _db_absolute_path
            
            # CRITICAL: Ensure path is absolute and normalized
            abs_path = os.path.normpath(os.path.abspath(abs_path))
            
            # Verify path exists or can be created
            db_dir = os.path.dirname(abs_path)
            if not os.path.exists(db_dir):
                try:
                    os.makedirs(db_dir, exist_ok=True)
                    logger.info(f"[DB CONNECTION] Created database directory: {db_dir}")
                except Exception as dir_error:
                    logger.error(f"[DB CONNECTION] Failed to create directory {db_dir}: {dir_error}")
                    raise
            
            # Verify directory is writable
            if not os.access(db_dir, os.W_OK):
                logger.error(f"[DB CONNECTION] Database directory is not writable: {db_dir}")
                raise PermissionError(f"Database directory is not writable: {db_dir}")
            
            # Log connection attempt for debugging (use INFO level so it shows up)
            # This will help us see if creator is being called during requests
            import threading
            thread_id = threading.current_thread().ident
            logger.info(f"[DB CONNECTION] Creating connection (thread {thread_id}) to: {abs_path}")
            logger.info(f"[DB CONNECTION] Path exists: {os.path.exists(abs_path)}")
            logger.info(f"[DB CONNECTION] Directory writable: {os.access(db_dir, os.W_OK)}")
            logger.info(f"[DB CONNECTION] Working directory: {os.getcwd()}")
            
            # Create connection with proper parameters
            try:
                # Use absolute path directly - SQLite handles paths with spaces when using forward slashes
                # But we'll use the native path format for the OS
                conn = sqlite3.connect(
                    abs_path, 
                    check_same_thread=False, 
                    timeout=20.0,
                    isolation_level=None  # Autocommit mode for better SQLite compatibility
                )
                # Set pragmas for better performance
                conn.execute('PRAGMA foreign_keys=ON')
                conn.execute('PRAGMA journal_mode=WAL')
                conn.execute('PRAGMA synchronous=NORMAL')
                logger.info(f"[DB CONNECTION] Connection created successfully")
                return conn
            except sqlite3.OperationalError as op_error:
                # More detailed error logging for OperationalError
                logger.error(f"[DB CONNECTION] SQLite OperationalError: {op_error}")
                logger.error(f"[DB CONNECTION] Attempted path: {abs_path}")
                logger.error(f"[DB CONNECTION] Path exists: {os.path.exists(abs_path)}")
                logger.error(f"[DB CONNECTION] Directory exists: {os.path.exists(db_dir)}")
                logger.error(f"[DB CONNECTION] Directory writable: {os.access(db_dir, os.W_OK)}")
                logger.error(f"[DB CONNECTION] Working directory: {os.getcwd()}")
                logger.error(f"[DB CONNECTION] Path is absolute: {os.path.isabs(abs_path)}")
                import traceback
                logger.error(f"[DB CONNECTION] Traceback:\n{traceback.format_exc()}")
                raise
            except Exception as conn_error:
                logger.error(f"[DB CONNECTION] Failed to create connection: {conn_error}")
                logger.error(f"[DB CONNECTION] Attempted path: {abs_path}")
                logger.error(f"[DB CONNECTION] Path exists: {os.path.exists(abs_path)}")
                logger.error(f"[DB CONNECTION] Working directory: {os.getcwd()}")
                import traceback
                logger.error(f"[DB CONNECTION] Traceback:\n{traceback.format_exc()}")
                raise
        
        # CRITICAL: Set engine options with custom creator
        # The creator will be used instead of parsing the URI
        # IMPORTANT: For SQLite, we MUST use a creator function to ensure absolute paths work
        # Flask-SQLAlchemy 3.x reads SQLALCHEMY_ENGINE_OPTIONS from config automatically
        from sqlalchemy.pool import NullPool
        
        # CRITICAL FIX: For SQLite with creator, we should use a dummy URI
        # The creator function will handle the actual connection
        # But Flask-SQLAlchemy still needs a URI to determine the dialect
        # Use a placeholder URI that SQLAlchemy can parse, but creator will override
        dummy_uri = "sqlite:///"  # Minimal URI - creator will handle actual path
        
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'creator': create_connection,  # Use custom creator - this takes precedence over URI
            'poolclass': NullPool,  # Use NullPool for SQLite (no connection pooling, avoids locking issues)
            'pool_pre_ping': False,  # Not needed for NullPool
        }
        
        # CRITICAL: Store the normalized URI for reference, but creator will be used
        # Flask-SQLAlchemy needs a URI to determine dialect, but creator overrides connection creation
        app.config['SQLALCHEMY_DATABASE_URI'] = db_uri_normalized
        
        logger.info(f"[DB INIT] Creator function set: {create_connection is not None}")
        logger.info(f"[DB INIT] Creator will use absolute path: {_db_absolute_path}")
        logger.info(f"[DB INIT] Using NullPool for SQLite (recommended for SQLite)")
        logger.info(f"[DB INIT] Database URI (for dialect detection): {db_uri_normalized}")
        logger.info(f"[DB INIT] NOTE: Creator function will override URI for actual connections")
        
        logger.info(f"[DB INIT] Final database URI: {db_uri_normalized}")
        logger.info(f"[DB INIT] Database path (absolute): {db_path}")
        logger.info(f"[DB INIT] Database file exists: {os.path.exists(db_path)}")
        logger.info(f"[DB INIT] Using instance folder: {'instance' in db_path}")
        logger.info(f"[DB INIT] SQLite connect_args configured: check_same_thread=False")
        logger.info(f"[DB INIT] Engine options in config: {app.config.get('SQLALCHEMY_ENGINE_OPTIONS', 'NOT SET')}")
    
    # Initialize extensions AFTER all config is set
    # Flask-SQLAlchemy 3.1.1 should automatically read SQLALCHEMY_ENGINE_OPTIONS from config
    # But we verify it's set before calling init_app
    if 'SQLALCHEMY_ENGINE_OPTIONS' not in app.config:
        logger.warning("[DB INIT] SQLALCHEMY_ENGINE_OPTIONS not in config, setting defaults")
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'connect_args': {'check_same_thread': False, 'timeout': 20.0},
            'pool_pre_ping': True
        }
    
    # CRITICAL: Flask-SQLAlchemy 3.x reads SQLALCHEMY_ENGINE_OPTIONS from config automatically
    # We don't pass it to init_app - it reads from app.config
    engine_options = app.config.get('SQLALCHEMY_ENGINE_OPTIONS', {})
    logger.info(f"[DB INIT] Initializing Flask-SQLAlchemy (will read engine_options from config)")
    logger.info(f"[DB INIT] Engine options in config: {list(engine_options.keys())}")
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    
    # CRITICAL: Configure JWT error handlers to add CORS headers
    # JWT error handlers can intercept OPTIONS requests and return 401 without CORS headers
    from flask_jwt_extended.exceptions import (
        NoAuthorizationError, InvalidHeaderError, JWTDecodeError
    )
    # ExpiredSignatureError and InvalidTokenError come from PyJWT, not flask_jwt_extended
    # Import PyJWT with alias to avoid conflict with JWTManager (jwt)
    import jwt as pyjwt
    ExpiredSignatureError = pyjwt.ExpiredSignatureError
    InvalidTokenError = pyjwt.InvalidTokenError
    from flask import jsonify, Response
    
    @jwt.unauthorized_loader
    def unauthorized_callback(callback):
        """JWT unauthorized callback - MUST include CORS headers"""
        response = jsonify({'error': 'Authentication required', 'details': str(callback)})
        response = apply_env_cors_headers(response)
        return response, 401
    
    @jwt.invalid_token_loader
    def invalid_token_callback(callback):
        """JWT invalid token callback - MUST include CORS headers"""
        response = jsonify({'error': 'Invalid token', 'details': str(callback)})
        response = apply_env_cors_headers(response)
        return response, 422
    
    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        """JWT expired token callback - MUST include CORS headers"""
        response = jsonify({'error': 'Token has expired', 'details': 'Please login again'})
        response = apply_env_cors_headers(response)
        return response, 401
    
    # CRITICAL: Override JWT error handlers to check for OPTIONS first
    @app.errorhandler(NoAuthorizationError)
    def handle_no_auth_error(e):
        """Handle NoAuthorizationError - check if OPTIONS first"""
        try:
            if hasattr(request, 'method') and request.method == "OPTIONS":
                resp = make_response(("", 200))
                resp = apply_env_cors_headers(resp)
                return resp
        except:
            pass
        return unauthorized_callback(str(e))
    
    @app.errorhandler(InvalidTokenError)
    def handle_invalid_token_error(e):
        """Handle InvalidTokenError - check if OPTIONS first"""
        try:
            if hasattr(request, 'method') and request.method == "OPTIONS":
                resp = make_response(("", 200))
                resp = apply_env_cors_headers(resp)
                return resp
        except:
            pass
        return invalid_token_callback(str(e))
    
    @app.errorhandler(JWTDecodeError)
    def handle_jwt_decode_error(e):
        """Handle JWTDecodeError - check if OPTIONS first"""
        try:
            if hasattr(request, 'method') and request.method == "OPTIONS":
                resp = make_response(("", 200))
                resp = apply_env_cors_headers(resp)
                return resp
        except:
            pass
        return invalid_token_callback(str(e))
    
    # CRITICAL: Verify database connection and engine configuration after initialization
    # Add retry logic for connection issues
    max_retries = 3
    retry_delay = 1  # seconds
    connection_verified = False
    
    for attempt in range(max_retries):
        try:
            with app.app_context():
                from sqlalchemy import text
                from sqlalchemy.exc import OperationalError
                
                # Test the connection with retry
                try:
                    db.session.execute(text('SELECT 1'))
                    db.session.commit()
                    connection_verified = True
                    logger.info(f"[DB INIT] ✅ Database connection verified after init_app() (attempt {attempt + 1})")
                    
                    # Log engine details for debugging
                    logger.info(f"[DB INIT] Engine URL: {db.engine.url}")
                    logger.info(f"[DB INIT] Engine pool class: {type(db.engine.pool).__name__}")
                    break
                except OperationalError as op_error:
                    logger.warning(f"[DB INIT] OperationalError on attempt {attempt + 1}: {op_error}")
                    if attempt < max_retries - 1:
                        import time
                        time.sleep(retry_delay)
                        # Try to close and recreate connection
                        try:
                            db.session.close()
                        except:
                            pass
                        continue
                    else:
                        raise
        except Exception as e:
            if attempt == max_retries - 1:
                logger.error(f"[DB INIT] ❌ Database connection failed after {max_retries} attempts: {e}")
                import traceback
                error_trace = traceback.format_exc()
                logger.error(error_trace)
                
                # Try to diagnose the issue
                db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
                logger.error(f"[DB INIT] Failed DB URI: {db_uri}")
                if db_uri.startswith('sqlite:///'):
                    # Handle both 3 slashes (sqlite:///) and 4 slashes (sqlite:////)
                    if db_uri.startswith('sqlite:////'):
                        db_path = db_uri.replace('sqlite:////', '').replace('/', os.sep)
                    else:
                        db_path = db_uri.replace('sqlite:///', '').replace('/', os.sep)
                    db_path = os.path.abspath(db_path)
                    logger.error(f"[DB INIT] Failed DB path: {db_path}")
                    logger.error(f"[DB INIT] Path exists: {os.path.exists(db_path)}")
                    logger.error(f"[DB INIT] Path readable: {os.access(db_path, os.R_OK) if os.path.exists(db_path) else False}")
                    logger.error(f"[DB INIT] Directory writable: {os.access(os.path.dirname(db_path), os.W_OK) if os.path.exists(os.path.dirname(db_path)) else False}")
                    logger.error(f"[DB INIT] Working directory: {os.getcwd()}")
                    
                    # Try direct connection to see if it's a path issue
                    try:
                        import sqlite3
                        test_conn = sqlite3.connect(db_path, check_same_thread=False, timeout=20.0)
                        test_conn.execute('SELECT 1')
                        test_conn.close()
                        logger.error("[DB INIT] Direct SQLite connection works - issue is with SQLAlchemy engine configuration")
                    except Exception as direct_error:
                        logger.error(f"[DB INIT] Direct SQLite connection also fails: {direct_error}")
                        import traceback
                        logger.error(traceback.format_exc())
            else:
                import time
                time.sleep(retry_delay)

    # CRITICAL: Initialize CORS BEFORE blueprint registration
    # Flask-CORS must be initialized before routes are registered so it can wrap all routes
    # This ensures CORS headers are applied to all endpoints including /api/v1/auth/login
    import logging
    logger = logging.getLogger(__name__)
    
    # Get CORS origins from config (already loaded from environment)
    cors_origins = app.config.get("CORS_ALLOWED_ORIGINS", [])
    
    # CRITICAL: Configure CORS with specific origins (NOT wildcard) to support withCredentials
    # Wildcard (*) cannot be used with credentials, so we must specify exact origins
    # Initialize CORS BEFORE blueprints so it wraps all registered routes
    cors.init_app(
        app,
        supports_credentials=True,
        origins=cors_origins,
        expose_headers=["Content-Type", "Authorization"],
        allow_headers=["Content-Type", "Authorization"],
        methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    )
    
    joined_origins = ", ".join(cors_origins) or "<none>"
    logger.info(f"[CORS] Flask-CORS initialized BEFORE blueprints with origins: {joined_origins}")
    print(f"[CORS] Flask-CORS initialized BEFORE blueprints with origins: {joined_origins}")

    # CRITICAL: Add global preflight handler BEFORE blueprint registration
    # This intercepts OPTIONS requests before any route logic runs, preventing 500 errors
    # Note: Flask-CORS should handle OPTIONS automatically, but this provides a fallback
    @app.before_request
    def handle_preflight():
        """Global CORS preflight handler - runs FIRST before any route logic or JWT checks"""
        if request.method == "OPTIONS":
            response = make_response("", 200)
            origin = request.headers.get("Origin")
            allowed = app.config.get("CORS_ALLOWED_ORIGINS", []) or []
            if origin and origin in allowed:
                response.headers["Access-Control-Allow-Origin"] = origin

            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
            return response
        return None

    # Register blueprints AFTER CORS is initialized
    # This ensures Flask-CORS wraps all registered routes
    register_blueprints(app)
    
    # Global fallback OPTIONS handler for any unmatched routes
    # This catches any OPTIONS requests that weren't handled by blueprint handlers
    # Register with lower priority to avoid conflicts with blueprint routes
    @app.route("/<path:path>", methods=["OPTIONS"])
    def handle_options_fallback(path):
        """Global fallback OPTIONS handler for any unmatched routes"""
        try:
            logger.info(f"[TRACE] ✅ OPTIONS handler active for /{path}")
            print(f"[TRACE] ✅ OPTIONS handler active for /{path}")
            from flask import make_response
            response = make_response(("", 200))
            response = apply_env_cors_headers(response)
            return response
        except Exception as e:
            logger.error(f"[ERROR] Fallback OPTIONS handler failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            # Return minimal response even on error
            from flask import Response
            resp = Response("", status=200)
            resp = apply_env_cors_headers(resp)
            return resp
    
    # Universal CORS safeguard - ensures headers are always correct (overrides any wildcard "*")
    @app.after_request
    def after_request_cors(response):
        """Universal CORS handler - ALWAYS sets correct origin (never wildcard) for all responses"""
        return apply_env_cors_headers(response)
    
    # CRITICAL: Verify database connection at startup (runs immediately after app creation)
    # This ensures database is accessible before any requests
    with app.app_context():
        try:
            from sqlalchemy import text
            # db is already imported at top of file from app.extensions, so we can use it directly
            
            # Get database configuration
            db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', 'NOT SET')
            db_path = app.config.get('DATABASE_ABSOLUTE_PATH', 'NOT SET')
            
            logger.info("=" * 80)
            logger.info("[STARTUP] Verifying database connection at app creation...")
            logger.info(f"[STARTUP] Database URI: {db_uri}")
            logger.info(f"[STARTUP] Database absolute path: {db_path}")
            logger.info(f"[STARTUP] Working directory: {os.getcwd()}")
            
            # Test connection
            db.session.execute(text('SELECT 1'))
            db.session.commit()
            
            # Check engine configuration
            engine = db.engine
            logger.info(f"[STARTUP] Engine URL: {engine.url}")
            logger.info(f"[STARTUP] Engine pool class: {type(engine.pool).__name__}")
            
            # Verify creator is being used
            if hasattr(engine.pool, '_creator'):
                logger.info(f"[STARTUP] ✓ Engine pool has creator function")
            else:
                logger.warning(f"[STARTUP] ⚠ Engine pool does NOT have creator function")
            
            # Test User query to ensure tables exist
            from .models import User
            # Try to query users - handle case where employee_id column doesn't exist yet (migration pending)
            try:
                user_count = User.query.count()
            except Exception as db_error:
                if 'employee_id' in str(db_error):
                    logger.warning("[STARTUP] employee_id column not found - migration may be pending. Run: alembic upgrade head")
                    # Try query without employee_id by using raw SQL
                    from sqlalchemy import text
                    result = db.session.execute(text("SELECT COUNT(*) FROM users"))
                    user_count = result.scalar()
                    logger.info(f"[STARTUP] User count (via raw SQL): {user_count}")
                else:
                    raise
            
            logger.info(f"[STARTUP] ✓ Database connection verified")
            logger.info(f"[STARTUP] ✓ User table accessible, {user_count} users found")
            logger.info("=" * 80)
            
            # Log CORS configuration
            joined_origins = ", ".join(app.config.get("CORS_ALLOWED_ORIGINS", [])) or "<none>"
            logger.info(f"[CORS] Backend enforcing origins: {joined_origins}")
            print(f"[CORS] Backend enforcing origins: {joined_origins}")
            
        except Exception as e:
            logger.error("=" * 80)
            logger.error(f"[STARTUP] ❌ Database connection verification FAILED: {e}")
            logger.error(f"[STARTUP] Error type: {type(e).__name__}")
            import traceback
            logger.error(f"[STARTUP] Traceback:\n{traceback.format_exc()}")
            
            # Diagnostic information
            db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', 'NOT SET')
            db_path = app.config.get('DATABASE_ABSOLUTE_PATH', 'NOT SET')
            logger.error(f"[STARTUP] Database URI: {db_uri}")
            logger.error(f"[STARTUP] Database path: {db_path}")
            if db_path != 'NOT SET':
                logger.error(f"[STARTUP] Path exists: {os.path.exists(db_path)}")
                logger.error(f"[STARTUP] Directory exists: {os.path.exists(os.path.dirname(db_path))}")
                logger.error(f"[STARTUP] Directory writable: {os.access(os.path.dirname(db_path), os.W_OK)}")
            logger.error(f"[STARTUP] Working directory: {os.getcwd()}")
            logger.error("=" * 80)
            # Don't raise - let the app start, but log the error
    
    # Add global error handler for OperationalError (database connection issues)
    @app.errorhandler(Exception)
    def handle_operational_error(error):
        """Global error handler for database OperationalError and other exceptions
        
        TEMPORARILY MODIFIED: Disabled early returns to expose real exceptions
        """
        from sqlalchemy.exc import OperationalError
        from flask import request, Response
        import logging
        import traceback
        import sys
        
        logger = logging.getLogger(__name__)
        
        # CRITICAL: Get full traceback FIRST before any other operations
        error_trace = traceback.format_exc()
        
        # CRITICAL: Log that error handler was called with FULL TRACEBACK
        try:
            error_path = getattr(request, 'path', 'UNKNOWN') if hasattr(request, 'path') else 'UNKNOWN'
            error_method = getattr(request, 'method', 'UNKNOWN') if hasattr(request, 'method') else 'UNKNOWN'
            logger.error("=" * 80)
            logger.error(f"[ERROR_HANDLER] Called for {error_method} {error_path}")
            logger.error(f"[ERROR_HANDLER] Error Type: {type(error).__name__}")
            logger.error(f"[ERROR_HANDLER] Error Message: {str(error)}")
            logger.error(f"[ERROR_HANDLER] Full Traceback:")
            logger.error(error_trace)
            logger.error("=" * 80)
            
            # Also print to console/stderr for immediate visibility
            print("=" * 80, file=sys.stderr)
            print(f"[ERROR_HANDLER] Called for {error_method} {error_path}", file=sys.stderr)
            print(f"[ERROR_HANDLER] Error Type: {type(error).__name__}", file=sys.stderr)
            print(f"[ERROR_HANDLER] Error Message: {str(error)}", file=sys.stderr)
            print(f"[ERROR_HANDLER] Full Traceback:", file=sys.stderr)
            print(error_trace, file=sys.stderr)
            print("=" * 80, file=sys.stderr)
            sys.stderr.flush()
        except Exception as log_err:
            logger.error(f"[ERROR_HANDLER] Error logging failed: {log_err}")
            logger.error(f"[ERROR_HANDLER] Original error: {type(error).__name__}: {str(error)}")
            logger.error(f"[ERROR_HANDLER] Original traceback:\n{error_trace}")
            print(f"[ERROR_HANDLER] Error logging failed: {log_err}", file=sys.stderr)
            print(f"[ERROR_HANDLER] Original error: {type(error).__name__}: {str(error)}", file=sys.stderr)
            print(f"[ERROR_HANDLER] Original traceback:\n{error_trace}", file=sys.stderr)
            sys.stderr.flush()
        
        # Check if it's an OperationalError
        if isinstance(error, OperationalError):
            error_msg = str(error)
            error_trace = traceback.format_exc()
            
            logger.error(f"[OPERATIONAL_ERROR] {error_msg}")
            logger.error(f"[OPERATIONAL_ERROR] Request: {request.method} {request.path}")
            logger.error(f"[OPERATIONAL_ERROR] Traceback:\n{error_trace}")
            
            # Get database diagnostics
            db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
            db_path = None
            if db_uri.startswith('sqlite:///'):
                if db_uri.startswith('sqlite:////'):
                    db_path = db_uri.replace('sqlite:////', '').replace('/', os.sep)
                else:
                    db_path = db_uri.replace('sqlite:///', '').replace('/', os.sep)
                db_path = os.path.abspath(db_path)
            
            # Try to recover by closing and reopening connection
            try:
                db.session.close()
                db.session.remove()
                logger.info("[OPERATIONAL_ERROR] Closed and removed database session")
            except:
                pass
            
            # Return detailed error response
            error_response = {
                'error': 'Database connection error',
                'message': error_msg,
                'error_type': 'OperationalError',
                'database_uri': db_uri,
                'database_path': db_path,
                'database_path_exists': os.path.exists(db_path) if db_path else None,
                'working_directory': os.getcwd()
            }
            
            if app.config.get('DEBUG'):
                error_response['traceback'] = error_trace
            
            return jsonify(error_response), 500
        
        # TEMPORARILY DISABLED: All early returns for /schedule paths
        # We need to see the actual exception to fix the root cause
        
        # For other exceptions, log and return generic error
        # (error_trace already captured at the start of the function)
        
        # Always include error details for debugging (even in production for now)
        try:
            error_path = request.path if hasattr(request, 'path') else 'unknown'
            error_method = request.method if hasattr(request, 'method') else 'unknown'
        except:
            error_path = 'unknown'
            error_method = 'unknown'
        
        # CRITICAL: Always include traceback - truncate if too long but always include
        traceback_in_response = error_trace
        if len(traceback_in_response) > 10000:
            traceback_in_response = traceback_in_response[:10000] + "\n... (truncated)"
        
        error_response = {
            'error': 'An internal error occurred',
            'error_type': type(error).__name__,
            'message': str(error) if len(str(error)) < 2000 else str(error)[:2000] + '...',
            'path': error_path,
            'method': error_method,
            'traceback': traceback_in_response,  # CRITICAL: Always include traceback
            'debug_note': 'ERROR_HANDLER_WAS_CALLED_VERIFY_TRACEBACK_ABOVE',
            'handler_marker': 'GLOBAL_ERROR_HANDLER_EXECUTED'
        }
        
        logger.error(f"[ERROR_HANDLER] Final response - Error: {type(error).__name__}: {str(error)}")
        logger.error(f"[ERROR_HANDLER] Final response - Path: {error_path}, Method: {error_method}")
        logger.error(f"[ERROR_HANDLER] Traceback length: {len(traceback_in_response)} chars")
        logger.error(f"[ERROR_HANDLER] Full traceback:\n{traceback_in_response}")
        
        # Add CORS headers to error response
        try:
            response = jsonify(error_response)
            response = apply_env_cors_headers(response)
            
            # CRITICAL: Verify traceback is in response by checking response data
            import json as json_module
            try:
                response_data = json_module.loads(response.get_data(as_text=True))
                if 'traceback' not in response_data:
                    logger.error("[ERROR_HANDLER] WARNING: traceback missing from response data!")
                    # Force add it
                    response_data['traceback'] = traceback_in_response
                    response = jsonify(response_data)
                    response = apply_env_cors_headers(response)
            except:
                pass
            
            return response, 500
        except Exception as json_err:
            # If jsonify fails, return minimal response with traceback as string
            logger.error(f"[ERROR_HANDLER] jsonify failed: {json_err}")
            import json as json_module
            try:
                # Try to create JSON manually
                error_dict = {
                    'error': 'An internal error occurred',
                    'error_type': type(error).__name__,
                    'message': str(error)[:500],
                    'traceback': traceback_in_response
                }
                response_text = json_module.dumps(error_dict)
                response = Response(response_text, status=500, mimetype='application/json')
            except:
                # Last resort - plain text with traceback
                response = Response(
                    f"Error: {type(error).__name__}: {str(error)}\n\nTraceback:\n{traceback_in_response}",
                    status=500,
                    mimetype='text/plain'
                )
            response = apply_env_cors_headers(response)
            return response
    
    # Add request logging middleware to see all requests
    # This runs AFTER handle_preflight, so OPTIONS requests are already handled
    @app.before_request
    def log_request_info():
        from flask import request
        import logging
        import sys
        logger = logging.getLogger(__name__)
        
        # Skip if this is an OPTIONS request (already handled by handle_preflight)
        if request.method == "OPTIONS":
            return None  # Let the request continue (already handled)
        
        try:
            # Get query parameters
            query_params = dict(request.args) if request.args else {}
            query_str = f"?{request.query_string.decode()}" if request.query_string else ""
            
            # Log request details - use flush=True to ensure immediate output
            logger.info(f"[REQUEST] {request.method} {request.path}{query_str} from {request.remote_addr}")
            print(f"[API] {request.method} {request.path}{query_str} from {request.remote_addr}", flush=True)
            sys.stdout.flush()  # Force flush
            
            # Log query parameters if present
            if query_params:
                logger.info(f"[REQUEST] Query params: {query_params}")
                print(f"[API] Query params: {query_params}", flush=True)
                sys.stdout.flush()
            
            # Log headers for debugging (Authorization header masked)
            auth_header = request.headers.get('Authorization', None)
            if auth_header:
                masked_auth = f"{auth_header[:20]}..." if len(auth_header) > 20 else auth_header
                logger.info(f"[REQUEST] Authorization: {masked_auth}")
            
            # Log request body for POST/PUT/PATCH
            if request.method in ['POST', 'PUT', 'PATCH']:
                logger.info(f"[REQUEST] Content-Type: {request.content_type}")
                try:
                    if request.is_json:
                        json_data = request.get_json(silent=True)
                        if json_data:
                            # Log JSON keys (not full data for security)
                            logger.info(f"[REQUEST] JSON keys: {list(json_data.keys())}")
                            print(f"[API] JSON keys: {list(json_data.keys())}", flush=True)
                            sys.stdout.flush()
                    elif request.data:
                        data_preview = request.data[:200].decode('utf-8', errors='ignore') if len(request.data) > 0 else ''
                        if data_preview:
                            logger.info(f"[REQUEST] Data preview: {data_preview[:100]}...")
                except Exception as json_err:
                    logger.warning(f"[REQUEST] Could not parse request data: {json_err}")
        except Exception as log_err:
            # Don't let logging errors break the request
            logger.error(f"[REQUEST] Error in request logging: {log_err}")
            print(f"[API] Error in request logging: {log_err}", flush=True)
            sys.stdout.flush()
    
    @app.after_request
    def log_response_info(response):
        from flask import request
        import logging
        import sys
        logger = logging.getLogger(__name__)
        
        # Skip logging for OPTIONS (already logged in handle_preflight)
        if request.method == "OPTIONS":
            return response
        
        try:
            # Get response size
            response_size = len(response.get_data())
            
            # Log response details - use flush=True to ensure immediate output
            status_emoji = "✅" if response.status_code < 400 else "❌"
            logger.info(f"[RESPONSE] {status_emoji} {request.method} {request.path} -> {response.status_code} ({response_size} bytes)")
            print(f"[API] {status_emoji} {request.method} {request.path} -> {response.status_code} ({response_size} bytes)", flush=True)
            sys.stdout.flush()  # Force flush
            
            # Log error details for failed requests
            if response.status_code >= 400:
                try:
                    import json
                    response_data = response.get_data(as_text=True)
                    if response_data:
                        try:
                            error_data = json.loads(response_data)
                            logger.error(f"[RESPONSE ERROR] {error_data}")
                            print(f"[API ERROR] {error_data}", flush=True)
                            sys.stdout.flush()
                        except:
                            # Not JSON, log as text (truncated)
                            error_preview = response_data[:200] if len(response_data) > 200 else response_data
                            logger.error(f"[RESPONSE ERROR] {error_preview}")
                            print(f"[API ERROR] {error_preview}", flush=True)
                            sys.stdout.flush()
                except Exception as err:
                    logger.warning(f"[RESPONSE] Could not parse error response: {err}")
            
            # Log successful API responses (briefly)
            elif response.status_code == 200 and request.path.startswith('/api/'):
                logger.debug(f"[RESPONSE] Success: {request.method} {request.path}")
        except Exception as log_err:
            logger.error(f"[RESPONSE] Error in response logging: {log_err}")
            print(f"[API] Error in response logging: {log_err}", flush=True)
            sys.stdout.flush()
        
        return response
    
    # Add root endpoint
    @app.route("/")
    def index():
        """Root endpoint showing API information"""
        return jsonify({
            "message": "Smart Scheduling API is running",
            "version": "2.0.0",
            "health": "/api/v1/health",
            "routes": "/api/v1/routes",
            "auth": {
                "register_get_help": "/api/v1/auth/register",
                "register_post": "/api/v1/auth/register",
                "login_post": "/api/v1/auth/login"
            },
            "documentation": "See /api/v1/routes for all available endpoints"
        })

    # Create DB tables and initialize default data
    with app.app_context():
        try:
            db.create_all()
            # Initialize default users on first run
            from .utils.db import seed_initial_data, seed_schedule_definitions
            seed_initial_data(app)
            # Initialize default schedule definitions on first run
            seed_schedule_definitions(app)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Database initialization warning: {e}")
        
        # Auto-validate and regenerate Google Sheet outputs on startup
        try:
            from .services.auto_regeneration_service import AutoRegenerationService
            import logging
            logger = logging.getLogger(__name__)
            
            logger.info("[SCHEDULE] Starting auto-validation of Google Sheet outputs...")
            
            # Get credentials path from config
            creds_path = app.config.get('GOOGLE_APPLICATION_CREDENTIALS', 'service-account-creds.json')
            
            # Initialize auto-regeneration service
            auto_regen_service = AutoRegenerationService(credentials_path=creds_path)
            
            # Validate and regenerate all schedule definitions (we're already in app context)
            validation_results = auto_regen_service.validate_and_regenerate_all(None)
            
            logger.info(f"[SCHEDULE] Auto-validation complete: {validation_results['validated']} validated, "
                       f"{validation_results['regenerated']} regenerated")
            
            if validation_results['errors']:
                logger.warning(f"[SCHEDULE] Auto-validation had {len(validation_results['errors'])} errors")
                for error in validation_results['errors']:
                    logger.warning(f"[SCHEDULE] Validation error: {error}")
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"[SCHEDULE] Auto-validation warning (non-critical): {e}")
            # Don't fail startup if auto-validation fails
            import traceback
            logger.debug(traceback.format_exc())

    # Init Celery and bind tasks
    if with_celery:
        from .celery_app import init_celery_app

        celery_app = init_celery_app(app)
        bind_celery(celery_app)
        register_periodic_tasks(celery_app)

        import logging
        logger = logging.getLogger(__name__)
        registered_tasks = list(celery_app.tasks.keys())
        logger.info(f"[CELERY] ✅ Celery initialized with {len(registered_tasks)} registered tasks")
        logger.info(f"[CELERY] Key tasks: {[t for t in registered_tasks if 'schedule' in t.lower() or 'execute' in t.lower()]}")

    return app

# Legacy factory removed to prevent side-effects