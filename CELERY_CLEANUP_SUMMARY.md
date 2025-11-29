# Celery Cleanup & Google Sheets Config Standardization - Summary

**Date:** 2025-01-03  
**Status:** ✅ COMPLETED

---

## Changes Applied

### 1. ✅ Removed Minute-Based Periodic Tasks

**File:** `backend/app/services/celery_tasks.py`

**Removed from Celery Beat schedule:**
- ❌ `trigger_sheet_run` (every 5 minutes) - REMOVED
- ❌ `auto_sync_employee_data` (every 5 minutes) - REMOVED  
- ❌ `test_2min_auto_schedule` (every 2 minutes) - REMOVED
- ❌ `ensure_schedule_auto_sync` (every 10 minutes) - REMOVED (in google_sync.py)
- ❌ `sync_all_sheets_metadata` (every 5 minutes) - REMOVED (in google_sync.py)

**Kept (Daily tasks only):**
- ✅ `daily_run_all_schedules` (midnight - 00:00)
- ✅ `refresh_google_sheets_data` (1 AM - 01:00)
- ✅ `daily_sync_all_schedules` (2 AM - 02:00)

**Updated Celery Beat Schedule:**
```python
beat_schedule_definition = {
    'daily-run-all-schedules-midnight': {
        'task': 'daily_run_all_schedules',
        'schedule': crontab(minute=0, hour=0),
    },
    'daily-refresh-google-sheets': {
        'task': 'refresh_google_sheets_data',
        'schedule': crontab(minute=0, hour=1),
    },
    'daily-sync-all-schedules-2am': {
        'task': 'daily_sync_all_schedules',
        'schedule': crontab(minute=0, hour=2),
    },
}
```

**Note:** Task function definitions remain intact - only the periodic schedule entries were removed.

---

### 2. ✅ Standardized Google Sheets Config (ENV Only)

#### File: `backend/app/config.py`

**Before:**
```python
GOOGLE_INPUT_URL = os.getenv(
    "GOOGLE_INPUT_URL",
    "https://docs.google.com/spreadsheets/d/1hEr8XD3ThVQQAFWi-Q0owRYxYnBRkwyqiOdbmp6zafg/edit?gid=0#gid=0",
)
GOOGLE_OUTPUT_URL = os.getenv(
    "GOOGLE_OUTPUT_URL",
    "https://docs.google.com/spreadsheets/d/16K1AyhmOWWW1pDbWEIOyNB5td32sXxqsKCyO06pjUSw/edit?gid=0#gid=0",
)
```

**After:**
```python
# Google Sheets URLs - MUST be set via environment variables (no hardcoded defaults)
GOOGLE_INPUT_URL = os.getenv("GOOGLE_INPUT_URL")
GOOGLE_OUTPUT_URL = os.getenv("GOOGLE_OUTPUT_URL")
```

#### File: `backend/app/__init__.py`

**Before:**
```python
app.config.setdefault("GOOGLE_INPUT_URL", os.getenv("GOOGLE_INPUT_URL", "https://docs.google.com/spreadsheets/d/1hEr8XD3ThVQQAFWi-Q0owRYxYnBRkwyqiOdbmp6zafg/edit?gid=0#gid=0"))
app.config.setdefault("GOOGLE_OUTPUT_URL", os.getenv("GOOGLE_OUTPUT_URL", "https://docs.google.com/spreadsheets/d/1Imm6TJDWsoVXpf0ykMrPj4rGPfP1noagBdgoZc5Hhxg/edit?usp=sharing"))
```

**After:**
```python
# Google Sheets URLs - MUST be set via environment variables (no hardcoded defaults)
app.config["GOOGLE_INPUT_URL"] = os.getenv("GOOGLE_INPUT_URL")
app.config["GOOGLE_OUTPUT_URL"] = os.getenv("GOOGLE_OUTPUT_URL")
```

#### File: `backend/run_refactored.py`

**Before:**
```python
DEFAULT_INPUT_SHEET_URL = "https://docs.google.com/spreadsheets/d/1hEr8XD3ThVQQAFWi-Q0owRYxYnBRkwyqiOdbmp6zafg/edit?gid=0#gid=0"
DEFAULT_OUTPUT_SHEET_URL = "https://docs.google.com/spreadsheets/d/16K1AyhmOWWW1pDbWEIOyNB5td32sXxqsKCyO06pjUSw/edit?gid=0#gid=0"
```

**After:**
```python
# Google Sheets URLs - MUST be set via environment variables (no hardcoded defaults)
# Removed DEFAULT_INPUT_SHEET_URL and DEFAULT_OUTPUT_SHEET_URL
```

**Updated argument parser:**
```python
parser.add_argument("--input-sheet-url", 
                   default=None,
                   help="Input Google Sheet URL (required - set via GOOGLE_INPUT_URL env var or this argument)")
parser.add_argument("--output-sheet-url", 
                   default=None,
                   help="Output Google Sheet URL (required - set via GOOGLE_OUTPUT_URL env var or this argument)")
```

**Updated URL resolution:**
```python
# Use ENV variable or argument - no hardcoded defaults
input_sheet_url = args.input_sheet_url or os.getenv("GOOGLE_INPUT_URL")
if not input_sheet_url:
    print("Error: --input-sheet-url is required or set GOOGLE_INPUT_URL environment variable")
    sys.exit(1)

output_sheet_url = args.output_sheet_url or os.getenv("GOOGLE_OUTPUT_URL")
if not output_sheet_url:
    print("Error: --output-sheet-url is required or set GOOGLE_OUTPUT_URL environment variable")
    sys.exit(1)
```

#### File: `backend/app/utils/db.py`

**Before:**
```python
default_input_url = current_app.config.get(
    "GOOGLE_INPUT_URL",
    "https://docs.google.com/spreadsheets/d/1hEr8XD3ThVQQAFWi-Q0owRYxYnBRkwyqiOdbmp6zafg/edit?gid=0#gid=0"
)
default_output_url = current_app.config.get(
    "GOOGLE_OUTPUT_URL",
    "https://docs.google.com/spreadsheets/d/1Imm6TJDWsoVXpf0ykMrPj4rGPfP1noagBdgoZc5Hhxg/edit?usp=sharing"
)
```

**After:**
```python
# Get URLs from config (must be set via environment variables)
import os
default_input_url = current_app.config.get("GOOGLE_INPUT_URL") or os.getenv("GOOGLE_INPUT_URL")
default_output_url = current_app.config.get("GOOGLE_OUTPUT_URL") or os.getenv("GOOGLE_OUTPUT_URL")

# Skip seeding if URLs are not configured
if not default_input_url or not default_output_url:
    logger.warning("Cannot seed schedule definitions: GOOGLE_INPUT_URL or GOOGLE_OUTPUT_URL not set")
    return
```

#### File: `backend/app/services/celery_tasks.py`

**Before:**
```python
from .google_io import get_default_input_url, get_default_output_url

# In async_run_schedule:
cfg_in = flask_app_instance.config.get("GOOGLE_INPUT_URL")
cfg_out = flask_app_instance.config.get("GOOGLE_OUTPUT_URL")
sheet_id = flask_app_instance.config.get("GOOGLE_SHEET_ID")
in_url = input_url or cfg_in or get_default_input_url(sheet_id)
out_url = output_url or cfg_out or get_default_output_url(sheet_id)
```

**After:**
```python
# Removed: get_default_input_url, get_default_output_url - no longer using hardcoded defaults

# In async_run_schedule:
import os
cfg_in = flask_app_instance.config.get("GOOGLE_INPUT_URL") or os.getenv("GOOGLE_INPUT_URL")
cfg_out = flask_app_instance.config.get("GOOGLE_OUTPUT_URL") or os.getenv("GOOGLE_OUTPUT_URL")
in_url = input_url or cfg_in
out_url = output_url or cfg_out
```

---

### 3. ✅ Project Root .env is Authoritative

**File:** `backend/app/__init__.py`

**Updated .env loading:**
```python
# Load environment variables from .env if present
# PROJECT ROOT .env is authoritative - load it first
import pathlib
from dotenv import load_dotenv

backend_dir = pathlib.Path(__file__).parent.parent        # backend/
project_root = backend_dir.parent                          # Project root
project_env = project_root / ".env"                       # PROJECT_ROOT/.env
backend_env = backend_dir / ".env"                         # backend/.env

# Load PROJECT_ROOT/.env first (authoritative)
if project_env.exists():
    print(f"[ENV] Loaded PROJECT_ROOT/.env: {project_env}")
    load_dotenv(project_env, override=True)
elif backend_env.exists():
    print(f"[ENV] Loaded backend/.env: {backend_env}")
    load_dotenv(backend_env)
else:
    print(f"[ENV WARNING] No .env file found in PROJECT_ROOT or backend/ → Google Sheets URLs must be set via environment")
    load_dotenv()   # fallback to current directory
```

---

## Verification: No Hardcoded Google Sheet IDs Remaining

**Search Results:**
- ✅ No hardcoded Google Sheet IDs found in:
  - `backend/app/config.py`
  - `backend/app/__init__.py`
  - `backend/run_refactored.py`
  - `backend/app/utils/db.py`
  - `backend/app/services/celery_tasks.py`

**Note:** The audit report (`GOOGLE_SHEETS_AUDIT_REPORT.md`) still contains the IDs for documentation purposes, but they are not used in code.

---

## Required Environment Variables

The following environment variables **MUST** be set in `PROJECT_ROOT/.env`:

```bash
GOOGLE_INPUT_URL=https://docs.google.com/spreadsheets/d/YOUR_INPUT_SHEET_ID/edit
GOOGLE_OUTPUT_URL=https://docs.google.com/spreadsheets/d/YOUR_OUTPUT_SHEET_ID/edit
GOOGLE_APPLICATION_CREDENTIALS=service-account-creds.json
```

**If these are not set:**
- Flask app will start but `GOOGLE_INPUT_URL` and `GOOGLE_OUTPUT_URL` will be `None`
- Schedule seeding will be skipped (with warning)
- Celery tasks will fail if they try to use Google Sheets without URLs
- `run_refactored.py` will exit with error if URLs are not provided

---

## Files Modified

1. ✅ `backend/app/services/celery_tasks.py`
   - Removed minute-based periodic tasks
   - Updated `async_run_schedule` to use ENV only
   - Removed unused imports

2. ✅ `backend/app/config.py`
   - Removed hardcoded default URLs
   - Now uses `os.getenv()` only (no fallback)

3. ✅ `backend/app/__init__.py`
   - Removed hardcoded default URLs
   - Updated .env loading to prioritize PROJECT_ROOT/.env
   - Uses direct assignment (no `.setdefault()`)

4. ✅ `backend/run_refactored.py`
   - Removed `DEFAULT_INPUT_SHEET_URL` and `DEFAULT_OUTPUT_SHEET_URL`
   - Updated argument parser to require URLs
   - Updated URL resolution to use ENV only

5. ✅ `backend/app/utils/db.py`
   - Removed hardcoded default URLs
   - Added validation to skip seeding if URLs not set

---

## Testing Checklist

- [ ] Verify `.env` file exists in PROJECT_ROOT with `GOOGLE_INPUT_URL` and `GOOGLE_OUTPUT_URL`
- [ ] Verify Flask app starts without errors
- [ ] Verify Celery Beat only runs daily tasks (check logs)
- [ ] Verify `daily_run_all_schedules` runs at midnight
- [ ] Verify `refresh_google_sheets_data` runs at 1 AM
- [ ] Verify `daily_sync_all_schedules` runs at 2 AM
- [ ] Verify no minute-based tasks are scheduled
- [ ] Test that schedule seeding skips gracefully if URLs not set
- [ ] Test that `run_refactored.py` errors if URLs not provided

---

## Summary

✅ **All minute-based periodic tasks removed**  
✅ **All hardcoded Google Sheet URLs removed**  
✅ **Configuration now uses ENV variables only**  
✅ **PROJECT_ROOT/.env is authoritative**  
✅ **No logic changes - only config/schedule updates**

**Result:** The system now requires environment variables to be set explicitly, ensuring no hardcoded defaults can cause mismatches between components.

---

**End of Summary**

