"""
WSGI Entry Point for Gunicorn
This file is used by Gunicorn to serve the Flask application in production.
"""
import os
import sys

# Add project root to Python path
backend_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(backend_dir)  # Parent of backend/

# Add paths to sys.path if not already present
if project_root not in sys.path:
    sys.path.insert(0, project_root)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# Import and create the Flask application
from backend.app import create_app

# Create the application instance
# Gunicorn will use this 'application' variable
application = create_app()

if __name__ == "__main__":
    # This allows running with: python wsgi.py (for testing)
    application.run(host="0.0.0.0", port=8000, debug=False)










