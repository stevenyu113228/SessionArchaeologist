"""Celery task definitions — Phase 1 placeholder for future async pipeline."""

from celery import Celery

from archaeologist.config import settings

celery_app = Celery(
    "archaeologist",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    task_track_started=True,
)

# Phase 1: extraction runs synchronously in CLI.
# Phase 2+ will move these to proper Celery tasks for parallel execution.
