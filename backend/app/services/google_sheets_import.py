"""
Google Sheets Service Import Utility
Provides safe dynamic import with multiple fallback paths and detailed logging
"""
import logging
import sys
import os
import importlib.util
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Import trace logger
try:
    from backend.app.utils.trace_logger import trace_log, trace_import_success, trace_import_failure
except ImportError:
    # Fallback if trace logger not available
    def trace_log(stage, filename, detail, extra=None):
        logger.info(f"[TRACE] Stage={stage} | File={filename} | Detail={detail}")
    
    def trace_import_success(module_name, import_path):
        trace_log('ImportSuccess', 'service_loader.py', f'Google Sheets loaded from {import_path}')
    
    def trace_import_failure(reason, attempts=0):
        trace_log('ImportFailFinal', 'service_loader.py', f'No valid module found: {reason}')

# Module-level state
SHEETS_AVAILABLE = False
fetch_schedule_data = None
GoogleSheetsService = None
list_sheets = None
validate_sheets = None
_import_attempted = False
_last_import_error = None

# CRITICAL: Ensure os is always available at module level
# This prevents any UnboundLocalError when this module is imported
import os as _os_module_safe
import sys as _sys_module_safe


def _wrap_fetch_schedule_data(original_fetch, os_module):
    """
    Wrap fetch_schedule_data to ensure os is always available.
    This prevents UnboundLocalError when the function is called.
    """
    if not original_fetch:
        return original_fetch
    
    _os_module_for_wrapper = os_module
    
    def safe_fetch_schedule_data_wrapper(*args, **kwargs):
        """Wrapper that ensures os is available before calling fetch_schedule_data"""
        # CRITICAL: Import os at function level FIRST to ensure it's always available
        import os as _os_import
        
        # CRITICAL: Ensure os is in the module's globals BEFORE calling the function
        if hasattr(original_fetch, '__module__'):
            module_name = original_fetch.__module__
            if module_name in sys.modules:
                module = sys.modules[module_name]
                # Always set os in module dict, even if it exists
                module.__dict__['os'] = _os_module_for_wrapper
                logger.debug(f"Ensured os is available in {module_name} before calling fetch_schedule_data")
        
        # CRITICAL: Also inject os into the function's __globals__ if it has one
        # This is the key fix - Python looks in __globals__ for global variables
        # When code is executed via exec(), __globals__ might be a separate dict
        if hasattr(original_fetch, '__globals__'):
            # CRITICAL: Make sure __globals__ points to the module's __dict__
            if hasattr(original_fetch, '__module__'):
                module_name = original_fetch.__module__
                if module_name in sys.modules:
                    module = sys.modules[module_name]
                    # Try to make __globals__ reference the module's __dict__
                    try:
                        # If __globals__ is a dict, update it
                        if isinstance(original_fetch.__globals__, dict):
                            original_fetch.__globals__['os'] = _os_module_for_wrapper
                            # Also try to make it reference the module dict
                            if module.__dict__ is not original_fetch.__globals__:
                                # Copy os to both
                                original_fetch.__globals__['os'] = _os_module_for_wrapper
                        else:
                            # If it's not a dict, try to set it
                            original_fetch.__globals__ = module.__dict__
                    except (TypeError, AttributeError):
                        # If we can't modify __globals__, at least set os in it if it's a dict
                        if isinstance(original_fetch.__globals__, dict):
                            original_fetch.__globals__['os'] = _os_module_for_wrapper
            else:
                # Fallback: just set os in __globals__ if it's a dict
                if isinstance(original_fetch.__globals__, dict):
                    original_fetch.__globals__['os'] = _os_module_for_wrapper
            logger.debug(f"Injected os into function __globals__")
        
        # CRITICAL: Also try to set it in __builtins__ if available
        if hasattr(original_fetch, '__builtins__'):
            if isinstance(original_fetch.__builtins__, dict):
                original_fetch.__builtins__['os'] = _os_module_for_wrapper
            elif hasattr(original_fetch.__builtins__, '__dict__'):
                original_fetch.__builtins__.__dict__['os'] = _os_module_for_wrapper
        
        try:
            return original_fetch(*args, **kwargs)
        except UnboundLocalError as e:
            if 'os' in str(e):
                logger.error(f"UnboundLocalError for 'os' in fetch_schedule_data: {e}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
                # Force os into ALL possible locations and retry
                if hasattr(original_fetch, '__module__'):
                    module_name = original_fetch.__module__
                    if module_name in sys.modules:
                        module = sys.modules[module_name]
                        module.__dict__['os'] = _os_module_for_wrapper
                
                # Force into function globals
                if hasattr(original_fetch, '__globals__'):
                    original_fetch.__globals__['os'] = _os_module_for_wrapper
                
                # Force into builtins
                if hasattr(original_fetch, '__builtins__'):
                    if isinstance(original_fetch.__builtins__, dict):
                        original_fetch.__builtins__['os'] = _os_module_for_wrapper
                
                logger.info(f"Fixed os in all locations, retrying fetch_schedule_data...")
                try:
                    return original_fetch(*args, **kwargs)
                except UnboundLocalError as retry_error:
                    logger.error(f"Retry also failed with UnboundLocalError: {retry_error}")
                    logger.error(f"This suggests the function's bytecode has os as a local variable")
                    # Last resort: try to call with os explicitly passed
                    raise
                raise
            else:
                raise
        except Exception as other_error:
            # Log other errors but don't try to fix them
            logger.error(f"Error in fetch_schedule_data (not UnboundLocalError): {other_error}")
            raise
    
    return safe_fetch_schedule_data_wrapper


def _try_import_google_sheets(force_retry: bool = False) -> Tuple[bool, Optional[str]]:
    """
    Try to import Google Sheets service with multiple fallback paths.
    
    Args:
        force_retry: If True, retry even if previous attempt failed
    
    Returns:
        Tuple of (success: bool, import_path: Optional[str])
    """
    global SHEETS_AVAILABLE, fetch_schedule_data, GoogleSheetsService, list_sheets, validate_sheets, _import_attempted, _last_import_error
    
    if SHEETS_AVAILABLE:
        return True, "already_loaded"
    
    if _import_attempted and not force_retry:
        logger.warning(f"Skipping import - previous attempt failed. Last error: {_last_import_error}")
        return False, f"previous_attempt_failed: {_last_import_error}"
    
    # Reset for retry
    if force_retry:
        _import_attempted = False
        _last_import_error = None
        logger.info("Force retry requested, resetting import state")
    
    _import_attempted = True
    
    # Calculate project root paths
    current_file = os.path.abspath(__file__)  # backend/app/services/google_sheets_import.py
    services_dir = os.path.dirname(current_file)  # backend/app/services
    app_dir = os.path.dirname(services_dir)  # backend/app
    backend_dir = os.path.dirname(app_dir)  # backend/
    project_root = os.path.dirname(backend_dir)  # Project_Up/
    
    # Normalize paths to handle Windows/Unix differences
    project_root = os.path.normpath(project_root)
    current_file = os.path.normpath(current_file)
    
    trace_log('Import', 'google_sheets_import.py', 'Starting Google Sheets import attempt')
    
    logger.info("=" * 80)
    logger.info("GOOGLE SHEETS SERVICE IMPORT CHECK")
    logger.info("=" * 80)
    logger.info(f"Current file: {current_file}")
    logger.info(f"Project root: {project_root}")
    logger.info(f"Project root normalized: {os.path.normpath(project_root)}")
    
    # Path to check - Refactor is now in backend/refactor
    backend_path = os.path.dirname(os.path.dirname(os.path.dirname(current_file)))  # backend/ directory
    
    # Log all paths we'll try
        # Priority: backend/refactor (current location)
    paths_to_try = [
        # Standard location: backend/refactor/services/google_sheets/service.py
        os.path.join(backend_path, 'refactor', 'services', 'google_sheets', 'service.py'),
        # Docker: alternative path
        '/app/backend/refactor/services/google_sheets/service.py',
        # Fallback: check if it's at project root level (old location)
        os.path.join(project_root, 'refactor', 'services', 'google_sheets', 'service.py'),
    ]
    
    # Filter out paths that are clearly wrong (same path repeated)
    unique_paths = []
    for p in paths_to_try:
        normalized = os.path.normpath(p)
        if normalized not in [os.path.normpath(up) for up in unique_paths]:
            unique_paths.append(p)
    paths_to_try = unique_paths
    
    # Find the first path that exists
    target_path = None
    for path in paths_to_try:
        if os.path.exists(path):
            target_path = path
            break
    
    if target_path:
        logger.info(f"Found target path: {target_path}")
        path_exists = True
    else:
        target_path = paths_to_try[0]  # Use first path for logging
        path_exists = False
    
    logger.info(f"Target path: {target_path}")
    logger.info(f"Path exists: {path_exists}")
    
    trace_log('Import', 'google_sheets_import.py', f'Checking path: {target_path} (exists: {path_exists})')
    
    # If we found a valid path, update backend_path to point to backend directory
    if target_path and path_exists:
        # Extract the backend path from the found path
        # e.g., /app/backend/refactor/services/google_sheets/service.py -> /app/backend
        path_parts = target_path.split(os.sep)
        if 'refactor' in path_parts:
            refactor_idx = path_parts.index('refactor')
            backend_path = os.sep.join(path_parts[:refactor_idx])
            logger.info(f"Updated backend_path to: {backend_path} (based on refactor folder location)")
        # Keep original backend_path if path structure doesn't match expected patterns
    
    logger.info("All paths checked:")
    for idx, p in enumerate(paths_to_try, 1):
        exists = os.path.exists(p)
        logger.info(f"  {idx}. {p} - Exists: {exists}")
        trace_log('Import', 'google_sheets_import.py', f'PathChecked={p} | Exists={exists}')
    
    # Import strategy 1: Direct import with project root in path
    try:
        logger.info("Attempt 1: Direct import from refactor.services.google_sheets.service")
        trace_log('Import', 'google_sheets_import.py', 'Attempt 1: Direct import from refactor.services.google_sheets.service')
        
        # Ensure backend_path is in sys.path (normalize both for comparison)
        normalized_paths = [os.path.normpath(p) for p in sys.path]
        normalized_backend_path = os.path.normpath(backend_path)
        
        if normalized_backend_path not in normalized_paths:
            sys.path.insert(0, backend_path)
            logger.info(f"Added to sys.path: {backend_path}")
        else:
            # Move to front if it's not first
            idx = normalized_paths.index(normalized_backend_path)
            if idx > 0:
                sys.path.insert(0, sys.path.pop(idx))
                logger.info(f"Moved backend_path from position {idx} to position 0")
        
        # Verify path is actually in sys.path
        logger.info(f"Current sys.path[0]: {sys.path[0]}")
        logger.info(f"Normalized sys.path[0]: {os.path.normpath(sys.path[0])}")
        logger.info(f"Backend path normalized: {normalized_backend_path}")
        logger.info(f"Match: {os.path.normpath(sys.path[0]) == normalized_backend_path}")
        
        # Verify the refactor package directory exists
        refactor_dir_check = os.path.join(backend_path, 'refactor')
        logger.info(f"refactor directory exists: {os.path.exists(refactor_dir_check)}")
        logger.info(f"refactor directory path: {refactor_dir_check}")
        
        # Verify __init__.py files exist
        refactor_init = os.path.join(backend_path, 'refactor', '__init__.py')
        services_init = os.path.join(backend_path, 'refactor', 'services', '__init__.py')
        sheets_init = os.path.join(backend_path, 'refactor', 'services', 'google_sheets', '__init__.py')
        
        logger.info(f"refactor/__init__.py exists: {os.path.exists(refactor_init)}")
        logger.info(f"refactor/services/__init__.py exists: {os.path.exists(services_init)}")
        logger.info(f"refactor/services/google_sheets/__init__.py exists: {os.path.exists(sheets_init)}")
        
        # Use regular import - backend_path is now in sys.path
        # This is the cleanest approach and will work if the path is correct
        logger.info("Attempting regular import with backend_path in sys.path")
        
        # Double-check backend_path is first in path
        if sys.path[0] != backend_path:
            sys.path.insert(0, backend_path)
            logger.info(f"Moved backend_path to first position in sys.path")
        
        # Use importlib to load directly from file - bypasses Python's module resolution
        # Use the target_path we found earlier, or construct from backend/refactor
        if target_path and path_exists:
            service_file_path = target_path
        else:
            # Fall back to standard path: backend/refactor/services/google_sheets/service.py
            service_file_path = os.path.join(backend_path, 'refactor', 'services', 'google_sheets', 'service.py')
        
        logger.info(f"Loading module directly from file: {service_file_path}")
        
        try:
            # Use compile + exec to load module directly (bypasses importlib's strict name checking)
            logger.info("Loading module using compile + exec...")
            
            # Read the file
            with open(service_file_path, 'r', encoding='utf-8') as f:
                source_code = f.read()
            
            # Create a module object
            import types
            # Use refactor package name (now in backend/refactor)
            module_name = "refactor.services.google_sheets.service"
            module_package = "refactor.services.google_sheets"
            module = types.ModuleType(module_name)
            module.__file__ = service_file_path
            module.__package__ = module_package
            
            # CRITICAL: Pre-populate module namespace with essential imports to avoid UnboundLocalError
            # This ensures os and other standard library modules are available before code execution
            # When exec() runs, Python needs these to be in the namespace to avoid "referenced before assignment" errors
            import os as os_module
            import sys as sys_module
            import logging as logging_module
            import time as time_module
            import types as types_module
            import re as re_module
            from typing import Dict, Any, Optional, List, Tuple
            
            # Try to import pandas (used by the service)
            try:
                import pandas as pd_module
                pandas_available = True
            except ImportError:
                pd_module = None
                pandas_available = False
                logger.warning("pandas not available - some functionality may be limited")
            
            # Add essential modules to namespace BEFORE executing code
            # This prevents UnboundLocalError when the executed code uses these modules
            module.__dict__['os'] = os_module
            module.__dict__['sys'] = sys_module
            module.__dict__['logging'] = logging_module
            module.__dict__['time'] = time_module
            module.__dict__['types'] = types_module
            module.__dict__['re'] = re_module
            module.__dict__['Dict'] = Dict
            module.__dict__['Any'] = Any
            module.__dict__['Optional'] = Optional
            module.__dict__['List'] = List
            module.__dict__['Tuple'] = Tuple
            if pandas_available:
                module.__dict__['pd'] = pd_module
                module.__dict__['pandas'] = pd_module
            
            # Temporarily add parent modules to sys.modules
            parent_modules = [
                'refactor',
                'refactor.services',
                'refactor.services.google_sheets'
            ]
            
            for mod_name in parent_modules:
                if mod_name not in sys.modules:
                    fake_module = types.ModuleType(mod_name)
                    mod_path = os.path.join(backend_path, *mod_name.split('.'))
                    if os.path.isdir(mod_path):
                        fake_module.__path__ = [mod_path]
                        fake_module.__file__ = os.path.join(mod_path, '__init__.py')
                    sys.modules[mod_name] = fake_module
                    logger.info(f"Created parent module: {mod_name}")
            
            # Add module to sys.modules before execution
            sys.modules["refactor.services.google_sheets.service"] = module
            
            # CRITICAL: Also add __builtins__ to ensure built-in functions are available
            # This prevents any issues with built-in functions during execution
            import builtins
            module.__dict__['__builtins__'] = builtins
            
            # CRITICAL: Pre-process source code to prevent import conflicts
            # Replace "import os" with a comment to prevent Python from trying to import os again
            # This prevents UnboundLocalError by ensuring os is always from the pre-populated namespace
            # Pattern to match "import os" at module level (not inside functions)
            source_code_processed = source_code
            
            # Log original import statement for debugging
            if 'import os' in source_code:
                logger.info("Found 'import os' in source code, removing it to prevent UnboundLocalError")
            
            # CRITICAL: Find all function definitions that use os and ensure they have "global os"
            # This is the key fix - we need to add "global os" to functions that use os
            lines = source_code_processed.split('\n')
            processed_lines = []
            i = 0
            while i < len(lines):
                line = lines[i]
                processed_lines.append(line)
                
                # Check if this is a function definition
                func_match = re_module.match(r'^(\s*)def\s+(\w+)\s*\(', line)
                if func_match:
                    indent = func_match.group(1)
                    func_name = func_match.group(2)
                    func_start = i
                    func_indent_len = len(indent)
                    
                    # Look ahead to find the function body and check if it uses os
                    i += 1
                    func_body_lines = []
                    uses_os = False
                    has_global_os = False
                    
                    while i < len(lines):
                        current_line = lines[i]
                        current_indent = len(re_module.match(r'^(\s*)', current_line).group(1))
                        
                        # If we've dedented past the function, we're done
                        if current_line.strip() and current_indent <= func_indent_len and not current_line.strip().startswith('#'):
                            break
                        
                        # Check if line uses os
                        if 'os.' in current_line or re_module.search(r'\bos\s*=', current_line):
                            uses_os = True
                        
                        # Check if line has "global os"
                        if 'global os' in current_line:
                            has_global_os = True
                        
                        func_body_lines.append(current_line)
                        i += 1
                    
                    # If function uses os but doesn't have "global os", add it
                    if uses_os and not has_global_os:
                        logger.info(f"Adding 'global os' to function {func_name} to prevent UnboundLocalError")
                        # Find the first non-empty, non-comment line after the function definition
                        insert_pos = func_start + 1
                        while insert_pos < len(processed_lines) and (
                            not processed_lines[insert_pos].strip() or 
                            processed_lines[insert_pos].strip().startswith('#') or
                            processed_lines[insert_pos].strip().startswith('"""') or
                            processed_lines[insert_pos].strip().startswith("'''")
                        ):
                            insert_pos += 1
                        
                        # Insert "global os" after function definition
                        global_os_line = indent + "    global os  # Prevent UnboundLocalError"
                        processed_lines.insert(insert_pos, global_os_line)
                        i += 1  # Account for the inserted line
                    
                    # Add the function body lines
                    processed_lines.extend(func_body_lines)
                    continue
                
                i += 1
            
            source_code_processed = '\n'.join(processed_lines)
            
            # Replace standalone "import os" lines (not indented, at module level)
            # This regex matches "import os" at the start of a line (possibly with whitespace before it)
            source_code_processed = re_module.sub(
                r'^(\s*)import os\s*$',
                r'\1# import os  # os already in namespace from pre-population',
                source_code_processed,
                flags=re_module.MULTILINE
            )
            
            # Also handle "import os" as part of multiple imports (e.g., "import os, sys")
            # This is less common but could still cause issues
            source_code_processed = re_module.sub(
                r'^(\s*)import os\s*,',
                r'\1# import os,  # os already in namespace',
                source_code_processed,
                flags=re_module.MULTILINE
            )
            
            # Verify the replacement worked
            if 'import os' in source_code_processed and 'import os' not in source_code_processed.split('\n')[0:20]:
                # Check if it's in a function (indented) - that's OK, we only care about module level
                lines_with_import_os = [i+1 for i, line in enumerate(source_code_processed.split('\n')) if 'import os' in line and not line.strip().startswith('#')]
                if lines_with_import_os:
                    logger.warning(f"Still found 'import os' at lines: {lines_with_import_os} - these might be in functions (OK) or need further processing")
            
            logger.info("Source code processed - 'import os' statements removed/commented, 'global os' added to functions that use os")
            
            # CRITICAL: Ensure os is in the namespace and will remain after exec()
            # This prevents Python from treating os as a local variable in any function
            # Create exec namespace with os pre-populated
            exec_namespace = dict(module.__dict__)
            exec_namespace['os'] = os_module  # Ensure os is always available
            
            # Also ensure module metadata is set
            exec_namespace['__name__'] = 'refactor.services.google_sheets.service'
            exec_namespace['__package__'] = 'refactor.services.google_sheets'
            
            # CRITICAL: Add os to __builtins__ as well to ensure it's always accessible
            # This prevents UnboundLocalError by making os available at all scopes
            if '__builtins__' in exec_namespace:
                if isinstance(exec_namespace['__builtins__'], dict):
                    exec_namespace['__builtins__']['os'] = os_module
                elif hasattr(exec_namespace['__builtins__'], '__dict__'):
                    exec_namespace['__builtins__'].__dict__['os'] = os_module
            
            # Compile and execute the processed code
            code = compile(source_code_processed, service_file_path, 'exec')
            # CRITICAL: Execute code - os and other modules are already in module.__dict__
            # We've removed "import os" from the source, so it won't try to import it again
            # This prevents UnboundLocalError by ensuring os is always available
            try:
                exec(code, exec_namespace)
                # Copy all items back to module.__dict__
                for key, value in exec_namespace.items():
                    if key not in ['__builtins__', '__name__', '__package__', '__file__']:
                        module.__dict__[key] = value
                # Always ensure os is in module dict (critical!)
                module.__dict__['os'] = os_module
                
                # CRITICAL: Fix all functions' __globals__ to point to module.__dict__
                # This ensures that when functions access 'os', they find it in the module's dict
                # When code is executed via exec(), functions might have separate __globals__
                import types
                for name, obj in list(module.__dict__.items()):
                    if isinstance(obj, types.FunctionType):
                        # CRITICAL: Replace function's __globals__ with module.__dict__ if possible
                        # This ensures all global variable lookups go through the module's dict
                        try:
                            if hasattr(obj, '__globals__'):
                                # Try to make __globals__ reference module.__dict__ directly
                                # This is the key fix - when __globals__ is the same dict as module.__dict__,
                                # all global lookups will find os in the module dict
                                if isinstance(obj.__globals__, dict):
                                    # Ensure os is in the function's globals
                                    obj.__globals__['os'] = os_module
                                    # Try to replace the entire __globals__ dict with module.__dict__
                                    # This is safe because exec_namespace was based on module.__dict__
                                    if obj.__globals__ is not module.__dict__:
                                        # Create a new function with module.__dict__ as globals
                                        # This is the most reliable way to ensure globals are correct
                                        try:
                                            # Use types.FunctionType to create a new function with correct globals
                                            new_func = types.FunctionType(
                                                obj.__code__,
                                                module.__dict__,  # Use module.__dict__ as globals
                                                obj.__name__,
                                                obj.__defaults__,
                                                obj.__closure__
                                            )
                                            # Copy function attributes
                                            for attr in ['__annotations__', '__doc__', '__kwdefaults__']:
                                                if hasattr(obj, attr):
                                                    setattr(new_func, attr, getattr(obj, attr))
                                            # Replace the function in module dict
                                            module.__dict__[name] = new_func
                                            logger.info(f"✅ Replaced function {name} with corrected __globals__")
                                        except Exception as func_replace_error:
                                            # If we can't replace, at least ensure os is in globals
                                            obj.__globals__['os'] = os_module
                                            logger.warning(f"Could not replace function {name}, but ensured os in globals: {func_replace_error}")
                                    else:
                                        # Already using module.__dict__, just ensure os is there
                                        obj.__globals__['os'] = os_module
                                        logger.debug(f"Function {name} already using module.__dict__, ensured os is present")
                        except Exception as fix_error:
                            logger.warning(f"Could not fix __globals__ for function {name}: {fix_error}")
            except UnboundLocalError as e:
                if 'os' in str(e):
                    logger.error(f"UnboundLocalError for 'os' occurred despite fix! Error: {e}")
                    logger.error("This suggests a function is trying to use os before it's available")
                    import traceback
                    tb = traceback.format_exc()
                    logger.error(f"Traceback: {tb}")
                    # Force os into namespace and retry with explicit global handling
                    exec_namespace['os'] = os_module
                    # Inject a helper that ensures os is always available
                    # Prepend code to add global os to all functions that use it
                    injected_code = """
# CRITICAL: Ensure os is always available as a global
import sys
if 'os' not in globals():
    import os as _os_module
    globals()['os'] = _os_module
"""
                    # Try executing with injected code first
                    try:
                        exec(injected_code + source_code_processed, exec_namespace)
                        # Copy back
                        for key, value in exec_namespace.items():
                            if key not in ['__builtins__', '__name__', '__package__', '__file__']:
                                module.__dict__[key] = value
                        module.__dict__['os'] = os_module
                        logger.info("✅ Retry with os injection succeeded")
                    except Exception as retry_error:
                        logger.error(f"Retry with injected code also failed: {retry_error}")
                        raise e  # Re-raise original UnboundLocalError
                else:
                    raise
            
            # CRITICAL: After execution, ensure os is still in the namespace
            # Sometimes exec() can remove or reassign variables
            if 'os' not in module.__dict__ or not hasattr(module.__dict__.get('os', None), 'path'):
                module.__dict__['os'] = os_module
                logger.warning("os was missing or invalid from module namespace after exec(), restored it")
            
            # CRITICAL: Ensure os is ALWAYS in the module namespace before extracting functions
            # This prevents UnboundLocalError when functions are called later
            module.__dict__['os'] = os_module
            logger.info("✅ Ensured os is in module namespace before extracting functions")
            
            # CRITICAL: Fix all functions' __globals__ to point to module.__dict__
            # This ensures that when functions access 'os', they find it in the module's dict
            # When code is executed via exec(), functions might have separate __globals__
            import types
            for name, obj in list(module.__dict__.items()):
                if isinstance(obj, types.FunctionType):
                    # Ensure function's __globals__ has os
                    if hasattr(obj, '__globals__'):
                        if isinstance(obj.__globals__, dict):
                            obj.__globals__['os'] = os_module
                            logger.debug(f"Fixed __globals__['os'] for function {name}")
                        # Try to make __globals__ reference module.__dict__ if possible
                        try:
                            # If __globals__ is the same dict as module.__dict__, we're good
                            # Otherwise, ensure os is in both
                            if obj.__globals__ is not module.__dict__:
                                obj.__globals__['os'] = os_module
                        except (TypeError, AttributeError):
                            pass
            
            logger.info("✅ Module loaded successfully using compile + exec")
            
            # Extract required attributes
            _fetch = getattr(module, 'fetch_schedule_data', None)
            _GS = getattr(module, 'GoogleSheetsService', None)
            _list = getattr(module, 'list_sheets', None)
            _validate = getattr(module, 'validate_sheets', None)
            
            logger.info(f"Extracted - fetch_schedule_data: {_fetch is not None}, GoogleSheetsService: {_GS is not None}, list_sheets: {_list is not None}, validate_sheets: {_validate is not None}")
            
            if _fetch is None or _GS is None:
                raise ImportError(
                    f"Required attributes not found in module. "
                    f"fetch_schedule_data: {_fetch is not None}, "
                    f"GoogleSheetsService: {_GS is not None}"
                )
            
            logger.info("✅ Successfully extracted all required attributes")
            
            # CRITICAL: Wrap fetch_schedule_data to ensure os is always available when called
            # Use the centralized wrapper function for consistency
            _fetch = _wrap_fetch_schedule_data(_fetch, os_module)
            
        except Exception as e:
            logger.error(f"Failed to load module using importlib: {e}")
            import traceback
            logger.error(f"Full traceback:\n{traceback.format_exc()}")
            raise
        
        # CRITICAL: Always wrap fetch_schedule_data before assigning to module-level variable
        # This ensures that even direct imports get the wrapped version
        fetch_schedule_data = _wrap_fetch_schedule_data(_fetch, os_module)
        
        GoogleSheetsService = _GS
        list_sheets = _list
        validate_sheets = _validate
        SHEETS_AVAILABLE = True
        
        # CRITICAL: Ensure os is always available in the module after import
        # This prevents UnboundLocalError when fetch_schedule_data is called
        if fetch_schedule_data and hasattr(fetch_schedule_data, '__module__'):
            module_name = fetch_schedule_data.__module__
            if module_name in sys.modules:
                module = sys.modules[module_name]
                if 'os' not in module.__dict__ or not hasattr(module.__dict__.get('os', None), 'path'):
                    module.__dict__['os'] = os_module
                    logger.info(f"Ensured os is available in {module_name} after import")
        
        logger.info("✅ Google Sheets service loaded successfully from: refactor.services.google_sheets.service")
        logger.info(f"✅ Import path: {backend_path}")
        logger.info("=" * 80)
        trace_import_success('refactor.services.google_sheets.service', backend_path)
        
        # Verify imports are actually available
        if fetch_schedule_data is None or GoogleSheetsService is None:
            logger.error("[TRACE] Import reported success but fetch_schedule_data or GoogleSheetsService is None!")
            SHEETS_AVAILABLE = False
            return False, "Import succeeded but modules are None"
        
        logger.info(f"[TRACE] ✅ Verified imports - fetch_schedule_data: {fetch_schedule_data is not None}, GoogleSheetsService: {GoogleSheetsService is not None}")
        return True, backend_path
        
    except ImportError as e1:
        _last_import_error = str(e1)
        logger.warning(f"Attempt 1 failed: {e1}")
        import traceback
        logger.error(f"Import error traceback:\n{traceback.format_exc()}")
    
    # Import strategy 2: Check if file exists, then try with absolute path
    try:
        logger.info("Attempt 2: Checking absolute path and file existence")
        if not os.path.exists(target_path):
            logger.error(f"Target file does not exist: {target_path}")
        else:
            logger.info(f"Target file exists, trying import again with explicit path")
            # Try again with explicit path manipulation
            if project_root not in sys.path:
                sys.path.insert(0, project_root)
            
            from refactor.services.google_sheets.service import (
                fetch_schedule_data as _fetch,
                GoogleSheetsService as _GS,
                list_sheets as _list,
                validate_sheets as _validate
            )
            
            # CRITICAL: Wrap fetch_schedule_data to ensure os is always available
            import os as os_module_attempt2
            fetch_schedule_data = _wrap_fetch_schedule_data(_fetch, os_module_attempt2)
            GoogleSheetsService = _GS
            list_sheets = _list
            validate_sheets = _validate
            SHEETS_AVAILABLE = True
            
            logger.info("✅ Google Sheets service loaded successfully (attempt 2)")
            logger.info("=" * 80)
            return True, backend_path
            
    except ImportError as e2:
        _last_import_error = str(e2)
        logger.warning(f"Attempt 2 failed: {e2}")
        import traceback
        logger.error(f"Import error traceback:\n{traceback.format_exc()}")
    
    # Import strategy 3: Try importing from backend/refactor
    try:
        logger.info("Attempt 3: Checking backend/refactor directory")
        refactor_target = os.path.join(backend_path, 'refactor', 'services', 'google_sheets', 'service.py')
        
        if os.path.exists(refactor_target):
            logger.info(f"Found in backend/refactor: {refactor_target}")
            if backend_path not in sys.path:
                sys.path.insert(0, backend_path)
            
            from refactor.services.google_sheets.service import (
                fetch_schedule_data as _fetch,
                GoogleSheetsService as _GS,
                list_sheets as _list,
                validate_sheets as _validate
            )
            
            # CRITICAL: Wrap fetch_schedule_data to ensure os is always available
            import os as os_module_attempt3
            fetch_schedule_data = _wrap_fetch_schedule_data(_fetch, os_module_attempt3)
            GoogleSheetsService = _GS
            list_sheets = _list
            validate_sheets = _validate
            SHEETS_AVAILABLE = True
            
            logger.info("✅ Google Sheets service loaded successfully (attempt 3)")
            logger.info("=" * 80)
            return True, backend_path
            
    except ImportError as e3:
        _last_import_error = str(e3)
        logger.warning(f"Attempt 3 failed: {e3}")
        import traceback
        logger.error(f"Import error traceback:\n{traceback.format_exc()}")
    
    # All attempts failed
    _last_import_error = "All import attempts failed"
    logger.error("❌ Google Sheets service not available after all import attempts")
    logger.error("Checked paths:")
    logger.error(f"  1. {project_root}/app/services/google_sheets/service.py")
    logger.error(f"  2. {os.path.dirname(project_root)}/app/services/google_sheets/service.py")
    logger.error(f"Current sys.path (first 5): {sys.path[:5]}")
    logger.error("=" * 80)
    logger.error("💡 TIP: Make sure backend is run from backend/ directory")
    logger.error("💡 TIP: Check that app/services/google_sheets/service.py exists at project root")
    
    trace_import_failure(_last_import_error, attempts=3)
    return False, None


def get_google_sheets_service():
    """Get GoogleSheetsService instance if available"""
    success, path = _try_import_google_sheets()
    if success and GoogleSheetsService:
        return GoogleSheetsService
    return None


def get_fetch_schedule_data():
    """Get fetch_schedule_data function if available"""
    success, path = _try_import_google_sheets()
    if success and fetch_schedule_data:
        # CRITICAL: Wrap fetch_schedule_data to ensure os is always available
        # This prevents UnboundLocalError when the function is called
        def wrapped_fetch_schedule_data(*args, **kwargs):
            """Wrapper that ensures os is available before calling fetch_schedule_data"""
            import os as os_module
            # Ensure os is in globals before calling the actual function
            import sys
            # Get the module where fetch_schedule_data is defined
            if hasattr(fetch_schedule_data, '__module__'):
                module_name = fetch_schedule_data.__module__
                if module_name in sys.modules:
                    module = sys.modules[module_name]
                    # Ensure os is in the module's namespace
                    if 'os' not in module.__dict__ or not hasattr(module.__dict__.get('os', None), 'path'):
                        module.__dict__['os'] = os_module
                        logger.info(f"Ensured os is available in module {module_name} before calling fetch_schedule_data")
            
            try:
                return fetch_schedule_data(*args, **kwargs)
            except UnboundLocalError as e:
                if 'os' in str(e):
                    logger.error(f"UnboundLocalError for 'os' in fetch_schedule_data: {e}")
                    # Try to fix by ensuring os is in the module namespace
                    if hasattr(fetch_schedule_data, '__module__'):
                        module_name = fetch_schedule_data.__module__
                        if module_name in sys.modules:
                            module = sys.modules[module_name]
                            module.__dict__['os'] = os_module
                            logger.info(f"Fixed os in module {module_name}, retrying...")
                            return fetch_schedule_data(*args, **kwargs)
                    raise
                else:
                    raise
        
        return wrapped_fetch_schedule_data
    return None

