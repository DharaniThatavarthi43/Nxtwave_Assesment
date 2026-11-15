import math
import re
import unicodedata
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from time import sleep
from uuid import UUID, uuid4

import httpx
from langchain_core.exceptions import OutputParserException
from langchain_core.messages import HumanMessage
from pydantic import Field, ValidationError, model_validator

from app.config import ConfigurationError, Settings, load_settings
from app.knowledge.reference_loader import load_reference_material
from app.llm.provider import create_chat_model
from app.prompts.evaluator_prompt import format_evaluation_messages
from app.schemas import (
    CHECKPOINT_LABELS,
    CheckpointId,
    CheckpointStatus,
    EvaluationErrorCategory,
    EvaluationFailureStage,
    EvaluationRetryDisposition,
    EvaluationCheckpoint,
    EvaluationResult,
    Lesson,
    NonEmptyString,
    ReferenceMaterial,
    StrictModel,
)


MAX_EVALUATOR_API_RETRIES = 2
MAX_EVALUATOR_OUTPUT_RETRIES = 2
EVALUATOR_RETRY_BASE_DELAY_SECONDS = 1.0
TOKEN_RATE_LIMIT_RETRY_DELAY_SECONDS = 60.0


class EvaluatorError(RuntimeError):
    """Raised when an evaluation cannot be safely generated or validated."""

    def __init__(
        self,
        message: str,
        *,
        failure_stage: EvaluationFailureStage = (
            EvaluationFailureStage.EVALUATION_VALIDATION
        ),
        error_category: EvaluationErrorCategory = (
            EvaluationErrorCategory.EVALUATION_VALIDATION_ERROR
        ),
        exception_type: str = "EvaluatorError",
        retry_disposition: EvaluationRetryDisposition | None = None,
    ) -> None:
        super().__init__(message)
        self.failure_stage = EvaluationFailureStage(failure_stage)
        self.error_category = EvaluationErrorCategory(error_category)
        self.exception_type = _sanitize_exception_type(exception_type)
        self.retry_disposition = (
            EvaluationRetryDisposition(retry_disposition)
            if retry_disposition is not None
            else None
        )


class _EvaluatorResponse(StrictModel):
    checkpoints: tuple[EvaluationCheckpoint, ...] = Field(
        min_length=len(CheckpointId),
        max_length=len(CheckpointId),
    )
    correction_instructions: tuple[NonEmptyString, ...] = ()

    @model_validator(mode="after")
    def validate_checkpoint_set(self) -> "_EvaluatorResponse":
        checkpoint_ids = [checkpoint.checkpoint_id for checkpoint in self.checkpoints]
        if len(checkpoint_ids) != len(set(checkpoint_ids)):
            raise ValueError("Evaluator checkpoint IDs must be unique.")
        if set(checkpoint_ids) != set(CheckpointId):
            raise ValueError("Evaluator response must contain checkpoints C1 through C6.")
        return self


CITATION_GROUP_PATTERN = re.compile(r"\[(R[^\]]*)\]")
VALID_CITATION_PATTERN = re.compile(
    r"\[(R[1-9]\d*(?:\s*,\s*R[1-9]\d*)*)\]"
)
REFERENCE_ID_PATTERN = re.compile(r"\bR\d+\b")


def evaluate_lesson(
    lesson: Lesson,
    reference_material: ReferenceMaterial | None = None,
    run_id: UUID | None = None,
    *,
    settings: Settings | None = None,
) -> EvaluationResult:
    """Evaluate all mandatory checkpoints and calculate the final decision in code."""
    references = (
        reference_material
        if reference_material is not None
        else load_reference_material()
    )
    current_settings = settings if settings is not None else load_settings()
    messages = format_evaluation_messages(lesson, references)

    try:
        model = create_chat_model(
            current_settings,
            max_retries=0,
            max_output_tokens=2048,
            reasoning_effort="low",
        )
        structured_model = model.with_structured_output(_EvaluatorResponse)
    except ConfigurationError as exc:
        raise EvaluatorError(
            "The LLM configuration is invalid.",
            failure_stage=EvaluationFailureStage.API_REQUEST,
            error_category=EvaluationErrorCategory.CONFIGURATION_ERROR,
            exception_type=type(exc).__name__,
        ) from exc
    except Exception as exc:
        raise _provider_evaluator_error(exc) from exc

    evaluator_messages = list(messages)
    for output_retry in range(MAX_EVALUATOR_OUTPUT_RETRIES + 1):
        response = _invoke_with_bounded_retries(
            lambda: structured_model.invoke(evaluator_messages),
            max_retry_after_seconds=current_settings.evaluator_max_retry_after_seconds,
        )
        try:
            evaluator_response = _validate_model_response(response)
            _validate_evidence(evaluator_response, lesson, references)
            break
        except EvaluatorError as exc:
            if output_retry >= MAX_EVALUATOR_OUTPUT_RETRIES:
                raise
            evaluator_messages = [
                *messages,
                HumanMessage(
                    content=(
                        "Your previous checkpoint response failed local validation: "
                        f"{exc} Return a complete corrected result for C1 through C6. "
                        "For evidence, copy one complete sentence from the lesson "
                        "word for word. Do not paraphrase, shorten, or use ellipses."
                    )
                ),
            ]

    checkpoints_by_id = {
        checkpoint.checkpoint_id: checkpoint
        for checkpoint in evaluator_response.checkpoints
    }
    ordered_checkpoints = tuple(
        checkpoints_by_id[checkpoint_id] for checkpoint_id in CheckpointId
    )
    failed_checkpoints = tuple(
        checkpoint.checkpoint_id
        for checkpoint in ordered_checkpoints
        if checkpoint.status is CheckpointStatus.FAIL
    )
    if failed_checkpoints and not evaluator_response.correction_instructions:
        raise EvaluatorError(
            "Failed checkpoints require at least one correction instruction."
        )
    missing_corrections = [
        checkpoint_id
        for checkpoint_id in failed_checkpoints
        if not any(
            instruction.strip().upper().startswith(f"{checkpoint_id.value}:")
            for instruction in evaluator_response.correction_instructions
        )
    ]
    if missing_corrections:
        raise EvaluatorError(
            "Each failed checkpoint requires its own correction instruction: "
            + ", ".join(checkpoint_id.value for checkpoint_id in missing_corrections)
            + "."
        )
    if not failed_checkpoints and evaluator_response.correction_instructions:
        raise EvaluatorError(
            "Correction instructions must be empty when all checkpoints pass."
        )

    overall_status = (
        CheckpointStatus.FAIL if failed_checkpoints else CheckpointStatus.PASS
    )
    if failed_checkpoints:
        failed_labels = ", ".join(
            f"{checkpoint_id.value} ({CHECKPOINT_LABELS[checkpoint_id]})"
            for checkpoint_id in failed_checkpoints
        )
        overall_reason = f"Failed mandatory checkpoints: {failed_labels}."
    else:
        overall_reason = "All six mandatory checkpoints passed."

    return EvaluationResult(
        run_id=run_id if run_id is not None else uuid4(),
        attempt_number=lesson.attempt_number,
        overall_status=overall_status,
        checkpoints=ordered_checkpoints,
        failed_checkpoints=failed_checkpoints,
        correction_instructions=evaluator_response.correction_instructions,
        overall_reason=overall_reason,
    )


def _invoke_with_bounded_retries(
    invoke: Callable[[], object],
    *,
    max_retry_after_seconds: float,
) -> object:
    for retry_number in range(MAX_EVALUATOR_API_RETRIES + 1):
        try:
            return invoke()
        except OutputParserException as exc:
            raise EvaluatorError(
                "The model returned a malformed structured evaluation.",
                failure_stage=EvaluationFailureStage.STRUCTURED_OUTPUT_PARSING,
                error_category=EvaluationErrorCategory.STRUCTURED_OUTPUT_ERROR,
                exception_type=type(exc).__name__,
            ) from exc
        except ValidationError as exc:
            raise EvaluatorError(
                "The model returned an evaluation that failed schema validation.",
                failure_stage=EvaluationFailureStage.SCHEMA_VALIDATION,
                error_category=EvaluationErrorCategory.SCHEMA_VALIDATION_ERROR,
                exception_type=type(exc).__name__,
            ) from exc
        except Exception as exc:
            status_code = _http_status_code(exc)
            retry_after = _retry_after_seconds(exc)
            token_rate_limited = _is_token_rate_limited(exc)
            retryable = status_code == 429 or token_rate_limited or (
                status_code is not None and 500 <= status_code <= 599
            )
            if not retryable:
                disposition = (
                    EvaluationRetryDisposition.PERMANENT_PROVIDER_FAILURE
                    if status_code is not None and 400 <= status_code <= 499
                    else EvaluationRetryDisposition.RETRY_SKIPPED
                )
                raise _provider_evaluator_error(
                    exc,
                    retry_disposition=disposition,
                ) from exc
            if retry_after is not None:
                if retry_after > max_retry_after_seconds:
                    raise _provider_evaluator_error(
                        exc,
                        retry_disposition=(
                            EvaluationRetryDisposition.RETRY_AFTER_EXCEEDS_CAP
                        ),
                    ) from exc
                delay = retry_after
            elif token_rate_limited:
                delay = TOKEN_RATE_LIMIT_RETRY_DELAY_SECONDS
            else:
                delay = min(
                    EVALUATOR_RETRY_BASE_DELAY_SECONDS * (2**retry_number),
                    max_retry_after_seconds,
                )
            if retry_number >= MAX_EVALUATOR_API_RETRIES:
                raise _provider_evaluator_error(
                    exc,
                    retry_disposition=EvaluationRetryDisposition.RETRIES_EXHAUSTED,
                ) from exc
            sleep(delay)

    raise EvaluatorError(
        "Evaluator request ended without a response.",
        failure_stage=EvaluationFailureStage.API_REQUEST,
        error_category=EvaluationErrorCategory.PROVIDER_ERROR,
    )


def _http_status_code(error: Exception) -> int | None:
    response = getattr(error, "response", None)
    for status_code in (
        getattr(error, "status_code", None),
        getattr(error, "code", None),
        getattr(response, "status_code", None),
    ):
        if type(status_code) is int and 100 <= status_code <= 599:
            return status_code
    return None


def _is_token_rate_limited(error: Exception) -> bool:
    body = getattr(error, "body", None)
    response = getattr(error, "response", None)
    if body is None and response is not None:
        try:
            body = response.json()
        except (AttributeError, TypeError, ValueError):
            body = None
    message = str(body).casefold() if body is not None else str(error).casefold()
    return "rate_limit_exceeded" in message or "tokens per minute" in message


def _retry_after_seconds(error: Exception) -> float | None:
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", None)
    if headers is None:
        headers = getattr(error, "headers", None)
    if headers is None:
        return None
    try:
        value = headers.get("Retry-After")
    except (AttributeError, TypeError):
        return None
    if not isinstance(value, str) or not value.strip():
        return None

    value = value.strip()
    try:
        seconds = float(value)
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError, IndexError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        seconds = (retry_at - datetime.now(timezone.utc)).total_seconds()
    if not math.isfinite(seconds) or seconds < 0:
        return None
    return seconds


def _provider_evaluator_error(
    error: Exception,
    *,
    retry_disposition: EvaluationRetryDisposition = (
        EvaluationRetryDisposition.RETRY_SKIPPED
    ),
) -> EvaluatorError:
    status_code = _http_status_code(error)
    if status_code == 429 or _is_token_rate_limited(error):
        category = EvaluationErrorCategory.RATE_LIMITED
    elif status_code is not None and 500 <= status_code <= 599:
        category = EvaluationErrorCategory.PROVIDER_SERVER_ERROR
    elif status_code is not None and 400 <= status_code <= 499:
        category = EvaluationErrorCategory.PROVIDER_PERMANENT_ERROR
    else:
        category = EvaluationErrorCategory.PROVIDER_ERROR
    message = (
        "The configured LLM evaluation request timed out."
        if isinstance(error, (TimeoutError, httpx.TimeoutException))
        else "The configured LLM evaluation request failed."
    )
    return EvaluatorError(
        message,
        failure_stage=EvaluationFailureStage.API_REQUEST,
        error_category=category,
        exception_type=type(error).__name__,
        retry_disposition=retry_disposition,
    )


def _sanitize_exception_type(exception_type: str) -> str:
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", exception_type):
        return exception_type
    return "Exception"


def _validate_model_response(response: object) -> _EvaluatorResponse:
    if response is None or response == "" or response == {}:
        raise EvaluatorError(
            "The model returned an empty evaluation response.",
            failure_stage=EvaluationFailureStage.STRUCTURED_OUTPUT_PARSING,
            error_category=EvaluationErrorCategory.STRUCTURED_OUTPUT_ERROR,
        )
    if isinstance(response, _EvaluatorResponse):
        return response
    if not isinstance(response, Mapping):
        raise EvaluatorError(
            "The model returned an invalid structured evaluation.",
            failure_stage=EvaluationFailureStage.STRUCTURED_OUTPUT_PARSING,
            error_category=EvaluationErrorCategory.STRUCTURED_OUTPUT_ERROR,
        )
    try:
        return _EvaluatorResponse.model_validate(response)
    except ValidationError as exc:
        raise EvaluatorError(
            "The model returned an invalid structured evaluation.",
            failure_stage=EvaluationFailureStage.SCHEMA_VALIDATION,
            error_category=EvaluationErrorCategory.SCHEMA_VALIDATION_ERROR,
            exception_type=type(exc).__name__,
        ) from exc


def _validate_evidence(
    response: _EvaluatorResponse,
    lesson: Lesson,
    reference_material: ReferenceMaterial,
) -> None:
    normalized_lesson = _normalize_text(lesson.full_markdown)
    known_source_ids = {
        source.source_id for source in reference_material.sources
    }
    for checkpoint in response.checkpoints:
        if len(checkpoint.reason.strip()) < 20:
            raise EvaluatorError(
                f"{checkpoint.checkpoint_id.value} requires a clear evaluation reason."
            )
        if not _evidence_is_supported(checkpoint.evidence, normalized_lesson):
            raise EvaluatorError(
                f"{checkpoint.checkpoint_id.value} evidence is not a verbatim "
                "excerpt from the candidate lesson."
            )
        cited_ids = _extract_citations(checkpoint.reason)
        unknown_source_ids = cited_ids - known_source_ids
        if unknown_source_ids:
            raise EvaluatorError(
                f"{checkpoint.checkpoint_id.value} cites unknown reference IDs: "
                + ", ".join(sorted(unknown_source_ids))
                + "."
            )


def _extract_citations(text: str) -> set[str]:
    citations: set[str] = set()
    for citation_group in CITATION_GROUP_PATTERN.findall(text):
        full_group = f"[{citation_group}]"
        if VALID_CITATION_PATTERN.fullmatch(full_group) is None:
            raise EvaluatorError(f"Invalid reference citation '{full_group}'.")
        citations.update(REFERENCE_ID_PATTERN.findall(citation_group))
    citations.update(REFERENCE_ID_PATTERN.findall(text))
    return citations


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return " ".join(re.sub(r"[^\w]+", " ", normalized).split())


def _evidence_is_supported(evidence: str, normalized_lesson: str) -> bool:
    normalized_evidence = _normalize_text(evidence)
    if len(normalized_evidence) < 15:
        return False
    if normalized_evidence in normalized_lesson:
        return True

    # Allow an ellipsis to mark omitted text in a quote, while still requiring
    # every quoted segment to occur verbatim and in order in the lesson. This
    # handles common evaluator output for long examples and numbered lists.
    segments = re.split(r"(?:\.{3,}|…+)", evidence)
    normalized_segments = [_normalize_text(segment) for segment in segments]
    normalized_segments = [segment for segment in normalized_segments if segment]
    if len(normalized_segments) < 2:
        return False
    position = 0
    for segment in normalized_segments:
        if len(segment) < 12:
            return False
        match_at = normalized_lesson.find(segment, position)
        if match_at < 0:
            return False
        position = match_at + len(segment)
    return True
