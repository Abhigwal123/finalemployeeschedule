"""
Celery task definitions
"""

import logging
import traceback
from datetime import datetime
from typing import Dict, Any

from flask import current_app

from app.celery_app import celery
from ..extensions import db

from app.models.schedule_task import ScheduleTask
from ..scheduling.integration import run_scheduling_task_saas

# Setup logger
logger = logging.getLogger(__name__)


@celery.task(bind=True, name="app.tasks.process_schedule_task")
def process_schedule_task(self, task_db_id: int) -> Dict[str, Any]:
    """Process a schedule task by database id.

    Updates task status/progress in the database and returns the result dict.
    """
    celery_task_id = self.request.id
    logger.info(f"[Task {celery_task_id}] Starting processing for DB task {task_db_id}")
    
    app = current_app._get_current_object()
    with app.app_context():
        try:
            task: ScheduleTask = ScheduleTask.query.get(task_db_id)
            if not task:
                error_msg = f"Task id {task_db_id} not found in database"
                logger.error(f"[Task {celery_task_id}] {error_msg}")
                return {"error": error_msg}

            task.status = "running"
            task.progress = 5
            task.started_at = datetime.utcnow()
            task.task_id = celery_task_id
            db.session.commit()
            logger.info(f"[Task {celery_task_id}] Task marked as running in database")

            self.update_state(state='PROGRESS', meta={'progress': 10, 'status': 'Loading input data...'})
            task.progress = 10
            db.session.commit()
            logger.info(f"[Task {celery_task_id}] Loading data from {task.input_source}")

            result = run_scheduling_task_saas(
                input_source=task.input_source,
                input_config=task.input_config,
                output_destination=task.output_destination,
                output_config=task.output_config,
                time_limit=task.time_limit,
                debug_shift=task.debug_shift,
                log_level=task.log_level,
                user_id=task.user_id,
                task_id=celery_task_id,
            )

            logger.info(f"[Task {celery_task_id}] Scheduling task completed, processing result...")

            if isinstance(result, dict) and "error" not in result:
                task.status = "success"
                task.progress = 100
                task.result_data = result
                task.completed_at = datetime.utcnow()
                
                if task.input_source == "google_sheets" and "spreadsheet_url" in task.input_config:
                    task.input_sheet_url = task.input_config["spreadsheet_url"]
                if task.output_destination == "google_sheets" and "spreadsheet_url" in task.output_config:
                    task.output_sheet_url = task.output_config["spreadsheet_url"]
                
                db.session.commit()
                logger.info(f"[Task {celery_task_id}] Task completed successfully: {result.get('summary', 'N/A')}")
                
                self.update_state(state='SUCCESS', meta={
                    'progress': 100,
                    'status': 'Task completed successfully',
                    'result': result
                })
            else:
                error_msg = result.get("error") if isinstance(result, dict) else str(result)
                task.status = "failed"
                task.progress = 100
                task.error_message = error_msg
                task.completed_at = datetime.utcnow()
                db.session.commit()
                logger.error(f"[Task {celery_task_id}] Task failed: {error_msg}")
                
                self.update_state(state='FAILURE', meta={
                    'progress': 100,
                    'status': 'Task failed',
                    'error': error_msg
                })
            
            return result

        except Exception as e:
            error_msg = str(e)
            error_trace = traceback.format_exc()
            logger.error(f"[Task {celery_task_id}] Unhandled exception: {error_msg}\n{error_trace}")
            
            try:
                task: ScheduleTask = ScheduleTask.query.get(task_db_id)
                if task:
                    task.status = "failed"
                    task.progress = 100
                    task.error_message = f"{error_msg}\n\nTraceback:\n{error_trace}"
                    task.completed_at = datetime.utcnow()
                    db.session.commit()
            except Exception as db_error:
                logger.error(f"[Task {celery_task_id}] Failed to update database after error: {db_error}")
            
            self.update_state(state='FAILURE', meta={
                'progress': 100,
                'status': 'Task failed with exception',
                'error': error_msg
            })
            
            return {"error": error_msg}


