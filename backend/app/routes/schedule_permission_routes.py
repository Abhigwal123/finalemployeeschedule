# Schedule Permission Routes
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
# CRITICAL: Use relative import to ensure same db instance
from ..extensions import db
from ..models import SchedulePermission, User, ScheduleDefinition
from ..utils.role_utils import is_client_admin_role, is_schedule_manager_role
try:
    from app.schemas import SchedulePermissionSchema, SchedulePermissionUpdateSchema, PaginationSchema
    SCHEMAS_AVAILABLE = True
except ImportError:
    SCHEMAS_AVAILABLE = False
    SchedulePermissionSchema = None
    SchedulePermissionUpdateSchema = None
    PaginationSchema = None
import logging

logger = logging.getLogger(__name__)

schedule_permission_bp = Blueprint('schedule_permissions', __name__)

def get_current_user():
    """Get current authenticated user"""
    current_user_id = get_jwt_identity()
    return User.query.get(current_user_id)

def require_admin_or_scheduler():
    """Decorator to require admin or scheduler role"""
    def decorator(f):
        def decorated_function(*args, **kwargs):
            user = get_current_user()
            if not user:
                return jsonify({'error': 'User not found'}), 404
            # Allow ClientAdmin, tenant admins, and ScheduleManager roles
            if not (
                is_client_admin_role(user.role)
                or is_schedule_manager_role(user.role)
                or user.role in ['admin', 'scheduler']
            ):
                return jsonify({'error': 'Admin or scheduler access required'}), 403
            return f(*args, **kwargs)
        decorated_function.__name__ = f.__name__
        return decorated_function
    return decorator

@schedule_permission_bp.route('/', methods=['GET'])
@schedule_permission_bp.route('', methods=['GET'])  # Support both / and no slash
@jwt_required()
def get_schedule_permissions():
    """Get schedule permissions for current tenant"""
    import logging
    trace_logger = logging.getLogger('trace')
    
    # [TRACE] Logging
    trace_logger.info("[TRACE] Backend: GET /schedule-permissions")
    trace_logger.info(f"[TRACE] Backend: Path: {request.path}")
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
        try:
            if SCHEMAS_AVAILABLE and PaginationSchema:
                pagination_schema = PaginationSchema()
                pagination_data = pagination_schema.load(request.args)
                page = int(pagination_data.get('page', 1))
                per_page = min(int(pagination_data.get('per_page', 20)), 100)
            else:
                page = int(request.args.get('page', 1) or 1)
                per_page = min(int(request.args.get('per_page', 20) or 20), 100)
        except Exception:
            page = int(request.args.get('page', 1) or 1)
            per_page = min(int(request.args.get('per_page', 20) or 20), 100)
        
        # Query schedule permissions for current tenant
        permissions_query = SchedulePermission.query.filter_by(tenantID=user.tenantID)
        
        # Apply user filter if specified
        user_filter = request.args.get('user_id')
        if user_filter:
            permissions_query = permissions_query.filter_by(userID=user_filter)
        
        # Apply schedule filter if specified
        schedule_filter = request.args.get('schedule_def_id')
        if schedule_filter:
            permissions_query = permissions_query.filter_by(scheduleDefID=schedule_filter)
        
        # Apply active filter if specified
        active_filter = request.args.get('active')
        if active_filter is not None:
            is_active = active_filter.lower() == 'true'
            permissions_query = permissions_query.filter_by(is_active=is_active)
        
        permissions_pagination = permissions_query.order_by(SchedulePermission.created_at.desc()).paginate(
            page=page, 
            per_page=per_page, 
            error_out=False
        )
        
        permissions = [perm.to_dict() for perm in permissions_pagination.items]
        
        # Auto-sync: If no permissions found and this is the first page, trigger sync for schedule data
        if len(permissions) == 0 and page == 1 and permissions_pagination.total == 0:
            logger.info("[AUTO-SYNC] No schedule permissions found, checking if schedule data needs syncing...")
            try:
                from app.utils.auto_sync import sync_all_active_schedules_if_empty
                sync_result = sync_all_active_schedules_if_empty(tenant_id=user.tenantID)
                if sync_result:
                    logger.info(f"[AUTO-SYNC] Schedule sync result: {sync_result.get('success')}")
            except Exception as sync_err:
                logger.warning(f"[AUTO-SYNC] Error during auto-sync: {str(sync_err)}")
        
        trace_logger.info(f"[TRACE] Backend: Returning {len(permissions)} permissions")
        trace_logger.info(f"[TRACE] Backend: Response structure: {{success: True, data: [{len(permissions)} items], pagination: {{...}}}}")
        
        response = jsonify({
            'success': True,
            'data': permissions,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': permissions_pagination.total,
                'pages': permissions_pagination.pages,
                'has_next': permissions_pagination.has_next,
                'has_prev': permissions_pagination.has_prev
            }
        })
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response, 200
        
    except Exception as e:
        logger.error(f"Get schedule permissions error: {str(e)}")
        return jsonify({'error': 'Failed to retrieve schedule permissions', 'details': str(e)}), 500

@schedule_permission_bp.route('/', methods=['POST'])
@jwt_required()
@require_admin_or_scheduler()
def create_schedule_permission():
    """Create a new schedule permission"""
    try:
        current_user = get_current_user()
        
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Validate permission data (optional - only if schemas available)
        if SCHEMAS_AVAILABLE and SchedulePermissionSchema:
            try:
                permission_schema = SchedulePermissionSchema()
                errors = permission_schema.validate(data)
                if errors:
                    logger.warning(f"Schema validation errors (non-blocking): {errors}")
            except Exception as schema_err:
                logger.warning(f"Schema validation error (non-blocking): {str(schema_err)}")
        
        # Basic required field validation
        if 'userID' not in data or 'scheduleDefID' not in data:
            return jsonify({'error': 'userID and scheduleDefID are required'}), 400
        
        # Verify user belongs to tenant
        user = User.query.get(data['userID'])
        if not user or user.tenantID != current_user.tenantID:
            return jsonify({'error': 'Invalid user'}), 400
        
        # Verify schedule definition belongs to tenant
        schedule_def = ScheduleDefinition.query.get(data['scheduleDefID'])
        if not schedule_def or schedule_def.tenantID != current_user.tenantID:
            return jsonify({'error': 'Invalid schedule definition'}), 400
        
        # Check if permission already exists - if exists, update it instead of creating duplicate
        existing_perm = SchedulePermission.find_by_user_and_schedule(data['userID'], data['scheduleDefID'])
        if existing_perm:
            # Update existing permission instead of creating duplicate
            existing_perm.canRunJob = data.get('canRunJob', True)
            if 'can_view' in data or 'canView' in data:
                can_view = data.get('can_view') or data.get('canView')
                if can_view is not None:
                    existing_perm.canRunJob = can_view
            existing_perm.is_active = data.get('is_active', True)
            existing_perm.updated_at = db.func.now()
            db.session.commit()
            
            logger.info(f"Updated existing schedule permission for user {user.username} and schedule {schedule_def.scheduleName} by {current_user.username}")
            
            response = jsonify({
                'success': True,
                'message': 'Schedule permission updated successfully',
                'data': existing_perm.to_dict()
            })
            response.headers.add("Access-Control-Allow-Origin", "*")
            return response, 200
        
        # Create permission
        permission = SchedulePermission(
            tenantID=current_user.tenantID,
            userID=data['userID'],
            scheduleDefID=data['scheduleDefID'],
            canRunJob=data.get('canRunJob', data.get('can_view', data.get('canView', True))),
            granted_by=current_user.userID,
            expires_at=data.get('expires_at'),
            is_active=data.get('is_active', True)
        )
        
        db.session.add(permission)
        db.session.commit()
        
        logger.info(f"New schedule permission created for user {user.username} and schedule {schedule_def.scheduleName} by {current_user.username}")
        
        response = jsonify({
            'success': True,
            'message': 'Schedule permission created successfully',
            'data': permission.to_dict()
        })
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response, 201
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Create schedule permission error: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        response = jsonify({'error': 'Failed to create schedule permission', 'details': str(e)})
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response, 500

@schedule_permission_bp.route('/<permission_id>', methods=['GET'])
@jwt_required()
def get_schedule_permission(permission_id):
    """Get specific schedule permission information"""
    try:
        user = get_current_user()
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Find permission
        permission = SchedulePermission.query.get(permission_id)
        if not permission:
            return jsonify({'error': 'Schedule permission not found'}), 404
        
        # Check tenant access
        if user.tenantID != permission.tenantID:
            return jsonify({'error': 'Access denied'}), 403
        
        return jsonify({
            'success': True,
            'data': permission.to_dict()
        }), 200
        
    except Exception as e:
        logger.error(f"Get schedule permission error: {str(e)}")
        return jsonify({'error': 'Failed to retrieve schedule permission', 'details': str(e)}), 500

@schedule_permission_bp.route('/<permission_id>', methods=['PUT'])
@jwt_required()
@require_admin_or_scheduler()
def update_schedule_permission(permission_id):
    """Update schedule permission information"""
    try:
        current_user = get_current_user()
        
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Validate update data (optional - only if schemas available)
        if SCHEMAS_AVAILABLE and SchedulePermissionUpdateSchema:
            try:
                update_schema = SchedulePermissionUpdateSchema()
                errors = update_schema.validate(data)
                if errors:
                    logger.warning(f"Schema validation errors (non-blocking): {errors}")
            except Exception as schema_err:
                logger.warning(f"Schema validation error (non-blocking): {str(schema_err)}")
        
        # Find permission
        permission = SchedulePermission.query.get(permission_id)
        if not permission:
            return jsonify({'error': 'Schedule permission not found'}), 404
        
        # Check tenant access
        if current_user.tenantID != permission.tenantID:
            return jsonify({'error': 'Access denied'}), 403
        
        # Update fields
        if 'canRunJob' in data:
            permission.canRunJob = data['canRunJob']
        
        if 'can_view' in data or 'canView' in data:
            # Map can_view/canView to canRunJob for backward compatibility
            can_view = data.get('can_view') or data.get('canView')
            if can_view is not None:
                permission.canRunJob = can_view
        
        if 'expires_at' in data:
            permission.expires_at = data['expires_at']
        
        if 'is_active' in data:
            permission.is_active = data['is_active']
        
        permission.updated_at = db.func.now()
        db.session.commit()
        
        logger.info(f"Schedule permission updated: {permission_id} by user: {current_user.username}")
        
        response = jsonify({
            'success': True,
            'message': 'Schedule permission updated successfully',
            'data': permission.to_dict()
        })
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response, 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Update schedule permission error: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        response = jsonify({'error': 'Failed to update schedule permission', 'details': str(e)})
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response, 500

@schedule_permission_bp.route('/<permission_id>', methods=['DELETE'])
@jwt_required()
@require_admin_or_scheduler()
def delete_schedule_permission(permission_id):
    """Delete schedule permission"""
    try:
        current_user = get_current_user()
        
        # Find permission
        permission = SchedulePermission.query.get(permission_id)
        if not permission:
            return jsonify({'error': 'Schedule permission not found'}), 404
        
        # Check tenant access
        if current_user.tenantID != permission.tenantID:
            return jsonify({'error': 'Access denied'}), 403
        
        # Delete permission
        db.session.delete(permission)
        db.session.commit()
        
        logger.info(f"Schedule permission deleted: {permission_id} by user: {current_user.username}")
        
        return jsonify({
            'success': True,
            'message': 'Schedule permission deleted successfully'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Delete schedule permission error: {str(e)}")
        return jsonify({'error': 'Failed to delete schedule permission', 'details': str(e)}), 500

@schedule_permission_bp.route('/matrix', methods=['GET'])
@jwt_required()
def get_permissions_matrix():
    """
    Get permissions in matrix format for the UI
    
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
    try:
        current_user = get_current_user()
        if not current_user:
            return jsonify({'error': 'User not found'}), 404
        
        # Get all users who can be schedule managers (same tenant)
        managers = User.query.filter(
            User.tenantID == current_user.tenantID,
            User.role.in_(['ScheduleManager', 'Schedule_Manager', 'ClientAdmin', 'Client_Admin'])
        ).all()
        
        # Get all active schedule definitions for this tenant
        schedules = ScheduleDefinition.query.filter_by(
            tenantID=current_user.tenantID,
            is_active=True
        ).all()
        
        # Create a mapping of schedule names to short codes
        # Map schedule names to column keys (ER, OPD, F6, F7, F8)
        schedule_key_map = {}
        for schedule in schedules:
            schedule_name = schedule.scheduleName or ''
            # Create a short key from schedule name
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
                # Use first 2 chars of schedule name as key
                key = schedule_name[:2] if schedule_name else 'UNK'
            schedule_key_map[schedule.scheduleDefID] = {
                'key': key,
                'name': schedule_name,
                'department': schedule.department.departmentName if schedule.department else '未指定'
            }
        
        # Get all permissions for these users and schedules
        all_permissions = SchedulePermission.query.filter(
            SchedulePermission.tenantID == current_user.tenantID,
            SchedulePermission.userID.in_([m.userID for m in managers]),
            SchedulePermission.scheduleDefID.in_([s.scheduleDefID for s in schedules])
        ).all()
        
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
            all_keys = set(schedule_key_map[s.scheduleDefID]['key'] for s in schedules)
            for schedule in schedules:
                schedule_key = schedule_key_map[schedule.scheduleDefID]['key']
                permissions[schedule_key] = user_permissions.get(schedule.scheduleDefID, False)
            
            # If no permissions set, initialize all to False
            if not permissions:
                for schedule in schedules:
                    schedule_key = schedule_key_map[schedule.scheduleDefID]['key']
                    permissions[schedule_key] = False
            
            # Format user display name
            user_display_name = f"{manager.full_name or manager.username} ({manager.username})"
            
            matrix.append({
                'user': user_display_name,
                'user_id': manager.userID,
                'department': user_department,
                'permissions': permissions
            })
        
        return jsonify(matrix), 200
        
    except Exception as e:
        logger.error(f"Get permissions matrix error: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'error': 'Failed to retrieve permissions matrix', 'details': str(e)}), 500

@schedule_permission_bp.route('/update', methods=['PUT'])
@jwt_required()
@require_admin_or_scheduler()
def update_permissions_bulk():
    """
    Update permissions for a user in bulk
    
    Body:
    {
      "user_id": "user123",
      "permissions": { "ER": true, "OPD": false, ... }
    }
    """
    try:
        current_user = get_current_user()
        if not current_user:
            return jsonify({'error': 'User not found'}), 404
        
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        user_id = data.get('user_id')
        permissions = data.get('permissions', {})
        
        if not user_id:
            return jsonify({'error': 'user_id is required'}), 400
        
        # Verify user belongs to same tenant
        target_user = User.query.get(user_id)
        if not target_user or target_user.tenantID != current_user.tenantID:
            return jsonify({'error': 'Invalid user'}), 400
        
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
        
        logger.info(f"Updated permissions for user {user_id}: {updated_count} updated, {created_count} created")
        
        return jsonify({
            'success': True,
            'message': 'Permissions updated successfully',
            'updated': updated_count,
            'created': created_count
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Update permissions bulk error: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'error': 'Failed to update permissions', 'details': str(e)}), 500







