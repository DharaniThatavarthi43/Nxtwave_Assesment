from pathlib import Path
from unittest.mock import Mock, sentinel

import pytest

from app.config import ConfigurationError, Settings
from app.llm import provider


def make_settings(
    *,
    llm_provider: str | None = "google",
    llm_model: str | None = "unit-test-model",
    llm_api_key: str | None = "not-a-real-api-key",
) -> Settings:
    return Settings(
        app_env="test",
        log_level="INFO",
        database_path=Path("test.db"),
        max_retries=2,
        llm_provider=llm_provider,
        llm_model=llm_model,
        llm_api_key=llm_api_key,
    )


def test_provider_requires_configuration() -> None:
    settings = make_settings(
        llm_provider=None,
        llm_model=None,
        llm_api_key=None,
    )
    with pytest.raises(ConfigurationError, match="LLM configuration is missing"):
        provider.create_chat_model(settings)


def test_provider_rejects_unsupported_provider() -> None:
    with pytest.raises(
        ConfigurationError,
        match="Supported providers are 'google' and 'groq'",
    ):
        provider.create_chat_model(make_settings(llm_provider="unsupported"))


def test_provider_requires_model_and_key() -> None:
    with pytest.raises(ConfigurationError, match="LLM_MODEL and LLM_API_KEY"):
        provider.create_chat_model(make_settings(llm_api_key=None))


def test_provider_constructs_gemini_model_with_configured_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructor = Mock(return_value=sentinel.chat_model)
    monkeypatch.setattr(provider, "ChatGoogleGenerativeAI", constructor)

    model = provider.create_chat_model(make_settings())

    assert model is sentinel.chat_model
    constructor.assert_called_once_with(
        model="unit-test-model",
        api_key="not-a-real-api-key",
        request_timeout=provider.MODEL_TIMEOUT_SECONDS,
        retries=provider.MODEL_MAX_RETRIES,
        temperature=0.2,
    )


def test_provider_constructs_groq_model_with_configured_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructor = Mock(return_value=sentinel.chat_model)
    monkeypatch.setattr(provider, "ChatGroq", constructor)

    model = provider.create_chat_model(
        make_settings(llm_provider="groq", llm_model="openai/gpt-oss-120b")
    )

    assert model is sentinel.chat_model
    constructor.assert_called_once_with(
        model="openai/gpt-oss-120b",
        api_key="not-a-real-api-key",
        timeout=provider.MODEL_TIMEOUT_SECONDS,
        max_retries=provider.MODEL_MAX_RETRIES,
        temperature=0.2,
    )


def test_provider_allows_disabling_sdk_retries_for_evaluator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructor = Mock(return_value=sentinel.chat_model)
    monkeypatch.setattr(provider, "ChatGroq", constructor)

    provider.create_chat_model(
        make_settings(llm_provider="groq"),
        max_retries=0,
    )

    constructor.assert_called_once_with(
        model="unit-test-model",
        api_key="not-a-real-api-key",
        timeout=provider.MODEL_TIMEOUT_SECONDS,
        max_retries=0,
        temperature=0.2,
    )


def test_groq_provider_requires_model_and_key() -> None:
    with pytest.raises(ConfigurationError, match="LLM_MODEL and LLM_API_KEY"):
        provider.create_chat_model(
            make_settings(llm_provider="groq", llm_api_key=None)
        )
