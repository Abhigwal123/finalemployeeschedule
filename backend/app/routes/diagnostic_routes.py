"""
Diagnostic routes for schedule linking issues
"""
from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import User, CachedSchedule, ScheduleDefinition, EmployeeMapping
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

diagnostic_bp = Blueprint('diagnostic', __name__, url_prefix='/api/v1/diagnostic')

@diagnostic_bp.route('/schedule-linking', methods=['GET'])
@jwt_required()
def diagnose_schedule_linking():
    """Diagnose schedule linking issues for current user"""
    
    try:
        current_user_id = get_jwt_identity()
        current_user = User.query.get(current_user_id)
        
        if not current_user:
            return jsonify({'error': 'User not found'}), 404
        
        # Check if user is admin (for security)
        if current_user.role not in ['admin', 'sys_admin']:
            return jsonify({'error': 'Admin access required'}), 403
        
        result = {
            'timestamp': datetime.utcnow().isoformat(),
            'users': {},
            'employee_mappings': {},
            'schedules': {},
            'issues': []
        }
        
        # Check E01 and E02 users
        for emp_id in ['E01', 'E02']:
            user = User.query.filter(
                (User.username == emp_id) | (User.employee_id == emp_id)
            ).first()
            
            if user:
                result['users'][emp_id] = {
                    'userID': user.userID,
                    'username': user.username,
                    'employee_id': user.employee_id,
                    'tenantID': user.tenantID
                }
                
                # Get EmployeeMapping
                mapping = EmployeeMapping.query.filter_by(
                    sheets_identifier=emp_id
                ).first()
                
                if mapping:
                    result['employee_mappings'][emp_id] = {
                        'mappingID': mapping.mappingID,
                        'userID': mapping.userID,
                        'sheets_identifier': mapping.sheets_identifier,
                        'sheets_name_id': mapping.sheets_name_id,
                        'matches_user': mapping.userID == user.userID
                    }
                    
                    if mapping.userID != user.userID:
                        result['issues'].append(f"{emp_id}: EmployeeMapping.userID ({mapping.userID}) != User.userID ({user.userID})")
                
                # Get schedules
                schedule_defs = ScheduleDefinition.query.filter_by(
                    tenantID=user.tenantID,
                    is_active=True
                ).all()
                
                for sd in schedule_defs:
                    schedules = CachedSchedule.query.filter_by(
                        user_id=user.userID,
                        schedule_def_id=sd.scheduleDefID
                    ).all()
                    
                    if emp_id not in result['schedules']:
                        result['schedules'][emp_id] = {}
                    
                    result['schedules'][emp_id][sd.scheduleDefID] = {
                        'count': len(schedules),
                        'sample_dates': [s.date.isoformat() for s in sorted(schedules, key=lambda x: x.date)[:10]],
                        'sample_entries': [
                            {
                                'date': s.date.isoformat(),
                                'shift_type': s.shift_type,
                                'time_range': s.time_range
                            } for s in sorted(schedules, key=lambda x: x.date)[:5]
                        ]
                    }
        
        # Check for overlaps
        if 'E01' in result['schedules'] and 'E02' in result['schedules']:
            e01_schedules = result['schedules']['E01']
            e02_schedules = result['schedules']['E02']
            
            for schedule_def_id in e01_schedules:
                if schedule_def_id in e02_schedules:
                    e01_dates = set(e01_schedules[schedule_def_id]['sample_dates'])
                    e02_dates = set(e02_schedules[schedule_def_id]['sample_dates'])
                    overlap = e01_dates & e02_dates
                    
                    if len(overlap) > 0:
                        result['issues'].append(f"Overlap found: {len(overlap)} dates overlap between E01 and E02 for schedule {schedule_def_id}")
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Diagnostic error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@diagnostic_bp.route('/check-user-schedule/<employee_id>', methods=['GET'])
@jwt_required()
def check_user_schedule(employee_id):
    """Check what schedule a specific employee_id should see"""
    
    try:
        current_user_id = get_jwt_identity()
        current_user = User.query.get(current_user_id)
        
        if not current_user:
            return jsonify({'error': 'User not found'}), 404
        
        # Find user by employee_id
        target_user = User.query.filter(
            (User.username == employee_id) | (User.employee_id == employee_id)
        ).first()
        
        if not target_user:
            return jsonify({'error': f'User with employee_id {employee_id} not found'}), 404
        
        result = {
            'employee_id': employee_id,
            'user': {
                'userID': target_user.userID,
                'username': target_user.username,
                'employee_id': target_user.employee_id
            },
            'schedules': {}
        }
        
        # Get all schedules for this user
        schedule_defs = ScheduleDefinition.query.filter_by(
            tenantID=target_user.tenantID,
            is_active=True
        ).all()
        
        for sd in schedule_defs:
            schedules = CachedSchedule.query.filter_by(
                user_id=target_user.userID,
                schedule_def_id=sd.scheduleDefID
            ).order_by(CachedSchedule.date.asc()).all()
            
            result['schedules'][sd.scheduleDefID] = {
                'schedule_name': sd.scheduleName,
                'count': len(schedules),
                'entries': [
                    {
                        'date': s.date.isoformat(),
                        'shift_type': s.shift_type,
                        'time_range': s.time_range
                    } for s in schedules
                ]
            }
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Check user schedule error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


