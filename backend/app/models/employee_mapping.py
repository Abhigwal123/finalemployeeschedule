"""
Employee Mapping Model
Maps database userIDs to Google Sheets employee identifiers (e.g., E01, E02, E04)
"""
from ..extensions import db
from datetime import datetime, date
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class EmployeeMapping(db.Model):
    """
    Maps database user IDs to Google Sheets employee identifiers
    
    This allows the system to match database users (e.g., user-004) 
    with their corresponding identifiers in Google Sheets (e.g., E04, 謝○穎/E04)
    """
    
    __tablename__ = 'employee_mappings'
    
    # Primary Key
    mappingID = db.Column(db.String(36), primary_key=True, unique=True, nullable=False)
    
    # Foreign Keys
    userID = db.Column(db.String(36), db.ForeignKey('users.userID'), nullable=True, unique=True, index=True)  # Nullable - can exist without user (available for registration)
    tenantID = db.Column(db.String(36), db.ForeignKey('tenants.tenantID'), nullable=False, index=True)
    
    # Mapping Fields
    sheets_identifier = db.Column(db.String(255), nullable=False, index=True)  # E04, E01, etc.
    sheets_name_id = db.Column(db.String(255), nullable=True)  # Full format: "謝○穎/E04"
    employee_sheet_name = db.Column(db.String(255), nullable=True)  # Employee name from sheet
    
    # Metadata
    schedule_def_id = db.Column(db.String(36), db.ForeignKey('schedule_definitions.scheduleDefID'), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    
    # Relationships
    user = db.relationship('User', backref='employee_mapping')
    tenant = db.relationship('Tenant')
    schedule_definition = db.relationship('ScheduleDefinition')
    
    def __init__(self, mappingID: str = None, userID: str = None, 
                 tenantID: str = None, sheets_identifier: str = None,
                 sheets_name_id: str = None, schedule_def_id: str = None, **kwargs):
        """
        Initialize a new EmployeeMapping instance
        
        Args:
            mappingID: Unique mapping identifier (auto-generated if not provided)
            userID: Database user ID (e.g., "user-004")
            tenantID: Tenant ID
            sheets_identifier: Google Sheets identifier (e.g., "E04")
            sheets_name_id: Full format from sheets (e.g., "謝○穎/E04")
            schedule_def_id: Optional schedule definition ID
        """
        if mappingID:
            self.mappingID = mappingID
        else:
            from app.utils.security import generate_user_id
            self.mappingID = generate_user_id()
        
        self.userID = userID
        self.tenantID = tenantID
        self.sheets_identifier = sheets_identifier
        self.sheets_name_id = sheets_name_id
        self.schedule_def_id = schedule_def_id
        super().__init__(**kwargs)
    
    @classmethod
    def find_by_user(cls, user_id: str, schedule_def_id: Optional[str] = None) -> Optional['EmployeeMapping']:
        """
        Find employee mapping for a user
        
        Args:
            user_id: Database user ID
            schedule_def_id: Optional schedule definition ID for filtering
            
        Returns:
            EmployeeMapping instance or None
        """
        query = cls.query.filter_by(userID=user_id, is_active=True)
        if schedule_def_id:
            query = query.filter_by(schedule_def_id=schedule_def_id)
        return query.first()
    
    @classmethod
    def find_by_sheets_identifier(cls, sheets_identifier: str, schedule_def_id: Optional[str] = None) -> Optional['EmployeeMapping']:
        """
        Find employee mapping by Google Sheets identifier
        
        Args:
            sheets_identifier: Google Sheets identifier (e.g., "E04")
            schedule_def_id: Optional schedule definition ID for filtering
            
        Returns:
            EmployeeMapping instance or None
        """
        query = cls.query.filter_by(sheets_identifier=sheets_identifier, is_active=True)
        if schedule_def_id:
            query = query.filter_by(schedule_def_id=schedule_def_id)
        return query.first()
    
    def to_dict(self) -> dict:
        """
        Convert employee mapping to dictionary
        
        Returns:
            Dictionary representation
        """
        return {
            'mappingID': self.mappingID,
            'userID': self.userID,
            'tenantID': self.tenantID,
            'sheets_identifier': self.sheets_identifier,
            'sheets_name_id': self.sheets_name_id,
            'employee_sheet_name': self.employee_sheet_name,
            'schedule_def_id': self.schedule_def_id,
            'created_at': self.created_at.isoformat() if self.created_at is not None and isinstance(self.created_at, (datetime, date)) else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at is not None and isinstance(self.updated_at, (datetime, date)) else None,
            'is_active': self.is_active
        }












