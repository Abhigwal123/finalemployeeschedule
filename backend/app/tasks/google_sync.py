"""
Google Sheets Sync Tasks
Celery tasks for periodic synchronization of Google Sheets data to database
"""
import logging
from flask import current_app
# CRITICAL: Use relative import to ensure same db instance
from ..extensions import db
from app.models import ScheduleDefinition, SyncLog
from ..services.google_sheets_sync_service import GoogleSheetsSyncService

logger = logging.getLogger(__name__)

from app.celery_app import celery


@celery.task(name="app.tasks.google_sync.sync_google_sheets_daily", bind=True)
def sync_google_sheets_daily(self):
    """
    Daily sync task - syncs all active schedule definitions
    Runs periodically via Celery Beat
    """
    with current_app.app_context():
        try:
            logger.info("[SYNC] Starting daily Google Sheets sync task")
            
            # Get all active schedule definitions
            schedules = ScheduleDefinition.query.filter_by(is_active=True).all()
            
            if not schedules:
                logger.info("[SYNC] No active schedules found, skipping sync")
                return {"success": True, "message": "No active schedules to sync"}
            
            # Get credentials path
            creds_path = current_app.config.get('GOOGLE_APPLICATION_CREDENTIALS', 'service-account-creds.json')
            sync_service = GoogleSheetsSyncService(creds_path)
            
            results = []
            for schedule_def in schedules:
                # Daily sync: Always sync (force=True) to ensure data is fresh daily
                # The periodic task runs at midnight and every 4 hours, so we ensure sync happens
                logger.info(f"[SYNC] Syncing schedule {schedule_def.scheduleDefID} (daily sync - forced)")
                try:
                    result = sync_service.sync_schedule_data(
                        schedule_def_id=schedule_def.scheduleDefID,
                        sync_type='scheduled',
                        triggered_by=None,
                        force=True  # Force sync for daily sync to ensure it runs
                    )
                    
                    results.append({
                        'schedule_def_id': schedule_def.scheduleDefID,
                        'schedule_name': schedule_def.scheduleName,
                        **result
                    })
                    
                except Exception as e:
                    logger.error(f"[SYNC] Error syncing schedule {schedule_def.scheduleDefID}: {str(e)}")
                    results.append({
                        'schedule_def_id': schedule_def.scheduleDefID,
                        'schedule_name': schedule_def.scheduleName,
                        'success': False,
                        'error': str(e)
                    })
            
            success_count = len([r for r in results if r.get('success', False)])
            logger.info(f"[SYNC] Daily sync completed: {success_count}/{len(results)} schedules synced")
            
            return {
                'success': True,
                'schedules_synced': success_count,
                'total_schedules': len(results),
                'results': results
            }
            
        except Exception as e:
            logger.error(f"[SYNC] Daily sync task failed: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            raise


@celery.task(name="app.tasks.google_sync.sync_schedule_definition", bind=True)
def sync_schedule_definition(self, schedule_def_id: str, force: bool = False):
    """
    Sync a specific schedule definition
    
    Args:
        schedule_def_id: Schedule definition ID to sync
        force: Force sync even if recent sync exists
    """
    with current_app.app_context():
        try:
            logger.info(f"[SYNC] Syncing schedule definition {schedule_def_id} (force={force})")
            
            creds_path = current_app.config.get('GOOGLE_APPLICATION_CREDENTIALS', 'service-account-creds.json')
            sync_service = GoogleSheetsSyncService(creds_path)
            
            result = sync_service.sync_schedule_data(
                schedule_def_id=schedule_def_id,
                sync_type='scheduled',
                triggered_by=None,
                force=force
            )
            
            return result
            
        except Exception as e:
            logger.error(f"[SYNC] Error syncing schedule definition {schedule_def_id}: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            raise


@celery.task(name="app.tasks.google_sync.ensure_schedule_auto_sync", bind=True)
def ensure_schedule_auto_sync(self):
    """
    Periodic task that checks all EmployeeMappings every 10 minutes.
    If any user lacks CachedSchedule data or their schedule is older than 6 hours,
    trigger an automatic sync.
    """
    with current_app.app_context():
        try:
            from datetime import datetime, timedelta
            from app.models import CachedSchedule, EmployeeMapping, ScheduleDefinition
            
            logger.info("[AUTO-SYNC] Starting periodic schedule auto-sync check")
            
            # Get all active employee mappings
            mappings = EmployeeMapping.query.filter_by(is_active=True).all()
            
            if not mappings:
                logger.info("[AUTO-SYNC] No active employee mappings found")
                return {"success": True, "message": "No active employee mappings to check"}
            
            sync_threshold_hours = 6  # 6 hours threshold
            sync_threshold_seconds = sync_threshold_hours * 3600
            now = datetime.utcnow()
            
            synced_count = 0
            skipped_count = 0
            
            for emp in mappings:
                try:
                    # Get user's schedule definition
                    if not emp.schedule_def_id:
                        # Try to find active schedule for tenant
                        schedule_def = ScheduleDefinition.query.filter_by(
                            tenantID=emp.tenantID,
                            is_active=True
                        ).first()
                        if not schedule_def:
                            skipped_count += 1
                            continue
                        schedule_def_id = schedule_def.scheduleDefID
                    else:
                        schedule_def_id = emp.schedule_def_id
                    
                    # Check if user has recent cached schedule
                    recent = CachedSchedule.query.filter_by(
                        user_id=emp.userID,
                        schedule_def_id=schedule_def_id
                    ).order_by(CachedSchedule.updated_at.desc()).first()
                    
                    # Determine if sync is needed
                    needs_sync = False
                    if not recent:
                        needs_sync = True
                        logger.info(f"[AUTO-SYNC] User {emp.userID} has no cached schedule, triggering sync")
                    elif recent.updated_at:
                        age_seconds = (now - recent.updated_at).total_seconds()
                        if age_seconds > sync_threshold_seconds:
                            needs_sync = True
                            logger.info(f"[AUTO-SYNC] User {emp.userID} schedule is {age_seconds/3600:.1f} hours old, triggering sync")
                    
                    if needs_sync:
                        # Trigger sync via Celery task
                        try:
                            # Use celery app to send task
                            celery.send_task(
                                "app.tasks.google_sync.sync_schedule_definition",
                                args=[schedule_def_id],
                                kwargs={'force': True}
                            )
                            synced_count += 1
                            logger.info(f"[AUTO-SYNC] ✅ Triggered sync for user {emp.userID}, schedule {schedule_def_id}")
                        except Exception as e:
                            logger.error(f"[AUTO-SYNC] Failed to trigger sync for user {emp.userID}: {e}")
                    else:
                        skipped_count += 1
                        
                except Exception as e:
                    logger.error(f"[AUTO-SYNC] Error processing employee mapping {emp.mappingID}: {e}")
                    continue
            
            logger.info(f"[AUTO-SYNC] Periodic check completed: {synced_count} syncs triggered, {skipped_count} skipped")
            
            return {
                'success': True,
                'synced_count': synced_count,
                'skipped_count': skipped_count,
                'total_checked': len(mappings)
            }
            
        except Exception as e:
            logger.error(f"[AUTO-SYNC] Periodic auto-sync task failed: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                'success': False,
                'error': str(e)
            }


@celery.task(name="app.tasks.google_sync.sync_all_sheets_metadata", bind=True)
def sync_all_sheets_metadata(self):
    """
    Periodic task to sync Google Sheets metadata for all active schedule definitions
    Runs every 5 minutes to ensure data freshness
    
    This task syncs metadata (row count, preview data) from Google Sheets
    and updates the database without affecting the frontend API response structure.
    """
    with current_app.app_context():
        try:
            logger.info("[SYNC] Starting periodic Google Sheets metadata sync task")
            
            # Get all active schedule definitions
            schedules = ScheduleDefinition.query.filter_by(is_active=True).all()
            
            if not schedules:
                logger.info("[SYNC] No active schedules found, skipping metadata sync")
                return {"success": True, "message": "No active schedules to sync"}
            
            # Get credentials path
            creds_path = current_app.config.get('GOOGLE_APPLICATION_CREDENTIALS', 'service-account-creds.json')
            sync_service = GoogleSheetsSyncService(creds_path)
            
            results = []
            for schedule_def in schedules:
                try:
                    logger.info(f"[SYNC] Syncing metadata for schedule {schedule_def.scheduleDefID} ({schedule_def.scheduleName})")
                    
                    # Sync metadata (row count, preview data, etc.)
                    result = sync_service.sync_schedule_definition_metadata(schedule_def, creds_path)
                    
                    results.append({
                        'schedule_def_id': schedule_def.scheduleDefID,
                        'schedule_name': schedule_def.scheduleName,
                        **result
                    })
                    
                    if result.get('success'):
                        logger.info(f"[SYNC] Metadata synced for {schedule_def.scheduleName}: {result.get('row_count', 0)} rows")
                    elif result.get('skipped'):
                        logger.debug(f"[SYNC] Metadata sync skipped for {schedule_def.scheduleName}")
                    
                except Exception as e:
                    logger.error(f"[Google Sheets Sync Error] Error syncing metadata for {schedule_def.scheduleDefID}: {str(e)}")
                    results.append({
                        'schedule_def_id': schedule_def.scheduleDefID,
                        'schedule_name': schedule_def.scheduleName,
                        'success': False,
                        'error': str(e)
                    })
            
            success_count = len([r for r in results if r.get('success', False)])
            logger.info(f"[SYNC] Metadata sync completed: {success_count}/{len(results)} schedules synced")
            
            return {
                'success': True,
                'schedules_synced': success_count,
                'total_schedules': len(results),
                'results': results
            }
            
        except Exception as e:
            logger.error(f"[Google Sheets Sync Error] Metadata sync task failed: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                'success': False,
                'error': str(e)
            }



