from dataclasses import replace
from pathlib import Path

import pytest

from app.config import DEFAULT_TOPIC, Settings
from app.knowledge.reference_loader import load_reference_material
from app.memory.memory_manager import MemoryManager
from app.schemas import (
    CHECKPOINT_LABELS,
    CheckpointId,
    CheckpointStatus,
    EvaluationCheckpoint,
    EvaluationResult,
    Lesson,
    RunStatus,
)
from app.services import output_service
from app.services.output_service import (
    APPROVED_FILENAMES,
    REJECTED_FILENAMES,
    OutputGenerationError,
    generate_execution_outputs,
)
from app.workflow import run_lesson_workflow


def _settings(tmp_path: Path, *, max_retries: int = 2) -> Settings:
    return Settings(
        app_env="test",
        log_level="INFO",
        database_path=tmp_path / "unused.sqlite3",
        max_retries=max_retries,
        llm_provider="google",
        llm_model="mock-model",
        llm_api_key="not-a-real-api-key",
    )


def _lesson(attempt_number: int) -> Lesson:
    evidence = f"RAG uses retrieved information. Attempt {attempt_number}. [R1]"
    sections = {"Introduction": evidence}
    return Lesson(
        topic=DEFAULT_TOPIC,
        title=f"RAG lesson attempt {attempt_number}",
        attempt_number=attempt_number,
        sections=sections,
        full_markdown=f"# RAG lesson\n\n## Introduction\n\n{evidence}",
        reference_ids=("R1",),
    )


def _run_execution(
    tmp_path: Path,
    outcomes: list[set[CheckpointId]],
    *,
    memory: MemoryManager | None = None,
    max_retries: int = 2,
):
    manager = memory or MemoryManager(tmp_path / "memory.sqlite3")

    def generator(**kwargs) -> Lesson:
        return _lesson(kwargs["attempt_number"])

    def evaluator(**kwargs) -> EvaluationResult:
        lesson = kwargs["lesson"]
        failed = outcomes.pop(0) if outcomes else set()
        checkpoints = tuple(
            EvaluationCheckpoint(
                checkpoint_id=checkpoint_id,
                status=(
                    CheckpointStatus.FAIL
                    if checkpoint_id in failed
                    else CheckpointStatus.PASS
                ),
                reason=(
                    f"Checkpoint {checkpoint_id.value} requires a lesson correction."
                    if checkpoint_id in failed
                    else f"Checkpoint {checkpoint_id.value} is sufficiently supported."
                ),
                evidence=lesson.sections["Introduction"],
            )
            for checkpoint_id in CheckpointId
        )
        return EvaluationResult(
            run_id=kwargs["run_id"],
            attempt_number=lesson.attempt_number,
            overall_status=(
                CheckpointStatus.FAIL if failed else CheckpointStatus.PASS
            ),
            checkpoints=checkpoints,
            failed_checkpoints=tuple(
                checkpoint_id
                for checkpoint_id in CheckpointId
                if checkpoint_id in failed
            ),
            correction_instructions=tuple(
                f"{checkpoint_id.value}: Add the missing lesson explanation."
                for checkpoint_id in CheckpointId
                if checkpoint_id in failed
            ),
            overall_reason=(
                "One or more quality checkpoints failed."
                if failed
                else "All six mandatory checkpoints passed."
            ),
        )

    result = run_lesson_workflow(
        generator_fn=generator,
        evaluator_fn=evaluator,
        memory_manager=manager,
        reference_material=load_reference_material(),
        settings=_settings(tmp_path, max_retries=max_retries),
    )
    return result, manager


def test_approved_execution_writes_exact_outputs_and_all_six_checkpoint_results(
    tmp_path: Path,
) -> None:
    result, memory = _run_execution(tmp_path, [set()])
    artifacts = generate_execution_outputs(
        result,
        memory,
        output_root=tmp_path / "outputs",
    )
    names = {path.name for path in artifacts.files}

    assert names == set(APPROVED_FILENAMES)
    assert (artifacts.directory / "final_lesson.md").is_file()
    assert "APPROVED" in (artifacts.directory / "final_lesson.md").read_text(
        encoding="utf-8"
    )
    summary = (artifacts.directory / "execution_summary.md").read_text(
        encoding="utf-8"
    )
    assert str(result.run.run_id) in summary
    assert result.run.created_at.isoformat() in summary
    assert result.run.updated_at.isoformat() in summary
    assert str(artifacts.directory) in summary
    evaluation_report = (
        artifacts.directory / "evaluation_report.md"
    ).read_text(encoding="utf-8")
    for checkpoint_id in CheckpointId:
        assert (
            f"### {checkpoint_id.value} — "
            f"{CHECKPOINT_LABELS[checkpoint_id]}: PASS"
        ) in evaluation_report
    assert str(result.run.run_id) in evaluation_report
    assert result.run.created_at.isoformat() in evaluation_report
    assert "C1: Add the missing" not in evaluation_report


def test_rejected_execution_writes_rejection_outputs_after_three_generations(
    tmp_path: Path,
) -> None:
    failed_attempts = [
        {CheckpointId.ACCURACY_AND_GROUNDING},
        {
            CheckpointId.CLEAR_EXPLANATIONS,
        },
        {
            CheckpointId.BEGINNER_FRIENDLY_LANGUAGE,
            CheckpointId.TEACHING_THROUGH_EXAMPLES,
            CheckpointId.KEY_CONCEPT_COVERAGE,
            CheckpointId.TEACHING_FLOW,
        },
    ]
    result, memory = _run_execution(tmp_path, failed_attempts)
    artifacts = generate_execution_outputs(
        result,
        memory,
        output_root=tmp_path / "outputs",
    )
    names = {path.name for path in artifacts.files}
    rejected_lesson = (artifacts.directory / "rejected_lesson.md").read_text(
        encoding="utf-8"
    )
    report = (artifacts.directory / "evaluation_report.md").read_text(
        encoding="utf-8"
    )
    attempts = (artifacts.directory / "attempt_history.md").read_text(
        encoding="utf-8"
    )
    rejection_log = (artifacts.directory / "rejection_log.md").read_text(
        encoding="utf-8"
    )

    assert not result.approved
    assert len(result.attempt_history) == 3
    assert names == set(REJECTED_FILENAMES)
    assert "REJECTED" in rejected_lesson
    assert "NOT APPROVED" in rejected_lesson
    assert "final_lesson.md" not in names
    expected_failures = {
        1: {CheckpointId.ACCURACY_AND_GROUNDING},
        2: {CheckpointId.CLEAR_EXPLANATIONS},
        3: {
            CheckpointId.BEGINNER_FRIENDLY_LANGUAGE,
            CheckpointId.TEACHING_THROUGH_EXAMPLES,
            CheckpointId.KEY_CONCEPT_COVERAGE,
            CheckpointId.TEACHING_FLOW,
        },
    }
    for attempt_number, failed in expected_failures.items():
        for checkpoint_id in CheckpointId:
            expected_status = (
                "FAIL" if checkpoint_id in failed else "PASS"
            )
            assert (
                f"### {checkpoint_id.value} — "
                f"{CHECKPOINT_LABELS[checkpoint_id]}: {expected_status}"
            ) in report
    assert "Attempt 1: FAIL" in report
    assert "Attempt 2: FAIL" in report
    assert "Attempt 3: FAIL" in report
    assert "Generation attempt 1" in attempts
    assert "Generation attempt 2" in attempts
    assert "Generation attempt 3" in attempts
    assert "Corrections requested:" in attempts
    assert "Changes made:" in attempts
    assert "Failed checkpoints: C2, C3, C5, C6" in attempts
    assert "Candidate generation attempt: 2" in rejected_lesson
    assert "Attempt 2." in rejected_lesson
    assert "Final execution REJECTED" in rejection_log
    assert "The final lesson is rejected and is not an approved lesson." in rejection_log
    assert "C1: Add the missing lesson explanation." in rejection_log
    assert "No further regeneration was performed" in rejection_log


def test_each_output_run_gets_a_unique_directory_without_overwriting(
    tmp_path: Path,
) -> None:
    result, memory = _run_execution(tmp_path, [set()])
    root = tmp_path / "outputs"

    first = generate_execution_outputs(result, memory, output_root=root)
    first_lesson = (first.directory / "final_lesson.md").read_text(encoding="utf-8")
    second = generate_execution_outputs(result, memory, output_root=root)

    assert first.directory != second.directory
    assert first.directory.parent == second.directory.parent == root
    assert str(result.run.run_id) in first.directory.name
    assert DEFAULT_TOPIC not in first.directory.name
    assert (first.directory / "final_lesson.md").read_text(
        encoding="utf-8"
    ) == first_lesson
    assert (second.directory / "final_lesson.md").is_file()


def test_learned_rules_report_includes_applied_rule_provenance(
    tmp_path: Path,
) -> None:
    memory = MemoryManager(tmp_path / "memory.sqlite3")
    for _ in range(2):
        _run_execution(
            tmp_path,
            [{CheckpointId.CLEAR_EXPLANATIONS}],
            memory=memory,
            max_retries=0,
        )
    result, memory = _run_execution(
        tmp_path,
        [set()],
        memory=memory,
        max_retries=0,
    )

    artifacts = generate_execution_outputs(
        result,
        memory,
        output_root=tmp_path / "outputs",
    )
    rules_report = (artifacts.directory / "learned_rules.md").read_text(
        encoding="utf-8"
    )

    assert result.applied_rules
    assert result.applied_rules[0].rule_description in rules_report
    assert "Applied at run start" in rules_report
    assert "ACTIVE" in rules_report
    assert "Distinct supporting runs: 2" in rules_report
    assert str(result.applied_rules[0].rule_id) in rules_report


def test_learned_rules_report_includes_rule_created_by_current_rejection(
    tmp_path: Path,
) -> None:
    memory = MemoryManager(tmp_path / "memory.sqlite3")
    _run_execution(
        tmp_path,
        [{CheckpointId.CLEAR_EXPLANATIONS}],
        memory=memory,
        max_retries=0,
    )
    result, memory = _run_execution(
        tmp_path,
        [{CheckpointId.CLEAR_EXPLANATIONS}],
        memory=memory,
        max_retries=0,
    )

    artifacts = generate_execution_outputs(
        result,
        memory,
        output_root=tmp_path / "outputs",
    )
    rules_report = (artifacts.directory / "learned_rules.md").read_text(
        encoding="utf-8"
    )

    assert result.run.status is RunStatus.REJECTED
    assert result.applied_rules == ()
    assert "Learned from this run" in rules_report
    assert "Checkpoint C4 failed in 2 distinct Introduction to RAG runs." in rules_report
    assert "ACTIVE" in rules_report


def test_failed_evaluation_cannot_be_written_as_approved(
    tmp_path: Path,
) -> None:
    result, memory = _run_execution(
        tmp_path,
        [{CheckpointId.ACCURACY_AND_GROUNDING}],
        max_retries=0,
    )
    approved_run = memory.update_run_status(result.run.run_id, RunStatus.APPROVED)
    corrupted_result = replace(result, run=approved_run)
    output_root = tmp_path / "outputs"

    with pytest.raises(OutputGenerationError, match="requires PASS on all six"):
        generate_execution_outputs(
            corrupted_result,
            memory,
            output_root=output_root,
        )

    assert not output_root.exists()


def test_output_write_failure_does_not_change_decision_or_leave_partial_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result, memory = _run_execution(tmp_path, [set()])
    output_root = tmp_path / "outputs"

    def fail_write(path: Path, content: str) -> None:
        raise OSError("simulated disk failure")

    monkeypatch.setattr(output_service, "_write_file", fail_write)

    with pytest.raises(OutputGenerationError, match="Unable to write execution outputs"):
        generate_execution_outputs(result, memory, output_root=output_root)

    assert memory.get_run(result.run.run_id).status is RunStatus.APPROVED
    assert result.approved
    assert list(output_root.iterdir()) == []


def test_incomplete_execution_does_not_create_output_directory(
    tmp_path: Path,
) -> None:
    result, memory = _run_execution(tmp_path, [set()])
    assert memory.delete_evaluation_result(result.final_evaluation.evaluation_id)
    output_root = tmp_path / "outputs"

    with pytest.raises(OutputGenerationError, match="persisted evaluation history"):
        generate_execution_outputs(
            result,
            memory,
            output_root=output_root,
        )

    assert not output_root.exists()


@pytest.mark.parametrize("status", [RunStatus.FAILED, RunStatus.IN_PROGRESS])
def test_nonterminal_execution_does_not_create_output_reports(
    tmp_path: Path,
    status: RunStatus,
) -> None:
    result, memory = _run_execution(tmp_path, [set()])
    updated_run = memory.update_run_status(result.run.run_id, status)
    nonterminal_result = replace(result, run=updated_run)
    output_root = tmp_path / "outputs"

    with pytest.raises(OutputGenerationError, match="only available for completed"):
        generate_execution_outputs(
            nonterminal_result,
            memory,
            output_root=output_root,
        )

    assert not output_root.exists()
