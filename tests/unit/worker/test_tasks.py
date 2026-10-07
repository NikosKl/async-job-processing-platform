from datetime import UTC
from unittest.mock import MagicMock, patch

import pytest

from app.worker.celery_app import celery_app
from app.worker.tasks import OUTBOX_BATCH_SIZE, run_outbox_publisher_batch


def test_run_outbox_publisher_batch_is_registered():
    assert run_outbox_publisher_batch.name == "run_outbox_publisher_batch"
    assert "run_outbox_publisher_batch" in celery_app.tasks


def test_run_outbox_publisher_batch_calls_publisher_with_session_cutoff_and_limit():
    with patch("app.worker.tasks.DBSession") as session_factory_mock:
        fake_session = session_factory_mock.return_value

        with patch("app.worker.tasks.publish_outbox_batch") as publish_mock:
            run_outbox_publisher_batch.run()

            called_db = publish_mock.call_args.kwargs["db"]
            called_cutoff = publish_mock.call_args.kwargs["cutoff"]
            called_limit = publish_mock.call_args.kwargs["limit"]

            assert called_db is fake_session
            assert called_cutoff.tzinfo is UTC
            assert called_limit == OUTBOX_BATCH_SIZE


def test_run_outbox_publisher_batch_closes_session_after_success():
    with patch("app.worker.tasks.DBSession") as session_factory_mock:
        fake_session = session_factory_mock.return_value
        with patch("app.worker.tasks.publish_outbox_batch"):
            run_outbox_publisher_batch.run()

    fake_session.close.assert_called_once()


def test_run_outbox_publisher_batch_closes_session_and_propagates_service_error():
    with patch("app.worker.tasks.DBSession") as session_factory_mock:
        fake_session = session_factory_mock.return_value
        with patch(
            "app.worker.tasks.publish_outbox_batch",
            side_effect=RuntimeError("publisher failed"),
        ):
            with pytest.raises(RuntimeError, match="publisher failed"):
                run_outbox_publisher_batch.run()

    fake_session.close.assert_called_once()


def test_run_outbox_publisher_batch_uses_separate_sessions():
    session_a = MagicMock()
    session_b = MagicMock()

    with patch("app.worker.tasks.DBSession") as session_factory_mock:
        session_factory_mock.side_effect = [session_a, session_b]

        with patch("app.worker.tasks.publish_outbox_batch") as publish_mock:
            for _ in range(2):
                run_outbox_publisher_batch.run()

            call_a = publish_mock.call_args_list[0]
            call_b = publish_mock.call_args_list[1]

            call_a_db = call_a.kwargs["db"]
            call_b_db = call_b.kwargs["db"]

    assert call_a_db is session_a
    assert call_b_db is session_b

    assert session_factory_mock.call_count == 2
    session_a.close.assert_called_once()
    session_b.close.assert_called_once()
