from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)


NonEmptyString = Annotated[StrictStr, Field(min_length=1)]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CheckpointId(str, Enum):
    ACCURACY_AND_GROUNDING = "C1"
    BEGINNER_FRIENDLY_LANGUAGE = "C2"
    TEACHING_THROUGH_EXAMPLES = "C3"
    CLEAR_EXPLANATIONS = "C4"
    KEY_CONCEPT_COVERAGE = "C5"
    TEACHING_FLOW = "C6"


CHECKPOINT_LABELS = {
    CheckpointId.ACCURACY_AND_GROUNDING: "Accuracy and grounding",
    CheckpointId.BEGINNER_FRIENDLY_LANGUAGE: "Beginner-friendly language",
    CheckpointId.TEACHING_THROUGH_EXAMPLES: "Teaching through examples",
    CheckpointId.CLEAR_EXPLANATIONS: "Clear explanations",
    CheckpointId.KEY_CONCEPT_COVERAGE: "Key concept coverage",
    CheckpointId.TEACHING_FLOW: "Teaching flow",
}


class CheckpointStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"


class RunStatus(str, Enum):
    IN_PROGRESS = "IN_PROGRESS"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class GenerationFailureStage(str, Enum):
    UNKNOWN = "unknown"
    PROVIDER_REQUEST = "provider_request"
    STRUCTURED_OUTPUT_PARSING = "structured_output_parsing"
    SCHEMA_VALIDATION = "schema_validation"
    LESSON_CONTENT_VALIDATION = "lesson_content_validation"


class GenerationErrorCategory(str, Enum):
    GENERATION_ERROR = "generation_error"
    PROVIDER_REQUEST_ERROR = "provider_request_error"
    STRUCTURED_OUTPUT_ERROR = "structured_output_error"
    SCHEMA_VALIDATION_ERROR = "schema_validation_error"
    LESSON_CONTENT_VALIDATION_ERROR = "lesson_content_validation_error"
    CONFIGURATION_ERROR = "configuration_error"


class LessonValidationSubcode(str, Enum):
    MISSING_REQUIRED_SECTION = "missing_required_section"
    DUPLICATE_REQUIRED_SECTION = "duplicate_required_section"
    DUPLICATE_SECTION = "duplicate_section"
    UNKNOWN_REFERENCE_ID = "unknown_reference_id"
    MISSING_FACTUAL_CITATION = "missing_factual_citation"
    INVALID_CITATION_FORMAT = "invalid_citation_format"


class EvaluationFailureStage(str, Enum):
    UNKNOWN = "unknown"
    API_REQUEST = "api_request"
    STRUCTURED_OUTPUT_PARSING = "structured_output_parsing"
    SCHEMA_VALIDATION = "schema_validation"
    EVALUATION_VALIDATION = "evaluation_validation"


class EvaluationErrorCategory(str, Enum):
    EVALUATOR_ERROR = "evaluator_error"
    RATE_LIMITED = "rate_limited"
    PROVIDER_SERVER_ERROR = "provider_server_error"
    PROVIDER_PERMANENT_ERROR = "provider_permanent_error"
    PROVIDER_ERROR = "provider_error"
    CONFIGURATION_ERROR = "configuration_error"
    STRUCTURED_OUTPUT_ERROR = "structured_output_error"
    SCHEMA_VALIDATION_ERROR = "schema_validation_error"
    EVALUATION_VALIDATION_ERROR = "evaluation_validation_error"


class EvaluationRetryDisposition(str, Enum):
    RETRY_SKIPPED = "retry_skipped"
    RETRIES_EXHAUSTED = "retries_exhausted"
    RETRY_AFTER_EXCEEDS_CAP = "retry_after_exceeds_cap"
    PERMANENT_PROVIDER_FAILURE = "permanent_provider_failure"


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    @field_validator("*")
    @classmethod
    def normalize_timestamps_to_utc(cls, value: object) -> object:
        if isinstance(value, datetime):
            if value.utcoffset() is None:
                raise ValueError("Timestamps must include a timezone.")
            return value.astimezone(timezone.utc)
        return value


class ReferenceSource(StrictModel):
    source_id: Annotated[StrictStr, Field(pattern=r"^R[1-9]\d*$")]
    title: NonEmptyString
    url: AnyHttpUrl


class ReferenceMaterial(StrictModel):
    title: NonEmptyString
    version: NonEmptyString
    content: NonEmptyString
    sources: tuple[ReferenceSource, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_sources(self) -> "ReferenceMaterial":
        source_ids = [source.source_id for source in self.sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("Reference source IDs must be unique.")
        return self


class ExecutionRun(StrictModel):
    run_id: UUID = Field(default_factory=uuid4)
    topic: NonEmptyString
    mode: Literal["assessment", "gpt", "rag", "demo"] = "assessment"
    max_retries: Annotated[StrictInt, Field(ge=0, le=2)] = 2
    status: RunStatus = RunStatus.IN_PROGRESS
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class Lesson(StrictModel):
    lesson_id: UUID = Field(default_factory=uuid4)
    topic: NonEmptyString
    title: NonEmptyString
    attempt_number: Annotated[StrictInt, Field(ge=1, le=3)]
    sections: dict[StrictStr, StrictStr] = Field(min_length=1)
    full_markdown: NonEmptyString
    reference_ids: tuple[Annotated[StrictStr, Field(pattern=r"^R[1-9]\d*$")], ...] = (
        Field(min_length=1)
    )
    generation_timestamp: datetime = Field(default_factory=utc_now)

    @field_validator("sections")
    @classmethod
    def validate_sections(cls, value: dict[str, str]) -> dict[str, str]:
        if not value:
            raise ValueError("A lesson must contain at least one section.")
        if any(
            not heading.strip() or not text.strip()
            for heading, text in value.items()
        ):
            raise ValueError("Lesson section headings and content must not be empty.")
        return value

    @field_validator("reference_ids")
    @classmethod
    def validate_unique_reference_ids(
        cls, value: tuple[str, ...]
    ) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("Lesson reference IDs must be unique.")
        return value


class ApprovedLessonNote(StrictModel):
    run_id: UUID
    topic: NonEmptyString
    mode: Literal["assessment", "gpt", "rag", "demo"]
    title: NonEmptyString
    created_at: datetime
    evaluation_status: Literal["APPROVED"] = "APPROVED"
    full_markdown: NonEmptyString


class EvaluationCheckpoint(StrictModel):
    checkpoint_id: CheckpointId
    status: CheckpointStatus
    reason: NonEmptyString
    evidence: NonEmptyString


class EvaluationResult(StrictModel):
    evaluation_id: UUID = Field(default_factory=uuid4)
    run_id: UUID
    attempt_number: Annotated[StrictInt, Field(ge=1, le=3)]
    overall_status: CheckpointStatus
    checkpoints: tuple[EvaluationCheckpoint, ...] = Field(
        min_length=len(CheckpointId), max_length=len(CheckpointId)
    )
    failed_checkpoints: tuple[CheckpointId, ...] = ()
    correction_instructions: tuple[NonEmptyString, ...] = ()
    overall_reason: NonEmptyString
    evaluated_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_checkpoint_set(self) -> "EvaluationResult":
        checkpoint_ids = [checkpoint.checkpoint_id for checkpoint in self.checkpoints]
        if len(checkpoint_ids) != len(set(checkpoint_ids)):
            raise ValueError("Evaluation checkpoint IDs must be unique.")
        if set(checkpoint_ids) != set(CheckpointId):
            raise ValueError(
                "Evaluation must contain exactly checkpoints C1 through C6."
            )
        if len(self.failed_checkpoints) != len(set(self.failed_checkpoints)):
            raise ValueError("Failed checkpoint IDs must be unique.")
        failed_by_status = {
            checkpoint.checkpoint_id
            for checkpoint in self.checkpoints
            if checkpoint.status is CheckpointStatus.FAIL
        }
        if set(self.failed_checkpoints) != failed_by_status:
            raise ValueError(
                "Failed checkpoint IDs must match the checkpoints marked FAIL."
            )
        expected_status = (
            CheckpointStatus.FAIL if failed_by_status else CheckpointStatus.PASS
        )
        if self.overall_status is not expected_status:
            raise ValueError(
                "Overall status must be FAIL unless every checkpoint passes."
            )
        return self


class GenerationAttempt(StrictModel):
    attempt_id: UUID = Field(default_factory=uuid4)
    run_id: UUID
    attempt_number: Annotated[StrictInt, Field(ge=1, le=3)]
    generated_lesson: Lesson
    timestamp: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_lesson_attempt_number(self) -> "GenerationAttempt":
        if self.generated_lesson.attempt_number != self.attempt_number:
            raise ValueError("Lesson attempt number must match its generation attempt.")
        return self


class FailedGenerationAttempt(StrictModel):
    failure_id: UUID = Field(default_factory=uuid4)
    run_id: UUID
    attempt_number: Annotated[StrictInt, Field(ge=1, le=3)]
    status: Literal["FAILED"] = "FAILED"
    failure_stage: GenerationFailureStage = GenerationFailureStage.UNKNOWN
    error_category: GenerationErrorCategory = GenerationErrorCategory.GENERATION_ERROR
    validation_subcode: LessonValidationSubcode | None = None
    error_type: NonEmptyString
    error_description: NonEmptyString
    timestamp: datetime = Field(default_factory=utc_now)


class FailedEvaluationAttempt(StrictModel):
    failure_id: UUID = Field(default_factory=uuid4)
    run_id: UUID
    attempt_number: Annotated[StrictInt, Field(ge=1, le=3)]
    status: Literal["FAILED"] = "FAILED"
    failure_stage: EvaluationFailureStage = EvaluationFailureStage.UNKNOWN
    error_category: EvaluationErrorCategory = EvaluationErrorCategory.EVALUATOR_ERROR
    retry_disposition: EvaluationRetryDisposition | None = None
    error_type: NonEmptyString
    error_description: NonEmptyString
    timestamp: datetime = Field(default_factory=utc_now)


class RejectionRecord(StrictModel):
    rejection_id: UUID = Field(default_factory=uuid4)
    run_id: UUID
    attempt_number: Annotated[StrictInt, Field(ge=1, le=3)]
    retry_attempt_number: Annotated[StrictInt, Field(ge=2, le=3)] | None = None
    failed_checkpoints: tuple[CheckpointId, ...] = Field(min_length=1)
    failure_reasons: dict[CheckpointId, NonEmptyString] = Field(min_length=1)
    evidence: dict[CheckpointId, NonEmptyString] = Field(min_length=1)
    correction_instructions: tuple[NonEmptyString, ...] = Field(min_length=1)
    correction_applied: StrictStr = ""
    changes_made: StrictStr = ""
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_failure_details(self) -> "RejectionRecord":
        failed = set(self.failed_checkpoints)
        if len(failed) != len(self.failed_checkpoints):
            raise ValueError("Failed checkpoint IDs must be unique.")
        if set(self.failure_reasons) != failed or set(self.evidence) != failed:
            raise ValueError(
                "Failure reasons and evidence must cover exactly the failed checkpoints."
            )
        if (
            self.retry_attempt_number is not None
            and self.retry_attempt_number <= self.attempt_number
        ):
            raise ValueError("Retry attempt number must follow the rejected attempt.")
        return self


class LearnedRule(StrictModel):
    rule_id: UUID = Field(default_factory=uuid4)
    rule_description: NonEmptyString
    rationale: NonEmptyString
    related_checkpoint: CheckpointId
    failure_count: Annotated[StrictInt, Field(ge=1)]
    confidence: Annotated[StrictFloat, Field(ge=0.0, le=1.0)]
    source_rejection_ids: tuple[UUID, ...] = Field(min_length=1)
    active_status: StrictBool = True
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_unique_source_rejections(self) -> "LearnedRule":
        if len(self.source_rejection_ids) != len(set(self.source_rejection_ids)):
            raise ValueError("Learned rule rejection IDs must be unique.")
        return self
