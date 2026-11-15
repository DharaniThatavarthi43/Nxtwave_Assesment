import json
import sqlite3
from pathlib import Path
from typing import Any
from uuid import UUID

from app.config import load_settings
from app.memory.database import connect, initialize_database
from app.schemas import (
    CheckpointId,
    EvaluationCheckpoint,
    FailedEvaluationAttempt,
    EvaluationResult,
    ApprovedLessonNote,
    ExecutionRun,
    FailedGenerationAttempt,
    GenerationAttempt,
    LearnedRule,
    Lesson,
    RejectionRecord,
    RunStatus,
    utc_now,
)


class RecordNotFoundError(LookupError):
    """Raised when an update targets a record that does not exist."""


DELETE_TARGETS = {
    ("execution_runs", "run_id"),
    ("generation_attempts", "attempt_id"),
    ("evaluation_results", "evaluation_id"),
    ("rejection_logs", "rejection_id"),
}


class MemoryManager:
    def __init__(self, database_path: Path | str | None = None) -> None:
        self.database_path = (
            Path(database_path)
            if database_path is not None
            else load_settings().database_path
        )
        initialize_database(self.database_path)

    def create_run(self, run: ExecutionRun) -> ExecutionRun:
        with connect(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO execution_runs (
                    run_id, topic, mode, max_retries, status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(run.run_id),
                    run.topic,
                    run.mode,
                    run.max_retries,
                    run.status.value,
                    run.created_at.isoformat(),
                    run.updated_at.isoformat(),
                ),
            )
        return run

    def get_run(self, run_id: UUID) -> ExecutionRun | None:
        with connect(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT run_id, topic, mode, max_retries, status, created_at, updated_at
                FROM execution_runs
                WHERE run_id = ?
                """,
                (str(run_id),),
            ).fetchone()
        return ExecutionRun.model_validate(dict(row)) if row else None

    def get_run_history(self, limit: int = 100) -> list[ExecutionRun]:
        if limit < 1:
            raise ValueError("Run history limit must be at least one.")
        with connect(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT run_id, topic, mode, max_retries, status, created_at, updated_at
                FROM execution_runs
                ORDER BY created_at DESC, run_id
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [ExecutionRun.model_validate(dict(row)) for row in rows]

    def get_approved_notes(self) -> list[ApprovedLessonNote]:
        with connect(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT r.run_id, r.topic, r.mode, r.updated_at, g.generated_lesson_json,
                       e.overall_status, e.checkpoints_json
                FROM execution_runs AS r
                JOIN generation_attempts AS g
                  ON g.run_id = r.run_id
                 AND g.attempt_number = (
                     SELECT MAX(latest.attempt_number)
                     FROM generation_attempts AS latest
                     WHERE latest.run_id = r.run_id
                 )
                JOIN evaluation_results AS e
                  ON e.run_id = g.run_id
                 AND e.attempt_number = g.attempt_number
                WHERE r.status = 'APPROVED'
                  AND e.overall_status = 'PASS'
                ORDER BY r.updated_at DESC, r.run_id
                """
            ).fetchall()
        return [
            note
            for row in rows
            if (note := self._approved_note_from_row(row)) is not None
        ]

    def get_approved_note(self, run_id: UUID) -> ApprovedLessonNote | None:
        with connect(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT r.run_id, r.topic, r.mode, r.updated_at, g.generated_lesson_json,
                       e.overall_status, e.checkpoints_json
                FROM execution_runs AS r
                JOIN generation_attempts AS g
                  ON g.run_id = r.run_id
                 AND g.attempt_number = (
                     SELECT MAX(latest.attempt_number)
                     FROM generation_attempts AS latest
                     WHERE latest.run_id = r.run_id
                 )
                JOIN evaluation_results AS e
                  ON e.run_id = g.run_id
                 AND e.attempt_number = g.attempt_number
                WHERE r.run_id = ?
                  AND r.status = 'APPROVED'
                  AND e.overall_status = 'PASS'
                """,
                (str(run_id),),
            ).fetchone()
        return self._approved_note_from_row(row) if row is not None else None

    @staticmethod
    def _approved_note_from_row(row: sqlite3.Row) -> ApprovedLessonNote | None:
        if row["overall_status"] != "PASS":
            return None
        try:
            checkpoints = json.loads(row["checkpoints_json"])
            checkpoint_statuses = {
                item["checkpoint_id"]: item["status"]
                for item in checkpoints
                if isinstance(item, dict)
            }
            if (
                len(checkpoint_statuses) != len(CheckpointId)
                or set(checkpoint_statuses) != {item.value for item in CheckpointId}
                or any(status != "PASS" for status in checkpoint_statuses.values())
            ):
                return None
            lesson_data = json.loads(row["generated_lesson_json"])
            lesson = Lesson.model_validate(lesson_data)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None
        return ApprovedLessonNote(
            run_id=UUID(row["run_id"]),
            topic=row["topic"],
            mode=row["mode"],
            title=lesson.title,
            created_at=lesson.generation_timestamp,
            full_markdown=lesson.full_markdown,
        )

    def update_run_status(self, run_id: UUID, status: RunStatus) -> ExecutionRun:
        run_status = RunStatus(status)
        with connect(self.database_path) as connection:
            cursor = connection.execute(
                """
                UPDATE execution_runs
                SET status = ?, updated_at = ?
                WHERE run_id = ?
                """,
                (run_status.value, utc_now().isoformat(), str(run_id)),
            )
            if cursor.rowcount == 0:
                raise RecordNotFoundError(f"Run {run_id} does not exist.")
        updated_run = self.get_run(run_id)
        if updated_run is None:
            raise RecordNotFoundError(f"Run {run_id} disappeared after update.")
        return updated_run

    def delete_run(self, run_id: UUID) -> bool:
        return self._delete("execution_runs", "run_id", run_id)

    def save_generation_attempt(self, attempt: GenerationAttempt) -> GenerationAttempt:
        with connect(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO generation_attempts (
                    attempt_id, run_id, attempt_number, generated_lesson_json, timestamp
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(attempt.attempt_id),
                    str(attempt.run_id),
                    attempt.attempt_number,
                    attempt.generated_lesson.model_dump_json(),
                    attempt.timestamp.isoformat(),
                ),
            )
        return attempt

    def get_generation_attempt(self, attempt_id: UUID) -> GenerationAttempt | None:
        with connect(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT attempt_id, run_id, attempt_number, generated_lesson_json, timestamp
                FROM generation_attempts
                WHERE attempt_id = ?
                """,
                (str(attempt_id),),
            ).fetchone()
        if row is None:
            return None
        return GenerationAttempt(
            attempt_id=row["attempt_id"],
            run_id=row["run_id"],
            attempt_number=row["attempt_number"],
            generated_lesson=Lesson.model_validate_json(row["generated_lesson_json"]),
            timestamp=row["timestamp"],
        )

    def get_attempt_history(self, run_id: UUID) -> list[GenerationAttempt]:
        with connect(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT attempt_id, run_id, attempt_number, generated_lesson_json, timestamp
                FROM generation_attempts
                WHERE run_id = ?
                ORDER BY attempt_number
                """,
                (str(run_id),),
            ).fetchall()
        return [
            GenerationAttempt(
                attempt_id=row["attempt_id"],
                run_id=row["run_id"],
                attempt_number=row["attempt_number"],
                generated_lesson=Lesson.model_validate_json(
                    row["generated_lesson_json"]
                ),
                timestamp=row["timestamp"],
            )
            for row in rows
        ]

    def delete_generation_attempt(self, attempt_id: UUID) -> bool:
        return self._delete("generation_attempts", "attempt_id", attempt_id)

    def save_failed_generation_attempt(
        self, attempt: FailedGenerationAttempt
    ) -> FailedGenerationAttempt:
        with connect(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO failed_generation_attempts (
                    failure_id, run_id, attempt_number, status, failure_stage,
                    error_category, validation_subcode, error_type,
                    error_description, timestamp
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(attempt.failure_id),
                    str(attempt.run_id),
                    attempt.attempt_number,
                    attempt.status,
                    attempt.failure_stage.value,
                    attempt.error_category.value,
                    (
                        attempt.validation_subcode.value
                        if attempt.validation_subcode is not None
                        else None
                    ),
                    attempt.error_type,
                    attempt.error_description,
                    attempt.timestamp.isoformat(),
                ),
            )
        return attempt

    def get_failed_generation_attempts(
        self, run_id: UUID | None = None
    ) -> list[FailedGenerationAttempt]:
        query = """
            SELECT failure_id, run_id, attempt_number, status, failure_stage,
                   error_category, validation_subcode, error_type,
                   error_description, timestamp
            FROM failed_generation_attempts
        """
        parameters: tuple[str, ...] = ()
        if run_id is not None:
            query += " WHERE run_id = ?"
            parameters = (str(run_id),)
        query += " ORDER BY timestamp, failure_id"
        with connect(self.database_path) as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [
            FailedGenerationAttempt.model_validate(dict(row))
            for row in rows
        ]

    def save_evaluation_result(self, result: EvaluationResult) -> EvaluationResult:
        checkpoint_payload = [
            checkpoint.model_dump(mode="json") for checkpoint in result.checkpoints
        ]
        with connect(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO evaluation_results (
                    evaluation_id, run_id, attempt_number, overall_status,
                    checkpoints_json, failed_checkpoints_json,
                    correction_instructions_json, overall_reason, evaluated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(result.evaluation_id),
                    str(result.run_id),
                    result.attempt_number,
                    result.overall_status.value,
                    json.dumps(checkpoint_payload),
                    json.dumps(
                        [checkpoint.value for checkpoint in result.failed_checkpoints]
                    ),
                    json.dumps(list(result.correction_instructions)),
                    result.overall_reason,
                    result.evaluated_at.isoformat(),
                ),
            )
        return result

    def save_failed_evaluation_attempt(
        self, attempt: FailedEvaluationAttempt
    ) -> FailedEvaluationAttempt:
        with connect(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO failed_evaluation_attempts (
                    failure_id, run_id, attempt_number, status, failure_stage,
                    error_category, retry_disposition, error_type,
                    error_description, timestamp
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(attempt.failure_id),
                    str(attempt.run_id),
                    attempt.attempt_number,
                    attempt.status,
                    attempt.failure_stage.value,
                    attempt.error_category.value,
                    (
                        attempt.retry_disposition.value
                        if attempt.retry_disposition is not None
                        else None
                    ),
                    attempt.error_type,
                    attempt.error_description,
                    attempt.timestamp.isoformat(),
                ),
            )
        return attempt

    def get_failed_evaluation_attempts(
        self, run_id: UUID | None = None
    ) -> list[FailedEvaluationAttempt]:
        query = """
            SELECT failure_id, run_id, attempt_number, status, failure_stage,
                   error_category, retry_disposition, error_type,
                   error_description, timestamp
            FROM failed_evaluation_attempts
        """
        parameters: tuple[str, ...] = ()
        if run_id is not None:
            query += " WHERE run_id = ?"
            parameters = (str(run_id),)
        query += " ORDER BY timestamp, failure_id"
        with connect(self.database_path) as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [
            FailedEvaluationAttempt.model_validate(dict(row))
            for row in rows
        ]

    def get_evaluation_result(self, evaluation_id: UUID) -> EvaluationResult | None:
        with connect(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT evaluation_id, run_id, attempt_number, overall_status,
                       checkpoints_json, failed_checkpoints_json,
                       correction_instructions_json, overall_reason, evaluated_at
                FROM evaluation_results
                WHERE evaluation_id = ?
                """,
                (str(evaluation_id),),
            ).fetchone()
        if row is None:
            return None
        return self._evaluation_from_row(row)

    def get_evaluation_history(
        self, run_id: UUID | None = None
    ) -> list[EvaluationResult]:
        query = """
            SELECT evaluation_id, run_id, attempt_number, overall_status,
                   checkpoints_json, failed_checkpoints_json,
                   correction_instructions_json, overall_reason, evaluated_at
            FROM evaluation_results
        """
        parameters: tuple[str, ...] = ()
        if run_id is not None:
            query += " WHERE run_id = ?"
            parameters = (str(run_id),)
        query += " ORDER BY evaluated_at, evaluation_id"
        with connect(self.database_path) as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [self._evaluation_from_row(row) for row in rows]

    def delete_evaluation_result(self, evaluation_id: UUID) -> bool:
        return self._delete("evaluation_results", "evaluation_id", evaluation_id)

    def save_rejection(self, record: RejectionRecord) -> RejectionRecord:
        with connect(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO rejection_logs (
                    rejection_id, run_id, attempt_number, failed_checkpoints_json,
                    failure_reasons_json, evidence_json, correction_instructions_json,
                    correction_applied, changes_made, created_at, retry_attempt_number
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(record.rejection_id),
                    str(record.run_id),
                    record.attempt_number,
                    json.dumps(
                        [checkpoint.value for checkpoint in record.failed_checkpoints]
                    ),
                    json.dumps(
                        {
                            checkpoint.value: reason
                            for checkpoint, reason in record.failure_reasons.items()
                        }
                    ),
                    json.dumps(
                        {
                            checkpoint.value: evidence
                            for checkpoint, evidence in record.evidence.items()
                        }
                    ),
                    json.dumps(list(record.correction_instructions)),
                    record.correction_applied,
                    record.changes_made,
                    record.created_at.isoformat(),
                    record.retry_attempt_number,
                ),
            )
        return record

    def update_rejection_progress(
        self,
        rejection_id: UUID,
        retry_attempt_number: int | None,
        correction_applied: str,
        changes_made: str,
    ) -> RejectionRecord:
        with connect(self.database_path) as connection:
            cursor = connection.execute(
                """
                UPDATE rejection_logs
                SET retry_attempt_number = ?, correction_applied = ?, changes_made = ?
                WHERE rejection_id = ?
                """,
                (
                    retry_attempt_number,
                    correction_applied,
                    changes_made,
                    str(rejection_id),
                ),
            )
            if cursor.rowcount == 0:
                raise RecordNotFoundError(
                    f"Rejection {rejection_id} does not exist."
                )
        updated_record = self.get_rejection(rejection_id)
        if updated_record is None:
            raise RecordNotFoundError(
                f"Rejection {rejection_id} disappeared after update."
            )
        return updated_record

    def get_rejection(self, rejection_id: UUID) -> RejectionRecord | None:
        with connect(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT rejection_id, run_id, attempt_number, failed_checkpoints_json,
                       failure_reasons_json, evidence_json, correction_instructions_json,
                       correction_applied, changes_made, created_at,
                       retry_attempt_number
                FROM rejection_logs
                WHERE rejection_id = ?
                """,
                (str(rejection_id),),
            ).fetchone()
        return self._rejection_from_row(row) if row else None

    def get_rejections(self, run_id: UUID) -> list[RejectionRecord]:
        with connect(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT rejection_id, run_id, attempt_number, failed_checkpoints_json,
                       failure_reasons_json, evidence_json, correction_instructions_json,
                       correction_applied, changes_made, created_at,
                       retry_attempt_number
                FROM rejection_logs
                WHERE run_id = ?
                ORDER BY attempt_number
                """,
                (str(run_id),),
            ).fetchall()
        return [self._rejection_from_row(row) for row in rows]

    def get_previous_failures(
        self, checkpoint_id: CheckpointId | None = None
    ) -> list[RejectionRecord]:
        with connect(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT rejection_id, run_id, attempt_number, failed_checkpoints_json,
                       failure_reasons_json, evidence_json, correction_instructions_json,
                       correction_applied, changes_made, created_at,
                       retry_attempt_number
                FROM rejection_logs
                ORDER BY created_at DESC, rejection_id
                """
            ).fetchall()
        records = [self._rejection_from_row(row) for row in rows]
        if checkpoint_id is None:
            return records
        target = CheckpointId(checkpoint_id)
        return [record for record in records if target in record.failed_checkpoints]

    def delete_rejection(self, rejection_id: UUID) -> bool:
        return self._delete("rejection_logs", "rejection_id", rejection_id)

    def save_learned_rule(self, rule: LearnedRule) -> LearnedRule:
        with connect(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO learned_rules (
                    rule_id, rule_description, rationale, related_checkpoint,
                    failure_count, confidence, active_status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(rule.rule_id),
                    rule.rule_description,
                    rule.rationale,
                    rule.related_checkpoint.value,
                    rule.failure_count,
                    rule.confidence,
                    int(rule.active_status),
                    rule.created_at.isoformat(),
                    rule.updated_at.isoformat(),
                ),
            )
            connection.executemany(
                """
                INSERT INTO learned_rule_rejections (rule_id, rejection_id)
                VALUES (?, ?)
                """,
                [
                    (str(rule.rule_id), str(rejection_id))
                    for rejection_id in rule.source_rejection_ids
                ],
            )
        return rule

    def get_learned_rule(self, rule_id: UUID) -> LearnedRule | None:
        with connect(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT rule_id, rule_description, rationale, related_checkpoint,
                       failure_count, confidence, active_status, created_at, updated_at
                FROM learned_rules
                WHERE rule_id = ?
                """,
                (str(rule_id),),
            ).fetchone()
            if row is None:
                return None
            source_rows = connection.execute(
                """
                SELECT rejection_id
                FROM learned_rule_rejections
                WHERE rule_id = ?
                ORDER BY rejection_id
                """,
                (str(rule_id),),
            ).fetchall()
        return self._learned_rule_from_rows(row, source_rows)

    def get_learned_rules(
        self, checkpoint_id: CheckpointId | None = None
    ) -> list[LearnedRule]:
        query = """
            SELECT rule_id, rule_description, rationale, related_checkpoint,
                   failure_count, confidence, active_status, created_at, updated_at
            FROM learned_rules
        """
        parameters: tuple[Any, ...] = ()
        if checkpoint_id is not None:
            query += " WHERE related_checkpoint = ?"
            parameters = (CheckpointId(checkpoint_id).value,)
        query += " ORDER BY created_at, rule_id"

        with connect(self.database_path) as connection:
            rows = connection.execute(query, parameters).fetchall()
            source_rows_by_rule = {
                row["rule_id"]: connection.execute(
                    """
                    SELECT rejection_id
                    FROM learned_rule_rejections
                    WHERE rule_id = ?
                    ORDER BY rejection_id
                    """,
                    (row["rule_id"],),
                ).fetchall()
                for row in rows
            }
        return [
            self._learned_rule_from_rows(row, source_rows_by_rule[row["rule_id"]])
            for row in rows
        ]

    def get_active_rules(
        self, checkpoint_id: CheckpointId | None = None
    ) -> list[LearnedRule]:
        return [
            rule
            for rule in self.get_learned_rules(checkpoint_id)
            if rule.active_status
        ]

    def update_learned_rule(self, rule: LearnedRule) -> LearnedRule:
        with connect(self.database_path) as connection:
            cursor = connection.execute(
                """
                UPDATE learned_rules
                SET rule_description = ?, rationale = ?, related_checkpoint = ?,
                    failure_count = ?, confidence = ?, active_status = ?, updated_at = ?
                WHERE rule_id = ?
                """,
                (
                    rule.rule_description,
                    rule.rationale,
                    rule.related_checkpoint.value,
                    rule.failure_count,
                    rule.confidence,
                    int(rule.active_status),
                    rule.updated_at.isoformat(),
                    str(rule.rule_id),
                ),
            )
            if cursor.rowcount == 0:
                raise RecordNotFoundError(f"Learned rule {rule.rule_id} does not exist.")
            connection.execute(
                "DELETE FROM learned_rule_rejections WHERE rule_id = ?",
                (str(rule.rule_id),),
            )
            connection.executemany(
                """
                INSERT INTO learned_rule_rejections (rule_id, rejection_id)
                VALUES (?, ?)
                """,
                [
                    (str(rule.rule_id), str(rejection_id))
                    for rejection_id in rule.source_rejection_ids
                ],
            )
        updated_rule = self.get_learned_rule(rule.rule_id)
        if updated_rule is None:
            raise RecordNotFoundError(
                f"Learned rule {rule.rule_id} disappeared after update."
            )
        return updated_rule

    def delete_learned_rule(self, rule_id: UUID) -> bool:
        with connect(self.database_path) as connection:
            connection.execute(
                "DELETE FROM learned_rule_rejections WHERE rule_id = ?",
                (str(rule_id),),
            )
            cursor = connection.execute(
                "DELETE FROM learned_rules WHERE rule_id = ?",
                (str(rule_id),),
            )
        return cursor.rowcount > 0

    def _delete(self, table: str, column: str, record_id: UUID) -> bool:
        if (table, column) not in DELETE_TARGETS:
            raise ValueError("Unsupported database deletion target.")
        with connect(self.database_path) as connection:
            cursor = connection.execute(
                f"DELETE FROM {table} WHERE {column} = ?",
                (str(record_id),),
            )
        return cursor.rowcount > 0

    @staticmethod
    def _evaluation_from_row(row: sqlite3.Row) -> EvaluationResult:
        return EvaluationResult(
            evaluation_id=row["evaluation_id"],
            run_id=row["run_id"],
            attempt_number=row["attempt_number"],
            overall_status=row["overall_status"],
            checkpoints=tuple(
                EvaluationCheckpoint.model_validate(checkpoint)
                for checkpoint in json.loads(row["checkpoints_json"])
            ),
            failed_checkpoints=tuple(json.loads(row["failed_checkpoints_json"])),
            correction_instructions=tuple(
                json.loads(row["correction_instructions_json"])
            ),
            overall_reason=row["overall_reason"],
            evaluated_at=row["evaluated_at"],
        )

    @staticmethod
    def _rejection_from_row(row: sqlite3.Row) -> RejectionRecord:
        return RejectionRecord(
            rejection_id=row["rejection_id"],
            run_id=row["run_id"],
            attempt_number=row["attempt_number"],
            retry_attempt_number=row["retry_attempt_number"],
            failed_checkpoints=tuple(json.loads(row["failed_checkpoints_json"])),
            failure_reasons={
                CheckpointId(checkpoint): reason
                for checkpoint, reason in json.loads(
                    row["failure_reasons_json"]
                ).items()
            },
            evidence={
                CheckpointId(checkpoint): evidence
                for checkpoint, evidence in json.loads(row["evidence_json"]).items()
            },
            correction_instructions=tuple(
                json.loads(row["correction_instructions_json"])
            ),
            correction_applied=row["correction_applied"],
            changes_made=row["changes_made"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _learned_rule_from_rows(
        row: sqlite3.Row, source_rows: list[sqlite3.Row]
    ) -> LearnedRule:
        return LearnedRule(
            rule_id=row["rule_id"],
            rule_description=row["rule_description"],
            rationale=row["rationale"],
            related_checkpoint=row["related_checkpoint"],
            failure_count=row["failure_count"],
            confidence=row["confidence"],
            source_rejection_ids=tuple(
                source_row["rejection_id"] for source_row in source_rows
            ),
            active_status=bool(row["active_status"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
