from flask import Blueprint, jsonify, request, make_response
from flask_jwt_extended import jwt_required, get_jwt_identity
# CRITICAL: Use relative import to ensure same db instance
from ..extensions import db
from ..models import User
import logging
import os

logger = logging.getLogger(__name__)
employee_bp = Blueprint("employee", __name__)


# CRITICAL: Top-level OPTIONS bypass handler - MUST be first before_request
# This prevents JWT/auth middleware from running on OPTIONS requests
@employee_bp.before_request
def handle_options():
    """
    Skip all middleware for OPTIONS preflight requests.
    This handler MUST return 200 OK for OPTIONS requests, even if exceptions occur.
    """
    import sys
    
    # CRITICAL: Safely get request method - use multiple fallback strategies
    method = None
    path = 'unknown'
    
    # Strategy 1: Try request.method attribute (safest)
    try:
        if hasattr(request, 'method'):
            method = request.method
    except:
        pass
    
    # Strategy 2: Try request.environ if method is None
    if method is None:
        try:
            if hasattr(request, 'environ'):
                method = request.environ.get('REQUEST_METHOD', None)
        except:
            pass
    
    # Strategy 3: Try to get path safely
    try:
        if hasattr(request, 'path'):
            path = request.path
    except:
        try:
            if hasattr(request, 'environ'):
                path = request.environ.get('PATH_INFO', 'unknown')
        except:
            pass
    
    # CRITICAL: Log with flush=True to ensure logs appear immediately
    try:
        log_msg = f"[EMPLOYEE_BP][BEFORE_REQUEST] Method={method}, Path={path}"
        logger.info(log_msg)
        print(log_msg, flush=True)
        sys.stdout.flush()
    except:
        pass  # Don't let logging errors break the handler
    
    # CRITICAL: Check if OPTIONS - use string comparison for safety
    if method and str(method).upper() == "OPTIONS":
        try:
            log_msg = f"[TRACE][CORS] ✅ OPTIONS preflight detected in employee_bp for {path}"
            logger.info(log_msg)
            print(log_msg, flush=True)
            sys.stdout.flush()
        except:
            pass
        
        # CRITICAL: Return 200 OK with CORS headers - use multiple fallback strategies
        # Strategy 1: Try make_response (preferred)
        try:
            response = make_response(("", 200))
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With, Origin, Accept"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Max-Age"] = "3600"
            
            log_msg = "[TRACE][CORS] ✅ Returning 200 OK response for OPTIONS (make_response)"
            logger.info(log_msg)
            print(log_msg, flush=True)
            sys.stdout.flush()
            
            return response
        except Exception as resp_error:
            logger.error(f"[EMPLOYEE_BP][ERROR] make_response failed: {resp_error}")
            # Strategy 2: Try Response class directly
            try:
                from flask import Response
                resp = Response("", status=200)
                resp.headers["Access-Control-Allow-Origin"] = "*"
                resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
                resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With, Origin, Accept"
                resp.headers["Access-Control-Allow-Credentials"] = "true"
                return resp
            except Exception as resp2_error:
                logger.error(f"[EMPLOYEE_BP][ERROR] Response class failed: {resp2_error}")
                # Strategy 3: Return minimal tuple response
                try:
                    headers = {
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
                        "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Requested-With, Origin, Accept",
                        "Access-Control-Allow-Credentials": "true"
                    }
                    return ("", 200, headers)
                except:
                    # Strategy 4: Absolute last resort - return empty 200
                    from flask import Response
                    return Response("", status=200)


@employee_bp.route("/schedule", methods=["GET", "OPTIONS"], strict_slashes=False)
def my_schedule():
    """Get schedule for current employee from database cache"""
    # CRITICAL: Check OPTIONS FIRST before any other operations
    # This is a safety net in case before_request handler didn't catch it
    try:
        if hasattr(request, 'method') and request.method == "OPTIONS":
            logger.info(f"[TRACE] ✅ OPTIONS handler ready for /employee/schedule (route-level)")
            response = make_response(("", 200))
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With, Origin, Accept"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response
    except:
        # If we can't check method, assume it's not OPTIONS and continue
        pass
    
    logger.info(f"[CACHE] ===== /employee/schedule ENDPOINT CALLED =====")
    logger.info(f"[CACHE] Request method: {request.method}")
    logger.info(f"[CACHE] Request path: {request.path}")
    logger.info(f"[CACHE] Request args: {dict(request.args)}")
    
    # JWT required for actual GET request
    from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
    verify_jwt_in_request()
    
    try:
        current_user_id = get_jwt_identity()
        logger.info(f"[TRACE][SYNC] /employee/schedule called by user {current_user_id}")
        logger.info(f"[CACHE] Current user ID from JWT: {current_user_id}")
        
        user = User.query.get(current_user_id)
        
        if not user:
            logger.error(f"[TRACE][SYNC] User not found for ID: {current_user_id}")
            logger.error(f"[CACHE] User not found for ID: {current_user_id}")
            response = jsonify({'error': 'User not found'})
            response.headers.add("Access-Control-Allow-Origin", "*")
            return response, 404
        
        month = request.args.get('month')
        logger.info(f"[TRACE][SYNC] ===== FETCHING SCHEDULE FOR USER =====")
        logger.info(f"[TRACE][SYNC] User ID: {user.userID}")
        logger.info(f"[TRACE][SYNC] Username: {user.username}")
        logger.info(f"[TRACE][SYNC] Employee ID: {user.employee_id}")
        logger.info(f"[TRACE][SYNC] Role: {user.role}")
        logger.info(f"[TRACE][SYNC] Month: {month}")
        logger.info(f"[CACHE] ===== START CACHE FETCH =====")
        logger.info(f"[CACHE] Fetching schedule from DB for user {user.userID} (username: {user.username}), month: {month}")
        
        # Get active schedule definition for user's tenant
        from app.models import ScheduleDefinition
        schedule_def = ScheduleDefinition.query.filter_by(
            tenantID=user.tenantID,
            is_active=True
        ).first()
        
        # For employees, username IS the employee_id, so use username if employee_id is not set
        employee_id_for_sync = user.employee_id
        if not employee_id_for_sync and user.role and user.role.lower() == 'employee' and user.username:
            employee_id_for_sync = user.username
            logger.info(f"[TRACE][SYNC] Using username as employee_id for sync: {user.username}")
        
        # Ensure data is synced before fetching
        if schedule_def:
            from app.utils.sync_guard import ensure_data_synced
            sync_status = ensure_data_synced(
                user_id=current_user_id,
                schedule_def_id=schedule_def.scheduleDefID,
                employee_id=employee_id_for_sync,
                max_age_minutes=30  # Sync if data is older than 30 minutes
            )
            # Log sync status for debugging
            if sync_status.get('synced'):
                logger.info(f"[TRACE][SYNC] Auto-sync completed: {sync_status.get('reason', 'N/A')}")
            elif sync_status.get('used_cache'):
                logger.debug(f"[TRACE][SYNC] Using cached data: {sync_status.get('reason', 'N/A')}")
        
        if not schedule_def:
            response = jsonify({
                "success": True,
                "user_id": user.userID,
                "month": month,
                "schedule": [],
                "source": "database",
                "message": "No active schedule found"
            })
            response.headers.add("Access-Control-Allow-Origin", "*")
            return response, 200
        
        # Get cached schedule from database
        from app.models import CachedSchedule, SyncLog, EmployeeMapping
        
        logger.info(f"[CACHE] Querying cache for user_id={current_user_id}, schedule_def_id={schedule_def.scheduleDefID}, month={month}")
        
        # Check if sync is needed before fetching cache
        # Trigger sync if: 1) No sync exists, 2) Last sync > 24 hours ago (daily sync), 3) No cache data for this month
        should_sync = SyncLog.should_sync(schedule_def_id=schedule_def.scheduleDefID, min_minutes=1440)  # 24 hours (1 day) threshold for daily sync
        last_sync = SyncLog.get_last_sync(schedule_def_id=schedule_def.scheduleDefID)
        
        # Check if cache is empty for this user/month
        # CRITICAL: Always check cache first, but if empty, MUST sync from Google Sheets
        cache_check = CachedSchedule.query.filter_by(
            user_id=current_user_id,
            schedule_def_id=schedule_def.scheduleDefID
        )
        if month:
            # Parse month (YYYY-MM format)
            try:
                year, month_num = month.split('-')
                from datetime import datetime
                start_date = datetime(int(year), int(month_num), 1).date()
                if int(month_num) == 12:
                    end_date = datetime(int(year) + 1, 1, 1).date()
                else:
                    end_date = datetime(int(year), int(month_num) + 1, 1).date()
                cache_check = cache_check.filter(
                    CachedSchedule.date >= start_date,
                    CachedSchedule.date < end_date
                )
            except:
                pass
        
        cache_count = cache_check.count()
        cache_empty = cache_count == 0
        
        logger.info(f"[CACHE] Cache check: {cache_count} entries found for user {current_user_id}, month {month}")
        logger.info(f"[CACHE] Cache empty: {cache_empty}")
        
        # Initialize schedules_result variable (will be updated after sync if needed)
        schedules_result = None
        
        # Trigger sync if needed (on-demand sync)
        # If cache is empty, do synchronous sync to get data immediately
        if should_sync or cache_empty:
            logger.info(f"[CACHE] Triggering on-demand sync: should_sync={should_sync}, cache_empty={cache_empty}")
            try:
                from app.services.google_sheets_sync_service import GoogleSheetsSyncService
                from flask import current_app
                creds_path = current_app.config.get('GOOGLE_APPLICATION_CREDENTIALS', 'service-account-creds.json')
                sync_service = GoogleSheetsSyncService(creds_path)
                
                # CRITICAL: If cache is empty, ALWAYS sync from Google Sheets synchronously
                # This ensures data is fetched from Google Sheets, not just checked in DB
                if cache_empty:
                    logger.info(f"[CACHE] ⚠️  Cache is EMPTY - performing SYNCHRONOUS sync from Google Sheets")
                    logger.info(f"[CACHE] This will fetch ALL schedule data from Google Sheets and match by employee_id='{user.username}'")
                    try:
                        # Force sync from Google Sheets (not just DB check)
                        sync_result = sync_service.sync_schedule_data(
                            schedule_def_id=schedule_def.scheduleDefID,
                            sync_type='on_demand',
                            triggered_by=current_user_id,
                            force=True  # CRITICAL: Force sync to fetch from Google Sheets
                        )
                        
                        logger.info(f"[CACHE] ✅ Synchronous sync completed: success={sync_result.get('success', False)}")
                        logger.info(f"[CACHE] 📊 Rows synced: {sync_result.get('rows_synced', 0)}, Users synced: {sync_result.get('users_synced', 0)}")
                        
                        if sync_result.get('error'):
                            logger.error(f"[CACHE] ❌ Sync error: {sync_result.get('error')}")
                        
                        # CRITICAL: After sync, immediately refresh cache query to get newly synced data
                        if sync_result.get('success'):
                            # IMPORTANT: Use the same query variable that will be used later
                            # This ensures we get the data that was just synced
                            logger.info(f"[CACHE] ⏳ Waiting briefly for database commit to complete...")
                            import time
                            time.sleep(0.5)  # Brief wait to ensure DB commit is complete
                            
                            # Re-query cache after sync
                            schedules_query_after_sync = CachedSchedule.get_user_schedule(
                                user_id=current_user_id,
                                schedule_def_id=schedule_def.scheduleDefID,
                                month=month,
                                max_age_hours=0
                            )
                            schedules_result_after_sync = schedules_query_after_sync.all()
                            logger.info(f"[CACHE] ✅ After sync, found {len(schedules_result_after_sync)} schedule entries for user {current_user_id} (username: {user.username})")
                            
                            # Update the main query result with synced data
                            schedules_result = schedules_result_after_sync
                            
                            # If still empty after sync, log detailed warning
                            if len(schedules_result_after_sync) == 0:
                                logger.warning(f"[CACHE] ⚠️  Still no schedule entries after sync - user '{user.username}' may not match any row in Google Sheets")
                                logger.warning(f"[CACHE] Check if Google Sheets has row with employee_id matching username '{user.username}'")
                                logger.warning(f"[CACHE] Sync result: rows_synced={sync_result.get('rows_synced', 0)}, users_synced={sync_result.get('users_synced', 0)}")
                        else:
                            logger.warning(f"[CACHE] ⚠️  Sync did not succeed, but will try to fetch from cache anyway")
                            if sync_result.get('error'):
                                logger.error(f"[CACHE] Sync error details: {sync_result.get('error')}")
                    except Exception as sync_error:
                        logger.error(f"[CACHE] ❌ Synchronous sync failed: {sync_error}")
                        import traceback
                        logger.error(traceback.format_exc())
                else:
                    # Cache exists but might be stale - do background sync
                    import threading
                    from flask import current_app
                    app = current_app._get_current_object()
                    def sync_in_background():
                        # Use Flask app context in background thread
                        with app.app_context():
                            try:
                                logger.info(f"[CACHE] Starting background sync for schedule {schedule_def.scheduleDefID}")
                                sync_result = sync_service.sync_schedule_data(
                                    schedule_def_id=schedule_def.scheduleDefID,
                                    sync_type='on_demand',
                                    triggered_by=current_user_id,
                                    force=True
                                )
                                logger.info(f"[CACHE] Background sync completed: {sync_result.get('success', False)}")
                            except Exception as e:
                                logger.error(f"[CACHE] Background sync failed: {e}")
                                import traceback
                                logger.error(traceback.format_exc())
                    
                    # Start sync in background thread
                    sync_thread = threading.Thread(target=sync_in_background, daemon=True)
                    sync_thread.start()
                    logger.info(f"[CACHE] Background sync thread started")
            except Exception as e:
                logger.warning(f"[CACHE] Failed to trigger sync: {e}")
        
        # CRITICAL: Validate user authentication
        if current_user_id != user.userID:
            logger.error(f"[CACHE] SECURITY: JWT user_id ({current_user_id}) does not match user.userID ({user.userID})")
            response = jsonify({'error': 'User authentication mismatch'})
            response.headers.add("Access-Control-Allow-Origin", "*")
            return response, 403
        
        # CRITICAL: Query cache AFTER sync (in case sync just ran)
        # This ensures we get the latest data that was just synced from Google Sheets
        # If sync just ran and updated schedules_result, use that; otherwise query fresh
        if schedules_result is None:
            # CRITICAL DEBUG: Check what user_id we're using
            logger.info(f"[CACHE] ========== USER ID VERIFICATION ==========")
            logger.info(f"[CACHE] JWT current_user_id: {current_user_id}")
            logger.info(f"[CACHE] User.username: {user.username}")
            logger.info(f"[CACHE] User.userID: {user.userID}")
            logger.info(f"[CACHE] User.employee_id: {user.employee_id}")
            logger.info(f"[CACHE] Do they match? current_user_id == user.userID: {current_user_id == user.userID}")
            
            # Check if there's data for this specific user_id
            direct_check = CachedSchedule.query.filter_by(
                user_id=current_user_id,
                schedule_def_id=schedule_def.scheduleDefID
            ).first()
            logger.info(f"[CACHE] Direct query check (any month): {direct_check is not None}")
            if direct_check:
                logger.info(f"[CACHE] Sample entry found: date={direct_check.date}, shift_type={direct_check.shift_type}")
            
            # Also check by username/employee_id in case user_id doesn't match
            if user.employee_id:
                mapping_check = EmployeeMapping.find_by_sheets_identifier(user.employee_id, schedule_def.scheduleDefID)
                if mapping_check and mapping_check.userID:
                    logger.info(f"[CACHE] EmployeeMapping.userID: {mapping_check.userID}")
                    logger.info(f"[CACHE] Does mapping.userID match current_user_id? {mapping_check.userID == current_user_id}")
                    
                    # Check if data exists for the mapping's userID
                    mapping_data_check = CachedSchedule.query.filter_by(
                        user_id=mapping_check.userID,
                        schedule_def_id=schedule_def.scheduleDefID
                    ).count()
                    logger.info(f"[CACHE] Schedule entries for mapping.userID ({mapping_check.userID}): {mapping_data_check}")
            
            logger.info(f"[CACHE] =========================================")
            
            # Initialize query with current_user_id (will be updated if needed)
            schedules_query = CachedSchedule.get_user_schedule(
                user_id=current_user_id,
                schedule_def_id=schedule_def.scheduleDefID,
                month=month,
                max_age_hours=0  # Disable TTL - use all cached data
            )
            
            # Debug: Check raw query
            logger.info(f"[CACHE] 🔍 Querying CachedSchedule for user_id={current_user_id} (username: {user.username}), schedule_def_id={schedule_def.scheduleDefID}, month={month}")
            
            # Check if any data exists for this user at all (regardless of month)
            all_user_schedules = CachedSchedule.query.filter_by(
                user_id=current_user_id,
                schedule_def_id=schedule_def.scheduleDefID
            ).count()
            logger.info(f"[CACHE] 📊 Total schedule entries for user {current_user_id} (all months): {all_user_schedules}")
            
            # CRITICAL SECURITY FIX: Only use schedules for the logged-in user's userID
            # DO NOT use fallback strategies that might return schedules for other users
            # If no data found, it means schedules haven't been synced yet - don't return wrong data
            if all_user_schedules == 0:
                logger.warning(f"[CACHE] ⚠️  No schedule data found for user_id={current_user_id} (username: {user.username}, employee_id: {user.employee_id})")
                logger.info(f"[CACHE] This is expected if schedules haven't been synced yet. Will return empty schedule.")
                logger.info(f"[CACHE] Schedules will be synced automatically on next sync cycle.")
                
                # Verify EmployeeMapping exists and is correct
                if user.employee_id:
                    mapping = EmployeeMapping.find_by_sheets_identifier(user.employee_id, schedule_def.scheduleDefID)
                    if mapping:
                        if mapping.userID == current_user_id:
                            logger.info(f"[CACHE] ✅ EmployeeMapping is correctly linked to current user")
                        else:
                            logger.error(f"[CACHE] ❌ EmployeeMapping.userID ({mapping.userID}) != current_user_id ({current_user_id})")
                            logger.error(f"[CACHE] This is a data integrity issue - EmployeeMapping needs to be fixed")
                    else:
                        logger.warning(f"[CACHE] ⚠️  No EmployeeMapping found for employee_id={user.employee_id}")
                
                # DO NOT try alternative user_ids - this could return wrong schedules
                # Instead, return empty schedule and let sync handle it
            
            schedules_result = schedules_query.all()
            logger.info(f"[CACHE] ✅ Query returned {len(schedules_result)} schedule entries for month {month}")
        else:
            # schedules_result was already updated by sync above
            logger.info(f"[CACHE] ✅ Using schedule data from sync: {len(schedules_result)} entries")
        
        # Debug: Log first few entries if any
        if schedules_result:
            logger.info(f"[CACHE] 📅 First entry: date={schedules_result[0].date}, shift_type={schedules_result[0].shift_type}")
            logger.info(f"[CACHE] 📅 Last entry: date={schedules_result[-1].date}, shift_type={schedules_result[-1].shift_type}")
        else:
            logger.warning(f"[CACHE] ⚠️  No schedule entries found for user {current_user_id} (username: {user.username}) in month {month}")
            logger.warning(f"[CACHE] ⚠️  This may mean:")
            logger.warning(f"[CACHE]     1. Google Sheets doesn't have data for employee_id '{user.username}'")
            logger.warning(f"[CACHE]     2. Sync failed to match '{user.username}' with Google Sheets row")
            logger.warning(f"[CACHE]     3. Sync hasn't run yet (check sync logs)")
        
        schedules = []
        for schedule_entry in schedules_result:
            # CRITICAL SECURITY CHECK: Verify each entry belongs to the logged-in user
            if schedule_entry.user_id != current_user_id:
                logger.error(f"[CACHE] SECURITY ISSUE: Schedule entry {schedule_entry.id} has user_id={schedule_entry.user_id} but expected {current_user_id}")
                logger.error(f"[CACHE] Skipping this entry to prevent data leakage")
                continue  # Skip entries that don't belong to this user
            
            # CRITICAL: Use raw shift_value from sheet (e.g., "C 櫃台人力", "A 藥局人力")
            # Fallback to shift_type if shift_value is not available (for backward compatibility)
            shift_value = schedule_entry.shift_value or schedule_entry.shift_type or ""
            
            schedules.append({
                "date": schedule_entry.date.isoformat() if schedule_entry.date else None,
                "shift": shift_value,  # CRITICAL: Return EXACT value from sheet
                "shift_type": schedule_entry.shift_type,  # Keep normalized for backward compatibility
                "shiftType": schedule_entry.shift_type,  # Frontend expects camelCase
                "time_range": schedule_entry.time_range,
                "timeRange": schedule_entry.time_range  # Frontend expects camelCase
            })
        
        # Refresh last sync time
        last_sync = SyncLog.get_last_sync(schedule_def_id=schedule_def.scheduleDefID)
        last_synced_at = last_sync.completed_at.isoformat() if last_sync and last_sync.completed_at else None
        
        # Log sync status for debugging
        if last_sync and last_sync.completed_at:
            from datetime import datetime
            time_since_sync = (datetime.utcnow() - last_sync.completed_at).total_seconds() / 3600  # hours
            logger.info(f"[CACHE] Last sync: {last_sync.completed_at.isoformat()}, {time_since_sync:.1f} hours ago")
        else:
            logger.warning(f"[CACHE] No sync found for schedule {schedule_def.scheduleDefID}")
        
        logger.info(f"[TRACE][SYNC] Served {len(schedules)} schedule entries from DB for user {user.userID} (username='{user.username}', employee_id='{user.employee_id}'), month: {month}")
        logger.info(f"[CACHE] Served {len(schedules)} schedule entries from DB for user {user.userID} (month: {month})")
        
        # If no schedules found after sync, try direct Google Sheets fetch as fallback
        if len(schedules) == 0:
            logger.warning(f"[TRACE][SYNC] No cached schedules found for user {user.userID} (username='{user.username}', employee_id='{user.employee_id}'), schedule_def {schedule_def.scheduleDefID}, month {month}")
            logger.warning(f"[CACHE] WARNING: No cached schedules found for user {user.userID}, schedule_def {schedule_def.scheduleDefID}, month {month}")
            
            # Check if there's any data for this user at all
            all_count = CachedSchedule.query.filter_by(
                user_id=current_user_id,
                schedule_def_id=schedule_def.scheduleDefID
            ).count()
            logger.info(f"[CACHE] Total cached entries for this user/schedule: {all_count}")
            
            # Try direct Google Sheets fetch as fallback
            logger.info(f"[CACHE] Attempting direct Google Sheets fetch as fallback for username='{user.username}'")
            try:
                from app.services.dashboard_data_service import DashboardDataService
                from flask import current_app
                creds_path = current_app.config.get('GOOGLE_APPLICATION_CREDENTIALS', 'service-account-creds.json')
                dashboard_service = DashboardDataService(creds_path)
                
                dashboard_data = dashboard_service.get_employee_dashboard_data(
                    user_id=current_user_id,
                    schedule_def_id=schedule_def.scheduleDefID
                )
                
                if dashboard_data.get("success") and dashboard_data.get("data", {}).get("my_schedule"):
                    logger.info(f"[CACHE] Successfully fetched from Google Sheets, parsing schedule data")
                    # Parse the schedule data from dashboard service response
                    my_schedule = dashboard_data["data"]["my_schedule"]
                    # The frontend will parse this, but we can also try to extract dates here
                    # For now, return the raw data and let frontend handle it
                    response_data = {
                        "success": True,
                        "user_id": user.userID,
                        "month": month,
                        "schedule": [],  # Empty for now, frontend will parse from my_schedule
                        "source": "google_sheets",
                        "last_synced_at": last_synced_at,
                        "cache_count": 0,
                        "raw_data": my_schedule  # Include raw data for frontend parsing
                    }
                    response = jsonify(response_data)
                    response.headers.add("Access-Control-Allow-Origin", "*")
                    return response, 200
                else:
                    logger.warning(f"[CACHE] Google Sheets fetch failed or returned no data: {dashboard_data.get('error', 'Unknown error')}")
            except Exception as fallback_error:
                logger.error(f"[CACHE] Fallback Google Sheets fetch failed: {fallback_error}")
                import traceback
                logger.error(traceback.format_exc())
        
        # CRITICAL DEBUG: Log response before sending
        logger.info(f"[CACHE] ========== FINAL API RESPONSE ==========")
        logger.info(f"[CACHE] user_id: {user.userID}")
        logger.info(f"[CACHE] username: {user.username}")
        logger.info(f"[CACHE] employee_id: {user.employee_id}")
        logger.info(f"[CACHE] month: {month}")
        logger.info(f"[CACHE] schedules array length: {len(schedules)}")
        logger.info(f"[CACHE] source: database")
        logger.info(f"[CACHE] cache_count: {len(schedules)}")
        if schedules:
            logger.info(f"[CACHE] First schedule entry: {schedules[0]}")
            logger.info(f"[CACHE] Last schedule entry: {schedules[-1]}")
        else:
            logger.warning(f"[CACHE] ⚠️  WARNING: schedules array is EMPTY!")
            logger.warning(f"[CACHE] This should not happen if data exists in database")
        logger.info(f"[CACHE] =========================================")
        
        response_data = {
            "success": True,
            "user_id": user.userID,
            "month": month,
            "schedule": schedules,
            "source": "database",
            "last_synced_at": last_synced_at,
            "cache_count": len(schedules)
        }
        
        response = jsonify(response_data)
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response, 200
        
    except Exception as e:
        logger.error(f"Error fetching employee schedule: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        response = jsonify({
            'success': False,
            'error': 'Failed to fetch schedule',
            'details': str(e),
            'schedule': []
        })
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response, 500


@employee_bp.route("/schedule-data", methods=["GET", "OPTIONS"])
def schedule_data():
    """E1 My Dashboard - Employee schedule data: Try cache first, fallback to Google Sheets"""
    # CRITICAL: Handle CORS preflight BEFORE JWT check - use safe method check
    try:
        if hasattr(request, 'method') and request.method == "OPTIONS":
            logger.info(f"[TRACE] ✅ OPTIONS handler ready for /employee/schedule-data (route-level)")
            response = make_response(("", 200))
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With, Origin, Accept"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Max-Age"] = "3600"
            return response
    except:
        # If we can't check method, assume it's not OPTIONS and continue
        pass
    
    # JWT required for actual GET request
    from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
    from flask import current_app
    from app.models import ScheduleDefinition, CachedSchedule, SyncLog, EmployeeMapping
    
    verify_jwt_in_request()
    
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if not user:
            response = jsonify({'error': 'User not found'})
            response.headers.add("Access-Control-Allow-Origin", "*")
            return response, 404
        
        logger.info(f"[CACHE] /schedule-data endpoint: Checking cache first for user {user.userID}")
        
        # Get active schedule definition
        schedule_def_id = request.args.get('schedule_def_id')
        schedule_def = None
        if not schedule_def_id:
            schedule_def = ScheduleDefinition.query.filter_by(
                tenantID=user.tenantID,
                is_active=True
            ).first()
            if schedule_def:
                schedule_def_id = schedule_def.scheduleDefID
        else:
            schedule_def = ScheduleDefinition.query.get(schedule_def_id)
        
        # Ensure data is synced before fetching
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
        
        # Try to get cached data first
        if schedule_def_id:
            try:
                # Get month from request if available
                month = request.args.get('month')
                
                # Get cached schedules
                schedules_query = CachedSchedule.query.filter_by(
                    user_id=current_user_id,
                    schedule_def_id=schedule_def_id
                )
                
                if month:
                    # Parse month format (e.g., "2025-10" or "2025/10")
                    from datetime import datetime
                    try:
                        if '-' in month:
                            year, month_num = map(int, month.split('-'))
                        elif '/' in month:
                            year, month_num = map(int, month.split('/'))
                        else:
                            year, month_num = int(month[:4]), int(month[4:6])
                        
                        # Filter by month using date range
                        from calendar import monthrange
                        from datetime import date
                        _, last_day = monthrange(year, month_num)
                        start_date = date(year, month_num, 1)
                        end_date = date(year, month_num, last_day)
                        
                        schedules_query = schedules_query.filter(
                            CachedSchedule.date >= start_date,
                            CachedSchedule.date <= end_date
                        )
                    except:
                        pass  # If month parsing fails, return all
                
                cached_schedules = schedules_query.all()
                
                if cached_schedules:
                    logger.info(f"[CACHE] Found {len(cached_schedules)} cached entries, returning from DB")
                    
                    # Transform to DashboardDataService format
                    rows = []
                    columns = ['日期', '星期', '班別', '時段']
                    
                    for schedule in cached_schedules:
                        if schedule.date:
                            from datetime import datetime, date as date_type
                            if isinstance(schedule.date, date_type):
                                date_obj = schedule.date
                            elif isinstance(schedule.date, datetime):
                                date_obj = schedule.date.date()
                            else:
                                date_obj = datetime.strptime(str(schedule.date), '%Y-%m-%d').date()
                            
                            # Get day of week
                            weekdays = ['週一', '週二', '週三', '週四', '週五', '週六', '週日']
                            weekday = weekdays[date_obj.weekday()]
                            
                            rows.append({
                                '日期': date_obj.strftime('%Y-%m-%d'),
                                '星期': weekday,
                                '班別': schedule.shift_type or 'D',
                                '時段': schedule.time_range or '--'
                            })
                    
                    # Return cached data
                    dashboard_data = {
                        'success': True,
                        'source': 'database_cache',
                        'data': {
                            'my_schedule': {
                                'rows': rows,
                                'columns': columns
                            }
                        }
                    }
                    
                    # Get last sync time
                    last_sync = SyncLog.get_last_sync(schedule_def_id=schedule_def_id)
                    if last_sync and last_sync.completed_at:
                        dashboard_data['last_synced_at'] = last_sync.completed_at.isoformat()
                    
                    response = jsonify(dashboard_data)
                    response.headers.add("Access-Control-Allow-Origin", "*")
                    return response, 200
                    
            except Exception as cache_err:
                logger.warning(f"[CACHE] Error reading from cache: {cache_err}, falling back to Google Sheets")
        
        # Cache miss or error - try Google Sheets (only if quota allows)
        logger.info(f"[CACHE] Cache miss or empty, attempting Google Sheets fetch")
        
        # Check Google Sheets service availability
        from app.services.google_sheets_import import _try_import_google_sheets
        import app.services.google_sheets_import as sheets_import_module
        
        if not sheets_import_module.SHEETS_AVAILABLE:
            logger.warning("[TRACE] SHEETS_AVAILABLE is False, attempting force retry...")
            success, path = _try_import_google_sheets(force_retry=True)
            import importlib
            importlib.reload(sheets_import_module)
            if not sheets_import_module.SHEETS_AVAILABLE:
                # Return empty data if Sheets unavailable and no cache
                logger.error(f"[CACHE] Google Sheets unavailable and no cache found")
                error_response = {
                    'success': False,
                    'error': 'Google Sheets service not available and no cached data found.',
                    'source': 'none',
                    'data': {
                        'my_schedule': {'rows': [], 'columns': []}
                    }
                }
                response = jsonify(error_response)
                response.headers.add("Access-Control-Allow-Origin", "*")
                return response, 503
        
        # Get credentials path
        creds_path = current_app.config.get('GOOGLE_APPLICATION_CREDENTIALS', 'service-account-creds.json')
        if not os.path.isabs(creds_path) and not os.path.exists(creds_path):
            backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            project_root = os.path.dirname(backend_dir)
            project_creds = os.path.join(project_root, 'service-account-creds.json')
            if os.path.exists(project_creds):
                creds_path = project_creds
        
        # Try to fetch from Google Sheets
        try:
            from app.services.dashboard_data_service import DashboardDataService
            service = DashboardDataService(creds_path)
            dashboard_data = service.get_employee_dashboard_data(current_user_id, schedule_def_id)
            
            # If successful, update cache in background
            if dashboard_data.get("success"):
                try:
                    # Trigger background cache update
                    import threading
                    def update_cache():
                        try:
                            from app.services.google_sheets_sync_service import GoogleSheetsSyncService
                            sync_service = GoogleSheetsSyncService(creds_path)
                            if schedule_def_id:
                                sync_service.sync_schedule_data(
                                    schedule_def_id=schedule_def_id,
                                    sync_type='auto',
                                    triggered_by=None,
                                    force=False
                                )
                        except Exception as e:
                            logger.warning(f"[CACHE] Background cache update failed: {e}")
                    threading.Thread(target=update_cache, daemon=True).start()
                except:
                    pass
            
            # Return Google Sheets data
            if dashboard_data.get("success"):
                dashboard_data['source'] = 'google_sheets'
                response = jsonify(dashboard_data)
                response.headers.add("Access-Control-Allow-Origin", "*")
                return response, 200
            else:
                # Google Sheets failed - try to return cache anyway (even if empty)
                logger.warning(f"[CACHE] Google Sheets fetch failed, returning empty result")
                error_response = {
                    'success': False,
                    'error': dashboard_data.get('error', 'Failed to fetch from Google Sheets'),
                    'source': 'google_sheets_failed',
                    'data': {
                        'my_schedule': {'rows': [], 'columns': []}
                    }
                }
                response = jsonify(error_response)
                response.headers.add("Access-Control-Allow-Origin", "*")
                return response, 400
                
        except Exception as sheets_err:
            logger.error(f"[CACHE] Google Sheets error (likely rate limit): {sheets_err}")
            # Return empty result - frontend should handle gracefully
            error_response = {
                'success': False,
                'error': f'Google Sheets API error: {str(sheets_err)}',
                'source': 'google_sheets_error',
                'data': {
                    'my_schedule': {'rows': [], 'columns': []}
                }
            }
            response = jsonify(error_response)
            response.headers.add("Access-Control-Allow-Origin", "*")
            return response, 429 if '429' in str(sheets_err) or 'quota' in str(sheets_err).lower() else 500
            
    except Exception as e:
        logger.error(f"Error in schedule-data endpoint: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        response = jsonify({'error': 'Failed to fetch schedule data', 'details': str(e)})
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response, 500


@employee_bp.route("/available-ids", methods=["GET", "OPTIONS"])
def get_available_employee_ids():
    """
    Get list of ALL active Employee IDs from EmployeeMapping table (DATABASE ONLY)
    
    This endpoint reads directly from the database - it does NOT access Google Sheets.
    The database is automatically synced from Google Sheets by Celery every 5 minutes.
    
    Flow:
    1. Celery task (auto_sync_employee_data) runs every 5 minutes
    2. Celery syncs Google Sheets → EmployeeMapping table in database
    3. This endpoint reads from EmployeeMapping table only
    
    Returns all active employees (E01-E04, N01-N05) regardless of link status.
    Public endpoint - no JWT required for registration flow.
    """

    from flask import jsonify, request, current_app

    # ✅ Step 1: Handle CORS preflight safely (fixes 500 issue)
    try:
        if hasattr(request, 'method') and request.method == "OPTIONS":
            logger.info(f"[TRACE] ✅ OPTIONS handler ready for /employee/available-ids (route-level)")
            response = make_response(("", 200))
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With, Origin, Accept"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Max-Age"] = "3600"
            return response
    except:
        # If we can't check method, assume it's not OPTIONS and continue
        pass

    try:
        logger.info(f"[TRACE][EMPLOYEE] GET request received - Fetching Employee IDs from DATABASE ONLY...")

        from app.models import EmployeeMapping, SyncLog
        # CRITICAL: Use relative import to ensure same db instance
        from ..extensions import db

        # ✅ Step 2: Verify DB connection
        try:
            db.session.execute(db.text('SELECT 1'))
            logger.info(f"[TRACE][EMPLOYEE] Database connection verified")
        except Exception as db_check_err:
            logger.error(f"[TRACE][EMPLOYEE][ERROR] Database session check failed: {db_check_err}")
            current_app.logger.exception("Database session check failed")
            raise

        # ✅ Step 3: Query all active EmployeeMappings that are NOT linked to users
        # Only return employee IDs available for registration (not already linked)
        employees = (
            db.session.query(EmployeeMapping)
            .filter_by(is_active=True)
            .filter(
                (EmployeeMapping.userID.is_(None)) | (EmployeeMapping.userID == '')
            )
            .order_by(EmployeeMapping.sheets_identifier.asc())
            .all()
        )
        logger.info(f"[TRACE][EMPLOYEE] Found {len(employees)} available (unlinked) EmployeeMappings in database")

        # Debug info
        total_count = db.session.query(EmployeeMapping).count()
        active_count = db.session.query(EmployeeMapping).filter_by(is_active=True).count()
        linked_count = db.session.query(EmployeeMapping).filter(
            EmployeeMapping.is_active == True,
            EmployeeMapping.userID.isnot(None),
            EmployeeMapping.userID != ''
        ).count()
        inactive_count = db.session.query(EmployeeMapping).filter_by(is_active=False).count()
        logger.info(f"[TRACE][EMPLOYEE] Total: {total_count}, Active: {active_count}, Available (unlinked): {len(employees)}, Linked: {linked_count}, Inactive: {inactive_count}")

        # Optional last sync log
        try:
            last_sync = SyncLog.query.filter_by(status='success').order_by(SyncLog.completed_at.desc()).first()
            if last_sync and last_sync.completed_at:
                logger.info(f"[TRACE][EMPLOYEE] Last successful sync: {last_sync.completed_at.isoformat()}")
        except Exception:
            pass

        # ✅ Step 4: Build available employee data
        available_ids = []
        for emp in employees:
            try:
                identifier = getattr(emp, 'sheets_identifier', None) or ''
                if not identifier:
                    continue

                employee_name = (
                    getattr(emp, 'employee_sheet_name', None)
                    or getattr(emp, 'sheets_name_id', None)
                    or identifier
                )

                available_ids.append({
                    'employee_id': identifier,
                    'employee_name': employee_name or identifier
                })
            except Exception as row_err:
                current_app.logger.exception("Error processing employee row")
                logger.warning(f"[TRACE][EMPLOYEE] ⚠️ Error processing row: {row_err}")
                continue

        # ✅ Step 5: Return response
        if len(available_ids) == 0:
            response_data = {
                'success': False,
                'message': 'No available employee IDs found',
                'available_ids': [],
                'count': 0
            }
            logger.warning(f"[TRACE][EMPLOYEE] ⚠️ No employees found in database")
        else:
            response_data = {
                'success': True,
                'available_ids': available_ids,
                'count': len(available_ids)
            }
            logger.info(f"[TRACE][EMPLOYEE] ✅ Endpoint verification passed - {len(available_ids)} employees")

        response = jsonify(response_data)
        logger.info(f"[TRACE][EMPLOYEE] ✅ Endpoint verified successfully ({len(available_ids)} employees)")
        print(f"[TRACE][EMPLOYEE] ✅ Endpoint verified successfully ({len(available_ids)} employees)")
        return response, 200

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()

        try:
            if current_app:
                current_app.logger.exception("[TRACE][EMPLOYEE][ERROR] Failed to fetch Employee IDs")
            logger.error(f"[TRACE][EMPLOYEE][ERROR] Error fetching Employee IDs: {str(e)}")
            logger.error(f"[TRACE][EMPLOYEE][ERROR] Traceback: {error_trace}")
            print(f"[TRACE][EMPLOYEE][ERROR] Error: {str(e)}")
            print(f"[TRACE][EMPLOYEE][ERROR] Full traceback:\n{error_trace}")
        except Exception as log_err:
            import sys
            print(f"[CRITICAL][EMPLOYEE] Error logging failed: {log_err}", file=sys.stderr)
            print(f"[CRITICAL][EMPLOYEE] Original error: {str(e)}", file=sys.stderr)

        # Always return JSON error with valid CORS headers
        try:
            response = jsonify({
                'success': False,
                'error': 'An internal error occurred',
                'error_type': type(e).__name__,
                'error_message': str(e),
                'available_ids': [],
                'count': 0
            })
            response.status_code = 500
            return response
        except Exception as resp_err:
            from flask import Response
            import json
            error_data = json.dumps({
                'success': False,
                'error': 'An internal error occurred',
                'error_type': type(e).__name__,
                'available_ids': [],
                'count': 0
            })
            resp = Response(error_data, status=500, mimetype='application/json')
            resp.headers["Access-Control-Allow-Origin"] = "http://localhost:5173"
            resp.headers["Access-Control-Allow-Credentials"] = "true"
            return resp
