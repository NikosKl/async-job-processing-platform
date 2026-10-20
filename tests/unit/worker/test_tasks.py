import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.worker.celery_app import celery_app
from app.worker.tasks import OUTBOX_BATCH_SIZE, process_job, run_outbox_publisher_batch


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


def test_process_job_is_registered():
    assert process_job.name == "process_job"
    assert "process_job" in celery_app.tasks


def test_process_job_passes_uuid_to_claim_service():
    job_id = uuid.uuid4()

    parsed_job_id = str(job_id)

    with patch("app.worker.tasks.DBSession"):
        with patch("app.worker.tasks.claim_job_for_execution") as claim_mock:
            with patch("app.worker.tasks.execute_claimed_job"):
                process_job.run(parsed_job_id)

            called_id = claim_mock.call_args.kwargs["job_id"]

            assert isinstance(called_id, uuid.UUID)
            assert called_id == job_id


def test_process_job_passes_utc_time_and_lease_duration():
    job_id = str(uuid.uuid4())
    fixed_time = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)

    with patch("app.worker.tasks.datetime") as datetime_mock:
        datetime_mock.now.return_value = fixed_time

        with patch("app.worker.tasks.DBSession"):
            with patch("app.worker.tasks.claim_job_for_execution") as claim_mock:
                with patch("app.worker.tasks.execute_claimed_job"):
                    process_job.run(job_id)

    called_claim_time = claim_mock.call_args.kwargs["claim_time"]
    called_lease_duration = claim_mock.call_args.kwargs["lease_duration"]

    datetime_mock.now.assert_called_once_with(UTC)

    assert called_claim_time == fixed_time
    assert called_claim_time.tzinfo is UTC
    assert called_lease_duration == timedelta(minutes=10)


def test_process_job_unsuccessful_claim_returns_normally():
    job_id = str(uuid.uuid4())

    with patch("app.worker.tasks.DBSession"):
        with patch(
            "app.worker.tasks.claim_job_for_execution", return_value=None
        ) as claim_mock:
            with patch("app.worker.tasks.execute_claimed_job") as execute_mock:
                process_job.run(job_id)

    claim_mock.assert_called_once()
    execute_mock.assert_not_called()


def test_process_job_closes_session_after_success():
    job_id = str(uuid.uuid4())

    with patch("app.worker.tasks.DBSession") as session_factory_mock:
        fake_session = session_factory_mock.return_value
        with patch("app.worker.tasks.claim_job_for_execution"):
            with patch("app.worker.tasks.execute_claimed_job"):
                process_job.run(job_id)

        fake_session.close.assert_called_once()


def test_process_job_closes_session_and_propagates_service_error():
    job_id = str(uuid.uuid4())

    with patch("app.worker.tasks.DBSession") as session_factory_mock:
        fake_session = session_factory_mock.return_value

        with patch(
            "app.worker.tasks.claim_job_for_execution",
            side_effect=RuntimeError("claim failed"),
        ):
            with pytest.raises(RuntimeError, match="claim failed"):
                process_job.run(job_id)

    fake_session.close.assert_called_once()


def test_process_job_rejects_invalid_uuid_before_opening_session():
    job_id = "invalid_uuid"

    with patch("app.worker.tasks.DBSession") as session_factory_mock:
        with pytest.raises(ValueError):
            process_job.run(job_id)

    session_factory_mock.assert_not_called()


def test_process_job_uses_separate_sessions():

    session_a = MagicMock()
    session_b = MagicMock()

    job_id = str(uuid.uuid4())

    with patch("app.worker.tasks.DBSession") as session_factory_mock:
        session_factory_mock.side_effect = [session_a, session_b]

        with patch("app.worker.tasks.claim_job_for_execution") as claim_mock:
            with patch("app.worker.tasks.execute_claimed_job"):
                for _ in range(2):
                    process_job.run(job_id)

                call_a = claim_mock.call_args_list[0]
                call_b = claim_mock.call_args_list[1]

                call_a_db = call_a.kwargs["db"]
                call_b_db = call_b.kwargs["db"]

                assert call_a_db is session_a
                assert call_b_db is session_b

    assert session_factory_mock.call_count == 2
    session_a.close.assert_called_once()
    session_b.close.assert_called_once()


def test_process_job_uses_fresh_claim_time_per_invocation():
    job_id = str(uuid.uuid4())

    time_a = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)
    time_b = datetime(2026, 10, 12, 12, 5, tzinfo=UTC)

    with patch("app.worker.tasks.datetime") as datetime_mock:
        datetime_mock.now.side_effect = [time_a, time_b]

        with patch("app.worker.tasks.DBSession"):
            with patch("app.worker.tasks.claim_job_for_execution") as claim_mock:
                with patch("app.worker.tasks.execute_claimed_job"):
                    process_job.run(job_id)
                    process_job.run(job_id)

    first_call = claim_mock.call_args_list[0]
    second_call = claim_mock.call_args_list[1]

    assert first_call.kwargs["claim_time"] == time_a
    assert second_call.kwargs["claim_time"] == time_b

    assert datetime_mock.now.call_count == 2


def test_process_job_successful_claim_calls_execution_service():
    job_id = str(uuid.uuid4())
    execution_token = uuid.uuid4()

    with patch("app.worker.tasks.DBSession") as session_factory_mock:
        with patch("app.worker.tasks.claim_job_for_execution") as claim_mock:
            claim_mock.return_value.execution_token = execution_token
            with patch("app.worker.tasks.execute_claimed_job") as execute_mock:
                process_job.run(job_id)

    execute_mock.assert_called_once()

    called_kwargs = execute_mock.call_args.kwargs

    assert called_kwargs["execution_token"] == execution_token
    assert called_kwargs["db"] is session_factory_mock.return_value
    assert called_kwargs["job_id"] == uuid.UUID(job_id)


@pytest.mark.parametrize(
    "execution_result",
    [
        True,
        False,
    ],
)
def test_process_job_closes_session_after_execution(execution_result):
    job_id = str(uuid.uuid4())
    execution_token = uuid.uuid4()

    with patch("app.worker.tasks.DBSession") as session_factory_mock:
        with patch("app.worker.tasks.claim_job_for_execution") as claim_mock:
            claim_mock.return_value.execution_token = execution_token
            with patch(
                "app.worker.tasks.execute_claimed_job", return_value=execution_result
            ) as execute_mock:
                process_job.run(job_id)

    session_factory_mock.return_value.close.assert_called_once()
    execute_mock.assert_called_once()


def test_process_job_closes_session_and_propagates_execution_error():
    job_id = str(uuid.uuid4())
    execution_token = uuid.uuid4()

    with patch("app.worker.tasks.DBSession") as session_factory_mock:
        with patch("app.worker.tasks.claim_job_for_execution") as claim_mock:
            claim_mock.return_value.execution_token = execution_token
            with patch(
                "app.worker.tasks.execute_claimed_job",
                side_effect=RuntimeError("execution failed"),
            ) as execute_mock:
                with pytest.raises(RuntimeError, match="execution failed"):
                    process_job.run(job_id)

    execute_mock.assert_called_once()
    session_factory_mock.return_value.close.assert_called_once()
