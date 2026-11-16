from app.core.config import Settings


class SettingsWithoutEnv(Settings):
    model_config = {**Settings.model_config, "env_file": None}


def test_settings_defaults_github_token_to_none(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    settings = SettingsWithoutEnv(
        database_url="postgresql+psycopg://test:test@localhost:5432/test_db",
        jwt_secret="fake-jwt-secret",
    )

    assert settings.github_token is None


def test_settings_loads_github_token_from_environment(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "fake-token-123")

    settings = SettingsWithoutEnv(
        database_url="postgresql+psycopg://test:test@localhost:5432/test_db",
        jwt_secret="fake-jwt-secret",
    )

    assert settings.github_token == "fake-token-123"


def test_settings_accepts_empty_github_token(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "")

    settings = SettingsWithoutEnv(
        database_url="postgresql+psycopg://test:test@localhost:5432/test_db",
        jwt_secret="fake-jwt-secret",
    )

    assert settings.github_token == ""
