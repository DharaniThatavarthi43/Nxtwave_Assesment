from langchain_core.language_models.chat_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq

from app.config import ConfigurationError, Settings, load_settings


MODEL_TIMEOUT_SECONDS = 30
MODEL_MAX_RETRIES = 2


def create_chat_model(
    settings: Settings | None = None,
    *,
    max_retries: int = MODEL_MAX_RETRIES,
    max_output_tokens: int | None = None,
    reasoning_effort: str | None = None,
) -> BaseChatModel:
    """Create the configured LangChain chat model without exposing its key."""
    current_settings = settings if settings is not None else load_settings()

    if current_settings.llm_provider is None:
        raise ConfigurationError(
            "LLM configuration is missing. Set LLM_PROVIDER=google or groq, "
            "LLM_MODEL, and LLM_API_KEY in .env."
        )
    if current_settings.llm_provider.casefold() not in {"google", "groq"}:
        raise ConfigurationError(
            "Unsupported LLM_PROVIDER. Supported providers are 'google' and 'groq'."
        )
    if not current_settings.llm_model or not current_settings.llm_api_key:
        raise ConfigurationError("LLM configuration requires LLM_MODEL and LLM_API_KEY.")

    if current_settings.llm_provider.casefold() == "google":
        return ChatGoogleGenerativeAI(
            model=current_settings.llm_model,
            api_key=current_settings.llm_api_key,
            request_timeout=MODEL_TIMEOUT_SECONDS,
            retries=max_retries,
            temperature=0.2,
            max_output_tokens=max_output_tokens,
            reasoning_effort=reasoning_effort,
        )

    return ChatGroq(
        model=current_settings.llm_model,
        api_key=current_settings.llm_api_key,
        timeout=MODEL_TIMEOUT_SECONDS,
        max_retries=max_retries,
        temperature=0.2,
        max_tokens=max_output_tokens,
        reasoning_effort=reasoning_effort,
    )
