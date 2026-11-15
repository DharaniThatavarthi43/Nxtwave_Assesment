from pathlib import Path

import pytest

from app.config import (
    DEFAULT_EVALUATOR_MAX_RETRY_AFTER_SECONDS,
    ConfigurationError,
    DEFAULT_TOPIC,
    load_settings,
)
from app.main import main


def test_load_settings_uses_assessment_defaults(tmp_path: Path) -> None:
    settings = load_settings(environ={}, project_root=tmp_path)

    assert settings.app_env == "development"
    assert settings.log_level == "INFO"
    assert settings.max_retries == 2
    assert (
        settings.evaluator_max_retry_after_seconds
        == DEFAULT_EVALUATOR_MAX_RETRY_AFTER_SECONDS
    )
    assert settings.database_path == (
        tmp_path / "data" / "database" / "lesson_generator.db"
    )
    assert DEFAULT_TOPIC == "Introduction to RAG"
    assert settings.llm_provider is None


def test_load_settings_reads_environment_values(tmp_path: Path) -> None:
    settings = load_settings(
        environ={
            "APP_ENV": "test",
            "LOG_LEVEL": "debug",
            "MAX_RETRIES": "1",
            "DATABASE_PATH": "tmp/test.db",
            "EVALUATOR_MAX_RETRY_AFTER_SECONDS": "75",
        },
        project_root=tmp_path,
    )

    assert settings.app_env == "test"
    assert settings.log_level == "DEBUG"
    assert settings.max_retries == 1
    assert settings.database_path == (tmp_path / "tmp" / "test.db")
    assert settings.evaluator_max_retry_after_seconds == 75


def test_load_settings_reads_groq_provider_configuration(tmp_path: Path) -> None:
    settings = load_settings(
        environ={
            "LLM_PROVIDER": "groq",
            "LLM_MODEL": "openai/gpt-oss-120b",
            "LLM_API_KEY": "mock-groq-key",
        },
        project_root=tmp_path,
    )

    assert settings.llm_provider == "groq"
    assert settings.llm_model == "openai/gpt-oss-120b"
    assert "mock-groq-key" not in repr(settings)


def test_load_settings_normalizes_case_for_provider_and_log_level(
    tmp_path: Path,
) -> None:
    settings = load_settings(
        environ={
            "APP_ENV": "Production",
            "LOG_LEVEL": "warning",
            "LLM_PROVIDER": "GOOGLE",
            "LLM_MODEL": "gemini-1.5-flash",
            "LLM_API_KEY": "mock-google-key",
        },
        project_root=tmp_path,
    )

    assert settings.app_env == "production"
    assert settings.log_level == "WARNING"
    assert settings.llm_provider == "google"


def test_load_settings_reads_dotenv_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in (
        "APP_ENV",
        "LOG_LEVEL",
        "MAX_RETRIES",
        "DATABASE_PATH",
        "EVALUATOR_MAX_RETRY_AFTER_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)
    (tmp_path / ".env").write_text(
        "APP_ENV=test\nLOG_LEVEL=WARNING\nMAX_RETRIES=0\n",
        encoding="utf-8",
    )

    settings = load_settings(project_root=tmp_path)

    assert settings.app_env == "test"
    assert settings.log_level == "WARNING"
    assert settings.max_retries == 0


@pytest.mark.parametrize("value", ["-1", "3", "two"])
def test_load_settings_rejects_invalid_retry_count(
    value: str, tmp_path: Path
) -> None:
    with pytest.raises(ConfigurationError, match="MAX_RETRIES"):
        load_settings(environ={"MAX_RETRIES": value}, project_root=tmp_path)


@pytest.mark.parametrize("value", ["0", "3601", "two"])
def test_load_settings_rejects_invalid_evaluator_retry_after_cap(
    value: str, tmp_path: Path
) -> None:
    with pytest.raises(ConfigurationError, match="EVALUATOR_MAX_RETRY_AFTER_SECONDS"):
        load_settings(
            environ={"EVALUATOR_MAX_RETRY_AFTER_SECONDS": value},
            project_root=tmp_path,
        )


def test_load_settings_requires_complete_llm_configuration(
    tmp_path: Path,
) -> None:
    with pytest.raises(ConfigurationError, match="LLM_API_KEY"):
        load_settings(
            environ={"LLM_PROVIDER": "example", "LLM_MODEL": "example-model"},
            project_root=tmp_path,
        )


def test_api_key_is_not_in_settings_repr(tmp_path: Path) -> None:
    secret = "test-secret-value"
    settings = load_settings(
        environ={
            "LLM_PROVIDER": "example",
            "LLM_MODEL": "example-model",
            "LLM_API_KEY": secret,
        },
        project_root=tmp_path,
    )

    assert secret not in repr(settings)


def test_main_rejects_blank_topic() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--topic", "  "])

    assert exc_info.value.code == 2


def test_main_rejects_non_assessment_topic() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--topic", "A future topic"])

    assert exc_info.value.code == 2
