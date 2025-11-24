# Schedule Permission Model
from ..extensions import db
from datetime import datetime, timedelta, date
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)

class SchedulePermission(db.Model):
    """
    Schedule Permission model representing user permissions for schedule definitions
    
    Permissions control which users can run specific schedule definitions.
    Each permission links a user to a schedule definition with a boolean flag
    indicating whether the user can run the job.
    """
    
    __tablename__ = 'schedule_permissions'
    
    # Primary Key
    permissionID = db.Column(db.String(36), primary_key=True, unique=True, nullable=False)
    
    # Foreign Keys
    tenantID = db.Column(db.String(36), db.ForeignKey('tenants.tenantID'), nullable=False, index=True)
    userID = db.Column(db.String(36), db.ForeignKey('users.userID'), nullable=False, index=True)
    scheduleDefID = db.Column(db.String(36), db.ForeignKey('schedule_definitions.scheduleDefID'), nullable=False, index=True)
    
    # Fields
    canRunJob = db.Column(db.Boolean, nullable=False, default=False, index=True)
    granted_by = db.Column(db.String(36), db.ForeignKey('users.userID'), nullable=True)
    granted_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    tenant = db.relationship('Tenant', back_populates='schedule_permissions')
    user = db.relationship('User', foreign_keys=[userID], viewonly=True)
    schedule_definition = db.relationship('ScheduleDefinition', back_populates='schedule_permissions', foreign_keys=[scheduleDefID])
    granted_by_user = db.relationship('User', foreign_keys=[granted_by], viewonly=True)
    
    # Unique constraint to prevent duplicate permissions
    __table_args__ = (
        db.UniqueConstraint('userID', 'scheduleDefID', name='unique_user_schedule_permission'),
    )
    
    def __init__(self, permissionID: str = None, tenantID: str = None,
                 userID: str = None, scheduleDefID: str = None,
                 canRunJob: bool = False, granted_by: str = None, **kwargs):
        """
        Initialize a new SchedulePermission instance
        
        Args:
            permissionID: Unique permission identifier (auto-generated if not provided)
            tenantID: ID of the tenant
            userID: ID of the user this permission is granted to
            scheduleDefID: ID of the schedule definition
            canRunJob: Whether the user can run the job
            granted_by: ID of the user who granted this permission
            **kwargs: Additional fields
        """
        if permissionID:
            self.permissionID = permissionID
        else:
            from app.utils.security import generate_permission_id
            self.permissionID = generate_permission_id()
        
        self.tenantID = tenantID
        self.userID = userID
        self.scheduleDefID = scheduleDefID
        self.canRunJob = canRunJob
        self.granted_by = granted_by
        super().__init__(**kwargs)
    
    def to_dict(self) -> dict:
        """
        Convert schedule permission instance to dictionary
        
        Returns:
            Dictionary representation of the schedule permission
        """
        return {
            'permissionID': self.permissionID,
            'tenantID': self.tenantID,
            'userID': self.userID,
            'scheduleDefID': self.scheduleDefID,
            'canRunJob': self.canRunJob,
            'granted_by': self.granted_by,
            'granted_at': self.granted_at.isoformat() if self.granted_at is not None and isinstance(self.granted_at, (datetime, date)) else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at is not None and isinstance(self.expires_at, (datetime, date)) else None,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at is not None and isinstance(self.created_at, (datetime, date)) else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at is not None and isinstance(self.updated_at, (datetime, date)) else None,
            'user': self.user.to_dict() if self.user else None,
            'schedule_definition': self.schedule_definition.to_dict() if self.schedule_definition else None
        }
    
    def grant_permission(self, granted_by_user_id: str = None) -> None:
        """
        Grant permission to run the schedule
        
        Args:
            granted_by_user_id: ID of the user granting the permission
        """
        self.canRunJob = True
        self.granted_by = granted_by_user_id
        self.granted_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        db.session.commit()
    
    def revoke_permission(self) -> None:
        """Revoke permission to run the schedule"""
        self.canRunJob = False
        self.updated_at = datetime.utcnow()
        db.session.commit()
    
    def activate(self) -> None:
        """Activate the permission"""
        self.is_active = True
        self.updated_at = datetime.utcnow()
        db.session.commit()
    
    def deactivate(self) -> None:
        """Deactivate the permission"""
        self.is_active = False
        self.updated_at = datetime.utcnow()
        db.session.commit()
    
    def is_expired(self) -> bool:
        """
        Check if the permission has expired
        
        Returns:
            True if permission has expired, False otherwise
        """
        if not self.expires_at:
            return False
        return datetime.utcnow() > self.expires_at
    
    def is_valid(self) -> bool:
        """
        Check if the permission is valid (active and not expired)
        
        Returns:
            True if permission is valid, False otherwise
        """
        return self.is_active and not self.is_expired() and self.canRunJob
    
    def set_expiration(self, days: int) -> None:
        """
        Set expiration date for the permission
        
        Args:
            days: Number of days from now when permission expires
        """
        self.expires_at = datetime.utcnow() + timedelta(days=days)
        self.updated_at = datetime.utcnow()
        db.session.commit()
    
    @classmethod
    def find_by_user_and_schedule(cls, user_id: str, schedule_def_id: str) -> Optional['SchedulePermission']:
        """
        Find permission for a specific user and schedule definition
        
        Args:
            user_id: ID of the user
            schedule_def_id: ID of the schedule definition
            
        Returns:
            SchedulePermission instance or None if not found
        """
        return cls.query.filter_by(
            userID=user_id,
            scheduleDefID=schedule_def_id
        ).first()
    
    @classmethod
    def get_by_user(cls, user_id: str) -> List['SchedulePermission']:
        """
        Get all permissions for a specific user
        
        Args:
            user_id: ID of the user
            
        Returns:
            List of SchedulePermission instances
        """
        return cls.query.filter_by(userID=user_id).all()
    
    @classmethod
    def get_by_schedule(cls, schedule_def_id: str) -> List['SchedulePermission']:
        """
        Get all permissions for a specific schedule definition
        
        Args:
            schedule_def_id: ID of the schedule definition
            
        Returns:
            List of SchedulePermission instances
        """
        return cls.query.filter_by(scheduleDefID=schedule_def_id).all()
    
    @classmethod
    def sync_for_user(cls, user_id: str, entries: List[dict]) -> dict:
        """
        Replace all permissions for a user with the provided entries.
        
        Args:
            user_id: Target user ID
            entries: List of permission payloads containing at minimum scheduleDefID
        
        Returns:
            Summary dictionary containing created/updated/removed counts.
        """
        if not user_id:
            raise ValueError("user_id is required")
        
        from app.models import User  # Local import to avoid circular dependency at module load
        user = User.query.get(user_id)
        if not user:
            raise ValueError("User not found")
        
        entries = entries or []
        sanitized_entries = {}
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            schedule_def_id = entry.get('scheduleDefID') or entry.get('scheduleDefId')
            if not schedule_def_id:
                continue
            sanitized_entries[schedule_def_id] = entry
        
        existing_permissions = {
            perm.scheduleDefID: perm for perm in cls.query.filter_by(userID=user_id).all()
        }
        
        created = 0
        updated = 0
        removed = 0
        
        def parse_bool(value, default=True):
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                lowered = value.strip().lower()
                if lowered in ('true', '1', 'yes', 'y'):
                    return True
                if lowered in ('false', '0', 'no', 'n'):
                    return False
            return default
        
        def parse_datetime(value):
            if isinstance(value, datetime):
                return value
            if isinstance(value, str):
                try:
                    return datetime.fromisoformat(value)
                except ValueError:
                    return None
            return None
        
        for schedule_def_id, entry in sanitized_entries.items():
            permission = existing_permissions.get(schedule_def_id)
            can_run = parse_bool(entry.get('canRunJob'), True if not permission else permission.canRunJob)
            is_active = parse_bool(entry.get('is_active'), True if not permission else permission.is_active)
            expires_at = parse_datetime(entry.get('expires_at'))
            granted_by = entry.get('granted_by')
            tenant_id = entry.get('tenantID') or user.tenantID
            
            if permission:
                permission.canRunJob = can_run
                permission.is_active = is_active
                permission.granted_by = granted_by or permission.granted_by
                if expires_at:
                    permission.expires_at = expires_at
                permission.updated_at = datetime.utcnow()
                updated += 1
            else:
                permission = cls(
                    tenantID=tenant_id,
                    userID=user_id,
                    scheduleDefID=schedule_def_id,
                    canRunJob=can_run,
                    granted_by=granted_by
                )
                permission.is_active = is_active
                if expires_at:
                    permission.expires_at = expires_at
                db.session.add(permission)
                existing_permissions[schedule_def_id] = permission
                created += 1
        
        for schedule_def_id, permission in existing_permissions.items():
            if schedule_def_id not in sanitized_entries:
                db.session.delete(permission)
                removed += 1
        
        return {
            'created': created,
            'updated': updated,
            'removed': removed,
            'total': created + updated
        }
    
    @classmethod
    def get_by_tenant(cls, tenant_id: str) -> List['SchedulePermission']:
        """
        Get all permissions for a specific tenant
        
        Args:
            tenant_id: ID of the tenant
            
        Returns:
            List of SchedulePermission instances
        """
        return cls.query.filter_by(tenantID=tenant_id).all()
    
    @classmethod
    def get_active_by_user(cls, user_id: str) -> List['SchedulePermission']:
        """
        Get all active permissions for a specific user
        
        Args:
            user_id: ID of the user
            
        Returns:
            List of active SchedulePermission instances
        """
        return cls.query.filter_by(userID=user_id, is_active=True).all()
    
    @classmethod
    def get_valid_by_user(cls, user_id: str) -> List['SchedulePermission']:
        """
        Get all valid (active and not expired) permissions for a specific user
        
        Args:
            user_id: ID of the user
            
        Returns:
            List of valid SchedulePermission instances
        """
        permissions = cls.query.filter_by(userID=user_id, is_active=True, canRunJob=True).all()
        return [perm for perm in permissions if not perm.is_expired()]
    
    @classmethod
    def cleanup_expired(cls) -> int:
        """
        Clean up expired permissions by deactivating them
        
        Returns:
            Number of permissions deactivated
        """
        expired_permissions = cls.query.filter(
            cls.expires_at.isnot(None),
            cls.expires_at < datetime.utcnow(),
            cls.is_active == True
        ).all()
        
        count = 0
        for perm in expired_permissions:
            perm.deactivate()
            count += 1
        
        return count
    
    def __repr__(self) -> str:
        """String representation of the schedule permission"""
        return f'<SchedulePermission {self.permissionID}: User {self.userID} -> Schedule {self.scheduleDefID}>'
    
    def __str__(self) -> str:
        """Human-readable string representation"""
        return f'Permission: {self.user.username if self.user else self.userID} -> {self.schedule_definition.scheduleName if self.schedule_definition else self.scheduleDefID}'







