import os
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.security import create_access_token, hash_password
from app.models import RepositoryAnalysisItem
from app.repositories.user import create_user
from app.schemas.jobs import CreateJobRequest, RepositoryBatchAnalysisInput
from app.services.job_service import claim_job_for_execution, submit_job

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env.test")

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

if not TEST_DATABASE_URL:
    raise RuntimeError("TEST_DATABASE_URL is not set")

import app.models  # noqa: E402, F401
from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402

test_engine = create_engine(TEST_DATABASE_URL)
TestSession = sessionmaker(autoflush=False, expire_on_commit=False)


@pytest.fixture(scope="session")
def setup_db():
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture()
def db_session(setup_db):
    connection = test_engine.connect()
    outer_transaction = connection.begin()
    session = TestSession(bind=connection, join_transaction_mode="create_savepoint")

    try:
        yield session
    finally:
        session.close()
        outer_transaction.rollback()
        connection.close()


@pytest.fixture()
def test_session_factory(setup_db):
    factory = sessionmaker(
        bind=test_engine,
        autoflush=False,
        expire_on_commit=False,
    )

    yield factory

    with test_engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(table.delete())


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    fastapi_app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(fastapi_app) as client:
            yield client
    finally:
        fastapi_app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def authenticated_user_factory(db_session):
    def create_authenticated_user(email: str, password: str):
        user = create_user(db_session, email, hash_password(password))
        token = create_access_token(user.id)
        headers = {"Authorization": f"Bearer {token}"}

        return user, headers

    return create_authenticated_user


@pytest.fixture()
def claimed_job_factory(db_session, authenticated_user_factory):
    def create_claimed_job(
        repositories: list[str], claim_time: datetime, idempotency_key: str
    ):
        user, headers = authenticated_user_factory("user@example.com", "password123")

        request = CreateJobRequest(
            type="repository_batch_analysis",
            input=RepositoryBatchAnalysisInput(
                repositories=repositories,
            ),
        )

        job = submit_job(
            db_session, user.id, request=request, idempotency_key=idempotency_key
        )

        lease_duration = timedelta(minutes=10)

        claimed_job = claim_job_for_execution(
            db=db_session,
            job_id=job.id,
            claim_time=claim_time,
            lease_duration=lease_duration,
        )

        assert claimed_job is not None
        assert claimed_job.execution_token is not None

        stmt = select(RepositoryAnalysisItem).where(
            RepositoryAnalysisItem.job_id == job.id
        )
        items = db_session.scalars(stmt).all()

        return user, headers, claimed_job, items

    return create_claimed_job
