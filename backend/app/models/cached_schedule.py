"""
Cached Schedule Model
Stores individual schedule entries (date + shift) for employees in database
Used for fast dashboard loading without hitting Google Sheets API
"""
from ..extensions import db
from datetime import datetime, date
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class CachedSchedule(db.Model):
    """
    Caches individual schedule entries for employees
    
    Stores date, shift_type, time_range for each employee for each schedule definition
    """
    
    __tablename__ = 'cached_schedules'
    
    # Primary Key
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    
    # Foreign Keys
    tenant_id = db.Column(db.String(36), db.ForeignKey('tenants.tenantID'), nullable=False, index=True)
    schedule_def_id = db.Column(db.String(36), db.ForeignKey('schedule_definitions.scheduleDefID'), nullable=False, index=True)
    user_id = db.Column(db.String(36), db.ForeignKey('users.userID'), nullable=False, index=True)
    
    # Schedule Data
    date = db.Column(db.Date, nullable=False, index=True)  # Date of the schedule entry
    shift_type = db.Column(db.String(10), nullable=True)  # D, E, N, OFF (normalized)
    shift_value = db.Column(db.String(255), nullable=True)  # Raw shift value from sheet (e.g., "C 櫃台人力", "A 藥局人力")
    time_range = db.Column(db.String(50), nullable=True)  # e.g., "08:00 - 16:00"
    
    # Metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Composite unique index for fast lookups (one entry per user/date/schedule)
    __table_args__ = (
        db.UniqueConstraint('schedule_def_id', 'user_id', 'date', name='uq_schedule_user_date'),
        db.Index('idx_schedule_user_month', 'schedule_def_id', 'user_id', 'date'),
    )
    
    # Relationships
    tenant = db.relationship('Tenant', backref='cached_schedules')
    schedule_definition = db.relationship('ScheduleDefinition', backref='cached_schedules')
    user = db.relationship('User', backref='cached_schedules')
    
    @classmethod
    def get_user_schedule(cls, user_id: str, schedule_def_id: str, month: Optional[str] = None, max_age_hours: int = 24):
        """
        Get cached schedule for a user
        
        Args:
            user_id: User ID
            schedule_def_id: Schedule definition ID
            month: Optional month filter (YYYY-MM or YYYY/MM format)
            max_age_hours: Maximum age of cache in hours (default 24)
            
        Returns:
            Query object for filtered schedules
        """
        query = cls.query.filter_by(
            user_id=user_id,
            schedule_def_id=schedule_def_id
        )
        
        # Filter by cache age (24 hours TTL) - but allow max_age_hours=0 to disable
        if max_age_hours and max_age_hours > 0:
            from datetime import timedelta
            min_updated_at = datetime.utcnow() - timedelta(hours=max_age_hours)
            query = query.filter(cls.updated_at >= min_updated_at)
        
        if month:
            # Parse month format (support both YYYY-MM and YYYY/MM)
            try:
                if '-' in month:
                    year, month_num = map(int, month.split('-'))
                elif '/' in month:
                    year, month_num = map(int, month.split('/'))
                else:
                    # Assume YYYYMM format
                    year, month_num = int(month[:4]), int(month[4:6])
                
                from calendar import monthrange
                _, last_day = monthrange(year, month_num)
                
                start_date = datetime(year, month_num, 1).date()
                end_date = datetime(year, month_num, last_day).date()
                
                query = query.filter(
                    cls.date >= start_date,
                    cls.date <= end_date
                )
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"[CACHE] Error parsing month '{month}': {e}")
        
        return query.order_by(cls.date.asc())
    
    @classmethod
    def clear_user_schedule(cls, user_id: str, schedule_def_id: str, month: Optional[str] = None):
        """
        Clear cached schedule for a user (before syncing new data)
        
        Args:
            user_id: User ID
            schedule_def_id: Schedule definition ID
            month: Optional month filter
        """
        query = cls.query.filter_by(
            user_id=user_id,
            schedule_def_id=schedule_def_id
        )
        
        if month:
            year, month_num = map(int, month.split('-'))
            from calendar import monthrange
            _, last_day = monthrange(year, month_num)
            
            start_date = datetime(year, month_num, 1).date()
            end_date = datetime(year, month_num, last_day).date()
            
            query = query.filter(
                cls.date >= start_date,
                cls.date <= end_date
            )
        
        deleted_count = query.delete()
        logger.info(f"[SYNC] Cleared {deleted_count} cached schedule entries for user {user_id}, schedule {schedule_def_id}")
        return deleted_count
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'schedule_def_id': self.schedule_def_id,
            'user_id': self.user_id,
            'date': self.date.isoformat() if self.date is not None and isinstance(self.date, (datetime, date)) else None,
            'shift_type': self.shift_type,
            'shift_value': self.shift_value,  # Raw shift value from sheet
            'time_range': self.time_range,
            'created_at': self.created_at.isoformat() if self.created_at is not None and isinstance(self.created_at, (datetime, date)) else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at is not None and isinstance(self.updated_at, (datetime, date)) else None,
        }

