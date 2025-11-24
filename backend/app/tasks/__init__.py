"""
Celery tasks module - exports celery instance and task definitions
"""
from app.celery_app import celery, init_celery_app

__all__ = ["celery", "init_celery_app"]
