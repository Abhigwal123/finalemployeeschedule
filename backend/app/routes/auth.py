# Authentication Routes
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, get_jwt, verify_jwt_in_request
from .. import db
from ..models import User, Tenant
try:
    from ..schemas import UserSchema, UserLoginSchema, TenantSchema
    SCHEMAS_AVAILABLE = True
except ImportError:
    SCHEMAS_AVAILABLE = False
    UserSchema = None
    UserLoginSchema = None
    TenantSchema = None
from ..utils.security import hash_password, verify_password, validate_password_strength
from ..utils.role_utils import (
    EMPLOYEE_ROLE,
    format_role_for_response,
    is_client_admin_role,
    normalize_role,
)
from ..utils.cors import apply_cors_headers as apply_env_cors_headers
from datetime import datetime, timedelta
import logging
import os

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__)

# Blacklist for revoked tokens (in production, use Redis)
blacklisted_tokens = set()


def _apply_auth_cors(response):
    return apply_env_cors_headers(response)


@auth_bp.after_request
def _auth_after_request(response):
    return _apply_auth_cors(response)


@auth_bp.route('/register', methods=['POST'])
def register():
    """
    Register a new user
    
    Creates a new user. If no tenant is provided, creates a default tenant.
    Supports both simple user registration and tenant+user registration.
    
    Registration permissions:
    - ClientAdmin: can register any role and create tenants
    - SysAdmin: can register ScheduleManager or DepartmentEmployee within their tenant
    - ScheduleManager: can register DepartmentEmployee within their tenant
    - DepartmentEmployee/others: cannot register anyone
    - Anonymous requests are rejected
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        verify_jwt_in_request(optional=False)
        current_user_id = get_jwt_identity()
        if not current_user_id:
            return jsonify({'error': 'Authentication required'}), 401
        
        current_user = User.query.get(current_user_id)
        if not current_user:
            return jsonify({'error': 'User not found'}), 404

        is_current_client_admin = is_client_admin_role(current_user.role)
        
        # Handle both formats: simple user data or tenant+user data
        if 'user' in data and 'tenant' in data:
            # Full registration with tenant
            if not is_current_client_admin:
                return jsonify({
                    'error': 'Registration permission denied',
                    'details': 'Only ClientAdmin users can create tenants during registration.'
                }), 403

            tenant_data = data.get('tenant', {})
            user_data = data.get('user', {})
            
            # Validate tenant data if provided
            if tenant_data and SCHEMAS_AVAILABLE and TenantSchema:
                tenant_schema = TenantSchema()
                tenant_errors = tenant_schema.validate(tenant_data)
                if tenant_errors:
                    return jsonify({'error': 'Invalid tenant data', 'details': tenant_errors}), 400
                
                # Check if tenant name already exists
                existing_tenant = Tenant.find_by_name(tenant_data.get('tenantName', ''))
                if existing_tenant:
                    return jsonify({'error': 'Tenant with this name already exists'}), 409
                
                # Create tenant
                tenant = Tenant(
                    tenantName=tenant_data.get('tenantName', 'Default Tenant'),
                    is_active=tenant_data.get('is_active', True)
                )
                db.session.add(tenant)
                db.session.flush()
                tenant_id = tenant.tenantID
            else:
                # Use first available tenant or create default
                tenant = Tenant.query.first()
                if not tenant:
                    tenant = Tenant(tenantName='Default Tenant', is_active=True)
                    db.session.add(tenant)
                    db.session.flush()
                tenant_id = tenant.tenantID
        else:
            # Simple registration - just user data
            user_data = data
            requested_tenant_id = data.get('tenant_id') or data.get('tenantID')
            tenant = None
            
            if is_current_client_admin:
                tenant_id = requested_tenant_id
                if tenant_id:
                    tenant = Tenant.query.get(tenant_id)
                    if not tenant:
                        return jsonify({'error': 'Tenant not found'}), 404
                else:
                    tenant = Tenant.query.first()
                    if not tenant:
                        tenant = Tenant(tenantName='Default Tenant', is_active=True)
                        db.session.add(tenant)
                        db.session.flush()
                    tenant_id = tenant.tenantID
            else:
                tenant_id = current_user.tenantID
                if not tenant_id:
                    return jsonify({
                        'error': 'Registration permission denied',
                        'details': 'Only ClientAdmin users can register outside their tenant.'
                    }), 403
                
                if requested_tenant_id and requested_tenant_id != tenant_id:
                    return jsonify({
                        'error': 'Registration permission denied',
                        'details': 'You can only register users under your assigned tenant.'
                    }), 403
                
                # Verify tenant exists
                tenant = Tenant.query.get(tenant_id)
                if not tenant:
                    return jsonify({'error': 'Tenant not found'}), 404
        
        # Validate user data
        username = user_data.get('username') or data.get('username')
        password = user_data.get('password') or data.get('password')
        email = user_data.get('email') or data.get('email')
        requested_role = user_data.get('role') or data.get('role', 'employee')
        normalized_role = normalize_role(requested_role or 'employee')
        role_display_value = format_role_for_response(requested_role or 'employee')
        full_name = user_data.get('full_name') or data.get('fullName') or data.get('name')
        employee_id = user_data.get('employee_id') or data.get('employeeID') or data.get('employeeId')
        
        # Validate username is provided
        if not username:
            return jsonify({'error': 'Username is required'}), 400
        
        # Normalize username (strip whitespace, uppercase for consistency)
        username = str(username).strip().upper()
        
        # For employee role: username must match an employee_id in EmployeeMapping
        # For other roles: username is just a regular username
        if normalized_role == EMPLOYEE_ROLE:
            # Employee registration: username must be a valid employee_id from EmployeeMapping
            # The username IS the employee_id
            employee_id = username
            logger.info(f"[REGISTER] Employee registration: Verifying username '{username}' as employee_id in EmployeeMapping")
        else:
            # Non-employee registration: username is regular, employee_id is optional
            if employee_id:
                employee_id = str(employee_id).strip().upper()
        
        if not password:
            return jsonify({'error': 'Password is required'}), 400
        
        # Role-based permission checking
        from app.utils.register_user_helper import can_register_role
        can_register, permission_error = can_register_role(current_user, role_display_value)
        if not can_register:
            logger.warning(f"Registration denied: User {current_user.username if current_user else 'public'} attempted to register role '{role_display_value}': {permission_error}")
            return jsonify({
                'error': 'Registration permission denied',
                'details': permission_error
            }), 403
        
        # For employee role: username will be verified against EmployeeMapping (username must exist as employee_id)
        # For non-employee roles: check if username already exists
        if normalized_role != EMPLOYEE_ROLE:
            existing_user = User.find_by_username(username)
            if existing_user:
                return jsonify({'error': 'Username already exists'}), 409
        
        # Check if email already exists (if provided)
        if email:
            existing_email = User.find_by_email(email)
            if existing_email:
                return jsonify({'error': 'Email already exists'}), 409
        
        # 🔍 CRITICAL: For employee role, validate username matches an employee_id in EmployeeMapping
        from app.models.employee_mapping import EmployeeMapping
        
        # For employee role: username must match an employee_id in EmployeeMapping
        if normalized_role == EMPLOYEE_ROLE:
            # Username IS the employee_id - verify it exists in EmployeeMapping
            # Find EmployeeMapping by sheets_identifier (username = employee_id)
            employee_mapping = EmployeeMapping.find_by_sheets_identifier(username)
            
            if not employee_mapping:
                logger.warning(f"Registration rejected: Username '{username}' does not match any Employee ID in EmployeeMapping")
                return jsonify({
                    'error': 'Invalid Employee ID',
                    'details': f'Username "{username}" does not exist as an Employee ID in the system. Please ensure the Google Sheet has been synced and enter a valid Employee ID as your username.'
                }), 404
            
            # Verify employee_id is active
            if not employee_mapping.is_active:
                logger.warning(f"Registration rejected: Employee ID '{username}' is inactive")
                return jsonify({
                    'error': 'Employee ID is inactive',
                    'details': f'Employee ID "{username}" exists but is marked as inactive. Please contact an administrator.'
                }), 403
            
            # Set employee_id to username for consistency
            employee_id = username
            logger.info(f"[REGISTER] Employee registration: Username '{username}' verified as valid employee_id in EmployeeMapping")
        else:
            # For non-employee roles, employee_id is optional
            employee_mapping = None
            if employee_id:
                employee_mapping = EmployeeMapping.find_by_sheets_identifier(employee_id)
                if not employee_mapping:
                    logger.warning(f"Registration: Employee ID '{employee_id}' not found for non-employee role '{role_display_value}', continuing without employee_id")
                    employee_id = None  # Clear employee_id if not found
        
        # For employee role, verify employee_id is not already linked
        if normalized_role == EMPLOYEE_ROLE and employee_mapping:
            # Check if Employee ID is already linked to another user
            if employee_mapping.userID:
                existing_user = User.query.get(employee_mapping.userID)
                if existing_user:
                    logger.warning(f"Registration rejected: Employee ID '{employee_id}' already linked to user '{existing_user.username}'")
                    return jsonify({
                        'error': 'Employee ID already linked',
                        'details': f'Employee ID "{employee_id}" is already linked to user "{existing_user.username}". Each Employee ID can only be linked to one user account.'
                    }), 409
            
            # Check if another user already has this employee_id
            existing_user_with_employee_id = User.find_by_employee_id(employee_id)
            if existing_user_with_employee_id:
                logger.warning(f"Registration rejected: Employee ID '{employee_id}' already assigned to user '{existing_user_with_employee_id.username}'")
                return jsonify({
                    'error': 'Employee ID already registered',
                    'details': f'Employee ID "{employee_id}" is already assigned to another user account.'
                }), 409
            
            # Verify tenant matches (if schedule_def_id is set in mapping)
            if employee_mapping.tenantID and employee_mapping.tenantID != tenant_id:
                logger.warning(f"Registration rejected: Employee ID '{employee_id}' belongs to different tenant")
                return jsonify({
                    'error': 'Tenant mismatch',
                    'details': f'Employee ID "{employee_id}" belongs to a different tenant.'
                }), 403
            
            # Check if username (which equals employee_id) already exists
            existing_user_with_username = User.find_by_username(username)
            if existing_user_with_username:
                logger.warning(f"Registration rejected: Username '{username}' (employee_id) already exists")
                return jsonify({
                    'error': 'Employee ID already registered',
                    'details': f'Employee ID "{username}" is already registered. This Employee ID may already be linked to another user account.'
                }), 409
        
        # Create user with employee_id
        user = User(
            tenantID=tenant_id,
            username=username,
            password=password,
            role=role_display_value,
            status='active',
            email=email,
            full_name=full_name,
            employee_id=employee_id
        )
        db.session.add(user)
        db.session.flush()  # Flush to get userID
        
        # 🔗 Auto-link EmployeeMapping to the new user (only for employee role)
        normalized_username = None
        if normalized_role == EMPLOYEE_ROLE:
            # Normalize username to ensure consistent matching
            normalized_username = username.strip().upper()
            
            # Attempt to find matching EmployeeMapping
            employee_mapping = EmployeeMapping.find_by_sheets_identifier(normalized_username)
            
            if employee_mapping:
                # Safety check: ensure mapping is not already linked to another user
                if employee_mapping.userID and employee_mapping.userID != user.userID:
                    existing_user = User.query.get(employee_mapping.userID)
                    logger.warning(f"[WARN][REGISTER] EmployeeMapping for '{normalized_username}' already linked to user '{existing_user.username if existing_user else employee_mapping.userID}'")
                else:
                    # Link the found mapping
                    logger.info(f"[TRACE][REGISTER] Employee auto-linked: {normalized_username} -> userID {user.userID}")
                    employee_mapping.userID = user.userID
                    employee_mapping.tenantID = tenant_id  # Ensure tenant matches
                    employee_mapping.is_active = True
                    employee_mapping.updated_at = datetime.utcnow()
                    
                    # Also link any other EmployeeMapping records with the same sheets_identifier and tenant
                    # (in case employee appears in multiple schedules)
                    other_mappings = EmployeeMapping.query.filter(
                        EmployeeMapping.sheets_identifier == normalized_username,
                        EmployeeMapping.tenantID == tenant_id,
                        EmployeeMapping.userID.is_(None),
                        EmployeeMapping.is_active == True
                    ).all()
                    
                    for other_mapping in other_mappings:
                        if other_mapping.mappingID != employee_mapping.mappingID:
                            other_mapping.userID = user.userID
                            other_mapping.updated_at = datetime.utcnow()
                            logger.info(f"[TRACE][REGISTER] Linked additional EmployeeMapping {other_mapping.mappingID} to user {user.userID}")
                    
                    # Ensure user.employee_id is set
                    if not user.employee_id or user.employee_id.upper() != normalized_username:
                        user.employee_id = normalized_username
                        logger.info(f"[TRACE][REGISTER] Set user.employee_id to '{normalized_username}'")
            else:
                logger.warning(f"[WARN][REGISTER] No EmployeeMapping found for '{normalized_username}'. User registered but not linked to employee mapping.")
        
        db.session.commit()
        
        logger.info(f"[TRACE][REGISTER] New user registered: {user.username} (employee_id: {user.employee_id or 'None'}) in tenant: {tenant.tenantName}")
        if normalized_role == EMPLOYEE_ROLE and normalized_username:
            # Re-fetch mapping to ensure we have the latest state after auto-linking
            linked_mapping = EmployeeMapping.find_by_sheets_identifier(normalized_username)
            if linked_mapping and linked_mapping.userID == user.userID:
                logger.info(f"[TRACE][REGISTER] EmployeeMapping auto-linked: {linked_mapping.sheets_identifier} -> {user.userID}")
        
        # For employee role: Trigger sync from Google Sheets to fetch schedule data
        if normalized_role == EMPLOYEE_ROLE:
            from app.models import ScheduleDefinition
            schedule_defs = ScheduleDefinition.query.filter_by(tenantID=tenant_id, is_active=True).all()
            
            for schedule_def in schedule_defs:
                # Check if schedule data exists
                from app.models import CachedSchedule
                schedule_count = CachedSchedule.query.filter_by(
                    user_id=user.userID,
                    schedule_def_id=schedule_def.scheduleDefID
                ).count()
                
                if schedule_count > 0:
                    logger.info(f"[TRACE][SYNC] User {user.userID} already has {schedule_count} schedule entries in schedule {schedule_def.scheduleName}")
                else:
                    logger.info(f"[TRACE][SYNC] User {user.userID} has no schedule entries yet - triggering sync from Google Sheets...")
                    
                    # Trigger sync from Google Sheets to fetch schedule data for this new employee
                    try:
                        from app.services.google_sheets_sync_service import GoogleSheetsSyncService
                        creds_path = current_app.config.get('GOOGLE_APPLICATION_CREDENTIALS', 'service-account-creds.json')
                        sync_service = GoogleSheetsSyncService(creds_path)
                        
                        # Sync in background (non-blocking) so registration response is fast
                        import threading
                        def sync_after_registration():
                            try:
                                with current_app.app_context():
                                    logger.info(f"[TRACE][SYNC] Starting post-registration sync for user {user.userID} (employee_id: {employee_id})")
                                    sync_result = sync_service.sync_schedule_data(
                                        schedule_def_id=schedule_def.scheduleDefID,
                                        sync_type='on_demand',
                                        triggered_by=user.userID,
                                        force=True  # Force sync to fetch from Google Sheets
                                    )
                                    if sync_result.get('success'):
                                        logger.info(f"[TRACE][SYNC] Post-registration sync successful: {sync_result.get('rows_synced', 0)} rows, {sync_result.get('users_synced', 0)} users")
                                    else:
                                        logger.warning(f"[TRACE][SYNC] Post-registration sync failed: {sync_result.get('error', 'Unknown error')}")
                            except Exception as e:
                                logger.error(f"[TRACE][SYNC] Post-registration sync error: {e}")
                                import traceback
                                logger.error(traceback.format_exc())
                        
                        # Start sync in background thread
                        sync_thread = threading.Thread(target=sync_after_registration, daemon=True)
                        sync_thread.start()
                        logger.info(f"[TRACE][SYNC] Post-registration sync thread started for user {user.userID}")
                    except Exception as sync_err:
                        logger.warning(f"[TRACE][SYNC] Failed to trigger post-registration sync: {sync_err}")
        
        # Create access token
        access_token = create_access_token(identity=str(user.userID))
        
        return jsonify({
            'success': True,
            'message': 'User registered successfully',
            'access_token': access_token,
            'user': user.to_dict(),
            'tenant': tenant.to_dict() if tenant else None
        }), 201
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Registration error: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'error': 'Registration failed', 'details': str(e)}), 500


@auth_bp.route('/register', methods=['GET'])
def register_info():
    """Helpful message when visiting the register URL in a browser."""
    return jsonify({
        'message': 'Use POST to register a new user at this endpoint.',
        'example_body': {
            'username': 'testuser',
            'password': 'password123',
            'email': 'test@example.com',
            'role': 'employee'
        },
        'note': 'You can also send {"tenant": {...}, "user": {...}} to create a tenant and user together.'
    }), 200

@auth_bp.route('/login', methods=['POST'])
def login():
    """
    Authenticate user and return access token
    
    Validates user credentials and returns a JWT token for API access.
    """
    # CRITICAL: Import os at function level to avoid UnboundLocalError in exception handlers
    import os as os_module
    # CRITICAL: Log that the route was hit
    logger.info("=" * 80)
    logger.info("[LOGIN] Route hit - POST /api/v1/auth/login")
    logger.info(f"[LOGIN] Request method: {request.method}")
    logger.info(f"[LOGIN] Request origin: {request.headers.get('Origin', 'N/A')}")
    logger.info(f"[LOGIN] Current working directory: {os_module.getcwd()}")
    
    try:
        # Parse JSON data with error handling
        try:
            data = request.get_json(force=True)  # force=True allows parsing even if Content-Type is wrong
            logger.info(f"Login request received - Content-Type: {request.content_type}, Data keys: {list(data.keys()) if data else 'None'}")
        except Exception as json_error:
            logger.error(f"JSON parsing error: {json_error}")
            import traceback
            logger.error(traceback.format_exc())
            return jsonify({'error': 'Invalid JSON data', 'details': str(json_error)}), 400
        
        if not data:
            logger.warning("Login request with no data")
            return jsonify({'error': 'No data provided'}), 400
        
        # Validate login data
        if SCHEMAS_AVAILABLE and UserLoginSchema:
            login_schema = UserLoginSchema()
            errors = login_schema.validate(data)
            if errors:
                return jsonify({'error': 'Invalid login data', 'details': errors}), 400
        
        # Safely extract username and password with proper error handling
        username = data.get('username')
        password = data.get('password')
        
        if not username or not password:
            return jsonify({'error': 'Username and password are required'}), 400
        
        # Verify database connection before querying
        # CRITICAL: Log database configuration at request time
        db_uri = current_app.config.get('SQLALCHEMY_DATABASE_URI', 'NOT SET')
        db_abs_path = current_app.config.get('DATABASE_ABSOLUTE_PATH', 'NOT SET')
        logger.info(f"[LOGIN] Database URI: {db_uri}")
        logger.info(f"[LOGIN] Database absolute path: {db_abs_path}")
        logger.info(f"[LOGIN] Current working directory: {os_module.getcwd()}")
        logger.info(f"[LOGIN] Engine options: {current_app.config.get('SQLALCHEMY_ENGINE_OPTIONS', 'NOT SET')}")
        
        try:
            from sqlalchemy import text
            # Log engine URL before attempting connection
            logger.info(f"[LOGIN] Engine URL: {db.engine.url}")
            logger.info(f"[LOGIN] Attempting database connection...")
            
            # CRITICAL: Ensure we're using the correct database path
            # If the engine URL doesn't match our stored absolute path, log a warning
            engine_url_str = str(db.engine.url)
            if db_abs_path != 'NOT SET' and db_abs_path not in engine_url_str:
                logger.warning(f"[LOGIN] Engine URL path mismatch! Engine: {engine_url_str}, Stored: {db_abs_path}")
            
            db.session.execute(text('SELECT 1'))
            logger.info(f"[LOGIN] Database connection: SUCCESS")
        except Exception as db_error:
            logger.error("=" * 80)
            logger.error(f"[LOGIN] Database connection error: {db_error}")
            logger.error(f"[LOGIN] Error type: {type(db_error).__name__}")
            import traceback
            error_trace = traceback.format_exc()
            logger.error(error_trace)
            
            # Include database URI in error for debugging
            logger.error(f"[LOGIN] Database URI at time of error: {db_uri}")
            
            # Always include database URI for debugging (even if DEBUG is off)
            db_path = None
            db_path_exists = None
            if db_uri.startswith('sqlite:///'):
                # Handle both 3 slashes (sqlite:///) and 4 slashes (sqlite:////)
                if db_uri.startswith('sqlite:////'):
                    db_path = db_uri.replace('sqlite:////', '/')
                else:
                    db_path = db_uri.replace('sqlite:///', '')
                db_path = os_module.path.abspath(db_path)
                db_path_exists = os_module.path.exists(db_path)
            
            error_response = {
                'error': 'Database connection failed', 
                'details': str(db_error),
                'error_type': type(db_error).__name__,
                'database_uri': db_uri,  # Always show for debugging
                'database_path': db_path,
                'database_path_exists': db_path_exists,
                'working_directory': os_module.getcwd()
            }
            if current_app.config.get('DEBUG'):
                error_response['trace'] = error_trace
            return jsonify(error_response), 500
        
        # Find user by username using case-insensitive lookup
        normalized_username = User._normalize_lookup_value(username)
        logger.info(f"[LOGIN] Normalized username for lookup: {normalized_username}")
        try:
            user = User.find_by_username(username)
        except Exception as query_error:
            logger.error(f"Database query error during login: {query_error}")
            import traceback
            error_trace = traceback.format_exc()
            logger.error(error_trace)
            
            db_uri = current_app.config.get('SQLALCHEMY_DATABASE_URI', 'NOT SET')
            error_response = {
                'error': 'Database query failed', 
                'details': str(query_error),
                'error_type': type(query_error).__name__,
                'database_uri': db_uri
            }
            
            if db_uri.startswith('sqlite:///'):
                if db_uri.startswith('sqlite:////'):
                    db_path = db_uri.replace('sqlite:////', '/')
                else:
                    db_path = db_uri.replace('sqlite:///', '')
                db_path = os.path.abspath(db_path)
                error_response['database_path'] = db_path
                error_response['database_path_exists'] = os.path.exists(db_path)
                error_response['working_directory'] = os.getcwd()
                error_response['directory_writable'] = os_module.access(os_module.path.dirname(db_path), os_module.W_OK) if os_module.path.exists(os_module.path.dirname(db_path)) else False
            
            if current_app.config.get('DEBUG'):
                error_response['trace'] = error_trace
            
            return jsonify(error_response), 500
        if not user:
            logger.warning(f"Login attempt with non-existent username: {normalized_username} (original: {username})")
            return jsonify({'error': 'Invalid credentials'}), 401
        
        # Check if user is active
        if not user.is_active():
            logger.warning(f"Login attempt with inactive user: {normalized_username}")
            return jsonify({'error': 'Account is inactive'}), 401
        
        # Verify password (with error handling)
        try:
            password_match = user.check_password(password)
            logger.info(f"[LOGIN] Password verification for {normalized_username}: {password_match}")
            if not password_match:
                logger.warning(f"Invalid password for user: {normalized_username}")
                # Log password hash info for debugging (first 20 chars only)
                logger.debug(f"[LOGIN] Password hash preview: {user.hashedPassword[:20]}...")
                return jsonify({'error': 'Invalid credentials'}), 401
        except Exception as pwd_error:
            logger.error(f"Password verification error for user {username}: {pwd_error}")
            return jsonify({'error': 'Password verification failed', 'details': str(pwd_error)}), 500
        
        # Update last login (non-fatal if commit fails)
        try:
            user.update_last_login()
            db.session.commit()  # Commit the last_login update
        except Exception as commit_error:
            logger.warning(f"Failed to update last_login for user {username}: {commit_error}")
            db.session.rollback()  # Rollback to prevent session issues
            # Continue with login even if last_login update fails
        
        # Get tenant info without loading relationship (use direct query)
        tenant = None
        if user.tenantID:
            from app.models import Tenant
            tenant = db.session.query(Tenant).filter_by(tenantID=user.tenantID).first()
        
        # Create access token with role in claims
        # Verify JWT configuration before creating token
        if not current_app.config.get('JWT_SECRET_KEY'):
            logger.error("JWT_SECRET_KEY not configured")
            return jsonify({'error': 'Server configuration error', 'details': 'JWT not configured'}), 500
        
        additional_claims = {
            'role': user.role,
            'tenantID': user.tenantID,
            'username': user.username
        }
        try:
            access_token = create_access_token(identity=str(user.userID), additional_claims=additional_claims)
        except Exception as jwt_error:
            logger.error(f"JWT token creation failed: {jwt_error}")
            return jsonify({'error': 'Token creation failed', 'details': str(jwt_error)}), 500
        
        logger.info(f"User logged in successfully: {username} (role: {user.role})")
        
        # For employee role: Trigger sync from Google Sheets to ensure schedule data is up-to-date
        if user.role and normalize_role(user.role) == EMPLOYEE_ROLE:
            from app.models import ScheduleDefinition, CachedSchedule
            schedule_defs = ScheduleDefinition.query.filter_by(tenantID=user.tenantID, is_active=True).all()
            
            for schedule_def in schedule_defs:
                # Check if schedule data exists and is recent
                from datetime import datetime, timedelta
                recent_threshold = datetime.utcnow() - timedelta(hours=1)  # 1 hour threshold
                
                schedule_count = CachedSchedule.query.filter_by(
                    user_id=user.userID,
                    schedule_def_id=schedule_def.scheduleDefID
                ).filter(
                    CachedSchedule.updated_at >= recent_threshold
                ).count()
                
                if schedule_count == 0:
                    logger.info(f"[TRACE][SYNC] User {user.userID} has no recent schedule entries - triggering sync after login...")
                    
                    # Trigger sync in background (non-blocking) so login response is fast
                    try:
                        from app.services.google_sheets_sync_service import GoogleSheetsSyncService
                        creds_path = current_app.config.get('GOOGLE_APPLICATION_CREDENTIALS', 'service-account-creds.json')
                        sync_service = GoogleSheetsSyncService(creds_path)
                        
                        import threading
                        def sync_after_login():
                            try:
                                with current_app.app_context():
                                    logger.info(f"[TRACE][SYNC] Starting post-login sync for user {user.userID} (employee_id: {user.employee_id or user.username})")
                                    sync_result = sync_service.sync_schedule_data(
                                        schedule_def_id=schedule_def.scheduleDefID,
                                        sync_type='auto',
                                        triggered_by=user.userID,
                                        force=False  # Don't force - respect rate limits
                                    )
                                    if sync_result.get('success'):
                                        logger.info(f"[TRACE][SYNC] Post-login sync successful: {sync_result.get('rows_synced', 0)} rows, {sync_result.get('users_synced', 0)} users")
                                    else:
                                        logger.warning(f"[TRACE][SYNC] Post-login sync failed: {sync_result.get('error', 'Unknown error')}")
                            except Exception as e:
                                logger.error(f"[TRACE][SYNC] Post-login sync error: {e}")
                                import traceback
                                logger.error(traceback.format_exc())
                        
                        # Start sync in background thread
                        sync_thread = threading.Thread(target=sync_after_login, daemon=True)
                        sync_thread.start()
                        logger.info(f"[TRACE][SYNC] Post-login sync thread started for user {user.userID}")
                    except Exception as sync_err:
                        logger.warning(f"[TRACE][SYNC] Failed to trigger post-login sync: {sync_err}")
        
        # Safely get tenant dict - avoid calling .count() which might trigger lazy loading issues
        tenant_dict = None
        if tenant:
            try:
                tenant_dict = {
                    'tenantID': tenant.tenantID,
                    'tenantName': tenant.tenantName,
                    'created_at': tenant.created_at.isoformat() if tenant.created_at else None,
                    'updated_at': tenant.updated_at.isoformat() if tenant.updated_at else None,
                    'is_active': tenant.is_active
                }
            except Exception as e:
                logger.warning(f"Error serializing tenant: {e}")
                tenant_dict = {'tenantID': tenant.tenantID, 'tenantName': tenant.tenantName}
        
        # Serialize user data (with error handling)
        try:
            user_dict = user.to_dict()
        except Exception as serialize_error:
            logger.error(f"User serialization error for user {username}: {serialize_error}")
            return jsonify({'error': 'User data serialization failed', 'details': str(serialize_error)}), 500
        
        response = jsonify({
            'success': True,
            'message': 'Login successful',
            'access_token': access_token,
            'user': user_dict,
            'tenant': tenant_dict
        })
        
        return response, 200
        
    except KeyError as ke:
        # Handle KeyError specifically (most common issue)
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"Login KeyError: {str(ke)}\n{error_trace}")
        error_response = {'error': 'Missing required field', 'details': f'Missing key: {str(ke)}'}
        if current_app.config.get('DEBUG'):
            error_response['trace'] = error_trace
        return jsonify(error_response), 400
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error("=" * 80)
        logger.error(f"[LOGIN] Unhandled exception: {type(e).__name__}: {str(e)}")
        logger.error(error_trace)
        
        # Always include error details for debugging
        error_response = {
            'error': 'Login failed', 
            'details': str(e), 
            'error_type': type(e).__name__
        }
        
        # ALWAYS include database diagnostics for ANY error (helps debug)
        db_uri = current_app.config.get('SQLALCHEMY_DATABASE_URI', 'NOT SET')
        error_response['database_uri'] = db_uri
        
        if db_uri.startswith('sqlite:///'):
            # Handle both 3 slashes (sqlite:///) and 4 slashes (sqlite:////)
            if db_uri.startswith('sqlite:////'):
                db_path = db_uri.replace('sqlite:////', '/')
            else:
                db_path = db_uri.replace('sqlite:///', '')
            db_path = os_module.path.abspath(db_path)
            error_response['database_path'] = db_path
            error_response['database_path_exists'] = os_module.path.exists(db_path)
            error_response['working_directory'] = os_module.getcwd()
            error_response['directory_writable'] = os_module.access(os_module.path.dirname(db_path), os_module.W_OK) if os_module.path.exists(os_module.path.dirname(db_path)) else False
        
        # Always include trace in development
        error_response['trace'] = error_trace
        
        response = jsonify(error_response)
        logger.error(f"[LOGIN] Returning error response: {error_response}")
        return response, 500

@auth_bp.route('/logout', methods=['POST'])
@jwt_required()
def logout():
    """
    Logout user by blacklisting the current token
    
    Adds the current JWT token to a blacklist to prevent further use.
    """
    try:
        jti = get_jwt()['jti']  # JWT ID
        blacklisted_tokens.add(jti)
        
        logger.info(f"User logged out: {get_jwt_identity()}")
        
        return jsonify({
            'success': True,
            'message': 'Logout successful'
        }), 200
        
    except Exception as e:
        logger.error(f"Logout error: {str(e)}")
        return jsonify({'error': 'Logout failed', 'details': str(e)}), 500

@auth_bp.route('/me', methods=['GET'])
def get_current_user():
    """
    Get current user information
    
    Returns the profile information of the currently authenticated user.
    """
    # Verify JWT token manually (to avoid decorator blocking OPTIONS)
    from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
    
    try:
        verify_jwt_in_request(optional=False)
        current_user_id = get_jwt_identity()
    except Exception as e:
        # Token invalid or missing - but still return proper CORS headers
        logger.warning(f"JWT verification failed for /auth/me: {str(e)}")
        response = jsonify({'error': 'Authentication required', 'details': str(e)})
        return response, 401
    
    try:
        user = User.query.get(current_user_id)
        
        if not user:
            response = jsonify({'error': 'User not found'})
            return response, 404
        
        if not user.is_active():
            response = jsonify({'error': 'Account is inactive'})
            return response, 401
        
        response = jsonify({
            'success': True,
            'user': user.to_dict(),
            'tenant': user.tenant.to_dict() if user.tenant else None
        })
        return response, 200
        
    except Exception as e:
        logger.error(f"Get current user error: {str(e)}")
        response = jsonify({'error': 'Failed to get user information', 'details': str(e)})
        return response, 500

@auth_bp.route('/change-password', methods=['POST'])
@jwt_required()
def change_password():
    """
    Change user password
    
    Allows authenticated users to change their password.
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        current_password = data.get('current_password')
        new_password = data.get('new_password')
        
        if not current_password or not new_password:
            return jsonify({'error': 'Current password and new password are required'}), 400
        
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Verify current password
        if not user.check_password(current_password):
            return jsonify({'error': 'Current password is incorrect'}), 401
        
        # Validate new password strength
        is_valid, error_message = validate_password_strength(new_password)
        if not is_valid:
            return jsonify({'error': error_message}), 400
        
        # Set new password
        user.set_password(new_password)
        db.session.commit()
        
        logger.info(f"Password changed for user: {user.username}")
        
        return jsonify({
            'success': True,
            'message': 'Password changed successfully'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Change password error: {str(e)}")
        return jsonify({'error': 'Failed to change password', 'details': str(e)}), 500

@auth_bp.route('/refresh', methods=['POST'])
@jwt_required()
def refresh():
    """
    Refresh access token
    
    Creates a new access token for the current user.
    """
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if not user or not user.is_active():
            return jsonify({'error': 'User not found or inactive'}), 401
        
        # Create new access token
        access_token = create_access_token(identity=str(user.userID))
        
        return jsonify({
            'success': True,
            'access_token': access_token
        }), 200
        
    except Exception as e:
        logger.error(f"Token refresh error: {str(e)}")
        return jsonify({'error': 'Failed to refresh token', 'details': str(e)}), 500

# JWT token blacklist checker
def check_if_token_revoked(jwt_header, jwt_payload):
    """Check if token is blacklisted"""
    jti = jwt_payload['jti']
    return jti in blacklisted_tokens

# Error handlers
@auth_bp.errorhandler(401)
def unauthorized(error):
    """Handle 401 Unauthorized errors"""
    return jsonify({'error': 'Authentication required'}), 401

@auth_bp.errorhandler(403)
def forbidden(error):
    """Handle 403 Forbidden errors"""
    return jsonify({'error': 'Insufficient permissions'}), 403







