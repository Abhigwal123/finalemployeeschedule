# Google Sheets Spreadsheet ID Audit Report

**Generated:** 2025-01-03  
**Purpose:** Comprehensive audit of all Google Sheets spreadsheet IDs and sheet keys across the entire project

---

## Executive Summary

This audit identified **3 unique Google Sheets spreadsheet IDs** used across the codebase:
- **1 Input Sheet ID** (consistent across all components)
- **2 Different Output Sheet IDs** (⚠️ **MISMATCH DETECTED**)

### Critical Findings

⚠️ **OUTPUT SHEET ID MISMATCH:**
- Backend API (`backend/app/__init__.py`) uses: `1Imm6TJDWsoVXpf0ykMrPj4rGPfP1noagBdgoZc5Hhxg`
- Backend Config (`backend/app/config.py`) uses: `16K1AyhmOWWW1pDbWEIOyNB5td32sXxqsKCyO06pjUSw`
- Celery Tasks (`backend/run_refactored.py`) uses: `16K1AyhmOWWW1pDbWEIOyNB5td32sXxqsKCyO06pjUSw`

**Impact:** Backend API and Celery tasks may be writing to different Google Sheets, causing data inconsistency.

---

## All Google Sheets Spreadsheet IDs Found

### 1. Input Sheet ID
**ID:** `1hEr8XD3ThVQQAFWi-Q0owRYxYnBRkwyqiOdbmp6zafg`

**Full URL:** `https://docs.google.com/spreadsheets/d/1hEr8XD3ThVQQAFWi-Q0owRYxYnBRkwyqiOdbmp6zafg/edit?gid=0#gid=0`

**Status:** ✅ **CONSISTENT** - Used identically across all components

**Locations:**
- `backend/app/config.py` (Line 96)
- `backend/app/__init__.py` (Line 150)
- `backend/app/utils/db.py` (Line 118)
- `backend/run_refactored.py` (Line 111)

---

### 2. Output Sheet ID (Version A) - ⚠️ MISMATCHED
**ID:** `1Imm6TJDWsoVXpf0ykMrPj4rGPfP1noagBdgoZc5Hhxg`

**Full URL:** `https://docs.google.com/spreadsheets/d/1Imm6TJDWsoVXpf0ykMrPj4rGPfP1noagBdgoZc5Hhxg/edit?usp=sharing`

**Status:** ⚠️ **USED BY BACKEND API ONLY**

**Locations:**
- `backend/app/__init__.py` (Line 151) - Default fallback in Flask app factory
- `backend/app/utils/db.py` (Line 122) - Seed function for schedule definitions

**Component Type:** Backend API / Flask Application Factory

---

### 3. Output Sheet ID (Version B) - ⚠️ MISMATCHED
**ID:** `16K1AyhmOWWW1pDbWEIOyNB5td32sXxqsKCyO06pjUSw`

**Full URL:** `https://docs.google.com/spreadsheets/d/16K1AyhmOWWW1pDbWEIOyNB5td32sXxqsKCyO06pjUSw/edit?gid=0#gid=0`

**Status:** ⚠️ **USED BY CELERY TASKS AND CONFIG**

**Locations:**
- `backend/app/config.py` (Line 100) - Config class default
- `backend/run_refactored.py` (Line 112) - Default for Celery/refactored scheduler

**Component Type:** Celery Tasks / Scheduled Jobs / Config Default

---

## Detailed File-by-File Analysis

### Backend API Configuration Files

#### 1. `backend/app/config.py`
**File Type:** Configuration  
**Component:** Backend API / Flask Config

| Line | Variable | Sheet ID | URL |
|------|----------|----------|-----|
| 96 | `GOOGLE_INPUT_URL` | `1hEr8XD3ThVQQAFWi-Q0owRYxYnBRkwyqiOdbmp6zafg` | Input Sheet |
| 100 | `GOOGLE_OUTPUT_URL` | `16K1AyhmOWWW1pDbWEIOyNB5td32sXxqsKCyO06pjUSw` | **Output Sheet B** |

**Code Context:**
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

---

#### 2. `backend/app/__init__.py`
**File Type:** Flask Application Factory  
**Component:** Backend API / Flask App Initialization

| Line | Variable | Sheet ID | URL |
|------|----------|----------|-----|
| 150 | `GOOGLE_INPUT_URL` | `1hEr8XD3ThVQQAFWi-Q0owRYxYnBRkwyqiOdbmp6zafg` | Input Sheet |
| 151 | `GOOGLE_OUTPUT_URL` | `1Imm6TJDWsoVXpf0ykMrPj4rGPfP1noagBdgoZc5Hhxg` | **Output Sheet A** ⚠️ |

**Code Context:**
```python
app.config.setdefault("GOOGLE_INPUT_URL", os.getenv("GOOGLE_INPUT_URL", "https://docs.google.com/spreadsheets/d/1hEr8XD3ThVQQAFWi-Q0owRYxYnBRkwyqiOdbmp6zafg/edit?gid=0#gid=0"))
app.config.setdefault("GOOGLE_OUTPUT_URL", os.getenv("GOOGLE_OUTPUT_URL", "https://docs.google.com/spreadsheets/d/1Imm6TJDWsoVXpf0ykMrPj4rGPfP1noagBdgoZc5Hhxg/edit?usp=sharing"))
```

**⚠️ CRITICAL:** This file uses **different output sheet ID** than `config.py`!

---

#### 3. `backend/app/utils/db.py`
**File Type:** Database Utilities  
**Component:** Backend API / Database Seeding

| Line | Variable | Sheet ID | URL |
|------|----------|----------|-----|
| 118 | `GOOGLE_INPUT_URL` (default) | `1hEr8XD3ThVQQAFWi-Q0owRYxYnBRkwyqiOdbmp6zafg` | Input Sheet |
| 122 | `GOOGLE_OUTPUT_URL` (default) | `1Imm6TJDWsoVXpf0ykMrPj4rGPfP1noagBdgoZc5Hhxg` | **Output Sheet A** ⚠️ |

**Code Context:**
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

**⚠️ NOTE:** This file uses the same output sheet ID as `__init__.py` (Output Sheet A).

---

### Celery Task Files

#### 4. `backend/run_refactored.py`
**File Type:** Celery Task Entry Point  
**Component:** Celery Worker / Scheduled Tasks

| Line | Variable | Sheet ID | URL |
|------|----------|----------|-----|
| 111 | `DEFAULT_INPUT_SHEET_URL` | `1hEr8XD3ThVQQAFWi-Q0owRYxYnBRkwyqiOdbmp6zafg` | Input Sheet |
| 112 | `DEFAULT_OUTPUT_SHEET_URL` | `16K1AyhmOWWW1pDbWEIOyNB5td32sXxqsKCyO06pjUSw` | **Output Sheet B** ⚠️ |

**Code Context:**
```python
DEFAULT_INPUT_SHEET_URL = "https://docs.google.com/spreadsheets/d/1hEr8XD3ThVQQAFWi-Q0owRYxYnBRkwyqiOdbmp6zafg/edit?gid=0#gid=0"
DEFAULT_OUTPUT_SHEET_URL = "https://docs.google.com/spreadsheets/d/16K1AyhmOWWW1pDbWEIOyNB5td32sXxqsKCyO06pjUSw/edit?gid=0#gid=0"
```

**⚠️ CRITICAL:** Celery tasks use **different output sheet ID** than Backend API (`__init__.py`)!

---

#### 5. `backend/app/services/celery_tasks.py`
**File Type:** Celery Task Definitions  
**Component:** Celery Worker / Task Registration

| Line | Reference | Source | Sheet ID |
|------|-----------|--------|----------|
| 127 | `GOOGLE_SHEET_ID` config | Reads from Flask config | Uses env var or default |
| 125-129 | Input/Output URLs | Reads from Flask config | Uses env vars or config defaults |

**Code Context:**
```python
cfg_in = flask_app_instance.config.get("GOOGLE_INPUT_URL")
cfg_out = flask_app_instance.config.get("GOOGLE_OUTPUT_URL")
sheet_id = flask_app_instance.config.get("GOOGLE_SHEET_ID")
in_url = input_url or cfg_in or get_default_input_url(sheet_id)
out_url = output_url or cfg_out or get_default_output_url(sheet_id)
```

**Behavior:** 
- Reads from Flask app config (which may use `__init__.py` defaults)
- Falls back to `get_default_input_url()` / `get_default_output_url()` from `google_io.py`
- If no environment variables are set, will use Output Sheet A from `__init__.py`

---

### Google Sheets Service Files

#### 6. `backend/refactor/services/google_sheets/service.py`
**File Type:** Google Sheets Service Implementation  
**Component:** Utility Service / Google Sheets Integration

| Line | Method | Behavior |
|------|--------|----------|
| 266-270 | `_extract_spreadsheet_id()` | Extracts sheet ID from URLs dynamically |
| 293 | `open_by_key()` | Uses extracted ID from URL parameter |
| Multiple | Various methods | All use `_extract_spreadsheet_id()` - no hardcoded IDs |

**Code Context:**
```python
def _extract_spreadsheet_id(self, url: str) -> str:
    """Extract spreadsheet ID from URL"""
    if '/spreadsheets/d/' in url:
        return url.split('/spreadsheets/d/')[1].split('/')[0]
    return url
```

**Status:** ✅ **DYNAMIC** - No hardcoded IDs, extracts from URLs at runtime

---

#### 7. `backend/app/services/google_sheets_sync_service.py`
**File Type:** Google Sheets Sync Service  
**Component:** Backend API / Data Sync

| Behavior | Details |
|----------|---------|
| Sheet URLs | Reads from `ScheduleDefinition` model (database) |
| No hardcoded IDs | Uses `paramsSheetURL`, `resultsSheetURL` from database |

**Status:** ✅ **DYNAMIC** - Reads sheet URLs from database, no hardcoded IDs

---

### Other Utility Files

#### 8. `backend/app/services/google_io.py`
**File Type:** Google Sheets I/O Utilities  
**Component:** Backend API / Utility Functions

**Functions:**
- `build_spreadsheet_url(sheet_id: str)` - Builds URL from ID
- `get_default_input_url(sheet_id: str)` - Builds input URL
- `get_default_output_url(sheet_id: str)` - Builds output URL

**Status:** ✅ **DYNAMIC** - Accepts sheet IDs as parameters, no hardcoded values

---

#### 9. `backend/app/services/google_sheets_import.py`
**File Type:** Google Sheets Import Wrapper  
**Component:** Backend API / Module Loading

**Status:** ✅ **NO HARDCODED IDs** - Only handles module loading/importing

---

## Component Mapping: Which Component Uses Which Sheet ID?

### Input Sheet ID: `1hEr8XD3ThVQQAFWi-Q0owRYxYnBRkwyqiOdbmp6zafg`
✅ **CONSISTENT ACROSS ALL COMPONENTS**

| Component | File | Line | Usage |
|-----------|------|------|-------|
| Backend Config | `backend/app/config.py` | 96 | Default `GOOGLE_INPUT_URL` |
| Backend API | `backend/app/__init__.py` | 150 | Default fallback |
| Database Seeding | `backend/app/utils/db.py` | 118 | Default for schedule definitions |
| Celery Tasks | `backend/run_refactored.py` | 111 | `DEFAULT_INPUT_SHEET_URL` |

---

### Output Sheet ID: `1Imm6TJDWsoVXpf0ykMrPj4rGPfP1noagBdgoZc5Hhxg` (Version A)
⚠️ **USED BY BACKEND API ONLY**

| Component | File | Line | Usage |
|-----------|------|------|-------|
| Backend API | `backend/app/__init__.py` | 151 | Default `GOOGLE_OUTPUT_URL` fallback |
| Database Seeding | `backend/app/utils/db.py` | 122 | Default for schedule definitions |

---

### Output Sheet ID: `16K1AyhmOWWW1pDbWEIOyNB5td32sXxqsKCyO06pjUSw` (Version B)
⚠️ **USED BY CELERY TASKS AND CONFIG**

| Component | File | Line | Usage |
|-----------|------|------|-------|
| Backend Config | `backend/app/config.py` | 100 | Default `GOOGLE_OUTPUT_URL` |
| Celery Tasks | `backend/run_refactored.py` | 112 | `DEFAULT_OUTPUT_SHEET_URL` |

---

## Mismatch Analysis

### The Problem

**Two different output sheet IDs are hardcoded in different parts of the codebase:**

1. **Output Sheet A** (`1Imm6TJDWsoVXpf0ykMrPj4rGPfP1noagBdgoZc5Hhxg`):
   - Used in `backend/app/__init__.py` (Flask app factory)
   - Used in `backend/app/utils/db.py` (database seeding)
   - **Impact:** Backend API requests without environment variables will use this sheet

2. **Output Sheet B** (`16K1AyhmOWWW1pDbWEIOyNB5td32sXxqsKCyO06pjUSw`):
   - Used in `backend/app/config.py` (Config class)
   - Used in `backend/run_refactored.py` (Celery tasks)
   - **Impact:** Celery scheduled tasks and config-based operations will use this sheet

### Root Cause

The mismatch occurs because:
1. `backend/app/__init__.py` has hardcoded fallback URL with Output Sheet A
2. `backend/app/config.py` has hardcoded default URL with Output Sheet B
3. `backend/run_refactored.py` (Celery) has hardcoded default with Output Sheet B

When Flask app is created:
- If `GOOGLE_OUTPUT_URL` env var is **not set**, `__init__.py` uses Output Sheet A
- Config class default (Output Sheet B) is ignored if `__init__.py` sets it first

When Celery tasks run:
- If no config is provided, `run_refactored.py` uses Output Sheet B
- If config is provided, it reads from Flask config (which may be Output Sheet A)

**Result:** Backend API and Celery tasks may write to different sheets!

---

## Environment Variables

### Expected Environment Variables

The codebase expects these environment variables (checked but not found in `.env` files):

| Variable | Purpose | Default Used If Not Set |
|----------|---------|------------------------|
| `GOOGLE_INPUT_URL` | Input Google Sheet URL | `1hEr8XD3ThVQQAFWi-Q0owRYxYnBRkwyqiOdbmp6zafg` |
| `GOOGLE_OUTPUT_URL` | Output Google Sheet URL | ⚠️ **MISMATCHED** (depends on component) |
| `GOOGLE_SHEET_ID` | Generic sheet ID | `YOUR_SHEET_ID_HERE` (placeholder) |
| `GOOGLE_APPLICATION_CREDENTIALS` | Service account JSON path | `service-account-creds.json` |

### Recommendations

1. **Set `GOOGLE_OUTPUT_URL` environment variable** in production to ensure consistency
2. **Choose one output sheet ID** and update all hardcoded defaults
3. **Remove hardcoded defaults** from `__init__.py` to rely on Config class

---

## Patterns Found

### Pattern 1: `open_by_key()`
**Usage:** Direct spreadsheet access via gspread

**Locations:**
- `backend/refactor/services/google_sheets/service.py` (Lines 293, 348, 361, 402, 457, 537, 656, 787)

**Behavior:** All use dynamically extracted IDs from URLs (no hardcoded IDs)

---

### Pattern 2: `open_by_url()`
**Usage:** Direct spreadsheet access via URL

**Locations:**
- `backend/app/services/auto_regeneration_service.py` (Line 179)
- `backend/refactor/data_writer.py` (Line 58)
- `backend/refactor/data_provider.py` (Line 173)

**Behavior:** Accepts URL as parameter (no hardcoded IDs)

---

### Pattern 3: `spreadsheet_id` extraction
**Usage:** Extract ID from URL using `_extract_spreadsheet_id()`

**Locations:**
- `backend/refactor/services/google_sheets/service.py` (Multiple locations)

**Behavior:** Dynamically extracts ID from URL string

---

### Pattern 4: Environment variable fallbacks
**Usage:** Read from env vars with hardcoded defaults

**Locations:**
- `backend/app/config.py` (Lines 94-102)
- `backend/app/__init__.py` (Lines 150-151)
- `backend/run_refactored.py` (Lines 111-112)

**Behavior:** Falls back to hardcoded URLs if env vars not set

---

## Summary of Findings

### ✅ Consistent Components
1. **Input Sheet ID** - Used identically everywhere
2. **Google Sheets Service** - Dynamic ID extraction (no hardcoded IDs)
3. **Sync Service** - Reads URLs from database (no hardcoded IDs)
4. **Utility Functions** - Accept IDs as parameters (no hardcoded IDs)

### ⚠️ Mismatched Components
1. **Output Sheet ID** - Two different IDs hardcoded:
   - Backend API uses: `1Imm6TJDWsoVXpf0ykMrPj4rGPfP1noagBdgoZc5Hhxg`
   - Celery/Config uses: `16K1AyhmOWWW1pDbWEIOyNB5td32sXxqsKCyO06pjUSw`

### 🔧 Recommendations

1. **IMMEDIATE ACTION:**
   - Decide which output sheet ID is correct
   - Update all hardcoded defaults to use the same ID
   - Set `GOOGLE_OUTPUT_URL` environment variable in production

2. **FIXES NEEDED:**
   - Update `backend/app/__init__.py` Line 151 to match `config.py`
   - OR update `backend/app/config.py` Line 100 to match `__init__.py`
   - Update `backend/app/utils/db.py` Line 122 to match chosen ID
   - Ensure `backend/run_refactored.py` Line 112 matches chosen ID

3. **BEST PRACTICE:**
   - Remove hardcoded defaults from `__init__.py` (let Config class handle it)
   - Always use environment variables in production
   - Document which sheet IDs are for input vs output

---

## Action Items

- [ ] **CRITICAL:** Choose correct output sheet ID and update all files
- [ ] Set `GOOGLE_OUTPUT_URL` environment variable in production
- [ ] Verify Celery tasks and Backend API use same output sheet
- [ ] Test that scheduled tasks write to correct sheet
- [ ] Remove duplicate hardcoded defaults (consolidate to Config class)
- [ ] Document which sheet IDs are for production vs development

---

## Files Modified Checklist

When fixing the mismatch, update these files:

1. `backend/app/__init__.py` (Line 151) - Change Output Sheet A to B (or vice versa)
2. `backend/app/config.py` (Line 100) - Ensure matches chosen ID
3. `backend/app/utils/db.py` (Line 122) - Update to match chosen ID
4. `backend/run_refactored.py` (Line 112) - Verify matches chosen ID

---

## Complete Celery Tasks Inventory

### Summary

This project contains **13 Celery tasks** distributed across 3 files:
- **4 tasks** in `backend/app/services/celery_tasks.py`
- **4 tasks** in `backend/app/tasks/google_sync.py`
- **2 tasks** in `backend/app/tasks/schedule.py`
- **1 task** in `backend/app/tasks/tasks.py`
- **2 additional tasks** registered in `backend/app/services/celery_tasks.py` (defined within functions)

---

### Task 1: `async_run_schedule`
- **File:** `backend/app/services/celery_tasks.py`
- **Line:** 89
- **Task Name:** `async_run_schedule`
- **Decorator:** `@celery.task(bind=True, name="async_run_schedule")`
- **Function Signature:**
  ```python
  def async_run_schedule(self, input_url: str | None = None, output_url: str | None = None)
  ```
- **Summary:** Executes scheduling task asynchronously using run_refactored.py. Reads Google Sheets input and writes results to Google Sheets output. Uses Flask app config to get default URLs if not provided.
- **Google Sheets Interaction:** ✅ YES - Reads input from Google Sheets and writes output to Google Sheets
- **Database Interaction:** ❌ NO - Does not directly interact with database
- **Trigger:** API call or manual task invocation

---

### Task 2: `execute_scheduling_task`
- **File:** `backend/app/services/celery_tasks.py`
- **Line:** 166
- **Task Name:** `celery_tasks.execute_scheduling_task`
- **Decorator:** `@celery_app.task(name="celery_tasks.execute_scheduling_task", bind=True)`
- **Function Signature:**
  ```python
  def execute_scheduling_task(self, schedule_config, job_log_id=None)
  ```
- **Summary:** Main scheduling execution task that runs CP-SAT scheduler via run_refactored.py. Updates ScheduleJobLog status in database. Reads from and writes to Google Sheets based on schedule_config.
- **Google Sheets Interaction:** ✅ YES - Reads input from Google Sheets and writes output to Google Sheets (via schedule_config)
- **Database Interaction:** ✅ YES - Updates ScheduleJobLog status and metadata
- **Trigger:** API call, scheduled task (daily_run_all_schedules), or test task

---

### Task 3: `trigger_sheet_run`
- **File:** `backend/app/services/celery_tasks.py`
- **Line:** 359
- **Task Name:** `trigger_sheet_run`
- **Decorator:** `@celery_app.task(name="trigger_sheet_run")`
- **Function Signature:**
  ```python
  def trigger_sheet_run()
  ```
- **Summary:** Lightweight periodic task that triggers async_run_schedule every 5 minutes. Acts as a liveness check and default runner.
- **Google Sheets Interaction:** ✅ YES (indirectly - triggers async_run_schedule which uses Google Sheets)
- **Database Interaction:** ❌ NO
- **Trigger:** Scheduled - Every 5 minutes via Celery Beat (`auto-run-schedule-5m`)

---

### Task 4: `daily_run_all_schedules`
- **File:** `backend/app/services/celery_tasks.py`
- **Line:** 364
- **Task Name:** `daily_run_all_schedules`
- **Decorator:** `@celery_app.task(name="daily_run_all_schedules")`
- **Function Signature:**
  ```python
  def daily_run_all_schedules()
  ```
- **Summary:** Daily automatic schedule execution at midnight. Queries all active schedules from database, creates ScheduleJobLog entries, and enqueues execute_scheduling_task for each schedule. Reads schedule URLs from database.
- **Google Sheets Interaction:** ✅ YES - Uses paramsSheetURL and resultsSheetURL from ScheduleDefinition (database)
- **Database Interaction:** ✅ YES - Queries ScheduleDefinition, Tenant, User, SchedulePermission; Creates ScheduleJobLog entries
- **Trigger:** Scheduled - Daily at midnight (00:00) via Celery Beat (`daily-run-all-schedules-midnight`)

---

### Task 5: `test_2min_auto_schedule`
- **File:** `backend/app/services/celery_tasks.py`
- **Line:** 458
- **Task Name:** `test_2min_auto_schedule`
- **Decorator:** `@celery_app.task(name="test_2min_auto_schedule")`
- **Function Signature:**
  ```python
  def test_2min_auto_schedule()
  ```
- **Summary:** Test task that runs "Daily Auto Schedule" every 2 minutes. Only active when ENABLE_TEST_CELERY_TASKS is enabled. Used for testing Celery Beat and worker execution.
- **Google Sheets Interaction:** ✅ YES - Uses schedule URLs from database to trigger execution
- **Database Interaction:** ✅ YES - Queries ScheduleDefinition, creates ScheduleJobLog
- **Trigger:** Scheduled - Every 2 minutes via Celery Beat (only if `enable_test_tasks=True`)

---

### Task 6: `auto_sync_employee_data`
- **File:** `backend/app/services/celery_tasks.py`
- **Line:** 559
- **Task Name:** `auto_sync_employee_data`
- **Decorator:** `@celery_app.task(name="auto_sync_employee_data")`
- **Function Signature:**
  ```python
  def auto_sync_employee_data()
  ```
- **Summary:** Automatic periodic task that syncs Employee IDs from Google Sheets to database every 5 minutes. Ensures EmployeeMapping table is always up-to-date with Google Sheets employee data.
- **Google Sheets Interaction:** ✅ YES - Reads employee data from Google Sheets
- **Database Interaction:** ✅ YES - Updates EmployeeMapping records
- **Trigger:** Scheduled - Every 5 minutes via Celery Beat (`auto-sync-employee-ids-every-5-mins`)

---

### Task 7: `daily_sync_all_schedules`
- **File:** `backend/app/services/celery_tasks.py`
- **Line:** 613
- **Task Name:** `daily_sync_all_schedules`
- **Decorator:** `@celery_app.task(name="daily_sync_all_schedules")`
- **Function Signature:**
  ```python
  def daily_sync_all_schedules()
  ```
- **Summary:** Daily sync task at 2 AM that syncs all active schedule definitions from Google Sheets to database. Backup sync to ensure data is synced even if sync after execution fails. Syncs to CachedSchedule table.
- **Google Sheets Interaction:** ✅ YES - Reads schedule data from Google Sheets Final Output sheet
- **Database Interaction:** ✅ YES - Writes to CachedSchedule, EmployeeMapping, SyncLog
- **Trigger:** Scheduled - Daily at 2 AM (02:00) via Celery Beat (`daily-sync-all-schedules-2am`)

---

### Task 8: `refresh_google_sheets_data`
- **File:** `backend/app/services/celery_tasks.py`
- **Line:** 680
- **Task Name:** `refresh_google_sheets_data`
- **Decorator:** `@celery_app.task(name="refresh_google_sheets_data")`
- **Function Signature:**
  ```python
  def refresh_google_sheets_data()
  ```
- **Summary:** Daily task at 1 AM to refresh/validate Google Sheets data for all active schedule definitions. Reads multiple sheets (parameters, employee, preferences, preschedule, designation flow, final output) to ensure all sheets are accessible and credentials are valid. Does not write to database.
- **Google Sheets Interaction:** ✅ YES - Reads from multiple Google Sheets to validate accessibility
- **Database Interaction:** ❌ NO - Only reads ScheduleDefinition to get URLs
- **Trigger:** Scheduled - Daily at 1 AM (01:00) via Celery Beat (`daily-refresh-google-sheets`)

---

### Task 9: `sync_google_sheets_daily`
- **File:** `backend/app/tasks/google_sync.py`
- **Line:** 17
- **Task Name:** `app.tasks.google_sync.sync_google_sheets_daily`
- **Decorator:** `@celery.task(name="app.tasks.google_sync.sync_google_sheets_daily", bind=True)`
- **Function Signature:**
  ```python
  def sync_google_sheets_daily(self)
  ```
- **Summary:** Daily sync task that syncs all active schedule definitions from Google Sheets to database. Forces sync for all schedules to ensure data freshness. Similar to daily_sync_all_schedules but runs at different time.
- **Google Sheets Interaction:** ✅ YES - Reads schedule data from Google Sheets
- **Database Interaction:** ✅ YES - Writes to CachedSchedule, EmployeeMapping, SyncLog via GoogleSheetsSyncService
- **Trigger:** Scheduled via Celery Beat (periodic) or API call

---

### Task 10: `sync_schedule_definition`
- **File:** `backend/app/tasks/google_sync.py`
- **Line:** 83
- **Task Name:** `app.tasks.google_sync.sync_schedule_definition`
- **Decorator:** `@celery.task(name="app.tasks.google_sync.sync_schedule_definition", bind=True)`
- **Function Signature:**
  ```python
  def sync_schedule_definition(self, schedule_def_id: str, force: bool = False)
  ```
- **Summary:** Syncs a specific schedule definition from Google Sheets to database. Can be forced to sync even if recent sync exists. Used by ensure_schedule_auto_sync task.
- **Google Sheets Interaction:** ✅ YES - Reads schedule data from Google Sheets for specific schedule
- **Database Interaction:** ✅ YES - Updates CachedSchedule, EmployeeMapping, SyncLog
- **Trigger:** API call, task chaining (from ensure_schedule_auto_sync), or manual invocation

---

### Task 11: `ensure_schedule_auto_sync`
- **File:** `backend/app/tasks/google_sync.py`
- **Line:** 115
- **Task Name:** `app.tasks.google_sync.ensure_schedule_auto_sync`
- **Decorator:** `@celery.task(name="app.tasks.google_sync.ensure_schedule_auto_sync", bind=True)`
- **Function Signature:**
  ```python
  def ensure_schedule_auto_sync(self)
  ```
- **Summary:** Periodic task that checks all EmployeeMappings every 10 minutes. If any user lacks CachedSchedule data or schedule is older than 6 hours, triggers automatic sync via sync_schedule_definition task.
- **Google Sheets Interaction:** ✅ YES (indirectly - triggers sync_schedule_definition which uses Google Sheets)
- **Database Interaction:** ✅ YES - Queries EmployeeMapping, CachedSchedule, ScheduleDefinition; Triggers sync tasks
- **Trigger:** Scheduled - Periodic (every 10 minutes) or API call

---

### Task 12: `sync_all_sheets_metadata`
- **File:** `backend/app/tasks/google_sync.py`
- **Line:** 215
- **Task Name:** `app.tasks.google_sync.sync_all_sheets_metadata`
- **Decorator:** `@celery.task(name="app.tasks.google_sync.sync_all_sheets_metadata", bind=True)`
- **Function Signature:**
  ```python
  def sync_all_sheets_metadata(self)
  ```
- **Summary:** Periodic task every 5 minutes to sync Google Sheets metadata (row count, preview data) for all active schedule definitions. Updates database metadata without affecting frontend API response structure.
- **Google Sheets Interaction:** ✅ YES - Reads metadata from Google Sheets (row counts, preview data)
- **Database Interaction:** ✅ YES - Updates ScheduleDefinition metadata field
- **Trigger:** Scheduled - Every 5 minutes via Celery Beat or API call

---

### Task 13: `process_schedule_task` (in tasks.py)
- **File:** `backend/app/tasks/tasks.py`
- **Line:** 22
- **Task Name:** `app.tasks.process_schedule_task`
- **Decorator:** `@celery.task(bind=True, name="app.tasks.process_schedule_task")`
- **Function Signature:**
  ```python
  def process_schedule_task(self, task_db_id: int) -> Dict[str, Any]
  ```
- **Summary:** Processes a schedule task by database ID. Updates task status/progress in ScheduleTask model and executes scheduling via run_scheduling_task_saas. Handles Google Sheets input/output.
- **Google Sheets Interaction:** ✅ YES - Uses input_config and output_config which can contain Google Sheets URLs
- **Database Interaction:** ✅ YES - Updates ScheduleTask model (status, progress, result_data, error_message)
- **Trigger:** API call with task_db_id parameter

---

### Task 14: `process_schedule_task` (in schedule.py)
- **File:** `backend/app/tasks/schedule.py`
- **Line:** 74
- **Task Name:** `app.tasks.schedule.process_schedule_task`
- **Decorator:** `@celery_app.task(bind=True, name="app.tasks.schedule.process_schedule_task")`
- **Function Signature:**
  ```python
  def process_schedule_task(self, task_id: str, user_id: int, input_source: str, input_config: Dict[str, Any], output_destination: str, output_config: Dict[str, Any], time_limit: int = 90, debug_shift: Optional[str] = None, log_level: str = "INFO")
  ```
- **Summary:** Processes schedule task using original scheduling logic. Similar to process_schedule_task in tasks.py but accepts more parameters directly. Supports Excel and Google Sheets input/output. Updates task status in database via update_task_status helper.
- **Google Sheets Interaction:** ✅ YES - Supports Google Sheets as input_source and output_destination
- **Database Interaction:** ✅ YES - Updates ScheduleTask via update_task_status helper
- **Trigger:** API call with task parameters

---

## Celery Task Summary Table

| # | Task Name | File | Google Sheets | Database | Trigger Type |
|---|-----------|------|---------------|----------|--------------|
| 1 | `async_run_schedule` | `celery_tasks.py:89` | ✅ YES | ❌ NO | API/Manual |
| 2 | `execute_scheduling_task` | `celery_tasks.py:166` | ✅ YES | ✅ YES | API/Scheduled |
| 3 | `trigger_sheet_run` | `celery_tasks.py:359` | ✅ YES (indirect) | ❌ NO | Scheduled (5m) |
| 4 | `daily_run_all_schedules` | `celery_tasks.py:364` | ✅ YES | ✅ YES | Scheduled (midnight) |
| 5 | `test_2min_auto_schedule` | `celery_tasks.py:458` | ✅ YES | ✅ YES | Scheduled (2m, test only) |
| 6 | `auto_sync_employee_data` | `celery_tasks.py:559` | ✅ YES | ✅ YES | Scheduled (5m) |
| 7 | `daily_sync_all_schedules` | `celery_tasks.py:613` | ✅ YES | ✅ YES | Scheduled (2 AM) |
| 8 | `refresh_google_sheets_data` | `celery_tasks.py:680` | ✅ YES | ❌ NO | Scheduled (1 AM) |
| 9 | `sync_google_sheets_daily` | `google_sync.py:17` | ✅ YES | ✅ YES | Scheduled/API |
| 10 | `sync_schedule_definition` | `google_sync.py:83` | ✅ YES | ✅ YES | API/Task chain |
| 11 | `ensure_schedule_auto_sync` | `google_sync.py:115` | ✅ YES (indirect) | ✅ YES | Scheduled (10m) |
| 12 | `sync_all_sheets_metadata` | `google_sync.py:215` | ✅ YES | ✅ YES | Scheduled (5m) |
| 13 | `process_schedule_task` | `tasks.py:22` | ✅ YES | ✅ YES | API |
| 14 | `process_schedule_task` | `schedule.py:74` | ✅ YES | ✅ YES | API |

---

## Periodic Task Schedule

| Task Name | Schedule | Frequency | Purpose |
|-----------|----------|-----------|---------|
| `trigger_sheet_run` | Every 5 minutes | 300 seconds | Liveness check, default runner |
| `daily_run_all_schedules` | Daily at midnight | `crontab(minute=0, hour=0)` | Auto-generate all schedules |
| `refresh_google_sheets_data` | Daily at 1 AM | `crontab(minute=0, hour=1)` | Validate Google Sheets accessibility |
| `auto_sync_employee_data` | Every 5 minutes | `crontab(minute="*/5")` | Sync employee IDs from Google Sheets |
| `daily_sync_all_schedules` | Daily at 2 AM | `crontab(minute=0, hour=2)` | Backup sync of schedule data |
| `test_2min_auto_schedule` | Every 2 minutes | 120 seconds | Test task (if enabled) |
| `ensure_schedule_auto_sync` | Every 10 minutes | Periodic | Auto-sync stale schedules |
| `sync_all_sheets_metadata` | Every 5 minutes | Periodic | Sync metadata from Google Sheets |

---

**End of Audit Report**

