# Tenant Model
from ..extensions import db
from datetime import datetime, date
from typing import List
import logging

logger = logging.getLogger(__name__)

class Tenant(db.Model):
    """
    Tenant model representing organizations/companies in the multi-tenant system
    
    Each tenant is isolated and can have its own users, departments, 
    schedule definitions, permissions, and job logs.
    """
    
    __tablename__ = 'tenants'
    
    # Primary Key
    tenantID = db.Column(db.String(36), primary_key=True, unique=True, nullable=False)
    
    # Fields
    tenantName = db.Column(db.String(255), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    
    # Relationships
    users = db.relationship('User', back_populates='tenant', lazy='dynamic', cascade='all, delete-orphan')
    departments = db.relationship('Department', back_populates='tenant', lazy='dynamic', cascade='all, delete-orphan')
    schedule_definitions = db.relationship('ScheduleDefinition', back_populates='tenant', lazy='dynamic', cascade='all, delete-orphan')
    schedule_permissions = db.relationship('SchedulePermission', back_populates='tenant', lazy='dynamic', cascade='all, delete-orphan')
    schedule_job_logs = db.relationship('ScheduleJobLog', back_populates='tenant', lazy='dynamic', cascade='all, delete-orphan')
    
    def __init__(self, tenantID: str = None, tenantName: str = None, **kwargs):
        """
        Initialize a new Tenant instance
        
        Args:
            tenantID: Unique tenant identifier (auto-generated if not provided)
            tenantName: Name of the tenant organization
            **kwargs: Additional fields
        """
        if tenantID:
            self.tenantID = tenantID
        else:
            from app.utils.security import generate_tenant_id
            self.tenantID = generate_tenant_id()
        
        self.tenantName = tenantName
        super().__init__(**kwargs)
    
    def to_dict(self) -> dict:
        """
        Convert tenant instance to dictionary
        
        Returns:
            Dictionary representation of the tenant
        """
        return {
            'tenantID': self.tenantID,
            'tenantName': self.tenantName,
            'created_at': self.created_at.isoformat() if self.created_at is not None and isinstance(self.created_at, (datetime, date)) else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at is not None and isinstance(self.updated_at, (datetime, date)) else None,
            'is_active': self.is_active,
            'users_count': self.users.count(),
            'departments_count': self.departments.count(),
            'schedule_definitions_count': self.schedule_definitions.count()
        }
    
    def get_active_users(self) -> List['User']:
        """
        Get all active users for this tenant
        
        Returns:
            List of active User instances
        """
        return self.users.filter_by(status='active').all()
    
    def get_active_departments(self) -> List['Department']:
        """
        Get all active departments for this tenant
        
        Returns:
            List of active Department instances
        """
        return self.departments.filter_by(is_active=True).all()
    
    def get_recent_job_logs(self, limit: int = 10) -> List['ScheduleJobLog']:
        """
        Get recent job logs for this tenant
        
        Args:
            limit: Maximum number of logs to return
            
        Returns:
            List of recent ScheduleJobLog instances
        """
        from app.models.schedule_job_log import ScheduleJobLog
        return self.schedule_job_logs.order_by(ScheduleJobLog.startTime.desc()).limit(limit).all()
    
    @classmethod
    def find_by_name(cls, tenant_name: str) -> 'Tenant':
        """
        Find tenant by name (case-insensitive)
        
        Args:
            tenant_name: Name of the tenant to find
            
        Returns:
            Tenant instance or None if not found
        """
        return cls.query.filter(
            db.func.lower(cls.tenantName) == db.func.lower(tenant_name)
        ).first()
    
    @classmethod
    def get_all_active(cls) -> List['Tenant']:
        """
        Get all active tenants
        
        Returns:
            List of active Tenant instances
        """
        return cls.query.filter_by(is_active=True).all()
    
    def __repr__(self) -> str:
        """String representation of the tenant"""
        return f'<Tenant {self.tenantID}: {self.tenantName}>'
    
    def __str__(self) -> str:
        """Human-readable string representation"""
        return f'{self.tenantName} ({self.tenantID})'

















