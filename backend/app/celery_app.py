"""
Central Celery application configured with the Flask app factory.
Ensures every Celery task executes inside the correct Flask app context.
"""

from __future__ import annotations

import logging
import os
import platform
from celery import Celery

logger = logging.getLogger(__name__)
celery = Celery("projectup")


def init_celery_app(flask_app=None):
    """
    Initialize the shared Celery instance with the provided Flask app.
    If no app is provided, create one via the factory while preventing recursive
    Celery initialization.
    """
    from app import create_app  # Local import to avoid circular dependency

    app = flask_app or create_app(with_celery=False)

    # Ensure a baseline app context exists for eager/registration time work
    app_ctx = app.app_context()
    app_ctx.push()

    # Ensure Celery and Flask share identical configuration
    broker_url = app.config.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
    result_backend = app.config.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

    # Keep environment variables aligned for any subprocess workers
    os.environ.setdefault("CELERY_BROKER_URL", broker_url)
    os.environ.setdefault("CELERY_RESULT_BACKEND", result_backend)
    os.environ.setdefault("CELERY_BROKER_TRANSPORT", "redis")

    celery.conf.update(app.config)
    celery.conf.broker_url = broker_url
    celery.conf.result_backend = result_backend
    celery.conf.broker_transport = "redis"
    celery.conf.enable_test_tasks = bool(app.config.get("ENABLE_TEST_CELERY_TASKS", False))
    celery.conf.setdefault("task_serializer", "json")
    celery.conf.setdefault("result_serializer", "json")
    celery.conf.setdefault("accept_content", ["json"])
    celery.conf.setdefault("timezone", "Asia/Kolkata")
    celery.conf.setdefault("enable_utc", True)
    celery.conf.setdefault("task_track_started", True)
    celery.conf.setdefault("worker_prefetch_multiplier", 1)
    celery.conf.setdefault("worker_max_tasks_per_child", 1000)
    celery.conf.setdefault("result_expires", 3600)

    if platform.system() == "Windows":
        celery.conf.worker_pool = "solo"

    include_modules = [
        "app.services.celery_tasks",
        "app.tasks.google_sync",
        "app.tasks.tasks",
        "app.tasks.schedule",
    ]
    celery.conf.update(include=include_modules)
    celery.autodiscover_tasks(include_modules, force=True)

    # OFFICIAL PATTERN: guarantee every Celery task runs inside the Flask context
    TaskBase = celery.Task

    class ContextTask(TaskBase):
        abstract = True

        def __call__(self, *args, **kwargs):
            with app.app_context():
                return TaskBase.__call__(self, *args, **kwargs)

    celery.Task = ContextTask
    app.extensions["celery"] = celery
    logger.info("[CELERY] Celery configured with Flask app context")
    return celery

