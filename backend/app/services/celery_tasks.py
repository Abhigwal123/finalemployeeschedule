import importlib.util
import importlib.machinery
import sys
from pathlib import Path
from app.extensions import init_celery
from flask import current_app
from app.services.google_io import get_default_input_url, get_default_output_url


def _load_phase1_run_schedule():
    # Import run_refactored.run_schedule_task from project root
    repo_root = Path(__file__).resolve().parents[2].parent
    repo_root_str = str(repo_root)
    # Ensure repo root takes precedence over current backend dir
    if sys.path and sys.path[0] == "":
        sys.path[0] = repo_root_str
    elif repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)
    module = importlib.import_module("run_refactored")
    return getattr(module, "run_schedule_task")


# Celery task bound at runtime via app factory; import task for registration
celery = None


def bind_celery(celery_app):
    global celery
    celery = celery_app
    
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"[CELERY] Binding Celery app and registering tasks...")
    
    # Register the schedule execution task
    register_schedule_execution_task(celery_app)
    
    # Log all registered tasks after registration
    registered_tasks = list(celery_app.tasks.keys())
    schedule_tasks = [t for t in registered_tasks if 'schedule' in t.lower() or 'execute' in t.lower()]
    logger.info(f"[CELERY] Registered {len(registered_tasks)} total tasks")
    logger.info(f"[CELERY] Schedule-related tasks: {schedule_tasks}")
    
    # Register test task for verification
    try:
        from app.tasks.test_task import register_test_task
        register_test_task(celery_app)
    except ImportError:
        pass  # Test task is optional

    @celery.task(bind=True, name="async_run_schedule")
    def async_run_schedule(self, input_url: str | None = None, output_url: str | None = None):
        self.update_state(state="STARTED")
        # Lazy import to avoid package name collisions at app startup
        original_app_module = sys.modules.get("app")
        try:
            # Prepare path
            repo_root = Path(__file__).resolve().parents[2].parent
            repo_root_str = str(repo_root)
            if sys.path and sys.path[0] == "":
                sys.path[0] = repo_root_str
            elif repo_root_str not in sys.path:
                sys.path.insert(0, repo_root_str)

            # Temporarily alias root app package
            from types import ModuleType
            phase1_pkg_name = "phase1"
            if phase1_pkg_name not in sys.modules:
                pkg_spec = importlib.machinery.ModuleSpec(phase1_pkg_name, loader=None, is_package=True)
                phase1_pkg = importlib.util.module_from_spec(pkg_spec)
                phase1_pkg.__path__ = [str(repo_root / "app")]  # type: ignore[attr-defined]
                sys.modules[phase1_pkg_name] = phase1_pkg
            # Point 'app' to phase1 during import
            sys.modules['app'] = sys.modules[phase1_pkg_name]

            # Add backend to sys.path to import run_refactored (now in backend/)
            backend_dir = repo_root / "backend"
            backend_dir_str = str(backend_dir)
            if backend_dir_str not in sys.path:
                sys.path.insert(0, backend_dir_str)

            mod = importlib.import_module("run_refactored")
            run_schedule_task = getattr(mod, "run_schedule_task")

            # Derive defaults from config when not provided
            cfg_in = current_app.config.get("GOOGLE_INPUT_URL")
            cfg_out = current_app.config.get("GOOGLE_OUTPUT_URL")
            sheet_id = current_app.config.get("GOOGLE_SHEET_ID")
            in_url = input_url or cfg_in or get_default_input_url(sheet_id)
            out_url = output_url or cfg_out or get_default_output_url(sheet_id)

            # Execute Phase 1 with Google Sheets mapping
            creds_path = current_app.config.get("GOOGLE_APPLICATION_CREDENTIALS", "service-account-creds.json")
            input_config = {"spreadsheet_url": in_url, "credentials_path": creds_path}
            output_config = {"spreadsheet_url": out_url, "credentials_path": creds_path}
            result = run_schedule_task(
                input_source="google_sheets",
                input_config=input_config,
                output_destination="google_sheets",
                output_config=output_config,
            )
        finally:
            # Restore original mapping if any
            if original_app_module is not None:
                sys.modules['app'] = original_app_module
            else:
                sys.modules.pop('app', None)

        self.update_state(state="SUCCESS", meta=result)
        return result

    return async_run_schedule


def register_schedule_execution_task(celery_app):
    """
    Register the execute_scheduling_task for manual schedule runs
    """
    from app import db
    from app.models import ScheduleJobLog
    from datetime import datetime
    import logging
    from app.services.schedule_executor import execute_schedule_task_sync
    
    logger = logging.getLogger(__name__)
    logger.info(f"[CELERY] Registering execute_scheduling_task...")
    
    @celery_app.task(name="celery_tasks.execute_scheduling_task", bind=True)
    def execute_scheduling_task(self, schedule_config, job_log_id=None):
        """
        Execute a scheduling task via Celery
        
        Args:
            schedule_config: Dictionary with schedule configuration
            job_log_id: ID of the job log to update
        """
        try:
            logger.info("=" * 80)
            logger.info(f"[CELERY_TASK] 🔄 Celery task received - will execute run_refactored.py")
            logger.info(f"[CELERY_TASK] Schedule def ID: {schedule_config.get('schedule_def_id')}")
            logger.info(f"[CELERY_TASK] Job log ID: {job_log_id}")
            logger.info("=" * 80)
            
            # Extract job_log_id from schedule_config if not provided in kwargs
            if not job_log_id and isinstance(schedule_config, dict):
                job_log_id = schedule_config.get('job_log_id')
            
            # Update job log status to running
            if job_log_id:
                try:
                    job_log = ScheduleJobLog.query.get(job_log_id)
                    if job_log:
                        job_log.status = 'running'
                        job_log.startTime = datetime.utcnow()
                        db.session.commit()
                        logger.info(f"[INFO] Job log {job_log_id} marked as running")
                    else:
                        logger.warning(f"[WARNING] Job log {job_log_id} not found when trying to mark as running")
                except Exception as update_error:
                    logger.error(f"[ERROR] Failed to update job log status to running: {update_error}")
                    # Continue execution even if status update fails
            
            # Execute the schedule task (sync function handles the actual work and completion)
            # The sync function will update the job log status to 'completed' or 'failed'
            import sys
            logger.info(f"[CELERY_TASK] 🔄 About to call execute_schedule_task_sync")
            logger.info(f"[CELERY_TASK] Effective sys.path[0:5]: {sys.path[0:5]}")
            logger.info(f"[CELERY_TASK] schedule_config keys: {list(schedule_config.keys()) if isinstance(schedule_config, dict) else 'N/A'}")
            logger.info(f"[CELERY_TASK] job_log_id: {job_log_id}")
            
            success = execute_schedule_task_sync(schedule_config, job_log_id)
            
            logger.info(f"[CELERY_TASK] execute_schedule_task_sync returned: success={success}")
            
            # Verify final status after execution
            if job_log_id:
                try:
                    # Get fresh job log from database to check final status
                    job_log = ScheduleJobLog.query.get(job_log_id)
                    if job_log:
                        final_status = job_log.status
                        logger.info(f"[INFO] Job {job_log_id} final status: {final_status}")
                        
                        if success and final_status == 'completed':
                            logger.info(f"[INFO] ✅ Schedule job completed successfully - status verified as 'completed'")
                        elif not success or final_status == 'failed':
                            logger.error(f"[ERROR] ❌ Schedule job failed - status: {final_status}")
                        else:
                            logger.warning(f"[WARNING] ⚠️ Job status mismatch: success={success}, status={final_status}")
                except Exception as status_check_error:
                    logger.warning(f"[WARNING] Could not verify final job status: {status_check_error}")
            
            if success:
                logger.info(f"[INFO] ✅ Schedule job execution completed successfully")
            else:
                logger.error(f"[ERROR] ❌ Schedule job execution failed for job_log_id={job_log_id}")
            
            return {"success": success, "job_log_id": job_log_id}
            
        except Exception as e:
            logger.error(f"[ERROR] Schedule execution task failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
            # Update job log to failed
            if job_log_id:
                try:
                    job_log = ScheduleJobLog.query.get(job_log_id)
                    if job_log:
                        job_log.status = 'failed'
                        job_log.endTime = datetime.utcnow()
                        job_log.error_message = str(e)
                        db.session.commit()
                except:
                    pass
            
            raise
    
    # Verify task was registered
    registered_tasks = list(celery_app.tasks.keys())
    task_registered = 'celery_tasks.execute_scheduling_task' in registered_tasks
    logger.info(f"[CELERY] Task registration {'✅ SUCCESS' if task_registered else '❌ FAILED'}")
    if task_registered:
        logger.info(f"[CELERY] ✅ execute_scheduling_task is now available in Celery")
    else:
        logger.error(f"[CELERY] ❌ execute_scheduling_task NOT found in registered tasks: {registered_tasks}")
    
    return execute_scheduling_task


def register_periodic_tasks(celery_app):
    """Register periodic tasks (including daily midnight auto-run)."""
    try:
        from celery.schedules import crontab
    except Exception:
        return

    enable_test_tasks = bool(celery_app.conf.get("enable_test_tasks", False))

    beat_schedule_definition = {
        'auto-run-schedule-5m': {
            'task': 'trigger_sheet_run',
            'schedule': 300.0,
        },
        'daily-run-all-schedules-midnight': {
            'task': 'daily_run_all_schedules',
            'schedule': crontab(minute=0, hour=0),
        },
        'daily-refresh-google-sheets': {
            'task': 'refresh_google_sheets_data',
            'schedule': crontab(minute=0, hour=1),
        },
        'auto-sync-employee-ids-every-5-mins': {
            'task': 'auto_sync_employee_data',
            'schedule': crontab(minute="*/5"),
        },
        'daily-sync-all-schedules-2am': {
            'task': 'daily_sync_all_schedules',
            'schedule': crontab(minute=0, hour=2),
        },
    }

    if enable_test_tasks:
        beat_schedule_definition['test-2min-auto-schedule'] = {
            'task': 'test_2min_auto_schedule',
            'schedule': 120.0,
        }

    # Store schedule definition for inspection (used by diagnostics/test script)
    celery_app.conf.beat_schedule = beat_schedule_definition

    @celery_app.on_after_finalize.connect
    def setup_periodic_tasks(sender, **kwargs):
        if enable_test_tasks:
            # TEST: 2-minute auto-run for testing Celery Beat and worker execution
            sender.add_periodic_task(
                beat_schedule_definition['test-2min-auto-schedule']['schedule'],
                test_2min_auto_schedule.s(),
                name="test-2min-auto-schedule",
            )
        # Lightweight liveness run every 5 minutes (noop default runner)
        sender.add_periodic_task(
            beat_schedule_definition['auto-run-schedule-5m']['schedule'],
            trigger_sheet_run.s(),
            name="auto-run-schedule-5m",
        )
        # Daily auto-run at midnight (server local time)
        sender.add_periodic_task(
            beat_schedule_definition['daily-run-all-schedules-midnight']['schedule'],
            daily_run_all_schedules.s(),
            name="daily-run-all-schedules-midnight",
        )
        # Daily Google Sheets refresh at 1 AM (validate all sheets are accessible)
        sender.add_periodic_task(
            beat_schedule_definition['daily-refresh-google-sheets']['schedule'],
            refresh_google_sheets_data.s(),
            name="daily-refresh-google-sheets",
        )
        # Auto-sync Employee IDs every 5 minutes from Google Sheets
        sender.add_periodic_task(
            beat_schedule_definition['auto-sync-employee-ids-every-5-mins']['schedule'],
            auto_sync_employee_data.s(),
            name="auto-sync-employee-ids-every-5-mins",
        )
        # Daily sync of schedule data at 2 AM (after schedules run at midnight)
        # This ensures data is synced to DB even if sync after execution fails
        sender.add_periodic_task(
            beat_schedule_definition['daily-sync-all-schedules-2am']['schedule'],
            daily_sync_all_schedules.s(),
            name="daily-sync-all-schedules-2am",
        )

    @celery_app.task(name="trigger_sheet_run")
    def trigger_sheet_run():
        # Fire and forget a new run using defaults
        celery_app.send_task("async_run_schedule", args=[None, None])

    @celery_app.task(name="daily_run_all_schedules")
    def daily_run_all_schedules():
        """
        Daily automatic schedule execution - runs run_refactored.py for all active schedules.
        This task runs at midnight daily via Celery Beat to automatically generate schedules.
        After execution, sync happens automatically to save data to DB.
        """
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            from flask import current_app as flask_app
            from app import db
            from app.models import Tenant, ScheduleDefinition, ScheduleJobLog, SchedulePermission, User
            from datetime import datetime

            logger.info("[DAILY_AUTO_RUN] 🔄 Starting daily automatic schedule execution...")
            logger.info("[DAILY_AUTO_RUN] This will run run_refactored.py for all active schedules")

            # Iterate tenants
            tenants = db.session.query(Tenant).all()
            logger.info(f"[DAILY_AUTO_RUN] Found {len(tenants)} tenants")
            
            total_schedules = 0
            for tenant in tenants:
                # Fetch schedule definitions for tenant
                defs = db.session.query(ScheduleDefinition).filter_by(tenantID=tenant.tenantID, is_active=True).all()
                logger.info(f"[DAILY_AUTO_RUN] Tenant {tenant.tenantID}: {len(defs)} active schedules")
                
                for sd in defs:
                    total_schedules += 1
                    try:
                        # Pick any user with permission to run (prefer ScheduleManager)
                        perm = db.session.query(SchedulePermission).filter_by(
                            tenantID=tenant.tenantID, scheduleDefID=sd.scheduleDefID, canRunJob=True, is_active=True
                        ).first()
                        run_by_user_id = perm.userID if perm else None
                        # Fallback to any active user in tenant
                        if not run_by_user_id:
                            u = db.session.query(User).filter_by(tenantID=tenant.tenantID, status='active').first()
                            run_by_user_id = u.userID if u else None

                        # Create job log for daily auto-run
                        job_log = ScheduleJobLog(
                            tenantID=tenant.tenantID,
                            scheduleDefID=sd.scheduleDefID,
                            runByUserID=run_by_user_id or "system",
                            status='pending',
                            metadata={
                                'parameters': {},
                                'priority': 'normal',
                                'requested_at': datetime.utcnow().isoformat(),
                                'trigger': 'daily-auto-run',
                                'schedule_name': sd.scheduleName
                            }
                        )
                        db.session.add(job_log)
                        db.session.commit()

                        logger.info(f"[DAILY_AUTO_RUN] Created job log {job_log.logID} for schedule {sd.scheduleName}")

                        # Prepare schedule config for run_refactored.py execution
                        schedule_config = {
                            'input_source': 'google_sheets',
                            'input_config': {
                                'spreadsheet_url': sd.paramsSheetURL,
                                'credentials_path': flask_app.config.get('GOOGLE_APPLICATION_CREDENTIALS', 'service-account-creds.json')
                            },
                            'output_destination': 'google_sheets',
                            'output_config': {
                                'spreadsheet_url': sd.resultsSheetURL,
                                'credentials_path': flask_app.config.get('GOOGLE_APPLICATION_CREDENTIALS', 'service-account-creds.json')
                            },
                            'schedule_def_id': sd.scheduleDefID,
                            'job_log_id': job_log.logID
                        }

                        # Enqueue Celery task to execute run_refactored.py
                        # This uses execute_scheduling_task which calls run_refactored.py
                        logger.info(f"[DAILY_AUTO_RUN] Enqueuing execution task for schedule {sd.scheduleName} (job_log: {job_log.logID})")
                        celery_app.send_task(
                            'celery_tasks.execute_scheduling_task',
                            args=[schedule_config],
                            kwargs={'job_log_id': job_log.logID}
                        )
                        logger.info(f"[DAILY_AUTO_RUN] ✅ Execution task enqueued for schedule {sd.scheduleName}")
                        
                    except Exception as schedule_error:
                        import traceback
                        logger.error(f"[DAILY_AUTO_RUN] ❌ Error processing schedule {sd.scheduleDefID}: {schedule_error}")
                        logger.error(f"[DAILY_AUTO_RUN] Traceback: {traceback.format_exc()}")
                        # Continue with next schedule even if one fails
                        continue
            
            logger.info(f"[DAILY_AUTO_RUN] ✅ Daily auto-run initiated for {total_schedules} schedules")
            logger.info(f"[DAILY_AUTO_RUN] Each schedule will run run_refactored.py and then sync to DB automatically")
            return {"success": True, "schedules_queued": total_schedules}
            
        except Exception as e:  # best-effort; log and continue
            import traceback
            logger.error(f"[DAILY_AUTO_RUN] ❌ Daily auto-run failed: {e}")
            logger.error(f"[DAILY_AUTO_RUN] Traceback: {traceback.format_exc()}")
            return {"success": False, "error": str(e)}

    @celery_app.task(name="test_2min_auto_schedule")
    def test_2min_auto_schedule():
        """
        TEST TASK: Runs "Daily Auto Schedule" every 2 minutes for testing Celery Beat and worker execution.
        This is a test task to verify that Celery periodic tasks are working correctly.
        """
        if not celery_app.conf.get("enable_test_tasks", False):
            return {"success": False, "skipped": True, "reason": "Test tasks disabled"}
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            from flask import current_app as flask_app
            from app import db
            from app.models import ScheduleDefinition, ScheduleJobLog, SchedulePermission, User, Tenant
            from datetime import datetime
            
            logger.info("=" * 80)
            logger.info("[TEST_2MIN] 🔄 TEST: 2-minute auto-schedule task triggered")
            logger.info("[TEST_2MIN] This task runs every 2 minutes to test Celery Beat")
            logger.info("=" * 80)
            
            # Find "Daily Auto Schedule" by name
            schedule_def = db.session.query(ScheduleDefinition).filter_by(
                scheduleName="Daily Auto Schedule",
                is_active=True
            ).first()
            
            if not schedule_def:
                logger.warning("[TEST_2MIN] ⚠️ 'Daily Auto Schedule' not found or not active")
                return {"success": False, "error": "Daily Auto Schedule not found"}
            
            logger.info(f"[TEST_2MIN] Found schedule: {schedule_def.scheduleName} (ID: {schedule_def.scheduleDefID})")
            
            # Get tenant
            tenant = db.session.query(Tenant).filter_by(tenantID=schedule_def.tenantID).first()
            if not tenant:
                logger.warning(f"[TEST_2MIN] ⚠️ Tenant {schedule_def.tenantID} not found")
                return {"success": False, "error": "Tenant not found"}
            
            # Pick a user with permission to run
            perm = db.session.query(SchedulePermission).filter_by(
                tenantID=tenant.tenantID,
                scheduleDefID=schedule_def.scheduleDefID,
                canRunJob=True,
                is_active=True
            ).first()
            run_by_user_id = perm.userID if perm else None
            
            # Fallback to any active user in tenant
            if not run_by_user_id:
                u = db.session.query(User).filter_by(tenantID=tenant.tenantID, status='active').first()
                run_by_user_id = u.userID if u else None
            
            # Create job log for test run
            job_log = ScheduleJobLog(
                tenantID=tenant.tenantID,
                scheduleDefID=schedule_def.scheduleDefID,
                runByUserID=run_by_user_id or "system",
                status='pending',
                metadata={
                    'parameters': {},
                    'priority': 'normal',
                    'requested_at': datetime.utcnow().isoformat(),
                    'trigger': 'test-2min-auto-run',
                    'schedule_name': schedule_def.scheduleName
                }
            )
            db.session.add(job_log)
            db.session.commit()
            
            logger.info(f"[TEST_2MIN] Created job log {job_log.logID} for schedule {schedule_def.scheduleName}")
            
            # Prepare schedule config for run_refactored.py execution
            schedule_config = {
                'input_source': 'google_sheets',
                'input_config': {
                    'spreadsheet_url': schedule_def.paramsSheetURL,
                    'credentials_path': flask_app.config.get('GOOGLE_APPLICATION_CREDENTIALS', 'service-account-creds.json')
                },
                'output_destination': 'google_sheets',
                'output_config': {
                    'spreadsheet_url': schedule_def.resultsSheetURL,
                    'credentials_path': flask_app.config.get('GOOGLE_APPLICATION_CREDENTIALS', 'service-account-creds.json')
                },
                'schedule_def_id': schedule_def.scheduleDefID,
                'job_log_id': job_log.logID
            }
            
            # Enqueue Celery task to execute run_refactored.py
            logger.info(f"[TEST_2MIN] Enqueuing execution task for schedule {schedule_def.scheduleName} (job_log: {job_log.logID})")
            celery_app.send_task(
                'celery_tasks.execute_scheduling_task',
                args=[schedule_config],
                kwargs={'job_log_id': job_log.logID}
            )
            logger.info(f"[TEST_2MIN] ✅ Execution task enqueued for schedule {schedule_def.scheduleName}")
            logger.info(f"[TEST_2MIN] Task will execute run_refactored.py via Celery worker")
            logger.info("=" * 80)
            
            return {"success": True, "job_log_id": job_log.logID, "schedule_name": schedule_def.scheduleName}
            
        except Exception as e:
            import traceback
            logger.error(f"[TEST_2MIN] ❌ Test 2-minute auto-schedule failed: {e}")
            logger.error(f"[TEST_2MIN] Traceback: {traceback.format_exc()}")
            return {"success": False, "error": str(e)}

    @celery_app.task(name="auto_sync_employee_data")
    def auto_sync_employee_data():
        """
        Automatic periodic task to sync Employee IDs from Google Sheets to database.
        Runs every 5 minutes to ensure EmployeeMapping table is always up-to-date.
        """
        try:
            from flask import current_app as flask_app
            from app import db
            from app.models import ScheduleDefinition
            from app.services.google_sheets_sync_service import GoogleSheetsSyncService
            import logging
            
            logger = logging.getLogger(__name__)
            logger.info("[SYNC] 🔄 Starting automatic Employee ID sync from Google Sheets...")
            
            # Get credentials path
            creds_path = flask_app.config.get('GOOGLE_APPLICATION_CREDENTIALS', 'service-account-creds.json')
            sync_service = GoogleSheetsSyncService(creds_path)
            
            # Get all active schedule definitions and sync employee mappings for each
            with flask_app.app_context():
                schedule_defs = db.session.query(ScheduleDefinition).filter_by(is_active=True).all()
                
                total_synced = 0
                for schedule_def in schedule_defs:
                    try:
                        # Sync employee mappings for this schedule definition
                        sync_result = sync_service.sync_schedule_data(
                            schedule_def_id=schedule_def.scheduleDefID,
                            sync_type='auto',
                            triggered_by=None,
                            force=False  # Don't force - respect rate limits and time thresholds
                        )
                        
                        if sync_result.get('success'):
                            rows_synced = sync_result.get('rows_synced', 0)
                            total_synced += rows_synced
                            logger.info(f"[SYNC] ✅ Synced {rows_synced} rows for schedule {schedule_def.scheduleName}")
                        else:
                            # Check if it was skipped due to recent sync
                            if sync_result.get('skipped'):
                                logger.debug(f"[SYNC] ⏭️ Sync skipped for {schedule_def.scheduleName}: {sync_result.get('message')}")
                            else:
                                logger.warning(f"[SYNC] ⚠️ Sync failed for {schedule_def.scheduleName}: {sync_result.get('error')}")
                    except Exception as e:
                        logger.warning(f"[SYNC] ⚠️ Error syncing schedule {schedule_def.scheduleDefID}: {e}")
                
                logger.info(f"[SYNC] ✅ Employee IDs auto-synced successfully. Total rows synced: {total_synced}")
                return {
                    "success": True,
                    "total_synced": total_synced,
                    "schedules_processed": len(schedule_defs)
                }
                
        except Exception as e:
            import logging, traceback
            logger = logging.getLogger(__name__)
            logger.error(f"[SYNC] ❌ Auto-sync Employee IDs failed:\n{traceback.format_exc()}")
            return {"success": False, "error": str(e)}
    
    @celery_app.task(name="daily_sync_all_schedules")
    def daily_sync_all_schedules():
        """
        Daily sync task - syncs all active schedule definitions to database.
        Runs at 2 AM daily via Celery Beat to ensure data is synced to DB.
        This is a backup sync in case sync after execution fails.
        Users fetch data from DB (CachedSchedule table), not directly from Google Sheets.
        """
        try:
            from flask import current_app as flask_app
            from app import db
            from app.models import ScheduleDefinition
            from app.services.google_sheets_sync_service import GoogleSheetsSyncService
            import logging
            
            logger = logging.getLogger(__name__)
            logger.info("[DAILY_SYNC] 🔄 Starting daily sync of all schedules to database...")
            logger.info("[DAILY_SYNC] This ensures users can fetch data from DB (CachedSchedule table)")
            
            # Get all active schedule definitions
            schedule_defs = db.session.query(ScheduleDefinition).filter_by(is_active=True).all()
            logger.info(f"[DAILY_SYNC] Found {len(schedule_defs)} active schedules to sync")
            
            # Get credentials path
            creds_path = flask_app.config.get('GOOGLE_APPLICATION_CREDENTIALS', 'service-account-creds.json')
            sync_service = GoogleSheetsSyncService(creds_path)
            
            total_synced = 0
            total_failed = 0
            
            for schedule_def in schedule_defs:
                try:
                    logger.info(f"[DAILY_SYNC] Syncing schedule: {schedule_def.scheduleName} ({schedule_def.scheduleDefID})")
                    sync_result = sync_service.sync_schedule_data(
                        schedule_def_id=schedule_def.scheduleDefID,
                        sync_type='auto',
                        triggered_by=None,
                        force=True  # Force sync to get fresh data
                    )
                    
                    if sync_result.get('success'):
                        rows_synced = sync_result.get('rows_synced', 0)
                        users_synced = sync_result.get('users_synced', 0)
                        logger.info(f"[DAILY_SYNC] ✅ Synced {schedule_def.scheduleName}: {rows_synced} rows, {users_synced} users")
                        total_synced += 1
                    else:
                        error_msg = sync_result.get('error', 'Unknown error')
                        logger.warning(f"[DAILY_SYNC] ⚠️ Failed to sync {schedule_def.scheduleName}: {error_msg}")
                        total_failed += 1
                except Exception as sync_error:
                    import traceback
                    logger.error(f"[DAILY_SYNC] ❌ Error syncing {schedule_def.scheduleName}: {sync_error}")
                    logger.error(f"[DAILY_SYNC] Traceback: {traceback.format_exc()}")
                    total_failed += 1
            
            logger.info(f"[DAILY_SYNC] ✅ Daily sync completed: {total_synced} succeeded, {total_failed} failed")
            logger.info(f"[DAILY_SYNC] ✅ Users can now fetch schedule data from database (CachedSchedule table)")
            
            return {
                "success": True,
                "schedules_synced": total_synced,
                "schedules_failed": total_failed,
                "total_schedules": len(schedule_defs)
            }
        except Exception as e:
            import logging, traceback
            logger = logging.getLogger(__name__)
            logger.error(f"[DAILY_SYNC] ❌ Daily sync task failed: {e}")
            logger.error(f"[DAILY_SYNC] Traceback: {traceback.format_exc()}")
            return {"success": False, "error": str(e)}
    
    @celery_app.task(name="refresh_google_sheets_data")
    def refresh_google_sheets_data():
        """
        Daily task to refresh/validate Google Sheets data for all active schedule definitions.
        This ensures all sheets are accessible and credentials are valid.
        """
        # CRITICAL: Import os at the very beginning to avoid UnboundLocalError
        import os
        try:
            from flask import current_app as flask_app
            from app import db
            from app.models import ScheduleDefinition
            import logging
            import sys
            
            logger = logging.getLogger(__name__)
            logger.info("Starting daily Google Sheets refresh...")
            
            # Import GoogleSheetsService
            project_root = Path(__file__).resolve().parents[2].parent
            project_root_str = str(project_root)
            if project_root_str not in sys.path:
                sys.path.insert(0, project_root_str)
            
            try:
                from app.services.google_sheets.service import GoogleSheetsService
            except ImportError:
                # Try alternative path
                # os is already imported at the beginning of the function
                sys.path.insert(0, os.path.join(project_root_str, 'app'))
                from services.google_sheets.service import GoogleSheetsService
            
            # Get credentials path
            creds_path = flask_app.config.get('GOOGLE_APPLICATION_CREDENTIALS', 'service-account-creds.json')
            service = GoogleSheetsService(creds_path)
            
            # Get all active schedule definitions
            with flask_app.app_context():
                schedule_defs = db.session.query(ScheduleDefinition).filter_by(is_active=True).all()
                
                refresh_results = {
                    "total": len(schedule_defs),
                    "success": 0,
                    "failed": 0,
                    "details": []
                }
                
                for sd in schedule_defs:
                    try:
                        # Validate and refresh all 6 sheets for this schedule definition
                        main_spreadsheet_url = sd.paramsSheetURL
                        results_spreadsheet_url = sd.resultsSheetURL
                        
                        # Read all sheets to validate they're accessible
                        params_data = service.read_parameters_sheet(main_spreadsheet_url)
                        employee_data = service.read_employee_sheet(main_spreadsheet_url)
                        preferences_data = service.read_preferences_sheet(main_spreadsheet_url)
                        preschedule_data = service.read_preschedule_sheet(sd.prefsSheetURL or main_spreadsheet_url)
                        designation_flow_data = service.read_designation_flow_sheet(main_spreadsheet_url)
                        final_output_data = service.read_final_output_sheet(results_spreadsheet_url)
                        
                        # Count successful reads
                        success_count = sum([
                            params_data.get("success", False),
                            employee_data.get("success", False),
                            preferences_data.get("success", False),
                            preschedule_data.get("success", False),
                            designation_flow_data.get("success", False),
                            final_output_data.get("success", False)
                        ])
                        
                        if success_count >= 4:  # At least Parameters and Pre-Schedule must succeed
                            refresh_results["success"] += 1
                            logger.info(f"✓ Refreshed sheets for schedule: {sd.scheduleName} ({sd.scheduleDefID})")
                        else:
                            refresh_results["failed"] += 1
                            logger.warning(f"✗ Some sheets failed for schedule: {sd.scheduleName} ({sd.scheduleDefID})")
                        
                        refresh_results["details"].append({
                            "schedule_def_id": sd.scheduleDefID,
                            "schedule_name": sd.scheduleName,
                            "success": success_count >= 4,
                            "sheets_read": success_count,
                            "sheets_total": 6
                        })
                        
                    except Exception as e:
                        refresh_results["failed"] += 1
                        logger.error(f"Error refreshing sheets for schedule {sd.scheduleDefID}: {e}")
                        refresh_results["details"].append({
                            "schedule_def_id": sd.scheduleDefID,
                            "schedule_name": sd.scheduleName,
                            "success": False,
                            "error": str(e)
                        })
                
                logger.info(f"Daily Google Sheets refresh completed: {refresh_results['success']}/{refresh_results['total']} succeeded")
                return refresh_results
                
        except Exception as e:
            import logging, traceback
            logger = logging.getLogger(__name__)
            logger.error(f"Daily Google Sheets refresh failed:\n{traceback.format_exc()}")
            return {"success": False, "error": str(e)}


