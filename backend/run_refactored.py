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

# 🔧 CRITICAL: Setup Python path BEFORE importing refactor.* modules
# Refactor folder is now in backend/refactor
# NOTE: This file is now in backend/, so script_dir is backend/
script_dir = os.path.dirname(os.path.abspath(__file__))  # This IS the backend directory
project_root = os.path.dirname(script_dir)  # Project root (parent of backend/)
# Refactor folder is now in backend/refactor
refactor_dir = os.path.abspath(os.path.join(script_dir, "refactor"))
if not os.path.exists(refactor_dir):
    # Try Docker paths
    docker_refactor_dir = "/app/backend/refactor"
    if os.path.exists(docker_refactor_dir):
        refactor_dir = docker_refactor_dir
backend_dir = script_dir  # We're now inside backend/

# CRITICAL: Pre-import google-auth BEFORE adding backend to sys.path
# If backend/ is already in sys.path (from integration.py or main.py), temporarily remove it
# This prevents our local refactor/ folder from shadowing the installed google-auth package
normalized_backend_dir = os.path.normpath(backend_dir)
normalized_refactor_dir = os.path.normpath(refactor_dir)
normalized_paths = [os.path.normpath(p) for p in sys.path]

# Also check for current directory '.' which might be backend/
current_dir = os.path.normpath(os.getcwd())
_backend_was_in_path = normalized_backend_dir in normalized_paths or current_dir == normalized_backend_dir
_refactor_dir_was_in_path = normalized_refactor_dir in normalized_paths

# Remove both backend_dir and refactor_dir from sys.path before pre-importing
# Remove in reverse order to avoid index shifting issues
paths_to_remove = []
for i, path in enumerate(sys.path):
    norm_path = os.path.normpath(path)
    if norm_path == normalized_refactor_dir:
        paths_to_remove.append(i)
    elif norm_path == normalized_backend_dir or (path == '.' and current_dir == normalized_backend_dir):
        paths_to_remove.append(i)

# Remove from end to beginning to avoid index shifting
for i in sorted(paths_to_remove, reverse=True):
    sys.path.pop(i)

_pre_imported_google_auth = False
# Check if google-auth is already in sys.modules (pre-imported by integration.py)
if 'google.auth' in sys.modules:
    _pre_imported_google_auth = True
else:
    try:
        # Import google-auth and all its submodules BEFORE backend is in sys.path
        # This ensures they're loaded into sys.modules and won't be shadowed
        import google.auth
        import google.auth.credentials
        import google.auth.transport
        import google.auth.transport.requests
        import google.oauth2
        import google.oauth2.service_account
        import google.oauth2.credentials
        # Also pre-import gspread which depends on google.auth
        import gspread
        # Mark as successfully pre-imported
        _pre_imported_google_auth = True
    except ImportError as e:
        # google-auth may not be installed - that's OK, will be imported when needed
        # But we need to handle the case where gspread tries to import it
        _pre_imported_google_auth = False
        import logging
        logging.basicConfig(level=logging.WARNING)
        _temp_logger = logging.getLogger(__name__)
        _temp_logger.warning(f"[RUN_REFACTORED] Could not pre-import google-auth: {e}")

# CRITICAL: Setup sys.path for backend (refactor is already in backend/)
# Add backend first so backend.app takes precedence
# Note: google-auth is already in sys.modules, so it won't be shadowed
# CRITICAL: Do NOT add refactor_dir to sys.path - it will shadow google-auth
normalized_paths = [os.path.normpath(p) for p in sys.path]
if normalized_backend_dir not in normalized_paths:
    sys.path.insert(0, backend_dir)
elif _backend_was_in_path:
    # Restore backend to sys.path (it was temporarily removed)
    sys.path.insert(0, backend_dir)

# Ensure refactor_dir is NOT in sys.path (it would shadow google-auth)
normalized_paths = [os.path.normpath(p) for p in sys.path]
if normalized_refactor_dir in normalized_paths:
    idx = normalized_paths.index(normalized_refactor_dir)
    sys.path.pop(idx)

# Log path setup for debugging
import logging
logging.basicConfig(level=logging.INFO)
_path_logger = logging.getLogger(__name__)
_path_logger.info(f"[RUN_REFACTORED] Script dir (backend): {script_dir}")
_path_logger.info(f"[RUN_REFACTORED] Project root: {project_root}")
_path_logger.info(f"[RUN_REFACTORED] Refactor package location: {refactor_dir}")
_path_logger.info(f"[RUN_REFACTORED] sys.path[0:3]: {sys.path[0:3]}")
_path_logger.info(f"[RUN_REFACTORED] ✅ Refactor in sys.path - 'from refactor.*' imports should work")

# Google Sheets URLs - MUST be set via environment variables (no hardcoded defaults)
# Credentials are in project root, not backend/
DEFAULT_CREDENTIALS_PATH = os.path.join(project_root, "service-account-creds.json")
os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", DEFAULT_CREDENTIALS_PATH)

# Import our refactored modules - Use absolute imports
# These imports will fail with explicit error if modules not found (no try/except)
_path_logger.info(f"[RUN_REFACTORED] Attempting to import refactor.* modules...")

# Import our local google modules using importlib to avoid package conflicts
# CRITICAL: Temporarily remove backend from sys.path when loading modules
# This ensures google-auth can be imported by gspread without conflicts
try:
    import importlib.util
    import types
    
    # Temporarily remove backend and refactor_dir from sys.path to allow google-auth imports
    # Normalize paths for comparison (Windows vs Unix paths)
    _backend_removed_for_import = False
    _refactor_dir_removed_for_import = False
    normalized_backend_dir = os.path.normpath(backend_dir)
    normalized_refactor_dir = os.path.normpath(refactor_dir)
    normalized_paths = [os.path.normpath(p) for p in sys.path]
    
    # Remove refactor_dir first (if present)
    if normalized_refactor_dir in normalized_paths:
        idx = normalized_paths.index(normalized_refactor_dir)
        sys.path.pop(idx)
        normalized_paths.pop(idx)  # Update our tracking list
        _refactor_dir_removed_for_import = True
        _path_logger.info(f"[RUN_REFACTORED] Removed refactor_dir from sys.path for module execution")
    
    # Remove backend_dir (if present)
    if normalized_backend_dir in normalized_paths:
        idx = normalized_paths.index(normalized_backend_dir)
        sys.path.pop(idx)
        _backend_removed_for_import = True
        _path_logger.info(f"[RUN_REFACTORED] Removed backend_dir from sys.path for module execution")
    
    try:
        # Ensure google-auth and gspread are in sys.modules before loading our modules
        # (gspread will need google.auth when our modules import it)
        if 'google.auth' not in sys.modules:
            try:
                import google.auth
                import google.auth.credentials
                import google.oauth2.service_account
            except ImportError:
                pass  # Will fail later if needed
        
        # Pre-import gspread to ensure it can find google.auth
        # This must happen while backend_dir is NOT in sys.path
        if 'gspread' not in sys.modules:
            try:
                import gspread
                _path_logger.info(f"[RUN_REFACTORED] ✅ Pre-imported gspread successfully")
            except ImportError as e:
                _path_logger.warning(f"[RUN_REFACTORED] Could not pre-import gspread: {e}")
                # Continue anyway - will fail later if needed
        
        # Verify setup before executing modules
        _path_logger.info(f"[RUN_REFACTORED] Verifying setup: google.auth in sys.modules={('google.auth' in sys.modules)}, backend_dir in sys.path={backend_dir in sys.path}")
        
        # CRITICAL: Set up the refactor package namespace for relative imports
        # Create a refactor package module if it doesn't exist
        if 'refactor' not in sys.modules:
            refactor_package = types.ModuleType('refactor')
            refactor_package.__path__ = [str(refactor_dir)]
            sys.modules['refactor'] = refactor_package
        else:
            refactor_package = sys.modules['refactor']
        
        # Create refactor.utils package for logger
        if 'refactor.utils' not in sys.modules:
            refactor_utils_package = types.ModuleType('refactor.utils')
            refactor_utils_package.__path__ = [str(os.path.join(refactor_dir, 'utils'))]
            sys.modules['refactor.utils'] = refactor_utils_package
            refactor_package.utils = refactor_utils_package
        else:
            refactor_utils_package = sys.modules['refactor.utils']
        
        # Load modules directly from files and add to sys.modules for relative imports
        # Load logger FIRST (schedule_cpsat imports from .utils.logger)
        logger_path = os.path.join(refactor_dir, "utils", "logger.py")
        spec = importlib.util.spec_from_file_location("refactor.utils.logger", logger_path)
        logger_module = importlib.util.module_from_spec(spec)
        logger_module.__package__ = 'refactor.utils'
        logger_module.__name__ = 'refactor.utils.logger'
        sys.modules['refactor.utils.logger'] = logger_module
        refactor_utils_package.logger = logger_module
        spec.loader.exec_module(logger_module)
        setup_logging = logger_module.setup_logging
        get_logger = logger_module.get_logger
        
        # Load data_provider (schedule_cpsat imports from .data_provider)
        data_provider_path = os.path.join(refactor_dir, "data_provider.py")
        spec = importlib.util.spec_from_file_location("refactor.data_provider", data_provider_path)
        data_provider_module = importlib.util.module_from_spec(spec)
        data_provider_module.__package__ = 'refactor'
        data_provider_module.__name__ = 'refactor.data_provider'
        # Add google-auth to module's namespace so gspread can find it
        if 'google.auth' in sys.modules:
            data_provider_module.__dict__['refactor'] = refactor_package
            data_provider_module.__dict__['refactor'].auth = sys.modules['google.auth']
            data_provider_module.__dict__['refactor'].oauth2 = sys.modules.get('google.oauth2', types.ModuleType('google.oauth2'))
        sys.modules['refactor.data_provider'] = data_provider_module
        refactor_package.data_provider = data_provider_module
        spec.loader.exec_module(data_provider_module)
        create_data_provider = data_provider_module.create_data_provider
        
        # Load data_writer
        data_writer_path = os.path.join(refactor_dir, "data_writer.py")
        spec = importlib.util.spec_from_file_location("refactor.data_writer", data_writer_path)
        data_writer_module = importlib.util.module_from_spec(spec)
        data_writer_module.__package__ = 'refactor'
        data_writer_module.__name__ = 'refactor.data_writer'
        if 'google.auth' in sys.modules:
            data_writer_module.__dict__['refactor'] = refactor_package
            data_writer_module.__dict__['refactor'].auth = sys.modules['google.auth']
            data_writer_module.__dict__['refactor'].oauth2 = sys.modules.get('google.oauth2', types.ModuleType('google.oauth2'))
        sys.modules['refactor.data_writer'] = data_writer_module
        refactor_package.data_writer = data_writer_module
        spec.loader.exec_module(data_writer_module)
        create_data_writer = data_writer_module.create_data_writer
        write_all_results_to_excel = data_writer_module.write_all_results_to_excel
        write_all_results_to_google_sheets = data_writer_module.write_all_results_to_google_sheets
        
        # Load schedule_cpsat (needs data_provider and utils.logger)
        schedule_cpsat_path = os.path.join(refactor_dir, "schedule_cpsat.py")
        spec = importlib.util.spec_from_file_location("refactor.schedule_cpsat", schedule_cpsat_path)
        schedule_cpsat_module = importlib.util.module_from_spec(spec)
        schedule_cpsat_module.__package__ = 'refactor'
        schedule_cpsat_module.__name__ = 'refactor.schedule_cpsat'
        # Make sure parent package is available for relative imports
        schedule_cpsat_module.__dict__['refactor'] = refactor_package
        sys.modules['refactor.schedule_cpsat'] = schedule_cpsat_module
        refactor_package.schedule_cpsat = schedule_cpsat_module
        spec.loader.exec_module(schedule_cpsat_module)
        process_input_data = schedule_cpsat_module.process_input_data
        solve_cpsat = schedule_cpsat_module.solve_cpsat
        
        # Load schedule_helpers (needs schedule_cpsat)
        schedule_helpers_path = os.path.join(refactor_dir, "schedule_helpers.py")
        spec = importlib.util.spec_from_file_location("refactor.schedule_helpers", schedule_helpers_path)
        schedule_helpers_module = importlib.util.module_from_spec(spec)
        schedule_helpers_module.__package__ = 'refactor'
        schedule_helpers_module.__name__ = 'refactor.schedule_helpers'
        schedule_helpers_module.__dict__['refactor'] = refactor_package
        sys.modules['refactor.schedule_helpers'] = schedule_helpers_module
        refactor_package.schedule_helpers = schedule_helpers_module
        spec.loader.exec_module(schedule_helpers_module)
        build_rows = schedule_helpers_module.build_rows
        build_daily_analysis_report = schedule_helpers_module.build_daily_analysis_report
        check_hard_constraints = schedule_helpers_module.check_hard_constraints
        check_soft_constraints = schedule_helpers_module.check_soft_constraints
        generate_soft_constraint_report = schedule_helpers_module.generate_soft_constraint_report
        create_schedule_chart = schedule_helpers_module.create_schedule_chart
        debug_schedule = schedule_helpers_module.debug_schedule
        
    finally:
        # Restore backend to sys.path (refactor_dir should NOT be in sys.path)
        if _backend_removed_for_import and backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)
    
    _path_logger.info(f"[RUN_REFACTORED] ✅ Successfully imported all refactor.* modules using importlib")
    if _pre_imported_google_auth or 'google.auth' in sys.modules:
        _path_logger.info(f"[RUN_REFACTORED] ✅ google-auth package available for gspread")
except Exception as e:
    # Restore backend to sys.path even on error (refactor_dir should NOT be restored)
    if '_backend_removed_for_import' in locals() and _backend_removed_for_import and backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)
    _path_logger.error(f"[RUN_REFACTORED] ❌ FAILED to import refactor.* modules: {e}")
    _path_logger.error(f"[RUN_REFACTORED] Refactor dir exists: {os.path.exists(refactor_dir)}")
    _path_logger.error(f"[RUN_REFACTORED] Refactor dir contents: {os.listdir(refactor_dir)[:10] if os.path.exists(refactor_dir) else 'N/A'}")
    _path_logger.error(f"[RUN_REFACTORED] sys.path: {sys.path[:5]}")
    import traceback
    _path_logger.error(f"[RUN_REFACTORED] Traceback: {traceback.format_exc()}")
    raise ImportError(f"Cannot import refactor.* modules. Refactor dir: {refactor_dir}, Error: {e}")

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
                    from refactor.schedule_helpers import generate_gap_analysis_report
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
                       default=None,
                       help="Input Google Sheet URL (required - set via GOOGLE_INPUT_URL env var or this argument)")
    parser.add_argument("--credentials", default=DEFAULT_CREDENTIALS_PATH,
                       help=f"Path to Google service account credentials file (default: {DEFAULT_CREDENTIALS_PATH})")
    
    # Output configuration
    parser.add_argument("--output-type", choices=['excel', 'google_sheets'], 
                       default='google_sheets',
                       help="Output destination type (default: google_sheets)")
    parser.add_argument("--output-file", help="Output Excel file path (for excel output)")
    parser.add_argument("--output-sheet-url", 
                       default=None,
                       help="Output Google Sheet URL (required - set via GOOGLE_OUTPUT_URL env var or this argument)")
    
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
        # Use ENV variable or argument - no hardcoded defaults
        input_sheet_url = args.input_sheet_url or os.getenv("GOOGLE_INPUT_URL")
        if not input_sheet_url:
            print("Error: --input-sheet-url is required or set GOOGLE_INPUT_URL environment variable")
            sys.exit(1)
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
        # Use ENV variable or argument - no hardcoded defaults
        output_sheet_url = args.output_sheet_url or os.getenv("GOOGLE_OUTPUT_URL")
        if not output_sheet_url:
            print("Error: --output-sheet-url is required or set GOOGLE_OUTPUT_URL environment variable")
            sys.exit(1)
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

