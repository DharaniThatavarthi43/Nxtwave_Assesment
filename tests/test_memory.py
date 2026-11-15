import sqlite3
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest

from app.memory.database import connect, initialize_database
from app.memory.memory_manager import MemoryManager
from app.schemas import (
    CheckpointId,
    CheckpointStatus,
    EvaluationCheckpoint,
    EvaluationResult,
    EvaluationErrorCategory,
    EvaluationFailureStage,
    EvaluationRetryDisposition,
    ExecutionRun,
    FailedEvaluationAttempt,
    GenerationAttempt,
    LearnedRule,
    Lesson,
    RejectionRecord,
    RunStatus,
    utc_now,
)


def make_lesson(attempt_number: int = 1) -> Lesson:
    return Lesson(
        topic="Introduction to RAG",
        title=f"RAG lesson attempt {attempt_number}",
        attempt_number=attempt_number,
        sections={"Introduction": "RAG uses retrieved information."},
        full_markdown="# RAG lesson",
        reference_ids=("R1",),
    )


def make_failed_evaluation(run_id, attempt_number: int = 1) -> EvaluationResult:
    failed_checkpoint = CheckpointId.CLEAR_EXPLANATIONS
    checkpoints = tuple(
        EvaluationCheckpoint(
            checkpoint_id=checkpoint_id,
            status=(
                CheckpointStatus.FAIL
                if checkpoint_id is failed_checkpoint
                else CheckpointStatus.PASS
            ),
            reason=(
                "A technical term is not defined."
                if checkpoint_id is failed_checkpoint
                else "Checkpoint result stored for this test."
            ),
            evidence=(
                "The second section uses the term without defining it."
                if checkpoint_id is failed_checkpoint
                else "The lesson introduction contains the evidence."
            ),
        )
        for checkpoint_id in CheckpointId
    )
    return EvaluationResult(
        run_id=run_id,
        attempt_number=attempt_number,
        overall_status=CheckpointStatus.FAIL,
        checkpoints=checkpoints,
        failed_checkpoints=(failed_checkpoint,),
        correction_instructions=("Define the term before its first use.",),
        overall_reason="The clear-explanations checkpoint failed.",
    )


def make_rejection(run_id, attempt_number: int = 1) -> RejectionRecord:
    checkpoint_id = CheckpointId.CLEAR_EXPLANATIONS
    return RejectionRecord(
        run_id=run_id,
        attempt_number=attempt_number,
        failed_checkpoints=(checkpoint_id,),
        failure_reasons={checkpoint_id: "A technical term is not defined."},
        evidence={checkpoint_id: "The second section uses the term without defining it."},
        correction_instructions=("Define the term before its first use.",),
        correction_applied="Regeneration was requested.",
        changes_made="Pending a subsequent generation attempt.",
    )


@pytest.fixture
def manager(tmp_path: Path) -> MemoryManager:
    return MemoryManager(tmp_path / "lesson_memory.sqlite3")


def test_database_initialization_creates_tables_and_foreign_keys(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "nested" / "lesson_memory.sqlite3"
    initialize_database(database_path)

    with connect(database_path) as connection:
        table_names = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        foreign_keys_enabled = connection.execute(
            "PRAGMA foreign_keys"
        ).fetchone()[0]

    assert {
        "execution_runs",
        "generation_attempts",
        "failed_generation_attempts",
        "evaluation_results",
        "failed_evaluation_attempts",
        "rejection_logs",
        "learned_rules",
        "learned_rule_rejections",
    } <= table_names
    assert foreign_keys_enabled == 1


def test_legacy_failed_generation_records_receive_safe_diagnostic_defaults(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "legacy.sqlite3"
    run_id = uuid4()
    failure_id = uuid4()
    timestamp = utc_now().isoformat()
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE execution_runs (
                run_id TEXT PRIMARY KEY NOT NULL,
                topic TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE failed_generation_attempts (
                failure_id TEXT PRIMARY KEY NOT NULL,
                run_id TEXT NOT NULL,
                attempt_number INTEGER NOT NULL,
                status TEXT NOT NULL,
                error_type TEXT NOT NULL,
                error_description TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO execution_runs
                (run_id, topic, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (str(run_id), "Introduction to RAG", "FAILED", timestamp, timestamp),
        )
        connection.execute(
            """
            INSERT INTO failed_generation_attempts (
                failure_id, run_id, attempt_number, status, error_type,
                error_description, timestamp
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(failure_id),
                str(run_id),
                1,
                "FAILED",
                "LessonGenerationError",
                "Lesson generation failed before a validated lesson was produced.",
                timestamp,
            ),
        )

    manager = MemoryManager(database_path)
    [attempt] = manager.get_failed_generation_attempts(run_id)
    migrated_run = manager.get_run(run_id)

    assert attempt.failure_id == failure_id
    assert attempt.failure_stage.value == "unknown"
    assert attempt.error_category.value == "generation_error"
    assert attempt.validation_subcode is None
    assert migrated_run is not None
    assert migrated_run.mode == "assessment"


def test_legacy_failed_evaluation_records_migrate_without_data_loss(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "legacy-evaluation.sqlite3"
    run_id = uuid4()
    failure_id = uuid4()
    timestamp = utc_now().isoformat()
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE failed_evaluation_attempts (
                failure_id TEXT PRIMARY KEY NOT NULL,
                run_id TEXT NOT NULL,
                attempt_number INTEGER NOT NULL,
                status TEXT NOT NULL,
                failure_stage TEXT NOT NULL,
                error_category TEXT NOT NULL,
                error_type TEXT NOT NULL,
                error_description TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO failed_evaluation_attempts (
                failure_id, run_id, attempt_number, status, failure_stage,
                error_category, error_type, error_description, timestamp
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(failure_id),
                str(run_id),
                1,
                "FAILED",
                "api_request",
                "rate_limited",
                "RateLimitError",
                "Evaluator API request was rate-limited.",
                timestamp,
            ),
        )

    manager = MemoryManager(database_path)
    [attempt] = manager.get_failed_evaluation_attempts(run_id)

    assert attempt.failure_id == failure_id
    assert attempt.retry_disposition is None


def test_legacy_rejection_rows_migrate_retry_attempt_from_attempt_history(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "legacy-rejections.sqlite3"
    run_id = uuid4()
    rejection_id = uuid4()
    timestamp = utc_now().isoformat()
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE execution_runs (
                run_id TEXT PRIMARY KEY NOT NULL,
                topic TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE generation_attempts (
                run_id TEXT NOT NULL,
                attempt_number INTEGER NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE rejection_logs (
                rejection_id TEXT PRIMARY KEY NOT NULL,
                run_id TEXT NOT NULL,
                attempt_number INTEGER NOT NULL,
                failed_checkpoints_json TEXT NOT NULL,
                failure_reasons_json TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                correction_instructions_json TEXT NOT NULL,
                correction_applied TEXT NOT NULL,
                changes_made TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO execution_runs
                (run_id, topic, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (str(run_id), "Introduction to RAG", "APPROVED", timestamp, timestamp),
        )
        connection.executemany(
            """
            INSERT INTO generation_attempts (run_id, attempt_number)
            VALUES (?, ?)
            """,
            [(str(run_id), 1), (str(run_id), 2)],
        )
        connection.execute(
            """
            INSERT INTO rejection_logs (
                rejection_id, run_id, attempt_number, failed_checkpoints_json,
                failure_reasons_json, evidence_json, correction_instructions_json,
                correction_applied, changes_made, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(rejection_id),
                str(run_id),
                1,
                '["C4"]',
                '{"C4":"Unexplained term."}',
                '{"C4":"Term used without definition."}',
                '["Define the term."]',
                "Feedback supplied to generation attempt 2.",
                "Changed content in: Introduction.",
                timestamp,
            ),
        )

    manager = MemoryManager(database_path)
    [rejection] = manager.get_rejections(run_id)

    assert rejection.rejection_id == rejection_id
    assert rejection.retry_attempt_number == 2
    assert rejection.failure_reasons[CheckpointId.CLEAR_EXPLANATIONS] == (
        "Unexplained term."
    )


def test_failed_evaluation_retry_disposition_persists(
    tmp_path: Path,
) -> None:
    manager = MemoryManager(tmp_path / "failed-evaluation.sqlite3")
    run = ExecutionRun(topic="Introduction to RAG")
    manager.create_run(run)
    generation_attempt = GenerationAttempt(
        run_id=run.run_id,
        attempt_number=1,
        generated_lesson=make_lesson(),
    )
    manager.save_generation_attempt(generation_attempt)
    failed_evaluation = FailedEvaluationAttempt(
        run_id=run.run_id,
        attempt_number=1,
        failure_stage=EvaluationFailureStage.API_REQUEST,
        error_category=EvaluationErrorCategory.RATE_LIMITED,
        retry_disposition=EvaluationRetryDisposition.RETRY_AFTER_EXCEEDS_CAP,
        error_type="RateLimitError",
        error_description="Retry-After exceeded the configured maximum.",
    )

    manager.save_failed_evaluation_attempt(failed_evaluation)
    [loaded] = manager.get_failed_evaluation_attempts(run.run_id)

    assert loaded == failed_evaluation


def test_memory_manager_crud_and_history_relationships(manager: MemoryManager) -> None:
    run = ExecutionRun(topic="Introduction to RAG")
    manager.create_run(run)
    assert manager.get_run(run.run_id) == run

    updated_run = manager.update_run_status(run.run_id, RunStatus.APPROVED)
    assert updated_run.status is RunStatus.APPROVED
    assert manager.get_run_history()[0].run_id == run.run_id

    attempt = GenerationAttempt(
        run_id=run.run_id,
        attempt_number=1,
        generated_lesson=make_lesson(),
    )
    manager.save_generation_attempt(attempt)
    assert manager.get_generation_attempt(attempt.attempt_id) == attempt
    assert manager.get_attempt_history(run.run_id) == [attempt]

    evaluation = make_failed_evaluation(run.run_id)
    manager.save_evaluation_result(evaluation)
    assert manager.get_evaluation_result(evaluation.evaluation_id) == evaluation

    rejection = make_rejection(run.run_id)
    manager.save_rejection(rejection)
    assert manager.get_rejection(rejection.rejection_id) == rejection
    assert manager.get_rejections(run.run_id) == [rejection]
    assert manager.get_previous_failures(CheckpointId.CLEAR_EXPLANATIONS) == [
        rejection
    ]

    rule = LearnedRule(
        rule_description="Define important terms before using them.",
        rationale="The same terminology issue was rejected more than once.",
        related_checkpoint=CheckpointId.CLEAR_EXPLANATIONS,
        failure_count=2,
        confidence=0.75,
        source_rejection_ids=(rejection.rejection_id,),
    )
    manager.save_learned_rule(rule)
    assert manager.get_learned_rule(rule.rule_id) == rule
    assert manager.get_active_rules(CheckpointId.CLEAR_EXPLANATIONS) == [rule]

    updated_rule = rule.model_copy(
        update={
            "rule_description": "Define each important term before its first use.",
            "active_status": False,
            "updated_at": utc_now(),
        }
    )
    assert manager.update_learned_rule(updated_rule) == updated_rule
    assert manager.get_active_rules() == []

    assert manager.delete_learned_rule(rule.rule_id)
    assert manager.delete_rejection(rejection.rejection_id)
    assert manager.delete_evaluation_result(evaluation.evaluation_id)
    assert manager.delete_generation_attempt(attempt.attempt_id)
    assert manager.delete_run(run.run_id)
    assert manager.get_run(run.run_id) is None


def test_foreign_keys_reject_orphan_attempts(manager: MemoryManager) -> None:
    attempt = GenerationAttempt(
        run_id=uuid4(),
        attempt_number=1,
        generated_lesson=make_lesson(),
    )

    with pytest.raises(sqlite3.IntegrityError):
        manager.save_generation_attempt(attempt)


def test_duplicate_attempts_are_rejected(manager: MemoryManager) -> None:
    run = ExecutionRun(topic="Introduction to RAG")
    manager.create_run(run)
    manager.save_generation_attempt(
        GenerationAttempt(
            run_id=run.run_id,
            attempt_number=1,
            generated_lesson=make_lesson(),
        )
    )

    with pytest.raises(sqlite3.IntegrityError):
        manager.save_generation_attempt(
            GenerationAttempt(
                run_id=run.run_id,
                attempt_number=1,
                generated_lesson=make_lesson(),
            )
        )


def test_run_history_cannot_be_deleted_while_children_exist(
    manager: MemoryManager,
) -> None:
    run = ExecutionRun(topic="Introduction to RAG")
    manager.create_run(run)
    manager.save_generation_attempt(
        GenerationAttempt(
            run_id=run.run_id,
            attempt_number=1,
            generated_lesson=make_lesson(),
        )
    )

    with pytest.raises(sqlite3.IntegrityError):
        manager.delete_run(run.run_id)


def test_run_survives_a_separate_process(tmp_path: Path) -> None:
    database_path = tmp_path / "persistent.sqlite3"
    manager = MemoryManager(database_path)
    run = ExecutionRun(topic="Introduction to RAG")
    manager.create_run(run)

    script = (
        "import sys; "
        "from app.memory.memory_manager import MemoryManager; "
        "from uuid import UUID; "
        "run = MemoryManager(sys.argv[1]).get_run(UUID(sys.argv[2])); "
        "print(run.status.value if run else 'MISSING')"
    )
    result = subprocess.run(
        [sys.executable, "-c", script, str(database_path), str(run.run_id)],
        check=True,
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
    )

    assert result.stdout.strip() == "IN_PROGRESS"


def test_learned_rule_save_rolls_back_if_provenance_is_invalid(
    manager: MemoryManager,
) -> None:
    rule = LearnedRule(
        rule_description="Explain key terms before using them.",
        rationale="Repeated terminology failures.",
        related_checkpoint=CheckpointId.CLEAR_EXPLANATIONS,
        failure_count=2,
        confidence=0.8,
        source_rejection_ids=(uuid4(),),
    )

    with pytest.raises(sqlite3.IntegrityError):
        manager.save_learned_rule(rule)

    assert manager.get_learned_rule(rule.rule_id) is None
