"""
Dashboard Data Service
Transforms Google Sheets data into dashboard-ready format for each role
Supports Chinese language - data is preserved as-is from Google Sheets
"""

import logging
from typing import Dict, Any, List, Optional
import sys
import os
import re

logger = logging.getLogger(__name__)

# Use shared import utility - import module to access variables dynamically
from . import google_sheets_import as sheets_import_module
from .google_sheets_import import (
    _try_import_google_sheets,
    fetch_schedule_data,
    GoogleSheetsService
)
from ..utils.role_utils import is_client_admin_role

# Aliases for convenience
SHEETS_AVAILABLE = sheets_import_module.SHEETS_AVAILABLE

# Try import at module load
_try_import_google_sheets()


class DashboardDataService:
    """Service to provide Google Sheets data formatted for dashboards"""
    
    def __init__(self, credentials_path: Optional[str] = None):
        if credentials_path:
            # If path is relative and doesn't exist, try project root
            if not os.path.isabs(credentials_path) and not os.path.exists(credentials_path):
                # Calculate project root (assumes we're in backend/app/services/dashboard_data_service.py)
                current_file = os.path.abspath(__file__)
                # Go up: dashboard_data_service.py -> services -> app -> backend -> Project_Up
                project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(current_file))))
                project_creds = os.path.join(project_root, 'service-account-creds.json')
                if os.path.exists(project_creds):
                    credentials_path = project_creds
                    logger.info(f"[TRACE] Found credentials at project root: {credentials_path}")
        self.credentials_path = credentials_path
    
    def get_employee_dashboard_data(self, user_id: str, schedule_def_id: Optional[str] = None) -> Dict[str, Any]:
        """
        E1 My Dashboard - Employee's own schedule and preferences
        Data from: Preferences (filtered by employee), Final Output (filtered by employee)
        """
        # Try to import again if not available (force retry)
        # Use module reference to get latest value
        if not sheets_import_module.SHEETS_AVAILABLE:
            logger.warning("SHEETS_AVAILABLE is False, attempting re-import with force retry...")
            success, path = _try_import_google_sheets(force_retry=True)
            # Re-import to get updated value
            import importlib
            importlib.reload(sheets_import_module)
            if not sheets_import_module.SHEETS_AVAILABLE:
                logger.error(f"Failed to import Google Sheets service after retry. Path attempted: {path}")
                logger.error("Check backend startup logs for detailed import error messages")
                return {"success": False, "error": "Google Sheets service not available. Check backend logs for import errors."}
        
        if not sheets_import_module.SHEETS_AVAILABLE:
            return {"success": False, "error": "Google Sheets service not available"}
        
        try:
            # App context is already available from Flask route
            from app.models import ScheduleDefinition, User
            
            logger.info(f"[TRACE] get_employee_dashboard_data - user_id: {user_id}, schedule_def_id: {schedule_def_id}")
            
            user = User.query.get(user_id)
            if not user:
                logger.error(f"[TRACE] User not found for user_id: {user_id}")
                return {"success": False, "error": "User not found"}
            
            logger.info(f"[TRACE] Found user: {user.username} (tenantID: {user.tenantID})")
            
            # Get schedule definition for user's tenant
            if schedule_def_id:
                schedule_def = ScheduleDefinition.query.filter_by(
                    scheduleDefID=schedule_def_id,
                    tenantID=user.tenantID
                ).first()
                logger.info(f"[TRACE] Looking for schedule_def_id: {schedule_def_id}")
            else:
                schedule_def = ScheduleDefinition.query.filter_by(
                    tenantID=user.tenantID,
                    is_active=True
                ).first()
                logger.info(f"[TRACE] Looking for active schedule for tenant: {user.tenantID}")
            
            if not schedule_def:
                logger.error(f"[TRACE] No schedule definition found for tenant: {user.tenantID}")
                return {"success": False, "error": "No active schedule found"}
            
            logger.info(f"[TRACE] Found schedule definition: {schedule_def.scheduleName} (ID: {schedule_def.scheduleDefID})")
            logger.info(f"[TRACE] Schedule URLs - params: {schedule_def.paramsSheetURL}, results: {schedule_def.resultsSheetURL}")
            
            # Fetch sheets data (already filtered by employee role)
            logger.info(f"[TRACE] Calling fetch_schedule_data with scheduleDefID: {schedule_def.scheduleDefID}, user_role: employee")
            
            # Get fetch_schedule_data from module (may have changed after import)
            current_fetch = sheets_import_module.fetch_schedule_data
            if current_fetch is None:
                logger.error("[TRACE] fetch_schedule_data is None! Cannot fetch data.")
                return {"success": False, "error": "Google Sheets service function not available. Import may have failed."}
            
            try:
                logger.info(f"[TRACE] 📥 Fetching from Google Sheets API (scheduleDefID: {schedule_def.scheduleDefID})")
                sheets_data = current_fetch(
                    schedule_def.scheduleDefID,
                    self.credentials_path,
                    user_role="employee"
                )
                logger.info(f"[TRACE] 📥 Google Sheets API response received - success: {sheets_data.get('success')}")
            except Exception as fetch_err:
                logger.error(f"[TRACE] Exception calling fetch_schedule_data: {fetch_err}")
                import traceback
                logger.error(f"[TRACE] Traceback:\n{traceback.format_exc()}")
                return {"success": False, "error": f"Failed to fetch from Google Sheets: {str(fetch_err)}"}
            
            logger.info(f"[DEBUG] ========== FETCH SCHEDULE DATA RESULT ==========")
            logger.info(f"[DEBUG] Sheets data success: {sheets_data.get('success')}")
            logger.info(f"[DEBUG] Sheets data error: {sheets_data.get('error')}")
            logger.info(f"[DEBUG] Sheets data keys: {list(sheets_data.keys()) if isinstance(sheets_data, dict) else 'Not a dict'}")
            logger.info(f"[DEBUG] Sheets data type: {type(sheets_data)}")
            
            # Log sheets structure
            if isinstance(sheets_data, dict):
                sheets = sheets_data.get("sheets", {})
                if sheets:
                    logger.info(f"[DEBUG] Sheets in response: {list(sheets.keys())}")
                    for sheet_name, sheet_data in sheets.items():
                        if isinstance(sheet_data, dict):
                            logger.info(f"[DEBUG]   - {sheet_name}: success={sheet_data.get('success')}, error={sheet_data.get('error')}")
                        else:
                            logger.info(f"[DEBUG]   - {sheet_name}: type={type(sheet_data)}")
            
            logger.info(f"[DEBUG] ================================================")
            logger.info(f"[TRACE] fetch_schedule_data returned - success: {sheets_data.get('success')}, error: {sheets_data.get('error', 'None')}")
            
            # Even if overall success is False, try to return partial data if available
            # This allows frontend to show what it can instead of completely failing
            sheets = sheets_data.get("sheets", {}) if isinstance(sheets_data, dict) else {}
            
            if not sheets_data.get("success"):
                error_msg = sheets_data.get('error', 'Unknown error')
                logger.warning(f"[DEBUG] ⚠️ fetch_schedule_data returned success=False: {error_msg}")
                
                # Check if we have at least some valid sheet data to return
                has_valid_data = False
                failed_sheets = []
                
                for sheet_name, sheet_data in sheets.items():
                    if sheet_data is not None and isinstance(sheet_data, dict):
                        if sheet_data.get("success"):
                            has_valid_data = True
                            logger.info(f"[TRACE] Sheet '{sheet_name}' succeeded despite overall failure")
                        else:
                            sheet_error = sheet_data.get("error", "Unknown error")
                            failed_sheets.append(f"{sheet_name}: {sheet_error}")
                    elif sheet_data is None:
                        failed_sheets.append(f"{sheet_name}: Sheet data is None")
                
                # If we have no valid data at all, return error
                if not has_valid_data:
                    if failed_sheets:
                        error_msg = f"{error_msg}. Failed sheets: {'; '.join(failed_sheets)}"
                    logger.error(f"[DEBUG] ❌ No valid sheet data available. Returning error.")
                    return {
                        "success": False,
                        "error": error_msg,
                        "schedule_def_id": schedule_def.scheduleDefID,
                        "schedule_name": schedule_def.scheduleName,
                        "details": sheets_data
                    }
                else:
                    # We have partial data - log warning but continue to process
                    logger.warning(f"[TRACE] ⚠️ Some sheets failed, but proceeding with available data. Failed: {', '.join(failed_sheets) if failed_sheets else 'none'}")
            
            # Extract employee-specific data
            sheets = sheets_data.get("sheets", {})
            preferences = sheets.get("preferences") if sheets else None
            final_output = sheets.get("final_output") if sheets else None
            
            # Handle None values safely
            if preferences is None:
                preferences = {}
                logger.warning(f"[TRACE] Preferences sheet is None, using empty dict")
            if final_output is None:
                final_output = {}
                logger.warning(f"[TRACE] Final output sheet is None, using empty dict")
            
            # Safe access with None checks
            prefs_is_dict = isinstance(preferences, dict)
            output_is_dict = isinstance(final_output, dict)
            
            prefs_data = preferences.get('data', []) if prefs_is_dict else []
            output_data = final_output.get('data', []) if output_is_dict else []
            
            # Ensure data is always a list, never None
            if prefs_data is None:
                prefs_data = []
            if output_data is None:
                output_data = []
            
            # Additional type safety
            if not isinstance(prefs_data, list):
                prefs_data = []
            if not isinstance(output_data, list):
                output_data = []
            
            logger.info(f"[TRACE] Extracted sheets - preferences type: {type(preferences)}, final_output type: {type(final_output)}")
            logger.info(f"[TRACE] Extracted sheets - preferences has data: {prefs_is_dict and bool(prefs_data)}, final_output has data: {output_is_dict and bool(output_data)}")
            logger.info(f"[TRACE] Preferences rows fetched: {len(prefs_data)}, Final output rows fetched: {len(output_data)}")
            
            # Log sheet metadata if available
            if prefs_is_dict:
                logger.info(f"[TRACE] Preferences sheet - success: {preferences.get('success')}, rows: {preferences.get('rows', 0)}, columns: {len(preferences.get('columns', []))}")
            if output_is_dict:
                logger.info(f"[TRACE] Final output sheet - success: {final_output.get('success')}, rows: {final_output.get('rows', 0)}, columns: {len(final_output.get('columns', []))}")
            
            # Filter preferences by employee (match by username or employee ID)
            # Strategy: 1. Check EmployeeMapping table, 2. Check Employee sheet, 3. Try direct match
            
            # Step 1: Try to get mapping from database (EmployeeMapping table)
            employee_identifier_from_mapping = None
            from app.models import EmployeeMapping
            # CRITICAL: Use relative import to ensure same db instance
            from ..extensions import db
            
            logger.info(f"[TRACE] Looking up EmployeeMapping for user_id: {user_id}, schedule_def_id: {schedule_def.scheduleDefID}")
            employee_mapping_record = EmployeeMapping.find_by_user(user_id, schedule_def.scheduleDefID)
            
            if employee_mapping_record:
                employee_identifier_from_mapping = employee_mapping_record.sheets_identifier or employee_mapping_record.sheets_name_id
                logger.info(f"[TRACE] ✅ Found EmployeeMapping: '{user_id}' -> '{employee_identifier_from_mapping}'")
            else:
                logger.info(f"[TRACE] No EmployeeMapping found in database, will search Employee sheet")
            
            # Step 2: Try to find employee in Employee sheet to get their Google Sheets identifier
            employee_sheet = sheets.get("employee", {}) if sheets else {}
            employee_data = employee_sheet.get("data", []) if isinstance(employee_sheet, dict) else []
            
            # Try to find user in Employee sheet first
            employee_identifier_from_sheet = None
            if employee_data:
                logger.info(f"[TRACE] Searching Employee sheet for user mapping... (sheet has {len(employee_data)} rows)")
                for emp_row in employee_data:
                    if isinstance(emp_row, dict):
                        # Check multiple fields for matching
                        emp_username = str(emp_row.get('username', '')).strip().lower()
                        emp_name = str(emp_row.get('name', emp_row.get('員工姓名', emp_row.get('姓名', '')))).strip().lower()
                        emp_id = str(emp_row.get('employee_id', emp_row.get('員工ID', emp_row.get('ID', '')))).strip().lower()
                        emp_name_id = str(emp_row.get('員工(姓名/ID)', emp_row.get('員工姓名/ID', ''))).strip()
                        
                        user_match = (
                            emp_username == user.username.lower() or
                            (user.full_name and emp_name == user.full_name.lower()) or
                            str(user.userID).lower() in emp_id or
                            user.username.lower() in emp_id or
                            user.username.lower() in emp_name_id.lower()
                        )
                        
                        if user_match:
                            # Found match - extract the identifier used in schedule sheets
                            if emp_name_id:
                                employee_identifier_from_sheet = emp_name_id
                                logger.info(f"[TRACE] ✅ Found employee mapping in Employee sheet: '{user.username}' -> '{employee_identifier_from_sheet}'")
                            elif 'ID' in emp_row:
                                employee_identifier_from_sheet = str(emp_row['ID']).strip()
                                logger.info(f"[TRACE] ✅ Found employee ID in Employee sheet: '{employee_identifier_from_sheet}'")
                            break
            
            # Try multiple identifiers for better matching
            identifiers = []
            
            # Priority 1: Use mapping from database if available (MOST RELIABLE)
            if employee_identifier_from_mapping:
                identifiers.append(employee_identifier_from_mapping)
                logger.info(f"[TRACE] Added mapping identifier (PRIORITY 1): '{employee_identifier_from_mapping}' (from EmployeeMapping table)")
                # Also try parts of it (e.g., "E04" from "謝○穎/E04")
                if '/' in employee_identifier_from_mapping:
                    parts = employee_identifier_from_mapping.split('/')
                    for part in parts:
                        if part.strip() and part.strip() not in identifiers:
                            identifiers.append(part.strip())
                            logger.info(f"[TRACE] Added extracted part: '{part.strip()}'")
            
            # Priority 2: Use identifier from Employee sheet
            if employee_identifier_from_sheet:
                if employee_identifier_from_sheet not in identifiers:
                    identifiers.append(employee_identifier_from_sheet)
                    logger.info(f"[TRACE] Added sheet identifier (PRIORITY 2): '{employee_identifier_from_sheet}' (from Employee sheet)")
                    # Also try parts of it
                    if '/' in employee_identifier_from_sheet:
                        parts = employee_identifier_from_sheet.split('/')
                        for part in parts:
                            if part.strip() and part.strip() not in identifiers:
                                identifiers.append(part.strip())
            
            # Priority 3: For employees, username IS the employee_id, so prioritize it
            if user.role and user.role.lower() == 'employee' and user.username:
                username_upper = str(user.username).strip().upper()
                if username_upper not in identifiers:
                    identifiers.insert(0, username_upper)  # Insert at beginning for highest priority
                    logger.info(f"[TRACE] Added username as employee_id (PRIORITY 3 - HIGH): '{username_upper}' (for employee role)")
            
            # Priority 4: Try other user identifiers as fallback
            user_identifiers = [
                user.username,
                user.userID,
                f"EMP-{user.userID}",
                user.full_name or ""
            ]
            for uid in user_identifiers:
                if uid and uid not in identifiers:
                    identifiers.append(uid)
            
            logger.info(f"[TRACE] Final identifier list for matching (in priority order): {identifiers}")
            
            employee_preferences = []
            employee_schedule = []
            
            # Ensure we have data lists (handle None safely)
            prefs_data = preferences.get("data", []) if isinstance(preferences, dict) and preferences else []
            output_data = final_output.get("data", []) if isinstance(final_output, dict) and final_output else []
            
            # Ensure data is always a list, never None
            if prefs_data is None:
                prefs_data = []
                logger.warning(f"[TRACE] Preferences data was None, using empty list")
            if output_data is None:
                output_data = []
                logger.warning(f"[TRACE] Final output data was None, using empty list")
            
            # Additional safety: ensure they are lists
            if not isinstance(prefs_data, list):
                logger.warning(f"[TRACE] Preferences data is not a list (type: {type(prefs_data)}), converting to empty list")
                prefs_data = []
            if not isinstance(output_data, list):
                logger.warning(f"[TRACE] Final output data is not a list (type: {type(output_data)}), converting to empty list")
                output_data = []
            
            # Check for None/empty before processing
            if not prefs_data:
                logger.warning(f"[TRACE] Preferences data is empty or None")
            if not output_data:
                logger.warning(f"[TRACE] Final output data is empty or None")
            
            # Safe length checks - ensure we have lists before calling len()
            prefs_count = len(prefs_data) if prefs_data else 0
            output_count = len(output_data) if output_data else 0
            logger.info(f"[TRACE] Filtering with {len(identifiers)} identifier(s) against {prefs_count} prefs rows and {output_count} output rows")
            
            # Try each identifier until we find a match
            matched_identifier = None
            for identifier in identifiers:
                logger.info(f"[TRACE] Trying to match employee data with identifier: '{identifier}'")
                
                employee_preferences = self._filter_employee_data(prefs_data, identifier)
                employee_schedule = self._filter_employee_data(output_data, identifier)
                
                logger.info(f"[TRACE] Match result for '{identifier}': preferences={len(employee_preferences)}, schedule={len(employee_schedule)}")
                
                if employee_schedule and len(employee_schedule) > 0:
                    matched_identifier = identifier
                    logger.info(f"[TRACE] ✅ Successfully matched employee data using identifier: '{identifier}'")
                    
                    # Save mapping to database for future use (if not already saved)
                    if not employee_mapping_record and identifier and identifier != user.username:
                        try:
                            # Extract just the ID part if it's in format "姓名/E04"
                            sheets_id = identifier
                            if '/' in identifier:
                                parts = identifier.split('/')
                                # Try to find the ID part (usually contains letter+number like E04)
                                for part in parts:
                                    if any(c.isalpha() for c in part) and any(c.isdigit() for c in part):
                                        sheets_id = part.strip()
                                        break
                            
                            new_mapping = EmployeeMapping(
                                userID=user_id,
                                tenantID=user.tenantID,
                                sheets_identifier=sheets_id,
                                sheets_name_id=identifier,
                                schedule_def_id=schedule_def.scheduleDefID
                            )
                            db.session.add(new_mapping)
                            db.session.commit()
                            logger.info(f"[TRACE] ✅ Saved EmployeeMapping: '{user_id}' -> '{identifier}' to database")
                        except Exception as map_err:
                            logger.warning(f"[TRACE] Failed to save EmployeeMapping: {map_err}")
                            db.session.rollback()
                    
                    break
            
            # If still no match, log detailed diagnostic info
            if not employee_schedule:
                output_data_list = final_output.get("data", []) if isinstance(final_output, dict) else []
                logger.warning(f"[TRACE] ❌ No employee schedule data found for user '{user.username}' (userID: {user.userID}). Total rows in final_output: {len(output_data_list) if output_data_list else 0}")
                
                if output_data_list and len(output_data_list) > 0 and isinstance(output_data_list[0], dict):
                    # Log what columns/values are available for debugging
                    first_row_keys = list(output_data_list[0].keys())[:5]
                    logger.info(f"[TRACE] First row sample columns: {first_row_keys}")
                    
                    # Log available employee identifiers in the sheet
                    emp_col_key = '員工(姓名/ID)'
                    if emp_col_key in output_data_list[0]:
                        sample_values = [str(row.get(emp_col_key, ''))[:50] for row in output_data_list[:10] if isinstance(row, dict)]
                        logger.info(f"[TRACE] Sample '{emp_col_key}' values from sheet (first 10): {sample_values}")
                        logger.warning(f"[TRACE] These are the identifiers available in Google Sheets. User '{user.username}' needs a mapping to one of these.")
                    
                    # Suggest creating mapping
                    logger.info(f"[TRACE] 💡 SUGGESTION: Create EmployeeMapping record for user '{user.username}' (userID: {user.userID}) to map to one of the sheet identifiers above")
            
            # Ensure employee_schedule and employee_preferences are always lists
            if not isinstance(employee_schedule, list):
                logger.warning(f"[TRACE] employee_schedule is not a list (type: {type(employee_schedule)}), converting to empty list")
                employee_schedule = []
            if not isinstance(employee_preferences, list):
                logger.warning(f"[TRACE] employee_preferences is not a list (type: {type(employee_preferences)}), converting to empty list")
                employee_preferences = []
            
            # Ensure columns are always lists
            prefs_columns = preferences.get("columns", []) if isinstance(preferences, dict) else []
            if not isinstance(prefs_columns, list):
                prefs_columns = []
            
            output_columns = final_output.get("columns", []) if isinstance(final_output, dict) else []
            if not isinstance(output_columns, list):
                output_columns = []
            
            result = {
                "success": True,
                "dashboard": "E1_My",
                "user": {
                    "id": user.userID,
                    "username": user.username,
                    "full_name": user.full_name
                },
                "data": {
                    "preferences": {
                        "rows": employee_preferences,
                        "columns": prefs_columns
                    },
                    "my_schedule": {
                        "rows": employee_schedule,
                        "columns": output_columns
                    }
                },
                "metadata": {
                    "schedule_name": sheets_data.get("schedule_name") if isinstance(sheets_data, dict) else None,
                    "last_updated": None  # Could add timestamp if cached
                }
            }
            
            logger.info(f"[TRACE] ✅ Returning dashboard data - schedule rows: {len(employee_schedule)}, columns: {len(output_columns)}")
            logger.info(f"[TRACE] Preferences rows: {len(employee_preferences)}, columns: {len(prefs_columns)}")
            if employee_schedule:
                logger.info(f"[TRACE] First schedule row sample: {employee_schedule[0]}")
            logger.info(f"[TRACE] Column names (first 10): {output_columns[:10]}")
            
            return result
        except Exception as e:
            logger.error(f"Error getting employee dashboard data: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {"success": False, "error": str(e)}
    
    def get_schedule_manager_d1_data(self, user_id: str, schedule_def_id: Optional[str] = None) -> Dict[str, Any]:
        """
        D1 Scheduling Dashboard - View and manage scheduling data
        Data from: Parameters, Employee, Preferences, Pre-Schedule
        """
        if not SHEETS_AVAILABLE:
            return {"success": False, "error": "Google Sheets service not available"}
        
        try:
            from flask import current_app
            from app.models import ScheduleDefinition, User
            
            user = User.query.get(user_id)
            if not user:
                return {"success": False, "error": "User not found"}
            
            if schedule_def_id:
                schedule_def = ScheduleDefinition.query.filter_by(
                    scheduleDefID=schedule_def_id,
                    tenantID=user.tenantID
                ).first()
            else:
                schedule_def = ScheduleDefinition.query.filter_by(
                    tenantID=user.tenantID,
                    is_active=True
                ).first()
            
            if not schedule_def:
                return {"success": False, "error": "No active schedule found"}
            
            # Fetch all scheduling data
            # CRITICAL: Get fetch_schedule_data from module to ensure we use the wrapped version
            current_fetch = sheets_import_module.fetch_schedule_data
            if current_fetch is None:
                logger.error("[TRACE] fetch_schedule_data is None! Cannot fetch data.")
                return {"success": False, "error": "Google Sheets service function not available. Import may have failed."}
            
            try:
                sheets_data = current_fetch(
                    schedule_def.scheduleDefID,
                    self.credentials_path,
                    user_role="schedulemanager"
                )
            except Exception as fetch_err:
                logger.error(f"[TRACE] Exception calling fetch_schedule_data: {fetch_err}")
                import traceback
                logger.error(f"[TRACE] Traceback:\n{traceback.format_exc()}")
                return {"success": False, "error": f"Failed to fetch from Google Sheets: {str(fetch_err)}"}
            
            if not sheets_data.get("success"):
                return sheets_data
            
            sheets = sheets_data.get("sheets", {})
            
            return {
                "success": True,
                "dashboard": "D1_Scheduling",
                "schedule_def_id": schedule_def.scheduleDefID,
                "schedule_name": sheets_data.get("schedule_name"),
                "data": {
                    "parameters": {
                        "rows": sheets.get("parameters", {}).get("data", []),
                        "columns": sheets.get("parameters", {}).get("columns", []),
                        "rows_count": sheets.get("parameters", {}).get("rows", 0)
                    },
                    "employees": {
                        "rows": sheets.get("employee", {}).get("data", []),
                        "columns": sheets.get("employee", {}).get("columns", []),
                        "rows_count": sheets.get("employee", {}).get("rows", 0)
                    },
                    "preferences": {
                        "rows": sheets.get("preferences", {}).get("data", []),
                        "columns": sheets.get("preferences", {}).get("columns", []),
                        "rows_count": sheets.get("preferences", {}).get("rows", 0)
                    },
                    "pre_schedule": {
                        "rows": sheets.get("pre_schedule", {}).get("data", []),
                        "columns": sheets.get("pre_schedule", {}).get("columns", []),
                        "rows_count": sheets.get("pre_schedule", {}).get("rows", 0)
                    }
                }
            }
        except Exception as e:
            logger.error(f"Error getting D1 dashboard data: {e}")
            return {"success": False, "error": str(e)}
    
    def get_schedule_manager_d2_data(self, user_id: str, schedule_def_id: Optional[str] = None) -> Dict[str, Any]:
        """
        D2 Run Dashboard - Minimal data needed to run schedule
        Data from: Parameters, Pre-Schedule
        """
        if not SHEETS_AVAILABLE:
            return {"success": False, "error": "Google Sheets service not available"}
        
        try:
            from flask import current_app
            from app.models import ScheduleDefinition, User
            
            user = User.query.get(user_id)
            if not user:
                return {"success": False, "error": "User not found"}
            
            if schedule_def_id:
                schedule_def = ScheduleDefinition.query.filter_by(
                    scheduleDefID=schedule_def_id,
                    tenantID=user.tenantID
                ).first()
            else:
                schedule_def = ScheduleDefinition.query.filter_by(
                    tenantID=user.tenantID,
                    is_active=True
                ).first()
            
            if not schedule_def:
                return {"success": False, "error": "No active schedule found"}
            
            # Fetch only essential data for running
            # CRITICAL: Get fetch_schedule_data from module to ensure we use the wrapped version
            current_fetch = sheets_import_module.fetch_schedule_data
            if current_fetch is None:
                logger.error("[TRACE] fetch_schedule_data is None! Cannot fetch data.")
                return {"success": False, "error": "Google Sheets service function not available. Import may have failed."}
            
            try:
                sheets_data = current_fetch(
                    schedule_def.scheduleDefID,
                    self.credentials_path,
                    user_role="schedulemanager"
                )
            except Exception as fetch_err:
                logger.error(f"[TRACE] Exception calling fetch_schedule_data: {fetch_err}")
                import traceback
                logger.error(f"[TRACE] Traceback:\n{traceback.format_exc()}")
                return {"success": False, "error": f"Failed to fetch from Google Sheets: {str(fetch_err)}"}
            
            if not sheets_data.get("success"):
                return sheets_data
            
            sheets = sheets_data.get("sheets", {})
            
            return {
                "success": True,
                "dashboard": "D2_Run",
                "schedule_def_id": schedule_def.scheduleDefID,
                "schedule_name": sheets_data.get("schedule_name"),
                "data": {
                    "parameters": {
                        "rows": sheets.get("parameters", {}).get("data", []),
                        "columns": sheets.get("parameters", {}).get("columns", [])
                    },
                    "pre_schedule": {
                        "rows": sheets.get("pre_schedule", {}).get("data", []),
                        "columns": sheets.get("pre_schedule", {}).get("columns", [])
                    },
                    "ready_to_run": sheets.get("parameters", {}).get("success", False) and \
                                   sheets.get("pre_schedule", {}).get("success", False)
                }
            }
        except Exception as e:
            logger.error(f"Error getting D2 dashboard data: {e}")
            return {"success": False, "error": str(e)}
    
    def get_schedule_manager_d3_data(self, user_id: str, schedule_def_id: Optional[str] = None) -> Dict[str, Any]:
        """
        D3 Export Dashboard - Final schedule output for export
        Data from: Final Output
        """
        if not SHEETS_AVAILABLE:
            return {"success": False, "error": "Google Sheets service not available"}
        
        try:
            from flask import current_app
            from app.models import ScheduleDefinition, User
            
            user = User.query.get(user_id)
            if not user:
                return {"success": False, "error": "User not found"}
            
            if schedule_def_id:
                schedule_def = ScheduleDefinition.query.filter_by(
                    scheduleDefID=schedule_def_id,
                    tenantID=user.tenantID
                ).first()
            else:
                schedule_def = ScheduleDefinition.query.filter_by(
                    tenantID=user.tenantID,
                    is_active=True
                ).first()
            
            if not schedule_def:
                return {"success": False, "error": "No active schedule found"}
            
            # Fetch final output
            # CRITICAL: Get fetch_schedule_data from module to ensure we use the wrapped version
            current_fetch = sheets_import_module.fetch_schedule_data
            if current_fetch is None:
                logger.error("[TRACE] fetch_schedule_data is None! Cannot fetch data.")
                return {"success": False, "error": "Google Sheets service function not available. Import may have failed."}
            
            try:
                sheets_data = current_fetch(
                    schedule_def.scheduleDefID,
                    self.credentials_path,
                    user_role="schedulemanager"
                )
            except Exception as fetch_err:
                logger.error(f"[TRACE] Exception calling fetch_schedule_data: {fetch_err}")
                import traceback
                logger.error(f"[TRACE] Traceback:\n{traceback.format_exc()}")
                return {"success": False, "error": f"Failed to fetch from Google Sheets: {str(fetch_err)}"}
            
            if not sheets_data.get("success"):
                return sheets_data
            
            final_output = sheets_data.get("sheets", {}).get("final_output", {})
            
            return {
                "success": True,
                "dashboard": "D3_Export",
                "schedule_def_id": schedule_def.scheduleDefID,
                "schedule_name": sheets_data.get("schedule_name"),
                "data": {
                    "final_output": {
                        "rows": final_output.get("data", []),
                        "columns": final_output.get("columns", []),
                        "rows_count": final_output.get("rows", 0),
                        "sheet_name": final_output.get("sheet_name", "Final Output")
                    }
                },
                "export_options": {
                    "formats": ["json", "csv", "excel"],
                    "has_data": len(final_output.get("data", [])) > 0 if isinstance(final_output, dict) and final_output else False
                }
            }
        except Exception as e:
            logger.error(f"Error getting D3 dashboard data: {e}")
            return {"success": False, "error": str(e)}
    
    def get_client_admin_b1_data(self, user_id: str) -> Dict[str, Any]:
        """
        B1 ClientAdmin Dashboard - Organization overview
        Data from: All sheets (summary view)
        """
        # Try to import again if not available (force retry)
        if not sheets_import_module.SHEETS_AVAILABLE:
            logger.warning("SHEETS_AVAILABLE is False, attempting re-import with force retry...")
            success, path = _try_import_google_sheets(force_retry=True)
            # Re-import to get updated value
            import importlib
            importlib.reload(sheets_import_module)
            if not sheets_import_module.SHEETS_AVAILABLE:
                logger.error(f"Failed to import Google Sheets service after retry. Path attempted: {path}")
                return {"success": False, "error": "Google Sheets service not available. Check backend logs for import errors."}
        
        if not sheets_import_module.SHEETS_AVAILABLE:
            return {"success": False, "error": "Google Sheets service not available"}
        
        try:
            from flask import current_app
            from app.models import ScheduleDefinition, User, Tenant
            
            user = User.query.get(user_id)
            if not user:
                return {"success": False, "error": "User not found"}
            
            is_client_admin = is_client_admin_role(user.role)
            logger.info(
                "[TRACE] get_client_admin_b1_data - user_id: %s, username: %s, is_client_admin: %s",
                user_id,
                user.username,
                is_client_admin,
            )
            
            tenant_query = Tenant.query if is_client_admin else Tenant.query.filter_by(tenantID=user.tenantID)
            schedule_query = ScheduleDefinition.query if is_client_admin else ScheduleDefinition.query.filter_by(tenantID=user.tenantID)
            
            total_tenants = tenant_query.count()
            active_tenants = tenant_query.filter_by(is_active=True).count()
            all_schedules = schedule_query.all()
            active_schedule_list = [s for s in all_schedules if s.is_active]
            
            logger.info(
                "[TRACE] Database stats - tenants: %s, schedules (total/active): %s/%s",
                total_tenants,
                len(all_schedules),
                len(active_schedule_list),
            )
            
            summary_data = {}
            if active_schedule_list:
                schedule_def = active_schedule_list[0]
                logger.info(f"[TRACE] Fetching sheets data for schedule: {schedule_def.scheduleDefID}")
                
                current_fetch = sheets_import_module.fetch_schedule_data
                if current_fetch is None:
                    logger.error("[TRACE] fetch_schedule_data is None! Cannot fetch data.")
                    return {"success": False, "error": "Google Sheets service function not available. Import may have failed."}
                
                role_for_fetch = "clientadmin" if is_client_admin else "sysadmin"
                try:
                    sheets_data = current_fetch(
                        schedule_def.scheduleDefID,
                        self.credentials_path,
                        user_role=role_for_fetch
                    )
                except Exception as fetch_err:
                    logger.error(f"[TRACE] Exception calling fetch_schedule_data: {fetch_err}")
                    import traceback
                    logger.error(f"[TRACE] Traceback:\n{traceback.format_exc()}")
                    return {"success": False, "error": f"Failed to fetch from Google Sheets: {str(fetch_err)}"}
                
                if sheets_data.get("success"):
                    sheets = sheets_data.get("sheets", {})
                    summary_data = {
                        "total_sheets": len([s for s in sheets.values() if s.get("success")]),
                        "parameters_rows": sheets.get("parameters", {}).get("rows", 0),
                        "employee_rows": sheets.get("employee", {}).get("rows", 0),
                        "preferences_rows": sheets.get("preferences", {}).get("rows", 0),
                        "pre_schedule_rows": sheets.get("pre_schedule", {}).get("rows", 0),
                        "final_output_rows": sheets.get("final_output", {}).get("rows", 0)
                    }
            
            return {
                "success": True,
                "dashboard": "B1_Organization",
                "data": {
                    "summary": summary_data,
                    "system_stats": {
                        "total_tenants": total_tenants,
                        "active_schedules": len(active_schedule_list),
                        "total_schedule_definitions": len(all_schedules)
                    },
                    "sheets_summary": summary_data
                }
            }
        except Exception as e:
            logger.error(f"Error getting B1 dashboard data: {e}")
            return {"success": False, "error": str(e)}
    
    def get_client_admin_b2_data(self, user_id: str) -> Dict[str, Any]:
        """
        B2 ClientAdmin Schedule List Maintenance - List all schedules with sheet status
        Data from: All schedule definitions
        """
        try:
            from flask import current_app
            from app.models import ScheduleDefinition, User
            
            user = User.query.get(user_id)
            if not user:
                return {"success": False, "error": "User not found"}
            
            schedules_query = ScheduleDefinition.query
            if not is_client_admin_role(user.role):
                schedules_query = schedules_query.filter_by(tenantID=user.tenantID)
            
            schedules = schedules_query.all()
            
            schedule_list = []
            for schedule in schedules:
                schedule_list.append({
                    "scheduleDefID": schedule.scheduleDefID,
                    "scheduleName": schedule.scheduleName,
                    "tenantID": schedule.tenantID,
                    "is_active": schedule.is_active,
                    "paramsSheetURL": schedule.paramsSheetURL,
                    "resultsSheetURL": schedule.resultsSheetURL,
                    "created_at": schedule.created_at.isoformat() if schedule.created_at else None
                })
            
            return {
                "success": True,
                "dashboard": "B2_ScheduleListMaintenance",
                "data": {
                    "schedules": schedule_list,
                    "total": len(schedule_list)
                }
            }
        except Exception as e:
            logger.error(f"Error getting B2 dashboard data: {e}")
            return {"success": False, "error": str(e)}
    
    def get_client_admin_b3_data(self, user_id: str, schedule_def_id: Optional[str] = None) -> Dict[str, Any]:
        """
        B3 ClientAdmin Schedule Maintenance - Detailed view of schedule sheets
        Data from: All 6 sheets for specified schedule
        """
        if not SHEETS_AVAILABLE:
            return {"success": False, "error": "Google Sheets service not available"}
        
        try:
            from flask import current_app
            from app.models import ScheduleDefinition, User
            
            user = User.query.get(user_id)
            if not user:
                return {"success": False, "error": "User not found"}
            
            schedules_query = ScheduleDefinition.query
            if not is_client_admin_role(user.role):
                schedules_query = schedules_query.filter_by(tenantID=user.tenantID)
            
            if schedule_def_id:
                schedule_def = schedules_query.filter_by(
                    scheduleDefID=schedule_def_id
                ).first()
            else:
                schedule_def = schedules_query.filter_by(
                    is_active=True
                ).first()
            
            if not schedule_def:
                return {"success": False, "error": "No schedule found"}
            
            # Fetch all sheets
            role_for_fetch = "clientadmin" if is_client_admin_role(user.role) else "sysadmin"
            
            # CRITICAL: Get fetch_schedule_data from module to ensure we use the wrapped version
            current_fetch = sheets_import_module.fetch_schedule_data
            if current_fetch is None:
                logger.error("[TRACE] fetch_schedule_data is None! Cannot fetch data.")
                return {"success": False, "error": "Google Sheets service function not available. Import may have failed."}
            
            try:
                logger.info(f"[TRACE] 📥 Fetching from Google Sheets API (scheduleDefID: {schedule_def.scheduleDefID})")
                sheets_data = current_fetch(
                    schedule_def.scheduleDefID,
                    self.credentials_path,
                    user_role=role_for_fetch
                )
                logger.info(f"[TRACE] 📥 Google Sheets API response received - success: {sheets_data.get('success')}")
            except Exception as fetch_err:
                logger.error(f"[TRACE] Exception calling fetch_schedule_data: {fetch_err}")
                import traceback
                logger.error(f"[TRACE] Traceback:\n{traceback.format_exc()}")
                return {"success": False, "error": f"Failed to fetch from Google Sheets: {str(fetch_err)}"}
            
            return {
                "success": True,
                "dashboard": "B3_ScheduleMaintenance",
                "schedule_def_id": schedule_def.scheduleDefID,
                "schedule_name": schedule_def.scheduleName,
                "data": sheets_data.get("sheets", {})
            }
        except Exception as e:
            logger.error(f"Error getting B3 dashboard data: {e}")
            return {"success": False, "error": str(e)}
    
    def get_clientadmin_c1_data(self, user_id: str) -> Dict[str, Any]:
        """
        C1 Client Admin Dashboard - Tenant overview
        Data from: Organizational data from sheets
        """
        try:
            from flask import current_app
            from app.models import User, Tenant, Department
            
            user = User.query.get(user_id)
            if not user:
                return {"success": False, "error": "User not found"}
            
            tenant = user.tenant
            if not tenant:
                return {"success": False, "error": "Tenant not found"}
            
            departments = Department.query.filter_by(tenantID=tenant.tenantID).all()
            
            return {
                "success": True,
                "dashboard": "C1_Tenant",
                "data": {
                    "tenant": tenant.to_dict(),
                    "departments": [d.to_dict() for d in departments],
                    "stats": {
                        "total_departments": len(departments),
                        "total_users": tenant.users.count()
                    }
                }
            }
        except Exception as e:
            logger.error(f"Error getting C1 dashboard data: {e}")
            return {"success": False, "error": str(e)}
    
    def get_clientadmin_c2_data(self, user_id: str) -> Dict[str, Any]:
        """
        C2 Department Management
        Data from: Department data, Employee sheet (for department assignment)
        """
        try:
            from flask import current_app
            from app.models import User, Tenant, Department
            
            user = User.query.get(user_id)
            if not user:
                return {"success": False, "error": "User not found"}
            
            tenant = user.tenant
            departments = Department.query.filter_by(tenantID=tenant.tenantID).all()
            
            return {
                "success": True,
                "dashboard": "C2_Department",
                "data": {
                    "departments": [d.to_dict() for d in departments]
                }
            }
        except Exception as e:
            logger.error(f"Error getting C2 dashboard data: {e}")
            return {"success": False, "error": str(e)}
    
    def get_clientadmin_c3_data(self, user_id: str) -> Dict[str, Any]:
        """
        C3 User Account Management
        Data from: User data, Employee sheet (linked to users)
        """
        try:
            from flask import current_app
            from app.models import User, Tenant
            
            user = User.query.get(user_id)
            if not user:
                return {"success": False, "error": "User not found"}
            
            tenant = user.tenant
            users = User.query.filter_by(tenantID=tenant.tenantID).all()
            
            return {
                "success": True,
                "dashboard": "C3_UserAccountManagement",
                "data": {
                    "users": [u.to_dict() for u in users]
                }
            }
        except Exception as e:
            logger.error(f"Error getting C3 dashboard data: {e}")
            return {"success": False, "error": str(e)}
    
    def get_clientadmin_c4_data(self, user_id: str) -> Dict[str, Any]:
        """
        C4 Permission Maintenance
        Data from: Schedule permissions, Designation Flow sheet
        """
        try:
            from flask import current_app
            from app.models import User, Tenant, SchedulePermission
            
            user = User.query.get(user_id)
            if not user:
                return {"success": False, "error": "User not found"}
            
            tenant = user.tenant
            permissions = SchedulePermission.query.filter_by(tenantID=tenant.tenantID).all()
            
            return {
                "success": True,
                "dashboard": "C4_PermissionMaintenance",
                "data": {
                    "permissions": [p.to_dict() for p in permissions]
                }
            }
        except Exception as e:
            logger.error(f"Error getting C4 dashboard data: {e}")
            return {"success": False, "error": str(e)}
    
    def _normalize_identifier(self, s: str) -> str:
        """
        Normalize identifier for matching: trim, remove spaces, uppercase
        """
        if not s:
            return ''
        import re
        # Remove all whitespace and full-width spaces
        normalized = re.sub(r'\s+', '', str(s)).strip().upper()
        # Replace full-width characters with half-width
        normalized = normalized.replace('　', '')
        return normalized
    
    def _filter_employee_data(self, data_rows: List[Dict], employee_identifier: str) -> List[Dict]:
        """
        Filter employee data by matching identifier with normalization
        """
        logger.info(f"[TRACE] _filter_employee_data - filtering {len(data_rows)} rows for identifier: {employee_identifier}")
        
        if not data_rows:
            logger.warning(f"No data rows to filter for employee: {employee_identifier}")
            return []
        
        # Normalize the search identifier
        normalized_identifier = self._normalize_identifier(employee_identifier)
        logger.info(f"[TRACE] Normalized identifier: '{employee_identifier}' -> '{normalized_identifier}'")
        
        logger.info(f"Filtering {len(data_rows)} rows for employee identifier: {employee_identifier}")
        
        # Try to find identifier column (could be username, employee_id, name, etc.)
        # First, identify the identifier column by checking all rows
        identifier_column = None
        if data_rows and isinstance(data_rows[0], dict):
            # Check common identifier field names (including Chinese)
            possible_fields = [
                '員工(姓名/ID)', '員工姓名/ID', '員工',  # Chinese Google Sheets column names
                'username', 'employee_id', 'name', 'employee_name', 
                '用户名', '员工ID', '姓名', '员工姓名',
                '員工姓名', '員工ID', '姓名/ID', '姓名/員工ID'
            ]
            
            # Find which field exists in the data
            for field in possible_fields:
                if field in data_rows[0]:
                    identifier_column = field
                    logger.info(f"[TRACE] Found identifier column: '{identifier_column}'")
                    break
        
        filtered = []
        for idx, row in enumerate(data_rows):
            if isinstance(row, dict):
                matched = False
                
                # If we found an identifier column, use it
                if identifier_column and identifier_column in row:
                    row_value = str(row[identifier_column])
                    normalized_row_value = self._normalize_identifier(row_value)
                    
                    # Try exact match (normalized)
                    if normalized_row_value == normalized_identifier:
                        filtered.append(row)
                        matched = True
                        logger.info(f"[TRACE] ✅ Matched row {idx} by '{identifier_column}' (exact): '{row_value}' -> '{normalized_row_value}' == '{normalized_identifier}'")
                    
                    # Try suffix match after '/' (e.g., "E04" from "謝○穎/E04")
                    elif not matched and '/' in row_value:
                        parts = row_value.split('/')
                        for part in parts:
                            normalized_part = self._normalize_identifier(part)
                            if normalized_part == normalized_identifier:
                                filtered.append(row)
                                matched = True
                                logger.info(f"[TRACE] ✅ Matched row {idx} by '{identifier_column}' (suffix): '{part}' -> '{normalized_part}' == '{normalized_identifier}'")
                                break
                        
                        # Also try if identifier is contained in the normalized row value
                        if not matched and normalized_identifier in normalized_row_value:
                            filtered.append(row)
                            matched = True
                            logger.info(f"[TRACE] ✅ Matched row {idx} by '{identifier_column}' (contains): '{normalized_identifier}' in '{normalized_row_value}'")
                    
                    # Try if identifier ends with row value suffix or vice versa
                    elif not matched:
                        # Check if row value ends with identifier (normalized)
                        if normalized_row_value.endswith(normalized_identifier) or normalized_identifier.endswith(normalized_row_value):
                            filtered.append(row)
                            matched = True
                            logger.info(f"[TRACE] ✅ Matched row {idx} by '{identifier_column}' (endswith): '{normalized_row_value}' ends with '{normalized_identifier}'")
                        
                        # Check if identifier is contained in row value
                        elif normalized_identifier in normalized_row_value:
                            filtered.append(row)
                            matched = True
                            logger.info(f"[TRACE] ✅ Matched row {idx} by '{identifier_column}' (contains): '{normalized_identifier}' in '{normalized_row_value}'")
                
                # Fallback: try other common fields if identifier column didn't match
                if not matched:
                    identifier_fields = ['username', 'employee_id', 'name', 'employee_name', '用户名', '员工ID', '姓名', '员工姓名']
                    for field in identifier_fields:
                        if field in row:
                            row_value = str(row[field])
                            normalized_row_value = self._normalize_identifier(row_value)
                            logger.debug(f"[TRACE] Comparing field '{field}': row_value='{row_value}' (normalized: '{normalized_row_value}') vs identifier='{normalized_identifier}'")
                            if normalized_row_value == normalized_identifier:
                                filtered.append(row)
                                matched = True
                                logger.info(f"[TRACE] ✅ Matched row {idx} by field '{field}': '{row_value}' (normalized: '{normalized_row_value}') == '{normalized_identifier}'")
                                break
                    
                    # Try partial matches on other fields (normalized)
                    if not matched:
                        for field in identifier_fields:
                            if field in row:
                                row_value = str(row[field])
                                normalized_row_value = self._normalize_identifier(row_value)
                                if normalized_identifier in normalized_row_value or normalized_row_value in normalized_identifier:
                                    filtered.append(row)
                                    matched = True
                                    logger.info(f"[TRACE] ✅ Matched row {idx} by field '{field}' (partial): '{normalized_row_value}' contains '{normalized_identifier}'")
                                    break
        
        result_count = len(filtered)
        if result_count == 0:
            # Log available values from identifier column for debugging
            if identifier_column and data_rows:
                available_values = [str(row.get(identifier_column, 'N/A'))[:50] for row in data_rows[:5] if isinstance(row, dict)]
                logger.warning(f"No rows matched for employee '{employee_identifier}'. Identifier column: '{identifier_column}'. Available values (first 5): {available_values}")
            else:
                logger.warning(f"No rows matched for employee '{employee_identifier}'. Available row keys: {[list(r.keys())[:3] if isinstance(r, dict) and r else 'N/A' for r in data_rows[:3]]}")
        
        # DON'T return fallback - return empty list if no match
        # The calling code should handle "no match" as a real case, not use wrong data
        return filtered


# Convenience function
def get_dashboard_data(dashboard_code: str, user_id: str, schedule_def_id: Optional[str] = None, credentials_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Get dashboard data for specific dashboard code
    
    Dashboard codes:
    - E1: Employee My
    - D1: Schedule Manager Scheduling
    - D2: Schedule Manager Run
    - D3: Schedule Manager Export
        - B1: ClientAdmin Organization
        - B2: ClientAdmin Schedule List
        - B3: ClientAdmin Schedule Maintenance
    - C1: Client Admin Tenant
    - C2: Client Admin Department
    - C3: Client Admin User Account
    - C4: Client Admin Permissions
    """
    service = DashboardDataService(credentials_path)
    
    dashboard_map = {
        "E1": service.get_employee_dashboard_data,
        "D1": service.get_schedule_manager_d1_data,
        "D2": service.get_schedule_manager_d2_data,
        "D3": service.get_schedule_manager_d3_data,
        "B1": service.get_client_admin_b1_data,
        "B2": service.get_client_admin_b2_data,
        "B3": service.get_client_admin_b3_data,
        "C1": service.get_clientadmin_c1_data,
        "C2": service.get_clientadmin_c2_data,
        "C3": service.get_clientadmin_c3_data,
        "C4": service.get_clientadmin_c4_data
    }
    
    handler = dashboard_map.get(dashboard_code.upper())
    if not handler:
        return {"success": False, "error": f"Unknown dashboard code: {dashboard_code}"}
    
    if schedule_def_id:
        return handler(user_id, schedule_def_id)
    else:
        return handler(user_id)