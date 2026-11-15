import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar
from uuid import UUID, uuid4

from pydantic import ValidationError

from app.agents.evaluator import EvaluatorError, evaluate_lesson
from app.agents.generator import (
    LessonGenerationError,
    _sanitize_exception_type,
    generate_lesson,
)
from app.config import (
    DEFAULT_TOPIC,
    MAX_ALLOWED_RETRIES,
    ConfigurationError,
    Settings,
    load_settings,
)
from app.knowledge.knowledge_base import KnowledgeBaseManager
from app.knowledge.reference_loader import ReferenceLoadError, load_reference_material
from app.memory.learning_engine import (
    get_relevant_learned_rules,
    learn_from_rejection,
)
from app.memory.memory_manager import MemoryManager, RecordNotFoundError
from app.schemas import (
    CHECKPOINT_LABELS,
    CheckpointId,
    CheckpointStatus,
    EvaluationResult,
    EvaluationErrorCategory,
    EvaluationFailureStage,
    EvaluationRetryDisposition,
    ExecutionRun,
    GenerationErrorCategory,
    GenerationFailureStage,
    FailedGenerationAttempt,
    FailedEvaluationAttempt,
    LessonValidationSubcode,
    GenerationAttempt,
    LearnedRule,
    Lesson,
    ReferenceMaterial,
    RejectionRecord,
    RunStatus,
)


MAX_GENERATION_ATTEMPTS = MAX_ALLOWED_RETRIES + 1
GeneratorFunction = Callable[..., Lesson]
EvaluatorFunction = Callable[..., EvaluationResult]
T = TypeVar("T")


class WorkflowExecutionError(RuntimeError):
    """Raised when a workflow run fails before reaching approval or rejection."""

    def __init__(self, run_id: UUID, attempt_number: int, reason: str) -> None:
        super().__init__(
            f"Workflow run {run_id} failed during attempt {attempt_number}: {reason}"
        )
        self.run_id = run_id
        self.attempt_number = attempt_number


class WorkflowPersistenceError(RuntimeError):
    """Raised when workflow history cannot be persisted."""


@dataclass(frozen=True)
class WorkflowResult:
    run: ExecutionRun
    final_lesson: Lesson
    final_evaluation: EvaluationResult
    attempt_history: tuple[GenerationAttempt, ...]
    evaluation_history: tuple[EvaluationResult, ...]
    rejection_history: tuple[RejectionRecord, ...]
    applied_rules: tuple[LearnedRule, ...] = ()

    @property
    def approved(self) -> bool:
        return self.run.status is RunStatus.APPROVED


@dataclass(frozen=True)
class WorkflowProgress:
    stage: str
    attempt_number: int | None = None


ProgressCallback = Callable[[WorkflowProgress], None]


def run_lesson_workflow(
    topic: str = DEFAULT_TOPIC,
    *,
    generator_fn: GeneratorFunction = generate_lesson,
    evaluator_fn: EvaluatorFunction = evaluate_lesson,
    memory_manager: MemoryManager | None = None,
    reference_material: ReferenceMaterial | None = None,
    settings: Settings | None = None,
    run_id: UUID | None = None,
    progress_callback: ProgressCallback | None = None,
    mode: str = "assessment",
    knowledge_base_id: UUID | None = None,
    knowledge_base_manager: KnowledgeBaseManager | None = None,
    max_retries: int | None = None,
) -> WorkflowResult:
    """Generate, evaluate, and retry a lesson while persisting every valid result."""
    _emit_progress(progress_callback, "validating_topic")
    if not isinstance(topic, str) or not topic.strip():
        raise ValueError("Topic must not be empty.")
    normalized_topic = topic.strip()
    current_settings = settings if settings is not None else load_settings()
    mode_name = str(mode).strip().lower() if mode is not None else "assessment"
    if mode_name not in {"assessment", "gpt", "rag", "demo"}:
        raise ValueError("Generation mode must be one of: assessment, gpt, rag, demo.")
    retry_count = (
        MAX_ALLOWED_RETRIES
        if mode_name in {"gpt", "rag"}
        else current_settings.max_retries if max_retries is None else max_retries
    )
    if type(retry_count) is not int or not 0 <= retry_count <= MAX_ALLOWED_RETRIES:
        raise ConfigurationError(
            f"MAX_RETRIES must be between 0 and {MAX_ALLOWED_RETRIES}."
        )

    _emit_progress(progress_callback, "loading_reference_knowledge")
    references = (
        reference_material
        if reference_material is not None
        else _resolve_reference_material(
            normalized_topic,
            mode=mode_name,
            knowledge_base_id=knowledge_base_id,
            knowledge_base_manager=knowledge_base_manager,
        )
    )
    _emit_progress(progress_callback, "initializing_persistence")
    try:
        manager = (
            memory_manager
            if memory_manager is not None
            else MemoryManager(current_settings.database_path)
        )
    except (OSError, sqlite3.Error) as exc:
        raise WorkflowPersistenceError(
            "Unable to initialize workflow persistence."
        ) from exc

    run = ExecutionRun(
        run_id=run_id or uuid4(),
        topic=normalized_topic,
        mode=mode_name,
        max_retries=retry_count,
    )
    _persist("execution run", lambda: manager.create_run(run))
    _emit_progress(progress_callback, "retrieving_learned_rules")
    applied_rules = _persist(
        "relevant learned rules",
        lambda: get_relevant_learned_rules(manager, topic=normalized_topic),
        manager=manager,
        run_id=run.run_id,
    )

    attempts: list[GenerationAttempt] = []
    evaluations: list[EvaluationResult] = []
    rejections: list[RejectionRecord] = []
    previous_feedback: tuple[str, ...] = ()
    previous_lesson: Lesson | None = None
    pending_rejection: RejectionRecord | None = None
    max_attempts = min(
        retry_count + 1,
        MAX_GENERATION_ATTEMPTS,
    )

    for attempt_number in range(1, max_attempts + 1):
        _emit_progress(
            progress_callback,
            "generating_lesson",
            attempt_number,
        )
        if pending_rejection is not None:
            pending_rejection = _update_rejection(
                manager,
                pending_rejection,
                retry_attempt_number=attempt_number,
                correction_applied=(
                    f"Feedback supplied to generation attempt {attempt_number}."
                ),
                changes_made=f"Generation attempt {attempt_number} is in progress.",
            )
            rejections[-1] = pending_rejection

        try:
            lesson = generator_fn(
                topic=normalized_topic,
                attempt_number=attempt_number,
                previous_feedback=previous_feedback,
                reference_material=references,
                learned_rules=applied_rules,
                settings=current_settings,
            )
        except Exception as exc:
            _emit_progress(
                progress_callback,
                "failed",
                attempt_number,
            )
            if pending_rejection is not None:
                pending_rejection = _update_rejection(
                    manager,
                    pending_rejection,
                    retry_attempt_number=attempt_number,
                    correction_applied=(
                        f"Feedback supplied to generation attempt {attempt_number}."
                    ),
                    changes_made=(
                        f"Generation attempt {attempt_number} failed before "
                        f"producing a lesson ({_sanitize_exception_type(type(exc).__name__)})."
                    ),
                )
                rejections[-1] = pending_rejection
            failure_stage, error_category, exception_type, validation_subcode = (
                _generation_failure_metadata(exc)
            )
            failed_attempt = FailedGenerationAttempt(
                run_id=run.run_id,
                attempt_number=attempt_number,
                failure_stage=failure_stage,
                error_category=error_category,
                validation_subcode=validation_subcode,
                error_type=exception_type,
                error_description=_safe_generation_error_description(exc),
            )
            _persist(
                f"failed generation attempt {attempt_number}",
                lambda: manager.save_failed_generation_attempt(failed_attempt),
                manager=manager,
                run_id=run.run_id,
            )
            run = _persist(
                "failed execution status",
                lambda: manager.update_run_status(run.run_id, RunStatus.FAILED),
                mark_failed_on_error=False,
            )
            raise WorkflowExecutionError(
                run.run_id,
                attempt_number,
                "lesson generation failed",
            ) from exc

        if not isinstance(lesson, Lesson) or lesson.attempt_number != attempt_number:
            run = _persist(
                "failed execution status",
                lambda: manager.update_run_status(run.run_id, RunStatus.FAILED),
                mark_failed_on_error=False,
            )
            raise WorkflowExecutionError(
                run.run_id,
                attempt_number,
                "generator returned an invalid lesson or mismatched attempt number",
            )

        attempt = GenerationAttempt(
            run_id=run.run_id,
            attempt_number=attempt_number,
            generated_lesson=lesson,
        )
        _persist(
            f"generation attempt {attempt_number}",
            lambda: manager.save_generation_attempt(attempt),
            manager=manager,
            run_id=run.run_id,
        )
        attempts.append(attempt)

        if pending_rejection is not None and previous_lesson is not None:
            pending_rejection = _update_rejection(
                manager,
                pending_rejection,
                retry_attempt_number=attempt_number,
                correction_applied=(
                    f"Feedback supplied to generation attempt {attempt_number}."
                ),
                changes_made=_describe_changes(previous_lesson, lesson),
            )
            rejections[-1] = pending_rejection
            pending_rejection = None

        try:
            _emit_progress(
                progress_callback,
                "evaluating_lesson",
                attempt_number,
            )
            evaluation = evaluator_fn(
                lesson=lesson,
                reference_material=references,
                run_id=run.run_id,
                settings=current_settings,
            )
            evaluation = _validate_evaluation(
                evaluation,
                run_id=run.run_id,
                attempt_number=attempt_number,
            )
        except (
            ConfigurationError,
            EvaluatorError,
            ReferenceLoadError,
            ValidationError,
        ) as exc:
            _emit_progress(
                progress_callback,
                "failed",
                attempt_number,
            )
            _persist(
                f"failed evaluation attempt {attempt_number}",
                lambda: manager.save_failed_evaluation_attempt(
                    _failed_evaluation_attempt(
                        run_id=run.run_id,
                        attempt_number=attempt_number,
                        error=exc,
                    )
                ),
                manager=manager,
                run_id=run.run_id,
            )
            run = _persist(
                "failed execution status",
                lambda: manager.update_run_status(run.run_id, RunStatus.FAILED),
                mark_failed_on_error=False,
            )
            raise WorkflowExecutionError(
                run.run_id,
                attempt_number,
                "lesson evaluation failed",
            ) from exc
        except WorkflowExecutionError as exc:
            _emit_progress(
                progress_callback,
                "failed",
                attempt_number,
            )
            _persist(
                f"failed evaluation attempt {attempt_number}",
                lambda: manager.save_failed_evaluation_attempt(
                    _failed_evaluation_attempt(
                        run_id=run.run_id,
                        attempt_number=attempt_number,
                        error=exc,
                    )
                ),
                manager=manager,
                run_id=run.run_id,
            )
            _persist(
                "failed execution status",
                lambda: manager.update_run_status(run.run_id, RunStatus.FAILED),
                mark_failed_on_error=False,
            )
            raise

        _persist(
            f"evaluation for attempt {attempt_number}",
            lambda: manager.save_evaluation_result(evaluation),
            manager=manager,
            run_id=run.run_id,
        )
        evaluations.append(evaluation)

        if _evaluation_passes(evaluation):
            run = _persist(
                "approved execution status",
                lambda: manager.update_run_status(run.run_id, RunStatus.APPROVED),
                manager=manager,
                run_id=run.run_id,
            )
            _emit_progress(
                progress_callback,
                "approved",
                attempt_number,
            )
            return WorkflowResult(
                run=run,
                final_lesson=lesson,
                final_evaluation=evaluation,
                attempt_history=tuple(attempts),
                evaluation_history=tuple(evaluations),
                rejection_history=tuple(rejections),
                applied_rules=applied_rules,
            )

        rejection = _create_rejection_record(evaluation)
        _persist(
            f"rejection for attempt {attempt_number}",
            lambda: manager.save_rejection(rejection),
            manager=manager,
            run_id=run.run_id,
        )
        rejections.append(rejection)
        _persist(
            "failure-pattern learning",
            lambda: learn_from_rejection(
                manager,
                rejection,
                topic=normalized_topic,
            ),
            manager=manager,
            run_id=run.run_id,
        )

        if attempt_number == max_attempts:
            rejection = _update_rejection(
                manager,
                rejection,
                retry_attempt_number=None,
                correction_applied="No retry was available; the run is rejected.",
                changes_made=(
                    "No further regeneration was performed; this is the final "
                    "rejected lesson."
                ),
            )
            rejections[-1] = rejection
            run = _persist(
                "rejected execution status",
                lambda: manager.update_run_status(run.run_id, RunStatus.REJECTED),
                manager=manager,
                run_id=run.run_id,
            )
            _emit_progress(
                progress_callback,
                "rejected",
                attempt_number,
            )
            return WorkflowResult(
                run=run,
                final_lesson=lesson,
                final_evaluation=evaluation,
                attempt_history=tuple(attempts),
                evaluation_history=tuple(evaluations),
                rejection_history=tuple(rejections),
                applied_rules=applied_rules,
            )

        _emit_progress(
            progress_callback,
            "processing_feedback",
            attempt_number,
        )
        previous_feedback = build_evaluation_feedback(evaluation)
        previous_lesson = lesson
        pending_rejection = rejection

    raise WorkflowExecutionError(
        run.run_id,
        max_attempts,
        "workflow terminated without an approved or rejected result",
    )


def _emit_progress(
    callback: ProgressCallback | None,
    stage: str,
    attempt_number: int | None = None,
) -> None:
    if callback is not None:
        callback(WorkflowProgress(stage=stage, attempt_number=attempt_number))


def _validate_evaluation(
    evaluation: EvaluationResult,
    *,
    run_id: UUID,
    attempt_number: int,
) -> EvaluationResult:
    if not isinstance(evaluation, EvaluationResult):
        raise WorkflowExecutionError(
            run_id,
            attempt_number,
            "evaluator returned an unsupported result type",
        )
    try:
        validated = EvaluationResult.model_validate(evaluation.model_dump())
    except ValidationError as exc:
        raise WorkflowExecutionError(
            run_id,
            attempt_number,
            "evaluator returned an inconsistent result",
        ) from exc
    if validated.run_id != run_id or validated.attempt_number != attempt_number:
        raise WorkflowExecutionError(
            run_id,
            attempt_number,
            "evaluator result does not match the current run and attempt",
        )
    missing_corrections = [
        checkpoint_id
        for checkpoint_id in validated.failed_checkpoints
        if not any(
            instruction.strip().upper().startswith(f"{checkpoint_id.value}:")
            for instruction in validated.correction_instructions
        )
    ]
    if missing_corrections or (
        not validated.failed_checkpoints and validated.correction_instructions
    ):
        raise WorkflowExecutionError(
            run_id,
            attempt_number,
            "evaluator returned incomplete or unexpected correction instructions",
        )
    return validated


def _evaluation_passes(evaluation: EvaluationResult) -> bool:
    required_checkpoints = set(CheckpointId)
    checkpoint_ids = [checkpoint.checkpoint_id for checkpoint in evaluation.checkpoints]
    if len(checkpoint_ids) != len(required_checkpoints) or set(checkpoint_ids) != (
        required_checkpoints
    ):
        return False
    failed_checkpoints = {
        checkpoint.checkpoint_id
        for checkpoint in evaluation.checkpoints
        if checkpoint.status is CheckpointStatus.FAIL
    }
    return (
        not failed_checkpoints
        and not evaluation.failed_checkpoints
        and evaluation.overall_status is CheckpointStatus.PASS
    )


def build_evaluation_feedback(evaluation: EvaluationResult) -> tuple[str, ...]:
    failed_ids = set(evaluation.failed_checkpoints)
    checkpoints = {
        checkpoint.checkpoint_id: checkpoint
        for checkpoint in evaluation.checkpoints
        if checkpoint.checkpoint_id in failed_ids
    }
    instructions_by_checkpoint: dict[CheckpointId, list[str]] = {
        checkpoint_id: [] for checkpoint_id in failed_ids
    }
    for instruction in evaluation.correction_instructions:
        prefix, separator, _ = instruction.partition(":")
        if not separator:
            continue
        try:
            checkpoint_id = CheckpointId(prefix.strip())
        except ValueError:
            continue
        if checkpoint_id in instructions_by_checkpoint:
            instructions_by_checkpoint[checkpoint_id].append(instruction)

    feedback = []
    for checkpoint_id in CheckpointId:
        if checkpoint_id not in failed_ids:
            continue
        checkpoint = checkpoints.get(checkpoint_id)
        corrections = instructions_by_checkpoint[checkpoint_id]
        if checkpoint is None or not corrections:
            raise WorkflowExecutionError(
                evaluation.run_id,
                evaluation.attempt_number,
                f"failed checkpoint {checkpoint_id.value} has incomplete feedback",
            )
        feedback.append(
            "\n".join(
                (
                    f"{checkpoint_id.value} "
                    f"({CHECKPOINT_LABELS[checkpoint_id]}) failed.",
                    f"Failure reason: {checkpoint.reason}",
                    f"Supporting evidence: {checkpoint.evidence}",
                    "Required corrections:",
                    *[f"- {instruction}" for instruction in corrections],
                )
            )
        )
    return tuple(feedback)


def _create_rejection_record(evaluation: EvaluationResult) -> RejectionRecord:
    failed_checkpoints = tuple(
        checkpoint.checkpoint_id
        for checkpoint in evaluation.checkpoints
        if checkpoint.checkpoint_id in set(evaluation.failed_checkpoints)
    )
    failure_reasons = {
        checkpoint.checkpoint_id: checkpoint.reason
        for checkpoint in evaluation.checkpoints
        if checkpoint.checkpoint_id in set(failed_checkpoints)
    }
    evidence = {
        checkpoint.checkpoint_id: checkpoint.evidence
        for checkpoint in evaluation.checkpoints
        if checkpoint.checkpoint_id in set(failed_checkpoints)
    }
    return RejectionRecord(
        run_id=evaluation.run_id,
        attempt_number=evaluation.attempt_number,
        failed_checkpoints=failed_checkpoints,
        failure_reasons=failure_reasons,
        evidence=evidence,
        correction_instructions=evaluation.correction_instructions,
        correction_applied="Awaiting regeneration decision.",
        changes_made="Regeneration has not yet been attempted.",
    )


def _update_rejection(
    manager: MemoryManager,
    rejection: RejectionRecord,
    *,
    retry_attempt_number: int | None,
    correction_applied: str,
    changes_made: str,
) -> RejectionRecord:
    return _persist(
        f"rejection progress for attempt {rejection.attempt_number}",
        lambda: manager.update_rejection_progress(
            rejection.rejection_id,
            retry_attempt_number,
            correction_applied,
            changes_made,
        ),
        manager=manager,
        run_id=rejection.run_id,
    )


def _describe_changes(previous: Lesson, revised: Lesson) -> str:
    changed_sections = [
        heading
        for heading in dict.fromkeys((*previous.sections, *revised.sections))
        if previous.sections.get(heading) != revised.sections.get(heading)
    ]
    if previous.title != revised.title:
        changed_sections.insert(0, "Title")
    if not changed_sections:
        return "No lesson content changes were detected."
    return "Changed content in: " + ", ".join(changed_sections) + "."


def _resolve_reference_material(
    topic: str,
    *,
    mode: str,
    knowledge_base_id: UUID | None,
    knowledge_base_manager: KnowledgeBaseManager | None,
) -> ReferenceMaterial:
    if mode in {"assessment", "gpt", "demo"}:
        return load_reference_material()
    if knowledge_base_manager is None:
        raise ReferenceLoadError("The RAG knowledge base is unavailable.")
    try:
        if knowledge_base_id is not None:
            return knowledge_base_manager.build_reference_material_for_document(
                document_id=knowledge_base_id,
                query=topic,
                limit=5,
            )
        return knowledge_base_manager.build_reference_material(
            query=topic,
            limit=5,
        )
    except ValueError as exc:
        raise ReferenceLoadError(
            "The RAG knowledge base has no matching reference material."
        ) from exc


def _safe_generation_error_description(error: Exception) -> str:
    if isinstance(error, LessonGenerationError):
        return "Lesson generation failed before a validated lesson was produced."
    if isinstance(error, ConfigurationError):
        return "Generation stopped because the LLM configuration is invalid."
    if isinstance(error, ReferenceLoadError):
        return "Generation stopped because trusted reference material is unavailable."
    if isinstance(error, ValidationError):
        return "Generation stopped because the lesson response failed validation."
    return "Generation failed before a lesson was produced."


def _generation_failure_metadata(
    error: Exception,
) -> tuple[
    GenerationFailureStage,
    GenerationErrorCategory,
    str,
    LessonValidationSubcode | None,
]:
    if isinstance(error, LessonGenerationError):
        return (
            error.failure_stage,
            error.error_category,
            error.exception_type,
            error.validation_subcode,
        )
    if isinstance(error, ConfigurationError):
        return (
            GenerationFailureStage.PROVIDER_REQUEST,
            GenerationErrorCategory.CONFIGURATION_ERROR,
            _sanitize_exception_type(type(error).__name__),
            None,
        )
    if isinstance(error, ValidationError):
        return (
            GenerationFailureStage.SCHEMA_VALIDATION,
            GenerationErrorCategory.SCHEMA_VALIDATION_ERROR,
            _sanitize_exception_type(type(error).__name__),
            None,
        )
    return (
        GenerationFailureStage.UNKNOWN,
        GenerationErrorCategory.GENERATION_ERROR,
        _sanitize_exception_type(type(error).__name__),
        None,
    )


def _failed_evaluation_attempt(
    *,
    run_id: UUID,
    attempt_number: int,
    error: Exception,
) -> FailedEvaluationAttempt:
    (
        failure_stage,
        error_category,
        error_type,
        retry_disposition,
    ) = _evaluation_failure_metadata(error)
    return FailedEvaluationAttempt(
        run_id=run_id,
        attempt_number=attempt_number,
        failure_stage=failure_stage,
        error_category=error_category,
        retry_disposition=retry_disposition,
        error_type=error_type,
        error_description=_safe_evaluation_error_description(
            error_category,
            retry_disposition,
        ),
    )


def _evaluation_failure_metadata(
    error: Exception,
) -> tuple[
    EvaluationFailureStage,
    EvaluationErrorCategory,
    str,
    EvaluationRetryDisposition | None,
]:
    if isinstance(error, EvaluatorError):
        return (
            error.failure_stage,
            error.error_category,
            error.exception_type,
            error.retry_disposition,
        )
    if isinstance(error, ConfigurationError):
        return (
            EvaluationFailureStage.API_REQUEST,
            EvaluationErrorCategory.CONFIGURATION_ERROR,
            _sanitize_exception_type(type(error).__name__),
            None,
        )
    if isinstance(error, ValidationError):
        return (
            EvaluationFailureStage.SCHEMA_VALIDATION,
            EvaluationErrorCategory.SCHEMA_VALIDATION_ERROR,
            _sanitize_exception_type(type(error).__name__),
            None,
        )
    if isinstance(error, WorkflowExecutionError):
        return (
            EvaluationFailureStage.EVALUATION_VALIDATION,
            EvaluationErrorCategory.EVALUATION_VALIDATION_ERROR,
            _sanitize_exception_type(type(error).__name__),
            None,
        )
    return (
        EvaluationFailureStage.UNKNOWN,
        EvaluationErrorCategory.EVALUATOR_ERROR,
        _sanitize_exception_type(type(error).__name__),
        None,
    )


def _safe_evaluation_error_description(
    category: EvaluationErrorCategory,
    retry_disposition: EvaluationRetryDisposition | None,
) -> str:
    if retry_disposition is EvaluationRetryDisposition.RETRY_AFTER_EXCEEDS_CAP:
        return (
            "Evaluator retry was skipped because Retry-After exceeded the "
            "configured maximum wait."
        )
    if retry_disposition is EvaluationRetryDisposition.RETRIES_EXHAUSTED:
        if category is EvaluationErrorCategory.RATE_LIMITED:
            return "Evaluator API remained rate-limited after bounded retries."
        if category is EvaluationErrorCategory.PROVIDER_SERVER_ERROR:
            return "Evaluator API remained unavailable after bounded retries."
    if retry_disposition is EvaluationRetryDisposition.PERMANENT_PROVIDER_FAILURE:
        return "Evaluator provider rejected the request; no retry was attempted."
    if retry_disposition is EvaluationRetryDisposition.RETRY_SKIPPED:
        return "Evaluator provider failure was not eligible for retry."

    descriptions = {
        EvaluationErrorCategory.RATE_LIMITED: "Evaluator API request was rate-limited.",
        EvaluationErrorCategory.PROVIDER_SERVER_ERROR: (
            "Evaluator API request failed with a server error."
        ),
        EvaluationErrorCategory.PROVIDER_PERMANENT_ERROR: (
            "Evaluator provider rejected the request."
        ),
        EvaluationErrorCategory.PROVIDER_ERROR: (
            "Evaluator provider request failed."
        ),
        EvaluationErrorCategory.CONFIGURATION_ERROR: (
            "Evaluation stopped because the LLM configuration is invalid."
        ),
        EvaluationErrorCategory.STRUCTURED_OUTPUT_ERROR: (
            "Evaluator output could not be parsed as structured data."
        ),
        EvaluationErrorCategory.SCHEMA_VALIDATION_ERROR: (
            "Evaluator output failed schema validation."
        ),
        EvaluationErrorCategory.EVALUATION_VALIDATION_ERROR: (
            "Evaluator output failed application validation."
        ),
        EvaluationErrorCategory.EVALUATOR_ERROR: (
            "Evaluation failed before a valid result was produced."
        ),
    }
    return descriptions[category]


def _persist(
    action: str,
    operation: Callable[[], T],
    *,
    manager: MemoryManager | None = None,
    run_id: UUID | None = None,
    mark_failed_on_error: bool = True,
) -> T:
    try:
        return operation()
    except (OSError, sqlite3.Error) as exc:
        status_error = None
        if mark_failed_on_error and manager is not None and run_id is not None:
            try:
                manager.update_run_status(run_id, RunStatus.FAILED)
            except (OSError, RecordNotFoundError, sqlite3.Error) as update_exc:
                status_error = update_exc
        message = f"Unable to persist {action} ({type(exc).__name__})."
        if status_error is not None:
            message += (
                " The run could not be marked FAILED "
                f"({type(status_error).__name__})."
            )
        raise WorkflowPersistenceError(
            message
        ) from exc
