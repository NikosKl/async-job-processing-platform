import uuid
from unittest.mock import patch

import pytest

from app.worker.publication import publish_process_job


def test_publish_process_job_sends_process_job_task():

    job_id = uuid.uuid4()

    with patch("app.worker.publication.celery_app.send_task") as send_task_mock:
        publish_process_job(job_id)

    send_task_mock.assert_called_once_with(
        name="process_job",
        args=[str(job_id)],
        queue="jobs",
    )


def test_publish_process_job_propagates_publication_error():
    job_id = uuid.uuid4()

    with patch(
        "app.worker.publication.celery_app.send_task",
        side_effect=RuntimeError("broker unavailable"),
    ):
        with pytest.raises(RuntimeError, match="broker unavailable"):
            publish_process_job(job_id)
