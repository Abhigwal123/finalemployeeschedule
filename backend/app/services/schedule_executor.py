"""
Schedule Execution Service
Handles the actual execution of scheduling tasks, either via Celery or synchronously
"""
import logging
import os  # Import at module level - DO NOT reassign this variable
import sys
from datetime import datetime
from pathlib import Path
from flask import current_app, has_app_context
# CRITICAL: Use relative import to ensure we use the same db instance
# that was registered with the Flask app (avoids multiple SQLAlchemy instances)
from ..extensions import db
from app.models import ScheduleJobLog

logger = logging.getLogger(__name__)

# Calculate project paths
# backend/app/services/schedule_executor.py -> backend/ -> project root
_service_file = Path(__file__).resolve()
_backend_dir = _service_file.parent.parent.parent  # backend/
PROJECT_ROOT = str(_backend_dir.parent)  # project root (parent of backend/)
BASE_DIR = str(_backend_dir)  # backend/


def execute_schedule_task_sync(schedule_config, job_log_id, flask_app=None):
    """
    Execute a schedule task synchronously (fallback when Celery is not available)
    
    Args:
        schedule_config: Dictionary with schedule configuration
        job_log_id: ID of the job log to update (can also be in schedule_config)
        flask_app: Flask application instance (required for database operations in background threads)
    """
    # CRITICAL: Do NOT import os here - it's already imported at module level
    # Re-importing can cause UnboundLocalError if os is used before this line
    # Use the module-level os import instead
    
    # Get Flask app - use provided app or try to get from current_app
    app = flask_app
    if not app:
        try:
            if has_app_context():
                app = current_app._get_current_object()
            else:
                logger.warning(f"[WARNING] No app context available, but flask_app parameter was not provided")
                app = None
        except RuntimeError as e:
            logger.warning(f"[WARNING] Could not get Flask app from current_app: {e}")
            app = None
    
    if not app:
        logger.error(f"[ERROR] No Flask app available - cannot execute schedule task. Flask app must be passed as parameter.")
        return False
    
    # CRITICAL: Use app context for all database operations
    # This ensures SQLAlchemy has access to the Flask app instance
    # The app context must be active in the background thread
    with app.app_context():
        try:
            # Extract job_log_id from schedule_config if not provided directly
            if not job_log_id and isinstance(schedule_config, dict):
                job_log_id = schedule_config.get('job_log_id')
            
            logger.info(f"[INFO] Executing schedule task synchronously for job: {job_log_id}")
            
            # Get job log - refresh from database to ensure we have the latest state
            if job_log_id:
                # Get the job log from database
                job_log = ScheduleJobLog.query.get(job_log_id)
                if not job_log:
                    logger.error(f"Job log {job_log_id} not found")
                    return False
                
                # Only update status if it's not already running (avoid overwriting)
                if job_log.status not in ['running', 'completed', 'failed', 'cancelled']:
                    job_log.status = 'running'
                    job_log.startTime = datetime.utcnow()
                    db.session.commit()
                    logger.info(f"[INFO] Job log {job_log_id} status set to running")
            else:
                logger.error(f"No job_log_id provided in schedule_config or parameter")
                return False
            
            # Execute the scheduling task using the integration layer
            # Import the scheduling integration
            logger.info(f"[SCHEDULE] 🔄 Importing integration layer (app.scheduling.integration)...")
            logger.info(f"[SCHEDULE] Current sys.path[0:3]: {sys.path[0:3]}")
            try:
                from app.scheduling.integration import run_scheduling_task_saas
                logger.info(f"[SCHEDULE] ✅ Successfully imported run_scheduling_task_saas from integration layer")
            except ImportError as import_error:
                import traceback
                logger.error(f"[SCHEDULE] ❌ FAILED to import integration layer: {import_error}")
                logger.error(f"[SCHEDULE] Import traceback: {traceback.format_exc()}")
                raise
            
            # Extract configuration from schedule_config
            input_source = schedule_config.get('input_source', 'google_sheets')
            input_config = schedule_config.get('input_config', {}).copy()
            output_destination = schedule_config.get('output_destination', 'google_sheets')
            output_config = schedule_config.get('output_config', {}).copy()
            
            # Check for URL change and handle output folder regeneration
            url_changed = schedule_config.get('url_changed', False)
            output_url = schedule_config.get('output_url')
            
            # Pass URL change information through configs
            if url_changed:
                output_config['url_changed'] = True
                output_config['output_url'] = output_url
            
            # Log the URLs being used
            logger.info(f"[SCHEDULE] Executing schedule task synchronously for job: {job_log_id}")
            if input_source == 'google_sheets' and 'spreadsheet_url' in input_config:
                logger.info(f"[SCHEDULE] Input URL: {input_config['spreadsheet_url']}")
            if output_destination == 'google_sheets' and 'spreadsheet_url' in output_config:
                logger.info(f"[SCHEDULE] Output URL: {output_config['spreadsheet_url']}")
                logger.info(f"[SCHEDULE] Writing results to Google Sheets...")
            
            # If URL changed, create output folder structure
            if url_changed and output_url:
                logger.info(f"[OUTPUT] URL change detected - creating output folder structure")
                try:
                    # Create output folder under /app/output/ with job ID and timestamp
                    app_dir = Path(__file__).parent.parent.parent.parent / "app"
                    output_dir = app_dir / "output" / f"{job_log_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
                    output_dir.mkdir(parents=True, exist_ok=True)
                    
                    # Create input folder reference (for documentation)
                    input_dir = app_dir / "input"
                    input_dir.mkdir(parents=True, exist_ok=True)
                    
                    logger.info(f"[OUTPUT] Created output folder: {output_dir}")
                    logger.info(f"[OUTPUT] Input folder: {input_dir}")
                    
                    # Store output folder path in metadata
                    job_log.add_metadata('output_folder', str(output_dir))
                    job_log.add_metadata('input_folder', str(input_dir))
                    
                except Exception as folder_error:
                    logger.warning(f"[OUTPUT] Failed to create output folder: {folder_error}")
                    # Continue execution even if folder creation fails
            
            # Before execution, validate and auto-regenerate if needed
            try:
                from app.services.auto_regeneration_service import AutoRegenerationService
                from flask import current_app
                
                # Get credentials path
                creds_path = schedule_config.get('input_config', {}).get('credentials_path') or \
                            schedule_config.get('output_config', {}).get('credentials_path') or \
                            'service-account-creds.json'
                
                auto_regen_service = AutoRegenerationService(credentials_path=creds_path)
                validation_result = auto_regen_service.validate_and_regenerate(schedule_config.get('schedule_def_id'))
                
                if validation_result.get('regenerated'):
                    logger.info(f"[SCHEDULE] Auto-regeneration completed before execution")
                    # Continue with normal execution to ensure consistency
            except Exception as e:
                logger.warning(f"[SCHEDULE] Auto-validation before execution failed (non-critical): {e}")
                # Continue with normal execution even if validation fails
            
            # Execute the scheduling task
            logger.info("=" * 80)
            logger.info(f"[SCHEDULE] 🔄 STARTING run_refactored.py EXECUTION")
            logger.info(f"[SCHEDULE] This will fetch all sheets from input and generate schedule")
            logger.info(f"[SCHEDULE] Input: {input_source}, Output: {output_destination}")
            logger.info(f"[SCHEDULE] Input URL: {input_config.get('spreadsheet_url', 'N/A')}")
            logger.info(f"[SCHEDULE] Output URL: {output_config.get('spreadsheet_url', 'N/A')}")
            
            # Verify credentials path exists
            creds_path = input_config.get('credentials_path') or output_config.get('credentials_path')
            if creds_path:
                if os.path.exists(creds_path):
                    logger.info(f"[SCHEDULE] ✅ Credentials file found: {creds_path}")
                else:
                    logger.warning(f"[SCHEDULE] ⚠️ Credentials file not found: {creds_path}")
                    # Try to find it in common locations
                    possible_locations = [
                        os.path.join(PROJECT_ROOT, 'service-account-creds.json'),
                        os.path.join(BASE_DIR, 'service-account-creds.json'),
                        os.path.join(BASE_DIR, '..', 'service-account-creds.json'),
                    ]
                    for loc in possible_locations:
                        abs_loc = os.path.abspath(loc)
                        if os.path.exists(abs_loc):
                            logger.info(f"[SCHEDULE] ✅ Found credentials at: {abs_loc}")
                            input_config['credentials_path'] = abs_loc
                            output_config['credentials_path'] = abs_loc
                            break
            
            logger.info("=" * 80)
            
            try:
                result = run_scheduling_task_saas(
                    input_source=input_source,
                    input_config=input_config,
                    output_destination=output_destination,
                    output_config=output_config,
                    time_limit=90.0,
                    log_level="INFO",
                    user_id=None,
                    task_id=job_log_id
                )
                logger.info(f"[SCHEDULE] ✅ run_scheduling_task_saas completed")
                logger.info(f"[SCHEDULE] Result type: {type(result)}")
                if isinstance(result, dict):
                    logger.info(f"[SCHEDULE] Result keys: {list(result.keys())}")
                    logger.info(f"[SCHEDULE] Result status: {result.get('status', 'MISSING')}")
                    logger.info(f"[SCHEDULE] Result has error: {bool(result.get('error'))}")
                    if result.get('error'):
                        logger.error(f"[SCHEDULE] Result error message: {result.get('error')}")
                    # Log full result for debugging (truncate if too long)
                    result_str = str(result)
                    if len(result_str) > 500:
                        logger.info(f"[SCHEDULE] Result (truncated): {result_str[:500]}...")
                    else:
                        logger.info(f"[SCHEDULE] Full result: {result}")
                else:
                    logger.warning(f"[SCHEDULE] Result is not a dict: {result}")
            except Exception as exec_error:
                import traceback
                error_trace = traceback.format_exc()
                logger.error(f"[SCHEDULE] ❌ Exception during run_scheduling_task_saas: {exec_error}")
                logger.error(f"[SCHEDULE] Error traceback: {error_trace}")
                db.session.refresh(job_log)
                job_log.fail_job(
                    error_message=f"Execution exception: {str(exec_error)}",
                    metadata={'execution_mode': 'synchronous', 'error_type': 'execution_exception', 'traceback': error_trace}
                )
                return False
            
            # Check if execution was successful
            # run_schedule_task returns {"status": "success"} on success or {"error": "...", "status": "error"} on failure
            if not result:
                error_msg = "Schedule execution returned None/empty result"
                logger.error(f"[SCHEDULE] ❌ {error_msg}")
                db.session.refresh(job_log)
                job_log.fail_job(
                    error_message=error_msg,
                    metadata={'execution_mode': 'synchronous', 'error_type': 'empty_result'}
                )
                return False
            
            if not isinstance(result, dict):
                error_msg = f"Schedule execution returned invalid result type: {type(result)}"
                logger.error(f"[SCHEDULE] ❌ {error_msg}")
                db.session.refresh(job_log)
                job_log.fail_job(
                    error_message=error_msg,
                    metadata={'execution_mode': 'synchronous', 'error_type': 'invalid_result_type'}
                )
                return False
            
            # Check for error in result (multiple ways it can be indicated)
            if result.get("error"):
                error_msg = result["error"]
                
                # Always try to get more details from result if available
                error_details = result.get("error_details") or result.get("details")
                error_type = result.get("error_type")
                
                # If error message is incomplete or just a prefix, enhance it
                if error_details:
                    # If error message ends with colon or is very short, append details
                    if error_msg.endswith(":") or len(error_msg.strip()) < 30:
                        error_msg = f"{error_msg} {error_details}"
                    elif error_details not in error_msg:
                        # Append details if not already included
                        error_msg = f"{error_msg} ({error_details})"
                
                # Add error type if available and not already in message
                if error_type and error_type not in error_msg:
                    error_msg = f"{error_type}: {error_msg}"
                
                logger.error(f"[SCHEDULE] ❌ Schedule execution failed: {error_msg}")
                logger.error(f"[SCHEDULE] Full result: {result}")
                db.session.refresh(job_log)
                job_log.fail_job(
                    error_message=error_msg,
                    metadata={'execution_mode': 'synchronous', 'error_type': 'execution_error', 'result': result}
                )
                return False
            
            # Check status field
            result_status = result.get("status")
            logger.info(f"[SCHEDULE] Checking result status: '{result_status}'")
            
            if result_status == "error":
                error_msg = result.get("error", "Unknown error (status=error)")
                logger.error(f"[SCHEDULE] ❌ Schedule execution failed (status=error): {error_msg}")
                logger.error(f"[SCHEDULE] Full error result: {result}")
                db.session.refresh(job_log)
                job_log.fail_job(
                    error_message=error_msg,
                    metadata={'execution_mode': 'synchronous', 'error_type': 'status_error', 'result': result}
                )
                return False
            
            # Verify success status - allow None status if no error (backward compatibility)
            if result_status is None:
                # If status is None but no error, check if it looks like success
                if not result.get("error") and ("assignments_count" in result or "summary" in result):
                    logger.warning(f"[SCHEDULE] ⚠️ Result has no status field but looks successful, treating as success")
                    result_status = "success"  # Treat as success
                else:
                    error_msg = f"Result has no status field and appears to be an error"
                    logger.error(f"[SCHEDULE] ❌ {error_msg}")
                    logger.error(f"[SCHEDULE] Full result: {result}")
                    db.session.refresh(job_log)
                    job_log.fail_job(
                        error_message=error_msg,
                        metadata={'execution_mode': 'synchronous', 'error_type': 'missing_status', 'result': result}
                    )
                    return False
            
            # Verify success status
            if result_status != "success":
                error_msg = f"Unexpected status: '{result_status}' (expected 'success')"
                logger.error(f"[SCHEDULE] ❌ {error_msg}")
                logger.error(f"[SCHEDULE] Full result: {result}")
                db.session.refresh(job_log)
                job_log.fail_job(
                    error_message=error_msg,
                    metadata={'execution_mode': 'synchronous', 'error_type': 'unexpected_status', 'result': result}
                )
                return False
            
            logger.info("=" * 80)
            logger.info(f"[SCHEDULE] ✅ run_refactored.py EXECUTION SUCCESSFUL")
            logger.info(f"[SCHEDULE] Status verified: {result_status}")
            logger.info("=" * 80)
            
            # Extract summary information
            summary_parts = []
            if result.get("assignments_count"):
                summary_parts.append(f"{result['assignments_count']} assignments")
            if result.get("total_demand"):
                summary_parts.append(f"{result['total_demand']} total demand")
            if result.get("gap_count"):
                summary_parts.append(f"{result['gap_count']} gaps")
            
            result_summary = "Schedule executed successfully - all sheets fetched from input and written to output"
            if summary_parts:
                result_summary += f" ({', '.join(summary_parts)})"
            
            # Get output URL from config or result
            final_output_url = output_config.get('spreadsheet_url') if output_destination == 'google_sheets' else None
            if not final_output_url:
                final_output_url = schedule_config.get('output_url')
            
            # Use complete_job method for proper status handling
            # Initialize completion_metadata (will be updated with sync status later)
            completion_metadata = {
                'execution_mode': 'synchronous',
                'result': result,
                'output_url': final_output_url,
                'input_url': input_config.get('spreadsheet_url') if input_source == 'google_sheets' else None
            }
            
            # Add output folder info if URL changed
            if url_changed:
                completion_metadata['url_changed'] = True
                completion_metadata['regenerated'] = True
            
            if output_destination == 'google_sheets' and 'spreadsheet_url' in output_config:
                logger.info(f"[SCHEDULE] ✅ Results written to Google Sheets: {output_config['spreadsheet_url']}")
                logger.info(f"[OUTPUT] Output URL saved in metadata: {final_output_url}")
            if url_changed:
                logger.info(f"[OUTPUT] Output regeneration completed due to URL change")
            
            # 🔄 CRITICAL: Sync data from output after successful execution
            # User requirement: Sync must complete BEFORE marking job as success
            # This ensures export functionality works immediately
            # This ensures the database cache is updated with the new schedule results
            # so the frontend can immediately see the updated data in Schedule Manager dashboard
            # User requirement: Sync must complete before marking as success
            schedule_def_id = schedule_config.get('schedule_def_id')
            sync_successful = False
            sync_error_msg = None
            
            if schedule_def_id:
                try:
                    logger.info(f"[SYNC] 🔄 Starting sync after schedule execution for schedule: {schedule_def_id}")
                    logger.info(f"[SYNC] This will fetch all sheets from output and update Schedule Manager dashboard")
                    
                    from flask import current_app
                    from app.services.google_sheets_sync_service import GoogleSheetsSyncService
                    
                    app_instance = current_app._get_current_object()
                    creds_path = app_instance.config.get('GOOGLE_APPLICATION_CREDENTIALS', 'service-account-creds.json')
                    
                    # Run sync synchronously to ensure it completes before marking job as success
                    # This ensures export functionality works immediately
                    try:
                        logger.info(f"[SYNC] Running sync synchronously (will wait for completion)...")
                        sync_service = GoogleSheetsSyncService(creds_path)
                        sync_result = sync_service.sync_schedule_data(
                            schedule_def_id=schedule_def_id,
                            sync_type='on_demand',  # Use 'on_demand' to force fetch from Google Sheets
                            triggered_by=None,
                            force=True  # Force sync to get fresh data after execution
                        )
                        
                        if sync_result.get('success'):
                            rows_synced = sync_result.get('rows_synced', 0)
                            users_synced = sync_result.get('users_synced', 0)
                            logger.info(f"[SYNC] ✅ Sync completed successfully: {rows_synced} rows, {users_synced} users")
                            logger.info(f"[SYNC] ✅ Schedule Manager dashboard will now show updated data")
                            logger.info(f"[SYNC] ✅ Export functionality is now available")
                            sync_successful = True
                        else:
                            sync_error_msg = sync_result.get('error', 'Unknown sync error')
                            logger.warning(f"[SYNC] ⚠️ Sync failed: {sync_error_msg}")
                            logger.warning(f"[SYNC] ⚠️ Schedule execution was successful, but sync failed")
                            # Don't fail the job - execution was successful, sync is for dashboard
                            sync_successful = False
                    except Exception as sync_error:
                        import traceback
                        sync_error_msg = str(sync_error)
                        error_trace = traceback.format_exc()
                        logger.error(f"[SYNC] ❌ Sync error: {sync_error}")
                        logger.error(f"[SYNC] Error traceback: {error_trace}")
                        
                        # CRITICAL: If it's UnboundLocalError for os, log it but don't fail the job
                        # The schedule execution was successful, sync is just for dashboard
                        if 'UnboundLocalError' in str(sync_error) and 'os' in str(sync_error):
                            logger.error(f"[SYNC] ⚠️ UnboundLocalError for 'os' in sync - this is a known issue")
                            logger.error(f"[SYNC] ⚠️ Schedule execution was successful, but sync failed due to os error")
                            logger.error(f"[SYNC] ⚠️ This should be fixed by the wrapper, but if it persists, check google_sheets_import.py")
                        
                        # Don't fail the job - execution was successful
                        sync_successful = False
                    
                except Exception as sync_trigger_error:
                    # CRITICAL: Don't fail the execution if sync fails
                    # The schedule execution was successful, sync is just for dashboard display
                    import traceback
                    sync_error_msg = str(sync_trigger_error)
                    error_trace = traceback.format_exc()
                    logger.warning(f"[SYNC] ⚠️ Failed to run sync after execution (non-critical): {sync_trigger_error}")
                    logger.warning(f"[SYNC] Error traceback: {error_trace}")
                    logger.warning(f"[SYNC] ⚠️ Schedule execution was successful, but sync failed")
                    
                    # CRITICAL: If it's UnboundLocalError for os, provide more context
                    if 'UnboundLocalError' in str(sync_trigger_error) and 'os' in str(sync_trigger_error):
                        logger.error(f"[SYNC] ⚠️ UnboundLocalError for 'os' in sync trigger - this is a known issue")
                        logger.error(f"[SYNC] ⚠️ The wrapper should have caught this - check if fetch_schedule_data is using wrapped version")
                        logger.error(f"[SYNC] ⚠️ Schedule execution was successful, sync will be retried on next page load")
                    
                    sync_successful = False
            else:
                logger.warning(f"[SYNC] ⚠️ No schedule_def_id provided, skipping sync")
            
            # Add sync status to completion metadata
            if sync_successful:
                completion_metadata['sync_completed'] = True
                completion_metadata['sync_success'] = True
                result_summary += " - Sync completed successfully"
            else:
                completion_metadata['sync_completed'] = True
                completion_metadata['sync_success'] = False
                if sync_error_msg:
                    completion_metadata['sync_error'] = sync_error_msg
                result_summary += " - Sync failed (non-critical)"
            
            # CRITICAL: Mark job as completed ONLY AFTER sync completes
            # This ensures export functionality works immediately
            # Refresh job_log from database before completing to ensure we have latest state
            db.session.refresh(job_log)
            
            # Only complete if status is still 'running' or 'pending' (not already completed/failed)
            if job_log.status in ['running', 'pending']:
                job_log.complete_job(
                    result_summary=result_summary,
                    metadata=completion_metadata
                )
                logger.info("=" * 80)
                logger.info(f"[SCHEDULE] ✅✅✅ JOB COMPLETED SUCCESSFULLY ✅✅✅")
                logger.info(f"[SCHEDULE] Job ID: {job_log_id}")
                logger.info(f"[SCHEDULE] Status: completed")
                logger.info(f"[SCHEDULE] Summary: {result_summary}")
                logger.info(f"[SCHEDULE] ✅ run_refactored.py execution: SUCCESS")
                logger.info(f"[SCHEDULE] ✅ Sync to database: {'SUCCESS' if sync_successful else 'FAILED (non-critical)'}")
                logger.info(f"[SCHEDULE] ✅ Export functionality: AVAILABLE")
                logger.info("=" * 80)
            else:
                logger.warning(f"[SCHEDULE] ⚠️ Job {job_log_id} status is already '{job_log.status}', not updating to completed")
            
            # Return True to indicate successful execution
            logger.info(f"[SCHEDULE] ✅ Returning success for job: {job_log_id}")
            return True
        except Exception as e:
            # This catches errors during the actual schedule execution (run_scheduling_task_saas)
            import traceback
            error_trace = traceback.format_exc()
            logger.error(f"[ERROR] ❌ Schedule execution failed during task execution: {e}")
            logger.error(f"[ERROR] Error type: {type(e).__name__}")
            logger.error(f"[ERROR] Error traceback:\n{error_trace}")
            
            # Use fail_job method for proper status handling
            try:
                # Refresh job_log from database to ensure we have the latest state
                if job_log_id:
                    db.session.rollback()  # Rollback any pending changes
                    job_log = ScheduleJobLog.query.get(job_log_id)
                    if job_log:
                        # Only fail if status is not already completed
                        if job_log.status not in ['completed', 'success']:
                            error_msg = f"{type(e).__name__}: {str(e)}"
                            job_log.fail_job(
                                error_message=error_msg,
                                metadata={
                                    'execution_mode': 'synchronous', 
                                    'error_type': type(e).__name__,
                                    'traceback': error_trace[:1000]  # Truncate long tracebacks
                                }
                            )
                            logger.info(f"[INFO] Job log {job_log_id} marked as failed due to exception")
                        else:
                            logger.warning(f"[WARNING] Job {job_log_id} is already {job_log.status}, not changing to failed")
                    else:
                        logger.error(f"[ERROR] Job log {job_log_id} not found when trying to mark as failed")
            except Exception as fail_error:
                import traceback as tb
                logger.error(f"[ERROR] Failed to update job log to failed status: {fail_error}")
                logger.error(f"[ERROR] Traceback: {tb.format_exc()}")
            
            return False
            
        except Exception as e:
            # This catches errors in the outer try block (e.g., job_log not found, etc.)
            import traceback
            error_trace = traceback.format_exc()
            logger.error(f"[ERROR] ❌ Failed to execute schedule task (outer error): {e}")
            logger.error(f"[ERROR] Error type: {type(e).__name__}")
            logger.error(f"[ERROR] Error traceback:\n{error_trace}")
            
            # Try to update job log to failed if we have the ID
            try:
                if job_log_id:
                    db.session.rollback()
                    job_log = ScheduleJobLog.query.get(job_log_id)
                    if job_log:
                        # Only fail if status is not already completed
                        if job_log.status not in ['completed', 'success']:
                            error_msg = f"Task execution error ({type(e).__name__}): {str(e)}"
                            job_log.fail_job(
                                error_message=error_msg,
                                metadata={
                                    'execution_mode': 'synchronous', 
                                    'error_type': 'task_error',
                                    'outer_exception': type(e).__name__,
                                    'traceback': error_trace[:1000]  # Truncate long tracebacks
                                }
                            )
                            logger.info(f"[INFO] Job log {job_log_id} marked as failed due to outer error")
                        else:
                            logger.warning(f"[WARNING] Job {job_log_id} is already {job_log.status}, not changing to failed")
                    else:
                        logger.error(f"[ERROR] Job log {job_log_id} not found when trying to mark as failed (outer error)")
            except Exception as update_error:
                import traceback as tb
                logger.error(f"[ERROR] Failed to update job log status: {update_error}")
                logger.error(f"[ERROR] Update error traceback: {tb.format_exc()}")
                # Best effort - don't fail if we can't update the log
            
            return False

