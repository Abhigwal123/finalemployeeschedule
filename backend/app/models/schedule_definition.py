# Schedule Definition Model
from ..extensions import db
from datetime import datetime, date
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)

class ScheduleDefinition(db.Model):
    """
    Schedule Definition model representing scheduling configurations
    
    Schedule definitions belong to tenants and departments, and define
    the parameters, URLs, and settings for scheduling operations.
    """
    
    __tablename__ = 'schedule_definitions'
    
    # Primary Key
    scheduleDefID = db.Column(db.String(36), primary_key=True, unique=True, nullable=False)
    
    # Foreign Keys
    tenantID = db.Column(db.String(36), db.ForeignKey('tenants.tenantID'), nullable=False, index=True)
    departmentID = db.Column(db.String(36), db.ForeignKey('departments.departmentID'), nullable=False, index=True)
    
    # Fields
    scheduleName = db.Column(db.String(255), nullable=False, index=True)
    paramsSheetURL = db.Column(db.String(500), nullable=False)
    prefsSheetURL = db.Column(db.String(500), nullable=False)
    resultsSheetURL = db.Column(db.String(500), nullable=False)
    schedulingAPI = db.Column(db.String(500), nullable=False)
    remarks = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    tenant = db.relationship('Tenant', back_populates='schedule_definitions')
    department = db.relationship('Department', back_populates='schedule_definitions')
    schedule_permissions = db.relationship('SchedulePermission', foreign_keys='[SchedulePermission.scheduleDefID]', lazy='dynamic', cascade='all, delete-orphan', viewonly=False)
    schedule_job_logs = db.relationship('ScheduleJobLog', foreign_keys='[ScheduleJobLog.scheduleDefID]', lazy='dynamic', cascade='all, delete-orphan', viewonly=False)
    
    def __init__(self, scheduleDefID: str = None, tenantID: str = None, 
                 departmentID: str = None, scheduleName: str = None,
                 paramsSheetURL: str = None, prefsSheetURL: str = None,
                 resultsSheetURL: str = None, schedulingAPI: str = None,
                 remarks: str = None, **kwargs):
        """
        Initialize a new ScheduleDefinition instance
        
        Args:
            scheduleDefID: Unique schedule definition identifier (auto-generated if not provided)
            tenantID: ID of the tenant this definition belongs to
            departmentID: ID of the department this definition belongs to
            scheduleName: Name of the schedule
            paramsSheetURL: URL of the parameters Google Sheet
            prefsSheetURL: URL of the preferences Google Sheet
            resultsSheetURL: URL of the results Google Sheet
            schedulingAPI: API endpoint for scheduling
            remarks: Additional notes
            **kwargs: Additional fields
        """
        if scheduleDefID:
            self.scheduleDefID = scheduleDefID
        else:
            from app.utils.security import generate_schedule_definition_id
            self.scheduleDefID = generate_schedule_definition_id()
        
        self.tenantID = tenantID
        self.departmentID = departmentID
        self.scheduleName = scheduleName
        self.paramsSheetURL = paramsSheetURL
        self.prefsSheetURL = prefsSheetURL
        self.resultsSheetURL = resultsSheetURL
        self.schedulingAPI = schedulingAPI
        self.remarks = remarks
        super().__init__(**kwargs)
    
    def to_dict(self) -> dict:
        """
        Convert schedule definition instance to dictionary
        
        Returns:
            Dictionary representation of the schedule definition
        """
        return {
            'scheduleDefID': self.scheduleDefID,
            'tenantID': self.tenantID,
            'departmentID': self.departmentID,
            'scheduleName': self.scheduleName,
            'paramsSheetURL': self.paramsSheetURL,
            'prefsSheetURL': self.prefsSheetURL,
            'resultsSheetURL': self.resultsSheetURL,
            'schedulingAPI': self.schedulingAPI,
            'remarks': self.remarks,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at is not None and isinstance(self.created_at, (datetime, date)) else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at is not None and isinstance(self.updated_at, (datetime, date)) else None,
            'permissions_count': self.schedule_permissions.count(),
            'job_logs_count': self.schedule_job_logs.count()
        }
    
    def get_active_permissions(self) -> List['SchedulePermission']:
        """
        Get all active permissions for this schedule definition
        
        Returns:
            List of active SchedulePermission instances
        """
        return self.schedule_permissions.filter_by(canRunJob=True).all()
    
    def get_recent_job_logs(self, limit: int = 10) -> List['ScheduleJobLog']:
        """
        Get recent job logs for this schedule definition
        
        Args:
            limit: Maximum number of logs to return
            
        Returns:
            List of recent ScheduleJobLog instances
        """
        return self.schedule_job_logs.order_by(ScheduleJobLog.startTime.desc()).limit(limit).all()
    
    def get_users_with_permission(self) -> List['User']:
        """
        Get all users who have permission to run this schedule
        
        Returns:
            List of User instances with permission
        """
        permissions = self.schedule_permissions.filter_by(canRunJob=True).all()
        return [perm.user for perm in permissions]
    
    def activate(self) -> None:
        """Activate the schedule definition"""
        self.is_active = True
        self.updated_at = datetime.utcnow()
        db.session.commit()
    
    def deactivate(self) -> None:
        """Deactivate the schedule definition"""
        self.is_active = False
        self.updated_at = datetime.utcnow()
        db.session.commit()
    
    def validate_urls(self) -> dict:
        """
        Validate all URL fields
        
        Returns:
            Dictionary with validation results for each URL field
        """
        from app.utils.security import validate_url
        
        validation_results = {
            'paramsSheetURL': validate_url(self.paramsSheetURL),
            'prefsSheetURL': validate_url(self.prefsSheetURL),
            'resultsSheetURL': validate_url(self.resultsSheetURL),
            'schedulingAPI': validate_url(self.schedulingAPI)
        }
        
        return validation_results
    
    @classmethod
    def find_by_name(cls, tenant_id: str, schedule_name: str) -> 'ScheduleDefinition':
        """
        Find schedule definition by name within a tenant (case-insensitive)
        
        Args:
            tenant_id: ID of the tenant
            schedule_name: Name of the schedule to find
            
        Returns:
            ScheduleDefinition instance or None if not found
        """
        return cls.query.filter(
            cls.tenantID == tenant_id,
            db.func.lower(cls.scheduleName) == db.func.lower(schedule_name)
        ).first()
    
    @classmethod
    def get_by_tenant(cls, tenant_id: str) -> List['ScheduleDefinition']:
        """
        Get all schedule definitions for a specific tenant
        
        Args:
            tenant_id: ID of the tenant
            
        Returns:
            List of ScheduleDefinition instances
        """
        return cls.query.filter_by(tenantID=tenant_id).all()
    
    @classmethod
    def get_by_department(cls, department_id: str) -> List['ScheduleDefinition']:
        """
        Get all schedule definitions for a specific department
        
        Args:
            department_id: ID of the department
            
        Returns:
            List of ScheduleDefinition instances
        """
        return cls.query.filter_by(departmentID=department_id).all()
    
    @classmethod
    def get_active_by_tenant(cls, tenant_id: str) -> List['ScheduleDefinition']:
        """
        Get all active schedule definitions for a specific tenant
        
        Args:
            tenant_id: ID of the tenant
            
        Returns:
            List of active ScheduleDefinition instances
        """
        return cls.query.filter_by(tenantID=tenant_id, is_active=True).all()
    
    @classmethod
    def search_by_name(cls, tenant_id: str, search_term: str) -> List['ScheduleDefinition']:
        """
        Search schedule definitions by name within a tenant
        
        Args:
            tenant_id: ID of the tenant
            search_term: Search term to match against schedule names
            
        Returns:
            List of matching ScheduleDefinition instances
        """
        return cls.query.filter(
            cls.tenantID == tenant_id,
            cls.scheduleName.ilike(f'%{search_term}%')
        ).all()
    
    def __repr__(self) -> str:
        """String representation of the schedule definition"""
        return f'<ScheduleDefinition {self.scheduleDefID}: {self.scheduleName}>'
    
    def __str__(self) -> str:
        """Human-readable string representation"""
        return f'{self.scheduleName} ({self.scheduleDefID})'







