from collections.abc import Sequence
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest
from groq import (
    APIError as GroqAPIError,
    APIStatusError,
    AuthenticationError,
    InternalServerError,
    NotFoundError,
    RateLimitError,
)
from langchain_google_genai.chat_models import ChatGoogleGenerativeAIError
from pydantic import ValidationError

from app.agents import evaluator
from app.agents.evaluator import EvaluatorError, evaluate_lesson
from app.config import Settings
from app.knowledge.reference_loader import load_reference_material
from app.schemas import (
    CheckpointId,
    CheckpointStatus,
    EvaluationErrorCategory,
    EvaluationFailureStage,
    EvaluationRetryDisposition,
    EvaluationResult,
    Lesson,
)


LESSON_EVIDENCE = {
    CheckpointId.ACCURACY_AND_GROUNDING: (
        "RAG retrieves passages and adds them to the question as context. [R1]"
    ),
    CheckpointId.BEGINNER_FRIENDLY_LANGUAGE: (
        "A student can think of the retriever as a helpful librarian. [R2]"
    ),
    CheckpointId.TEACHING_THROUGH_EXAMPLES: (
        "A student asks about a scholarship, so the system searches its handbook. [R2]"
    ),
    CheckpointId.CLEAR_EXPLANATIONS: (
        "An embedding is a list of numbers that represents text for search. [R2]"
    ),
    CheckpointId.KEY_CONCEPT_COVERAGE: (
        "RAG retrieves useful information, adds it as context, and generates an answer. [R1]"
    ),
    CheckpointId.TEACHING_FLOW: (
        "First prepare the documents, then retrieve passages, and finally generate an answer. [R2]"
    ),
}


def make_lesson() -> Lesson:
    sections = {
        f"Evidence {checkpoint_id.value}": excerpt
        for checkpoint_id, excerpt in LESSON_EVIDENCE.items()
    }
    return Lesson(
        topic="Introduction to RAG",
        title="RAG for Beginners",
        attempt_number=2,
        sections=sections,
        full_markdown="\n\n".join(
            f"## {heading}\n\n{text}" for heading, text in sections.items()
        ),
        reference_ids=("R1", "R2"),
    )


def make_response(
    failed: set[CheckpointId] | None = None,
) -> dict[str, object]:
    failed_checkpoint_ids = failed or set()
    checkpoints = []
    for checkpoint_id in CheckpointId:
        is_failed = checkpoint_id in failed_checkpoint_ids
        checkpoints.append(
            {
                "checkpoint_id": checkpoint_id.value,
                "status": "FAIL" if is_failed else "PASS",
                "reason": (
                    f"The quoted lesson passage does not meet {checkpoint_id.value} "
                    "because it lacks a required quality."
                    if is_failed
                    else f"The quoted lesson passage clearly meets {checkpoint_id.value}."
                ),
                "evidence": LESSON_EVIDENCE[checkpoint_id],
            }
        )
    return {
        "checkpoints": checkpoints,
        "correction_instructions": [
            f"{checkpoint_id.value}: Improve the relevant lesson passage."
            for checkpoint_id in CheckpointId
            if checkpoint_id in failed_checkpoint_ids
        ],
    }


class FakeStructuredModel:
    def __init__(
        self,
        response: object = None,
        error: Exception | None = None,
        outcomes: list[object] | None = None,
    ) -> None:
        self.response = response
        self.error = error
        self.outcomes = list(outcomes or [])
        self.call_count = 0
        self.messages: Sequence[Any] | None = None

    def invoke(self, messages: Sequence[Any]) -> object:
        self.call_count += 1
        self.messages = messages
        if self.outcomes:
            outcome = self.outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        if self.error is not None:
            raise self.error
        return self.response


class FakeChatModel:
    def __init__(self, structured_model: FakeStructuredModel) -> None:
        self.structured_model = structured_model

    def with_structured_output(self, schema: type) -> FakeStructuredModel:
        return self.structured_model


def use_fake_model(
    monkeypatch: pytest.MonkeyPatch,
    fake_model: FakeChatModel,
) -> None:
    monkeypatch.setattr(
        evaluator,
        "create_chat_model",
        lambda settings, **kwargs: fake_model,
    )


def make_settings(*, max_retry_after_seconds: int = 120) -> Settings:
    return Settings(
        app_env="test",
        log_level="INFO",
        database_path=Path("test.db"),
        max_retries=2,
        llm_provider="google",
        llm_model="unit-test-model",
        llm_api_key="not-a-real-api-key",
        evaluator_max_retry_after_seconds=max_retry_after_seconds,
    )


def run_evaluation(
    response: object,
    monkeypatch: pytest.MonkeyPatch,
    *,
    error: Exception | None = None,
) -> tuple[EvaluationResult, FakeStructuredModel]:
    structured_model = FakeStructuredModel(response=response, error=error)
    use_fake_model(monkeypatch, FakeChatModel(structured_model))
    result = evaluate_lesson(
        lesson=make_lesson(),
        reference_material=load_reference_material(),
        run_id=uuid4(),
        settings=make_settings(),
    )
    return result, structured_model


def test_evaluator_passes_when_all_six_checkpoints_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result, _ = run_evaluation(make_response(), monkeypatch)

    assert result.overall_status is CheckpointStatus.PASS
    assert result.failed_checkpoints == ()
    assert tuple(checkpoint.checkpoint_id for checkpoint in result.checkpoints) == tuple(
        CheckpointId
    )
    assert all(
        checkpoint.status is CheckpointStatus.PASS
        and checkpoint.reason
        and checkpoint.evidence
        for checkpoint in result.checkpoints
    )


def test_one_failed_checkpoint_makes_overall_result_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failed = {CheckpointId.TEACHING_THROUGH_EXAMPLES}
    result, _ = run_evaluation(make_response(failed), monkeypatch)

    assert result.overall_status is CheckpointStatus.FAIL
    assert result.failed_checkpoints == tuple(failed)
    assert result.correction_instructions


def test_multiple_failed_checkpoints_make_overall_result_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failed = {
        CheckpointId.ACCURACY_AND_GROUNDING,
        CheckpointId.CLEAR_EXPLANATIONS,
    }
    result, _ = run_evaluation(make_response(failed), monkeypatch)

    assert result.overall_status is CheckpointStatus.FAIL
    assert result.failed_checkpoints == tuple(
        checkpoint_id for checkpoint_id in CheckpointId if checkpoint_id in failed
    )
    assert len(result.correction_instructions) == len(failed)


def test_missing_checkpoint_evaluation_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = make_response()
    response["checkpoints"] = response["checkpoints"][:-1]

    with pytest.raises(EvaluatorError, match="invalid structured evaluation"):
        run_evaluation(response, monkeypatch)


@pytest.mark.parametrize(
    "response",
    [
        "not structured",
        {
            "checkpoints": [
                {
                    "checkpoint_id": checkpoint_id.value,
                    "status": "MAYBE",
                    "reason": "The checkpoint result is not a valid binary status.",
                    "evidence": LESSON_EVIDENCE[checkpoint_id],
                }
                for checkpoint_id in CheckpointId
            ],
            "correction_instructions": [],
        },
    ],
)
def test_invalid_evaluator_response_is_rejected(
    response: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(EvaluatorError, match="invalid structured evaluation"):
        run_evaluation(response, monkeypatch)


def test_evaluator_rejects_evidence_not_found_in_lesson(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = make_response()
    response["checkpoints"][0]["evidence"] = "This fabricated sentence is unsupported."

    with pytest.raises(EvaluatorError, match="not a verbatim excerpt"):
        run_evaluation(response, monkeypatch)


def test_evaluator_rejects_unknown_reference_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = make_response()
    response["checkpoints"][0]["reason"] = (
        "This passage is supported by source [R99] in the trusted notes."
    )

    with pytest.raises(EvaluatorError, match="unknown reference IDs: R99"):
        run_evaluation(response, monkeypatch)


def test_evaluator_rejects_failed_checkpoint_without_correction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = make_response({CheckpointId.KEY_CONCEPT_COVERAGE})
    response["correction_instructions"] = []

    with pytest.raises(EvaluatorError, match="require at least one correction"):
        run_evaluation(response, monkeypatch)


def test_evaluator_requires_corrections_for_each_failed_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = make_response(
        {
            CheckpointId.ACCURACY_AND_GROUNDING,
            CheckpointId.CLEAR_EXPLANATIONS,
        }
    )
    response["correction_instructions"] = [
        "C1: Correct the unsupported factual claim."
    ]

    with pytest.raises(EvaluatorError, match="requires its own correction"):
        run_evaluation(response, monkeypatch)


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (
            ChatGoogleGenerativeAIError("simulated provider failure"),
            "evaluation request failed",
        ),
        (
            httpx.TimeoutException("simulated timeout"),
            "evaluation request timed out",
        ),
        (
            GroqAPIError(
                "simulated Groq API failure",
                httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
                body=None,
            ),
            "evaluation request failed",
        ),
    ],
)
def test_evaluator_surfaces_provider_errors_safely(
    error: Exception,
    message: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    structured_model = FakeStructuredModel(error=error)
    use_fake_model(monkeypatch, FakeChatModel(structured_model))

    with pytest.raises(EvaluatorError, match=message) as error_info:
        evaluate_lesson(
            lesson=make_lesson(),
            reference_material=load_reference_material(),
            settings=make_settings(),
        )

    assert (
        error_info.value.retry_disposition
        is EvaluationRetryDisposition.RETRY_SKIPPED
    )


def make_status_error(
    status_code: int,
    *,
    headers: dict[str, str] | None = None,
) -> APIStatusError:
    response = httpx.Response(
        status_code,
        headers=headers,
        request=httpx.Request(
            "POST",
            "https://api.groq.com/openai/v1/chat/completions",
        ),
    )
    arguments = {
        "message": "sensitive provider response and API details",
        "response": response,
        "body": {"sensitive": "provider payload"},
    }
    if status_code == 429:
        return RateLimitError(**arguments)
    if 500 <= status_code <= 599:
        return InternalServerError(**arguments)
    if status_code == 401:
        return AuthenticationError(**arguments)
    if status_code == 404:
        return NotFoundError(**arguments)
    return APIStatusError(**arguments)


def test_evaluator_retries_429_and_respects_retry_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    structured_model = FakeStructuredModel(
        outcomes=[
            make_status_error(429, headers={"Retry-After": "3"}),
            make_response(),
        ]
    )
    use_fake_model(monkeypatch, FakeChatModel(structured_model))
    delays: list[float] = []
    monkeypatch.setattr(evaluator, "sleep", delays.append)

    result = evaluate_lesson(
        lesson=make_lesson(),
        reference_material=load_reference_material(),
        settings=make_settings(),
    )

    assert result.overall_status is CheckpointStatus.PASS
    assert structured_model.call_count == 2
    assert delays == [3.0]


def test_evaluator_honors_long_retry_after_within_configured_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    structured_model = FakeStructuredModel(
        outcomes=[
            make_status_error(429, headers={"Retry-After": "45"}),
            make_response(),
        ]
    )
    use_fake_model(monkeypatch, FakeChatModel(structured_model))
    delays: list[float] = []
    monkeypatch.setattr(evaluator, "sleep", delays.append)

    result = evaluate_lesson(
        lesson=make_lesson(),
        reference_material=load_reference_material(),
        settings=make_settings(max_retry_after_seconds=60),
    )

    assert result.overall_status is CheckpointStatus.PASS
    assert structured_model.call_count == 2
    assert delays == [45.0]


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Retry-After": "not-a-delay"},
    ],
)
def test_evaluator_uses_bounded_backoff_when_retry_after_is_missing_or_malformed(
    headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    structured_model = FakeStructuredModel(
        outcomes=[make_status_error(429, headers=headers), make_response()]
    )
    use_fake_model(monkeypatch, FakeChatModel(structured_model))
    delays: list[float] = []
    monkeypatch.setattr(evaluator, "sleep", delays.append)

    result = evaluate_lesson(
        lesson=make_lesson(),
        reference_material=load_reference_material(),
        settings=make_settings(),
    )

    assert result.overall_status is CheckpointStatus.PASS
    assert structured_model.call_count == 2
    assert delays == [evaluator.EVALUATOR_RETRY_BASE_DELAY_SECONDS]


def test_evaluator_retries_503_with_bounded_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    structured_model = FakeStructuredModel(
        outcomes=[make_status_error(503), make_response()]
    )
    use_fake_model(monkeypatch, FakeChatModel(structured_model))
    delays: list[float] = []
    monkeypatch.setattr(evaluator, "sleep", delays.append)

    result = evaluate_lesson(
        lesson=make_lesson(),
        reference_material=load_reference_material(),
        settings=make_settings(),
    )

    assert result.overall_status is CheckpointStatus.PASS
    assert structured_model.call_count == 2
    assert delays == [evaluator.EVALUATOR_RETRY_BASE_DELAY_SECONDS]


def test_evaluator_exhausts_bounded_429_retries_with_safe_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    structured_model = FakeStructuredModel(
        outcomes=[make_status_error(429) for _ in range(3)]
    )
    use_fake_model(monkeypatch, FakeChatModel(structured_model))
    delays: list[float] = []
    monkeypatch.setattr(evaluator, "sleep", delays.append)

    with pytest.raises(EvaluatorError) as error:
        evaluate_lesson(
            lesson=make_lesson(),
            reference_material=load_reference_material(),
            settings=make_settings(),
        )

    assert structured_model.call_count == (
        evaluator.MAX_EVALUATOR_API_RETRIES + 1
    )
    assert delays == [
        evaluator.EVALUATOR_RETRY_BASE_DELAY_SECONDS,
        evaluator.EVALUATOR_RETRY_BASE_DELAY_SECONDS * 2,
    ]
    assert error.value.failure_stage is EvaluationFailureStage.API_REQUEST
    assert error.value.error_category is EvaluationErrorCategory.RATE_LIMITED
    assert error.value.exception_type == "RateLimitError"
    assert (
        error.value.retry_disposition
        is EvaluationRetryDisposition.RETRIES_EXHAUSTED
    )
    assert "sensitive provider response" not in str(error.value)


@pytest.mark.parametrize("status_code", [401, 404])
def test_evaluator_does_not_retry_permanent_provider_errors(
    status_code: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    structured_model = FakeStructuredModel(error=make_status_error(status_code))
    use_fake_model(monkeypatch, FakeChatModel(structured_model))
    delays: list[float] = []
    monkeypatch.setattr(evaluator, "sleep", delays.append)

    with pytest.raises(EvaluatorError) as error:
        evaluate_lesson(
            lesson=make_lesson(),
            reference_material=load_reference_material(),
            settings=make_settings(),
        )

    assert structured_model.call_count == 1
    assert delays == []
    assert (
        error.value.error_category
        is EvaluationErrorCategory.PROVIDER_PERMANENT_ERROR
    )
    assert (
        error.value.retry_disposition
        is EvaluationRetryDisposition.PERMANENT_PROVIDER_FAILURE
    )


def test_evaluator_marks_retry_after_above_configured_cap_without_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    structured_model = FakeStructuredModel(
        outcomes=[
            make_status_error(
                429,
                headers={
                    "Retry-After": "121"
                },
            ),
            make_response(),
        ]
    )
    use_fake_model(monkeypatch, FakeChatModel(structured_model))
    delays: list[float] = []
    monkeypatch.setattr(evaluator, "sleep", delays.append)

    with pytest.raises(EvaluatorError) as error:
        evaluate_lesson(
            lesson=make_lesson(),
            reference_material=load_reference_material(),
            settings=make_settings(max_retry_after_seconds=120),
        )

    assert structured_model.call_count == 1
    assert delays == []
    assert error.value.error_category is EvaluationErrorCategory.RATE_LIMITED
    assert (
        error.value.retry_disposition
        is EvaluationRetryDisposition.RETRY_AFTER_EXCEEDS_CAP
    )


def test_llm_cannot_override_the_application_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = make_response({CheckpointId.ACCURACY_AND_GROUNDING})
    response["overall_status"] = "PASS"

    with pytest.raises(EvaluatorError, match="invalid structured evaluation"):
        run_evaluation(response, monkeypatch)
