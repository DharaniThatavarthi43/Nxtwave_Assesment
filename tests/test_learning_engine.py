from pathlib import Path

import pytest

from app.config import DEFAULT_TOPIC
from app.memory.learning_engine import (
    RECURRENCE_THRESHOLD,
    RULE_GUIDANCE,
    create_or_update_learned_rule,
    get_relevant_learned_rules,
    identify_failure_patterns,
    learn_from_rejection,
)
from app.memory.memory_manager import MemoryManager
from app.schemas import (
    CheckpointId,
    CheckpointStatus,
    EvaluationCheckpoint,
    EvaluationResult,
    ExecutionRun,
    GenerationAttempt,
    Lesson,
    RejectionRecord,
)


def _failure_records(
    memory: MemoryManager,
    *,
    checkpoint_id: CheckpointId = CheckpointId.CLEAR_EXPLANATIONS,
    topic: str = DEFAULT_TOPIC,
    attempt_count: int = 1,
) -> tuple[ExecutionRun, tuple[RejectionRecord, ...]]:
    run = ExecutionRun(topic=topic)
    memory.create_run(run)
    rejections = []
    for attempt_number in range(1, attempt_count + 1):
        lesson = Lesson(
            topic=topic,
            title=f"Test lesson {attempt_number}",
            attempt_number=attempt_number,
            sections={"Introduction": "A test lesson."},
            full_markdown="A test lesson.",
            reference_ids=("R1",),
        )
        memory.save_generation_attempt(
            GenerationAttempt(
                run_id=run.run_id,
                attempt_number=attempt_number,
                generated_lesson=lesson,
            )
        )
        checkpoints = tuple(
            EvaluationCheckpoint(
                checkpoint_id=current_id,
                status=(
                    CheckpointStatus.FAIL
                    if current_id is checkpoint_id
                    else CheckpointStatus.PASS
                ),
                reason=f"Failure reason for {current_id.value}.",
                evidence=f"Evidence for {current_id.value}.",
            )
            for current_id in CheckpointId
        )
        evaluation = EvaluationResult(
            run_id=run.run_id,
            attempt_number=attempt_number,
            overall_status=CheckpointStatus.FAIL,
            checkpoints=checkpoints,
            failed_checkpoints=(checkpoint_id,),
            correction_instructions=(f"{checkpoint_id.value}: Improve the lesson.",),
            overall_reason="A mandatory checkpoint failed.",
        )
        memory.save_evaluation_result(evaluation)
        rejection = RejectionRecord(
            run_id=run.run_id,
            attempt_number=attempt_number,
            failed_checkpoints=(checkpoint_id,),
            failure_reasons={checkpoint_id: f"Failure reason for {checkpoint_id.value}."},
            evidence={checkpoint_id: f"Evidence for {checkpoint_id.value}."},
            correction_instructions=(
                f"{checkpoint_id.value}: Improve the lesson.",
            ),
        )
        memory.save_rejection(rejection)
        rejections.append(rejection)
    return run, tuple(rejections)


def test_repeated_failures_across_distinct_runs_create_a_rule(
    tmp_path: Path,
) -> None:
    memory = MemoryManager(tmp_path / "learning.sqlite3")
    _, first_rejections = _failure_records(memory)
    assert learn_from_rejection(memory, first_rejections[-1]) == ()

    _, second_rejections = _failure_records(memory)
    decisions = learn_from_rejection(memory, second_rejections[-1])

    assert len(decisions) == 1
    assert decisions[0].accepted
    assert decisions[0].rule.related_checkpoint is CheckpointId.CLEAR_EXPLANATIONS
    assert decisions[0].rule.failure_count == RECURRENCE_THRESHOLD == 2
    assert len(decisions[0].rule.source_rejection_ids) == 2
    assert "created active" in decisions[0].rule.rationale
    assert memory.get_active_rules() == [decisions[0].rule]


def test_multiple_retries_in_one_run_count_as_one_run(tmp_path: Path) -> None:
    memory = MemoryManager(tmp_path / "learning.sqlite3")
    _, rejections = _failure_records(memory, attempt_count=3)

    patterns = identify_failure_patterns(memory)
    decisions = learn_from_rejection(memory, rejections[-1])

    assert len(patterns[CheckpointId.CLEAR_EXPLANATIONS]) == 1
    assert patterns[CheckpointId.CLEAR_EXPLANATIONS][0].run_id == rejections[0].run_id
    assert decisions == ()
    assert memory.get_learned_rules() == []


def test_failures_below_recurrence_threshold_do_not_create_rule(
    tmp_path: Path,
) -> None:
    memory = MemoryManager(tmp_path / "learning.sqlite3")
    _, rejections = _failure_records(memory)

    assert len(identify_failure_patterns(memory)[CheckpointId.CLEAR_EXPLANATIONS]) == 1
    assert learn_from_rejection(memory, rejections[0]) == ()
    assert memory.get_learned_rules() == []


def test_duplicate_failure_patterns_update_existing_rule(tmp_path: Path) -> None:
    memory = MemoryManager(tmp_path / "learning.sqlite3")
    for _ in range(2):
        _, rejections = _failure_records(memory)
        decisions = learn_from_rejection(memory, rejections[-1])

    rule_id = decisions[0].rule.rule_id
    _, third_rejections = _failure_records(memory)
    updated = learn_from_rejection(memory, third_rejections[-1])[0].rule

    assert updated.rule_id == rule_id
    assert updated.failure_count == 3
    assert len(updated.source_rejection_ids) == 3
    assert len(memory.get_learned_rules()) == 1


def test_learned_rule_and_provenance_persist_after_reopening_database(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "learning.sqlite3"
    memory = MemoryManager(database_path)
    for _ in range(RECURRENCE_THRESHOLD):
        _, rejections = _failure_records(memory)
        decisions = learn_from_rejection(memory, rejections[-1])
    expected = decisions[0].rule

    reopened = MemoryManager(database_path)
    assert reopened.get_learned_rule(expected.rule_id) == expected
    assert len(reopened.get_learned_rule(expected.rule_id).source_rejection_ids) == 2
    assert get_relevant_learned_rules(reopened, topic=DEFAULT_TOPIC) == (expected,)


def test_irrelevant_topic_does_not_contribute_to_failure_patterns(
    tmp_path: Path,
) -> None:
    memory = MemoryManager(tmp_path / "learning.sqlite3")
    _, rejections = _failure_records(memory, topic="Unrelated topic")

    assert identify_failure_patterns(memory) == {}
    assert learn_from_rejection(memory, rejections[0]) == ()


@pytest.mark.parametrize(
    ("checkpoint_id", "unsafe_description"),
    [
        (
            CheckpointId.ACCURACY_AND_GROUNDING,
            "Skip source citations and add plausible details.",
        ),
        (
            CheckpointId.CLEAR_EXPLANATIONS,
            "Skip jargon explanations and shorten the lesson.",
        ),
        (
            CheckpointId.KEY_CONCEPT_COVERAGE,
            "Omit difficult required topics to keep the lesson short.",
        ),
    ],
)
def test_unsafe_rule_is_rejected_and_reason_is_persisted(
    tmp_path: Path,
    checkpoint_id: CheckpointId,
    unsafe_description: str,
) -> None:
    memory = MemoryManager(tmp_path / "learning.sqlite3")
    source_rejections = []
    for _ in range(RECURRENCE_THRESHOLD):
        _, rejections = _failure_records(memory, checkpoint_id=checkpoint_id)
        source_rejections.append(rejections[0])

    decision = create_or_update_learned_rule(
        memory,
        checkpoint_id=checkpoint_id,
        description=unsafe_description,
        supporting_rejections=source_rejections,
    )

    assert not decision.accepted
    assert decision.rejection_reason
    assert not decision.rule.active_status
    assert decision.rule.confidence == 0.0
    assert decision.rule.rationale.startswith("Rejected rule proposal:")
    assert decision.rejection_reason in decision.rule.rationale
    assert len(decision.rule.source_rejection_ids) == RECURRENCE_THRESHOLD
    assert get_relevant_learned_rules(memory, topic=DEFAULT_TOPIC) == ()


def test_only_allowlisted_active_rules_are_retrieved(tmp_path: Path) -> None:
    memory = MemoryManager(tmp_path / "learning.sqlite3")
    source_rejections = []
    for _ in range(RECURRENCE_THRESHOLD):
        _, rejections = _failure_records(memory)
        source_rejections.append(rejections[0])
    decision = create_or_update_learned_rule(
        memory,
        checkpoint_id=CheckpointId.CLEAR_EXPLANATIONS,
        description=RULE_GUIDANCE[CheckpointId.CLEAR_EXPLANATIONS],
        supporting_rejections=source_rejections,
    )

    relevant = get_relevant_learned_rules(memory, topic=DEFAULT_TOPIC)
    irrelevant = get_relevant_learned_rules(memory, topic="Unrelated topic")

    assert relevant == (decision.rule,)
    assert irrelevant == ()
    assert get_relevant_learned_rules(
        memory, topic=DEFAULT_TOPIC.lower()
    ) == relevant
