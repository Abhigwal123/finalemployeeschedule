"""
Google Sheets Service - Core service for reading and writing Google Sheets
Implements the full flow: Parameters Sheet → Preschedule Sheet → Results Sheet
"""
"""
Google Sheets Service - Core service for reading and writing Google Sheets
Implements the full flow: Parameters Sheet → Preschedule Sheet → Results Sheet
"""
# CRITICAL: Do NOT import os at module level when code is executed via exec()
# This causes UnboundLocalError. All functions use local imports instead.
# The module-level import is commented out to prevent UnboundLocalError
# import os  # REMOVED - causes UnboundLocalError when executed via exec()
import logging
import time
from typing import Dict, Any, Optional, List, Tuple
import pandas as pd

logger = logging.getLogger(__name__)

# Try to import gspread
try:
    import gspread
    from gspread.exceptions import WorksheetNotFound, APIError
    from google.oauth2.service_account import Credentials
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False
    WorksheetNotFound = Exception  # Fallback for when gspread is not available
    APIError = Exception
    logger.warning("gspread not available - Google Sheets functionality will be limited")

# Cache configuration
CACHE_TTL = 300  # 5 minutes in seconds
_cache: Dict[str, Tuple[Dict[str, Any], float]] = {}  # Key -> (data, timestamp)


class GoogleSheetsService:
    """
    Google Sheets Service for reading Parameters, Preschedule, and writing Results
    """
    
    def __init__(self, credentials_path: Optional[str] = None):
        """
        Initialize Google Sheets Service
        
        Args:
            credentials_path: Path to service account JSON file
        """
        # CRITICAL: Import os locally to avoid UnboundLocalError when executed via exec()
        import os as _os_init
        import sys
        
        self.credentials_path = credentials_path or _os_init.getenv(
            "GOOGLE_APPLICATION_CREDENTIALS", 
            "service-account-creds.json"
        )
        
        # If path is relative and doesn't exist, try project root
        if not _os_init.path.isabs(self.credentials_path) and not _os_init.path.exists(self.credentials_path):
            # Calculate project root (assumes we're in app/services/google_sheets/service.py)
            current_file = _os_init.path.abspath(__file__)
            # Go up: service.py -> google_sheets -> services -> app -> Project_Up
            project_root = _os_init.path.dirname(_os_init.path.dirname(_os_init.path.dirname(_os_init.path.dirname(current_file))))
            project_creds = _os_init.path.join(project_root, 'service-account-creds.json')
            if _os_init.path.exists(project_creds):
                self.credentials_path = project_creds
                logger.info(f"Found credentials at project root: {self.credentials_path}")
        
        self._credentials = None
        self._client = None
        
        # Cache configuration (can be overridden per instance if needed)
        self.cache_ttl = CACHE_TTL
    
    def _get_cache_key(self, spreadsheet_url: str, sheet_name: str) -> str:
        """Generate cache key for spreadsheet + sheet combination"""
        spreadsheet_id = self._extract_spreadsheet_id(spreadsheet_url)
        return f"{spreadsheet_id}:{sheet_name}"
    
    def _normalize_chinese_name(self, name: str) -> str:
        """
        Normalize Chinese sheet name by removing unwanted spaces
        
        RULES:
        - Do NOT translate any Chinese sheet names
        - Do NOT rename Chinese sheet names
        - ONLY remove unwanted internal spaces
        
        Examples:
        - "人 員資料庫" → "人員資料庫"
        - "硬 性限制" → "硬性限制"
        - "排 班週期" → "排班週期"
        - " 每月人力需求表" → "每月人力需求表"
        
        Args:
            name: Original sheet name
            
        Returns:
            Normalized name with spaces removed
        """
        if not name:
            return name
        # Remove regular spaces and full-width spaces (全角空格)
        return name.replace(' ', '').replace('　', '').strip()
    
    def _ensure_list_of_dicts(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        Global safety wrapper: Ensure all sheet data returns list[dict]
        
        This prevents 'int' object has no len() errors and guarantees
        that every sheet always returns a list of dictionaries.
        
        Args:
            df: pandas DataFrame
            
        Returns:
            List of dictionaries (never int, str, None, or empty dicts)
        """
        if df.empty:
            return []
        
        final_rows = []
        try:
            raw_records = df.to_dict('records')
            
            # Safety check: if raw_records is not a list, return empty
            if not isinstance(raw_records, list):
                logger.warning(f"DataFrame.to_dict('records') returned non-list: {type(raw_records)}, returning empty list")
                return []
            
            # Process each row - only keep valid dicts
            for idx, row in enumerate(raw_records):
                if isinstance(row, dict):
                    # Clean dict: remove None keys, skip empty dicts
                    clean_row = {k: v for k, v in row.items() if k is not None}
                    if clean_row:  # Only add non-empty rows
                        final_rows.append(clean_row)
                else:
                    # Skip non-dict rows (int, str, None, etc.)
                    logger.debug(f"Row {idx} is not a dict (type: {type(row)}), skipping")
                    continue
                    
        except Exception as e:
            logger.error(f"Error converting DataFrame to list[dict]: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return []
        
        return final_rows
    
    def _get_cached(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get data from cache if not expired"""
        if cache_key in _cache:
            data, timestamp = _cache[cache_key]
            age = time.time() - timestamp
            if age < self.cache_ttl:
                logger.debug(f"Cache hit for '{cache_key}' (age: {age:.1f}s)")
                return data
            else:
                logger.debug(f"Cache expired for '{cache_key}' (age: {age:.1f}s > {self.cache_ttl}s)")
                del _cache[cache_key]
        return None
    
    def _set_cached(self, cache_key: str, data: Dict[str, Any]) -> None:
        """Store data in cache"""
        _cache[cache_key] = (data, time.time())
        logger.debug(f"Cached data for '{cache_key}' (TTL: {self.cache_ttl}s)")
    
    def _read_with_retry(self, func, max_retries: int = 3, initial_delay: float = 2.0):
        """
        Execute a read function with retry logic for 429 (rate limit) errors
        
        Args:
            func: Callable function with no arguments (e.g., lambda: worksheet.get_all_values())
            max_retries: Maximum number of retries
            initial_delay: Initial delay in seconds (exponential backoff)
        
        Returns:
            Result from func, or error dict if all retries fail
        """
        last_error = None
        
        for attempt in range(max_retries):
            try:
                result = func()
                if attempt > 0:
                    logger.info(f"[RATE LIMIT] Successfully retried after {attempt} attempt(s)")
                return result
            except APIError as e:
                # Check if it's a 429 rate limit error
                error_code = getattr(e, 'code', None)
                if error_code == 429:
                    last_error = e
                    if attempt < max_retries - 1:
                        # Exponential backoff: 2s, 4s, 8s
                        delay = initial_delay * (2 ** attempt)
                        logger.warning(f"[RATE LIMIT] Google Sheets API quota exceeded (429). Retrying in {delay:.1f}s... (attempt {attempt + 1}/{max_retries})")
                        time.sleep(delay)
                        continue
                    else:
                        logger.error(f"[RATE LIMIT] Google Sheets API quota exceeded (429). All {max_retries} retries exhausted.")
                        return {
                            "success": False,
                            "error": f"Google Sheets API quota exceeded (429). Please try again in a few minutes.",
                            "error_code": 429,
                            "data": None
                        }
                
                # For other API errors, raise immediately
                raise
            except Exception as e:
                # For non-API errors, raise immediately
                raise
        
        # Should not reach here, but handle it
        if last_error:
            return {
                "success": False,
                "error": f"Google Sheets API error after {max_retries} retries: {str(last_error)}",
                "error_code": 429,
                "data": None
            }
        return {"success": False, "error": "Unknown error in retry logic", "data": None}
    
    def _get_credentials(self):
        """Get Google service account credentials"""
        if not GSPREAD_AVAILABLE:
            raise ImportError("gspread library not installed. Install with: pip install gspread google-auth")
        
        if self._credentials:
            return self._credentials
        
        # CRITICAL: Import os locally to avoid UnboundLocalError when executed via exec()
        import os as _os_creds
        
        if not _os_creds.path.exists(self.credentials_path):
            raise FileNotFoundError(
                f"Google credentials file not found: {self.credentials_path}. "
                "Please ensure service-account-creds.json exists or set GOOGLE_APPLICATION_CREDENTIALS environment variable."
            )
        
        try:
            scope = [
                'https://spreadsheets.google.com/feeds',
                'https://www.googleapis.com/auth/drive',
                'https://www.googleapis.com/auth/spreadsheets'
            ]
            self._credentials = Credentials.from_service_account_file(
                self.credentials_path, 
                scopes=scope
            )
            return self._credentials
        except Exception as e:
            logger.error(f"Error loading Google credentials: {e}")
            raise
    
    def _get_client(self):
        """Get authorized gspread client"""
        if self._client:
            return self._client
        
        creds = self._get_credentials()
        self._client = gspread.authorize(creds)
        return self._client
    
    def _extract_spreadsheet_id(self, url: str) -> str:
        """Extract spreadsheet ID from URL"""
        if '/spreadsheets/d/' in url:
            return url.split('/spreadsheets/d/')[1].split('/')[0]
        return url
    
    def list_sheets(self, spreadsheet_url: str) -> Dict[str, Any]:
        """
        List all sheets in a spreadsheet
        
        Args:
            spreadsheet_url: Full URL or spreadsheet ID
        
        Returns:
            Dictionary with sheet count and names
        """
        if not GSPREAD_AVAILABLE:
            return {
                "success": False,
                "error": "gspread library not installed",
                "count": 0,
                "sheets": []
            }
        
        try:
            client = self._get_client()
            spreadsheet_id = self._extract_spreadsheet_id(spreadsheet_url)
            spreadsheet = client.open_by_key(spreadsheet_id)
            
            worksheets = spreadsheet.worksheets()
            sheet_names = [ws.title for ws in worksheets]
            
            logger.info(f"Found {len(sheet_names)} sheets in spreadsheet: {spreadsheet.title}")
            
            return {
                "success": True,
                "count": len(sheet_names),
                "sheets": sheet_names,
                "spreadsheet_title": spreadsheet.title
            }
        except Exception as e:
            logger.error(f"Error listing sheets: {e}")
            return {
                "success": False,
                "error": str(e),
                "count": 0,
                "sheets": []
            }
    
    def validate_sheets(self, params_url: str, preschedule_url: Optional[str] = None) -> Dict[str, Any]:
        """
        Validate that Parameters and Preschedule sheets exist and are accessible
        
        Args:
            params_url: URL of Parameters sheet
            preschedule_url: Optional URL of Preschedule sheet
        
        Returns:
            Dictionary with validation results
        """
        if not GSPREAD_AVAILABLE:
            return {
                "success": False,
                "error": "gspread library not installed",
                "parameters_valid": False,
                "preschedule_valid": False
            }
        
        result = {
            "success": True,
            "parameters_valid": False,
            "preschedule_valid": False,
            "parameters_sheets": [],
            "preschedule_sheets": []
        }
        
        try:
            client = self._get_client()
            
            # Validate Parameters sheet
            try:
                params_id = self._extract_spreadsheet_id(params_url)
                params_spreadsheet = client.open_by_key(params_id)
                result["parameters_valid"] = True
                result["parameters_sheets"] = [ws.title for ws in params_spreadsheet.worksheets()]
                logger.info(f"Parameters sheet validated: {params_spreadsheet.title}")
            except Exception as e:
                result["parameters_valid"] = False
                result["parameters_error"] = str(e)
                logger.error(f"Parameters sheet validation failed: {e}")
            
            # Validate Preschedule sheet if provided
            if preschedule_url:
                try:
                    preschedule_id = self._extract_spreadsheet_id(preschedule_url)
                    preschedule_spreadsheet = client.open_by_key(preschedule_id)
                    result["preschedule_valid"] = True
                    result["preschedule_sheets"] = [ws.title for ws in preschedule_spreadsheet.worksheets()]
                    logger.info(f"Preschedule sheet validated: {preschedule_spreadsheet.title}")
                except Exception as e:
                    result["preschedule_valid"] = False
                    result["preschedule_error"] = str(e)
                    logger.error(f"Preschedule sheet validation failed: {e}")
            else:
                result["preschedule_valid"] = True  # Not required if not provided
            
            result["success"] = result["parameters_valid"] and result["preschedule_valid"]
            
        except Exception as e:
            logger.error(f"Error validating sheets: {e}")
            result["success"] = False
            result["error"] = str(e)
        
        return result
    
    def read_parameters_sheet(self, spreadsheet_url: str, sheet_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Read Parameters sheet data
        
        Args:
            spreadsheet_url: URL of Parameters sheet
            sheet_name: Optional specific sheet name (defaults to first sheet)
        
        Returns:
            Dictionary with data and metadata
        """
        if not GSPREAD_AVAILABLE:
            return {
                "success": False,
                "error": "gspread library not installed",
                "data": None
            }
        
        try:
            client = self._get_client()
            spreadsheet_id = self._extract_spreadsheet_id(spreadsheet_url)
            spreadsheet = client.open_by_key(spreadsheet_id)
            
            if sheet_name:
                worksheet = spreadsheet.worksheet(sheet_name)
            else:
                worksheet = spreadsheet.sheet1
            
            values = worksheet.get_all_values()
            
            if values:
                df = pd.DataFrame(values[1:], columns=values[0])
            else:
                df = pd.DataFrame()
            
            logger.info(f"Read {len(df)} rows from Parameters sheet: {worksheet.title}")
            
            # Use global safety wrapper to ensure list[dict]
            data_records = self._ensure_list_of_dicts(df)
            
            return {
                "success": True,
                "data": data_records,  # Always list[dict]
                "rows": len(data_records),
                "columns": list(df.columns) if not df.empty else [],
                "sheet_name": worksheet.title
            }
        except Exception as e:
            logger.error(f"Error reading Parameters sheet: {e}")
            return {
                "success": False,
                "error": str(e),
                "data": None
            }
    
    def read_preschedule_sheet(self, spreadsheet_url: str, sheet_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Read Preschedule sheet data
        
        Args:
            spreadsheet_url: URL of Preschedule sheet
            sheet_name: Optional specific sheet name
        
        Returns:
            Dictionary with data and metadata
        """
        if not GSPREAD_AVAILABLE:
            return {
                "success": False,
                "error": "gspread library not installed",
                "data": None
            }
        
        try:
            client = self._get_client()
            spreadsheet_id = self._extract_spreadsheet_id(spreadsheet_url)
            spreadsheet = client.open_by_key(spreadsheet_id)
            
            # Try common names for Pre-Schedule sheet
            if not sheet_name:
                sheet_name = "Pre-Schedule"
            
            try:
                worksheet = spreadsheet.worksheet(sheet_name)
            except WorksheetNotFound:
                # Fallback to first sheet if exact name not found
                worksheet = spreadsheet.sheet1
            
            values = worksheet.get_all_values()
            
            if values:
                df = pd.DataFrame(values[1:], columns=values[0])
            else:
                df = pd.DataFrame()
            
            logger.info(f"Read {len(df)} rows from Preschedule sheet: {worksheet.title}")
            
            # Use global safety wrapper to ensure list[dict]
            data_records = self._ensure_list_of_dicts(df)
            
            return {
                "success": True,
                "data": data_records,  # Always list[dict]
                "rows": len(data_records),
                "columns": list(df.columns) if not df.empty else [],
                "sheet_name": worksheet.title
            }
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error reading Preschedule sheet: {error_msg}")
            # Enhanced error logging for 404s
            if "404" in error_msg or "not found" in error_msg.lower():
                logger.error(f"  Sheet URL: {spreadsheet_url}")
                logger.error(f"  Sheet ID: {self._extract_spreadsheet_id(spreadsheet_url)}")
                logger.error(f"  Sheet Name: {sheet_name}")
            return {
                "success": False,
                "error": error_msg,
                "data": None,
                "sheet_url": spreadsheet_url,
                "sheet_id": self._extract_spreadsheet_id(spreadsheet_url) if hasattr(self, '_extract_spreadsheet_id') else None,
                "sheet_name": sheet_name
            }
    
    def read_sheet_by_name(self, spreadsheet_url: str, sheet_name: str) -> Dict[str, Any]:
        """
        Generic method to read any sheet by name from a spreadsheet
        Uses caching and retry logic for 429 rate limit errors
        
        Args:
            spreadsheet_url: URL of the spreadsheet
            sheet_name: Name of the sheet tab to read
        
        Returns:
            Dictionary with data and metadata
        """
        if not GSPREAD_AVAILABLE:
            return {
                "success": False,
                "error": "gspread library not installed",
                "data": None
            }
        
        # Check cache first
        cache_key = self._get_cache_key(spreadsheet_url, sheet_name)
        cached_result = self._get_cached(cache_key)
        if cached_result is not None:
            logger.info(f"Using cached data for sheet '{sheet_name}' (from cache)")
            return cached_result
        
        try:
            client = self._get_client()
            spreadsheet_id = self._extract_spreadsheet_id(spreadsheet_url)
            
            # Use retry logic for opening spreadsheet
            def open_spreadsheet():
                return client.open_by_key(spreadsheet_id)
            
            spreadsheet_result = self._read_with_retry(open_spreadsheet)
            if isinstance(spreadsheet_result, dict) and not spreadsheet_result.get("success"):
                return spreadsheet_result
            
            spreadsheet = spreadsheet_result
            
            # Normalize sheet name - remove stray spaces (but NOT translate Chinese)
            # This handles cases like "人 員資料庫" -> "人員資料庫"
            normalized_sheet_name = self._normalize_chinese_name(sheet_name) if sheet_name else sheet_name
            
            try:
                # Try exact name first
                try:
                    worksheet = spreadsheet.worksheet(sheet_name)
                except WorksheetNotFound:
                    # Try normalized name (without spaces)
                    if normalized_sheet_name != sheet_name:
                        try:
                            worksheet = spreadsheet.worksheet(normalized_sheet_name)
                            logger.info(f"Found sheet using normalized name: '{normalized_sheet_name}' (original: '{sheet_name}')")
                        except WorksheetNotFound:
                            raise  # Re-raise to trigger fallback logic
                    else:
                        raise  # Re-raise to trigger fallback logic
            except WorksheetNotFound:
                # Try alternative names with normalization
                all_sheets = [ws.title for ws in spreadsheet.worksheets()]
                # Also try normalized versions of available sheets
                normalized_available = [s.replace(' ', '') for s in all_sheets]
                
                # Check if normalized sheet name matches any available sheet
                matching_sheet = None
                for idx, avail_sheet in enumerate(all_sheets):
                    normalized_avail = self._normalize_chinese_name(avail_sheet)
                    if normalized_sheet_name == normalized_avail:
                        matching_sheet = avail_sheet
                        break
                
                if matching_sheet:
                    worksheet = spreadsheet.worksheet(matching_sheet)
                    logger.info(f"Found sheet using space-normalized match: '{matching_sheet}' (searched: '{sheet_name}')")
                else:
                    logger.warning(f"Sheet '{sheet_name}' not found. Available sheets: {all_sheets}")
                    result = {
                        "success": False,
                        "error": f"Sheet '{sheet_name}' not found. Available: {', '.join(all_sheets)}",
                        "data": None,
                        "available_sheets": all_sheets
                    }
                    # Don't cache errors
                    return result
            
            # Use retry logic for reading values (429 errors often happen here)
            def read_values():
                return worksheet.get_all_values()
            
            values_result = self._read_with_retry(read_values)
            if isinstance(values_result, dict) and not values_result.get("success"):
                return values_result
            
            values = values_result
            
            if values:
                df = pd.DataFrame(values[1:], columns=values[0])
            else:
                df = pd.DataFrame()
            
            rows_count = len(df)
            logger.info(f"Read {rows_count} rows from sheet '{sheet_name}': {worksheet.title}")
            
            # CRITICAL: Global safety wrapper - ensure ALL sheets return list[dict]
            # This prevents 'int' object has no len() errors
            data_records = self._ensure_list_of_dicts(df)
            
            result = {
                "success": True,
                "data": data_records,  # Always a list of dicts, never int/str/None
                "rows": len(data_records),  # Use actual count of valid records
                "columns": list(df.columns) if not df.empty else [],
                "sheet_name": worksheet.title
            }
            
            # Cache successful results only
            self._set_cached(cache_key, result)
            return result
            
        except APIError as e:
            # Check if it's a 429 error (should be handled by retry, but catch here as fallback)
            error_code = getattr(e, 'code', None)
            if error_code == 429:
                logger.error(f"[RATE LIMIT] Google Sheets API quota exceeded (429) reading sheet '{sheet_name}'")
                result = {
                    "success": False,
                    "error": "Google Sheets API quota exceeded (429). Please try again in a few minutes.",
                    "error_code": 429,
                    "data": None,
                    "sheet_url": spreadsheet_url,
                    "sheet_id": self._extract_spreadsheet_id(spreadsheet_url),
                    "sheet_name": sheet_name
                }
                return result
            raise  # Re-raise other API errors
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error reading sheet '{sheet_name}': {error_msg}")
            
            # Enhanced error logging for 404s and permission errors
            if "404" in error_msg or "not found" in error_msg.lower():
                sheet_id = self._extract_spreadsheet_id(spreadsheet_url)
                logger.error(f"  Spreadsheet ID: {sheet_id}")
                logger.error(f"  Spreadsheet URL: {spreadsheet_url}")
                logger.error(f"  Sheet Name: {sheet_name}")
                
                # Try to list available sheets for better error message
                try:
                    client = self._get_client()
                    spreadsheet = client.open_by_key(sheet_id)
                    all_sheets = [ws.title for ws in spreadsheet.worksheets()]
                    logger.error(f"  Available sheets: {all_sheets}")
                    error_msg = f"Sheet '{sheet_name}' not found in spreadsheet. Available sheets: {', '.join(all_sheets)}"
                except:
                    error_msg = f"Sheet '{sheet_name}' not found in spreadsheet (ID: {sheet_id})"
            
            return {
                "success": False,
                "error": error_msg,
                "data": None,
                "sheet_url": spreadsheet_url,
                "sheet_id": self._extract_spreadsheet_id(spreadsheet_url),
                "sheet_name": sheet_name
            }
    
    def read_employee_sheet(self, spreadsheet_url: str, sheet_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Read Employee sheet data
        
        Args:
            spreadsheet_url: URL of the spreadsheet containing Employee sheet
            sheet_name: Optional specific sheet name (defaults to trying multiple names)
        
        Returns:
            Dictionary with data and metadata
        """
        if sheet_name:
            return self.read_sheet_by_name(spreadsheet_url, sheet_name)
        
        # Try multiple names: English and Chinese
        possible_names = ["Employee", "人員資料庫", "人員"]
        for name in possible_names:
            result = self.read_sheet_by_name(spreadsheet_url, name)
            if result.get("success"):
                logger.info(f"Found Employee sheet as: {name}")
                return result
        # If all failed, return the last error
        return result
    
    def read_preferences_sheet(self, spreadsheet_url: str, sheet_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Read Preferences sheet data
        
        Args:
            spreadsheet_url: URL of the spreadsheet containing Preferences sheet
            sheet_name: Optional specific sheet name (defaults to trying multiple names)
        
        Returns:
            Dictionary with data and metadata
        """
        if sheet_name:
            return self.read_sheet_by_name(spreadsheet_url, sheet_name)
        
        # Try multiple names: English and Chinese
        possible_names = ["Preferences", "員工預排班表", "預排班表", "Pre-Schedule"]
        for name in possible_names:
            result = self.read_sheet_by_name(spreadsheet_url, name)
            if result.get("success"):
                logger.info(f"Found Preferences sheet as: {name}")
                return result
        # If all failed, return the last error
        return result
    
    def read_designation_flow_sheet(self, spreadsheet_url: str, sheet_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Read Designation Flow sheet data
        
        Args:
            spreadsheet_url: URL of the spreadsheet containing Designation Flow sheet
            sheet_name: Optional specific sheet name (defaults to "Designation Flow")
        
        Returns:
            Dictionary with data and metadata
        """
        if not sheet_name:
            sheet_name = "Designation Flow"
        return self.read_sheet_by_name(spreadsheet_url, sheet_name)
    
    def read_final_output_sheet(self, spreadsheet_url: str, sheet_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Read Final Output sheet data
        
        Args:
            spreadsheet_url: URL of the spreadsheet containing Final Output sheet
            sheet_name: Optional specific sheet name (defaults to "Final Output" or "Results")
        
        Returns:
            Dictionary with data and metadata
        """
        if not sheet_name:
            # Try multiple names: English and Chinese (order: most common first)
            # Matches required alias mapping: "排班結果表", "結果表", "Schedule Results"
            possible_names = ["排班結果表", "結果表", "Schedule Results", "Final Output", "Results"]
            for name in possible_names:
                result = self.read_sheet_by_name(spreadsheet_url, name)
                if result.get("success"):
                    logger.info(f"Found Final Output/Results sheet as: {name}")
                    return result
            # If all failed, return the last error
            return result
        return self.read_sheet_by_name(spreadsheet_url, sheet_name)
    
    def write_results_sheet(
        self, 
        data: List[Dict[str, Any]] or pd.DataFrame,
        spreadsheet_url: str,
        sheet_name: str = "Schedule_Results",
        clear_existing: bool = True
    ) -> Dict[str, Any]:
        """
        Write schedule results to Results sheet
        
        Args:
            data: List of dictionaries or pandas DataFrame
            spreadsheet_url: URL of Results sheet
            sheet_name: Name of sheet to write to
            clear_existing: Whether to clear existing data
        
        Returns:
            Dictionary with write results
        """
        if not GSPREAD_AVAILABLE:
            return {
                "success": False,
                "error": "gspread library not installed"
            }
        
        try:
            client = self._get_client()
            spreadsheet_id = self._extract_spreadsheet_id(spreadsheet_url)
            spreadsheet = client.open_by_key(spreadsheet_id)
            
            # Get or create worksheet
            try:
                worksheet = spreadsheet.worksheet(sheet_name)
            except WorksheetNotFound:
                worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=100, cols=20)
            
            # Convert data to list of lists
            if isinstance(data, pd.DataFrame):
                values = [data.columns.tolist()] + data.values.tolist()
            elif isinstance(data, list) and len(data) > 0:
                if isinstance(data[0], dict):
                    columns = list(data[0].keys())
                    values = [columns] + [[row.get(col, '') for col in columns] for row in data]
                else:
                    values = data
            else:
                values = []
            
            # Clear existing if requested
            if clear_existing and worksheet.row_count > 0:
                worksheet.clear()
            
            # Write data
            if values:
                worksheet.update(values, value_input_option='USER_ENTERED')
            
            logger.info(f"Wrote {len(values) - 1 if values else 0} rows to Results sheet: {worksheet.title}")
            
            return {
                "success": True,
                "rows_written": len(values) - 1 if values else 0,
                "sheet_name": worksheet.title
            }
        except Exception as e:
            logger.error(f"Error writing Results sheet: {e}")
            return {
                "success": False,
                "error": str(e)
            }


# Convenience functions
def list_sheets(spreadsheet_url: str, credentials_path: Optional[str] = None) -> Dict[str, Any]:
    """List sheets in a spreadsheet"""
    service = GoogleSheetsService(credentials_path)
    return service.list_sheets(spreadsheet_url)


def validate_sheets(params_url: str, preschedule_url: Optional[str] = None, credentials_path: Optional[str] = None) -> Dict[str, Any]:
    """Validate Parameters and Preschedule sheets"""
    service = GoogleSheetsService(credentials_path)
    return service.validate_sheets(params_url, preschedule_url)


def fetch_schedule_data(schedule_def_id: str, credentials_path: Optional[str] = None, user_role: Optional[str] = None) -> Dict[str, Any]:
    """
    Fetch all schedule data for a schedule definition (all 6 sheets)
    
    Args:
        schedule_def_id: Schedule definition ID
        credentials_path: Optional credentials path
        user_role: User role for filtering (sysadmin, clientadmin, schedulemanager, employee)
    
    Returns:
        Dictionary with all 6 sheets: Parameters, Employee, Preferences, Pre-Schedule, Designation Flow, Final Output
    """
    # CRITICAL: Import os at function level to avoid UnboundLocalError
    # When code is executed via exec(), global os declaration might not work correctly
    # So we import os locally with a different name and use it directly
    # This completely avoids any issues with global/local variable conflicts
    import os as _os_func
    import sys
    
    try:
        # Import here to avoid circular dependencies
        # Use _os_func for all os operations to avoid UnboundLocalError
        # Add backend to path if not already there
        # File is at backend/refactor/services/google_sheets/service.py, so go up 3 levels to get backend
        backend_path = _os_func.path.dirname(_os_func.path.dirname(_os_func.path.dirname(_os_func.path.abspath(__file__))))
        if backend_path not in sys.path:
            sys.path.insert(0, backend_path)
        
        from flask import current_app
        from app.models import ScheduleDefinition
        from app import db
        
        # Use Flask app context if available
        if current_app:
            with current_app.app_context():
                schedule_def = ScheduleDefinition.query.get(schedule_def_id)
        else:
            # Fallback: create app context
            from app import create_app
            app = create_app()
            with app.app_context():
                schedule_def = ScheduleDefinition.query.get(schedule_def_id)
        
        if not schedule_def:
            return {
                "success": False,
                "error": "Schedule definition not found"
            }
        
        service = GoogleSheetsService(credentials_path)
        
        # Use paramsSheetURL as the main spreadsheet (assumes all sheets are in same spreadsheet)
        # If sheets are in different spreadsheets, we'll try both URLs
        main_spreadsheet_url = schedule_def.paramsSheetURL
        results_spreadsheet_url = schedule_def.resultsSheetURL
        
        # Read ALL sheets using Chinese sheet names
        # Note: read_sheet_by_name will normalize spaces (remove stray spaces) but NOT translate
        # Sheet name mapping:
        #   人員資料庫 -> employee
        #   員工預排班表 -> preferences
        #   排班結果表 -> final_output
        #   軟性限制 -> parameters
        #   硬性限制 -> hard_constraints
        #   每月人力需求表 -> monthly_demand
        #   班別定義表 -> shift_definitions
        #   排班週期 -> schedule_cycle
        #   使用說明 -> usage_instructions
        
        # Read all required input sheets from main spreadsheet
        params_data = service.read_sheet_by_name(main_spreadsheet_url, "軟性限制")  # Soft constraints (Parameters)
        hard_constraints_data = service.read_sheet_by_name(main_spreadsheet_url, "硬性限制")  # Hard constraints
        employee_data = service.read_sheet_by_name(main_spreadsheet_url, "人員資料庫")  # Employee database
        preferences_data = service.read_sheet_by_name(main_spreadsheet_url, "員工預排班表")  # Employee pre-schedule
        schedule_cycle_data = service.read_sheet_by_name(main_spreadsheet_url, "排班週期")  # Schedule cycle
        monthly_demand_data = service.read_sheet_by_name(main_spreadsheet_url, "每月人力需求表")  # Monthly demand
        shift_definitions_data = service.read_sheet_by_name(main_spreadsheet_url, "班別定義表")  # Shift definitions
        usage_instructions_data = service.read_sheet_by_name(main_spreadsheet_url, "使用說明")  # Usage instructions (optional)
        
        # Read output sheet from results spreadsheet
        final_output_data = service.read_sheet_by_name(results_spreadsheet_url, "排班結果表")  # Final Output (Schedule Results)
        
        # Build response with all sheets
        result = {
            "success": True,
            "schedule_def_id": schedule_def_id,
            "schedule_name": schedule_def.scheduleName,
            "sheets": {
                "parameters": params_data,  # 軟性限制
                "hard_constraints": hard_constraints_data,  # 硬性限制
                "employee": employee_data,  # 人員資料庫
                "preferences": preferences_data,  # 員工預排班表
                "schedule_cycle": schedule_cycle_data,  # 排班週期
                "monthly_demand": monthly_demand_data,  # 每月人力需求表
                "shift_definitions": shift_definitions_data,  # 班別定義表
                "usage_instructions": usage_instructions_data,  # 使用說明
                "final_output": final_output_data  # 排班結果表
            }
        }
        
        # Apply role-based filtering
        if user_role:
            result = _filter_by_role(result, user_role)
        
        # Overall success if at least critical sheets are successful
        # Critical sheets: Employee, Preferences, Final Output
        overall_success = (
            employee_data.get("success", False) and 
            preferences_data.get("success", False) and
            final_output_data.get("success", False)
        )
        result["success"] = overall_success
        
        return result
    except Exception as e:
        logger.error(f"Error fetching schedule data: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            "success": False,
            "error": str(e)
        }


def _filter_by_role(data: Dict[str, Any], user_role: str) -> Dict[str, Any]:
    """
    Filter sheet data based on user role
    
    Args:
        data: Response data with all sheets
        user_role: User role (sysadmin, clientadmin, schedulemanager, employee)
    
    Returns:
        Filtered data based on role permissions
    """
    # SysAdmin sees everything
    if user_role == "sysadmin":
        return data
    
    # ClientAdmin sees most things except sensitive employee data
    if user_role == "clientadmin":
        filtered_data = data.copy()
        # Can see all sheets but may have limited columns in employee sheet
        return filtered_data
    
    # ScheduleManager sees operational sheets
    if user_role == "schedulemanager":
        filtered_data = data.copy()
        # Can see Parameters, Preferences, Pre-Schedule, Designation Flow, Final Output
        # Limited employee data
        if "sheets" in filtered_data and "employee" in filtered_data["sheets"]:
            # Filter sensitive columns from employee sheet if needed
            pass
        return filtered_data
    
    # Employee sees only their own data and final output
    if user_role == "employee":
        filtered_data = data.copy()
        # Employees see limited data - mainly final output and their preferences
        # Remove sensitive sheets
        if "sheets" in filtered_data:
            # Keep only Preferences (their own) and Final Output
            filtered_data["sheets"] = {
                "preferences": filtered_data["sheets"].get("preferences", {}),
                "final_output": filtered_data["sheets"].get("final_output", {})
            }
        return filtered_data
    
    # Default: return as-is
    return data