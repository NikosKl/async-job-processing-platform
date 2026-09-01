# Async Job Processing Platform

A backend platform for submitting, processing, and tracking asynchronous jobs. The project is designed to explore job lifecycle management, worker coordination, retries, and failure handling using a production-style backend architecture.

## Tech Stack

* Python 3.13
* FastAPI
* PostgreSQL
* SQLAlchemy
* Alembic
* Pytest
* Ruff
* Docker / Docker Compose

## Status

**Work in progress**

The project is currently under active development. Features and documentation will be expanded as new milestones are completed.

## Local Development

### 1. Create and activate a virtual environment

```bash
python -m venv .venv
```

macOS / Linux:

```bash
source .venv/bin/activate
```

Windows:

```bash
.venv\Scripts\activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

Create the local development environment file:

```bash
cp .env.example .env
```

Update the values in `.env` for your local PostgreSQL setup.

## Database Migrations

Apply all migrations:

```bash
alembic upgrade head
```

Check the currently applied migration:

```bash
alembic current
```

## Running Locally

Run the API directly from the local Python environment:

```bash
fastapi dev app/main.py
```

The API will be available at:

```text
http://localhost:8000
```

Interactive API documentation:

```text
http://localhost:8000/docs
```

## Docker Compose

For Docker Compose, create a separate environment file:

```bash
cp .env.compose.example .env.compose
```

Update the PostgreSQL development credentials in `.env.compose`.

Start PostgreSQL, run database migrations, and start the API:

```bash
docker compose --env-file .env.compose up --build
```

For subsequent starts when no image rebuild is required:

```bash
docker compose --env-file .env.compose up
```

Stop the services:

```bash
docker compose down
```

The Compose startup sequence is:

```text
PostgreSQL healthy
→ migrations complete successfully
→ API starts
```

## Health Checks

The application provides two health endpoints:

* `GET /health/live` checks whether the API process is running. It does not depend on the database.
* `GET /health/ready` checks whether the application is ready to serve requests, including verifying database connectivity.

This separation allows infrastructure to distinguish between an application that is running and one that is fully ready to handle requests.

## Tests

Run the test suite:

```bash
pytest
```

## Linting and Formatting

Run Ruff lint checks:

```bash
ruff check .
```

Check whether the code is correctly formatted:

```bash
ruff format --check .
```

To automatically format the project:

```bash
ruff format .
```
