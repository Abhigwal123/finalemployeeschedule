"""
Integration module to bridge the original scheduling system with the SaaS backend
"""

import os
import sys
import shutil
from typing import Dict, Any, Optional
from pathlib import Path

# 🔧 CRITICAL: Setup Python path BEFORE any imports
# Refactor folder is now in backend/refactor
integration_file = Path(__file__).resolve()
backend_dir = integration_file.parent.parent.parent  # backend/
refactor_dir = backend_dir / "refactor"  # backend/refactor/
backend_dir_str = str(backend_dir.resolve())
refactor_dir_str = str(refactor_dir.resolve())

# CRITICAL: Pre-import google-auth BEFORE adding backend to sys.path
# This prevents our local refactor/ folder from shadowing the installed google-auth package
# We MUST do this while backend_dir is NOT in sys.path
_google_auth_preloaded = False

# Normalize paths for comparison (Windows vs Unix paths)
normalized_backend_dir = os.path.normpath(backend_dir_str)
normalized_paths = [os.path.normpath(p) for p in sys.path]
_backend_was_in_path = normalized_backend_dir in normalized_paths

if _backend_was_in_path:
    # Temporarily remove backend from sys.path to import google-auth
    idx = normalized_paths.index(normalized_backend_dir)
    sys.path.pop(idx)

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
    _google_auth_preloaded = True
except ImportError as e:
    # google-auth may not be installed - that's OK, will be imported when needed
    _google_auth_preloaded = False
    # Can't use logging here as it might not be imported yet
    print(f"[INTEGRATION] WARNING: Could not pre-import google-auth: {e}", file=sys.stderr)

# Restore backend to sys.path if it was there
if _backend_was_in_path:
    sys.path.insert(0, backend_dir_str)

# Remove any old app/ directory from sys.path if it exists (it can cause conflicts)
project_root = backend_dir.parent
old_app_dir = project_root / "app"
normalized_old_app_dir = os.path.normpath(str(old_app_dir))
normalized_paths = [os.path.normpath(p) for p in sys.path]
if normalized_old_app_dir in normalized_paths:
    idx = normalized_paths.index(normalized_old_app_dir)
    sys.path.pop(idx)

# Refactor folder is now in backend/refactor
if not refactor_dir.exists():
    # Try Docker paths
    docker_refactor_dir = Path("/app/backend/refactor")
    if docker_refactor_dir.exists():
        refactor_dir = docker_refactor_dir
        refactor_dir_str = str(refactor_dir)

# CRITICAL: Remove refactor_dir from sys.path if it exists (it breaks package imports)
normalized_refactor_dir = os.path.normpath(refactor_dir_str)
normalized_paths = [os.path.normpath(p) for p in sys.path]
if normalized_refactor_dir in normalized_paths:
    idx = normalized_paths.index(normalized_refactor_dir)
    sys.path.pop(idx)

# Add backend to sys.path (refactor is already in backend/)
# Note: google-auth is already in sys.modules, so it won't be shadowed
normalized_paths = [os.path.normpath(p) for p in sys.path]
if normalized_backend_dir not in normalized_paths:
    sys.path.insert(0, backend_dir_str)

# Now we can safely import logging
import logging

# Log path setup for debugging
logger = logging.getLogger(__name__)
logger.info(f"[INTEGRATION] Backend dir: {backend_dir_str}")
logger.info(f"[INTEGRATION] Refactor package location: {refactor_dir_str}")
logger.info(f"[INTEGRATION] sys.path[0:3]: {sys.path[0:3]}")
if _google_auth_preloaded:
    logger.info(f"[INTEGRATION] ✅ google-auth pre-loaded to avoid conflicts")
logger.info(f"[INTEGRATION] ✅ Refactor added to sys.path - 'from refactor.*' imports should work")

# Now import with explicit error handling - Make it resilient so app can still run
run_schedule_task = None
setup_logging = None
get_logger = None

try:
    # Import run_refactored from backend (file has been moved to backend/)
    logger.info(f"[INTEGRATION] Attempting to import run_refactored from backend...")
    logger.info(f"[INTEGRATION] Backend dir: {backend_dir_str}")
    logger.info(f"[INTEGRATION] Checking if run_refactored.py exists...")
    
    run_refactored_path = backend_dir / "run_refactored.py"
    if run_refactored_path.exists():
        logger.info(f"[INTEGRATION] ✅ run_refactored.py found at: {run_refactored_path}")
    else:
        logger.error(f"[INTEGRATION] ❌ run_refactored.py NOT FOUND at: {run_refactored_path}")
        raise ImportError(f"run_refactored.py not found at {run_refactored_path}")
    
    # Add backend to sys.path if not already there (for importing backend.run_refactored)
    backend_dir_str = str(backend_dir)
    if backend_dir_str not in sys.path:
        sys.path.insert(0, backend_dir_str)
        logger.info(f"[INTEGRATION] Added backend to sys.path: {backend_dir_str}")
    
    logger.info(f"[INTEGRATION] Importing run_schedule_task from run_refactored...")
    from run_refactored import run_schedule_task
    logger.info(f"[INTEGRATION] ✅ Successfully imported run_schedule_task from backend.run_refactored")
    logger.info(f"[INTEGRATION] run_schedule_task type: {type(run_schedule_task)}")
except ImportError as e:
    import traceback
    error_trace = traceback.format_exc()
    logger.error(f"[INTEGRATION] ❌ FAILED to import run_refactored: {e}")
    logger.error(f"[INTEGRATION] Import error traceback:\n{error_trace}")
    logger.error(f"[INTEGRATION] Current sys.path: {sys.path[:5]}")
    logger.error(f"[INTEGRATION] Backend dir exists: {backend_dir.exists()}")
    logger.error(f"[INTEGRATION] Refactor dir exists: {refactor_dir.exists()}")
    logger.warning(f"[INTEGRATION] Scheduling features will be limited - app will continue without run_refactored")
    # Don't raise - allow app to continue, but scheduling features won't work
    run_schedule_task = None
except Exception as e:
    import traceback
    error_trace = traceback.format_exc()
    logger.error(f"[INTEGRATION] ❌ UNEXPECTED ERROR importing run_refactored: {e}")
    logger.error(f"[INTEGRATION] Error type: {type(e).__name__}")
    logger.error(f"[INTEGRATION] Error traceback:\n{error_trace}")
    run_schedule_task = None

try:
    # Import refactor modules (now in backend/refactor)
    logger.info(f"[INTEGRATION] Attempting to import refactor.* modules...")
    
    # Import refactor.utils.logger
    refactor_logger_path = refactor_dir / "utils" / "logger.py"
    if refactor_logger_path.exists():
        import importlib.util
        spec = importlib.util.spec_from_file_location("refactor_utils_logger", str(refactor_logger_path))
        if spec and spec.loader:
            refactor_logger_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(refactor_logger_module)
            setup_logging = refactor_logger_module.setup_logging
            get_logger = refactor_logger_module.get_logger
        else:
            raise ImportError(f"Could not load refactor logger from {refactor_logger_path}")
    else:
        raise ImportError(f"Refactor logger not found at {refactor_logger_path}")
    
    # Import other refactor modules - these are available from run_refactored which was already imported
    # We don't need to import them here since run_schedule_task from run_refactored handles everything
    # But we keep the imports for backward compatibility and in case they're needed directly
    try:
        from refactor.data_provider import create_data_provider
        from refactor.data_writer import create_data_writer, write_all_results_to_excel, write_all_results_to_google_sheets
        from refactor.schedule_cpsat import process_input_data, solve_cpsat
        from refactor.schedule_helpers import (
            build_rows, build_daily_analysis_report, check_hard_constraints, 
            check_soft_constraints, generate_soft_constraint_report, 
            create_schedule_chart, debug_schedule
        )
    except ImportError as import_err:
        # These imports may fail, but that's OK because run_schedule_task from run_refactored handles them
        logger.warning(f"[INTEGRATION] Could not import some refactor modules directly: {import_err}")
        logger.warning(f"[INTEGRATION] This is OK - run_schedule_task from run_refactored will handle them")
        # Set to None so code can check if they're available
        create_data_provider = None
        create_data_writer = None
        write_all_results_to_excel = None
        write_all_results_to_google_sheets = None
        process_input_data = None
        solve_cpsat = None
        build_rows = None
        build_daily_analysis_report = None
        check_hard_constraints = None
        check_soft_constraints = None
        generate_soft_constraint_report = None
        create_schedule_chart = None
        debug_schedule = None
    
    logger.info(f"[INTEGRATION] ✅ Successfully imported refactor logger modules")
except ImportError as e:
    logger.error(f"[INTEGRATION] ❌ FAILED to import refactor.* modules: {e}")
    logger.error(f"[INTEGRATION] Refactor dir exists: {Path(refactor_dir_str).exists()}")
    logger.error(f"[INTEGRATION] Refactor dir contents: {list(Path(refactor_dir_str).iterdir())[:10] if Path(refactor_dir_str).exists() else 'N/A'}")
    logger.warning(f"[INTEGRATION] Refactor modules import failed - some features may be limited")
    # Set defaults to None so code can check availability
    setup_logging = None
    get_logger = None
    # Don't raise - allow app to continue, but Google Sheets features won't work


def run_scheduling_task_saas(
    input_source: str,
    input_config: Dict[str, Any],
    output_destination: str,
    output_config: Dict[str, Any],
    time_limit: float = 90.0,
    debug_shift: Optional[str] = None,
    log_level: str = "INFO",
    user_id: Optional[int] = None,
    task_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Run scheduling task with SaaS-specific modifications
    
    Args:
        input_source: 'excel' or 'google_sheets'
        input_config: Configuration for input source
        output_destination: 'excel' or 'google_sheets'
        output_config: Configuration for output destination
        time_limit: Time limit for solving in seconds
        debug_shift: Optional debug shift in format "YYYY/MM/DD,班別,崗位"
        log_level: Logging level
        user_id: User ID for file organization
        task_id: Task ID for file organization
    
    Returns:
        Dictionary containing results and status
    """
    
    # Check if run_schedule_task is available
    if run_schedule_task is None:
        error_msg = "Scheduling system not available - run_refactored module could not be imported"
        logger.error(f"[INTEGRATION] {error_msg}")
        return {"error": error_msg, "status": "error"}
    
    # Setup logging (use standard logging if refactor logger not available)
    if setup_logging and get_logger:
        setup_logging(level=log_level)
        logger = get_logger(__name__)
    else:
        import logging
        logging.basicConfig(level=getattr(logging, log_level.upper(), logging.INFO))
        logger = logging.getLogger(__name__)
        logger.warning("[INTEGRATION] Using standard logging - refactor logger not available")
    
    logger.info(f"Starting SaaS scheduling task for user {user_id}, task {task_id}")
    
    try:
        # Create user-specific directories
        if user_id and task_id:
            user_dir = f"uploads/{user_id}"
            task_dir = f"{user_dir}/{task_id}"
            os.makedirs(task_dir, exist_ok=True)
            
            # Update file paths to be user/task specific
            if input_source == "excel" and "file_path" in input_config:
                original_path = input_config["file_path"]
                filename = os.path.basename(original_path)
                new_path = f"{task_dir}/input_{filename}"
                shutil.copy2(original_path, new_path)
                input_config = input_config.copy()
                input_config["file_path"] = new_path
            
            if output_destination == "excel" and "output_path" in output_config:
                original_path = output_config["output_path"]
                filename = os.path.basename(original_path)
                new_path = f"{task_dir}/output_{filename}"
                output_config = output_config.copy()
                output_config["output_path"] = new_path
        
        # Run the original scheduling task (run_refactored.py)
        logger.info(f"[INTEGRATION] 🔄 Calling run_schedule_task from run_refactored.py...")
        logger.info(f"[INTEGRATION] Input: {input_source}, Output: {output_destination}")
        logger.info(f"[INTEGRATION] Input URL: {input_config.get('spreadsheet_url', 'N/A')}")
        logger.info(f"[INTEGRATION] Output URL: {output_config.get('spreadsheet_url', 'N/A')}")
        
        result = run_schedule_task(
            input_source=input_source,
            input_config=input_config,
            output_destination=output_destination,
            output_config=output_config,
            time_limit=time_limit,
            debug_shift=debug_shift,
            log_level=log_level
        )
        
        logger.info(f"[INTEGRATION] ✅ run_schedule_task completed")
        logger.info(f"[INTEGRATION] Result type: {type(result)}")
        logger.info(f"[INTEGRATION] Result has error: {bool(result.get('error') if isinstance(result, dict) else False)}")
        
        # Add SaaS-specific metadata
        if isinstance(result, dict) and "error" not in result:
            result["user_id"] = user_id
            result["task_id"] = task_id
            result["saas_version"] = "2.0.0"
        
        logger.info(f"[INTEGRATION] ✅ SaaS scheduling task completed for user {user_id}, task {task_id}")
        return result
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"[INTEGRATION] ❌ Error in SaaS scheduling task: {e}")
        logger.error(f"[INTEGRATION] Error traceback: {error_trace}")
        return {"error": str(e), "status": "error"}


def validate_input_config(input_source: str, input_config: Dict[str, Any]) -> bool:
    """
    Validate input configuration
    
    Args:
        input_source: Input source type
        input_config: Input configuration
    
    Returns:
        True if valid, False otherwise
    """
    if input_source == "excel":
        if "file_path" not in input_config:
            return False
        if not os.path.exists(input_config["file_path"]):
            return False
    elif input_source == "google_sheets":
        if "spreadsheet_url" not in input_config:
            return False
        # Basic URL validation
        url = input_config["spreadsheet_url"]
        if not url.startswith("https://docs.google.com/spreadsheets/"):
            return False
    else:
        return False
    
    return True


def validate_output_config(output_destination: str, output_config: Dict[str, Any]) -> bool:
    """
    Validate output configuration
    
    Args:
        output_destination: Output destination type
        output_config: Output configuration
    
    Returns:
        True if valid, False otherwise
    """
    if output_destination == "excel":
        if "output_path" not in output_config:
            return False
    elif output_destination == "google_sheets":
        if "spreadsheet_url" not in output_config:
            return False
        # Basic URL validation
        url = output_config["spreadsheet_url"]
        if not url.startswith("https://docs.google.com/spreadsheets/"):
            return False
    else:
        return False
    
    return True


def cleanup_task_files(user_id: int, task_id: str) -> bool:
    """
    Clean up task-specific files
    
    Args:
        user_id: User ID
        task_id: Task ID
    
    Returns:
        True if cleanup successful, False otherwise
    """
    try:
        task_dir = f"uploads/{user_id}/{task_id}"
        if os.path.exists(task_dir):
            shutil.rmtree(task_dir)
        return True
    except Exception as e:
        print(f"Error cleaning up task files: {e}")
        return False
