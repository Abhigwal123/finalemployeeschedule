"""
Schedule API Routes
Provides /api/v1/schedule/ endpoint for fetching employee schedule data

CRITICAL: All heavy imports (db, models, services) are moved inside functions
to prevent import-time crashes. Only lightweight imports at module level.
"""
# LIGHTWEIGHT IMPORTS ONLY - Safe to import at module level
from flask import Blueprint, jsonify, request, make_response, Response
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
from flask_jwt_extended import get_jwt
from flask_jwt_extended.exceptions import (
    NoAuthorizationError, InvalidHeaderError, JWTDecodeError
)
# ExpiredSignatureError and InvalidTokenError come from PyJWT, not flask_jwt_extended
# Import PyJWT with alias to avoid conflict with JWTManager (jwt)
import jwt as pyjwt
ExpiredSignatureError = pyjwt.ExpiredSignatureError
InvalidTokenError = pyjwt.InvalidTokenError
import logging
import time
import os
from datetime import datetime, date
from math import ceil

from ..utils.role_utils import is_client_admin_role, is_schedule_manager_role

# Create logger and blueprint - these are safe at module level
logger = logging.getLogger(__name__)
schedule_bp = Blueprint("schedule", __name__)


# ============================================================================
# STEP 1: Register before_request handler for OPTIONS (MUST BE FIRST)
# ============================================================================
@schedule_bp.before_request
def skip_options_preflight():
    """
    Skip all middleware for OPTIONS preflight requests.
    This handler MUST return 200 OK for OPTIONS requests, even if exceptions occur.
    CRITICAL: OPTIONS check happens FIRST, before any logging.
    MUST NEVER throw exceptions that would cause 500 errors.
    """
    # CRITICAL: Check if we're in a request context first
    try:
        from flask import has_request_context
        if not has_request_context():
            return None
    except:
        # If we can't check context, just continue
        return None
    
    try:
        # Check OPTIONS FIRST - before ANY logging or other operations
        method = None
        try:
            method = request.method if hasattr(request, 'method') else None
        except (RuntimeError, AttributeError, Exception):
            # If request context is not available, try environ
            try:
                if hasattr(request, 'environ'):
                    method = request.environ.get('REQUEST_METHOD', None)
            except:
                pass
        
        # If OPTIONS, return 200 OK with CORS headers
        if method and str(method).upper() == "OPTIONS":
            # Get origin from request, default to http://localhost:5173
            origin = None
            try:
                if hasattr(request, 'headers'):
                    origin = request.headers.get('Origin', None)
            except:
                pass
            
            # Use specific origin (required for credentials=true)
            allow_origin = origin if origin and ('localhost' in origin or '127.0.0.1' in origin) else "http://localhost:5173"
            
            try:
                resp = make_response(("", 200))
                resp.headers["Access-Control-Allow-Origin"] = allow_origin
                resp.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
                resp.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
                resp.headers["Access-Control-Allow-Credentials"] = "true"
                return resp
            except Exception as resp_err:
                # Fallback to tuple response
                try:
                    return ("", 200, {
                        "Access-Control-Allow-Origin": allow_origin,
                        "Access-Control-Allow-Methods": "GET, OPTIONS",
                        "Access-Control-Allow-Headers": "Authorization, Content-Type",
                        "Access-Control-Allow-Credentials": "true"
                    })
                except:
                    # Absolute last resort - return minimal response
                    return ("", 200)
        
        # If not OPTIONS, return None to continue with normal request processing
        return None
    
    except Exception as handler_error:
        # CRITICAL: If handler fails, we MUST NOT block GET requests
        # Only return response if we're reasonably sure it's OPTIONS
        # Otherwise, return None to let the route handler deal with it
        try:
            # Try to determine if it's OPTIONS one more time
            method = None
            try:
                if hasattr(request, 'method'):
                    method = request.method
            except:
                pass
            
            # Only return response if we're sure it's OPTIONS
            if method and str(method).upper() == "OPTIONS":
                try:
                    resp = make_response(("", 200))
                    resp.headers["Access-Control-Allow-Origin"] = "http://localhost:5173"
                    resp.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
                    resp.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
                    resp.headers["Access-Control-Allow-Credentials"] = "true"
                    return resp
                except:
                    return ("", 200)
            
            # For GET or unknown methods, return None to continue processing
            return None
        except:
            # If everything fails, return None to let route handler deal with it
            return None


# ============================================================================
# STEP 2: Helper function for CORS headers
# ============================================================================
def apply_cors_headers(resp):
    """
    Helper function to apply CORS headers to a response.
    Uses http://localhost:5173 for credentials support.
    """
    from flask import request as flask_request
    origin = None
    try:
        if hasattr(flask_request, 'headers'):
            origin = flask_request.headers.get('Origin', None)
    except:
        pass
    
    # Use specific origin (required for credentials=true)
    allow_origin = origin if origin and ('localhost' in origin or '127.0.0.1' in origin) else "http://localhost:5173"
    
    resp.headers["Access-Control-Allow-Origin"] = allow_origin
    resp.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
    resp.headers["Access-Control-Allow-Credentials"] = "true"
    return resp


# ============================================================================
# STEP 3: Register routes
# ============================================================================
@schedule_bp.route("/", methods=["GET"])
def get_schedule():
    """
    GET /api/v1/schedule/?month=YYYY-MM
    
    Fetch schedule data for the authenticated employee
    """
    # HEAVY IMPORTS INSIDE FUNCTION - moved from top level
    # CRITICAL: Use relative import to ensure same db instance
    from ..extensions import db
    from app.models import User
    from app.utils.trace_logger import (
        trace_api_request, trace_sheets_fetch, trace_response, trace_error
    )
    
    start_time = time.time()
    
    # JWT required for actual GET request
    verify_jwt_in_request()
    
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if not user:
            trace_error('API Request', 'schedule_routes.py', 'User not found')
            response = jsonify({'error': 'User not found'})
            response = apply_cors_headers(response)
            trace_response(404, (time.time() - start_time) * 1000, '/api/v1/schedule/')
            return response, 404
        
        month = request.args.get('month')
        
        # Trace API request
        trace_api_request('/api/v1/schedule/', user.userID, {'month': month})
        
        logger.info(f"Fetching schedule for user {user.userID} (username: {user.username}), month: {month}")
        
        # Ensure data is synced before fetching (if using cache)
        from app.models import ScheduleDefinition
        schedule_def = ScheduleDefinition.query.filter_by(
            tenantID=user.tenantID,
            is_active=True
        ).first()
        
        if schedule_def:
            from app.utils.sync_guard import ensure_data_synced
            sync_status = ensure_data_synced(
                user_id=current_user_id,
                schedule_def_id=schedule_def.scheduleDefID,
                employee_id=user.employee_id,
                max_age_minutes=30  # Sync if data is older than 30 minutes
            )
            # Log sync status for debugging
            if sync_status.get('synced'):
                logger.info(f"[TRACE][SYNC] Auto-sync completed: {sync_status.get('reason', 'N/A')}")
            elif sync_status.get('used_cache'):
                logger.debug(f"[TRACE][SYNC] Using cached data: {sync_status.get('reason', 'N/A')}")
        
        # Try to import Google Sheets service
        from app.services.google_sheets_import import _try_import_google_sheets, SHEETS_AVAILABLE, fetch_schedule_data
        from app.services.dashboard_data_service import DashboardDataService
        from flask import current_app
        
        # Force retry import if not available
        if not SHEETS_AVAILABLE:
            logger.warning("Google Sheets service not available, attempting import...")
            success, path = _try_import_google_sheets(force_retry=True)
            if not success:
                trace_error('Sheets Fetch', 'schedule_routes.py', f'Import failed: {path}')
                error_msg = "Google Sheets service not available. Check backend logs for import errors."
                response = jsonify({'success': False, 'error': error_msg})
                response = apply_cors_headers(response)
                trace_response(503, (time.time() - start_time) * 1000, '/api/v1/schedule/')
                return response, 503
        
        # Get credentials path - resolve to project root if relative
        creds_path = current_app.config.get('GOOGLE_APPLICATION_CREDENTIALS', 'service-account-creds.json')
        if not os.path.isabs(creds_path) and not os.path.exists(creds_path):
            # Try project root
            backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            project_root = os.path.dirname(backend_dir)
            project_creds = os.path.join(project_root, 'service-account-creds.json')
            if os.path.exists(project_creds):
                creds_path = project_creds
                logger.info(f"[TRACE] Found credentials at project root: {creds_path}")
        logger.info(f"[TRACE] Using credentials path: {creds_path}")
        logger.info(f"[TRACE] Credentials file exists: {os.path.exists(creds_path)}")
        
        # Get dashboard data service
        logger.info(f"[TRACE] Creating DashboardDataService with creds_path: {creds_path}")
        service = DashboardDataService(creds_path)
        
        logger.info(f"[TRACE] Calling get_employee_dashboard_data for user_id: {current_user_id}")
        dashboard_data = service.get_employee_dashboard_data(current_user_id, None)
        
        logger.info(f"[TRACE] Dashboard data response - success: {dashboard_data.get('success')}, has_data: {bool(dashboard_data.get('data'))}, error: {dashboard_data.get('error', 'None')}")
        
        # Extract schedule data
        # Handle case where dashboard_data might be a dict or list
        logger.info(f"[TRACE] Dashboard data type: {type(dashboard_data)}")
        
        if isinstance(dashboard_data, dict):
            dashboard_success = dashboard_data.get('success', False)
            dashboard_data_obj = dashboard_data.get('data')
            logger.info(f"[TRACE] Dashboard success: {dashboard_success}, has data: {bool(dashboard_data_obj)}")
        else:
            # If it's not a dict, treat as error
            logger.error(f"[TRACE] Unexpected dashboard_data type: {type(dashboard_data)}, value: {str(dashboard_data)[:100]}")
            dashboard_success = False
            dashboard_data_obj = None
        
        if dashboard_success and dashboard_data_obj:
            logger.info(f"[TRACE] Dashboard data has success=True and data exists")
            my_schedule = dashboard_data_obj.get('my_schedule', {})
            rows = my_schedule.get('rows', [])
            columns = my_schedule.get('columns', [])
            
            logger.info(f"[TRACE] Extracted schedule data - rows: {len(rows)}, columns: {len(columns) if columns else 0}")
            if rows:
                logger.info(f"[TRACE] First row sample (first 5 keys): {list(rows[0].keys())[:5] if isinstance(rows[0], dict) else 'Not a dict'}")
                # Log the employee identifier column value if it exists
                if isinstance(rows[0], dict):
                    emp_col_key = '員工(姓名/ID)'
                    if emp_col_key in rows[0]:
                        logger.info(f"[TRACE] Employee identifier in row: '{rows[0][emp_col_key]}'")
            logger.info(f"[TRACE] Column sample (first 10): {columns[:10] if columns else 'No columns'}")
            if columns and month:
                # Find columns matching the month
                matching_cols = [col for col in columns if col and (month in col or month.replace('-', '/') in col)][:5]
                logger.info(f"[TRACE] Columns matching month '{month}': {matching_cols}")
            
            # Filter by month if provided
            schedule_entries = []
            if rows and columns:
                logger.info(f"[TRACE] Processing {len(rows)} rows with month filter: {month}")
                logger.info(f"[TRACE] First row keys (sample): {list(rows[0].keys())[:5] if rows and isinstance(rows[0], dict) else 'No rows'}")
                
                # Get time period helper function
                def get_time_period(shift_type):
                    shift_map = {
                        'D': '08:00 - 17:00',
                        'E': '16:00 - 01:00',
                        'N': '00:00 - 09:00',
                        'OFF': '休假'
                    }
                    return shift_map.get(shift_type.upper(), '08:00 - 17:00')
                
                # First, try to find columns matching the requested month
                matching_columns = []
                month_pattern = None
                if month:
                    # Convert "2025-11" to "2025/11" pattern for matching
                    if '-' in month:
                        parts = month.split('-')
                        if len(parts) == 2:
                            month_pattern = f"{parts[0]}/{int(parts[1])}/"  # "2025/11/"
                            logger.info(f"[TRACE] Month filter pattern: '{month_pattern}' (from '{month}')")
                    else:
                        month_pattern = month
                    
                    # Find all columns matching the month pattern
                    for col in columns:
                        if col and col != 'username' and col != 'employee_id' and col != '員工(姓名/ID)':
                            col_matches = (
                                col.startswith(month) or  # Direct match "2025-11"
                                col.startswith(month_pattern) or  # Pattern match "2025/11/"
                                month_pattern.replace('/', '-') in col or  # Reverse pattern
                                month in col  # Contains month
                            )
                            if col_matches:
                                matching_columns.append(col)
                    
                    logger.info(f"[TRACE] Found {len(matching_columns)} columns matching month '{month}'")
                    if matching_columns:
                        logger.info(f"[TRACE] Sample matching columns: {matching_columns[:3]}")
                
                # If no columns match requested month, try fallback to previous month
                fallback_used = False
                if len(matching_columns) == 0 and month:
                    logger.info(f"[TRACE] No columns found for month '{month}', checking fallback...")
                    logger.warning(f"[TRACE] No columns found for month '{month}', trying fallback to previous month...")
                    try:
                        year, month_num = month.split('-')
                        # Try previous month
                        prev_month_num = int(month_num) - 1
                        if prev_month_num == 0:
                            prev_month_num = 12
                            year = str(int(year) - 1)
                        prev_month_pattern = f"{year}/{prev_month_num:02d}/"  # e.g., "2025/10/"
                        logger.info(f"[TRACE] Trying fallback to previous month pattern: '{prev_month_pattern}'")
                        
                        for col in columns:
                            if col and col != 'username' and col != 'employee_id' and col != '員工(姓名/ID)':
                                if prev_month_pattern in str(col):
                                    matching_columns.append(col)
                        
                        if matching_columns:
                            fallback_used = True
                            logger.info(f"[TRACE] ✅ Fallback found {len(matching_columns)} columns for previous month")
                            logger.info(f"[TRACE] Sample fallback columns: {matching_columns[:3]}")
                    except Exception as fallback_err:
                        logger.warning(f"[TRACE] Fallback logic failed: {fallback_err}")
                
                # If still no columns, use all date columns (show all available data)
                if len(matching_columns) == 0:
                    logger.warning(f"[TRACE] No month-specific columns found, using all date columns")
                    for col in columns:
                        if col and col != 'username' and col != 'employee_id' and col != '員工(姓名/ID)':
                            # Check if it looks like a date column (contains '/' or date pattern)
                            if '/' in str(col) or any(char.isdigit() for char in str(col)):
                                matching_columns.append(col)
                    logger.info(f"[TRACE] Using {len(matching_columns)} date columns (all available)")
                
                # Now process rows with matching columns
                logger.info(f"[TRACE] Processing {len(rows)} rows with {len(matching_columns)} matching columns")
                for row in rows:
                    if isinstance(row, dict):
                        for col in matching_columns:
                            cell_value = row.get(col)
                            # Check if cell has any value (including empty string check)
                            if cell_value is not None and str(cell_value).strip() != '':
                                shift_value = str(cell_value).strip()
                                
                                # Handle complex shift values like "A 櫃台人力" -> extract shift type
                                # Map common patterns to shift types
                                shift_type = None
                                shift_upper = shift_value.upper()
                                
                                if shift_upper in ['OFF', '休', '休假']:
                                    shift_type = 'OFF'
                                elif 'D' in shift_upper or '白' in shift_value:
                                    shift_type = 'D'
                                elif 'E' in shift_upper or '小夜' in shift_value:
                                    shift_type = 'E'
                                elif 'N' in shift_upper or '大夜' in shift_value:
                                    shift_type = 'N'
                                else:
                                    # For complex values like "A 櫃台人力", default to D or use the value as-is
                                    # Check if it's a simple single letter
                                    if len(shift_value) == 1 and shift_value in ['D', 'E', 'N']:
                                        shift_type = shift_value
                                    else:
                                        # Use 'D' as default for complex assignments
                                        shift_type = 'D'
                                
                                schedule_entries.append({
                                    'date': col,
                                    'shift_type': shift_type or 'D',
                                    'shiftType': shift_type or 'D',  # Frontend compatibility
                                    'time_range': get_time_period(shift_type or 'D'),
                                    'timeRange': get_time_period(shift_type or 'D'),  # Frontend compatibility
                                    'assignment': shift_value if shift_type != shift_value else None  # Keep original value for complex assignments
                                })
                    elif isinstance(row, list):
                        # Handle array format
                        for col_idx, col_name in enumerate(matching_columns):
                            col_idx_in_cols = columns.index(col_name) if col_name in columns else -1
                            if col_idx_in_cols >= 0 and col_idx_in_cols < len(row):
                                cell_value = row[col_idx_in_cols]
                                if cell_value and str(cell_value).strip():
                                    shift_value = str(cell_value).strip()
                                    shift_upper = shift_value.upper()
                                    
                                    if shift_upper in ['OFF', '休', '休假']:
                                        shift_type = 'OFF'
                                    elif shift_value in ['D', 'E', 'N']:
                                        shift_type = shift_value
                                    else:
                                        shift_type = 'D'  # Default
                                    
                                    schedule_entries.append({
                                        'date': col_name,
                                        'shift_type': shift_type,
                                        'shiftType': shift_type,
                                        'time_range': get_time_period(shift_type),
                                        'timeRange': get_time_period(shift_type)
                                    })
                
                logger.info(f"[TRACE] Created {len(schedule_entries)} schedule entries after filtering")
                if len(schedule_entries) > 0:
                    logger.info(f"[TRACE] ✅ Sample schedule entry (first): {schedule_entries[0]}")
                    logger.info(f"[TRACE] ✅ Sample schedule entry (last): {schedule_entries[-1]}")
                elif len(matching_columns) > 0:
                    # Debug why entries are empty even though we have matching columns
                    logger.warning(f"[TRACE] ⚠️ No schedule entries created despite having {len(matching_columns)} matching columns")
                    # Check first row for sample values
                    if rows and len(rows) > 0:
                        first_row = rows[0]
                        sample_values = {}
                        non_empty_count = 0
                        for col in matching_columns[:10]:
                            val = first_row.get(col) if isinstance(first_row, dict) else 'N/A'
                            sample_values[col] = val
                            if val and str(val).strip():
                                non_empty_count += 1
                        logger.warning(f"[TRACE] Sample cell values from first row (first 10 columns): {sample_values}")
                        logger.warning(f"[TRACE] Non-empty cells in first 10 columns: {non_empty_count}/10")
            else:
                logger.warning(f"[TRACE] No rows or columns to process - rows: {len(rows) if rows else 0}, columns: {len(columns) if columns else 0}")
            
            # Trace sheets fetch
            trace_sheets_fetch(len(rows), month, success=True)
            
            # Prepare response
            response_data = {
                'success': True,
                'user_id': user.userID,
                'employee': f"EMP-{user.userID}",  # Frontend expects this format
                'month': month,
                'schedule': schedule_entries,
                'metadata': {
                    'total_rows': len(rows) if rows else 0,
                    'total_entries': len(schedule_entries),
                    'month_pattern': month_pattern if 'month_pattern' in locals() else month,
                    'fallback_used': fallback_used if 'fallback_used' in locals() else False
                }
            }
            
            logger.info(f"[DEBUG] ========== SCHEDULE API RESPONSE ==========")
            logger.info(f"[DEBUG] Response Data Structure:")
            logger.info(f"[DEBUG]   - success: {response_data.get('success')}")
            logger.info(f"[DEBUG]   - user_id: {response_data.get('user_id')}")
            logger.info(f"[DEBUG]   - employee: {response_data.get('employee')}")
            logger.info(f"[DEBUG]   - month: {response_data.get('month')}")
            logger.info(f"[DEBUG]   - schedule_entries_count: {len(schedule_entries)}")
            logger.info(f"[DEBUG]   - schedule type: {type(schedule_entries)}")
            if schedule_entries:
                logger.info(f"[DEBUG]   - First entry: {schedule_entries[0]}")
                logger.info(f"[DEBUG]   - Last entry: {schedule_entries[-1]}")
            logger.info(f"[DEBUG]   - metadata: {response_data.get('metadata')}")
            logger.info(f"[DEBUG] ===========================================")
            logger.info(f"[TRACE] Final API response payload: success=True, schedule_entries={len(schedule_entries)}, month={month}")
            
            # If no entries found, add helpful message
            if len(schedule_entries) == 0:
                # Check what months are available
                available_months = set()
                if columns:
                    for col in columns:
                        if '/' in str(col):
                            # Extract month from date column (e.g., "2025/10/01" -> "2025/10")
                            parts = str(col).split('/')
                            if len(parts) >= 2:
                                month_str = f"{parts[0]}/{parts[1]}"
                                available_months.add(month_str)
                
                if available_months:
                    months_list = sorted(list(available_months))
                    response_data['message'] = f"No schedule data for {month}. Available months: {', '.join(months_list)}"
                    response_data['available_months'] = months_list
                    logger.warning(f"[TRACE] No data for {month}. Available months: {months_list}")
                else:
                    response_data['message'] = f"No schedule data for {month}. No date columns found in sheet."
                    logger.warning(f"[TRACE] No data for {month} and no available months detected")
            else:
                logger.info(f"[TRACE] First schedule entry: {schedule_entries[0]}")
            
            # Log the exact JSON being sent
            import json
            json_str = json.dumps(response_data, ensure_ascii=False, default=str)
            logger.info(f"[DEBUG] JSON Response (first 500 chars): {json_str[:500]}")
            logger.info(f"[DEBUG] JSON Response length: {len(json_str)} bytes")
            
            response = jsonify(response_data)
            response = apply_cors_headers(response)
            duration_ms = (time.time() - start_time) * 1000
            trace_response(200, duration_ms, '/api/v1/schedule/')
            
            logger.info(f"[DEBUG] ✅ Sending response with status 200, {len(schedule_entries)} entries")
            return response, 200
            
        else:
            error_msg = dashboard_data.get('error', 'Failed to fetch schedule data')
            logger.error(f"[DEBUG] ========== SCHEDULE API ERROR ==========")
            logger.error(f"[DEBUG] Dashboard data success: {dashboard_data.get('success')}")
            logger.error(f"[DEBUG] Dashboard data error: {error_msg}")
            logger.error(f"[DEBUG] Dashboard data keys: {list(dashboard_data.keys())}")
            logger.error(f"[DEBUG] Dashboard data: {dashboard_data}")
            logger.error(f"[DEBUG] ==========================================")
            
            trace_error('Sheets Fetch', 'schedule_routes.py', error_msg)
            trace_sheets_fetch(0, month, success=False)
            
            error_response = {
                'success': False,
                'error': error_msg,
                'schedule': []
            }
            
            logger.info(f"[DEBUG] Error response JSON: {json.dumps(error_response, ensure_ascii=False)}")
            
            response = jsonify(error_response)
            response = apply_cors_headers(response)
            duration_ms = (time.time() - start_time) * 1000
            trace_response(400, duration_ms, '/api/v1/schedule/')
            return response, 400
            
    except Exception as e:
        logger.error(f"Error fetching schedule: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        error_response = {
            'success': False,
            'error': 'Failed to fetch schedule',
            'details': str(e),
            'schedule': []
        }
        trace_error('API Request', 'schedule_routes.py', str(e))
        response = jsonify(error_response)
        response = apply_cors_headers(response)
        duration_ms = (time.time() - start_time) * 1000
        trace_response(500, duration_ms, '/api/v1/schedule/')
        return response, 500


@schedule_bp.route("/employee/<employee_id>", methods=["GET"])
def get_employee_schedule(employee_id):
    """
    GET /api/v1/schedule/employee/<employee_id>?month=YYYY-MM
    
    Fetch schedule data for a specific employee by employee_id
    This endpoint uses JWT authentication and fetches schedules from database cache
    """
    # HEAVY IMPORTS INSIDE FUNCTION
    # CRITICAL: Use relative import to ensure same db instance
    from ..extensions import db
    from app.models import User
    from app.utils.trace_logger import trace_response, trace_error
    
    start_time = time.time()
    
    # JWT required
    verify_jwt_in_request()
    
    try:
        current_user_id = get_jwt_identity()
        logger.info(f"[TRACE][SYNC] /api/v1/schedule/employee/{employee_id} called by user {current_user_id}")
        
        user = User.query.get(current_user_id)
        
        if not user:
            logger.error(f"[TRACE][SYNC] User not found for ID: {current_user_id}")
            response = jsonify({'error': 'User not found'})
            response = apply_cors_headers(response)
            trace_response(404, (time.time() - start_time) * 1000, f'/api/v1/schedule/employee/{employee_id}')
            return response, 404
        
        # Verify user has permission to view this employee's schedule
        # For now, allow users to view their own schedule only
        if user.employee_id and user.employee_id.upper() != employee_id.upper() and user.username.upper() != employee_id.upper():
            # Check if user is admin/scheduler (can view any employee)
            if user.role and not (is_client_admin_role(user.role) or is_schedule_manager_role(user.role)):
                logger.warning(f"[TRACE][SYNC] User {user.userID} attempted to view schedule for different employee {employee_id}")
                response = jsonify({
                    'success': False,
                    'error': 'Permission denied. You can only view your own schedule.',
                    'schedule': []
                })
                response = apply_cors_headers(response)
                trace_response(403, (time.time() - start_time) * 1000, f'/api/v1/schedule/employee/{employee_id}')
                return response, 403
        
        # Find user by employee_id
        target_user = None
        if user.employee_id and user.employee_id.upper() == employee_id.upper():
            target_user = user
        elif user.username and user.username.upper() == employee_id.upper():
            target_user = user
        else:
            # Try to find user by employee_id
            target_user = User.query.filter(
                (User.employee_id == employee_id.upper()) | (User.username == employee_id.upper())
            ).first()
        
        if not target_user:
            logger.warning(f"[TRACE][SYNC] No user found for employee_id '{employee_id}'")
            response = jsonify({
                'success': False,
                'error': f'No user found for employee_id: {employee_id}',
                'schedule': []
            })
            response = apply_cors_headers(response)
            trace_response(404, (time.time() - start_time) * 1000, f'/api/v1/schedule/employee/{employee_id}')
            return response, 404
        
        logger.info(f"[TRACE][SYNC] Fetching schedule for employee_id='{employee_id}', user_id={target_user.userID}")
        
        month = request.args.get('month')
        
        # Get active schedule definition for user's tenant
        from app.models import ScheduleDefinition, CachedSchedule, SyncLog
        schedule_def = ScheduleDefinition.query.filter_by(
            tenantID=target_user.tenantID,
            is_active=True
        ).first()
        
        # Ensure data is synced before fetching
        if schedule_def:
            from app.utils.sync_guard import ensure_data_synced
            sync_status = ensure_data_synced(
                user_id=target_user.userID,
                schedule_def_id=schedule_def.scheduleDefID,
                employee_id=target_user.employee_id or target_user.username,
                max_age_minutes=30  # Sync if data is older than 30 minutes
            )
            # Log sync status for debugging
            if sync_status.get('synced'):
                logger.info(f"[TRACE][SYNC] Auto-sync completed: {sync_status.get('reason', 'N/A')}")
            elif sync_status.get('used_cache'):
                logger.debug(f"[TRACE][SYNC] Using cached data: {sync_status.get('reason', 'N/A')}")
        
        if not schedule_def:
            logger.warning(f"[TRACE][SYNC] No active schedule definition found for tenant {target_user.tenantID}")
            response_data = {
                "success": True,
                "user_id": target_user.userID,
                "employee_id": target_user.employee_id or target_user.username,
                "month": month,
                "schedule": [],
                "source": "database",
                "message": "No active schedule found"
            }
            response = jsonify(response_data)
            response = apply_cors_headers(response)
            trace_response(200, (time.time() - start_time) * 1000, f'/api/v1/schedule/employee/{employee_id}')
            return response, 200
        
        logger.info(f"[TRACE][SYNC] Using schedule definition: {schedule_def.scheduleName} ({schedule_def.scheduleDefID})")
        
        # Get cached schedule from database using user_id
        schedules_query = CachedSchedule.get_user_schedule(
            user_id=target_user.userID,
            schedule_def_id=schedule_def.scheduleDefID,
            month=month,
            max_age_hours=0  # Disable age filtering - show all cached data
        )
        
        schedules_result = schedules_query.all()
        logger.info(f"[TRACE][SYNC] Found {len(schedules_result)} schedule entries for employee_id='{employee_id}' (user_id={target_user.userID})")
        
        schedules = []
        for schedule_entry in schedules_result:
            # CRITICAL SECURITY CHECK: Verify each entry belongs to the target user
            if schedule_entry.user_id != target_user.userID:
                logger.error(f"[TRACE][SYNC] SECURITY ISSUE: Schedule entry {schedule_entry.id} has user_id={schedule_entry.user_id} but expected {target_user.userID}")
                logger.error(f"[TRACE][SYNC] Skipping this entry to prevent data leakage")
                continue  # Skip entries that don't belong to this user
            
            schedules.append({
                "date": schedule_entry.date.isoformat() if schedule_entry.date else None,
                "shift_type": schedule_entry.shift_type,
                "shiftType": schedule_entry.shift_type,  # Frontend expects camelCase
                "time_range": schedule_entry.time_range,
                "timeRange": schedule_entry.time_range  # Frontend expects camelCase
            })
        
        # Get last sync time
        last_sync = SyncLog.get_last_sync(schedule_def_id=schedule_def.scheduleDefID)
        last_synced_at = last_sync.completed_at.isoformat() if last_sync and last_sync.completed_at else None
        
        if len(schedules) == 0:
            logger.warning(f"[TRACE][SYNC] No schedule entries found for employee_id='{employee_id}' (user_id={target_user.userID})")
            # Check if EmployeeMapping exists
            from app.models import EmployeeMapping
            mapping = EmployeeMapping.find_by_sheets_identifier(employee_id, schedule_def.scheduleDefID)
            if mapping:
                logger.info(f"[TRACE][SYNC] EmployeeMapping exists for employee_id='{employee_id}' - schedules may need sync")
            else:
                logger.warning(f"[TRACE][SYNC] No EmployeeMapping found for employee_id='{employee_id}'")
        
        # Get employee name from EmployeeMapping if available
        employee_name = None
        from app.models import EmployeeMapping
        mapping = EmployeeMapping.find_by_sheets_identifier(
            target_user.employee_id or target_user.username,
            schedule_def.scheduleDefID
        )
        if mapping and mapping.employee_sheet_name:
            employee_name = mapping.employee_sheet_name
        elif mapping and mapping.sheets_name_id and '/' in mapping.sheets_name_id:
            # Extract name from sheets_name_id format (e.g., "謝○穎/E01")
            employee_name = mapping.sheets_name_id.split('/')[0]
        
        response_data = {
            "success": True,
            "user_id": target_user.userID,
            "employee_id": target_user.employee_id or target_user.username,
            "employee_name": employee_name,  # Include employee name
            "month": month,
            "schedule": schedules,
            "source": "database",
            "last_synced_at": last_synced_at,
            "cache_count": len(schedules)
        }
        
        logger.info(f"[TRACE][SYNC] Returning {len(schedules)} schedule entries for employee_id='{employee_id}'")
        
        response = jsonify(response_data)
        response = apply_cors_headers(response)
        duration_ms = (time.time() - start_time) * 1000
        trace_response(200, duration_ms, f'/api/v1/schedule/employee/{employee_id}')
        return response, 200
        
    except Exception as e:
        logger.error(f"[TRACE][SYNC] Error in /api/v1/schedule/employee/{employee_id}: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        error_response = {
            'success': False,
            'error': 'Failed to fetch schedule',
            'details': str(e),
            'schedule': []
        }
        trace_error('API Request', 'schedule_routes.py', str(e))
        response = jsonify(error_response)
        response = apply_cors_headers(response)
        duration_ms = (time.time() - start_time) * 1000
        trace_response(500, duration_ms, f'/api/v1/schedule/employee/{employee_id}')
        return response, 500


@schedule_bp.route("/my", methods=["GET"])
def my_schedule():
    """Return cached schedule rows for the authenticated employee."""

    def _apply_cors(resp: Response) -> Response:
        resp.headers["Access-Control-Allow-Origin"] = "http://localhost:5173"
        resp.headers["Access-Control-Allow-Methods"] = "GET"
        resp.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
        resp.headers["Access-Control-Allow-Credentials"] = "true"
        return resp

    try:
        from app.models import User, ScheduleDefinition, CachedSchedule
    except Exception as import_error:  # pragma: no cover
        logger.error(f"[SCHEDULE_MY] Import error: {import_error}")
        return _apply_cors(jsonify({"success": False, "error": "Server configuration error"})), 500

    try:
        verify_jwt_in_request()
        current_user_id = get_jwt_identity()
        claims = get_jwt()
    except Exception as jwt_error:
        response = jsonify({
            "success": False,
            "error": "Authentication required",
            "details": str(jwt_error),
        })
        return _apply_cors(response), 401

    user = User.query.get(current_user_id)
    if not user:
        return _apply_cors(jsonify({"success": False, "error": "User not found"})), 404

    # CRITICAL: Validate that JWT user_id matches the user's userID
    if current_user_id != user.userID:
        logger.error(f"[SCHEDULE_MY] Security: JWT user_id ({current_user_id}) does not match user.userID ({user.userID})")
        return _apply_cors(jsonify({"success": False, "error": "User authentication mismatch"})), 403

    employee_id = claims.get("username") or user.employee_id or user.username
    if not employee_id:
        return _apply_cors(jsonify({"success": False, "error": "Employee ID missing"})), 400

    # Log for debugging
    logger.info(f"[SCHEDULE_MY] Fetching schedule for user_id={user.userID}, username={user.username}, employee_id={employee_id}")

    month_raw = (request.args.get("month") or datetime.utcnow().strftime("%Y-%m")).strip()
    try:
        year_part, month_part = month_raw.split("-")
        year = int(year_part)
        month_num = int(month_part)
        start_date = date(year, month_num, 1)
        end_date = date(year + 1, 1, 1) if month_num == 12 else date(year, month_num + 1, 1)
    except ValueError:
        return _apply_cors(jsonify({"success": False, "error": "Invalid month format"})), 400

    schedule_def = (
        ScheduleDefinition.query.filter_by(tenantID=user.tenantID, is_active=True)
        .order_by(ScheduleDefinition.created_at.asc())
        .first()
    )

    if not schedule_def:
        payload = {
            "success": True,
            "employee_id": employee_id,
            "month": month_raw,
            "entries": [],
        }
        return _apply_cors(jsonify(payload)), 200

    # CRITICAL: Ensure we only fetch schedules for the logged-in user
    # Double-check that we're using user.userID (not current_user_id) for consistency
    schedule_rows = (
        CachedSchedule.query.filter(
            CachedSchedule.tenant_id == user.tenantID,
            CachedSchedule.schedule_def_id == schedule_def.scheduleDefID,
            CachedSchedule.user_id == user.userID,  # CRITICAL: Filter by logged-in user's userID
            CachedSchedule.date >= start_date,
            CachedSchedule.date < end_date,
        )
        .order_by(CachedSchedule.date.asc())
        .all()
    )
    
    # Log for debugging
    logger.info(f"[SCHEDULE_MY] ========== FETCHING SCHEDULE ==========")
    logger.info(f"[SCHEDULE_MY] User ID: {user.userID}")
    logger.info(f"[SCHEDULE_MY] Username: {user.username}")
    logger.info(f"[SCHEDULE_MY] Employee ID: {employee_id}")
    logger.info(f"[SCHEDULE_MY] Tenant ID: {user.tenantID}")
    logger.info(f"[SCHEDULE_MY] Schedule Def ID: {schedule_def.scheduleDefID if schedule_def else 'N/A'}")
    logger.info(f"[SCHEDULE_MY] Month: {month_raw}")
    logger.info(f"[SCHEDULE_MY] Date range: {start_date} to {end_date}")
    logger.info(f"[SCHEDULE_MY] Found {len(schedule_rows)} schedule entries")
    
    if len(schedule_rows) > 0:
        # Verify all entries belong to this user
        mismatched_count = 0
        for row in schedule_rows:
            if row.user_id != user.userID:
                mismatched_count += 1
                logger.error(f"[SCHEDULE_MY] SECURITY ISSUE: Schedule entry {row.id} has user_id={row.user_id} but expected {user.userID}")
        
        if mismatched_count > 0:
            logger.error(f"[SCHEDULE_MY] ⚠️ WARNING: {mismatched_count} entries have incorrect user_id!")
        else:
            logger.info(f"[SCHEDULE_MY] ✅ All {len(schedule_rows)} entries belong to user {user.userID}")
        
        # Log sample entries
        logger.info(f"[SCHEDULE_MY] Sample entries (first 3):")
        for i, row in enumerate(schedule_rows[:3]):
            logger.info(f"[SCHEDULE_MY]   Entry {i+1}: date={row.date}, shift_value='{row.shift_value}', shift_type={row.shift_type}, user_id={row.user_id}")
        
        # Count entries per user_id (should all be the same)
        user_ids = set(row.user_id for row in schedule_rows)
        if len(user_ids) > 1:
            logger.error(f"[SCHEDULE_MY] ⚠️ WARNING: Found multiple user_ids in results: {user_ids}")
            for uid in user_ids:
                count = sum(1 for row in schedule_rows if row.user_id == uid)
                logger.error(f"[SCHEDULE_MY]   user_id={uid}: {count} entries")
        else:
            logger.info(f"[SCHEDULE_MY] ✅ All entries belong to single user_id: {list(user_ids)[0]}")
    else:
        logger.warning(f"[SCHEDULE_MY] ⚠️ No schedule entries found for user {user.userID}")
        # Check if there are any entries for this schedule_def at all
        total_count = CachedSchedule.query.filter_by(
            schedule_def_id=schedule_def.scheduleDefID
        ).count()
        logger.info(f"[SCHEDULE_MY] Total entries in schedule_def: {total_count}")
        
        # Check entries for other users
        other_users = db.session.query(CachedSchedule.user_id).filter_by(
            schedule_def_id=schedule_def.scheduleDefID
        ).distinct().all()
        if other_users:
            logger.info(f"[SCHEDULE_MY] Found entries for {len(other_users)} other users")
    
    logger.info(f"[SCHEDULE_MY] =====================================")

    SHIFT_NAME_MAP = {
        "A": "早班",
        "B": "中班",
        "C": "晚班",
        "D": "日班",
        "E": "晚班",
        "N": "夜班",
        "OFF": "休假",
    }

    def _split_time_range(raw: str | None) -> tuple[str | None, str | None]:
        if not raw or raw.strip() in {"", "--"}:
            return None, None
        parts = [part.strip() for part in raw.split("-")]
        if len(parts) != 2:
            return None, None
        start_val, end_val = parts
        start_val = start_val if start_val and start_val != "--" else None
        end_val = end_val if end_val and end_val != "--" else None
        return start_val, end_val

    entries = []
    for row in schedule_rows:
        # CRITICAL: Use raw shift_value from sheet (e.g., "C 櫃台人力", "A 藥局人力")
        # Fallback to shift_type if shift_value is not available (for backward compatibility)
        shift_value = (row.shift_value or row.shift_type or "").strip()
        shift_code = (row.shift_type or "").strip()  # Keep normalized for internal use
        shift_name = SHIFT_NAME_MAP.get(shift_code, shift_value)  # Use raw value as name if not in map
        start_time, end_time = _split_time_range(row.time_range)

        entries.append(
            {
                "date": row.date.isoformat(),
                "shift": shift_value,  # CRITICAL: Return EXACT value from sheet
                "shift_code": shift_code,  # Keep for backward compatibility
                "shift_name": shift_name,
                "start_time": start_time or "",
                "end_time": end_time or "",
            }
        )

    payload = {
        "success": True,
        "employee_id": employee_id,
        "month": month_raw,
        "entries": entries,
    }

    return _apply_cors(jsonify(payload)), 200


# ============================================================================
# STEP 4: Register JWT error handlers (MUST BE AFTER ROUTES)
# ============================================================================
@schedule_bp.errorhandler(NoAuthorizationError)
def handle_no_auth_error(e):
    """Handle NoAuthorizationError - check if OPTIONS first"""
    try:
        if hasattr(request, 'method') and request.method == "OPTIONS":
            origin = None
            try:
                if hasattr(request, 'headers'):
                    origin = request.headers.get('Origin', None)
            except:
                pass
            allow_origin = origin if origin and ('localhost' in origin or '127.0.0.1' in origin) else "http://localhost:5173"
            
            resp = make_response(("", 200))
            resp.headers["Access-Control-Allow-Origin"] = allow_origin
            resp.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
            resp.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
            resp.headers["Access-Control-Allow-Credentials"] = "true"
            return resp
    except:
        pass
    # For non-OPTIONS, return normal error with CORS headers
    response = jsonify({'error': 'Authentication required', 'details': str(e)})
    response = apply_cors_headers(response)
    return response, 401


@schedule_bp.errorhandler(JWTDecodeError)
def handle_jwt_decode_error(e):
    """Handle JWTDecodeError - check if OPTIONS first"""
    try:
        if hasattr(request, 'method') and request.method == "OPTIONS":
            origin = None
            try:
                if hasattr(request, 'headers'):
                    origin = request.headers.get('Origin', None)
            except:
                pass
            allow_origin = origin if origin and ('localhost' in origin or '127.0.0.1' in origin) else "http://localhost:5173"
            
            resp = make_response(("", 200))
            resp.headers["Access-Control-Allow-Origin"] = allow_origin
            resp.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
            resp.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
            resp.headers["Access-Control-Allow-Credentials"] = "true"
            return resp
    except:
        pass
    # For non-OPTIONS, return normal error with CORS headers
    response = jsonify({'error': 'Invalid token', 'details': str(e)})
    response = apply_cors_headers(response)
    return response, 422


@schedule_bp.errorhandler(InvalidTokenError)
def handle_invalid_token_error(e):
    """Handle InvalidTokenError - check if OPTIONS first"""
    try:
        if hasattr(request, 'method') and request.method == "OPTIONS":
            origin = None
            try:
                if hasattr(request, 'headers'):
                    origin = request.headers.get('Origin', None)
            except:
                pass
            allow_origin = origin if origin and ('localhost' in origin or '127.0.0.1' in origin) else "http://localhost:5173"
            
            resp = make_response(("", 200))
            resp.headers["Access-Control-Allow-Origin"] = allow_origin
            resp.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
            resp.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
            resp.headers["Access-Control-Allow-Credentials"] = "true"
            return resp
    except:
        pass
    # For non-OPTIONS, return normal error with CORS headers
    response = jsonify({'error': 'Invalid token', 'details': str(e)})
    response = apply_cors_headers(response)
    return response, 422
