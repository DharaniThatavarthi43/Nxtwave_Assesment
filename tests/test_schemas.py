from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas import (
    CheckpointId,
    CheckpointStatus,
    EvaluationCheckpoint,
    EvaluationResult,
    GenerationAttempt,
    LearnedRule,
    Lesson,
    RejectionRecord,
)


def make_lesson(attempt_number: int = 1) -> Lesson:
    return Lesson(
        topic="Introduction to RAG",
        title="RAG for beginners",
        attempt_number=attempt_number,
        sections={"Introduction": "RAG uses retrieved information."},
        full_markdown="# RAG for beginners",
        reference_ids=("R1",),
    )


def make_checkpoints() -> tuple[EvaluationCheckpoint, ...]:
    return tuple(
        EvaluationCheckpoint(
            checkpoint_id=checkpoint_id,
            status=CheckpointStatus.PASS,
            reason="The lesson meets this checkpoint.",
            evidence="The introduction explains the idea.",
        )
        for checkpoint_id in CheckpointId
    )


def test_lesson_schema_accepts_required_fields_and_defaults_id() -> None:
    lesson = make_lesson()

    assert lesson.lesson_id is not None
    assert lesson.attempt_number == 1
    assert lesson.reference_ids == ("R1",)


def test_lesson_schema_rejects_empty_sections_and_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        Lesson(
            topic="RAG",
            title="Title",
            attempt_number=1,
            sections={},
            full_markdown="# Title",
            reference_ids=("R1",),
        )
    with pytest.raises(ValidationError):
        Lesson(
            topic="RAG",
            title="Title",
            attempt_number=1,
            sections={"Intro": "Text"},
            full_markdown="# Title",
            reference_ids=("R1",),
            unexpected="not allowed",
        )


def test_lesson_schema_rejects_out_of_range_attempt_and_unknown_reference() -> None:
    with pytest.raises(ValidationError):
        Lesson(
            topic="RAG",
            title="Title",
            attempt_number=4,
            sections={"Intro": "Text"},
            full_markdown="# Title",
            reference_ids=("R1",),
        )
    with pytest.raises(ValidationError):
        Lesson(
            topic="RAG",
            title="Title",
            attempt_number=1,
            sections={"Intro": "Text"},
            full_markdown="# Title",
            reference_ids=("UNKNOWN",),
        )


def test_schema_timestamps_must_be_timezone_aware() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        Lesson(
            topic="RAG",
            title="Title",
            attempt_number=1,
            sections={"Intro": "Text"},
            full_markdown="# Title",
            reference_ids=("R1",),
            generation_timestamp="2026-01-01T10:00:00",
        )


def test_evaluation_result_requires_exactly_six_unique_checkpoints() -> None:
    result = EvaluationResult(
        run_id=uuid4(),
        attempt_number=1,
        overall_status=CheckpointStatus.PASS,
        checkpoints=make_checkpoints(),
        overall_reason="Structured result for later workflow use.",
    )
    assert len(result.checkpoints) == 6

    with pytest.raises(ValidationError):
        EvaluationResult(
            run_id=uuid4(),
            attempt_number=1,
            overall_status=CheckpointStatus.PASS,
            checkpoints=make_checkpoints()[:-1],
            overall_reason="Missing a checkpoint.",
        )

    duplicate = list(make_checkpoints())
    duplicate[-1] = duplicate[0]
    with pytest.raises(ValidationError):
        EvaluationResult(
            run_id=uuid4(),
            attempt_number=1,
            overall_status=CheckpointStatus.PASS,
            checkpoints=tuple(duplicate),
            overall_reason="Duplicate checkpoint.",
        )


def test_evaluation_result_rejects_overall_status_inconsistent_with_checkpoints() -> None:
    one_failed = tuple(
        EvaluationCheckpoint(
            checkpoint_id=checkpoint_id,
            status=(
                CheckpointStatus.FAIL
                if checkpoint_id is CheckpointId.ACCURACY_AND_GROUNDING
                else CheckpointStatus.PASS
            ),
            reason="The lesson meets or fails this checkpoint.",
            evidence="The lesson contains this supporting excerpt.",
        )
        for checkpoint_id in CheckpointId
    )
    with pytest.raises(ValidationError, match="Overall status must be FAIL"):
        EvaluationResult(
            run_id=uuid4(),
            attempt_number=1,
            overall_status=CheckpointStatus.PASS,
            checkpoints=one_failed,
            failed_checkpoints=(CheckpointId.ACCURACY_AND_GROUNDING,),
            overall_reason="One checkpoint failed.",
        )

    with pytest.raises(ValidationError, match="Overall status must be FAIL"):
        EvaluationResult(
            run_id=uuid4(),
            attempt_number=1,
            overall_status=CheckpointStatus.FAIL,
            checkpoints=make_checkpoints(),
            overall_reason="All checkpoints passed.",
        )


def test_checkpoint_schema_rejects_invalid_status_or_id() -> None:
    with pytest.raises(ValidationError):
        EvaluationCheckpoint(
            checkpoint_id="C7",
            status="PASS",
            reason="Reason",
            evidence="Evidence",
        )
    with pytest.raises(ValidationError):
        EvaluationCheckpoint(
            checkpoint_id="C1",
            status="MAYBE",
            reason="Reason",
            evidence="Evidence",
        )


def test_generation_attempt_requires_matching_lesson_attempt_number() -> None:
    with pytest.raises(ValidationError, match="must match"):
        GenerationAttempt(
            run_id=uuid4(),
            attempt_number=2,
            generated_lesson=make_lesson(attempt_number=1),
        )


def test_rejection_schema_requires_evidence_for_each_failed_checkpoint() -> None:
    rejection = RejectionRecord(
        run_id=uuid4(),
        attempt_number=1,
        failed_checkpoints=(CheckpointId.CLEAR_EXPLANATIONS,),
        failure_reasons={
            CheckpointId.CLEAR_EXPLANATIONS: "A term is not explained."
        },
        evidence={CheckpointId.CLEAR_EXPLANATIONS: "The second section uses jargon."},
        correction_instructions=("Define the term before using it.",),
    )
    assert rejection.failed_checkpoints == (CheckpointId.CLEAR_EXPLANATIONS,)

    with pytest.raises(ValidationError, match="cover exactly"):
        RejectionRecord(
            run_id=uuid4(),
            attempt_number=1,
            failed_checkpoints=(CheckpointId.CLEAR_EXPLANATIONS,),
            failure_reasons={CheckpointId.ACCURACY_AND_GROUNDING: "Wrong map."},
            evidence={CheckpointId.CLEAR_EXPLANATIONS: "Evidence."},
            correction_instructions=("Explain the term.",),
        )


def test_learned_rule_schema_validates_confidence_and_provenance() -> None:
    rule = LearnedRule(
        rule_description="Explain important terms in simple language.",
        rationale="Repeated terminology failures.",
        related_checkpoint=CheckpointId.CLEAR_EXPLANATIONS,
        failure_count=2,
        confidence=0.8,
        source_rejection_ids=(uuid4(),),
    )
    assert rule.active_status is True

    with pytest.raises(ValidationError):
        LearnedRule(
            rule_description="Explain terms.",
            rationale="Repeated failures.",
            related_checkpoint=CheckpointId.CLEAR_EXPLANATIONS,
            failure_count=0,
            confidence=1.2,
            source_rejection_ids=(),
        )
