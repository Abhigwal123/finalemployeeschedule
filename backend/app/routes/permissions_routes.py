# Permissions Routes - Matrix Format API
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
# CRITICAL: Use relative import to ensure same db instance
from ..extensions import db
from ..models import SchedulePermission, User, ScheduleDefinition
from ..utils.role_utils import is_client_admin_role, is_schedule_manager_role
import logging

logger = logging.getLogger(__name__)

permissions_bp = Blueprint('permissions', __name__)

def get_current_user():
    """Get current authenticated user"""
    current_user_id = get_jwt_identity()
    return User.query.get(current_user_id)

def require_admin_or_scheduler():
    """Decorator to require admin or scheduler role"""
    from functools import wraps
    
    def decorator(f):
        @wraps(f)
        @jwt_required()
        def decorated_function(*args, **kwargs):
            current_user = get_current_user()
            if not current_user:
                return jsonify({'error': 'User not found'}), 404
            
            # Allow ClientAdmin, tenant admins, and ScheduleManager roles
            if not (
                is_client_admin_role(current_user.role)
                or is_schedule_manager_role(current_user.role)
                or current_user.role in ['admin']
            ):
                return jsonify({'error': 'Access denied'}), 403
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@permissions_bp.route('/matrix', methods=['GET'])
def get_permissions_matrix():
    """
    Get permissions in matrix format for the UI
    Handles OPTIONS preflight requests for CORS
    
    Returns:
    [
      {
        "user": "陳主任 (ER-Manager)",
        "user_id": "user123",
        "department": "急診護理站",
        "permissions": {
          "ER": true,
          "OPD": false,
          "F6": false,
          "F7": false,
          "F8": false
        }
      },
      ...
    ]
    """
    # Require JWT for actual requests
    from flask_jwt_extended import verify_jwt_in_request
    try:
        verify_jwt_in_request()
    except Exception as jwt_err:
        logger.error(f"JWT verification failed: {str(jwt_err)}")
        origin = request.headers.get('Origin', 'http://localhost:5173')
        response = jsonify({'error': 'Authentication required', 'details': 'Invalid or missing token'})
        if 'localhost' in origin or '127.0.0.1' in origin:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, Accept, X-Requested-With"
        return response, 401
    
    try:
        logger.info(f"[TRACE] GET /permissions/matrix - Starting request")
        current_user = get_current_user()
        if not current_user:
            logger.error(f"[ERROR] GET /permissions/matrix - User not found")
            origin = request.headers.get('Origin', 'http://localhost:5173')
            response = jsonify({'error': 'User not found'})
            if 'localhost' in origin or '127.0.0.1' in origin:
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, Accept, X-Requested-With"
            return response, 404
        
        logger.info(f"[TRACE] GET /permissions/matrix - User: {current_user.username}, Role: {current_user.role}, Tenant: {current_user.tenantID}")
        
        # Get all users who can be schedule managers (same tenant)
        # Only show ScheduleManager role users, not ClientAdmin
        managers = User.query.filter(
            User.tenantID == current_user.tenantID,
            User.role.in_(['ScheduleManager', 'Schedule_Manager'])
        ).filter(
            User.status == 'active'
        ).all()
        
        logger.info(f"[TRACE] GET /permissions/matrix - Found {len(managers)} ScheduleManager users for tenant {current_user.tenantID}")
        
        # If no ScheduleManagers found, return empty array with proper CORS
        if not managers:
            logger.info(f"[INFO] No ScheduleManager users found for tenant {current_user.tenantID}")
            origin = request.headers.get('Origin', 'http://localhost:5173')
            response = jsonify([])
            if 'localhost' in origin or '127.0.0.1' in origin:
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, Accept, X-Requested-With"
            logger.info(f"[TRACE] GET /permissions/matrix - Returning empty array (200 OK)")
            return response, 200
        
        # Get all active schedule definitions for this tenant
        schedules = ScheduleDefinition.query.filter_by(
            tenantID=current_user.tenantID,
            is_active=True
        ).all()
        
        # Create a mapping of schedule names to short codes
        # Map schedule names to column keys (ER, OPD, F6, F7, F8)
        schedule_key_map = {}
        schedule_headers = []  # Store header names in order
        
        for schedule in schedules:
            schedule_name = schedule.scheduleName or ''
            # Create a short key from schedule name
            if '急診' in schedule_name or 'ER' in schedule_name.upper():
                key = 'ER'
                header = '急診護理站班表'
            elif '門診' in schedule_name or 'OPD' in schedule_name.upper():
                key = 'OPD'
                header = '門診護理站班表'
            elif '六樓' in schedule_name or 'F6' in schedule_name.upper() or '6F' in schedule_name.upper():
                key = 'F6'
                header = '六樓護理站班表'
            elif '七樓' in schedule_name or 'F7' in schedule_name.upper() or '7F' in schedule_name.upper():
                key = 'F7'
                header = '七樓護理站班表'
            elif '八樓' in schedule_name or 'F8' in schedule_name.upper() or '8F' in schedule_name.upper():
                key = 'F8'
                header = '八樓護理站班表'
            else:
                # Use first 2 chars of schedule name as key
                key = schedule_name[:2] if schedule_name else 'UNK'
                header = schedule_name
            
            schedule_key_map[schedule.scheduleDefID] = {
                'key': key,
                'name': schedule_name,
                'header': header,
                'department': schedule.department.departmentName if schedule.department else '未指定'
            }
            
            # Store headers in order (ER, OPD, F6, F7, F8)
            if key in ['ER', 'OPD', 'F6', 'F7', 'F8'] and header not in schedule_headers:
                schedule_headers.append(header)
        
        # Get all permissions for these users and schedules
        manager_ids = [m.userID for m in managers]
        schedule_ids = [s.scheduleDefID for s in schedules]
        
        if manager_ids and schedule_ids:
            all_permissions = SchedulePermission.query.filter(
                SchedulePermission.tenantID == current_user.tenantID,
                SchedulePermission.userID.in_(manager_ids),
                SchedulePermission.scheduleDefID.in_(schedule_ids)
            ).all()
        else:
            all_permissions = []
        
        # Build permission map: userID -> scheduleDefID -> has_permission
        permission_map = {}
        for perm in all_permissions:
            if perm.userID not in permission_map:
                permission_map[perm.userID] = {}
            permission_map[perm.userID][perm.scheduleDefID] = perm.is_active and perm.canRunJob
        
        # Build matrix rows
        matrix = []
        for manager in managers:
            # Get user's department from their first schedule permission or default
            user_department = '未指定'
            user_permissions = permission_map.get(manager.userID, {})
            
            # Find department from first schedule permission
            for schedule_def_id, has_perm in user_permissions.items():
                if schedule_def_id in schedule_key_map:
                    user_department = schedule_key_map[schedule_def_id]['department']
                    break
            
            # Build permissions object with all schedule keys
            permissions = {}
            # Initialize all standard keys to False
            for key in ['ER', 'OPD', 'F6', 'F7', 'F8']:
                permissions[key] = False
            
            # Set permissions based on actual data
            for schedule in schedules:
                schedule_key = schedule_key_map[schedule.scheduleDefID]['key']
                if schedule_key in ['ER', 'OPD', 'F6', 'F7', 'F8']:
                    permissions[schedule_key] = user_permissions.get(schedule.scheduleDefID, False)
            
            # Format user display name
            user_display_name = f"{manager.full_name or manager.username} ({manager.username})"
            
            matrix.append({
                'user': user_display_name,
                'user_id': manager.userID,
                'department': user_department,
                'permissions': permissions
            })
        
        origin = request.headers.get('Origin', 'http://localhost:5173')
        # Return wrapped format for consistency (frontend handles both formats)
        response = jsonify({"success": True, "permissions": matrix})
        # Always set CORS headers for all origins (development and production)
        if 'localhost' in origin or '127.0.0.1' in origin:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
        else:
            response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, Accept, X-Requested-With"
        logger.info(f"[SUCCESS] GET /permissions/matrix - Returning {len(matrix)} managers for tenant {current_user.tenantID}")
        logger.info(f"[TRACE] GET /permissions/matrix - Response status: 200 OK")
        print("[TRACE] ✅ Returning Permission Matrix Data for ClientAdmin")
        return response, 200
        
    except Exception as e:
        logger.error(f"Get permissions matrix error: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        from flask import request as req
        origin = req.headers.get('Origin', 'http://localhost:5173')
        response = jsonify({'error': 'Failed to retrieve permissions matrix', 'details': str(e)})
        # Allow any localhost origin in development
        if 'localhost' in origin or '127.0.0.1' in origin:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
        return response, 500

@permissions_bp.route('/update', methods=['PUT'])
def update_permissions_bulk():
    """
    Update permissions for a user in bulk
    
    Body:
    {
      "user_id": "user123",
      "permissions": { "ER": true, "OPD": false, ... }
    }
    """
    # Require JWT for actual requests
    from flask_jwt_extended import verify_jwt_in_request
    try:
        verify_jwt_in_request()
    except Exception as jwt_err:
        logger.error(f"JWT verification failed: {str(jwt_err)}")
        origin = request.headers.get('Origin', 'http://localhost:5173')
        response = jsonify({'error': 'Authentication required', 'details': 'Invalid or missing token'})
        if 'localhost' in origin or '127.0.0.1' in origin:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, Accept, X-Requested-With"
        return response, 401
    
    try:
        logger.info(f"[TRACE] PUT /permissions/update - Starting request")
        current_user = get_current_user()
        if not current_user:
            logger.error(f"[ERROR] PUT /permissions/update - User not found")
            origin = request.headers.get('Origin', 'http://localhost:5173')
            response = jsonify({'error': 'User not found'})
            if 'localhost' in origin or '127.0.0.1' in origin:
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, Accept, X-Requested-With"
            return response, 404
        
        logger.info(f"[TRACE] PUT /permissions/update - User: {current_user.username}, Role: {current_user.role}, Tenant: {current_user.tenantID}")
        
        # Check role permissions - only ClientAdmin (platform) or tenant admins can edit
        if not (is_client_admin_role(current_user.role) or current_user.role in ['admin']):
            logger.warning(f"[WARN] PUT /permissions/update - User {current_user.username} (role: {current_user.role}) attempted to update permissions")
            origin = request.headers.get('Origin', 'http://localhost:5173')
            response = jsonify({'error': 'Permission denied. Only ClientAdmin users can update permissions.'})
            if 'localhost' in origin or '127.0.0.1' in origin:
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, Accept, X-Requested-With"
            return response, 403
        
        data = request.get_json()
        if not data:
            logger.error(f"[ERROR] PUT /permissions/update - No data provided")
            origin = request.headers.get('Origin', 'http://localhost:5173')
            response = jsonify({'error': 'No data provided'})
            if 'localhost' in origin or '127.0.0.1' in origin:
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, Accept, X-Requested-With"
            return response, 400
        
        user_id = data.get('user_id')
        permissions = data.get('permissions', {})
        
        logger.info(f"[TRACE] PUT /permissions/update - Updating permissions for user {user_id}, permissions: {list(permissions.keys())}")
        
        if not user_id:
            logger.error(f"[ERROR] PUT /permissions/update - user_id is required")
            origin = request.headers.get('Origin', 'http://localhost:5173')
            response = jsonify({'error': 'user_id is required'})
            if 'localhost' in origin or '127.0.0.1' in origin:
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, Accept, X-Requested-With"
            return response, 400
        
        # Verify user belongs to same tenant
        target_user = User.query.get(user_id)
        if not target_user:
            logger.error(f"[ERROR] PUT /permissions/update - Target user {user_id} not found")
            origin = request.headers.get('Origin', 'http://localhost:5173')
            response = jsonify({'error': 'Target user not found'})
            if 'localhost' in origin or '127.0.0.1' in origin:
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, Accept, X-Requested-With"
            return response, 404
        
        # Tenant check - ClientAdmin can edit any tenant, others are restricted
        if not is_client_admin_role(current_user.role) and target_user.tenantID != current_user.tenantID:
            logger.warning(f"[WARN] PUT /permissions/update - Cross-tenant update attempt: {current_user.username} (tenant: {current_user.tenantID}) tried to update {target_user.username} (tenant: {target_user.tenantID})")
            origin = request.headers.get('Origin', 'http://localhost:5173')
            response = jsonify({'error': 'Cross-tenant update forbidden'})
            if 'localhost' in origin or '127.0.0.1' in origin:
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, Accept, X-Requested-With"
            return response, 403
        
        # Get all active schedules for this tenant
        schedules = ScheduleDefinition.query.filter_by(
            tenantID=current_user.tenantID,
            is_active=True
        ).all()
        
        # Create reverse mapping: schedule key -> scheduleDefID
        key_to_schedule = {}
        for schedule in schedules:
            schedule_name = schedule.scheduleName or ''
            if '急診' in schedule_name or 'ER' in schedule_name.upper():
                key = 'ER'
            elif '門診' in schedule_name or 'OPD' in schedule_name.upper():
                key = 'OPD'
            elif '六樓' in schedule_name or 'F6' in schedule_name.upper() or '6F' in schedule_name.upper():
                key = 'F6'
            elif '七樓' in schedule_name or 'F7' in schedule_name.upper() or '7F' in schedule_name.upper():
                key = 'F7'
            elif '八樓' in schedule_name or 'F8' in schedule_name.upper() or '8F' in schedule_name.upper():
                key = 'F8'
            else:
                key = schedule_name[:2] if schedule_name else 'UNK'
            key_to_schedule[key] = schedule.scheduleDefID
        
        # Update permissions for each schedule
        updated_count = 0
        created_count = 0
        
        for key, has_permission in permissions.items():
            if key not in key_to_schedule:
                logger.warning(f"Schedule key '{key}' not found in active schedules")
                continue
            
            schedule_def_id = key_to_schedule[key]
            
            # Find existing permission
            existing_perm = SchedulePermission.find_by_user_and_schedule(user_id, schedule_def_id)
            
            if has_permission:
                # Grant permission
                if existing_perm:
                    existing_perm.canRunJob = True
                    existing_perm.is_active = True
                    existing_perm.granted_by = current_user.userID
                    existing_perm.updated_at = db.func.now()
                    updated_count += 1
                else:
                    # Create new permission
                    new_perm = SchedulePermission(
                        tenantID=current_user.tenantID,
                        userID=user_id,
                        scheduleDefID=schedule_def_id,
                        canRunJob=True,
                        granted_by=current_user.userID,
                        is_active=True
                    )
                    db.session.add(new_perm)
                    created_count += 1
            else:
                # Revoke permission
                if existing_perm:
                    existing_perm.canRunJob = False
                    existing_perm.is_active = False
                    existing_perm.updated_at = db.func.now()
                    updated_count += 1
        
        db.session.commit()
        
        logger.info(f"[SUCCESS] PUT /permissions/update - Updated permissions for user {user_id}: {updated_count} updated, {created_count} created")
        
        origin = request.headers.get('Origin', 'http://localhost:5173')
        response = jsonify({
            'success': True,
            'message': 'Permissions updated successfully',
            'updated': updated_count,
            'created': created_count
        })
        # Always set CORS headers
        if 'localhost' in origin or '127.0.0.1' in origin:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
        else:
            response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, Accept, X-Requested-With"
        logger.info(f"[TRACE] PUT /permissions/update - Response status: 200 OK")
        return response, 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Update permissions bulk error: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        from flask import request as req
        origin = req.headers.get('Origin', 'http://localhost:5173')
        response = jsonify({'error': 'Failed to update permissions', 'details': str(e)})
        # Allow any localhost origin in development
        if 'localhost' in origin or '127.0.0.1' in origin:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
        return response, 500

# Add a minimal test route to verify blueprint is working
@permissions_bp.route('/test', methods=['GET'])
def test_route():
    """Minimal test route to verify blueprint is working"""
    return jsonify({"message": "test route works"}), 200

# Module-level confirmation - printed when module is imported
print("[TRACE] ✅ Permissions routes module loaded for /permissions/matrix")
print("[TRACE] ✅ Route registered: /api/v1/permissions/matrix with methods GET")
print("[TRACE] ✅ Test route registered: /api/v1/permissions/test")
