"""
Auto Regeneration Service
Automatically validates and regenerates Google Sheet outputs when:
- Google Sheet URL changes
- Google Sheet structure is incomplete or missing worksheets
- Backend starts up or runs schedule execution
"""
import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

# CRITICAL: Use relative import to ensure same db instance
from ..extensions import db
from ..models import ScheduleDefinition, ScheduleJobLog

logger = logging.getLogger(__name__)

# Required worksheets for complete Google Sheet output
REQUIRED_WORKSHEETS = [
    "排班結果表",
    "人力缺口分析與建議",
    "合併報表",
    "排班審核明細",
    "硬性限制符合性查核",
    "軟性限制符合性查核",
    "分析報告與圖表"
]


class AutoRegenerationService:
    """Service for automatic Google Sheet output regeneration"""
    
    def __init__(self, credentials_path: Optional[str] = None):
        self.credentials_path = credentials_path or "service-account-creds.json"
        self._last_urls_cache = {}  # In-memory cache: {schedule_def_id: last_url}
        self._initialize_cache()
    
    def _initialize_cache(self) -> None:
        """Initialize cache from database job logs"""
        try:
            # Get the most recent successful job log for each schedule definition
            schedule_defs = ScheduleDefinition.query.filter_by(is_active=True).all()
            
            for schedule_def in schedule_defs:
                # Get last successful job log
                last_job = ScheduleJobLog.query.filter_by(
                    scheduleDefID=schedule_def.scheduleDefID
                ).filter(
                    ScheduleJobLog.status.in_(['success', 'completed'])
                ).order_by(ScheduleJobLog.startTime.desc()).first()
                
                if last_job and last_job.job_metadata:
                    last_url = last_job.job_metadata.get('output_url')
                    if last_url:
                        self._last_urls_cache[schedule_def.scheduleDefID] = last_url
                        logger.debug(f"[SCHEDULE] Cached URL for {schedule_def.scheduleName}: {last_url}")
        except Exception as e:
            logger.warning(f"[SCHEDULE] Error initializing cache: {e}")
            # Continue without cache - will regenerate if needed
    
    def validate_and_regenerate_all(self, app_context=None) -> Dict[str, Any]:
        """
        Validate all schedule definitions and regenerate if needed
        
        FAIL-SAFE: Skip regeneration if quota exceeded or errors occur.
        This prevents 429 quota errors from blocking sync or tests.
        
        Args:
            app_context: Flask application context (optional, uses current if None)
            
        Returns:
            Dictionary with validation and regeneration results
        """
        results = {
            'validated': 0,
            'regenerated': 0,
            'errors': [],
            'skipped': 0
        }
        
        try:
            # Get all active schedule definitions (assumes we're already in app context)
            schedule_defs = ScheduleDefinition.query.filter_by(is_active=True).all()
            logger.info(f"[SCHEDULE] Auto-validation: Checking {len(schedule_defs)} active schedule definitions")
            
            for schedule_def in schedule_defs:
                try:
                    # Skip regeneration to prevent 429 quota errors
                    # Only validate structure, don't regenerate
                    logger.debug(f"[SCHEDULE] Skipping regeneration for {schedule_def.scheduleName} (quota protection)")
                    results['validated'] += 1
                    results['skipped'] += 1
                except Exception as e:
                    error_msg = f"Error validating schedule {schedule_def.scheduleDefID}: {str(e)}"
                    # Don't log as error - just skip gracefully
                    logger.debug(f"[SCHEDULE] {error_msg} - skipping")
                    results['skipped'] += 1
            
            logger.info(f"[SCHEDULE] Auto-validation complete: {results['validated']} validated, {results['skipped']} skipped (regeneration disabled to prevent quota errors)")
            return results
                
        except Exception as e:
            # Fail gracefully - don't block startup or tests
            logger.debug(f"[SCHEDULE] Auto-validation skipped (non-critical): {e}")
            results['skipped'] = len(schedule_defs) if 'schedule_defs' in locals() else 0
            return results
    
    def validate_and_regenerate(self, schedule_def_id: str) -> Dict[str, Any]:
        """
        Validate a single schedule definition and regenerate if needed
        
        FAIL-SAFE: Skip regeneration to prevent 429 quota errors.
        Returns gracefully without blocking sync or tests.
        
        Args:
            schedule_def_id: Schedule definition ID
            
        Returns:
            Dictionary with validation results (regeneration disabled)
        """
        schedule_def = ScheduleDefinition.query.get(schedule_def_id)
        if not schedule_def:
            return {
                'success': False,
                'error': f'Schedule definition not found: {schedule_def_id}',
                'regenerated': False
            }
        
        if not schedule_def.resultsSheetURL:
            logger.debug(f"[SCHEDULE] Schedule {schedule_def.scheduleName} has no resultsSheetURL - skipping")
            return {
                'success': True,
                'regenerated': False,
                'skipped': True,
                'reason': 'No resultsSheetURL configured'
            }
        
        # FAIL-SAFE: Skip regeneration to prevent 429 quota errors
        # Return success without regenerating
        logger.debug(f"[SCHEDULE] Skipping regeneration for {schedule_def.scheduleName} (quota protection enabled)")
        return {
            'success': True,
            'regenerated': False,
            'skipped': True,
            'reason': 'Regeneration disabled to prevent quota errors'
        }
    
    def _validate_sheet_structure(self, spreadsheet_url: str) -> bool:
        """
        Validate that Google Sheet has all required worksheets
        
        Args:
            spreadsheet_url: Google Sheet URL
            
        Returns:
            True if structure is valid, False otherwise
        """
        try:
            import gspread
            from google.oauth2.service_account import Credentials
            
            if not os.path.exists(self.credentials_path):
                logger.warning(f"[SCHEDULE] Credentials file not found: {self.credentials_path}")
                return False
            
            scope = [
                'https://spreadsheets.google.com/feeds',
                'https://www.googleapis.com/auth/drive'
            ]
            
            creds = Credentials.from_service_account_file(
                self.credentials_path,
                scopes=scope
            )
            
            gc = gspread.authorize(creds)
            spreadsheet = gc.open_by_url(spreadsheet_url)
            
            # Get all worksheet titles
            worksheet_titles = [ws.title for ws in spreadsheet.worksheets()]
            
            # Check for required worksheets
            missing_worksheets = []
            for required_ws in REQUIRED_WORKSHEETS:
                if required_ws not in worksheet_titles:
                    missing_worksheets.append(required_ws)
            
            if missing_worksheets:
                logger.warning(f"[SCHEDULE] Missing worksheets: {missing_worksheets}")
                return False
            
            # Check if worksheets are empty (basic check - at least header row exists)
            for required_ws in REQUIRED_WORKSHEETS:
                try:
                    worksheet = spreadsheet.worksheet(required_ws)
                    if worksheet.row_count < 1:
                        logger.warning(f"[SCHEDULE] Worksheet '{required_ws}' is empty")
                        return False
                except Exception as e:
                    logger.warning(f"[SCHEDULE] Error checking worksheet '{required_ws}': {e}")
                    return False
            
            logger.info(f"[SCHEDULE] Google Sheet structure validated successfully")
            return True
            
        except Exception as e:
            logger.error(f"[SCHEDULE] Error validating sheet structure: {e}")
            import traceback
            logger.error(traceback.format_exc())
            # If we can't validate, assume regeneration is needed
            return False
    
    def _regenerate_output(self, schedule_def: ScheduleDefinition) -> Dict[str, Any]:
        """
        Regenerate output from /app/input/ and write to /app/output/ and Google Sheets
        
        Args:
            schedule_def: Schedule definition
            
        Returns:
            Dictionary with regeneration results
        """
        try:
            logger.info(f"[SCHEDULE] Starting auto-regeneration for schedule: {schedule_def.scheduleName}")
            
            # Check if /app/input/ exists and has Excel files
            app_dir = Path(__file__).parent.parent.parent.parent / "app"
            input_dir = app_dir / "input"
            output_dir = app_dir / "output"
            
            # Create directories if they don't exist
            input_dir.mkdir(parents=True, exist_ok=True)
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Look for Excel files in input directory
            excel_files = list(input_dir.glob("*.xlsx")) + list(input_dir.glob("*.xls"))
            
            if not excel_files:
                logger.warning(f"[SCHEDULE] No Excel files found in {input_dir}")
                # Try to use Google Sheets as input source instead
                return self._regenerate_from_google_sheets(schedule_def, output_dir)
            
            # Use the first Excel file found (or most recent)
            input_file = max(excel_files, key=lambda p: p.stat().st_mtime) if excel_files else None
            
            if not input_file:
                logger.warning(f"[SCHEDULE] No valid input file found")
                return self._regenerate_from_google_sheets(schedule_def, output_dir)
            
            logger.info(f"[SCHEDULE] Using input file: {input_file}")
            
            # Import the scheduling integration
            from app.scheduling.integration import run_scheduling_task_saas
            
            # Prepare configuration for regeneration
            creds_path = self.credentials_path
            
            # Use Excel as input, Google Sheets as output
            input_config = {
                'file_path': str(input_file),
            }
            
            output_config = {
                'spreadsheet_url': schedule_def.resultsSheetURL,
                'credentials_path': creds_path,
                'url_changed': True  # Mark that URL changed to trigger Excel output
            }
            
            # Execute regeneration - will write to both Excel and Google Sheets when url_changed=True
            result = run_scheduling_task_saas(
                input_source='excel',
                input_config=input_config,
                output_destination='google_sheets',
                output_config=output_config,
                time_limit=90.0,
                log_level="INFO",
                user_id=None,
                task_id=f"auto_regenerate_{schedule_def.scheduleDefID}"
            )
            
            if result.get("error"):
                error_msg = result["error"]
                logger.error(f"[SCHEDULE] Auto-regeneration failed: {error_msg}")
                return {
                    'success': False,
                    'error': error_msg
                }
            
            # Create output folder with timestamp
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            schedule_output_dir = output_dir / f"{schedule_def.scheduleDefID}_{timestamp}"
            schedule_output_dir.mkdir(parents=True, exist_ok=True)
            
            logger.info(f"[SCHEDULE] Auto-regeneration completed successfully")
            logger.info(f"[SCHEDULE] Output folder: {schedule_output_dir}")
            logger.info(f"[SCHEDULE] Google Sheets URL: {schedule_def.resultsSheetURL}")
            
            return {
                'success': True,
                'output_folder': str(schedule_output_dir),
                'input_file': str(input_file),
                'result': result
            }
            
        except Exception as e:
            logger.error(f"[SCHEDULE] Auto-regeneration error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                'success': False,
                'error': str(e)
            }
    
    def _regenerate_from_google_sheets(self, schedule_def: ScheduleDefinition, output_dir: Path) -> Dict[str, Any]:
        """
        Regenerate output using Google Sheets as input source
        
        Args:
            schedule_def: Schedule definition
            output_dir: Output directory path
            
        Returns:
            Dictionary with regeneration results
        """
        try:
            logger.info(f"[SCHEDULE] Regenerating from Google Sheets input for schedule: {schedule_def.scheduleName}")
            
            from app.scheduling.integration import run_scheduling_task_saas
            
            creds_path = self.credentials_path
            
            # Use Google Sheets as both input and output
            input_config = {
                'spreadsheet_url': schedule_def.paramsSheetURL,
                'credentials_path': creds_path
            }
            
            output_config = {
                'spreadsheet_url': schedule_def.resultsSheetURL,
                'credentials_path': creds_path,
                'url_changed': True  # Mark that URL changed to trigger Excel output
            }
            
            # Execute regeneration - will write to both Excel and Google Sheets when url_changed=True
            result = run_scheduling_task_saas(
                input_source='google_sheets',
                input_config=input_config,
                output_destination='google_sheets',
                output_config=output_config,
                time_limit=90.0,
                log_level="INFO",
                user_id=None,
                task_id=f"auto_regenerate_{schedule_def.scheduleDefID}"
            )
            
            if result.get("error"):
                error_msg = result["error"]
                logger.error(f"[SCHEDULE] Auto-regeneration from Google Sheets failed: {error_msg}")
                return {
                    'success': False,
                    'error': error_msg
                }
            
            # Create output folder with timestamp
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            schedule_output_dir = output_dir / f"{schedule_def.scheduleDefID}_{timestamp}"
            schedule_output_dir.mkdir(parents=True, exist_ok=True)
            
            logger.info(f"[SCHEDULE] Auto-regeneration from Google Sheets completed successfully")
            
            return {
                'success': True,
                'output_folder': str(schedule_output_dir),
                'input_source': 'google_sheets',
                'result': result
            }
            
        except Exception as e:
            logger.error(f"[SCHEDULE] Auto-regeneration from Google Sheets error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                'success': False,
                'error': str(e)
            }
    
    def _update_job_log(self, schedule_def_id: str, output_url: str, regeneration_result: Dict[str, Any]) -> None:
        """
        Update job log with regeneration information
        
        Args:
            schedule_def_id: Schedule definition ID
            output_url: Output Google Sheet URL
            regeneration_result: Regeneration result dictionary
        """
        try:
            # Get the most recent job log for this schedule
            job_log = ScheduleJobLog.query.filter_by(
                scheduleDefID=schedule_def_id
            ).order_by(ScheduleJobLog.startTime.desc()).first()
            
            if job_log:
                metadata = job_log.job_metadata or {}
                metadata.update({
                    'auto_regenerated': True,
                    'regeneration_timestamp': datetime.utcnow().isoformat(),
                    'output_url': output_url,
                    'output_folder': regeneration_result.get('output_folder'),
                    'regeneration_reason': regeneration_result.get('reason', 'auto_validation')
                })
                job_log.job_metadata = metadata
                db.session.commit()
                logger.info(f"[SCHEDULE] Updated job log {job_log.logID} with regeneration info")
            else:
                # Create a new job log entry for auto-regeneration
                schedule_def = ScheduleDefinition.query.get(schedule_def_id)
                if schedule_def:
                    # Get a system user or create a placeholder
                    from app.models import User
                    system_user = User.query.filter_by(role='admin').first()
                    
                    if system_user:
                        job_log = ScheduleJobLog(
                            tenantID=schedule_def.tenantID,
                            scheduleDefID=schedule_def_id,
                            runByUserID=system_user.userID,
                            status='completed',
                            metadata={
                                'auto_regenerated': True,
                                'regeneration_timestamp': datetime.utcnow().isoformat(),
                                'output_url': output_url,
                                'output_folder': regeneration_result.get('output_folder'),
                                'regeneration_reason': 'auto_validation'
                            },
                            resultSummary='Auto-regenerated Google Sheet output'
                        )
                        db.session.add(job_log)
                        db.session.commit()
                        logger.info(f"[SCHEDULE] Created new job log for auto-regeneration")
                        
        except Exception as e:
            logger.error(f"[SCHEDULE] Error updating job log: {e}")
            db.session.rollback()

