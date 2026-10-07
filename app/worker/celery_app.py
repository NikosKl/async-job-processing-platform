from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "async_job_processing_platform",
    broker=settings.celery_broker_url,
)

celery_app.conf.update(
    task_ignore_result=True,
    task_serializer="json",
    accept_content=["json"],
    task_default_queue="jobs",
    worker_concurrency=2,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=False,
    imports=("app.worker.tasks",),
)
