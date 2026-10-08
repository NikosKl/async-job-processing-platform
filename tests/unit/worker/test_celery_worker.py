from app.core.config import settings
from app.worker.celery_app import celery_app


def test_celery_uses_configured_broker_url():
    assert celery_app.conf.broker_url == settings.celery_broker_url


def test_celery_has_no_result_backend():
    assert celery_app.conf.result_backend is None


def test_celery_uses_only_json_serializer():
    assert celery_app.conf.task_serializer == "json"
    assert celery_app.conf.accept_content == ["json"]


def test_celery_uses_jobs_as_default_queue():
    assert celery_app.conf.task_default_queue == "jobs"


def test_celery_worker_delivery_configuration():
    assert celery_app.conf.worker_prefetch_multiplier == 1
    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.task_reject_on_worker_lost is False


def test_celery_ignores_task_results():
    assert celery_app.conf.task_ignore_result is True


def test_celery_worker_concurrency():
    assert celery_app.conf.worker_concurrency == 2


def test_publisher_beat_schedule_exists():
    assert "publish_outbox" in celery_app.conf.beat_schedule


def test_publisher_beat_schedule_targets_registered_task():
    publisher_schedule = celery_app.conf.beat_schedule["publish_outbox"]

    assert publisher_schedule["task"] == "run_outbox_publisher_batch"


def test_publisher_beat_schedule_runs_every_ten_seconds():
    publisher_schedule = celery_app.conf.beat_schedule["publish_outbox"]

    assert publisher_schedule["schedule"] == 10


def test_publisher_beat_schedule_routes_to_jobs_with_no_arguments():
    publisher_schedule = celery_app.conf.beat_schedule["publish_outbox"]

    assert publisher_schedule["args"] == ()
    assert publisher_schedule["options"]["queue"] == "jobs"
