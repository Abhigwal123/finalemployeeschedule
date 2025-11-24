"""
Integration module to bridge the original scheduling system with the SaaS backend
"""

import os
import sys
import shutil
import logging
from typing import Dict, Any, Optional
from pathlib import Path

# 🔧 CRITICAL: Setup Python path BEFORE any imports
# Calculate project root: backend/app/scheduling/integration.py -> project root
integration_file = Path(__file__).resolve()
backend_dir = integration_file.parent.parent.parent  # backend/
project_root = backend_dir.parent  # project root (parent of backend/)

# In Docker: ./backend -> /app/backend, ./app -> /app/legacy_app
# Check for legacy_app mount first (Docker), then fall back to app (local dev)
legacy_app_dir = project_root / "legacy_app"
app_dir = project_root / "app"
if legacy_app_dir.exists():
    app_dir = legacy_app_dir
    app_dir_str = str(app_dir)
elif app_dir.exists():
    app_dir_str = str(app_dir)
else:
    # Try Docker paths
    legacy_app_dir = Path("/app/legacy_app")
    if legacy_app_dir.exists():
        app_dir = legacy_app_dir
        app_dir_str = str(app_dir)
    else:
        app_dir_str = str(app_dir)

# CRITICAL: Remove app_dir from sys.path if it exists (it breaks package imports)
if app_dir_str in sys.path:
    sys.path.remove(app_dir_str)

# Add both backend and legacy_app to sys.path
backend_dir_str = str(backend_dir)
if backend_dir_str not in sys.path:
    sys.path.insert(0, backend_dir_str)
    
# Add legacy_app to sys.path for "from legacy_app.*" imports
if app_dir_str not in sys.path:
    sys.path.insert(0, app_dir_str)

# Log path setup for debugging
logger = logging.getLogger(__name__)
project_root_str = str(project_root)
logger.info(f"[INTEGRATION] Project root: {project_root_str}")
logger.info(f"[INTEGRATION] Legacy app package location: {app_dir_str}")
logger.info(f"[INTEGRATION] sys.path[0:3]: {sys.path[0:3]}")
logger.info(f"[INTEGRATION] ✅ Legacy app added to sys.path - 'from legacy_app.*' imports should work")

# Now import with explicit error handling - DO NOT hide ImportError
try:
    # Import run_refactored from backend (file has been moved to backend/)
    logger.info(f"[INTEGRATION] Attempting to import run_refactored from backend...")
    # Add backend to sys.path if not already there (for importing backend.run_refactored)
    backend_dir_str = str(backend_dir)
    if backend_dir_str not in sys.path:
        sys.path.insert(0, backend_dir_str)
    from run_refactored import run_schedule_task
    logger.info(f"[INTEGRATION] ✅ Successfully imported run_schedule_task from backend.run_refactored")
except ImportError as e:
    logger.error(f"[INTEGRATION] ❌ FAILED to import run_refactored: {e}")
    logger.error(f"[INTEGRATION] Current sys.path: {sys.path[:5]}")
    raise ImportError(f"Cannot import run_refactored from backend. Backend dir: {backend_dir_str}, Error: {e}")

try:
    # Import legacy app modules
    # NOTE: We need to import root app modules directly using importlib because after run_refactored
    # restores the backend app in sys.modules, direct imports would find backend modules instead
    logger.info(f"[INTEGRATION] Attempting to import legacy_app.* modules...")
    import importlib.util
    
    # Import root app.utils.logger directly from file path to avoid backend app conflict
    root_logger_path = Path(app_dir_str) / "utils" / "logger.py"
    if root_logger_path.exists():
        spec = importlib.util.spec_from_file_location("root_app_utils_logger", str(root_logger_path))
        if spec and spec.loader:
            root_logger_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(root_logger_module)
            setup_logging = root_logger_module.setup_logging
            get_logger = root_logger_module.get_logger
        else:
            raise ImportError(f"Could not load root app logger from {root_logger_path}")
    else:
        raise ImportError(f"Root app logger not found at {root_logger_path}")
    
    # Import other root app modules - these are available from run_refactored which was already imported
    # We don't need to import them here since run_schedule_task from run_refactored handles everything
    # But we keep the imports for backward compatibility and in case they're needed directly
    try:
        from legacy_app.data_provider import create_data_provider
        from legacy_app.data_writer import create_data_writer, write_all_results_to_excel, write_all_results_to_google_sheets
        from legacy_app.schedule_cpsat import process_input_data, solve_cpsat
        from legacy_app.schedule_helpers import (
            build_rows, build_daily_analysis_report, check_hard_constraints, 
            check_soft_constraints, generate_soft_constraint_report, 
            create_schedule_chart, debug_schedule
        )
    except ImportError as import_err:
        # These imports may fail if backend app is in sys.modules, but that's OK
        # because run_schedule_task from run_refactored already has access to them
        logger.warning(f"[INTEGRATION] Could not import some root app modules directly: {import_err}")
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
    
    logger.info(f"[INTEGRATION] ✅ Successfully imported root app logger modules")
except ImportError as e:
    logger.error(f"[INTEGRATION] ❌ FAILED to import legacy_app.* modules: {e}")
    logger.error(f"[INTEGRATION] Legacy app dir exists: {Path(app_dir_str).exists()}")
    logger.error(f"[INTEGRATION] Legacy app dir contents: {list(Path(app_dir_str).iterdir())[:10] if Path(app_dir_str).exists() else 'N/A'}")
    raise ImportError(f"Cannot import legacy_app.* modules. Legacy app dir: {app_dir_str}, Error: {e}")


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
    
    # Setup logging
    setup_logging(level=log_level)
    logger = get_logger(__name__)
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
