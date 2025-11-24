"""
Sheet Cache Model
Caches Google Sheets data in database to reduce API quota usage
Uses tenant_id + month + sheet_name as cache key
"""
from ..extensions import db
from datetime import datetime, timedelta, date
from typing import Optional, Dict, Any
import json
import logging
import hashlib

logger = logging.getLogger(__name__)

class CachedSheetData(db.Model):
    """
    Caches Google Sheets data in database
    
    Stores fetched sheet data with expiration times to avoid repeated API calls
    Cache key: tenant_id + month + sheet_name
    """
    
    __tablename__ = 'cached_sheet_data'
    
    # Primary Key
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    
    # Cache Keys - tenant_id + month + sheet_name
    tenant_id = db.Column(db.String(36), db.ForeignKey('tenants.tenantID'), nullable=False, index=True)
    month = db.Column(db.String(7), nullable=False, index=True)  # Format: YYYY-MM (e.g., "2025-11")
    sheet_name = db.Column(db.String(100), nullable=False, index=True)  # parameters, employee, preferences, etc.
    
    # Composite unique index for fast lookups
    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'month', 'sheet_name', name='uq_tenant_month_sheet'),
    )
    
    # Cached Data
    data = db.Column(db.JSON, nullable=False)  # JSON field for cached data
    
    # Metadata
    spreadsheet_url = db.Column(db.String(500), nullable=True)
    row_count = db.Column(db.Integer, nullable=True, default=0)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, onupdate=datetime.utcnow, index=True)
    
    # Relationships
    tenant = db.relationship('Tenant', backref='cached_sheets')
    
    @staticmethod
    def generate_cache_key(tenant_id: str, month: str, sheet_name: str) -> str:
        """
        Generate cache key from tenant_id, month, and sheet_name
        
        Args:
            tenant_id: Tenant ID
            month: Month in YYYY-MM format
            sheet_name: Sheet name (parameters, employee, etc.)
            
        Returns:
            Cache key string (hash)
        """
        key_string = f"{tenant_id}:{month}:{sheet_name}"
        return hashlib.md5(key_string.encode()).hexdigest()
    
    def is_expired(self, expiry_hours: int = 1) -> bool:
        """
        Check if cache is expired
        
        Args:
            expiry_hours: Cache expiration in hours (default: 1 hour)
            
        Returns:
            True if expired, False otherwise
        """
        expiry_time = self.last_updated + timedelta(hours=expiry_hours)
        return datetime.utcnow() > expiry_time
    
    @classmethod
    def get_cached(cls, tenant_id: str, month: str, sheet_name: str, expiry_hours: int = 1) -> Optional['CachedSheetData']:
        """
        Get cached data if available and not expired
        
        Args:
            tenant_id: Tenant ID
            month: Month in YYYY-MM format
            sheet_name: Sheet name
            expiry_hours: Cache expiration in hours
            
        Returns:
            CachedSheetData instance or None if not found/expired
        """
        cache = cls.query.filter_by(
            tenant_id=tenant_id,
            month=month,
            sheet_name=sheet_name
        ).first()
        
        if cache:
            if not cache.is_expired(expiry_hours):
                logger.info(f"[CACHE] Loaded {sheet_name} data for tenant-{tenant_id} (month={month}) from DB")
                return cache
            else:
                logger.info(f"[CACHE] Cache expired for {sheet_name} (tenant-{tenant_id}, month={month})")
                # Delete expired cache
                db.session.delete(cache)
                db.session.commit()
        
        logger.info(f"[CACHE] Cache MISS for {sheet_name} (tenant-{tenant_id}, month={month})")
        return None
    
    @classmethod
    def set_cached(cls, tenant_id: str, month: str, sheet_name: str, data: Dict[str, Any],
                   spreadsheet_url: Optional[str] = None) -> 'CachedSheetData':
        """
        Store data in cache
        
        Args:
            tenant_id: Tenant ID
            month: Month in YYYY-MM format
            sheet_name: Sheet name
            data: Data to cache (dict)
            spreadsheet_url: Optional spreadsheet URL
            
        Returns:
            CachedSheetData instance
        """
        # Check if cache exists
        existing = cls.query.filter_by(
            tenant_id=tenant_id,
            month=month,
            sheet_name=sheet_name
        ).first()
        
        # Calculate row count
        row_count = 0
        if isinstance(data, dict):
            data_list = data.get('data', [])
            if isinstance(data_list, list):
                row_count = len(data_list)
        
        if existing:
            # Update existing cache
            existing.data = data
            existing.row_count = row_count
            existing.last_updated = datetime.utcnow()
            if spreadsheet_url:
                existing.spreadsheet_url = spreadsheet_url
            logger.info(f"[CACHE] Updated cache for {sheet_name} (tenant-{tenant_id}, month={month}, rows={row_count})")
            return existing
        else:
            # Create new cache
            cache = cls(
                tenant_id=tenant_id,
                month=month,
                sheet_name=sheet_name,
                data=data,
                row_count=row_count,
                spreadsheet_url=spreadsheet_url
            )
            db.session.add(cache)
            logger.info(f"[CACHE] Created cache for {sheet_name} (tenant-{tenant_id}, month={month}, rows={row_count})")
            return cache
    
    @classmethod
    def get_stale_cache(cls, tenant_id: str, month: str, sheet_name: str) -> Optional['CachedSheetData']:
        """
        Get cache even if expired (for graceful API failure handling)
        
        Args:
            tenant_id: Tenant ID
            month: Month in YYYY-MM format
            sheet_name: Sheet name
            
        Returns:
            CachedSheetData instance or None if not found
        """
        cache = cls.query.filter_by(
            tenant_id=tenant_id,
            month=month,
            sheet_name=sheet_name
        ).first()
        
        if cache:
            logger.warning(f"[CACHE] Using STALE cache for {sheet_name} (tenant-{tenant_id}, month={month}) - API may have failed")
            return cache
        
        return None
    
    def to_dict(self) -> dict:
        """
        Convert cache to dictionary
        
        Returns:
            Dictionary representation
        """
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'month': self.month,
            'sheet_name': self.sheet_name,
            'row_count': self.row_count,
            'last_updated': self.last_updated.isoformat() if self.last_updated is not None and isinstance(self.last_updated, (datetime, date)) else None,
            'is_expired': self.is_expired(),
            'spreadsheet_url': self.spreadsheet_url
        }
