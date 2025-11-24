"""
Flask Application Entry Point
Run with: python main.py --port 8000
"""
import sys
import os
import argparse
import logging

# 🔧 CRITICAL: Pre-import google-auth BEFORE adding backend to sys.path
# This prevents our local backend/refactor/ folder from shadowing the installed google-auth package
backend_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(backend_dir)  # Parent of backend/

# Normalize paths for comparison
normalized_backend_dir = os.path.normpath(backend_dir)
normalized_paths = [os.path.normpath(p) for p in sys.path]
_backend_was_in_path = normalized_backend_dir in normalized_paths

# Temporarily remove backend_dir if it's already in sys.path
if _backend_was_in_path:
    idx = normalized_paths.index(normalized_backend_dir)
    sys.path.pop(idx)

# Pre-import google-auth while backend_dir is NOT in sys.path
try:
    import google.auth
    import google.auth.credentials
    import google.oauth2.service_account
    # Also pre-import gspread
    import gspread
    _google_auth_preloaded = True
except ImportError:
    _google_auth_preloaded = False
    # Will fail later if needed, but don't block startup

# Restore backend_dir to sys.path if it was there
if _backend_was_in_path:
    sys.path.insert(0, backend_dir)

# Add project root to sys.path so backend/ can be imported as a package
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Also add backend_dir to sys.path for refactor.* imports
# Note: google-auth is already in sys.modules, so it won't be shadowed
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from backend.app import create_app

# Configure logging for startup messages
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Check Google Sheets service availability at startup
from backend.app.utils.trace_logger import trace_startup
trace_startup("Testing Google Sheets import readiness")

logger.info("Checking Google Sheets service availability...")
try:
    from backend.app.services.google_sheets_import import _try_import_google_sheets
    success, path = _try_import_google_sheets()
    if success:
        logger.info(f"✅ Google Sheets service ready (loaded from: {path})")
        trace_startup(f"Google Sheets ready (loaded from: {path})")
    else:
        logger.warning("⚠️ Google Sheets service not available - some features may be limited")
        trace_startup("Google Sheets not ready, will retry at runtime")
except Exception as e:
    logger.warning(f"⚠️ Could not check Google Sheets service: {e}")
    trace_startup(f"Google Sheets check failed: {e}")

# Create app instance
try:
    app = create_app()
except Exception as e:
    print(f"\n❌ ERROR: Failed to create Flask app: {e}", file=sys.stderr)
    print(f"   Error type: {type(e).__name__}", file=sys.stderr)
    import traceback
    traceback.print_exc()
    sys.exit(1)


DEFAULT_HOST = os.getenv("FLASK_HOST", "localhost")  # Use 0.0.0.0 in Docker
DEFAULT_PORT = 8000


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Flask Backend Server')
    parser.add_argument('--host', type=str, default=DEFAULT_HOST, help='Host to bind to (default: localhost, use 0.0.0.0 for Docker)')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT, help='Port to run the server on (default: 8000)')
    args = parser.parse_args()
    
    try:
        print("\n" + "="*80)
        print("  Flask Backend Server Starting")
        print("="*80)
        bind_address = args.host if args.host != "0.0.0.0" else "0.0.0.0"
        print(f"\n✓ Running on http://{bind_address}:{args.port}")
        print(f"✓ API endpoints available at: http://{bind_address}:{args.port}/api/v1/")
        print("\nPress Ctrl+C to stop\n")
        print("="*80 + "\n")
        
        # In Docker, bind to 0.0.0.0 to accept connections from outside container
        # In local development, bind to localhost for security
        app.run(debug=False, host=args.host, port=args.port, use_reloader=False)
    except KeyboardInterrupt:
        print("\n\nServer stopped by user")
    except Exception as e:
        print(f"\n❌ ERROR: Server failed to start: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
