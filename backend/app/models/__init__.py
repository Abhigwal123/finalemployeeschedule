# Models Package - Import all models for easy access
from .tenant import Tenant
from .user import User
from .department import Department
from .schedule_definition import ScheduleDefinition
from .schedule_permission import SchedulePermission
from .schedule_job_log import ScheduleJobLog

# Try to import new models (may not exist yet)
try:
    from .employee_mapping import EmployeeMapping
except ImportError:
    EmployeeMapping = None

try:
    from .sheet_cache import CachedSheetData
except ImportError:
    CachedSheetData = None

try:
    from .cached_schedule import CachedSchedule
except ImportError:
    CachedSchedule = None

try:
    from .sync_log import SyncLog
except ImportError:
    SyncLog = None

# Schedule model removed - not used
Schedule = None

try:
    from .schedule_task import ScheduleTask
except ImportError:
    ScheduleTask = None

# Legacy alias for backwards compatibility
SheetCache = CachedSheetData

# Export all models
__all__ = [
    'Tenant',
    'User', 
    'Department',
    'ScheduleDefinition',
    'SchedulePermission',
    'ScheduleJobLog',
    'EmployeeMapping',
    'SheetCache',
    'CachedSchedule',
    'SyncLog',
    'ScheduleTask'
]

# Ensure "app.models" (and submodules) resolve to the already-loaded backend modules.
import sys as _sys
_alias_root = "app.models"
_backend_root = __name__
_sys.modules.setdefault(_alias_root, _sys.modules[_backend_root])

# Mirror every loaded submodule under the app.models namespace so imports like
# "from app.models.schedule_task import ScheduleTask" reuse the exact same module
# objects instead of loading duplicates (which caused duplicate table definitions).
for _module_name, _module in list(_sys.modules.items()):
    if not _module_name or not _module_name.startswith(_backend_root):
        continue
    _alias_name = _module_name.replace(_backend_root, _alias_root, 1)
    _sys.modules.setdefault(_alias_name, _module)
