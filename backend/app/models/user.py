# User Model
from ..extensions import db
from datetime import datetime, date
from typing import List, Optional, TYPE_CHECKING
from sqlalchemy.orm import foreign
from sqlalchemy import func
import logging

from ..utils.role_utils import (
    format_role_for_response,
    is_client_admin_role,
    is_schedule_manager_role,
    normalize_role,
)

if TYPE_CHECKING:
    from app.models.schedule_permission import SchedulePermission
    from app.models.schedule_job_log import ScheduleJobLog

logger = logging.getLogger(__name__)

class User(db.Model):
    """
    User model representing individuals within tenant organizations
    
    Users belong to a tenant and have roles that determine their permissions
    within the scheduling system.
    """
    
    __tablename__ = 'users'
    
    # Primary Key
    userID = db.Column(db.String(36), primary_key=True, unique=True, nullable=False)
    
    # Foreign Keys
    tenantID = db.Column(db.String(36), db.ForeignKey('tenants.tenantID'), nullable=False, index=True)
    
    # Fields
    username = db.Column(db.String(100), nullable=False, unique=True, index=True)
    hashedPassword = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), nullable=False, index=True)  # admin, scheduler, viewer, etc.
    status = db.Column(db.String(20), nullable=False, default='active', index=True)  # active, inactive, suspended
    email = db.Column(db.String(255), unique=True, nullable=True, index=True)
    full_name = db.Column(db.String(255), nullable=True)
    # Employee ID from Google Sheets (e.g., "E01", "E02") - must match EmployeeMapping.sheets_identifier
    # Note: This column is added via migration - may not exist in older databases
    employee_id = db.Column(db.String(255), unique=True, nullable=True, index=True, info={'migrated': True})
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    tenant = db.relationship('Tenant', back_populates='users')
    # Explicit relationships with foreign_keys to avoid ambiguous join errors
    # SchedulePermission has two FKs to User (userID and granted_by), so we specify userID
    schedule_permissions = db.relationship(
        'SchedulePermission',
        primaryjoin='User.userID == foreign(SchedulePermission.userID)',
        foreign_keys='[SchedulePermission.userID]',
        lazy='dynamic'
    )
    schedule_job_logs = db.relationship(
        'ScheduleJobLog',
        primaryjoin='User.userID == foreign(ScheduleJobLog.runByUserID)',
        foreign_keys='[ScheduleJobLog.runByUserID]',
        lazy='dynamic'
    )
    
    def __init__(self, userID: str = None, tenantID: str = None, username: str = None, 
                 password: str = None, role: str = 'viewer', employee_id: str = None, **kwargs):
        """
        Initialize a new User instance
        
        Args:
            userID: Unique user identifier (auto-generated if not provided)
            tenantID: ID of the tenant this user belongs to
            username: Username for login
            password: Plain text password (will be hashed)
            role: User role (admin, scheduler, viewer)
            employee_id: Employee ID from Google Sheets (e.g., "E01", "E02")
            **kwargs: Additional fields
        """
        if userID:
            self.userID = userID
        else:
            from app.utils.security import generate_user_id
            self.userID = generate_user_id()
        
        self.tenantID = tenantID
        self.username = username.strip() if isinstance(username, str) else username
        self.employee_id = employee_id.strip().upper() if isinstance(employee_id, str) else employee_id
        
        if password:
            from app.utils.security import hash_password
            self.hashedPassword = hash_password(password)
        
        self.role = format_role_for_response(role) if role else role
        super().__init__(**kwargs)
    
    def set_password(self, password: str) -> None:
        """
        Set user password (hashes the password)
        
        Args:
            password: Plain text password
        """
        from app.utils.security import hash_password
        self.hashedPassword = hash_password(password)
    
    def check_password(self, password: str) -> bool:
        """
        Check if provided password matches user's password
        
        Args:
            password: Plain text password to check
            
        Returns:
            True if password matches, False otherwise
        """
        from app.utils.security import verify_password
        return verify_password(password, self.hashedPassword)
    
    def to_dict(self, include_sensitive: bool = False) -> dict:
        """
        Convert user instance to dictionary
        
        Args:
            include_sensitive: Whether to include sensitive information
            
        Returns:
            Dictionary representation of the user
        """
        data = {
            'userID': self.userID,
            'tenantID': self.tenantID,
            'username': self.username,
            'role': format_role_for_response(self.role),
            'status': self.status,
            'email': self.email,
            'full_name': self.full_name,
            'employee_id': self.employee_id,
            'created_at': self.created_at.isoformat() if self.created_at is not None and isinstance(self.created_at, (datetime, date)) else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at is not None and isinstance(self.updated_at, (datetime, date)) else None,
            'last_login': self.last_login.isoformat() if self.last_login is not None and isinstance(self.last_login, (datetime, date)) else None
        }
        
        if include_sensitive:
            data['hashedPassword'] = self.hashedPassword
        
        return data
    
    def update_last_login(self) -> None:
        """Update the last login timestamp"""
        self.last_login = datetime.utcnow()
        # Don't commit here - let the calling code handle the commit
        # This prevents session conflicts in routes
    
    def is_active(self) -> bool:
        """
        Check if user is active
        
        Returns:
            True if user status is 'active', False otherwise
        """
        return self.status == 'active'
    
    @property
    def normalized_role(self) -> str:
        """Return normalized role identifier."""
        return normalize_role(self.role)

    def is_admin(self) -> bool:
        """
        Check if user has admin role
        
        Returns:
            True if user is a ClientAdmin, False otherwise
        """
        return self.is_client_admin
    
    @property
    def is_client_admin(self) -> bool:
        """Return True if the user is a ClientAdmin-level account."""
        return is_client_admin_role(self.role)

    def is_scheduler(self) -> bool:
        """
        Check if user has scheduler role
        
        Returns:
            True if user role maps to ScheduleManager, False otherwise
        """
        return is_schedule_manager_role(self.role)
    
    def can_run_schedules(self) -> bool:
        """
        Check if user can run schedules
        
        Returns:
            True if user is admin or scheduler, False otherwise
        """
        return self.is_client_admin or is_schedule_manager_role(self.role)
    
    def get_permissions(self) -> List['SchedulePermission']:
        """
        Get all schedule permissions for this user
        
        Returns:
            List of SchedulePermission instances
        """
        from app.models.schedule_permission import SchedulePermission
        return db.session.query(SchedulePermission).filter_by(userID=self.userID).all()
    
    def get_recent_job_logs(self, limit: int = 10) -> List['ScheduleJobLog']:
        """
        Get recent job logs run by this user
        
        Args:
            limit: Maximum number of logs to return
            
        Returns:
            List of recent ScheduleJobLog instances
        """
        from app.models.schedule_job_log import ScheduleJobLog
        return db.session.query(ScheduleJobLog).filter_by(runByUserID=self.userID).order_by(ScheduleJobLog.startTime.desc()).limit(limit).all()
    
    @classmethod
    @staticmethod
    def _normalize_lookup_value(value: Optional[str]) -> Optional[str]:
        """
        Normalize lookup strings (username, employee_id) for case-insensitive comparisons.
        """
        if value is None:
            return None
        return str(value).strip().lower()
    
    @classmethod
    def find_by_username(cls, username: str) -> Optional['User']:
        """
        Find user by username
        
        Args:
            username: Username to search for
            
        Returns:
            User instance or None if not found
        """
        normalized = cls._normalize_lookup_value(username)
        if not normalized:
            return None
        return cls.query.filter(func.lower(cls.username) == normalized).first()
    
    @classmethod
    def find_by_email(cls, email: str) -> Optional['User']:
        """
        Find user by email
        
        Args:
            email: Email address to search for
            
        Returns:
            User instance or None if not found
        """
        return cls.query.filter_by(email=email).first()
    
    @classmethod
    def get_by_tenant(cls, tenant_id: str) -> List['User']:
        """
        Get all users for a specific tenant
        
        Args:
            tenant_id: ID of the tenant
            
        Returns:
            List of User instances
        """
        return cls.query.filter_by(tenantID=tenant_id).all()
    
    @classmethod
    def get_active_by_tenant(cls, tenant_id: str) -> List['User']:
        """
        Get all active users for a specific tenant
        
        Args:
            tenant_id: ID of the tenant
            
        Returns:
            List of active User instances
        """
        return cls.query.filter_by(tenantID=tenant_id, status='active').all()
    
    @classmethod
    def get_by_role(cls, role: str) -> List['User']:
        """
        Get all users with a specific role
        
        Args:
            role: Role to search for
            
        Returns:
            List of User instances with the specified role
        """
        return cls.query.filter_by(role=role).all()
    
    @classmethod
    def find_by_employee_id(cls, employee_id: str) -> Optional['User']:
        """
        Find user by employee ID
        
        Args:
            employee_id: Employee ID from Google Sheets (e.g., "E01", "E02")
            
        Returns:
            User instance or None if not found
        """
        normalized = cls._normalize_lookup_value(employee_id)
        if not normalized:
            return None
        return cls.query.filter(func.lower(cls.employee_id) == normalized).first()
    
    def __repr__(self) -> str:
        """String representation of the user"""
        return f'<User {self.userID}: {self.username}>'
    
    def __str__(self) -> str:
        """Human-readable string representation"""
        return f'{self.username} ({self.role})'