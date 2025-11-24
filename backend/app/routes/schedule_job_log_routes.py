# Schedule Job Log Routes
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
# CRITICAL: Use relative import to ensure same db instance
from ..extensions import db
from ..models import ScheduleJobLog, User, ScheduleDefinition, SchedulePermission
from ..utils.role_utils import is_sys_admin_role, is_client_admin_role, normalize_role, SYS_ADMIN_ROLE, CLIENT_ADMIN_ROLE
try:
    from app.schemas import ScheduleJobLogSchema, ScheduleJobLogUpdateSchema, PaginationSchema, JobRunSchema
    SCHEMAS_AVAILABLE = True
except ImportError:
    SCHEMAS_AVAILABLE = False
    ScheduleJobLogSchema = None
    ScheduleJobLogUpdateSchema = None
    PaginationSchema = None
    JobRunSchema = None
from datetime import datetime, timedelta
import logging
import os

logger = logging.getLogger(__name__)

schedule_job_log_bp = Blueprint('schedule_job_logs', __name__)

def get_current_user():
    """Get current authenticated user"""
    current_user_id = get_jwt_identity()
    return User.query.get(current_user_id)

def require_admin_or_scheduler():
    """Decorator to require admin or scheduler role"""
    def decorator(f):
        def decorated_function(*args, **kwargs):
            user = get_current_user()
            # Allow ScheduleManager, Schedule_Manager, admin, and scheduler roles
            allowed_roles = ['admin', 'scheduler', 'ScheduleManager', 'Schedule_Manager']
            if not user or user.role not in allowed_roles:
                return jsonify({'error': 'Admin or scheduler access required'}), 403
            return f(*args, **kwargs)
        decorated_function.__name__ = f.__name__
        return decorated_function
    return decorator

@schedule_job_log_bp.route('/', methods=['GET'])
@schedule_job_log_bp.route('', methods=['GET'])  # Support both / and no slash
@jwt_required()
def get_schedule_job_logs():
    """Get schedule job logs for current tenant"""
    import logging
    trace_logger = logging.getLogger('trace')
    
    trace_logger.info("[TRACE] Backend: GET /schedule-job-logs")
    trace_logger.info(f"[TRACE] Backend: Path: {request.path}")
    trace_logger.info(f"[TRACE] Backend: Full path: {request.full_path}")
    trace_logger.info(f"[TRACE] Backend: Query params: {dict(request.args)}")
    
    try:
        from flask_jwt_extended import get_jwt_identity, get_jwt
        current_user_id = get_jwt_identity()
        claims = get_jwt() or {}
        trace_logger.info(f"[TRACE] Backend: User ID: {current_user_id}")
        trace_logger.info(f"[TRACE] Backend: Role: {claims.get('role')}")
    except:
        pass
    
    try:
        user = get_current_user()
        if not user:
            response = jsonify({'error': 'User not found'})
            response.headers.add("Access-Control-Allow-Origin", "*")
            return response, 404
        
        # Parse pagination parameters with safe defaults
        # Default to 10 logs (last 10 execution logs)
        try:
            if SCHEMAS_AVAILABLE and PaginationSchema:
                pagination_schema = PaginationSchema()
                pagination_data = pagination_schema.load(request.args)
                page = int(pagination_data.get('page', 1))
                per_page = min(int(pagination_data.get('per_page', 10)), 100)
            else:
                page = int(request.args.get('page', 1) or 1)
                per_page = min(int(request.args.get('per_page', 10) or 10), 100)
        except Exception:
            page = int(request.args.get('page', 1) or 1)
            per_page = min(int(request.args.get('per_page', 10) or 10), 100)
        
        # Query job logs for current tenant
        logs_query = ScheduleJobLog.query.filter_by(tenantID=user.tenantID)
        
        # Apply user filter if specified
        user_filter = request.args.get('user_id')
        if user_filter:
            logs_query = logs_query.filter_by(runByUserID=user_filter)
        
        # Apply schedule filter if specified (support both schedule_def_id and scheduleDefID)
        schedule_filter = request.args.get('schedule_def_id') or request.args.get('scheduleDefID')
        if schedule_filter:
            logs_query = logs_query.filter_by(scheduleDefID=schedule_filter)
            trace_logger.info(f"[DEBUG] Schedule filter: {schedule_filter}")
        
        # Apply status filter if specified
        status_filter = request.args.get('status')
        if status_filter:
            logs_query = logs_query.filter_by(status=status_filter)
        
        # Apply date range filter if specified (support both date_from and dateFrom)
        date_from = request.args.get('date_from') or request.args.get('dateFrom')
        if date_from:
            try:
                # Handle both ISO format and simple date string
                if 'T' in date_from:
                    date_from_dt = datetime.fromisoformat(date_from.replace('Z', '+00:00'))
                else:
                    date_from_dt = datetime.strptime(date_from, '%Y-%m-%d')
                logs_query = logs_query.filter(ScheduleJobLog.startTime >= date_from_dt)
                trace_logger.info(f"[DEBUG] Date filter from: {date_from_dt}")
            except ValueError as e:
                trace_logger.warning(f"[DEBUG] Invalid date_from format: {date_from}, error: {e}")
        
        date_to = request.args.get('date_to') or request.args.get('dateTo')
        if date_to:
            try:
                # Handle both ISO format and simple date string
                if 'T' in date_to:
                    date_to_dt = datetime.fromisoformat(date_to.replace('Z', '+00:00'))
                else:
                    # For date only, set to end of day
                    date_to_dt = datetime.strptime(date_to, '%Y-%m-%d')
                    date_to_dt = date_to_dt.replace(hour=23, minute=59, second=59)
                logs_query = logs_query.filter(ScheduleJobLog.startTime <= date_to_dt)
                trace_logger.info(f"[DEBUG] Date filter to: {date_to_dt}")
            except ValueError as e:
                trace_logger.warning(f"[DEBUG] Invalid date_to format: {date_to}, error: {e}")
        
        logs_pagination = logs_query.order_by(ScheduleJobLog.startTime.desc()).paginate(
            page=page, 
            per_page=per_page, 
            error_out=False
        )
        
        logs = [log.to_dict() for log in logs_pagination.items]
        
        trace_logger.info(f"[TRACE] Backend: Query result - total: {logs_pagination.total}, page: {page}, items: {len(logs)}")
        trace_logger.info(f"[DEBUG] Checking Schedule Logs → count: {len(logs)}")
        if len(logs) == 0:
            trace_logger.warning(f"[DEBUG] No logs found - tenantID: {user.tenantID}, filters: {dict(request.args)}")
        
        response = jsonify({
            'success': True,
            'data': logs,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': logs_pagination.total,
                'pages': logs_pagination.pages,
                'has_next': logs_pagination.has_next,
                'has_prev': logs_pagination.has_prev
            }
        })
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response, 200
        
    except Exception as e:
        logger.error(f"Get schedule job logs error: {str(e)}")
        return jsonify({'error': 'Failed to retrieve schedule job logs', 'details': str(e)}), 500

@schedule_job_log_bp.route('/', methods=['POST'])
@jwt_required()
@require_admin_or_scheduler()
def create_schedule_job_log():
    """Create a new schedule job log"""
    try:
        current_user = get_current_user()
        
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Validate job log data
        log_schema = ScheduleJobLogSchema()
        errors = log_schema.validate(data)
        if errors:
            return jsonify({'error': 'Invalid job log data', 'details': errors}), 400
        
        # Verify schedule definition belongs to tenant
        schedule_def = ScheduleDefinition.query.get(data['scheduleDefID'])
        if not schedule_def or schedule_def.tenantID != current_user.tenantID:
            return jsonify({'error': 'Invalid schedule definition'}), 400
        
        # Verify user belongs to tenant
        run_by_user = User.query.get(data['runByUserID'])
        if not run_by_user or run_by_user.tenantID != current_user.tenantID:
            return jsonify({'error': 'Invalid user'}), 400
        
        # Create job log
        job_log = ScheduleJobLog(
            tenantID=current_user.tenantID,
            scheduleDefID=data['scheduleDefID'],
            runByUserID=data['runByUserID'],
            startTime=data.get('startTime', datetime.utcnow()),
            status=data.get('status', 'pending'),
            metadata=data.get('metadata', {})
        )
        
        db.session.add(job_log)
        db.session.commit()
        
        logger.info(f"New schedule job log created: {job_log.logID} by user: {current_user.username}")
        
        return jsonify({
            'success': True,
            'message': 'Schedule job log created successfully',
            'data': job_log.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Create schedule job log error: {str(e)}")
        return jsonify({'error': 'Failed to create schedule job log', 'details': str(e)}), 500

@schedule_job_log_bp.route('/run', methods=['POST'])
@jwt_required()
def run_schedule_job():
    """Run a schedule job"""
    import logging
    trace_logger = logging.getLogger('trace')
    
    trace_logger.info("[TRACE] Backend: POST /schedule-job-logs/run")
    
    try:
        from flask_jwt_extended import get_jwt_identity, get_jwt
        current_user_id = get_jwt_identity()
        claims = get_jwt() or {}
        trace_logger.info(f"[TRACE] Backend: User ID: {current_user_id}")
        trace_logger.info(f"[TRACE] Backend: Role: {claims.get('role')}")
    except:
        pass
    
    try:
        current_user = get_current_user()
        if not current_user:
            response = jsonify({'error': 'User not found'})
            response.headers.add("Access-Control-Allow-Origin", "*")
            return response, 404
        
        data = request.get_json()
        trace_logger.info(f"[TRACE] Backend: Request data: {data}")
        trace_logger.info(f"[DEBUG] Current user role: {current_user.role}")
        trace_logger.info(f"[DEBUG] Current user tenantID: {current_user.tenantID}")
        
        if not data:
            response = jsonify({'error': 'No data provided'})
            response.headers.add("Access-Control-Allow-Origin", "*")
            return response, 400
        
        # Validate run job data (with fallback if schema not available)
        if SCHEMAS_AVAILABLE and JobRunSchema:
            run_schema = JobRunSchema()
            errors = run_schema.validate(data)
            if errors:
                response = jsonify({'error': 'Invalid run job data', 'details': errors})
                response.headers.add("Access-Control-Allow-Origin", "*")
                return response, 400
        else:
            # Basic validation without schema
            if not data.get('scheduleDefID'):
                response = jsonify({'error': 'scheduleDefID is required'})
                response.headers.add("Access-Control-Allow-Origin", "*")
                return response, 400
        
        schedule_def_id = data['scheduleDefID']
        
        # Find schedule definition
        schedule_def = ScheduleDefinition.query.get(schedule_def_id)
        if not schedule_def:
            return jsonify({'error': 'Schedule definition not found'}), 404
        
        trace_logger.info(f"[DEBUG] Schedule tenantID: {schedule_def.tenantID}")
        
        # Check tenant access (skip for SysAdmin and ClientAdmin as they have elevated permissions)
        # Check role using normalized comparison
        normalized_role = normalize_role(current_user.role)
        is_client_admin = is_client_admin_role(current_user.role)
        is_sys_admin = is_sys_admin_role(current_user.role)
        
        # Fallback: also check raw role string (case-insensitive) for edge cases
        raw_role_lower = (current_user.role or '').lower().strip()
        is_sys_admin_fallback = raw_role_lower in ['sysadmin', 'sys_admin', 'sys-admin']
        is_client_admin_fallback = raw_role_lower in ['clientadmin', 'client_admin', 'client-admin', 'admin']
        
        is_admin_user = is_client_admin or is_sys_admin or is_sys_admin_fallback or is_client_admin_fallback
        
        trace_logger.info(f"[DEBUG] User role (raw): '{current_user.role}'")
        trace_logger.info(f"[DEBUG] User role (normalized): '{normalized_role}'")
        trace_logger.info(f"[DEBUG] Is ClientAdmin (function): {is_client_admin}")
        trace_logger.info(f"[DEBUG] Is SysAdmin (function): {is_sys_admin}")
        trace_logger.info(f"[DEBUG] Is SysAdmin (fallback): {is_sys_admin_fallback}")
        trace_logger.info(f"[DEBUG] Is admin user (ClientAdmin or SysAdmin): {is_admin_user}")
        
        if not is_admin_user and current_user.tenantID != schedule_def.tenantID:
            trace_logger.warning(f"[DEBUG] Tenant mismatch: user tenant {current_user.tenantID} != schedule tenant {schedule_def.tenantID}")
            response = jsonify({'error': 'Access denied'})
            response.headers.add("Access-Control-Allow-Origin", "*")
            return response, 403
        
        # Check if user has permission to run this schedule
        # Allow ClientAdmin and SysAdmin to run any schedule in their tenant
        if not is_admin_user:
            # Try multiple methods to find permission
            permission = None
            try:
                if hasattr(SchedulePermission, 'find_by_user_and_schedule'):
                    permission = SchedulePermission.find_by_user_and_schedule(current_user.userID, schedule_def_id)
                else:
                    # Fallback: query directly
                    permission = SchedulePermission.query.filter_by(
                        userID=current_user.userID,
                        scheduleDefID=schedule_def_id,
                        is_active=True
                    ).first()
            except Exception as perm_error:
                trace_logger.warning(f"[DEBUG] Permission check error: {perm_error}")
            
            if not permission:
                # For ScheduleManager role, allow if schedule belongs to their tenant
                if current_user.role in ['ScheduleManager', 'Schedule_Manager'] and schedule_def.tenantID == current_user.tenantID:
                    trace_logger.info(f"[DEBUG] Allowing ScheduleManager to run schedule in their tenant")
                else:
                    trace_logger.warning(f"[DEBUG] Permission denied: user {current_user.userID} ({current_user.role}) cannot run schedule {schedule_def_id}")
                    response = jsonify({'error': 'Permission denied to run this schedule'})
                    response.headers.add("Access-Control-Allow-Origin", "*")
                    return response, 403
            elif hasattr(permission, 'is_valid') and not permission.is_valid():
                trace_logger.warning(f"[DEBUG] Permission expired or invalid for user {current_user.userID}")
                response = jsonify({'error': 'Permission expired or invalid'})
                response.headers.add("Access-Control-Allow-Origin", "*")
                return response, 403
        else:
            # Admin users (ClientAdmin or SysAdmin) can run schedules
            trace_logger.info(f"[DEBUG] Allowing {current_user.role} (admin user) to run schedule {schedule_def_id} (admin privilege)")
            logger.info(f"[INFO] Admin user {current_user.username} ({current_user.role}) running schedule {schedule_def.scheduleName}")
        
        # Create job log
        job_log = ScheduleJobLog(
            tenantID=current_user.tenantID,
            scheduleDefID=schedule_def_id,
            runByUserID=current_user.userID,
            status='pending',
            metadata={
                'parameters': data.get('parameters', {}),
                'priority': data.get('priority', 'normal'),
                'requested_at': datetime.utcnow().isoformat()
            }
        )
        
        db.session.add(job_log)
        db.session.commit()
        
        # Enqueue the job for background processing via Celery
        from flask import current_app as flask_app
        
        # CRITICAL: Get the actual Flask app instance (not proxy) for background thread
        # We need to get it from the current request context
        try:
            flask_app_instance = flask_app._get_current_object()
        except RuntimeError:
            # If we can't get it from current_app, try to import it from app creation
            from .. import create_app
            flask_app_instance = create_app()
        
        # Get Celery instance - try multiple methods
        celery_app = None
        try:
            # Method 1: Try to get from Flask app extensions
            if hasattr(flask_app, 'extensions') and 'celery' in flask_app.extensions:
                celery_app = flask_app.extensions['celery']
        except Exception as e:
            trace_logger.warning(f"[DEBUG] Failed to get Celery from Flask extensions: {e}")
        
        if not celery_app:
            try:
                # Method 2: Try to get from celery current_app
                from celery import current_app as celery_current_app
                celery_app = celery_current_app
                # Verify it's actually initialized (not just a placeholder)
                if celery_app and hasattr(celery_app, 'tasks'):
                    test_tasks = list(celery_app.tasks.keys())
                    if not test_tasks:
                        celery_app = None  # Not properly initialized
            except (AttributeError, RuntimeError, Exception) as e:
                trace_logger.warning(f"[DEBUG] Failed to get Celery from current_app: {e}")
                celery_app = None
        
        if not celery_app:
            try:
                # Method 3: Try to get from extensions module
                from app.extensions import celery as ext_celery
                if ext_celery and hasattr(ext_celery, 'tasks'):
                    celery_app = ext_celery
            except Exception as e:
                trace_logger.warning(f"[DEBUG] Failed to get Celery from extensions module: {e}")
        
        if not celery_app:
            trace_logger.warning(f"[DEBUG] Celery not available - will use synchronous fallback")
            logger.warning(f"[WARNING] Celery not initialized - schedule will run synchronously")
        
        # Try to use registered Celery tasks
        task_id = None
        task_enqueued = False
        
        if celery_app:
            # Check if execute_scheduling_task exists, otherwise use async_run_schedule
            registered_tasks = list(celery_app.tasks.keys())
            trace_logger.info(f"[DEBUG] Available Celery tasks: {registered_tasks}")
            
            # Prepare schedule config from definition
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
                'schedule_def_id': schedule_def_id,
                'job_log_id': job_log.logID
            }
            
            # Try execute_scheduling_task first, fallback to async_run_schedule
            task_name = None
            if 'celery_tasks.execute_scheduling_task' in registered_tasks:
                task_name = 'celery_tasks.execute_scheduling_task'
            elif 'async_run_schedule' in registered_tasks:
                task_name = 'async_run_schedule'
                # async_run_schedule expects (input_url, output_url) instead of config dict
                schedule_config = (
                    schedule_config.get('input_config', {}).get('spreadsheet_url'),
                    schedule_config.get('output_config', {}).get('spreadsheet_url')
                )
            
            if task_name:
                trace_logger.info(f"[DEBUG] Triggering Celery Task: {task_name}")
                trace_logger.info(f"[DEBUG] Job Params: schedule={schedule_def.scheduleName}, logID={job_log.logID}")
                trace_logger.info(f"[DEBUG] Schedule Config: schedule_def_id={schedule_config.get('schedule_def_id')}, job_log_id={schedule_config.get('job_log_id')}")
                
                # Check if Celery worker is actually running and can process tasks
                worker_available = False
                try:
                    # Try to inspect active workers
                    inspect = celery_app.control.inspect()
                    active_workers = inspect.active()
                    if active_workers:
                        worker_available = True
                        trace_logger.info(f"[DEBUG] ✅ Celery workers detected: {list(active_workers.keys())}")
                    else:
                        trace_logger.warning(f"[DEBUG] ⚠️ No active Celery workers detected")
                except Exception as inspect_error:
                    trace_logger.warning(f"[DEBUG] ⚠️ Could not inspect Celery workers: {inspect_error}")
                    # Assume worker might be available but inspection failed
                    worker_available = True  # Give it a chance
                
                if not worker_available:
                    trace_logger.warning(f"[DEBUG] ⚠️ Celery worker not available - will use synchronous execution")
                    logger.warning(f"[WARNING] ⚠️ Celery worker not running - will use synchronous execution")
                    # Don't try to enqueue if worker is not available
                    task_enqueued = False
                else:
                    try:
                        # Prepare task arguments based on task type
                        if task_name == 'celery_tasks.execute_scheduling_task':
                            task_args = [schedule_config]
                            task_kwargs = {'job_log_id': job_log.logID}
                        else:
                            task_args = schedule_config if isinstance(schedule_config, tuple) else [schedule_config]
                            task_kwargs = {}
                        
                        trace_logger.info(f"[DEBUG] Sending task with args={len(task_args)} items, kwargs={task_kwargs}")
                        
                        task = celery_app.send_task(
                            task_name,
                            args=task_args,
                            kwargs=task_kwargs
                        )
                        task_id = task.id
                        task_enqueued = True
                        
                        # Store Celery task ID in job log metadata
                        job_log.add_metadata('celery_task_id', task_id)
                        job_log.status = 'running'
                        db.session.commit()
                        
                        logger.info(f"[INFO] ✅ Schedule job queued successfully: job_log={job_log.logID}, celery_task={task_id}, schedule={schedule_def.scheduleName}, user={current_user.username} ({current_user.role})")
                        logger.info(f"[INFO] ✅ Task will execute run_refactored.py via Celery worker")
                        trace_logger.info(f"[DEBUG] ✅ Task enqueued: task_id={task_id}, status=running")
                    except Exception as celery_error:
                        import traceback
                        error_trace = traceback.format_exc()
                        trace_logger.error(f"[DEBUG] ❌ Celery task enqueue failed: {celery_error}")
                        trace_logger.error(f"[DEBUG] Error traceback: {error_trace}")
                        logger.error(f"❌ Failed to enqueue Celery task: {celery_error}")
                        logger.error(f"Error traceback: {error_trace}")
                        # Fall through to fallback
                        task_enqueued = False
            else:
                trace_logger.warning(f"[DEBUG] ⚠️ No suitable Celery task found. Available tasks: {registered_tasks}")
                trace_logger.warning(f"[DEBUG] Looking for: 'celery_tasks.execute_scheduling_task' or 'async_run_schedule'")
                logger.warning(f"⚠️ No suitable Celery task found for scheduling. Available: {registered_tasks}")
        
        if not task_enqueued:
            # Fallback: execute synchronously in background thread
            # This ensures run_refactored.py executes even if Celery worker is not running
            from app.services.schedule_executor import execute_schedule_task_sync
            
            trace_logger.info(f"[DEBUG] ⚠️ Falling back to synchronous execution (Celery worker not available)")
            logger.warning(f"[WARNING] ⚠️ Celery worker not available - using synchronous execution for job: {job_log.logID}")
            logger.info(f"[INFO] 🔄 Will execute run_refactored.py synchronously in background thread")
            logger.info(f"[INFO] This ensures the schedule runs even without Celery worker")
            
            # Execute in background thread to avoid blocking the HTTP response
            try:
                # Mark as running first
                job_log.start_job()
                db.session.commit()
                
                # Prepare schedule config for run_refactored.py execution
                schedule_config_fallback = {
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
                    'schedule_def_id': schedule_def_id,
                    'job_log_id': job_log.logID
                }
                
                # Execute in a background thread to avoid blocking the HTTP response
                # The thread will run run_refactored.py and update job status
                import threading
                # CRITICAL: Capture os from module level to avoid UnboundLocalError in nested function
                # Python's closure mechanism requires explicit capture for nested functions
                _os_module = os  # Capture module-level os import
                # CRITICAL: Capture Flask app for use in background thread
                flask_app_instance = flask_app._get_current_object()
                def run_schedule_in_thread():
                    try:
                        logger.info(f"[INFO] 🔄 Starting run_refactored.py execution in background thread for job {job_log.logID}")
                        logger.info(f"[INFO] This will fetch all sheets from input and write to output")
                        success = execute_schedule_task_sync(schedule_config_fallback, job_log.logID, flask_app=flask_app_instance)
                        if success:
                            logger.info(f"[INFO] ✅ run_refactored.py completed successfully for job {job_log.logID}")
                        else:
                            logger.error(f"[ERROR] ❌ run_refactored.py failed for job {job_log.logID}")
                    except Exception as thread_error:
                        import traceback
                        logger.error(f"[ERROR] ❌ Error in background thread: {thread_error}")
                        logger.error(f"[ERROR] Traceback: {traceback.format_exc()}")
                
                thread = threading.Thread(
                    target=run_schedule_in_thread,
                    daemon=False  # Not daemon so it completes even if main thread exits
                )
                thread.start()
                
                trace_logger.info(f"[DEBUG] ✅ Synchronous execution started in background thread for job {job_log.logID}")
                logger.info(f"[INFO] ✅ Background thread started - run_refactored.py will execute now")
                logger.info(f"[INFO] Job status will update to 'completed' when run_refactored.py finishes")
            except Exception as fallback_error:
                import traceback
                error_trace = traceback.format_exc()
                logger.error(f"[ERROR] ❌ Synchronous execution setup failed: {fallback_error}")
                logger.error(f"Error traceback: {error_trace}")
                trace_logger.error(f"[DEBUG] ❌ Fallback execution error: {fallback_error}")
                trace_logger.error(f"[DEBUG] Error traceback: {error_trace}")
                job_log.status = 'failed'
                job_log.error_message = f"Execution setup failed: {str(fallback_error)}"
                db.session.commit()
        
        trace_logger.info(f"[TRACE] Backend: Job created - logID: {job_log.logID}, status: {job_log.status}")
        
        response = jsonify({
            'success': True,
            'message': 'Schedule job started successfully',
            'data': job_log.to_dict(),
            'celery_task_id': job_log.get_metadata('celery_task_id') if celery_app else None
        })
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response, 201
        
    except Exception as e:
        db.session.rollback()
        import traceback
        error_trace = traceback.format_exc()
        trace_logger.error(f"[DEBUG] Run schedule job error: {e}")
        trace_logger.error(f"[DEBUG] Traceback: {error_trace}")
        logger.error(f"Run schedule job error: {str(e)}")
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Full traceback:\n{error_trace}")
        
        # Provide more detailed error message
        error_message = str(e)
        if "run_refactored" in error_message.lower() or "run_schedule_task" in error_message.lower():
            error_message = f"Scheduling system error: {error_message}. Please check that run_refactored.py and google modules are properly configured."
        elif "google.auth" in error_message or "google-auth" in error_message:
            error_message = f"Google authentication error: {error_message}. Please ensure google-auth package is installed."
        elif "import" in error_message.lower() and "error" in error_message.lower():
            error_message = f"Import error: {error_message}. Please check that all required modules are installed."
        
        response = jsonify({
            'error': 'Failed to run schedule job',
            'details': error_message,
            'error_type': type(e).__name__,
            'success': False
        })
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response, 500

@schedule_job_log_bp.route('/<log_id>', methods=['GET'])
@jwt_required()
def get_schedule_job_log(log_id):
    """Get specific schedule job log information"""
    try:
        user = get_current_user()
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Find job log
        job_log = ScheduleJobLog.query.get(log_id)
        if not job_log:
            return jsonify({'error': 'Schedule job log not found'}), 404
        
        # Check tenant access
        if user.tenantID != job_log.tenantID:
            return jsonify({'error': 'Access denied'}), 403
        
        return jsonify({
            'success': True,
            'data': job_log.to_dict()
        }), 200
        
    except Exception as e:
        logger.error(f"Get schedule job log error: {str(e)}")
        return jsonify({'error': 'Failed to retrieve schedule job log', 'details': str(e)}), 500

@schedule_job_log_bp.route('/<log_id>', methods=['PUT'])
@jwt_required()
@require_admin_or_scheduler()
def update_schedule_job_log(log_id):
    """Update schedule job log information"""
    try:
        current_user = get_current_user()
        
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Validate update data
        update_schema = ScheduleJobLogUpdateSchema()
        errors = update_schema.validate(data)
        if errors:
            return jsonify({'error': 'Invalid update data', 'details': errors}), 400
        
        # Find job log
        job_log = ScheduleJobLog.query.get(log_id)
        if not job_log:
            return jsonify({'error': 'Schedule job log not found'}), 404
        
        # Check tenant access
        if current_user.tenantID != job_log.tenantID:
            return jsonify({'error': 'Access denied'}), 403
        
        # Update fields
        if 'endTime' in data:
            job_log.endTime = data['endTime']
        
        if 'status' in data:
            job_log.status = data['status']
        
        if 'resultSummary' in data:
            job_log.resultSummary = data['resultSummary']
        
        if 'error_message' in data:
            job_log.error_message = data['error_message']
        
        if 'metadata' in data:
            job_log.metadata = data['metadata']
        
        job_log.updated_at = db.func.now()
        db.session.commit()
        
        logger.info(f"Schedule job log updated: {log_id} by user: {current_user.username}")
        
        return jsonify({
            'success': True,
            'message': 'Schedule job log updated successfully',
            'data': job_log.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Update schedule job log error: {str(e)}")
        return jsonify({'error': 'Failed to update schedule job log', 'details': str(e)}), 500

@schedule_job_log_bp.route('/<log_id>/cancel', methods=['POST'])
@jwt_required()
def cancel_schedule_job(log_id):
    """Cancel a running schedule job"""
    try:
        current_user = get_current_user()
        
        # Find job log
        job_log = ScheduleJobLog.query.get(log_id)
        if not job_log:
            return jsonify({'error': 'Schedule job log not found'}), 404
        
        # Check tenant access
        if current_user.tenantID != job_log.tenantID:
            return jsonify({'error': 'Access denied'}), 403
        
        # Check if user can cancel this job
        if not current_user.is_admin() and job_log.runByUserID != current_user.userID:
            return jsonify({'error': 'Permission denied to cancel this job'}), 403
        
        # Check if job can be cancelled
        if job_log.is_completed():
            return jsonify({'error': 'Job is already completed'}), 400
        
        # Cancel the job
        reason = request.get_json().get('reason', 'Cancelled by user') if request.get_json() else 'Cancelled by user'
        job_log.cancel_job(reason)
        
        logger.info(f"Schedule job cancelled: {log_id} by user: {current_user.username}")
        
        return jsonify({
            'success': True,
            'message': 'Schedule job cancelled successfully',
            'data': job_log.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Cancel schedule job error: {str(e)}")
        return jsonify({'error': 'Failed to cancel schedule job', 'details': str(e)}), 500

@schedule_job_log_bp.route('/<log_id>/export', methods=['GET'])
def export_schedule_job(log_id):
    """Export schedule results for a completed job as CSV"""
    import csv
    import io
    from flask import Response
    from app.models import CachedSchedule, User
    
    logger.info(f"[EXPORT] Export request: method={request.method}, log_id={log_id}, path={request.path}")
    
    # Handle CORS preflight - must be before @jwt_required to avoid 404
    # Require JWT for actual GET request
    from flask_jwt_extended import verify_jwt_in_request
    try:
        verify_jwt_in_request()
    except Exception as e:
        response = jsonify({'error': 'Authentication required'})
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response, 401
    
    try:
        current_user = get_current_user()
        if not current_user:
            response = jsonify({'error': 'User not found'})
            response.headers.add("Access-Control-Allow-Origin", "*")
            return response, 404
        
        # Find job log
        job_log = ScheduleJobLog.query.get(log_id)
        if not job_log:
            response = jsonify({'error': 'Schedule job log not found'})
            response.headers.add("Access-Control-Allow-Origin", "*")
            return response, 404
        
        # Check tenant access
        if current_user.tenantID != job_log.tenantID:
            response = jsonify({'error': 'Access denied'})
            response.headers.add("Access-Control-Allow-Origin", "*")
            return response, 403
        
        # Check if job is completed
        if job_log.status not in ['completed', 'success']:
            response = jsonify({'error': 'Job is not completed yet. Only completed jobs can be exported.'})
            response.headers.add("Access-Control-Allow-Origin", "*")
            return response, 400
        
        # Get schedule definition
        schedule_def = job_log.schedule_definition
        if not schedule_def:
            response = jsonify({'error': 'Schedule definition not found'})
            response.headers.add("Access-Control-Allow-Origin", "*")
            return response, 404
        
        # Get all cached schedules for this schedule definition
        cached_schedules = CachedSchedule.query.filter_by(
            schedule_def_id=job_log.scheduleDefID
        ).order_by(CachedSchedule.user_id, CachedSchedule.date).all()
        
        if not cached_schedules:
            response = jsonify({'error': 'No schedule data found for this job'})
            response.headers.add("Access-Control-Allow-Origin", "*")
            return response, 404
        
        # Get all unique users
        user_ids = list(set([s.user_id for s in cached_schedules]))
        users = {u.userID: u for u in User.query.filter(User.userID.in_(user_ids)).all()}
        
        # Create CSV in memory
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(['員工ID', '員工姓名', '日期', '星期', '班別', '時段'])
        
        # Group by user and write rows
        for user_id in sorted(user_ids):
            user = users.get(user_id)
            user_name = user.full_name if user else 'Unknown'
            user_display_id = f"SM-{str(user_id).zfill(3)}" if user_id else 'Unknown'
            
            # Get schedules for this user
            user_schedules = [s for s in cached_schedules if s.user_id == user_id]
            
            for schedule in sorted(user_schedules, key=lambda x: x.date):
                date_obj = schedule.date
                if date_obj:
                    # Get day of week
                    weekdays = ['週一', '週二', '週三', '週四', '週五', '週六', '週日']
                    weekday = weekdays[date_obj.weekday()]
                    
                    writer.writerow([
                        user_display_id,
                        user_name,
                        date_obj.strftime('%Y-%m-%d'),
                        weekday,
                        schedule.shift_type or '--',
                        schedule.time_range or '--'
                    ])
        
        # Create response
        output.seek(0)
        csv_data = output.getvalue()
        
        # Generate filename
        schedule_name = schedule_def.scheduleName.replace(' ', '_') if schedule_def.scheduleName else 'schedule'
        filename = f"{schedule_name}_{log_id[:8]}_{datetime.utcnow().strftime('%Y%m%d')}.csv"
        
        response = Response(
            csv_data,
            mimetype='text/csv',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Access-Control-Allow-Origin': '*'
            }
        )
        
        logger.info(f"Schedule exported: {log_id} by user: {current_user.username}, rows: {len(cached_schedules)}")
        
        return response, 200
        
    except Exception as e:
        logger.error(f"Export schedule job error: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        response = jsonify({'error': 'Failed to export schedule job', 'details': str(e)})
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response, 500







