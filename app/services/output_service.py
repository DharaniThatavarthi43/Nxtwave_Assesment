import sqlite3
import tempfile
from dataclasses import dataclass
from datetime import timezone
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from app.config import PROJECT_ROOT
from app.memory.memory_manager import MemoryManager
from app.schemas import (
    CHECKPOINT_LABELS,
    CheckpointId,
    CheckpointStatus,
    EvaluationResult,
    ExecutionRun,
    GenerationAttempt,
    LearnedRule,
    RejectionRecord,
    RunStatus,
)
from app.workflow import WorkflowResult


APPROVED_FILENAMES = (
    "final_lesson.md",
    "evaluation_report.md",
    "execution_summary.md",
    "attempt_history.md",
    "learned_rules.md",
)
REJECTED_FILENAMES = (
    "rejected_lesson.md",
    "evaluation_report.md",
    "execution_summary.md",
    "attempt_history.md",
    "rejection_log.md",
    "learned_rules.md",
)


class OutputGenerationError(RuntimeError):
    """Raised when a complete, safe execution output cannot be created."""


@dataclass(frozen=True)
class OutputArtifacts:
    directory: Path
    files: tuple[Path, ...]


@dataclass(frozen=True)
class _PersistedExecution:
    run: ExecutionRun
    attempts: tuple[GenerationAttempt, ...]
    evaluations: tuple[EvaluationResult, ...]
    rejections: tuple[RejectionRecord, ...]
    rules: tuple[LearnedRule, ...]
    applied_rules: tuple[LearnedRule, ...]


def generate_execution_outputs(
    result: WorkflowResult,
    memory_manager: MemoryManager,
    *,
    output_root: Path | str | None = None,
) -> OutputArtifacts:
    execution = _load_persisted_execution(result, memory_manager)
    root = Path(output_root) if output_root is not None else PROJECT_ROOT / "outputs"
    root = root.expanduser().resolve()
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise OutputGenerationError(
            f"Unable to create the output directory ({type(exc).__name__})."
        ) from exc

    directory_name = _output_directory_name(execution.run)
    final_directory = root / directory_name
    try:
        with tempfile.TemporaryDirectory(prefix=".staging-", dir=root) as temporary:
            staging_directory = Path(temporary)
            rendered_files = _render_execution(execution, final_directory)
            for filename, content in rendered_files.items():
                _write_file(staging_directory / filename, content)
            staging_directory.rename(final_directory)
    except FileExistsError as exc:
        raise OutputGenerationError(
            "The unique output directory already exists; no files were overwritten."
        ) from exc
    except OSError as exc:
        raise OutputGenerationError(
            f"Unable to write execution outputs ({type(exc).__name__})."
        ) from exc

    return OutputArtifacts(
        directory=final_directory,
        files=tuple(final_directory / filename for filename in rendered_files),
    )


def _load_persisted_execution(
    result: WorkflowResult,
    memory_manager: MemoryManager,
) -> _PersistedExecution:
    try:
        run = memory_manager.get_run(result.run.run_id)
        if run is None:
            raise OutputGenerationError("The persisted execution run is missing.")
        attempts = tuple(memory_manager.get_attempt_history(run.run_id))
        evaluations = tuple(memory_manager.get_evaluation_history(run.run_id))
        rejections = tuple(memory_manager.get_rejections(run.run_id))
        rules = tuple(memory_manager.get_learned_rules())
    except (OSError, sqlite3.Error, ValidationError) as exc:
        raise OutputGenerationError(
            f"Unable to load persisted execution data ({type(exc).__name__})."
        ) from exc

    if run.status not in {RunStatus.APPROVED, RunStatus.REJECTED}:
        raise OutputGenerationError(
            "Outputs are only available for completed APPROVED or REJECTED runs."
        )
    if run.status is not result.run.status:
        raise OutputGenerationError(
            "The persisted run status does not match the workflow result."
        )
    if not attempts or len(attempts) > 3:
        raise OutputGenerationError("The persisted attempt history is incomplete.")

    attempt_numbers = tuple(attempt.attempt_number for attempt in attempts)
    if attempt_numbers != tuple(range(1, len(attempts) + 1)):
        raise OutputGenerationError("The persisted attempt numbers are inconsistent.")
    evaluations_by_attempt = {
        evaluation.attempt_number: evaluation for evaluation in evaluations
    }
    if set(evaluations_by_attempt) != set(attempt_numbers):
        raise OutputGenerationError("The persisted evaluation history is incomplete.")
    if any(
        evaluation.overall_status is CheckpointStatus.PASS
        for evaluation in evaluations
        if evaluation.attempt_number != attempts[-1].attempt_number
    ):
        raise OutputGenerationError(
            "The workflow continued after a passing evaluation."
        )
    if attempts[-1].generated_lesson != result.final_lesson:
        raise OutputGenerationError(
            "The final lesson does not match the persisted final attempt."
        )
    final_evaluation = evaluations_by_attempt[attempts[-1].attempt_number]
    if final_evaluation != result.final_evaluation:
        raise OutputGenerationError(
            "The final evaluation does not match persisted evaluation history."
        )
    if run.status is RunStatus.APPROVED:
        if not _all_checkpoints_pass(final_evaluation):
            raise OutputGenerationError(
                "An approved output requires PASS on all six checkpoints."
            )
    elif (
        final_evaluation.overall_status is not CheckpointStatus.FAIL
        or not final_evaluation.failed_checkpoints
    ):
        raise OutputGenerationError(
            "A rejected output requires at least one failed checkpoint."
        )

    rejections_by_attempt = {rejection.attempt_number: rejection for rejection in rejections}
    for evaluation in evaluations:
        has_rejection = evaluation.overall_status is CheckpointStatus.FAIL
        if has_rejection != (evaluation.attempt_number in rejections_by_attempt):
            raise OutputGenerationError(
                "The persisted rejection history does not match its evaluations."
            )
        rejection = rejections_by_attempt.get(evaluation.attempt_number)
        if rejection is not None and set(rejection.failed_checkpoints) != set(
            evaluation.failed_checkpoints
        ):
            raise OutputGenerationError(
                "A persisted rejection does not match its evaluation."
            )

    rules_by_id = {rule.rule_id: rule for rule in rules}
    try:
        applied_rules = tuple(
            rules_by_id[rule.rule_id] for rule in result.applied_rules
        )
    except KeyError as exc:
        raise OutputGenerationError(
            "A learned rule applied to the run is missing from persistence."
        ) from exc

    return _PersistedExecution(
        run=run,
        attempts=attempts,
        evaluations=evaluations,
        rejections=rejections,
        rules=rules,
        applied_rules=applied_rules,
    )


def _render_execution(
    execution: _PersistedExecution,
    output_directory: Path,
) -> dict[str, str]:
    run = execution.run
    evaluations_by_attempt = {
        evaluation.attempt_number: evaluation for evaluation in execution.evaluations
    }
    rejections_by_attempt = {
        rejection.attempt_number: rejection for rejection in execution.rejections
    }
    final_status = run.status.value

    rendered = {
        "evaluation_report.md": _render_evaluation_report(execution),
        "execution_summary.md": _render_execution_summary(
            execution,
            output_directory,
        ),
        "attempt_history.md": _render_attempt_history(
            execution,
            evaluations_by_attempt,
            rejections_by_attempt,
        ),
        "learned_rules.md": _render_learned_rules(execution),
    }
    if run.status is RunStatus.APPROVED:
        rendered["final_lesson.md"] = _render_lesson(
            execution,
            approved=True,
        )
    else:
        rendered["rejected_lesson.md"] = _render_lesson(
            execution,
            approved=False,
        )
        rendered["rejection_log.md"] = _render_rejection_log(
            execution,
            rejections_by_attempt,
        )

    expected_names = (
        APPROVED_FILENAMES if final_status == RunStatus.APPROVED.value else REJECTED_FILENAMES
    )
    if set(rendered) != set(expected_names):
        raise OutputGenerationError("The output set does not match the final decision.")
    return rendered


def _render_evaluation_report(execution: _PersistedExecution) -> str:
    lines = [
        "# Evaluation Report",
        *_execution_metadata(execution.run),
        f"- Final decision: **{execution.run.status.value}**",
        f"- Total generations: **{len(execution.attempts)}**",
        "",
    ]
    for evaluation in execution.evaluations:
        lines.extend(
            [
                f"## Attempt {evaluation.attempt_number}: {evaluation.overall_status.value}",
                f"- Evaluated at: {evaluation.evaluated_at.isoformat()}",
                f"- Overall reason: {evaluation.overall_reason}",
                "",
            ]
        )
        for checkpoint in evaluation.checkpoints:
            lines.extend(
                [
                    f"### {checkpoint.checkpoint_id.value} — "
                    f"{_checkpoint_label(checkpoint.checkpoint_id)}: "
                    f"{checkpoint.status.value}",
                    f"- Reason: {checkpoint.reason}",
                    f"- Evidence: {checkpoint.evidence}",
                    "",
                ]
            )
    return "\n".join(lines)


def _render_execution_summary(
    execution: _PersistedExecution,
    output_directory: Path,
) -> str:
    rejection_ids = {rejection.rejection_id for rejection in execution.rejections}
    linked_rule_count = sum(
        bool(rejection_ids.intersection(rule.source_rejection_ids))
        for rule in execution.rules
    )
    return "\n".join(
        [
            "# Execution Summary",
            *_execution_metadata(execution.run),
            f"- Final decision: **{execution.run.status.value}**",
            f"- Total generations: **{len(execution.attempts)}**",
            f"- Output directory: `{output_directory}`",
            "- Memory persistence: run, attempt, evaluation, rejection, and rule history loaded from SQLite",
            f"- Learned rules linked to this run: {linked_rule_count}",
            "",
        ]
    )


def _render_attempt_history(
    execution: _PersistedExecution,
    evaluations_by_attempt: dict[int, EvaluationResult],
    rejections_by_attempt: dict[int, RejectionRecord],
) -> str:
    lines = [
        "# Attempt History",
        *_execution_metadata(execution.run),
        f"- Final decision: **{execution.run.status.value}**",
        "",
    ]
    for attempt in execution.attempts:
        evaluation = evaluations_by_attempt[attempt.attempt_number]
        rejection = rejections_by_attempt.get(attempt.attempt_number)
        lines.extend(
            [
                f"## Generation attempt {attempt.attempt_number}",
                f"- Generated at: {attempt.timestamp.isoformat()}",
                f"- Lesson: {attempt.generated_lesson.title}",
                f"- Evaluation: **{evaluation.overall_status.value}**",
            ]
        )
        if rejection is None:
            lines.extend(["- Rejection: none; all checkpoints passed.", ""])
            continue
        lines.extend(
            [
                f"- Failed checkpoints: {', '.join(c.value for c in rejection.failed_checkpoints)}",
                f"- Corrections requested: {'; '.join(rejection.correction_instructions)}",
                f"- Corrections applied: {rejection.correction_applied or 'Not recorded.'}",
                f"- Changes made: {rejection.changes_made or 'Not recorded.'}",
                "",
            ]
        )
        for checkpoint_id in rejection.failed_checkpoints:
            lines.extend(
                [
                    f"### {checkpoint_id.value}: {_checkpoint_label(checkpoint_id)}",
                    f"- Failure reason: {rejection.failure_reasons[checkpoint_id]}",
                    f"- Evidence: {rejection.evidence[checkpoint_id]}",
                    "",
                ]
            )
    return "\n".join(lines)


def _render_rejection_log(
    execution: _PersistedExecution,
    rejections_by_attempt: dict[int, RejectionRecord],
) -> str:
    lines = [
        "# Rejection Log — Final execution REJECTED",
        *_execution_metadata(execution.run),
        "- Final decision: **REJECTED**",
        "",
    ]
    for rejection in execution.rejections:
        lines.extend(
            [
                f"## Rejected attempt {rejection.attempt_number}",
                f"- Failed checkpoints: {', '.join(c.value for c in rejection.failed_checkpoints)}",
                "",
            ]
        )
        for checkpoint_id in rejection.failed_checkpoints:
            lines.extend(
                [
                    f"### {checkpoint_id.value}: {_checkpoint_label(checkpoint_id)}",
                    f"- Failure reason: {rejection.failure_reasons[checkpoint_id]}",
                    f"- Evidence: {rejection.evidence[checkpoint_id]}",
                    "",
                ]
            )
        lines.extend(
            [
                f"- Feedback requested: {'; '.join(rejection.correction_instructions)}",
                f"- Corrections applied: {rejection.correction_applied or 'Not recorded.'}",
                f"- Changes made: {rejection.changes_made or 'Not recorded.'}",
                "",
            ]
        )
    last_rejection = rejections_by_attempt.get(execution.attempts[-1].attempt_number)
    if last_rejection is None:
        raise OutputGenerationError("The final rejected attempt has no rejection log.")
    best_candidate = _best_rejected_attempt(execution)
    lines.extend(
        [
            f"The rejected lesson output selects generation attempt "
            f"{best_candidate.attempt_number}, which has the highest number of passing checkpoints "
            "(ties select the latest attempt).",
            "The final lesson is rejected and is not an approved lesson.",
            "",
        ]
    )
    return "\n".join(lines)


def _render_learned_rules(execution: _PersistedExecution) -> str:
    rejection_ids = {
        rejection.rejection_id for rejection in execution.rejections
    }
    applied_by_id = {rule.rule_id: rule for rule in execution.applied_rules}
    for rule in execution.rules:
        if rejection_ids.intersection(rule.source_rejection_ids):
            applied_by_id.setdefault(rule.rule_id, rule)

    lines = [
        "# Learned Rules",
        *_execution_metadata(execution.run),
        "",
    ]
    if not applied_by_id:
        lines.append("No relevant active rules were applied or created by this run.")
        return "\n".join(lines) + "\n"

    applied_rule_ids = {rule.rule_id for rule in execution.applied_rules}
    for rule in applied_by_id.values():
        applied = rule.rule_id in applied_rule_ids
        lines.extend(
            [
                f"## {rule.related_checkpoint.value} — "
                f"{'Applied at run start' if applied else 'Learned from this run'}",
                f"- Rule ID: `{rule.rule_id}`",
                f"- Status: **{'ACTIVE' if rule.active_status else 'INACTIVE'}**",
                f"- Rule: {rule.rule_description}",
                f"- Rationale: {rule.rationale}",
                f"- Distinct supporting runs: {rule.failure_count}",
                f"- Source rejection IDs: {', '.join(str(item) for item in rule.source_rejection_ids)}",
                "",
            ]
        )
    return "\n".join(lines)


def _render_lesson(execution: _PersistedExecution, *, approved: bool) -> str:
    candidate = (
        execution.attempts[-1]
        if approved
        else _best_rejected_attempt(execution)
    )
    lesson = candidate.generated_lesson
    decision = "APPROVED" if approved else "REJECTED - NOT APPROVED"
    header = [
        f"# {decision}",
        *_execution_metadata(execution.run),
        f"- Candidate generation attempt: {candidate.attempt_number}",
        "",
        "---",
        "",
    ]
    return "\n".join(header) + lesson.full_markdown.rstrip() + "\n"


def _best_rejected_attempt(execution: _PersistedExecution) -> GenerationAttempt:
    evaluations_by_attempt = {
        evaluation.attempt_number: evaluation for evaluation in execution.evaluations
    }
    return max(
        execution.attempts,
        key=lambda attempt: (
            sum(
                checkpoint.status is CheckpointStatus.PASS
                for checkpoint in evaluations_by_attempt[attempt.attempt_number].checkpoints
            ),
            attempt.attempt_number,
        ),
    )


def _execution_metadata(run: ExecutionRun) -> list[str]:
    return [
        f"- Run ID: `{run.run_id}`",
        f"- Topic: {run.topic}",
        f"- Execution timestamp: {run.created_at.isoformat()}",
        f"- Completed at: {run.updated_at.isoformat()}",
    ]


def _checkpoint_label(checkpoint_id: CheckpointId) -> str:
    return CHECKPOINT_LABELS[checkpoint_id]


def _all_checkpoints_pass(evaluation: EvaluationResult) -> bool:
    return (
        len(evaluation.checkpoints) == len(CheckpointId)
        and {checkpoint.checkpoint_id for checkpoint in evaluation.checkpoints}
        == set(CheckpointId)
        and all(
            checkpoint.status is CheckpointStatus.PASS
            for checkpoint in evaluation.checkpoints
        )
        and not evaluation.failed_checkpoints
        and evaluation.overall_status is CheckpointStatus.PASS
    )


def _output_directory_name(run: ExecutionRun) -> str:
    timestamp = run.created_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}-run-{run.run_id}-{uuid4().hex}"


def _write_file(path: Path, content: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as output_file:
        output_file.write(content)
