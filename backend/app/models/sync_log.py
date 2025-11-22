"""
Sync Log Model
Tracks Google Sheets synchronization operations
"""
from app import db
from datetime import datetime
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class SyncLog(db.Model):
    """
    Logs Google Sheets sync operations
    
    Tracks when syncs occur, their status, and any errors
    """
    
    __tablename__ = 'sync_logs'
    
    # Primary Key
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    
    # Sync Metadata
    schedule_def_id = db.Column(db.String(36), db.ForeignKey('schedule_definitions.scheduleDefID'), nullable=True, index=True)
    tenant_id = db.Column(db.String(36), db.ForeignKey('tenants.tenantID'), nullable=True, index=True)
    
    # Sync Status
    status = db.Column(db.String(20), nullable=False, index=True)  # success, failed, in_progress
    sync_type = db.Column(db.String(20), nullable=False, index=True)  # manual, auto, scheduled
    
    # Timing
    started_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    duration_seconds = db.Column(db.Float, nullable=True)
    
    # Results
    rows_synced = db.Column(db.Integer, nullable=True, default=0)
    users_synced = db.Column(db.Integer, nullable=True, default=0)
    error_message = db.Column(db.Text, nullable=True)
    
    # Metadata
    triggered_by = db.Column(db.String(36), nullable=True)  # User ID who triggered manual sync
    retry_count = db.Column(db.Integer, default=0, nullable=False)
    
    # Relationships
    schedule_definition = db.relationship('ScheduleDefinition', backref='sync_logs')
    tenant = db.relationship('Tenant', backref='sync_logs')
    
    @classmethod
    def create_sync_log(cls, schedule_def_id: Optional[str] = None, tenant_id: Optional[str] = None,
                       sync_type: str = 'auto', triggered_by: Optional[str] = None) -> 'SyncLog':
        """Create a new sync log entry"""
        sync_log = cls(
            schedule_def_id=schedule_def_id,
            tenant_id=tenant_id,
            status='in_progress',
            sync_type=sync_type,
            triggered_by=triggered_by
        )
        db.session.add(sync_log)
        db.session.commit()
        return sync_log
    
    def mark_completed(self, rows_synced: int = 0, users_synced: int = 0, 
                      error_message: Optional[str] = None):
        """Mark sync as completed"""
        self.completed_at = datetime.utcnow()
        if self.started_at:
            self.duration_seconds = (self.completed_at - self.started_at).total_seconds()
        
        self.rows_synced = rows_synced
        self.users_synced = users_synced
        
        if error_message:
            self.status = 'failed'
            self.error_message = error_message
        else:
            self.status = 'success'
        
        db.session.commit()
    
    @classmethod
    def get_last_sync(cls, schedule_def_id: Optional[str] = None, tenant_id: Optional[str] = None):
        """Get the last successful sync log"""
        query = cls.query.filter_by(status='success')
        
        if schedule_def_id:
            query = query.filter_by(schedule_def_id=schedule_def_id)
        elif tenant_id:
            query = query.filter_by(tenant_id=tenant_id)
        
        return query.order_by(cls.completed_at.desc()).first()
    
    @classmethod
    def should_sync(cls, schedule_def_id: Optional[str] = None, tenant_id: Optional[str] = None,
                   min_minutes: int = 10):
        """
        Check if a sync is needed (based on last sync time)
        
        Args:
            schedule_def_id: Schedule definition ID
            tenant_id: Tenant ID
            min_minutes: Minimum minutes since last sync
            
        Returns:
            True if sync is needed, False otherwise
        """
        last_sync = cls.get_last_sync(schedule_def_id, tenant_id)
        
        if not last_sync or not last_sync.completed_at:
            logger.info(f"[SYNC] No previous sync found, sync needed")
            return True
        
        time_since_sync = (datetime.utcnow() - last_sync.completed_at).total_seconds() / 60
        
        if time_since_sync >= min_minutes:
            logger.info(f"[SYNC] Last sync was {time_since_sync:.1f} minutes ago (threshold: {min_minutes}), sync needed")
            return True
        else:
            logger.info(f"[SYNC] Last sync was {time_since_sync:.1f} minutes ago (threshold: {min_minutes}), skipping sync")
            return False
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'schedule_def_id': self.schedule_def_id,
            'tenant_id': self.tenant_id,
            'status': self.status,
            'sync_type': self.sync_type,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'duration_seconds': self.duration_seconds,
            'rows_synced': self.rows_synced,
            'users_synced': self.users_synced,
            'error_message': self.error_message,
            'triggered_by': self.triggered_by,
            'retry_count': self.retry_count,
        }


























