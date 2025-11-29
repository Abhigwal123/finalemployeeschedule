from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from flask_migrate import Migrate


# Core extensions singletons
# SQLAlchemy - engine_options will be read from app.config['SQLALCHEMY_ENGINE_OPTIONS']
# Note: Flask-SQLAlchemy 3.x automatically reads SQLALCHEMY_ENGINE_OPTIONS from app.config
# We can also pass engine_options here as defaults, but config takes precedence
db = SQLAlchemy()
jwt = JWTManager()
cors = CORS()
migrate = Migrate()

# Ensure absolute imports like "import app.extensions" resolve to this same module.
# Without this alias Flask-SQLAlchemy could be instantiated twice (once as
# "backend.app.extensions" and once as "app.extensions"), which leads to the
# "Flask app is not registered with this SQLAlchemy instance" runtime error.
import sys as _sys
_sys.modules.setdefault("app.extensions", _sys.modules[__name__])


