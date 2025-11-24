from flask import Blueprint, jsonify, current_app, redirect, request
from flask_jwt_extended import jwt_required
import logging

logger = logging.getLogger(__name__)

common_bp = Blueprint("common", __name__)


# Note: Auth routes are now handled by auth_bp in routes/auth.py
# These routes are kept for backwards compatibility only
# They use a simplified login without database validation


@common_bp.route("/health", methods=["GET"])
def health():
    components = {"flask": True, "database": False}
    
    # CRITICAL: Test database connection - this is what login endpoint needs
    try:
        # CRITICAL: Use relative import to ensure same db instance
        from ..extensions import db
        from sqlalchemy import text
        db.session.execute(text('SELECT 1'))
        db.session.commit()
        components["database"] = True
    except Exception as db_error:
        logger.error(f"[HEALTH] Database connection failed: {db_error}")
        components["database"] = False
        # Include database diagnostics in response
        db_uri = current_app.config.get('SQLALCHEMY_DATABASE_URI', 'NOT SET')
        db_path = current_app.config.get('DATABASE_ABSOLUTE_PATH', 'NOT SET')
        import os
        response_data = {
            "status": "degraded",
            "components": components,
            "database_error": str(db_error),
            "database_uri": db_uri,
            "database_path": db_path,
            "database_path_exists": os.path.exists(db_path) if db_path != 'NOT SET' else False,
            "database_dir_writable": os.access(os.path.dirname(db_path), os.W_OK) if db_path != 'NOT SET' and os.path.exists(os.path.dirname(db_path)) else False
        }
        response = jsonify(response_data)
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Methods", "GET, OPTIONS, POST, PUT, DELETE")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type, Authorization")
        return response, 503  # Service Unavailable if database is down
    
    # Redis/Celery checks are best-effort to avoid blocking startup
    try:
        import redis  # type: ignore
        url = current_app.config.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
        r = redis.Redis.from_url(url)
        r.ping()
        components["redis"] = True
    except Exception:
        components["redis"] = False
    try:
        from celery import current_app as celery_app  # type: ignore
        # Not a full ping, just ensure app is configured
        components["celery"] = bool(getattr(celery_app, "conf", None))
    except Exception:
        components["celery"] = False
    
    response = jsonify({"status": "ok" if all(components.values()) else "degraded", "components": components})
    # Add CORS headers explicitly
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add("Access-Control-Allow-Methods", "GET, OPTIONS, POST, PUT, DELETE")
    response.headers.add("Access-Control-Allow-Headers", "Content-Type, Authorization")
    return response


@common_bp.route("/routes", methods=["GET"])
def list_routes():
    """List all registered routes (useful for debugging 404s)."""
    try:
        rules = []
        for rule in current_app.url_map.iter_rules():
            methods = ",".join(sorted(m for m in rule.methods if m not in {"HEAD", "OPTIONS"}))
            rules.append({
                "endpoint": rule.endpoint,
                "rule": str(rule),
                "methods": methods
            })
        # Sort for stable output
        rules.sort(key=lambda r: (r["rule"], r["methods"]))
        return jsonify({
            "count": len(rules),
            "routes": rules
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@common_bp.route("/dashboard", methods=["GET"])
@jwt_required()
def unified_dashboard():
    """Unified dashboard endpoint that routes to role-specific dashboard"""
    from flask_jwt_extended import get_jwt_identity, get_jwt
    from app.models import User
    from flask import redirect
    
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        # Get role from JWT claims or user object
        claims = get_jwt() or {}
        role = claims.get('role') or user.role
        
        # Map ERD roles to dashboard endpoints
        role_map = {
            'Client_Admin': '/api/v1/clientadmin/dashboard',
            'ClientAdmin': '/api/v1/clientadmin/dashboard',
            'Schedule_Manager': '/api/v1/schedulemanager/dashboard',
            'ScheduleManager': '/api/v1/schedulemanager/dashboard',
            'Department_Employee': '/api/v1/employee/schedule',
            'employee': '/api/v1/employee/schedule'
        }
        
        dashboard_url = role_map.get(role)
        if dashboard_url:
            return redirect(dashboard_url, code=302)
        
        # Default: return user info
        return jsonify({
            "message": "No specific dashboard for role",
            "user": user.to_dict(),
            "role": role
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@common_bp.route("/dashboard/stats", methods=["GET"])
@jwt_required()
def dashboard_stats():
    """Dashboard statistics for current user"""
    from flask_jwt_extended import get_jwt_identity
    from app.models import User, ScheduleJobLog, ScheduleDefinition
    
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        stats = {
            "total_jobs": ScheduleJobLog.query.filter_by(tenantID=user.tenantID).count(),
            "active_schedules": ScheduleDefinition.query.filter_by(tenantID=user.tenantID, is_active=True).count(),
            "recent_activity": ScheduleJobLog.query.filter_by(tenantID=user.tenantID).order_by(ScheduleJobLog.startTime.desc()).limit(5).count()
        }
        
        return jsonify({"success": True, "data": stats}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@common_bp.route("/dashboard/activities", methods=["GET"])
@jwt_required()
def dashboard_activities():
    """Recent activities for dashboard"""
    from flask_jwt_extended import get_jwt_identity
    from app.models import User, ScheduleJobLog
    from datetime import datetime, timedelta
    
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        recent_jobs = ScheduleJobLog.query.filter_by(tenantID=user.tenantID).order_by(ScheduleJobLog.startTime.desc()).limit(10).all()
        
        activities = [{
            "id": job.logID,
            "type": "schedule_run",
            "description": f"Schedule job {job.status}",
            "timestamp": job.startTime.isoformat() if job.startTime else None
        } for job in recent_jobs]
        
        return jsonify({"success": True, "data": activities}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@common_bp.route("/dashboard/notifications", methods=["GET"])
@jwt_required()
def dashboard_notifications():
    """Dashboard notifications"""
    from flask_jwt_extended import get_jwt_identity
    from app.models import User
    
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        # Return empty notifications for now
        return jsonify({"success": True, "data": []}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@common_bp.route("/analytics/schedule-performance", methods=["GET"])
@jwt_required()
def analytics_schedule_performance():
    """Schedule performance analytics"""
    from flask_jwt_extended import get_jwt_identity
    from app.models import User, ScheduleJobLog
    
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        jobs = ScheduleJobLog.query.filter_by(tenantID=user.tenantID).all()
        
        return jsonify({
            "success": True,
            "data": {
                "total_jobs": len(jobs),
                "success_rate": len([j for j in jobs if j.status == "success"]) / max(len(jobs), 1),
                "performance_metrics": []
            }
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@common_bp.route("/analytics/task-trends", methods=["GET"])
@jwt_required()
def analytics_task_trends():
    """Task trends analytics"""
    from flask_jwt_extended import get_jwt_identity
    from app.models import User, ScheduleJobLog
    from datetime import datetime, timedelta
    
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        days = int(request.args.get('days', 7))
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        jobs = ScheduleJobLog.query.filter(
            ScheduleJobLog.tenantID == user.tenantID,
            ScheduleJobLog.startTime >= cutoff
        ).all()
        
        return jsonify({
            "success": True,
            "data": {
                "period_days": days,
                "total_tasks": len(jobs),
                "trends": []
            }
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@common_bp.route("/analytics/department-analytics", methods=["GET"])
@jwt_required()
def analytics_department_analytics():
    """Department analytics (ClientAdmin only)"""
    from flask_jwt_extended import get_jwt_identity
    from app.models import User, Department
    
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        departments = Department.query.filter_by(tenantID=user.tenantID).all()
        
        return jsonify({
            "success": True,
            "data": {
                "departments": len(departments),
                "analytics": []
            }
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@common_bp.route("/analytics/user-activity", methods=["GET"])
@jwt_required()
def analytics_user_activity():
    """User activity analytics (ClientAdmin only)"""
    from flask_jwt_extended import get_jwt_identity
    from app.models import User
    
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        return jsonify({
            "success": True,
            "data": {
                "total_users": User.query.filter_by(tenantID=user.tenantID).count(),
                "activity": []
            }
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@common_bp.route("/analytics/system-metrics", methods=["GET"])
@jwt_required()
def analytics_system_metrics():
    """System metrics (ClientAdmin only)"""
    from flask_jwt_extended import get_jwt_identity
    from app.models import User, Tenant, ScheduleDefinition
    
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        return jsonify({
            "success": True,
            "data": {
                "total_tenants": Tenant.query.count(),
                "total_schedules": ScheduleDefinition.query.count(),
                "metrics": []
            }
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@common_bp.route("/data/validate-source", methods=["POST"])
@jwt_required()
def data_validate_source():
    """Validate data source (Excel or Google Sheets)"""
    from flask_jwt_extended import get_jwt_identity
    from app.models import User
    
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        data = request.get_json()
        source_type = data.get("source_type", "")
        
        # Basic validation
        valid = source_type in ["excel", "google_sheets"]
        
        return jsonify({
            "success": True,
            "valid": valid,
            "source_type": source_type
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@common_bp.route("/dashboard/chart-data", methods=["GET"])
@jwt_required()
def dashboard_chart_data():
    """Chart data for dashboard"""
    chart_type = request.args.get("type", "performance")
    
    return jsonify({
        "success": True,
        "type": chart_type,
        "data": []
    }), 200


@common_bp.route("/dashboard/system-health", methods=["GET"])
@jwt_required()
def dashboard_system_health():
    """System health check endpoint"""
    from flask import current_app
    import redis
    
    components = {
        "flask": True,
        "database": True,
        "redis": False,
        "celery": False
    }
    
    # Check Redis
    try:
        broker_url = current_app.config.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
        r = redis.Redis.from_url(broker_url)
        r.ping()
        components["redis"] = True
    except Exception:
        pass
    
    # Check Celery
    try:
        from celery import current_app as celery_app
        components["celery"] = bool(getattr(celery_app, "conf", None))
    except Exception:
        pass
    
    status = "ok" if all(components.values()) else "degraded"
    
    return jsonify({
        "status": status,
        "components": components
    }), 200


@common_bp.route("/system/health", methods=["GET"])
def system_health():
    """System health check endpoint (no auth required for monitoring)"""
    from flask import current_app
    import redis
    # CRITICAL: Use relative import to ensure same db instance
    from ..extensions import db
    from sqlalchemy import text
    import os
    
    components = {
        "flask": True,
        "database": True,
        "mysql": False,
        "redis": False,
        "celery": False
    }
    
    # Check Redis
    try:
        broker_url = current_app.config.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
        r = redis.Redis.from_url(broker_url)
        r.ping()
        components["redis"] = True
    except Exception:
        pass
    
    # Check Celery
    try:
        from celery import current_app as celery_app
        components["celery"] = bool(getattr(celery_app, "conf", None))
    except Exception:
        pass

    # Check DB connectivity and mark mysql if applicable
    db_ok = False
    db_error = None
    db_uri = current_app.config.get("SQLALCHEMY_DATABASE_URI", "")
    try:
        db.session.execute(text("SELECT 1"))
        db_ok = True
    except Exception as e:
        db_error = str(e)
        db_ok = False
    
    components["database"] = db_ok
    try:
        components["mysql"] = db_ok and ("mysql" in db_uri.lower())
    except Exception:
        components["mysql"] = False
    
    # Extract database path for diagnostics
    db_path = None
    db_path_exists = False
    if db_uri.startswith("sqlite:///"):
        db_path = db_uri.replace("sqlite:///", "").replace("/", os.sep)
        db_path = os.path.abspath(db_path)
        db_path_exists = os.path.exists(db_path)
    
    status = "ok" if all(components.values()) else "degraded"
    
    response_data = {
        "status": status,
        "components": components
    }
    
    # Add diagnostic info if database is failing
    if not db_ok:
        response_data["database_diagnostics"] = {
            "uri": db_uri,
            "path": db_path,
            "path_exists": db_path_exists,
            "error": db_error[:200] if db_error else None
        }
    
    return jsonify(response_data), 200


@common_bp.route("/dashboard/schedule-data", methods=["GET"])
@jwt_required()
def dashboard_schedule_data():
    """Dashboard schedule data endpoint (for employees) - redirects to employee schedule-data"""
    from flask_jwt_extended import get_jwt_identity
    from app.models import User
    
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        # Return employee schedule data
        return jsonify({
            "success": True,
            "data": {
                "user_id": user.userID,
                "schedule": []
            }
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@common_bp.route("/schedule/", methods=["GET"])
@jwt_required()
def schedule_user_tasks():
    """Get employee schedule from database cache (if month param provided) or job logs"""
    from flask_jwt_extended import get_jwt_identity
    from app.models import User, ScheduleJobLog, ScheduleDefinition, CachedSchedule, SyncLog
    
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        # CRITICAL: Validate user authentication
        if current_user_id != user.userID:
            logger.error(f"[CACHE] SECURITY: JWT user_id ({current_user_id}) does not match user.userID ({user.userID})")
            return jsonify({"error": "User authentication mismatch"}), 403
        
        # If month parameter is provided, return employee schedule from cache
        month = request.args.get('month')
        if month:
            logger.info(f"[CACHE] /schedule/ endpoint: Fetching schedule from DB for user {user.userID} (username: {user.username}, employee_id: {user.employee_id}), month: {month}")
            
            # Get active schedule definition
            schedule_def = ScheduleDefinition.query.filter_by(
                tenantID=user.tenantID,
                is_active=True
            ).first()
            
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
            
            if not schedule_def:
                return jsonify({
                    "success": True,
                    "month": month,
                    "schedule": [],
                    "source": "database",
                    "message": "No active schedule found"
                }), 200
            
            # CRITICAL: Ensure we only fetch schedules for the logged-in user
            # Use user.userID (not current_user_id) for consistency and validation
            schedules_query = CachedSchedule.get_user_schedule(
                user_id=user.userID,  # CRITICAL: Use user.userID to ensure correct filtering
                schedule_def_id=schedule_def.scheduleDefID,
                month=month,
                max_age_hours=0  # Disable age filtering - show all cached data
            )
            
            schedules = []
            for schedule_entry in schedules_query.all():
                # CRITICAL: Verify each entry belongs to this user
                if schedule_entry.user_id != user.userID:
                    logger.error(f"[CACHE] SECURITY ISSUE: Schedule entry {schedule_entry.id} has user_id={schedule_entry.user_id} but expected {user.userID}")
                    continue  # Skip entries that don't belong to this user
                
                schedules.append({
                    "date": schedule_entry.date.isoformat() if schedule_entry.date else None,
                    "shift_type": schedule_entry.shift_type,
                    "shiftType": schedule_entry.shift_type,  # Also include camelCase for frontend
                    "time_range": schedule_entry.time_range,
                    "timeRange": schedule_entry.time_range  # Also include camelCase
                })
            
            logger.info(f"[CACHE] Returning {len(schedules)} schedule entries for user_id={user.userID} (employee_id={user.employee_id})")
            
            # Get last sync time
            last_sync = SyncLog.get_last_sync(schedule_def_id=schedule_def.scheduleDefID)
            last_synced_at = last_sync.completed_at.isoformat() if last_sync and last_sync.completed_at else None
            
            # AUTO-SYNC FALLBACK: If no cached schedule data exists, trigger Celery sync automatically
            cache_empty = len(schedules) == 0
            no_sync_exists = not last_sync or not last_sync.completed_at
            
            if cache_empty or no_sync_exists:
                logger.info(f"[AUTO-SYNC] No cached schedule data found for user {current_user_id}, triggering Celery sync")
                try:
                    # Import celery to trigger async task
                    try:
                        from app.celery_app import celery
                    except ImportError:
                        try:
                            from app.extensions import celery
                        except ImportError:
                            celery = None
                    
                    if celery:
                        # Trigger Celery task asynchronously (non-blocking)
                        celery.send_task(
                            "app.tasks.google_sync.sync_schedule_definition",
                            args=[schedule_def.scheduleDefID],
                            kwargs={'force': True}
                        )
                        logger.info(f"[AUTO-SYNC] ✅ Celery sync task triggered for schedule {schedule_def.scheduleDefID}")
                        
                        # Return 202 Accepted with message indicating auto-sync is running
                        return jsonify({
                            "success": False,
                            "synced": False,  # Not synced yet
                            "message": "Auto-sync triggered. Schedule will be available soon.",
                            "auto_sync_triggered": True,
                            "schedule_def_id": schedule_def.scheduleDefID,
                            "schedule": [],  # Empty schedule while syncing
                            "last_synced_at": last_synced_at
                        }), 202
                    else:
                        # Fallback to direct sync if Celery not available
                        logger.warning("[AUTO-SYNC] Celery not available, falling back to direct sync")
                        from app.services.google_sheets_sync_service import GoogleSheetsSyncService
                        creds_path = current_app.config.get('GOOGLE_APPLICATION_CREDENTIALS', 'service-account-creds.json')
                        sync_service = GoogleSheetsSyncService(creds_path)
                        import threading
                        app_instance = current_app._get_current_object()
                        def sync_in_background():
                            with app_instance.app_context():
                                try:
                                    sync_result = sync_service.sync_schedule_data(
                                        schedule_def_id=schedule_def.scheduleDefID,
                                        sync_type='auto',
                                        triggered_by=current_user_id,
                                        force=True
                                    )
                                    if sync_result.get('success'):
                                        logger.info(f"[AUTO-SYNC] ✅ Direct sync completed: {sync_result.get('rows_synced', 0)} rows")
                                except Exception as e:
                                    logger.error(f"[AUTO-SYNC] Direct sync exception: {e}")
                        threading.Thread(target=sync_in_background, daemon=True).start()
                        return jsonify({
                            "success": False,
                            "synced": False,  # Not synced yet
                            "message": "Auto-sync triggered. Schedule will be available soon.",
                            "auto_sync_triggered": True,
                            "schedule": [],  # Empty schedule while syncing
                            "last_synced_at": last_synced_at
                        }), 202
                except Exception as e:
                    logger.error(f"[AUTO-SYNC] Failed to trigger auto-sync: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    # Continue to return empty schedule if auto-sync fails
            
            # Trigger daily sync if data is stale (but not empty - handled above)
            # Sync if: Last sync > 24 hours ago (daily sync)
            should_sync = SyncLog.should_sync(schedule_def_id=schedule_def.scheduleDefID, min_minutes=1440)  # 24 hours (1 day) threshold for daily sync
            
            if should_sync and not cache_empty:
                logger.info(f"[CACHE] Triggering daily sync: should_sync={should_sync} (last sync > 24h)")
                try:
                    # Trigger async sync (non-blocking) - ensure fresh daily data
                    from app.services.google_sheets_sync_service import GoogleSheetsSyncService
                    creds_path = current_app.config.get('GOOGLE_APPLICATION_CREDENTIALS', 'service-account-creds.json')
                    sync_service = GoogleSheetsSyncService(creds_path)
                    # Run sync in background thread (don't wait for it)
                    import threading
                    app_instance = current_app._get_current_object()
                    def sync_in_background():
                        with app_instance.app_context():
                            try:
                                logger.info(f"[CACHE] Starting daily sync for schedule {schedule_def.scheduleDefID}")
                                from flask_jwt_extended import get_jwt_identity
                                try:
                                    current_user_id = get_jwt_identity()
                                except:
                                    current_user_id = None
                                sync_result = sync_service.sync_schedule_data(
                                    schedule_def_id=schedule_def.scheduleDefID,
                                    sync_type='on_demand',
                                    triggered_by=current_user_id,
                                    force=True
                                )
                                if sync_result.get('success'):
                                    logger.info(f"[CACHE] ✅ Daily sync completed: {sync_result.get('rows_synced', 0)} rows, {sync_result.get('users_synced', 0)} users")
                                else:
                                    logger.error(f"[CACHE] ❌ Daily sync failed: {sync_result.get('error', 'Unknown error')}")
                            except Exception as e:
                                logger.error(f"[CACHE] Daily sync exception: {e}")
                                import traceback
                                logger.error(traceback.format_exc())
                    threading.Thread(target=sync_in_background, daemon=True).start()
                    logger.info(f"[CACHE] Daily sync triggered for schedule {schedule_def.scheduleDefID}")
                except Exception as e:
                    logger.warning(f"[CACHE] Failed to trigger daily sync: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
            
            logger.info(f"[CACHE] Served {len(schedules)} schedule entries from DB via /schedule/ endpoint")
            
            # Determine sync status: synced=True if we have schedule data OR if last sync exists
            is_synced = len(schedules) > 0 or (last_sync is not None and last_sync.completed_at is not None)
            
            return jsonify({
                "success": True,
                "month": month,
                "schedule": schedules,
                "source": "database",
                "synced": is_synced,  # True if schedule data exists or sync has occurred
                "last_synced_at": last_synced_at,
                "cache_empty": len(schedules) == 0
            }), 200
        
        # No month parameter - return job logs (backward compatibility)
        tasks = ScheduleJobLog.query.filter_by(
            tenantID=user.tenantID,
            runByUserID=user.userID
        ).order_by(ScheduleJobLog.startTime.desc()).limit(20).all()
        
        return jsonify([task.to_dict() for task in tasks]), 200
    except Exception as e:
        logger.error(f"Error in schedule_user_tasks: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@common_bp.route("/sync/trigger", methods=["POST"])
def trigger_sync_immediate():
    """
    Immediate sync trigger endpoint (can be called when changes detected)
    No authentication required - can be called from webhooks or external systems
    """
    try:
        data = request.get_json() or {}
        schedule_def_id = data.get('schedule_def_id')
        
        from flask import current_app
        from app.services.google_sheets_sync_service import GoogleSheetsSyncService
        from app.models import ScheduleDefinition
        
        creds_path = current_app.config.get('GOOGLE_APPLICATION_CREDENTIALS', 'service-account-creds.json')
        sync_service = GoogleSheetsSyncService(creds_path)
        
        if schedule_def_id:
            # Sync specific schedule
            result = sync_service.sync_schedule_data(
                schedule_def_id=schedule_def_id,
                sync_type='on_demand',
                triggered_by=None,
                force=True  # Force immediate sync
            )
        else:
            # Sync all active schedules
            schedules = ScheduleDefinition.query.filter_by(is_active=True).all()
            results = []
            for schedule_def in schedules:
                sync_result = sync_service.sync_schedule_data(
                    schedule_def_id=schedule_def.scheduleDefID,
                    sync_type='on_demand',
                    triggered_by=None,
                    force=True
                )
                results.append({
                    'schedule_def_id': schedule_def.scheduleDefID,
                    'schedule_name': schedule_def.scheduleName,
                    **sync_result
                })
            result = {
                'success': all(r.get('success', False) for r in results),
                'schedules': results,
                'total_synced': len([r for r in results if r.get('success', False)])
            }
        
        response = jsonify(result)
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response, 200
        
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error triggering immediate sync: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        response = jsonify({"success": False, "error": str(e)})
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response, 500


@common_bp.route("/admin/sync", methods=["POST"])
@jwt_required()
def sync_google_sheets():
    """Manual sync trigger for Google Sheets to database"""
    from flask_jwt_extended import get_jwt_identity
    from app.utils.auth import role_required
    from app.models import ScheduleDefinition, User, SyncLog
    
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if not user:
            response = jsonify({"success": False, "error": "User not found"})
            response.headers.add("Access-Control-Allow-Origin", "*")
            return response, 404
        
        # Get schedule_def_id from request (optional)
        data = request.get_json() or {}
        schedule_def_id = data.get('schedule_def_id')
        force = data.get('force', False)
        
        logger.info(f"[TRACE][SYNC] /api/v1/admin/sync called by user {current_user_id}, schedule_def_id={schedule_def_id}, force={force}")
        
        # Import sync service
        from flask import current_app
        from app.services.google_sheets_sync_service import GoogleSheetsSyncService
        
        creds_path = current_app.config.get('GOOGLE_APPLICATION_CREDENTIALS', 'service-account-creds.json')
        sync_service = GoogleSheetsSyncService(creds_path)
        
        if schedule_def_id:
            # Sync specific schedule
            logger.info(f"[TRACE][SYNC] Triggering manual sync for schedule {schedule_def_id}")
            result = sync_service.sync_schedule_data(
                schedule_def_id=schedule_def_id,
                sync_type='manual',
                triggered_by=current_user_id,
                force=force
            )
            logger.info(f"[TRACE][SYNC] Manual sync completed: success={result.get('success')}, rows_synced={result.get('rows_synced', 0)}, users_synced={result.get('users_synced', 0)}")
        else:
            # Sync all active schedules for user's tenant
            schedules = ScheduleDefinition.query.filter_by(
                tenantID=user.tenantID,
                is_active=True
            ).all()
            
            logger.info(f"[TRACE][SYNC] Triggering manual sync for {len(schedules)} active schedules in tenant {user.tenantID}")
            
            results = []
            for schedule_def in schedules:
                logger.info(f"[TRACE][SYNC] Syncing schedule: {schedule_def.scheduleName} ({schedule_def.scheduleDefID})")
                sync_result = sync_service.sync_schedule_data(
                    schedule_def_id=schedule_def.scheduleDefID,
                    sync_type='manual',
                    triggered_by=current_user_id,
                    force=force
                )
                results.append({
                    'schedule_def_id': schedule_def.scheduleDefID,
                    'schedule_name': schedule_def.scheduleName,
                    **sync_result
                })
                logger.info(f"[TRACE][SYNC] Schedule {schedule_def.scheduleName} sync: success={sync_result.get('success')}, rows={sync_result.get('rows_synced', 0)}, users={sync_result.get('users_synced', 0)}")
            
            result = {
                'success': all(r.get('success', False) for r in results),
                'schedules': results,
                'total_synced': len([r for r in results if r.get('success', False)])
            }
            logger.info(f"[TRACE][SYNC] Manual sync completed for all schedules: {result['total_synced']}/{len(schedules)} successful")
        
        response = jsonify(result)
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response, 200
        
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error syncing Google Sheets: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        response = jsonify({"success": False, "error": str(e)})
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response, 500


@common_bp.route("/admin/sync/status", methods=["GET"])
@jwt_required()
def sync_status():
    """Get sync status for schedule definitions"""
    from flask_jwt_extended import get_jwt_identity
    from app.models import User, SyncLog
    
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if not user:
            response = jsonify({"success": False, "error": "User not found"})
            response.headers.add("Access-Control-Allow-Origin", "*")
            return response, 404
        
        schedule_def_id = request.args.get('schedule_def_id')
        
        if schedule_def_id:
            last_sync = SyncLog.get_last_sync(schedule_def_id=schedule_def_id)
        else:
            last_sync = SyncLog.get_last_sync(tenant_id=user.tenantID)
        
        if last_sync:
            status_data = {
                'last_synced_at': last_sync.completed_at.isoformat() if last_sync.completed_at else None,
                'status': last_sync.status,
                'rows_synced': last_sync.rows_synced,
                'users_synced': last_sync.users_synced,
                'duration_seconds': last_sync.duration_seconds
            }
        else:
            status_data = {
                'last_synced_at': None,
                'status': 'never_synced',
                'rows_synced': 0,
                'users_synced': 0
            }
        
        response = jsonify({
            "success": True,
            **status_data
        })
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response, 200
        
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error getting sync status: {str(e)}")
        response = jsonify({"success": False, "error": str(e)})
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response, 500

