# Database Utilities
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.engine import Engine
import logging

logger = logging.getLogger(__name__)

def init_db(app):
    """Initialize database with the Flask app"""
    
    @event.listens_for(Engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        """Set SQLite pragmas for better performance and foreign key support"""
        if 'sqlite' in str(dbapi_connection):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.close()

def create_tables(app):
    """Create all database tables"""
    with app.app_context():
        from app.models import (
            Tenant, User, Department, ScheduleDefinition, 
            SchedulePermission, ScheduleJobLog
        )
        
        db.create_all()
        logger.info("Database tables created successfully")

def drop_tables(app):
    """Drop all database tables"""
    with app.app_context():
        db.drop_all()
        logger.info("Database tables dropped successfully")

def seed_initial_data(app):
    """Seed database with initial data including default users (admin/editor/viewer)"""
    with app.app_context():
        # CRITICAL: Use relative import to ensure same db instance
        from ..extensions import db
        from app.models import Tenant, User, Department
        from app.utils.security import hash_password
        
        # Check if data already exists
        if User.query.filter_by(username="admin").first():
            logger.info("Database already has default users, skipping seed")
            return
        
        # Create default tenant if it doesn't exist
        tenant = Tenant.query.filter_by(tenantID="default-tenant-001").first()
        if not tenant:
            tenant = Tenant(
                tenantID="default-tenant-001",
                tenantName="Default Organization"
            )
            db.session.add(tenant)
        
        # Create default users: admin, editor, viewer
        default_users = [
            {"username": "admin", "password": "admin123", "role": "ClientAdmin", "email": "admin@test.com", "full_name": "Client Admin"},
            {"username": "editor", "password": "editor123", "role": "ScheduleManager", "email": "editor@test.com", "full_name": "Editor User"},
            {"username": "viewer", "password": "viewer123", "role": "Department_Employee", "email": "viewer@test.com", "full_name": "Viewer User"},
            {"username": "schedulemanager", "password": "manager123", "role": "ScheduleManager", "email": "manager@test.com", "full_name": "Schedule Manager"},
            {"username": "client_admin", "password": "client123", "role": "ClientAdmin", "email": "client@test.com", "full_name": "Client Admin"},
            {"username": "employee", "password": "employee123", "role": "Department_Employee", "email": "employee@test.com", "full_name": "Employee User"}
        ]
        
        for user_data in default_users:
            existing = User.query.filter_by(username=user_data["username"]).first()
            if not existing:
                user = User(
                    tenantID=tenant.tenantID,
                    username=user_data["username"],
                    password=user_data["password"],
                    role=user_data["role"],
                    status="active",
                    email=user_data.get("email"),
                    full_name=user_data.get("full_name")
                )
                db.session.add(user)
                logger.info(f"Created default user: {user_data['username']}")
        
        # Create default department if it doesn't exist
        department = Department.query.filter_by(departmentID="default-dept-001").first()
        if not department:
            department = Department(
                departmentID="default-dept-001",
                tenantID=tenant.tenantID,
                departmentName="General"
            )
            db.session.add(department)
        
        db.session.commit()
        logger.info("Initial data seeded successfully with default users")


def seed_schedule_definitions(app):
    """Seed default schedule definitions if none exist"""
    with app.app_context():
        # CRITICAL: Use relative import to ensure same db instance
        from ..extensions import db
        from app.models import ScheduleDefinition, Tenant, Department
        
        # Check if schedule definitions already exist
        if ScheduleDefinition.query.count() > 0:
            logger.info("Schedule definitions already exist, skipping seed")
            return
        
        # Get default tenant and department
        tenant = Tenant.query.filter_by(tenantID="default-tenant-001").first()
        department = Department.query.filter_by(departmentID="default-dept-001").first()
        
        if not tenant or not department:
            logger.warning("Cannot seed schedule definitions: default tenant or department not found")
            return
        
        # Get default URLs from config or use defaults
        from flask import current_app
        default_input_url = current_app.config.get(
            "GOOGLE_INPUT_URL",
            "https://docs.google.com/spreadsheets/d/1hEr8XD3ThVQQAFWi-Q0owRYxYnBRkwyqiOdbmp6zafg/edit?gid=0#gid=0"
        )
        default_output_url = current_app.config.get(
            "GOOGLE_OUTPUT_URL",
            "https://docs.google.com/spreadsheets/d/1Imm6TJDWsoVXpf0ykMrPj4rGPfP1noagBdgoZc5Hhxg/edit?usp=sharing"
        )
        
        # Create default schedule definition
        schedule_def = ScheduleDefinition(
            tenantID=tenant.tenantID,
            departmentID=department.departmentID,
            scheduleName="Daily Auto Schedule",
            paramsSheetURL=default_input_url,
            prefsSheetURL=default_input_url,
            resultsSheetURL=default_output_url,
            schedulingAPI="/api/v1/schedule-job-logs/run",
            remarks="Default schedule definition for testing",
            is_active=True
        )
        
        db.session.add(schedule_def)
        
        # Grant permission to schedule manager users to run the default schedule
        from app.models import User, SchedulePermission
        schedule_managers = User.query.filter_by(
            tenantID=tenant.tenantID,
            role="ScheduleManager"
        ).all()
        
        for manager in schedule_managers:
            # Check if permission already exists
            existing_perm = SchedulePermission.query.filter_by(
                tenantID=tenant.tenantID,
                userID=manager.userID,
                scheduleDefID=schedule_def.scheduleDefID
            ).first()
            
            if not existing_perm:
                permission = SchedulePermission(
                    tenantID=tenant.tenantID,
                    userID=manager.userID,
                    scheduleDefID=schedule_def.scheduleDefID,
                    canRunJob=True,
                    granted_by=manager.userID,  # Self-granted for default
                    is_active=True
                )
                db.session.add(permission)
                logger.info(f"Granted permission to {manager.username} for default schedule")
        
        db.session.commit()
        logger.info(f"Created default schedule definition: {schedule_def.scheduleName}")







