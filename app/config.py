import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TOPIC = "Introduction to RAG"
MAX_ALLOWED_RETRIES = 2
DEFAULT_EVALUATOR_MAX_RETRY_AFTER_SECONDS = 120
MAX_CONFIGURED_EVALUATOR_RETRY_AFTER_SECONDS = 3600


class ConfigurationError(ValueError):
    """Raised when application configuration is invalid."""


@dataclass(frozen=True)
class Settings:
    app_env: str
    log_level: str
    database_path: Path
    max_retries: int
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_api_key: str | None = field(default=None, repr=False)
    evaluator_max_retry_after_seconds: int = (
        DEFAULT_EVALUATOR_MAX_RETRY_AFTER_SECONDS
    )


def load_settings(
    environ: Mapping[str, str] | None = None,
    project_root: Path = PROJECT_ROOT,
) -> Settings:
    if environ is None:
        load_dotenv(project_root / ".env", override=False)
        values = os.environ
    else:
        values = environ

    app_env = values.get("APP_ENV", "development").strip().lower()
    if app_env not in {"development", "test", "production"}:
        raise ConfigurationError(
            "APP_ENV must be one of: development, test, production."
        )

    log_level = values.get("LOG_LEVEL", "INFO").strip().upper()
    if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ConfigurationError(
            "LOG_LEVEL must be one of: DEBUG, INFO, WARNING, ERROR, CRITICAL."
        )

    raw_retries = values.get("MAX_RETRIES", str(MAX_ALLOWED_RETRIES)).strip()
    try:
        max_retries = int(raw_retries)
    except ValueError as exc:
        raise ConfigurationError("MAX_RETRIES must be a whole number.") from exc
    if not 0 <= max_retries <= MAX_ALLOWED_RETRIES:
        raise ConfigurationError(
            f"MAX_RETRIES must be between 0 and {MAX_ALLOWED_RETRIES}."
        )

    raw_evaluator_retry_after = values.get(
        "EVALUATOR_MAX_RETRY_AFTER_SECONDS",
        str(DEFAULT_EVALUATOR_MAX_RETRY_AFTER_SECONDS),
    ).strip()
    try:
        evaluator_max_retry_after_seconds = int(raw_evaluator_retry_after)
    except ValueError as exc:
        raise ConfigurationError(
            "EVALUATOR_MAX_RETRY_AFTER_SECONDS must be a whole number."
        ) from exc
    if not 1 <= evaluator_max_retry_after_seconds <= (
        MAX_CONFIGURED_EVALUATOR_RETRY_AFTER_SECONDS
    ):
        raise ConfigurationError(
            "EVALUATOR_MAX_RETRY_AFTER_SECONDS must be between 1 and "
            f"{MAX_CONFIGURED_EVALUATOR_RETRY_AFTER_SECONDS}."
        )

    raw_database_path = values.get(
        "DATABASE_PATH", "data/database/lesson_generator.db"
    ).strip()
    if not raw_database_path:
        raise ConfigurationError("DATABASE_PATH must not be empty.")
    database_path = Path(raw_database_path).expanduser()
    if not database_path.is_absolute():
        database_path = project_root / database_path
    database_path = database_path.resolve()

    provider = values.get("LLM_PROVIDER", "").strip().casefold()
    model = values.get("LLM_MODEL", "").strip()
    api_key = values.get("LLM_API_KEY", "").strip()
    llm_values = {
        "LLM_PROVIDER": provider,
        "LLM_MODEL": model,
        "LLM_API_KEY": api_key,
    }
    configured_llm_values = {name: value for name, value in llm_values.items() if value}
    if configured_llm_values and len(configured_llm_values) != len(llm_values):
        missing = sorted(set(llm_values) - set(configured_llm_values))
        raise ConfigurationError(
            "Configure LLM settings together; missing: " + ", ".join(missing) + "."
        )

    return Settings(
        app_env=app_env,
        log_level=log_level,
        database_path=database_path,
        max_retries=max_retries,
        llm_provider=provider or None,
        llm_model=model or None,
        llm_api_key=api_key or None,
        evaluator_max_retry_after_seconds=evaluator_max_retry_after_seconds,
    )
