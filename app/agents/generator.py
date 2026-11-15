import re
from collections.abc import Mapping, Sequence

import httpx
from google.genai.errors import APIError as GoogleGenAIAPIError
from langchain_core.exceptions import OutputParserException
from langchain_google_genai.chat_models import ChatGoogleGenerativeAIError
from groq import APIError as GroqAPIError
from pydantic import Field, ValidationError

from app.config import ConfigurationError, DEFAULT_TOPIC, Settings, load_settings
from app.knowledge.reference_loader import load_reference_material
from app.llm.provider import create_chat_model
from app.prompts.generator_prompt import (
    NON_FACTUAL_SECTIONS,
    REQUIRED_LESSON_SECTIONS,
    TARGET_LEARNER_PROFILE,
    format_generation_messages,
)
from app.schemas import (
    LearnedRule,
    Lesson,
    GenerationFailureStage,
    GenerationErrorCategory,
    LessonValidationSubcode,
    NonEmptyString,
    ReferenceMaterial,
    StrictModel,
)


class LessonGenerationError(RuntimeError):
    """Raised when a lesson response cannot be generated or validated."""

    def __init__(
        self,
        message: str,
        *,
        failure_stage: GenerationFailureStage = GenerationFailureStage.UNKNOWN,
        error_category: GenerationErrorCategory = GenerationErrorCategory.GENERATION_ERROR,
        exception_type: str = "LessonGenerationError",
        validation_subcode: LessonValidationSubcode | None = None,
    ) -> None:
        super().__init__(message)
        self.failure_stage = GenerationFailureStage(failure_stage)
        self.error_category = GenerationErrorCategory(error_category)
        self.exception_type = _sanitize_exception_type(exception_type)
        self.validation_subcode = (
            LessonValidationSubcode(validation_subcode)
            if validation_subcode is not None
            else None
        )


class _GeneratedLessonContent(StrictModel):
    title: NonEmptyString
    sections: dict[NonEmptyString, NonEmptyString] = Field(min_length=1)


CITATION_GROUP_PATTERN = re.compile(r"\[(R[^\]]*)\]")
VALID_CITATION_PATTERN = re.compile(
    r"\[(R[1-9]\d*(?:\s*,\s*R[1-9]\d*)*)\]"
)
REFERENCE_ID_PATTERN = re.compile(r"R[1-9]\d*")
SECTION_NORMALIZATION_PATTERN = re.compile(r"[^a-z0-9]+")


def generate_lesson(
    topic: str = DEFAULT_TOPIC,
    learner_profile: str = TARGET_LEARNER_PROFILE,
    reference_material: ReferenceMaterial | None = None,
    learned_rules: Sequence[str | LearnedRule] = (),
    attempt_number: int = 1,
    previous_feedback: Sequence[str] = (),
    *,
    settings: Settings | None = None,
) -> Lesson:
    """Generate and validate a complete lesson without making an approval decision."""
    if not isinstance(topic, str) or not topic.strip():
        raise ValueError("Topic must not be empty.")
    if not isinstance(learner_profile, str) or not learner_profile.strip():
        raise ValueError("Learner profile must not be empty.")
    if type(attempt_number) is not int or not 1 <= attempt_number <= 3:
        raise ValueError("Attempt number must be between 1 and 3.")

    references = (
        reference_material
        if reference_material is not None
        else load_reference_material()
    )
    current_settings = settings if settings is not None else load_settings()
    messages = format_generation_messages(
        topic=topic.strip(),
        learner_profile=learner_profile.strip(),
        reference_material=references,
        learned_rules=learned_rules,
        attempt_number=attempt_number,
        previous_feedback=previous_feedback,
    )

    try:
        model = create_chat_model(current_settings)
        response = model.with_structured_output(_GeneratedLessonContent).invoke(
            messages
        )
    except OutputParserException as exc:
        raise LessonGenerationError(
            "The model returned malformed structured lesson content.",
            failure_stage=GenerationFailureStage.STRUCTURED_OUTPUT_PARSING,
            error_category=GenerationErrorCategory.STRUCTURED_OUTPUT_ERROR,
            exception_type=type(exc).__name__,
        ) from exc
    except ValidationError as exc:
        raise LessonGenerationError(
            "The model returned lesson content that failed schema validation.",
            failure_stage=GenerationFailureStage.SCHEMA_VALIDATION,
            error_category=GenerationErrorCategory.SCHEMA_VALIDATION_ERROR,
            exception_type=type(exc).__name__,
        ) from exc
    except ConfigurationError as exc:
        raise LessonGenerationError(
            "The LLM configuration is invalid.",
            failure_stage=GenerationFailureStage.PROVIDER_REQUEST,
            error_category=GenerationErrorCategory.CONFIGURATION_ERROR,
            exception_type=type(exc).__name__,
        ) from exc
    except (TimeoutError, httpx.TimeoutException) as exc:
        raise LessonGenerationError(
            "The configured LLM request timed out.",
            failure_stage=GenerationFailureStage.PROVIDER_REQUEST,
            error_category=GenerationErrorCategory.PROVIDER_REQUEST_ERROR,
            exception_type=type(exc).__name__,
        ) from exc
    except (
        GoogleGenAIAPIError,
        ChatGoogleGenerativeAIError,
        GroqAPIError,
    ) as exc:
        raise LessonGenerationError(
            "The configured LLM request failed.",
            failure_stage=GenerationFailureStage.PROVIDER_REQUEST,
            error_category=GenerationErrorCategory.PROVIDER_REQUEST_ERROR,
            exception_type=type(exc).__name__,
        ) from exc
    except Exception as exc:
        raise LessonGenerationError(
            "The configured LLM request failed.",
            failure_stage=GenerationFailureStage.PROVIDER_REQUEST,
            error_category=GenerationErrorCategory.PROVIDER_REQUEST_ERROR,
            exception_type=type(exc).__name__,
        ) from exc

    content = _validate_model_response(response)
    sections, cited_source_ids = _validate_lesson_content(content, references)
    sources_by_id = {source.source_id: source for source in references.sources}
    cited_sources = [
        source
        for source in references.sources
        if source.source_id in cited_source_ids
    ]
    source_section = "\n".join(
        f"- [{source.source_id}] {source.title} | {source.url}"
        for source in cited_sources
    )
    sections["Sources"] = source_section

    markdown_sections = [f"# {content.title}"]
    markdown_sections.extend(
        f"## {heading}\n\n{section_content}"
        for heading, section_content in sections.items()
    )
    try:
        return Lesson(
            topic=topic.strip(),
            title=content.title,
            attempt_number=attempt_number,
            sections=sections,
            full_markdown="\n\n".join(markdown_sections),
            reference_ids=tuple(
                source_id
                for source_id in sources_by_id
                if source_id in cited_source_ids
            ),
        )
    except ValidationError as exc:
        raise LessonGenerationError(
            "The completed lesson failed schema validation.",
            failure_stage=GenerationFailureStage.SCHEMA_VALIDATION,
            error_category=GenerationErrorCategory.SCHEMA_VALIDATION_ERROR,
            exception_type=type(exc).__name__,
        ) from exc


def _validate_model_response(response: object) -> _GeneratedLessonContent:
    if response is None or response == "" or response == {}:
        raise LessonGenerationError(
            "The model returned an empty lesson response.",
            failure_stage=GenerationFailureStage.STRUCTURED_OUTPUT_PARSING,
            error_category=GenerationErrorCategory.STRUCTURED_OUTPUT_ERROR,
        )
    if isinstance(response, _GeneratedLessonContent):
        return response
    if not isinstance(response, Mapping):
        raise LessonGenerationError(
            "The model returned malformed structured lesson content.",
            failure_stage=GenerationFailureStage.STRUCTURED_OUTPUT_PARSING,
            error_category=GenerationErrorCategory.STRUCTURED_OUTPUT_ERROR,
        )
    try:
        return _GeneratedLessonContent.model_validate(response)
    except ValidationError as exc:
        raise LessonGenerationError(
            "The model returned lesson content that failed schema validation.",
            failure_stage=GenerationFailureStage.SCHEMA_VALIDATION,
            error_category=GenerationErrorCategory.SCHEMA_VALIDATION_ERROR,
            exception_type=type(exc).__name__,
        ) from exc


def _validate_lesson_content(
    content: _GeneratedLessonContent,
    reference_material: ReferenceMaterial,
) -> tuple[dict[str, str], set[str]]:
    normalized_required_sections = {
        _normalize_heading(heading) for heading in REQUIRED_LESSON_SECTIONS
    }
    sections_by_normalized_heading: dict[str, tuple[str, str]] = {}
    for heading, section_content in content.sections.items():
        normalized_heading = _normalize_heading(heading)
        if normalized_heading in sections_by_normalized_heading:
            subcode = (
                LessonValidationSubcode.DUPLICATE_REQUIRED_SECTION
                if normalized_heading in normalized_required_sections
                else LessonValidationSubcode.DUPLICATE_SECTION
            )
            raise _lesson_content_error(
                f"The lesson contains duplicate section heading '{heading}'.",
                subcode,
            )
        sections_by_normalized_heading[normalized_heading] = (
            heading,
            section_content,
        )

    missing_sections = [
        heading
        for heading in REQUIRED_LESSON_SECTIONS
        if _normalize_heading(heading) not in sections_by_normalized_heading
    ]
    if missing_sections:
        raise _lesson_content_error(
            "The generated lesson is missing required sections: "
            + ", ".join(missing_sections)
            + ".",
            LessonValidationSubcode.MISSING_REQUIRED_SECTION,
        )

    known_source_ids = {source.source_id for source in reference_material.sources}
    cited_source_ids: set[str] = set()
    normalized_non_factual_sections = {
        _normalize_heading(heading) for heading in NON_FACTUAL_SECTIONS
    }
    canonical_sections: dict[str, str] = {}
    ordered_headings = list(REQUIRED_LESSON_SECTIONS)
    ordered_headings.extend(
        heading
        for heading in content.sections
        if _normalize_heading(heading) not in normalized_required_sections
    )
    for heading in ordered_headings:
        normalized_heading = _normalize_heading(heading)
        original_heading, section_content = sections_by_normalized_heading.get(
            normalized_heading, (heading, content.sections.get(heading, ""))
        )
        section_citations = _extract_citations(section_content)
        unknown_source_ids = section_citations - known_source_ids
        if unknown_source_ids:
            raise _lesson_content_error(
                f"Section '{original_heading}' cites unknown reference IDs: "
                + ", ".join(sorted(unknown_source_ids))
                + ".",
                LessonValidationSubcode.UNKNOWN_REFERENCE_ID,
            )
        if (
            normalized_heading not in normalized_non_factual_sections
            and not section_citations
        ):
            raise _lesson_content_error(
                f"Factual section '{original_heading}' must cite trusted references.",
                LessonValidationSubcode.MISSING_FACTUAL_CITATION,
            )
        cited_source_ids.update(section_citations)
        canonical_sections[heading] = section_content

    if not cited_source_ids:
        raise _lesson_content_error(
            "The generated lesson does not cite any trusted reference material.",
            LessonValidationSubcode.MISSING_FACTUAL_CITATION,
        )
    return canonical_sections, cited_source_ids


def _extract_citations(text: str) -> set[str]:
    citations: set[str] = set()
    for citation_group in CITATION_GROUP_PATTERN.findall(text):
        full_group = f"[{citation_group}]"
        if VALID_CITATION_PATTERN.fullmatch(full_group) is None:
            raise _lesson_content_error(
                f"The generated lesson contains an invalid citation '{full_group}'.",
                LessonValidationSubcode.INVALID_CITATION_FORMAT,
            )
        citations.update(REFERENCE_ID_PATTERN.findall(citation_group))
    return citations


def _normalize_heading(heading: str) -> str:
    return SECTION_NORMALIZATION_PATTERN.sub(" ", heading.casefold()).strip()


def _lesson_content_error(
    message: str,
    subcode: LessonValidationSubcode,
) -> LessonGenerationError:
    return LessonGenerationError(
        message,
        failure_stage=GenerationFailureStage.LESSON_CONTENT_VALIDATION,
        error_category=GenerationErrorCategory.LESSON_CONTENT_VALIDATION_ERROR,
        validation_subcode=subcode,
    )


def _sanitize_exception_type(exception_type: str) -> str:
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", exception_type):
        return exception_type
    return "Exception"
