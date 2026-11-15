from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator

from app.schemas import (
    CheckpointId,
    CheckpointStatus,
    EvaluationResult,
    ExecutionRun,
    FailedEvaluationAttempt,
    FailedGenerationAttempt,
    GenerationAttempt,
    LearnedRule,
    ReferenceMaterial,
    RejectionRecord,
)

GenerationMode = Literal["gpt", "rag"]
PersistedGenerationMode = Literal["assessment", "gpt", "rag", "demo"]


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StartRunRequest(ApiModel):
    mode: GenerationMode
    request_id: UUID
    topic: StrictStr = Field(min_length=1, max_length=120)
    knowledge_base_id: UUID | None = None
    max_retries: int = Field(default=2, ge=0, le=2)

    @field_validator("topic")
    @classmethod
    def validate_topic(cls, value: str, info: object) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Topic must not be blank.")
        return normalized



class StartRunResponse(ApiModel):
    run_id: UUID
    request_id: UUID
    topic: str
    mode: PersistedGenerationMode
    max_retries: int = 2
    job_status: Literal["queued", "running", "completed", "failed", "unknown"]
    duplicate_request: bool = False


class ProgressEventResponse(ApiModel):
    stage: str
    attempt_number: int | None = None
    recorded_at: datetime


class ArtifactResponse(ApiModel):
    filename: str
    download_url: str


class RunDetailResponse(ApiModel):
    run_id: UUID
    topic: str
    mode: PersistedGenerationMode
    max_retries: int = 2
    status: str
    job_status: Literal["queued", "running", "completed", "failed", "unknown"]
    current_stage: str
    current_attempt: int | None = None
    run: ExecutionRun | None = None
    attempts: tuple[GenerationAttempt, ...] = ()
    evaluations: tuple[EvaluationResult, ...] = ()
    feedback_sent: dict[int, tuple[str, ...]] = Field(default_factory=dict)
    rejections: tuple[RejectionRecord, ...] = ()
    failed_generation_attempts: tuple[FailedGenerationAttempt, ...] = ()
    failed_evaluation_attempts: tuple[FailedEvaluationAttempt, ...] = ()
    progress_events: tuple[ProgressEventResponse, ...] = ()
    artifacts: tuple[ArtifactResponse, ...] = ()
    output_error: str | None = None
    failure_reason: str | None = None


class RunSummaryResponse(ApiModel):
    run_id: UUID
    topic: str
    mode: PersistedGenerationMode
    status: str
    created_at: datetime
    updated_at: datetime
    attempt_count: int
    evaluation_count: int
    failure_reason: str | None = None


class RunListResponse(ApiModel):
    items: tuple[RunSummaryResponse, ...]
    total: int
    offset: int
    limit: int


class CheckpointFailureCount(ApiModel):
    checkpoint_id: CheckpointId
    failure_count: int


class DailyRunCount(ApiModel):
    date: str
    approved: int
    rejected: int
    failed: int


class DashboardResponse(ApiModel):
    total_executions: int
    approved_executions: int
    rejected_executions: int
    failed_executions: int
    total_generation_attempts: int
    active_learned_rules: int
    approval_rate: float | None
    mean_checkpoint_pass_rate: float | None
    checkpoint_failures: tuple[CheckpointFailureCount, ...]
    executions_by_day: tuple[DailyRunCount, ...]
    recent_runs: tuple[RunSummaryResponse, ...]


class SettingsResponse(ApiModel):
    topic: str
    provider: str | None
    model: str | None
    provider_configured: bool
    database_connected: bool
    max_generation_attempts: int
    max_generation_retries: int
    evaluator_api_retries: int
    evaluator_max_retry_after_seconds: int
    mandatory_checkpoints: tuple[CheckpointId, ...]
    target_audience: str


class ApiHealthResponse(ApiModel):
    status: Literal["ok", "degraded"]
    database_connected: bool


class RejectionListItem(ApiModel):
    rejection: RejectionRecord
    topic: str | None
    final_status: str | None
    feedback_sent: tuple[str, ...] = ()
    retry_attempt_status: CheckpointStatus | None = None


class LearnedRuleResponse(ApiModel):
    rule: LearnedRule
    distinct_supporting_runs: int


class KnowledgeResponse(ApiModel):
    reference_material: ReferenceMaterial
    active: Literal[True] = True


class ApprovedNoteResponse(ApiModel):
    run_id: UUID
    topic: str
    mode: PersistedGenerationMode
    title: str
    created_at: datetime
    evaluation_status: Literal["APPROVED"]
    full_markdown: str


class ApprovedNoteSummary(ApiModel):
    run_id: UUID
    topic: str
    mode: PersistedGenerationMode
    title: str
    created_at: datetime
    evaluation_status: Literal["APPROVED"]


class NoteListResponse(ApiModel):
    items: tuple[ApprovedNoteSummary, ...]
    total: int
