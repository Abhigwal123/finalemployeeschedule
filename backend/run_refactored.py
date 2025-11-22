#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CP-SAT Scheduling System (Refactored)
Main entry point for the scheduling system with Google Sheets integration
"""

import argparse
import json
import os
import sys
import pandas as pd
from typing import Dict, Any, Optional

# 🔧 CRITICAL: Setup Python path BEFORE importing app.* modules
# For "from app.data_provider import ..." to work, we need the PROJECT ROOT in sys.path
# NOT the app directory itself (that would break package imports)
# NOTE: This file is now in backend/, so script_dir is backend/, and project_root is parent of backend/
script_dir = os.path.dirname(os.path.abspath(__file__))  # This IS the backend directory
project_root = os.path.dirname(script_dir)  # Project root (parent of backend/)
app_dir = os.path.abspath(os.path.join(project_root, "app"))
backend_dir = script_dir  # We're now inside backend/

# CRITICAL: Remove app_dir from sys.path if it exists (it breaks package imports)
# Something else might have added it (e.g., Google Sheets service loader)
if app_dir in sys.path:
    sys.path.remove(app_dir)

# CRITICAL: Remove backend from sys.path temporarily to avoid namespace conflict
# When both project root and backend are in sys.path, Python might import backend/app instead of root app
backend_in_path = backend_dir in sys.path
if backend_in_path:
    sys.path.remove(backend_dir)

# Add project root to sys.path FIRST (this allows "from app.*" imports)
# DO NOT add app_dir to sys.path - that breaks package imports!
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Log path setup for debugging
import logging
logging.basicConfig(level=logging.INFO)
_path_logger = logging.getLogger(__name__)
_path_logger.info(f"[RUN_REFACTORED] Script dir (backend): {script_dir}")
_path_logger.info(f"[RUN_REFACTORED] Project root: {project_root}")
_path_logger.info(f"[RUN_REFACTORED] App package location: {app_dir}")
if app_dir in sys.path:
    _path_logger.warning(f"[RUN_REFACTORED] ⚠️ App dir was in sys.path - REMOVED to fix package imports")
if backend_in_path:
    _path_logger.warning(f"[RUN_REFACTORED] ⚠️ Backend dir was in sys.path - REMOVED to avoid namespace conflict")
_path_logger.info(f"[RUN_REFACTORED] sys.path[0:3]: {sys.path[0:3]}")
_path_logger.info(f"[RUN_REFACTORED] ✅ Project root in sys.path - 'from app.*' imports should work")

# Default configuration - URLs are preset in the file
DEFAULT_INPUT_SHEET_URL = "https://docs.google.com/spreadsheets/d/1hEr8XD3ThVQQAFWi-Q0owRYxYnBRkwyqiOdbmp6zafg/edit?gid=0#gid=0"
DEFAULT_OUTPUT_SHEET_URL = "https://docs.google.com/spreadsheets/d/16K1AyhmOWWW1pDbWEIOyNB5td32sXxqsKCyO06pjUSw/edit?gid=0#gid=0"
# Credentials are in project root, not backend/
DEFAULT_CREDENTIALS_PATH = os.path.join(project_root, "service-account-creds.json")
os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", DEFAULT_CREDENTIALS_PATH)

# Import our refactored modules - Use absolute imports
# These imports will fail with explicit error if modules not found (no try/except)
_path_logger.info(f"[RUN_REFACTORED] Attempting to import app.* modules...")

# CRITICAL: Verify we're importing from the correct app directory (root app, not backend/app)
# Check if 'app' is already in sys.modules and verify it's the root app
# IMPORTANT: We need to handle the case where backend/app is already imported
# We should NOT delete backend/app modules as they are needed by the backend
backend_app_path = os.path.join(backend_dir, 'app')
backend_app_init = os.path.join(backend_app_path, '__init__.py')

if 'app' in sys.modules:
    existing_app = sys.modules['app']
    existing_app_path = getattr(existing_app, '__file__', None)
    if existing_app_path:
        expected_app_path = os.path.join(app_dir, '__init__.py')
        if existing_app_path != expected_app_path:
            # The 'app' module is from backend/app, not root app
            # We need to handle this carefully - we can't just delete it because
            # backend/app modules (like app.scheduling.integration) depend on it
            _path_logger.warning(f"[RUN_REFACTORED] ⚠️ 'app' module loaded from backend: {existing_app_path}")
            _path_logger.warning(f"[RUN_REFACTORED] Expected root app: {expected_app_path}")
            _path_logger.warning(f"[RUN_REFACTORED] Will import root app modules with explicit path handling")
            
            # Don't delete backend/app - it's needed by the backend
            # Instead, we'll import root app modules directly using importlib
            # This avoids conflicts with backend/app
            use_importlib = True
        else:
            # Already the correct root app
            use_importlib = False
    else:
        use_importlib = False
else:
    use_importlib = False

try:
    if use_importlib:
        # Use importlib to import root app modules, but ensure they're loaded as part of 'app' package
        # This is necessary because root app modules use relative imports (from .data_provider import ...)
        import importlib.util
        import types
        _path_logger.info(f"[RUN_REFACTORED] Using importlib to import root app modules as 'app' package...")
        
        # Step 1: Temporarily store and remove only CONFLICTING backend/app modules from sys.modules
        # We only remove modules that would conflict with root app modules:
        # - app (the package itself) - needed so root app can be set up
        # - app.utils.* modules (if they exist in backend) - needed so root app.utils.* can be used
        # We do NOT remove backend-specific modules like app.scheduling.integration
        backend_app_backup = sys.modules.get('app')
        conflicting_modules = {}
        
        # Check and remove 'app' package if it's from backend
        if 'app' in sys.modules:
            v = sys.modules['app']
            if hasattr(v, '__file__') and v.__file__:
                file_path = str(v.__file__)
                if 'backend' in file_path and 'app' in file_path:
                    conflicting_modules['app'] = v
        
        # Check and remove app.utils.* modules that are from backend
        # We need to check all app.utils.* modules, not just specific ones
        for k, v in list(sys.modules.items()):
            if k.startswith('app.utils'):
                if hasattr(v, '__file__') and v.__file__:
                    file_path = str(v.__file__)
                    if 'backend' in file_path and 'app' in file_path:
                        conflicting_modules[k] = v
        
        # Remove only conflicting modules from sys.modules temporarily
        for k in list(conflicting_modules.keys()):
            del sys.modules[k]
        
        # Step 2: Create root 'app' package in sys.modules
        root_app_init_path = os.path.join(app_dir, '__init__.py')
        root_app_spec = importlib.util.spec_from_file_location('app', root_app_init_path)
        if root_app_spec is None or root_app_spec.loader is None:
            raise ImportError(f"Could not create spec for root app package from {root_app_init_path}")
        root_app_module = importlib.util.module_from_spec(root_app_spec)
        sys.modules['app'] = root_app_module
        root_app_spec.loader.exec_module(root_app_module)
        
        # Step 2.5: Ensure app.utils package is set up before importing modules that use it
        # This is critical because app.schedule_cpsat uses relative imports like "from .utils.logger import get_logger"
        utils_dir = os.path.join(app_dir, 'utils')
        utils_init_path = os.path.join(utils_dir, '__init__.py')
        if os.path.exists(utils_init_path):
            utils_spec = importlib.util.spec_from_file_location('app.utils', utils_init_path)
            if utils_spec and utils_spec.loader:
                utils_module = importlib.util.module_from_spec(utils_spec)
                sys.modules['app.utils'] = utils_module
                utils_spec.loader.exec_module(utils_module)
        
        # Step 3: Import app.utils.logger FIRST to ensure it's in sys.modules before schedule_cpsat imports it
        # This prevents schedule_cpsat from resolving the relative import to backend/app/utils/logger
        from app.utils.logger import setup_logging, get_logger
        
        # Step 4: Now import other root app modules (they'll use relative imports correctly)
        from app.data_provider import create_data_provider
        from app.data_writer import create_data_writer, write_all_results_to_excel, write_all_results_to_google_sheets
        from app.schedule_cpsat import process_input_data, solve_cpsat
        from app.schedule_helpers import (
            build_rows, build_daily_analysis_report, check_hard_constraints, 
            check_soft_constraints, generate_soft_constraint_report, 
            create_schedule_chart, debug_schedule
        )
        
        # Step 5: Restore backend/app and backend app.utils.* modules in sys.modules so backend code can import from them
        # Root app modules are already in sys.modules with their full names (e.g., app.schedule_cpsat),
        # so they remain accessible. We restore backend/app so backend code can do "from app import db"
        # We also need to restore backend app.utils package and its modules that we removed earlier
        if backend_app_backup is not None:
            # Ensure backend directory is in sys.path FIRST so Python can find backend modules when we restore them
            backend_dir_str = str(backend_dir)
            if backend_dir_str not in sys.path:
                sys.path.insert(0, backend_dir_str)
            
            # Restore backend app.utils package and all its modules that were removed
            # First, restore the app.utils package itself if it was removed
            backend_utils_backup = conflicting_modules.get('app.utils')
            if backend_utils_backup:
                sys.modules['app.utils'] = backend_utils_backup
            
            # Then restore all backend app.utils.* modules
            for k, v in conflicting_modules.items():
                if k.startswith('app.utils') and 'backend' in str(getattr(v, '__file__', '')):
                    sys.modules[k] = v
            
            # Finally, restore the backend app package itself
            sys.modules['app'] = backend_app_backup
            
            _path_logger.info(f"[RUN_REFACTORED] ✅ Restored backend/app and backend app.utils.* modules in sys.modules for backend imports")
        
        _path_logger.info(f"[RUN_REFACTORED] ✅ Successfully imported all root app modules")
    else:
        # Normal import path - app module is not conflicting
        # Import app module first to verify it's the correct one
        import app
        app_file = getattr(app, '__file__', None)
        expected_app_file = os.path.join(app_dir, '__init__.py')
        if app_file != expected_app_file:
            _path_logger.error(f"[RUN_REFACTORED] ❌ Imported 'app' from wrong location!")
            _path_logger.error(f"[RUN_REFACTORED] Got: {app_file}")
            _path_logger.error(f"[RUN_REFACTORED] Expected: {expected_app_file}")
            raise ImportError(f"Wrong 'app' module imported. Got {app_file}, expected {expected_app_file}")
        _path_logger.info(f"[RUN_REFACTORED] ✅ Verified 'app' module is from correct location: {app_file}")
        
        # Now import the submodules
        from app.data_provider import create_data_provider
        from app.data_writer import create_data_writer, write_all_results_to_excel, write_all_results_to_google_sheets
        from app.schedule_cpsat import process_input_data, solve_cpsat
        from app.schedule_helpers import (
            build_rows, build_daily_analysis_report, check_hard_constraints, 
            check_soft_constraints, generate_soft_constraint_report, 
            create_schedule_chart, debug_schedule
        )
        from app.utils.logger import setup_logging, get_logger
        _path_logger.info(f"[RUN_REFACTORED] ✅ Successfully imported all app.* modules")
except ImportError as e:
    _path_logger.error(f"[RUN_REFACTORED] ❌ FAILED to import app.* modules: {e}")
    _path_logger.error(f"[RUN_REFACTORED] App dir exists: {os.path.exists(app_dir)}")
    _path_logger.error(f"[RUN_REFACTORED] App dir contents: {os.listdir(app_dir)[:10] if os.path.exists(app_dir) else 'N/A'}")
    _path_logger.error(f"[RUN_REFACTORED] sys.path: {sys.path[:5]}")
    import traceback
    _path_logger.error(f"[RUN_REFACTORED] Traceback: {traceback.format_exc()}")
    raise ImportError(f"Cannot import app.* modules. App dir: {app_dir}, Error: {e}")

# Initialize logger
logger = get_logger(__name__)


def run_schedule_task(
    input_source: str,
    input_config: Dict[str, Any],
    output_destination: str,
    output_config: Dict[str, Any],
    time_limit: float = 90.0,
    debug_shift: Optional[str] = None,
    log_level: str = "INFO"
) -> Dict[str, Any]:
    """
    Main function to run the scheduling task
    
    This function executes the complete end-to-end scheduling process:
    1. Loads input data from specified source (Excel or Google Sheets)
    2. Processes and validates the input data
    3. Solves the scheduling problem using CP-SAT
    4. Generates reports, analysis, and charts
    5. Writes results to specified output destination
    
    Args:
        input_source: 'excel' or 'google_sheets'
        input_config: Configuration for input source
            - For excel: {'file_path': 'path/to/file.xlsx'}
            - For google_sheets: {'spreadsheet_url': 'https://...', 'credentials_path': 'path/to/creds.json'}
        output_destination: 'excel' or 'google_sheets'
        output_config: Configuration for output destination
            - For excel: {'output_path': 'path/to/output.xlsx'}
            - For google_sheets: {'spreadsheet_url': 'https://...', 'credentials_path': 'path/to/creds.json'}
        time_limit: Time limit for solving in seconds (default: 90.0)
        debug_shift: Optional debug shift in format "YYYY/MM/DD,班別,崗位"
        log_level: Logging level (default: "INFO")
    
    Returns:
        Dictionary containing results and status:
        {
            "status": "success" | "error",
            "summary": str,
            "assignments_count": int,
            "total_demand": int,
            "gap_count": int,
            "hard_violations_count": int,
            "soft_violations_count": int,
            "error": str (if status is "error")
        }
    """
    
    # Setup logging with file handler
    # Ensure logs directory exists (use backend/logs since we're in backend/)
    log_dir = os.path.join(script_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    log_file = os.path.join(log_dir, "system.log")
    setup_logging(level=log_level, log_file=log_file)
    logger = get_logger(__name__)
    
    logger.info("=" * 80)
    logger.info("Starting CP-SAT scheduling task...")
    logger.info(f"Input source: {input_source}")
    logger.info(f"Output destination: {output_destination}")
    logger.info(f"Time limit: {time_limit}s")
    logger.info("=" * 80)
    
    try:
        # Step 1: Create data provider and load input data
        logger.info(f"Step 1: Loading data from {input_source}...")
        try:
            data_provider = create_data_provider(input_source, **input_config)
            if data_provider is None:
                error_msg = f"Failed to create data provider for {input_source}"
                logger.error(error_msg)
                return {"error": error_msg, "status": "error"}
            
            provided = process_input_data(data_provider)
            if not provided or not isinstance(provided, dict):
                error_msg = "Failed to process input data - invalid data structure"
                logger.error(error_msg)
                return {"error": error_msg, "status": "error"}
            
            logger.info("✅ Input data processed successfully")
            logger.info(f"   - Employees: {len(provided.get('employees', []))}")
            logger.info(f"   - Weekly demand entries: {len(provided.get('weeklyDemand', []))}")
            logger.info(f"   - Pre-assignments: {len(provided.get('preAssignments', []))}")
            
        except FileNotFoundError as e:
            error_msg = f"Input file or credentials not found: {str(e)}"
            logger.error(error_msg)
            return {"error": error_msg, "status": "error"}
        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            error_type = type(e).__name__
            error_details = str(e) if str(e) else f"{error_type} occurred"
            
            # Create comprehensive error message
            error_msg = f"Error loading input data: {error_details}"
            
            logger.error(error_msg)
            logger.error(f"Error type: {error_type}")
            logger.error(f"Full traceback:\n{error_trace}")
            
            # Return error with full details
            return {
                "error": error_msg,
                "status": "error",
                "error_type": error_type,
                "error_details": error_details,
                "traceback": error_trace
            }
        
        # Debug mode - analyze specific shift
        if debug_shift:
            try:
                logger.info(f"Debug mode: Analyzing shift {debug_shift}")
                parts = debug_shift.split(',')
                if len(parts) != 3:
                    error_msg = "Debug shift format must be YYYY/MM/DD,班別,崗位"
                    logger.error(error_msg)
                    return {"error": error_msg, "status": "error"}
                debug_schedule(provided, parts[0], parts[1], parts[2])
                logger.info("✅ Debug analysis completed")
                return {"status": "debug_complete", "message": "Debug analysis completed successfully"}
            except Exception as e:
                error_msg = f"Error during debug analysis: {str(e)}"
                logger.error(error_msg)
                import traceback
                logger.error(traceback.format_exc())
                return {"error": error_msg, "status": "error"}
        
        # Step 2: Solve the scheduling problem
        logger.info("Step 2: Starting CP-SAT solving...")
        try:
            result = solve_cpsat(provided, time_limit=time_limit)
            if not result or "error" in result:
                error_msg = result.get("error", "Unknown error during solving") if result else "Solver returned no result"
                logger.error(f"❌ CP-SAT solving failed: {error_msg}")
                return {"error": error_msg, "status": "error"}
            
            logger.info("✅ CP-SAT solving completed")
            logger.info(f"   - Final assignments: {len(result.get('finalAssignments', []))}")
            logger.info(f"   - Total demand: {result.get('audit', {}).get('summary', {}).get('totalDemand', 0)}")
            logger.info(f"   - Gaps: {result.get('audit', {}).get('summary', {}).get('gap', 0)}")
            
        except Exception as e:
            error_msg = f"Error during CP-SAT solving: {str(e)}"
            logger.error(error_msg)
            import traceback
            logger.error(traceback.format_exc())
            return {"error": error_msg, "status": "error"}
        
        # Step 3: Generate reports and analysis
        logger.info("Step 3: Generating reports and analysis...")
        try:
            # Build the final schedule grid and get complete assignments
            rows_for_sheet, complete_assignments = build_rows(result["finalAssignments"], provided)
            logger.info(f"   - Built {len(rows_for_sheet)} schedule rows")
            logger.info(f"   - Complete assignments: {len(complete_assignments)}")
            
            # Generate daily analysis report
            detailed_report_lines = build_daily_analysis_report(provided, complete_assignments)
            detailed_report_df = pd.DataFrame(detailed_report_lines, columns=['每日分析'])
            logger.info(f"   - Daily analysis lines: {len(detailed_report_lines)}")
            
            # Perform compliance checks
            hard_violations = check_hard_constraints(complete_assignments, provided)
            soft_violations = check_soft_constraints(result, provided, result["audit"]["byKey"])
            logger.info(f"   - Hard constraint violations: {len(hard_violations)}")
            logger.info(f"   - Soft constraint violations: {len(soft_violations)}")
            
            # Generate gap analysis if gaps exist
            gaps = [item for item in result["audit"]["byKey"] if item.get("gap", 0) > 0]
            gap_analysis_df = pd.DataFrame()
            if gaps:
                # Import is already done at top of file, but ensure it's available
                try:
                    from app.schedule_helpers import generate_gap_analysis_report
                    gap_report_lines = generate_gap_analysis_report(provided, gaps)
                    gap_analysis_df = pd.DataFrame(gap_report_lines, columns=['人力缺口分析與建議'])
                    logger.info(f"   - Gap analysis lines: {len(gap_report_lines)}")
                except ImportError as gap_import_error:
                    logger.warning(f"   - Gap analysis import failed: {gap_import_error}, skipping gap analysis")
                    gap_analysis_df = pd.DataFrame()
            
            # Generate analysis report
            report_text = generate_soft_constraint_report(
                soft_violations, 
                result["audit"]["summary"]["totalDemand"], 
                len(complete_assignments), 
                result, 
                provided, 
                result["audit"]["byKey"]
            )
            logger.info(f"   - Analysis report generated ({len(report_text)} characters)")
            
            # Generate chart
            chart_path = create_schedule_chart(complete_assignments, provided)
            if chart_path:
                logger.info(f"   - Schedule chart created: {chart_path}")
            
            logger.info("✅ Reports and analysis generated successfully")
            
        except Exception as e:
            error_msg = f"Error generating reports: {str(e)}"
            logger.error(error_msg)
            import traceback
            logger.error(traceback.format_exc())
            return {"error": error_msg, "status": "error"}
        
        # Step 4: Prepare results for output
        logger.info("Step 4: Preparing results for output...")
        try:
            results_data = {
                "schedule_results": pd.DataFrame(rows_for_sheet),
                "audit_details": pd.DataFrame(result["audit"]["byKey"]),
                "hard_constraints": pd.DataFrame(hard_violations),
                "soft_constraints": pd.DataFrame(soft_violations),
                "daily_analysis": detailed_report_df,
                "analysis_report": report_text,
                "chart_path": chart_path
            }
            
            if not gap_analysis_df.empty:
                results_data["gap_analysis"] = gap_analysis_df
            
            logger.info(f"   - Prepared {len(results_data)} result sheets")
            
        except Exception as e:
            error_msg = f"Error preparing results: {str(e)}"
            logger.error(error_msg)
            import traceback
            logger.error(traceback.format_exc())
            return {"error": error_msg, "status": "error"}
        
        # Step 5: Write results to output destination
        logger.info(f"Step 5: Writing results to {output_destination}...")
        try:
            if output_destination.lower() == 'excel':
                if 'output_path' not in output_config:
                    error_msg = "output_path is required for excel output"
                    logger.error(error_msg)
                    return {"error": error_msg, "status": "error"}
                
                success = write_all_results_to_excel(output_config['output_path'], results_data)
            elif output_destination.lower() in ['google_sheets', 'google', 'sheets']:
                if 'spreadsheet_url' not in output_config:
                    error_msg = "spreadsheet_url is required for google_sheets output"
                    logger.error(error_msg)
                    return {"error": error_msg, "status": "error"}
                
                success = write_all_results_to_google_sheets(
                    output_config['spreadsheet_url'], 
                    results_data, 
                    output_config.get('credentials_path')
                )
            else:
                error_msg = f"Unsupported output destination: {output_destination}"
                logger.error(error_msg)
                return {"error": error_msg, "status": "error"}
            
            if not success:
                error_msg = "Failed to write results to output destination"
                logger.error(error_msg)
                return {"error": error_msg, "status": "error"}
            
            logger.info(f"✅ Results written successfully to {output_destination}")
            if output_destination.lower() in ['google_sheets', 'google', 'sheets']:
                logger.info(f"   Output URL: {output_config.get('spreadsheet_url', 'N/A')}")
            
        except FileNotFoundError as e:
            error_msg = f"Output file or credentials not found: {str(e)}"
            logger.error(error_msg)
            return {"error": error_msg, "status": "error"}
        except Exception as e:
            error_msg = f"Error writing results: {str(e)}"
            logger.error(error_msg)
            import traceback
            logger.error(traceback.format_exc())
            return {"error": error_msg, "status": "error"}
        
        # Step 6: Prepare final result summary
        logger.info("Step 6: Preparing final summary...")
        summary_parts = []
        if result.get("summary"):
            summary_parts.append(result["summary"])
        else:
            summary_parts.append(f"Generated {len(complete_assignments)} assignments")
            summary_parts.append(f"for {result['audit']['summary']['totalDemand']} total demand")
            if result["audit"]["summary"]["gap"] > 0:
                summary_parts.append(f"with {result['audit']['summary']['gap']} gaps")
        
        final_summary = " | ".join(summary_parts)
        
        logger.info("=" * 80)
        logger.info("✅ Scheduling task completed successfully")
        logger.info(f"   Summary: {final_summary}")
        logger.info(f"   Assignments: {len(complete_assignments)}")
        logger.info(f"   Total Demand: {result['audit']['summary']['totalDemand']}")
        logger.info(f"   Gaps: {result['audit']['summary']['gap']}")
        logger.info(f"   Hard Violations: {len(hard_violations)}")
        logger.info(f"   Soft Violations: {len(soft_violations)}")
        logger.info("=" * 80)
        
        return {
            "status": "success",
            "summary": final_summary,
            "assignments_count": len(complete_assignments),
            "total_demand": result["audit"]["summary"]["totalDemand"],
            "gap_count": result["audit"]["summary"]["gap"],
            "hard_violations_count": len(hard_violations),
            "soft_violations_count": len(soft_violations),
            "output_url": output_config.get('spreadsheet_url') if output_destination.lower() in ['google_sheets', 'google', 'sheets'] else None
        }
        
    except Exception as e:
        error_msg = f"Unexpected error during scheduling task: {str(e)}"
        logger.error(error_msg)
        import traceback
        logger.error(traceback.format_exc())
        return {"error": error_msg, "status": "error"}


def main():
    """
    Command-line interface for the refactored scheduling system
    """
    parser = argparse.ArgumentParser(description="CP-SAT Scheduling System (Refactored)")
    
    # Input configuration
    parser.add_argument("--input-type", choices=['excel', 'google_sheets'], 
                       default='google_sheets',
                       help=f"Input data source type (default: google_sheets)")
    parser.add_argument("--input-file", help="Input Excel file path (for excel input)")
    parser.add_argument("--input-sheet-url", 
                       default=DEFAULT_INPUT_SHEET_URL,
                       help=f"Input Google Sheet URL (default: preset URL in file)")
    parser.add_argument("--credentials", default=DEFAULT_CREDENTIALS_PATH,
                       help=f"Path to Google service account credentials file (default: {DEFAULT_CREDENTIALS_PATH})")
    
    # Output configuration
    parser.add_argument("--output-type", choices=['excel', 'google_sheets'], 
                       default='google_sheets',
                       help="Output destination type (default: google_sheets)")
    parser.add_argument("--output-file", help="Output Excel file path (for excel output)")
    parser.add_argument("--output-sheet-url", 
                       default=DEFAULT_OUTPUT_SHEET_URL,
                       help="Output Google Sheet URL (default: preset URL in file)")
    
    # Scheduling parameters
    parser.add_argument("--time-limit", type=float, default=90.0,
                       help="Time limit for solving in seconds (default: 90)")
    parser.add_argument("--debug-shift", help="Debug specific shift: YYYY/MM/DD,班別,崗位")
    parser.add_argument("--log-level", default="INFO", choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       help="Logging level (default: INFO)")
    
    args = parser.parse_args()
    
    # Validate input configuration
    if args.input_type == 'excel':
        if not args.input_file:
            print("Error: --input-file is required for excel input type")
            sys.exit(1)
        input_config = {"file_path": args.input_file}
    elif args.input_type == 'google_sheets':
        # Use default URL if not provided
        input_sheet_url = args.input_sheet_url or DEFAULT_INPUT_SHEET_URL
        print(f"Using input Google Sheet URL: {input_sheet_url}")
        input_config = {
            "spreadsheet_url": input_sheet_url,
            "credentials_path": args.credentials
        }
    
    # Validate output configuration
    if args.output_type == 'excel':
        if not args.output_file:
            print("Error: --output-file is required for excel output type")
            sys.exit(1)
        output_config = {"output_path": args.output_file}
    elif args.output_type == 'google_sheets':
        # Use default URL if not provided
        output_sheet_url = args.output_sheet_url or DEFAULT_OUTPUT_SHEET_URL
        print(f"Using output Google Sheet URL: {output_sheet_url}")
        output_config = {
            "spreadsheet_url": output_sheet_url,
            "credentials_path": args.credentials
        }
    
    # Run the scheduling task
    result = run_schedule_task(
        input_source=args.input_type,
        input_config=input_config,
        output_destination=args.output_type,
        output_config=output_config,
        time_limit=args.time_limit,
        debug_shift=args.debug_shift,
        log_level=args.log_level
    )
    
    # Output result
    if result.get("error"):
        print(f"Error: {result['error']}")
        sys.exit(1)
    elif result.get("status") == "debug_complete":
        print("Debug analysis completed")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

