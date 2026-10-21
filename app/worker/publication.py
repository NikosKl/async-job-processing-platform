from uuid import UUID

from app.worker.celery_app import celery_app


def publish_process_job(job_id: UUID) -> None:

    celery_app.send_task(name="process_job", args=[str(job_id)], queue="jobs")
