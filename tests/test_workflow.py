import sqlite3
from pathlib import Path
from typing import Any

import pytest

from app.agents.evaluator import EvaluatorError
from app.agents.generator import LessonGenerationError
from app.config import ConfigurationError, Settings
from app.knowledge.reference_loader import load_reference_material
from app.memory.database import connect
from app.memory.learning_engine import RULE_GUIDANCE
from app.memory.memory_manager import MemoryManager
from app.schemas import (
    CheckpointId,
    CheckpointStatus,
    EvaluationCheckpoint,
    EvaluationErrorCategory,
    EvaluationFailureStage,
    EvaluationRetryDisposition,
    EvaluationResult,
    GenerationErrorCategory,
    GenerationFailureStage,
    Lesson,
    LessonValidationSubcode,
    RunStatus,
    utc_now,
)
from app.workflow import (
    MAX_GENERATION_ATTEMPTS,
    WorkflowExecutionError,
    WorkflowPersistenceError,
    run_lesson_workflow,
)


def make_settings(
    database_path: Path,
    *,
    max_retries: int = 2,
) -> Settings:
    return Settings(
        app_env="test",
        log_level="INFO",
        database_path=database_path,
        max_retries=max_retries,
        llm_provider="google",
        llm_model="mock-model",
        llm_api_key="not-a-real-api-key",
    )


def make_lesson(attempt_number: int) -> Lesson:
    sections = {
        "Introduction": (
            f"RAG uses retrieved information to help answer questions. "
            f"Revision {attempt_number}. [R1]"
        ),
        "Simple Example": (
            f"A learner searches a handbook before asking a question. "
            f"Revision {attempt_number}. [R2]"
        ),
    }
    return Lesson(
        topic="Introduction to RAG",
        title=f"RAG lesson revision {attempt_number}",
        attempt_number=attempt_number,
        sections=sections,
        full_markdown="\n\n".join(
            f"## {heading}\n\n{text}" for heading, text in sections.items()
        ),
        reference_ids=("R1", "R2"),
    )


def make_evaluation(
    run_id,
    attempt_number: int,
    failed: set[CheckpointId] | None = None,
) -> EvaluationResult:
    failed_ids = failed or set()
    checkpoints = tuple(
        EvaluationCheckpoint(
            checkpoint_id=checkpoint_id,
            status=(
                CheckpointStatus.FAIL
                if checkpoint_id in failed_ids
                else CheckpointStatus.PASS
            ),
            reason=(
                f"The lesson does not satisfy {checkpoint_id.value} because "
                "the required quality is missing."
                if checkpoint_id in failed_ids
                else f"The lesson satisfies the requirement for {checkpoint_id.value}."
            ),
            evidence=(
                f"Evidence excerpt for checkpoint {checkpoint_id.value}."
            ),
        )
        for checkpoint_id in CheckpointId
    )
    return EvaluationResult(
        run_id=run_id,
        attempt_number=attempt_number,
        overall_status=(
            CheckpointStatus.FAIL if failed_ids else CheckpointStatus.PASS
        ),
        checkpoints=checkpoints,
        failed_checkpoints=tuple(
            checkpoint_id for checkpoint_id in CheckpointId if checkpoint_id in failed_ids
        ),
        correction_instructions=tuple(
            f"{checkpoint_id.value}: Add the missing requirement."
            for checkpoint_id in CheckpointId
            if checkpoint_id in failed_ids
        ),
        overall_reason=(
            "One or more checkpoints failed."
            if failed_ids
            else "All six mandatory checkpoints passed."
        ),
    )


class FakeGenerator:
    def __init__(self, outcomes: list[Lesson | Exception] | None = None) -> None:
        self.outcomes = outcomes or []
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs: Any) -> Lesson:
        self.calls.append(kwargs)
        if self.outcomes:
            outcome = self.outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        return make_lesson(kwargs["attempt_number"])


class FakeEvaluator:
    def __init__(
        self,
        outcomes: list[set[CheckpointId] | Exception] | None = None,
    ) -> None:
        self.outcomes = outcomes or []
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs: Any) -> EvaluationResult:
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0) if self.outcomes else set()
        if isinstance(outcome, Exception):
            raise outcome
        lesson = kwargs["lesson"]
        return make_evaluation(
            kwargs["run_id"],
            lesson.attempt_number,
            outcome,
        )


def run_workflow(
    tmp_path: Path,
    generator: FakeGenerator,
    evaluator: FakeEvaluator,
    *,
    manager: MemoryManager | None = None,
    max_retries: int = 2,
):
    memory = manager or MemoryManager(tmp_path / "workflow.sqlite3")
    result = run_lesson_workflow(
        generator_fn=generator,
        evaluator_fn=evaluator,
        memory_manager=memory,
        reference_material=load_reference_material(),
        settings=make_settings(tmp_path / "unused.sqlite3", max_retries=max_retries),
    )
    return result, memory


def test_initial_pass_generates_once_and_persists_approval(tmp_path: Path) -> None:
    generator = FakeGenerator()
    evaluator = FakeEvaluator([set()])

    result, memory = run_workflow(tmp_path, generator, evaluator)

    assert result.approved
    assert result.run.status is RunStatus.APPROVED
    assert len(generator.calls) == len(evaluator.calls) == 1
    assert memory.get_run(result.run.run_id) == result.run
    assert memory.get_attempt_history(result.run.run_id) == list(result.attempt_history)
    assert memory.get_evaluation_result(
        result.final_evaluation.evaluation_id
    ) == result.final_evaluation
    assert result.rejection_history == ()


def test_failed_first_generation_passes_on_retry_with_only_failed_feedback(
    tmp_path: Path,
) -> None:
    failed = {CheckpointId.CLEAR_EXPLANATIONS, CheckpointId.TEACHING_FLOW}
    generator = FakeGenerator()
    evaluator = FakeEvaluator([failed, set()])

    result, memory = run_workflow(tmp_path, generator, evaluator)

    assert result.approved
    assert len(generator.calls) == 2
    feedback = generator.calls[1]["previous_feedback"]
    assert len(feedback) == 2
    assert "C4" in feedback[0]
    assert "C6" in feedback[1]
    assert "Failure reason:" in feedback[0]
    assert "Supporting evidence: Evidence excerpt for checkpoint C4." in feedback[0]
    assert "C4: Add the missing requirement." in feedback[0]
    assert all(
        checkpoint_id.value not in "\n".join(feedback)
        for checkpoint_id in set(CheckpointId) - failed
    )
    assert all("Required corrections:" in item for item in feedback)
    assert len(result.rejection_history) == 1
    assert result.rejection_history[0].retry_attempt_number == 2
    assert "Changed content in: Title, Introduction, Simple Example." in (
        result.rejection_history[0].changes_made
    )
    assert memory.get_rejections(result.run.run_id) == list(result.rejection_history)
    assert all(
        rejection.failure_reasons
        and rejection.evidence
        and rejection.correction_instructions
        for rejection in result.rejection_history
    )


def test_two_failures_then_pass_stops_after_three_generations(
    tmp_path: Path,
) -> None:
    generator = FakeGenerator()
    evaluator = FakeEvaluator(
        [
            {CheckpointId.ACCURACY_AND_GROUNDING},
            {CheckpointId.KEY_CONCEPT_COVERAGE},
            set(),
        ]
    )

    result, memory = run_workflow(tmp_path, generator, evaluator)

    assert result.approved
    assert len(generator.calls) == MAX_GENERATION_ATTEMPTS == 3
    assert len(result.attempt_history) == len(result.evaluation_history) == 3
    assert len(result.rejection_history) == 2
    assert [
        item.retry_attempt_number for item in result.rejection_history
    ] == [2, 3]
    assert memory.get_attempt_history(result.run.run_id) == list(result.attempt_history)
    for evaluation in result.evaluation_history:
        assert memory.get_evaluation_result(evaluation.evaluation_id) == evaluation
    assert memory.get_rejections(result.run.run_id) == list(result.rejection_history)


def test_three_failed_generations_return_full_rejected_history(
    tmp_path: Path,
) -> None:
    generator = FakeGenerator()
    evaluator = FakeEvaluator(
        [
            {CheckpointId.ACCURACY_AND_GROUNDING},
            {CheckpointId.CLEAR_EXPLANATIONS, CheckpointId.TEACHING_FLOW},
            {CheckpointId.KEY_CONCEPT_COVERAGE},
        ]
    )

    result, memory = run_workflow(tmp_path, generator, evaluator)

    assert not result.approved
    assert result.run.status is RunStatus.REJECTED
    assert len(generator.calls) == MAX_GENERATION_ATTEMPTS == 3
    assert [attempt.attempt_number for attempt in result.attempt_history] == [1, 2, 3]
    assert [item.attempt_number for item in result.evaluation_history] == [1, 2, 3]
    assert [item.attempt_number for item in result.rejection_history] == [1, 2, 3]
    assert [
        item.retry_attempt_number for item in result.rejection_history
    ] == [2, 3, None]
    assert result.final_evaluation.failed_checkpoints == (
        CheckpointId.KEY_CONCEPT_COVERAGE,
    )
    assert memory.get_run(result.run.run_id).status is RunStatus.REJECTED
    assert memory.get_attempt_history(result.run.run_id) == list(result.attempt_history)
    for evaluation in result.evaluation_history:
        assert memory.get_evaluation_result(evaluation.evaluation_id) == evaluation
    assert memory.get_rejections(result.run.run_id) == list(result.rejection_history)
    assert "No further regeneration was performed" in (
        result.rejection_history[-1].changes_made
    )


def test_generator_failure_marks_run_failed_without_retrying(
    tmp_path: Path,
) -> None:
    generator = FakeGenerator(
        [
            LessonGenerationError(
                "simulated provider failure with sensitive-provider-response-data"
            )
        ]
    )
    evaluator = FakeEvaluator()
    memory = MemoryManager(tmp_path / "workflow.sqlite3")

    with pytest.raises(WorkflowExecutionError, match="lesson generation failed") as error:
        run_workflow(tmp_path, generator, evaluator, manager=memory)

    assert error.value.attempt_number == 1
    assert len(generator.calls) == 1
    assert memory.get_run(error.value.run_id).status is RunStatus.FAILED
    assert memory.get_attempt_history(error.value.run_id) == []
    failed_attempt = MemoryManager(memory.database_path).get_failed_generation_attempts(
        error.value.run_id
    )[0]
    assert failed_attempt.run_id == error.value.run_id
    assert failed_attempt.attempt_number == 1
    assert failed_attempt.status == "FAILED"
    assert failed_attempt.error_type == "LessonGenerationError"
    assert failed_attempt.failure_stage is GenerationFailureStage.UNKNOWN
    assert (
        failed_attempt.error_category is GenerationErrorCategory.GENERATION_ERROR
    )
    assert failed_attempt.error_description == (
        "Lesson generation failed before a validated lesson was produced."
    )
    assert "sensitive-provider-response-data" not in failed_attempt.error_description
    assert failed_attempt.timestamp.tzinfo is not None


@pytest.mark.parametrize(
    ("failure_stage", "error_category", "exception_type"),
    [
        (
            GenerationFailureStage.PROVIDER_REQUEST,
            GenerationErrorCategory.PROVIDER_REQUEST_ERROR,
            "GroqAPIError",
        ),
        (
            GenerationFailureStage.STRUCTURED_OUTPUT_PARSING,
            GenerationErrorCategory.STRUCTURED_OUTPUT_ERROR,
            "OutputParserException",
        ),
        (
            GenerationFailureStage.SCHEMA_VALIDATION,
            GenerationErrorCategory.SCHEMA_VALIDATION_ERROR,
            "ValidationError",
        ),
        (
            GenerationFailureStage.LESSON_CONTENT_VALIDATION,
            GenerationErrorCategory.LESSON_CONTENT_VALIDATION_ERROR,
            "LessonGenerationError",
        ),
    ],
)
def test_generation_failure_diagnostics_are_persisted_safely(
    failure_stage: GenerationFailureStage,
    error_category: GenerationErrorCategory,
    exception_type: str,
    tmp_path: Path,
) -> None:
    sensitive_details = "provider-secret-and-response-must-not-be-persisted"
    generator = FakeGenerator(
        [
            LessonGenerationError(
                sensitive_details,
                failure_stage=failure_stage,
                error_category=error_category,
                exception_type=exception_type,
            )
        ]
    )
    memory = MemoryManager(tmp_path / "workflow.sqlite3")

    with pytest.raises(WorkflowExecutionError) as error:
        run_workflow(tmp_path, generator, FakeEvaluator(), manager=memory)

    [failed_attempt] = memory.get_failed_generation_attempts(error.value.run_id)
    assert failed_attempt.failure_stage is failure_stage
    assert failed_attempt.error_category is error_category
    assert failed_attempt.error_type == exception_type
    assert failed_attempt.attempt_number == 1
    assert failed_attempt.timestamp.tzinfo is not None
    persisted_metadata = " ".join(
        (
            failed_attempt.failure_stage.value,
            failed_attempt.error_category.value,
            failed_attempt.error_type,
            failed_attempt.error_description,
        )
    )
    assert sensitive_details not in persisted_metadata
    assert memory.get_run(error.value.run_id).status is RunStatus.FAILED


def test_validation_subcode_is_persisted_without_lesson_excerpt(
    tmp_path: Path,
) -> None:
    secret_excerpt = "private lesson text must not be written"
    generator = FakeGenerator(
        [
            LessonGenerationError(
                secret_excerpt,
                failure_stage=GenerationFailureStage.LESSON_CONTENT_VALIDATION,
                error_category=(
                    GenerationErrorCategory.LESSON_CONTENT_VALIDATION_ERROR
                ),
                validation_subcode=(
                    LessonValidationSubcode.MISSING_REQUIRED_SECTION
                ),
            )
        ]
    )
    memory = MemoryManager(tmp_path / "workflow.sqlite3")

    with pytest.raises(WorkflowExecutionError) as error:
        run_workflow(tmp_path, generator, FakeEvaluator(), manager=memory)

    [failed_attempt] = memory.get_failed_generation_attempts(error.value.run_id)
    assert (
        failed_attempt.validation_subcode
        is LessonValidationSubcode.MISSING_REQUIRED_SECTION
    )
    with connect(memory.database_path) as connection:
        row = connection.execute(
            "SELECT * FROM failed_generation_attempts WHERE run_id = ?",
            (str(error.value.run_id),),
        ).fetchone()
    assert row["validation_subcode"] == "missing_required_section"
    assert secret_excerpt not in " ".join(str(value) for value in row)


def test_failed_generation_after_quality_retries_keeps_attempt_number_and_limit(
    tmp_path: Path,
) -> None:
    generator = FakeGenerator(
        [
            make_lesson(1),
            make_lesson(2),
            LessonGenerationError("provider response must not be persisted"),
        ]
    )
    evaluator = FakeEvaluator(
        [
            {CheckpointId.ACCURACY_AND_GROUNDING},
            {CheckpointId.CLEAR_EXPLANATIONS},
        ]
    )
    memory = MemoryManager(tmp_path / "workflow.sqlite3")

    with pytest.raises(WorkflowExecutionError, match="lesson generation failed") as error:
        run_workflow(tmp_path, generator, evaluator, manager=memory)

    assert [call["attempt_number"] for call in generator.calls] == [1, 2, 3]
    assert [call["lesson"].attempt_number for call in evaluator.calls] == [1, 2]
    assert [item.attempt_number for item in memory.get_attempt_history(error.value.run_id)] == [
        1,
        2,
    ]
    failed_attempts = memory.get_failed_generation_attempts(error.value.run_id)
    assert len(failed_attempts) == 1
    assert failed_attempts[0].attempt_number == 3
    assert failed_attempts[0].status == "FAILED"
    assert memory.get_run(error.value.run_id).status is RunStatus.FAILED
    assert "provider response must not be persisted" not in (
        failed_attempts[0].error_description
    )


def test_evaluator_failure_preserves_generation_and_marks_run_failed(
    tmp_path: Path,
) -> None:
    generator = FakeGenerator()
    evaluator = FakeEvaluator([EvaluatorError("simulated evaluator failure")])
    memory = MemoryManager(tmp_path / "workflow.sqlite3")

    with pytest.raises(WorkflowExecutionError, match="lesson evaluation failed") as error:
        run_workflow(tmp_path, generator, evaluator, manager=memory)

    assert len(generator.calls) == len(evaluator.calls) == 1
    assert memory.get_run(error.value.run_id).status is RunStatus.FAILED
    assert len(memory.get_attempt_history(error.value.run_id)) == 1
    assert memory.get_rejections(error.value.run_id) == []
    [failed_evaluation] = memory.get_failed_evaluation_attempts(error.value.run_id)
    assert failed_evaluation.attempt_number == 1
    assert failed_evaluation.failure_stage is EvaluationFailureStage.EVALUATION_VALIDATION
    assert (
        failed_evaluation.error_category
        is EvaluationErrorCategory.EVALUATION_VALIDATION_ERROR
    )
    assert failed_evaluation.error_type == "EvaluatorError"
    assert memory.get_evaluation_history(error.value.run_id) == []


def test_rate_limited_evaluator_failure_is_persisted_without_approval(
    tmp_path: Path,
) -> None:
    generator = FakeGenerator()
    evaluator = FakeEvaluator(
        [
            EvaluatorError(
                "provider body and credentials must never be persisted",
                failure_stage=EvaluationFailureStage.API_REQUEST,
                error_category=EvaluationErrorCategory.RATE_LIMITED,
                exception_type="RateLimitError",
                retry_disposition=(
                    EvaluationRetryDisposition.RETRY_AFTER_EXCEEDS_CAP
                ),
            )
        ]
    )
    memory = MemoryManager(tmp_path / "workflow.sqlite3")

    with pytest.raises(WorkflowExecutionError, match="lesson evaluation failed") as error:
        run_workflow(tmp_path, generator, evaluator, manager=memory)

    assert len(generator.calls) == 1
    assert len(memory.get_attempt_history(error.value.run_id)) == 1
    assert memory.get_run(error.value.run_id).status is RunStatus.FAILED
    assert memory.get_evaluation_history(error.value.run_id) == []
    [failed_evaluation] = memory.get_failed_evaluation_attempts(error.value.run_id)
    assert failed_evaluation.failure_stage is EvaluationFailureStage.API_REQUEST
    assert failed_evaluation.error_category is EvaluationErrorCategory.RATE_LIMITED
    assert (
        failed_evaluation.retry_disposition
        is EvaluationRetryDisposition.RETRY_AFTER_EXCEEDS_CAP
    )
    assert failed_evaluation.error_type == "RateLimitError"
    persisted_metadata = " ".join(
        (
            failed_evaluation.failure_stage.value,
            failed_evaluation.error_category.value,
            failed_evaluation.error_type,
            failed_evaluation.error_description,
            failed_evaluation.retry_disposition.value,
        )
    )
    assert "provider body and credentials" not in persisted_metadata
    assert "exceeded the configured maximum wait" in (
        failed_evaluation.error_description
    )


def test_evaluator_error_on_last_generation_does_not_exceed_retry_limit(
    tmp_path: Path,
) -> None:
    generator = FakeGenerator()
    evaluator = FakeEvaluator(
        [
            {CheckpointId.ACCURACY_AND_GROUNDING},
            {CheckpointId.CLEAR_EXPLANATIONS},
            EvaluatorError("simulated evaluator failure"),
        ]
    )
    memory = MemoryManager(tmp_path / "workflow.sqlite3")

    with pytest.raises(WorkflowExecutionError, match="lesson evaluation failed") as error:
        run_workflow(tmp_path, generator, evaluator, manager=memory)

    assert len(generator.calls) == len(evaluator.calls) == MAX_GENERATION_ATTEMPTS == 3
    assert len(memory.get_attempt_history(error.value.run_id)) == 3
    assert len(memory.get_rejections(error.value.run_id)) == 2
    assert memory.get_run(error.value.run_id).status is RunStatus.FAILED
    [failed_evaluation] = memory.get_failed_evaluation_attempts(error.value.run_id)
    assert failed_evaluation.attempt_number == MAX_GENERATION_ATTEMPTS


def test_inconsistent_evaluator_cannot_approve_a_failed_checkpoint(
    tmp_path: Path,
) -> None:
    generator = FakeGenerator()
    memory = MemoryManager(tmp_path / "workflow.sqlite3")

    def inconsistent_evaluator(**kwargs: Any) -> EvaluationResult:
        evaluation = make_evaluation(
            kwargs["run_id"],
            kwargs["lesson"].attempt_number,
            {CheckpointId.ACCURACY_AND_GROUNDING},
        )
        return evaluation.model_copy(
            update={"overall_status": CheckpointStatus.PASS}
        )

    with pytest.raises(WorkflowExecutionError, match="inconsistent result") as error:
        run_lesson_workflow(
            generator_fn=generator,
            evaluator_fn=inconsistent_evaluator,
            memory_manager=memory,
            reference_material=load_reference_material(),
            settings=make_settings(tmp_path / "unused.sqlite3"),
        )

    assert memory.get_run(error.value.run_id).status is RunStatus.FAILED
    assert len(memory.get_attempt_history(error.value.run_id)) == 1
    assert memory.get_rejections(error.value.run_id) == []


def test_database_persistence_failure_is_surfaced_without_approval(
    tmp_path: Path,
) -> None:
    class FailingMemoryManager(MemoryManager):
        def save_evaluation_result(self, result: EvaluationResult) -> EvaluationResult:
            raise sqlite3.OperationalError("simulated disk failure")

    generator = FakeGenerator()
    evaluator = FakeEvaluator([set()])
    memory = FailingMemoryManager(tmp_path / "workflow.sqlite3")

    with pytest.raises(WorkflowPersistenceError, match="evaluation for attempt 1"):
        run_workflow(tmp_path, generator, evaluator, manager=memory)

    run = memory.get_run_history()[0]
    assert run.status is RunStatus.FAILED
    assert len(memory.get_attempt_history(run.run_id)) == 1


def test_retry_configuration_cannot_exceed_two_retries(tmp_path: Path) -> None:
    generator = FakeGenerator()
    evaluator = FakeEvaluator()
    memory = MemoryManager(tmp_path / "workflow.sqlite3")

    with pytest.raises(ConfigurationError, match="MAX_RETRIES"):
        run_lesson_workflow(
            generator_fn=generator,
            evaluator_fn=evaluator,
            memory_manager=memory,
            reference_material=load_reference_material(),
            settings=make_settings(tmp_path / "unused.sqlite3", max_retries=3),
        )

    assert generator.calls == []


def test_learned_rules_are_created_and_passed_across_workflow_runs(
    tmp_path: Path,
) -> None:
    memory = MemoryManager(tmp_path / "workflow.sqlite3")
    failed = {CheckpointId.CLEAR_EXPLANATIONS}

    for _ in range(2):
        run_lesson_workflow(
            generator_fn=FakeGenerator(),
            evaluator_fn=FakeEvaluator([failed]),
            memory_manager=memory,
            reference_material=load_reference_material(),
            settings=make_settings(
                tmp_path / "unused.sqlite3",
                max_retries=0,
            ),
        )

    generator = FakeGenerator()
    result = run_lesson_workflow(
        generator_fn=generator,
        evaluator_fn=FakeEvaluator([set()]),
        memory_manager=memory,
        reference_material=load_reference_material(),
        settings=make_settings(tmp_path / "unused.sqlite3", max_retries=0),
    )

    assert result.approved
    assert len(result.applied_rules) == 1
    assert result.applied_rules[0].rule_description == RULE_GUIDANCE[
        CheckpointId.CLEAR_EXPLANATIONS
    ]
    assert generator.calls[0]["learned_rules"] == result.applied_rules
    assert len(result.final_evaluation.checkpoints) == len(CheckpointId) == 6


def test_inactive_and_topic_irrelevant_rules_are_not_passed_to_generator(
    tmp_path: Path,
) -> None:
    memory = MemoryManager(tmp_path / "workflow.sqlite3")
    failed = {CheckpointId.CLEAR_EXPLANATIONS}
    for _ in range(2):
        run_lesson_workflow(
            generator_fn=FakeGenerator(),
            evaluator_fn=FakeEvaluator([failed]),
            memory_manager=memory,
            reference_material=load_reference_material(),
            settings=make_settings(
                tmp_path / "unused.sqlite3",
                max_retries=0,
            ),
        )
    rule = memory.get_active_rules()[0]

    irrelevant_generator = FakeGenerator()
    run_lesson_workflow(
        topic="A different topic",
        generator_fn=irrelevant_generator,
        evaluator_fn=FakeEvaluator([set()]),
        memory_manager=memory,
        reference_material=load_reference_material(),
        settings=make_settings(tmp_path / "unused.sqlite3", max_retries=0),
    )
    memory.update_learned_rule(
        rule.model_copy(update={"active_status": False, "updated_at": utc_now()})
    )

    inactive_generator = FakeGenerator()
    run_lesson_workflow(
        generator_fn=inactive_generator,
        evaluator_fn=FakeEvaluator([set()]),
        memory_manager=memory,
        reference_material=load_reference_material(),
        settings=make_settings(tmp_path / "unused.sqlite3", max_retries=0),
    )

    assert irrelevant_generator.calls[0]["learned_rules"] == ()
    assert inactive_generator.calls[0]["learned_rules"] == ()


def test_learned_rule_cannot_override_a_failed_evaluation(
    tmp_path: Path,
) -> None:
    memory = MemoryManager(tmp_path / "workflow.sqlite3")
    failed = {CheckpointId.CLEAR_EXPLANATIONS}
    for _ in range(2):
        run_lesson_workflow(
            generator_fn=FakeGenerator(),
            evaluator_fn=FakeEvaluator([failed]),
            memory_manager=memory,
            reference_material=load_reference_material(),
            settings=make_settings(
                tmp_path / "unused.sqlite3",
                max_retries=0,
            ),
        )

    generator = FakeGenerator()
    result = run_lesson_workflow(
        generator_fn=generator,
        evaluator_fn=FakeEvaluator([failed]),
        memory_manager=memory,
        reference_material=load_reference_material(),
        settings=make_settings(tmp_path / "unused.sqlite3", max_retries=0),
    )

    assert generator.calls[0]["learned_rules"]
    assert not result.approved
    assert result.run.status is RunStatus.REJECTED
    assert result.final_evaluation.overall_status is CheckpointStatus.FAIL
    assert result.final_evaluation.failed_checkpoints == (
        CheckpointId.CLEAR_EXPLANATIONS,
    )
    assert len(result.final_evaluation.checkpoints) == len(CheckpointId) == 6


def test_learning_database_error_marks_run_failed_without_approval(
    tmp_path: Path,
) -> None:
    class FailingLearningMemoryManager(MemoryManager):
        def get_previous_failures(
            self,
            checkpoint_id: CheckpointId | None = None,
        ):
            raise sqlite3.OperationalError("simulated learning database failure")

    memory = FailingLearningMemoryManager(tmp_path / "workflow.sqlite3")
    generator = FakeGenerator()
    evaluator = FakeEvaluator([{CheckpointId.CLEAR_EXPLANATIONS}])

    with pytest.raises(
        WorkflowPersistenceError,
        match="failure-pattern learning",
    ):
        run_workflow(tmp_path, generator, evaluator, manager=memory, max_retries=0)

    run = memory.get_run_history()[0]
    assert run.status is RunStatus.FAILED
    assert len(memory.get_attempt_history(run.run_id)) == 1
    assert len(memory.get_evaluation_history(run.run_id)) == 1
    assert len(memory.get_rejections(run.run_id)) == 1
    assert memory.get_active_rules() == []
