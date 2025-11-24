# Schedule Job Log Model
from ..extensions import db
from datetime import datetime, date
from typing import List, Optional, Dict, Any
import logging
import json

logger = logging.getLogger(__name__)

class ScheduleJobLog(db.Model):
    """
    Schedule Job Log model representing execution logs for schedule jobs
    
    Job logs track the execution of schedule definitions, including
    start/end times, status, results, and error information.
    """
    
    __tablename__ = 'schedule_job_logs'
    
    # Primary Key
    logID = db.Column(db.String(36), primary_key=True, unique=True, nullable=False)
    
    # Foreign Keys
    tenantID = db.Column(db.String(36), db.ForeignKey('tenants.tenantID'), nullable=False, index=True)
    scheduleDefID = db.Column(db.String(36), db.ForeignKey('schedule_definitions.scheduleDefID'), nullable=False, index=True)
    runByUserID = db.Column(db.String(36), db.ForeignKey('users.userID'), nullable=False, index=True)
    
    # Fields
    startTime = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    endTime = db.Column(db.DateTime, nullable=True, index=True)
    status = db.Column(db.String(20), nullable=False, default='pending', index=True)  # pending, running, success, failed, cancelled
    resultSummary = db.Column(db.Text, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    execution_time_seconds = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Additional metadata as JSON (using job_metadata to avoid SQLAlchemy reserved word conflict)
    job_metadata = db.Column(db.JSON, nullable=True)
    
    # Relationships
    tenant = db.relationship('Tenant', back_populates='schedule_job_logs', foreign_keys=[tenantID])
    schedule_definition = db.relationship('ScheduleDefinition', foreign_keys=[scheduleDefID], viewonly=True)
    run_by_user = db.relationship('User', foreign_keys=[runByUserID], viewonly=True)
    
    def __init__(self, logID: str = None, tenantID: str = None,
                 scheduleDefID: str = None, runByUserID: str = None,
                 startTime: datetime = None, status: str = 'pending',
                 metadata: Dict[str, Any] = None, **kwargs):
        """
        Initialize a new ScheduleJobLog instance
        
        Args:
            logID: Unique log identifier (auto-generated if not provided)
            tenantID: ID of the tenant
            scheduleDefID: ID of the schedule definition
            runByUserID: ID of the user who ran the job
            startTime: When the job started (defaults to now)
            status: Initial status of the job
            metadata: Additional metadata as dictionary
            **kwargs: Additional fields
        """
        if logID:
            self.logID = logID
        else:
            from app.utils.security import generate_job_log_id
            self.logID = generate_job_log_id()
        
        self.tenantID = tenantID
        self.scheduleDefID = scheduleDefID
        self.runByUserID = runByUserID
        self.startTime = startTime or datetime.utcnow()
        self.status = status
        self.job_metadata = metadata or {}
        super().__init__(**kwargs)
    
    def to_dict(self) -> dict:
        """
        Convert schedule job log instance to dictionary
        
        Returns:
            Dictionary representation of the schedule job log
        """
        result = {
            'logID': self.logID,
            'jobLogID': self.logID,  # Frontend compatibility - some code expects jobLogID
            'tenantID': self.tenantID,
            'scheduleDefID': self.scheduleDefID,
            'runByUserID': self.runByUserID,
            'startTime': self.startTime.isoformat() if self.startTime is not None and isinstance(self.startTime, (datetime, date)) else None,
            'endTime': self.endTime.isoformat() if self.endTime is not None and isinstance(self.endTime, (datetime, date)) else None,
            'status': self.status,
            'resultSummary': self.resultSummary,
            'error_message': self.error_message,
            'execution_time_seconds': self.execution_time_seconds,
            'created_at': self.created_at.isoformat() if self.created_at is not None and isinstance(self.created_at, (datetime, date)) else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at is not None and isinstance(self.updated_at, (datetime, date)) else None,
            'metadata': self.job_metadata,
            'user': self.run_by_user.to_dict() if self.run_by_user else None,
            'schedule_definition': self.schedule_definition.to_dict() if self.schedule_definition else None,
        }
        
        # Frontend compatibility fields
        if self.run_by_user:
            result['runByUser'] = self.run_by_user.to_dict()
        if self.schedule_definition:
            result['scheduleName'] = self.schedule_definition.scheduleName
        
        return result
    
    def start_job(self) -> None:
        """Mark the job as started"""
        self.status = 'running'
        self.startTime = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        db.session.commit()
    
    def complete_job(self, result_summary: str = None, metadata: Dict[str, Any] = None) -> None:
        """
        Mark the job as completed successfully
        
        Args:
            result_summary: Summary of the job results
            metadata: Additional metadata about the completion
        """
        try:
            # Support both 'success' and 'completed' status for compatibility
            self.status = 'completed'  # Changed from 'success' to match frontend expectations
            self.endTime = datetime.utcnow()
            self.resultSummary = result_summary
            self.execution_time_seconds = self._calculate_execution_time()
            
            if metadata:
                self.job_metadata = {**(self.job_metadata or {}), **metadata}
            
            self.updated_at = datetime.utcnow()
            
            # Ensure we're in a valid session and commit
            db.session.add(self)  # Ensure object is in session
            db.session.commit()
            
            logger.info(f"Job log {self.logID} marked as completed with endTime: {self.endTime}")
        except Exception as e:
            logger.error(f"Error completing job log {self.logID}: {e}")
            db.session.rollback()
            raise
    
    def fail_job(self, error_message: str = None, metadata: Dict[str, Any] = None) -> None:
        """
        Mark the job as failed
        
        Args:
            error_message: Error message describing the failure
            metadata: Additional metadata about the failure
        """
        self.status = 'failed'
        self.endTime = datetime.utcnow()
        self.error_message = error_message
        self.execution_time_seconds = self._calculate_execution_time()
        
        if metadata:
            self.job_metadata = {**(self.job_metadata or {}), **metadata}
        
        self.updated_at = datetime.utcnow()
        db.session.commit()
    
    def cancel_job(self, reason: str = None) -> None:
        """
        Cancel the job
        
        Args:
            reason: Reason for cancellation
        """
        self.status = 'cancelled'
        self.endTime = datetime.utcnow()
        self.error_message = reason or 'Job cancelled'
        self.execution_time_seconds = self._calculate_execution_time()
        self.updated_at = datetime.utcnow()
        db.session.commit()
    
    def _calculate_execution_time(self) -> Optional[int]:
        """
        Calculate execution time in seconds
        
        Returns:
            Execution time in seconds or None if job hasn't ended
        """
        if not self.endTime or not self.startTime:
            return None
        
        delta = self.endTime - self.startTime
        return int(delta.total_seconds())
    
    def is_running(self) -> bool:
        """
        Check if the job is currently running
        
        Returns:
            True if job status is 'running', False otherwise
        """
        return self.status == 'running'
    
    def is_completed(self) -> bool:
        """
        Check if the job has completed (success or failure)
        
        Returns:
            True if job status is 'success' or 'failed', False otherwise
        """
        return self.status in ['success', 'failed', 'cancelled']
    
    def is_successful(self) -> bool:
        """
        Check if the job completed successfully
        
        Returns:
            True if job status is 'success', False otherwise
        """
        # Support both 'success' and 'completed' status
        return self.status in ['success', 'completed']
    
    def is_failed(self) -> bool:
        """
        Check if the job failed
        
        Returns:
            True if job status is 'failed', False otherwise
        """
        return self.status == 'failed'
    
    def get_duration_string(self) -> str:
        """
        Get human-readable duration string
        
        Returns:
            Formatted duration string
        """
        if not self.execution_time_seconds:
            return "N/A"
        
        seconds = self.execution_time_seconds
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            minutes = seconds // 60
            remaining_seconds = seconds % 60
            return f"{minutes}m {remaining_seconds}s"
        else:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            return f"{hours}h {minutes}m"
    
    def add_metadata(self, key: str, value: Any) -> None:
        """
        Add metadata to the job log
        
        Args:
            key: Metadata key
            value: Metadata value
        """
        if not self.job_metadata:
            self.job_metadata = {}
        
        self.job_metadata[key] = value
        self.updated_at = datetime.utcnow()
        db.session.commit()
    
    def get_metadata(self, key: str, default: Any = None) -> Any:
        """
        Get metadata value by key
        
        Args:
            key: Metadata key
            default: Default value if key not found
            
        Returns:
            Metadata value or default
        """
        if not self.job_metadata:
            return default
        
        return self.job_metadata.get(key, default)
    
    @classmethod
    def get_by_tenant(cls, tenant_id: str, limit: int = 50) -> List['ScheduleJobLog']:
        """
        Get job logs for a specific tenant
        
        Args:
            tenant_id: ID of the tenant
            limit: Maximum number of logs to return
            
        Returns:
            List of ScheduleJobLog instances
        """
        return cls.query.filter_by(tenantID=tenant_id).order_by(cls.startTime.desc()).limit(limit).all()
    
    @classmethod
    def get_by_user(cls, user_id: str, limit: int = 50) -> List['ScheduleJobLog']:
        """
        Get job logs run by a specific user
        
        Args:
            user_id: ID of the user
            limit: Maximum number of logs to return
            
        Returns:
            List of ScheduleJobLog instances
        """
        return cls.query.filter_by(runByUserID=user_id).order_by(cls.startTime.desc()).limit(limit).all()
    
    @classmethod
    def get_by_schedule(cls, schedule_def_id: str, limit: int = 50) -> List['ScheduleJobLog']:
        """
        Get job logs for a specific schedule definition
        
        Args:
            schedule_def_id: ID of the schedule definition
            limit: Maximum number of logs to return
            
        Returns:
            List of ScheduleJobLog instances
        """
        return cls.query.filter_by(scheduleDefID=schedule_def_id).order_by(cls.startTime.desc()).limit(limit).all()
    
    @classmethod
    def get_running_jobs(cls) -> List['ScheduleJobLog']:
        """
        Get all currently running jobs
        
        Returns:
            List of running ScheduleJobLog instances
        """
        return cls.query.filter_by(status='running').all()
    
    @classmethod
    def get_recent_jobs(cls, hours: int = 24, limit: int = 100) -> List['ScheduleJobLog']:
        """
        Get recent job logs within specified hours
        
        Args:
            hours: Number of hours to look back
            limit: Maximum number of logs to return
            
        Returns:
            List of recent ScheduleJobLog instances
        """
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        return cls.query.filter(cls.startTime >= cutoff_time).order_by(cls.startTime.desc()).limit(limit).all()
    
    @classmethod
    def get_failed_jobs(cls, days: int = 7) -> List['ScheduleJobLog']:
        """
        Get failed jobs within specified days
        
        Args:
            days: Number of days to look back
            
        Returns:
            List of failed ScheduleJobLog instances
        """
        cutoff_time = datetime.utcnow() - timedelta(days=days)
        return cls.query.filter(
            cls.status == 'failed',
            cls.startTime >= cutoff_time
        ).order_by(cls.startTime.desc()).all()
    
    @classmethod
    def cleanup_old_logs(cls, days: int = 30) -> int:
        """
        Clean up old job logs
        
        Args:
            days: Number of days to keep logs
            
        Returns:
            Number of logs deleted
        """
        cutoff_time = datetime.utcnow() - timedelta(days=days)
        old_logs = cls.query.filter(cls.startTime < cutoff_time).all()
        
        count = 0
        for log in old_logs:
            db.session.delete(log)
            count += 1
        
        db.session.commit()
        return count
    
    def __repr__(self) -> str:
        """String representation of the schedule job log"""
        return f'<ScheduleJobLog {self.logID}: {self.status}>'
    
    def __str__(self) -> str:
        """Human-readable string representation"""
        return f'Job {self.logID}: {self.status} ({self.get_duration_string()})'







