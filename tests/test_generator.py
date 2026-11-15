from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
import httpx
from groq import APIError as GroqAPIError
from langchain_core.exceptions import OutputParserException
from langchain_google_genai.chat_models import ChatGoogleGenerativeAIError
from pydantic import ValidationError

from app.agents import generator
from app.agents.generator import LessonGenerationError, generate_lesson
from app.config import Settings
from app.prompts.generator_prompt import (
    NON_FACTUAL_SECTIONS,
    REQUIRED_LESSON_SECTIONS,
)
from app.schemas import (
    GenerationErrorCategory,
    GenerationFailureStage,
    LearnedRule,
    Lesson,
    LessonValidationSubcode,
    ReferenceMaterial,
    ReferenceSource,
)


def make_sections() -> dict[str, str]:
    sections = {}
    for heading in REQUIRED_LESSON_SECTIONS:
        if heading == "Learning Objectives":
            sections[heading] = "By the end, you can explain RAG."
        elif heading == "Knowledge Check":
            sections[heading] = "What does a retriever do?"
        else:
            sections[heading] = "This section explains the topic in simple words. [R1]"
    return sections


class FakeStructuredModel:
    def __init__(self, response: object = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.messages: Sequence[Any] | None = None

    def invoke(self, messages: Sequence[Any]) -> object:
        self.messages = messages
        if self.error is not None:
            raise self.error
        return self.response


class FakeChatModel:
    def __init__(self, structured_model: FakeStructuredModel) -> None:
        self.structured_model = structured_model
        self.output_schema: type | None = None

    def with_structured_output(self, schema: type) -> FakeStructuredModel:
        self.output_schema = schema
        return self.structured_model


def use_fake_model(
    monkeypatch: pytest.MonkeyPatch,
    fake_model: FakeChatModel,
) -> None:
    monkeypatch.setattr(
        generator,
        "create_chat_model",
        lambda settings: fake_model,
    )
    monkeypatch.setattr(
        generator,
        "load_settings",
        lambda: Settings(
            app_env="test",
            log_level="INFO",
            database_path=Path("test.sqlite3"),
            max_retries=2,
        ),
    )


def test_generate_lesson_returns_complete_validated_lesson(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    structured_model = FakeStructuredModel(
        {"title": "RAG Made Simple", "sections": make_sections()}
    )
    fake_model = FakeChatModel(structured_model)
    use_fake_model(monkeypatch, fake_model)

    lesson = generate_lesson(attempt_number=2)

    assert isinstance(lesson, Lesson)
    assert lesson.topic == "Introduction to RAG"
    assert lesson.title == "RAG Made Simple"
    assert lesson.attempt_number == 2
    assert set(REQUIRED_LESSON_SECTIONS).issubset(lesson.sections)
    assert all(
        "[R1]" in lesson.sections[heading]
        for heading in REQUIRED_LESSON_SECTIONS
        if heading.casefold() not in NON_FACTUAL_SECTIONS
    )
    assert lesson.reference_ids == ("R1",)
    assert lesson.sections["Sources"].startswith("- [R1]")
    assert "## Sources" in lesson.full_markdown
    assert "[R1]" in lesson.full_markdown
    assert fake_model.output_schema is not None
    assert structured_model.messages is not None


def test_prompt_includes_trusted_notes_rules_and_previous_feedback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    structured_model = FakeStructuredModel(
        {"title": "RAG Made Simple", "sections": make_sections()}
    )
    fake_model = FakeChatModel(structured_model)
    use_fake_model(monkeypatch, fake_model)
    rule = LearnedRule(
        rule_description="Explain every important term simply.",
        rationale="Terminology was unclear in prior attempts.",
        related_checkpoint="C4",
        failure_count=2,
        confidence=0.8,
        source_rejection_ids=("11111111-1111-4111-8111-111111111111",),
    )

    generate_lesson(
        learned_rules=(rule,),
        previous_feedback=("Add a clearer retrieval example.",),
    )

    assert structured_model.messages is not None
    prompt_text = "\n".join(message.content for message in structured_model.messages)
    assert "Trusted Reference Notes: Introduction to RAG" in prompt_text
    assert "Valid source IDs for citations" in prompt_text
    assert "R1, R2" in prompt_text
    assert "all 16 required headings exactly once" in prompt_text
    assert "How Does RAG Work? - include at least one relevant valid citation" in (
        prompt_text
    )
    assert "Explain every important term simply." in prompt_text
    assert "Add a clearer retrieval example." in prompt_text


def test_generator_uses_reference_ids_from_supplied_curated_material(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    references = ReferenceMaterial(
        title="Test curated notes",
        version="1",
        content="A curated note supports the lesson claim [R7].",
        sources=(
            ReferenceSource(
                source_id="R7",
                title="Supported source",
                url="https://example.com/r7",
            ),
            ReferenceSource(
                source_id="R8",
                title="Another source",
                url="https://example.com/r8",
            ),
        ),
    )
    sections = {
        heading: content.replace("[R1]", "[R7]")
        for heading, content in make_sections().items()
    }
    structured_model = FakeStructuredModel(
        {"title": "RAG Made Simple", "sections": sections}
    )
    fake_model = FakeChatModel(structured_model)
    use_fake_model(monkeypatch, fake_model)

    lesson = generate_lesson(reference_material=references)

    assert lesson.reference_ids == ("R7",)
    assert structured_model.messages is not None
    prompt_text = "\n".join(message.content for message in structured_model.messages)
    assert "Valid source IDs for citations (use only these exact IDs):\nR7, R8" in (
        prompt_text
    )
    assert "R1" not in prompt_text


@pytest.mark.parametrize(
    ("response", "expected_stage"),
    [
        (
            "not structured",
            GenerationFailureStage.STRUCTURED_OUTPUT_PARSING,
        ),
        (
            {"title": "Missing sections", "sections": {}},
            GenerationFailureStage.SCHEMA_VALIDATION,
        ),
    ],
)
def test_generation_rejects_malformed_response(
    response: object,
    expected_stage: GenerationFailureStage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_model = FakeChatModel(FakeStructuredModel(response=response))
    use_fake_model(monkeypatch, fake_model)

    with pytest.raises(LessonGenerationError) as error:
        generate_lesson()
    assert error.value.failure_stage is expected_stage


def test_generation_error_sanitizes_exception_class_name() -> None:
    error = LessonGenerationError(
        "Untrusted error details.",
        exception_type="Groq API error with private details",
    )

    assert error.exception_type == "Exception"


@pytest.mark.parametrize("response", [None, "", {}])
def test_generation_rejects_empty_response(
    response: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_model = FakeChatModel(FakeStructuredModel(response=response))
    use_fake_model(monkeypatch, fake_model)

    with pytest.raises(
        LessonGenerationError, match="empty lesson response"
    ) as error:
        generate_lesson()
    assert error.value.failure_stage is GenerationFailureStage.STRUCTURED_OUTPUT_PARSING


def test_generation_rejects_incomplete_lesson(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sections = make_sections()
    sections.pop("Recap")
    fake_model = FakeChatModel(
        FakeStructuredModel({"title": "Incomplete", "sections": sections})
    )
    use_fake_model(monkeypatch, fake_model)

    with pytest.raises(
        LessonGenerationError, match="missing required sections: Recap"
    ) as error:
        generate_lesson()
    assert error.value.failure_stage is GenerationFailureStage.LESSON_CONTENT_VALIDATION
    assert (
        error.value.validation_subcode
        is LessonValidationSubcode.MISSING_REQUIRED_SECTION
    )


def test_generation_rejects_duplicate_required_section(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sections = make_sections()
    sections["How does RAG work"] = "Duplicate heading content. [R1]"
    use_fake_model(
        monkeypatch,
        FakeChatModel(
            FakeStructuredModel({"title": "Duplicate", "sections": sections})
        ),
    )

    with pytest.raises(LessonGenerationError) as error:
        generate_lesson()

    assert (
        error.value.validation_subcode
        is LessonValidationSubcode.DUPLICATE_REQUIRED_SECTION
    )


def test_generation_rejects_unknown_citation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sections = make_sections()
    sections["Introduction"] = "A made-up fact. [R99]"
    fake_model = FakeChatModel(
        FakeStructuredModel({"title": "Unsupported", "sections": sections})
    )
    use_fake_model(monkeypatch, fake_model)

    with pytest.raises(
        LessonGenerationError, match="unknown reference IDs: R99"
    ) as error:
        generate_lesson()
    assert error.value.failure_stage is GenerationFailureStage.LESSON_CONTENT_VALIDATION
    assert error.value.validation_subcode is LessonValidationSubcode.UNKNOWN_REFERENCE_ID


def test_generation_requires_citations_in_factual_sections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sections = make_sections()
    sections["How Does RAG Work?"] = "The system searches and answers."
    fake_model = FakeChatModel(
        FakeStructuredModel({"title": "Uncited", "sections": sections})
    )
    use_fake_model(monkeypatch, fake_model)

    with pytest.raises(
        LessonGenerationError, match="must cite trusted references"
    ) as error:
        generate_lesson()
    assert error.value.failure_stage is GenerationFailureStage.LESSON_CONTENT_VALIDATION
    assert (
        error.value.validation_subcode
        is LessonValidationSubcode.MISSING_FACTUAL_CITATION
    )


def test_generation_rejects_invalid_citation_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sections = make_sections()
    sections["Introduction"] = "RAG uses context. [R1; R2]"
    use_fake_model(
        monkeypatch,
        FakeChatModel(
            FakeStructuredModel({"title": "Bad citation", "sections": sections})
        ),
    )

    with pytest.raises(LessonGenerationError) as error:
        generate_lesson()

    assert (
        error.value.validation_subcode
        is LessonValidationSubcode.INVALID_CITATION_FORMAT
    )


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (TimeoutError("simulated timeout"), "request timed out"),
        (httpx.TimeoutException("simulated timeout"), "request timed out"),
        (
            ChatGoogleGenerativeAIError("simulated API failure"),
            "request failed",
        ),
        (
            GroqAPIError(
                "simulated Groq API failure",
                httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
                body=None,
            ),
            "request failed",
        ),
    ],
)
def test_generation_surfaces_provider_failures(
    error: Exception,
    message: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_model = FakeChatModel(FakeStructuredModel(error=error))
    use_fake_model(monkeypatch, fake_model)

    with pytest.raises(LessonGenerationError, match=message) as error_info:
        generate_lesson()
    assert error_info.value.failure_stage is GenerationFailureStage.PROVIDER_REQUEST
    assert (
        error_info.value.error_category
        is GenerationErrorCategory.PROVIDER_REQUEST_ERROR
    )
    assert error_info.value.exception_type == type(error).__name__


def test_generation_classifies_structured_output_parser_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = OutputParserException("untrusted response text")
    use_fake_model(
        monkeypatch,
        FakeChatModel(FakeStructuredModel(error=error)),
    )

    with pytest.raises(LessonGenerationError) as error_info:
        generate_lesson()

    assert (
        error_info.value.failure_stage
        is GenerationFailureStage.STRUCTURED_OUTPUT_PARSING
    )
    assert (
        error_info.value.error_category
        is GenerationErrorCategory.STRUCTURED_OUTPUT_ERROR
    )
    assert error_info.value.exception_type == "OutputParserException"
    assert "untrusted response text" not in str(error_info.value)


def test_generation_classifies_pydantic_schema_validation_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValidationError) as validation_error:
        generator._GeneratedLessonContent.model_validate(
            {"title": "", "sections": {}}
        )
    use_fake_model(
        monkeypatch,
        FakeChatModel(FakeStructuredModel(error=validation_error.value)),
    )

    with pytest.raises(LessonGenerationError) as error_info:
        generate_lesson()

    assert error_info.value.failure_stage is GenerationFailureStage.SCHEMA_VALIDATION
    assert (
        error_info.value.error_category
        is GenerationErrorCategory.SCHEMA_VALIDATION_ERROR
    )
    assert error_info.value.exception_type == "ValidationError"


def test_generation_loads_references_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    structured_model = FakeStructuredModel(
        {"title": "RAG Made Simple", "sections": make_sections()}
    )
    fake_model = FakeChatModel(structured_model)
    use_fake_model(monkeypatch, fake_model)

    lesson = generate_lesson()

    assert lesson.reference_ids == ("R1",)
