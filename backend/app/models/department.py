# Department Model
from ..extensions import db
from datetime import datetime, date
from typing import List
import logging

logger = logging.getLogger(__name__)

class Department(db.Model):
    """
    Department model representing organizational units within tenants
    
    Departments belong to tenants and can have multiple schedule definitions.
    They help organize scheduling by grouping related schedules together.
    """
    
    __tablename__ = 'departments'
    
    # Primary Key
    departmentID = db.Column(db.String(36), primary_key=True, unique=True, nullable=False)
    
    # Foreign Keys
    tenantID = db.Column(db.String(36), db.ForeignKey('tenants.tenantID'), nullable=False, index=True)
    
    # Fields
    departmentName = db.Column(db.String(255), nullable=False, index=True)
    description = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    tenant = db.relationship('Tenant', back_populates='departments')
    schedule_definitions = db.relationship('ScheduleDefinition', back_populates='department', lazy='dynamic', cascade='all, delete-orphan')
    
    def __init__(self, departmentID: str = None, tenantID: str = None, 
                 departmentName: str = None, description: str = None, **kwargs):
        """
        Initialize a new Department instance
        
        Args:
            departmentID: Unique department identifier (auto-generated if not provided)
            tenantID: ID of the tenant this department belongs to
            departmentName: Name of the department
            description: Optional description of the department
            **kwargs: Additional fields
        """
        if departmentID:
            self.departmentID = departmentID
        else:
            from app.utils.security import generate_department_id
            self.departmentID = generate_department_id()
        
        self.tenantID = tenantID
        self.departmentName = departmentName
        self.description = description
        super().__init__(**kwargs)
    
    def to_dict(self) -> dict:
        """
        Convert department instance to dictionary
        
        Returns:
            Dictionary representation of the department
        """
        return {
            'departmentID': self.departmentID,
            'tenantID': self.tenantID,
            'departmentName': self.departmentName,
            'description': self.description,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at is not None and isinstance(self.created_at, (datetime, date)) else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at is not None and isinstance(self.updated_at, (datetime, date)) else None,
            'schedule_definitions_count': self.schedule_definitions.count()
        }
    
    def get_active_schedule_definitions(self) -> List['ScheduleDefinition']:
        """
        Get all active schedule definitions for this department
        
        Returns:
            List of active ScheduleDefinition instances
        """
        return self.schedule_definitions.filter_by(is_active=True).all()
    
    def get_recent_schedule_definitions(self, limit: int = 10) -> List['ScheduleDefinition']:
        """
        Get recent schedule definitions for this department
        
        Args:
            limit: Maximum number of definitions to return
            
        Returns:
            List of recent ScheduleDefinition instances
        """
        return self.schedule_definitions.order_by(ScheduleDefinition.created_at.desc()).limit(limit).all()
    
    def activate(self) -> None:
        """Activate the department"""
        self.is_active = True
        self.updated_at = datetime.utcnow()
        db.session.commit()
    
    def deactivate(self) -> None:
        """Deactivate the department"""
        self.is_active = False
        self.updated_at = datetime.utcnow()
        db.session.commit()
    
    @classmethod
    def find_by_name(cls, tenant_id: str, department_name: str) -> 'Department':
        """
        Find department by name within a tenant (case-insensitive)
        
        Args:
            tenant_id: ID of the tenant
            department_name: Name of the department to find
            
        Returns:
            Department instance or None if not found
        """
        return cls.query.filter(
            cls.tenantID == tenant_id,
            db.func.lower(cls.departmentName) == db.func.lower(department_name)
        ).first()
    
    @classmethod
    def get_by_tenant(cls, tenant_id: str) -> List['Department']:
        """
        Get all departments for a specific tenant
        
        Args:
            tenant_id: ID of the tenant
            
        Returns:
            List of Department instances
        """
        return cls.query.filter_by(tenantID=tenant_id).all()
    
    @classmethod
    def get_active_by_tenant(cls, tenant_id: str) -> List['Department']:
        """
        Get all active departments for a specific tenant
        
        Args:
            tenant_id: ID of the tenant
            
        Returns:
            List of active Department instances
        """
        return cls.query.filter_by(tenantID=tenant_id, is_active=True).all()
    
    @classmethod
    def search_by_name(cls, tenant_id: str, search_term: str) -> List['Department']:
        """
        Search departments by name within a tenant
        
        Args:
            tenant_id: ID of the tenant
            search_term: Search term to match against department names
            
        Returns:
            List of matching Department instances
        """
        return cls.query.filter(
            cls.tenantID == tenant_id,
            cls.departmentName.ilike(f'%{search_term}%')
        ).all()
    
    def __repr__(self) -> str:
        """String representation of the department"""
        return f'<Department {self.departmentID}: {self.departmentName}>'
    
    def __str__(self) -> str:
        """Human-readable string representation"""
        return f'{self.departmentName} ({self.departmentID})'






