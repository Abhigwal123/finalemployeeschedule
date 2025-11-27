"""
Celery tasks for schedule processing
"""

import os
import sys
import json
import traceback
from datetime import datetime
from typing import Dict, Any, Optional
from celery import current_task
from flask import current_app

from ..extensions import db
from app.models.schedule_task import ScheduleTask

# Get Google credentials from environment
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "service-account-creds.json")

# Add the original app directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), "../../../"))

# Import the SaaS scheduling integration
try:
    from ..scheduling.integration import run_scheduling_task_saas
except ImportError:
    # Fallback if integration is not available
    def run_scheduling_task_saas(*args, **kwargs):
        return {"error": "Scheduling integration not available"}

from app.celery_app import celery as celery_app


def update_task_status(
    task_id: str, 
    status: str, 
    progress: int = None, 
    result_data: Dict[str, Any] = None, 
    error_message: str = None,
    output_file_path: str = None,
    chart_file_path: str = None,
    output_sheet_url: str = None
):
    """Update task status in database"""
    session = db.session
    try:
        task = session.query(ScheduleTask).filter(ScheduleTask.task_id == task_id).first()
        if task:
            task.status = status
            if progress is not None:
                task.progress = progress
            if result_data is not None:
                task.result_data = result_data
            if error_message is not None:
                task.error_message = error_message
            if output_file_path is not None:
                task.output_file_path = output_file_path
            if chart_file_path is not None:
                task.chart_file_path = chart_file_path
            if output_sheet_url is not None:
                task.output_sheet_url = output_sheet_url
            
            if status == "running" and not task.started_at:
                task.started_at = datetime.utcnow()
            elif status in ["success", "failed", "cancelled"]:
                task.completed_at = datetime.utcnow()
            
            session.commit()
    except Exception as e:
        session.rollback()
        print(f"Error updating task status: {e}")


@celery_app.task(bind=True, name="app.tasks.schedule.process_schedule_task")
def process_schedule_task(
    self,
    task_id: str,
    user_id: int,
    input_source: str,
    input_config: Dict[str, Any],
    output_destination: str,
    output_config: Dict[str, Any],
    time_limit: int = 90,
    debug_shift: Optional[str] = None,
    log_level: str = "INFO"
):
    """
    Process schedule task using the original scheduling logic
    """
    app = current_app._get_current_object()
    with app.app_context():
        try:
            update_task_status(task_id, "running", progress=0)
            
            current_task.update_state(state="PROGRESS", meta={"progress": 10})
            update_task_status(task_id, "running", progress=10)
            
            if input_source == "excel":
                input_config_processed = {
                    "file_path": input_config.get("file_path")
                }
            elif input_source == "google_sheets":
                input_config_processed = {
                    "spreadsheet_url": input_config.get("spreadsheet_url"),
                    "credentials_path": input_config.get("credentials_path", GOOGLE_CREDENTIALS_FILE)
                }
            else:
                raise ValueError(f"Unsupported input source: {input_source}")
            
            current_task.update_state(state="PROGRESS", meta={"progress": 20})
            update_task_status(task_id, "running", progress=20)
            
            if output_destination == "excel":
                output_config_processed = {
                    "output_path": output_config.get("output_path")
                }
            elif output_destination == "google_sheets":
                output_config_processed = {
                    "spreadsheet_url": output_config.get("spreadsheet_url"),
                    "credentials_path": output_config.get("credentials_path", GOOGLE_CREDENTIALS_FILE)
                }
            else:
                raise ValueError(f"Unsupported output destination: {output_destination}")
            
            current_task.update_state(state="PROGRESS", meta={"progress": 30})
            update_task_status(task_id, "running", progress=30)
            
            result = run_scheduling_task_saas(
                input_source=input_source,
                input_config=input_config_processed,
                output_destination=output_destination,
                output_config=output_config_processed,
                time_limit=time_limit,
                debug_shift=debug_shift,
                log_level=log_level,
                user_id=user_id,
                task_id=task_id
            )
            
            current_task.update_state(state="PROGRESS", meta={"progress": 80})
            update_task_status(task_id, "running", progress=80)
            
            if result.get("error"):
                update_task_status(
                    task_id, 
                    "failed", 
                    progress=100, 
                    error_message=result["error"]
                )
                return {
                    "status": "failed",
                    "error": result["error"]
                }
            
            output_file_path = None
            chart_file_path = None
            output_sheet_url = None
            
            if output_destination == "excel":
                output_file_path = output_config_processed.get("output_path")
            elif output_destination == "google_sheets":
                output_sheet_url = output_config_processed.get("spreadsheet_url")
            
            update_task_status(
                task_id,
                "success",
                progress=100,
                result_data=result,
                output_file_path=output_file_path,
                chart_file_path=chart_file_path,
                output_sheet_url=output_sheet_url
            )
            
            return {
                "status": "success",
                "result": result
            }
            
        except Exception as e:
            error_message = f"Task failed with error: {str(e)}\n{traceback.format_exc()}"
            
            update_task_status(
                task_id,
                "failed",
                progress=100,
                error_message=error_message
            )
            
            return {
                "status": "failed",
                "error": error_message
            }
