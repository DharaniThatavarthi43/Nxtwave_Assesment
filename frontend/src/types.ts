export type CheckpointId = "C1" | "C2" | "C3" | "C4" | "C5" | "C6";
export type CheckpointStatus = "PASS" | "FAIL";
export type RunStatus = "IN_PROGRESS" | "APPROVED" | "REJECTED" | "FAILED";
export type GenerationMode = "assessment" | "gpt" | "rag" | "demo";

export interface ExecutionRun {
  run_id: string;
  topic: string;
  status: RunStatus;
  max_retries: number;
  created_at: string;
  updated_at: string;
}

export interface Lesson {
  lesson_id: string;
  topic: string;
  title: string;
  attempt_number: number;
  sections: Record<string, string>;
  full_markdown: string;
  reference_ids: string[];
  generation_timestamp: string;
}

export interface GenerationAttempt {
  attempt_id: string;
  run_id: string;
  attempt_number: number;
  generated_lesson: Lesson;
  timestamp: string;
}

export interface EvaluationCheckpoint {
  checkpoint_id: CheckpointId;
  status: CheckpointStatus;
  reason: string;
  evidence: string;
}

export interface EvaluationResult {
  evaluation_id: string;
  run_id: string;
  attempt_number: number;
  overall_status: CheckpointStatus;
  checkpoints: EvaluationCheckpoint[];
  failed_checkpoints: CheckpointId[];
  correction_instructions: string[];
  overall_reason: string;
  evaluated_at: string;
}

export interface RejectionRecord {
  rejection_id: string;
  run_id: string;
  attempt_number: number;
  retry_attempt_number: number | null;
  failed_checkpoints: CheckpointId[];
  failure_reasons: Partial<Record<CheckpointId, string>>;
  evidence: Partial<Record<CheckpointId, string>>;
  correction_instructions: string[];
  correction_applied: string;
  changes_made: string;
  created_at: string;
}

export interface FailedEvaluationAttempt {
  failure_id: string;
  run_id: string;
  attempt_number: number;
  status: "FAILED";
  failure_stage: string;
  error_category: string;
  retry_disposition: string | null;
  error_type: string;
  error_description: string;
  timestamp: string;
}

export interface FailedGenerationAttempt {
  failure_id: string;
  run_id: string;
  attempt_number: number;
  status: "FAILED";
  failure_stage: string;
  error_category: string;
  validation_subcode: string | null;
  error_type: string;
  error_description: string;
  timestamp: string;
}

export interface ProgressEvent {
  stage: string;
  attempt_number: number | null;
  recorded_at: string;
}

export interface Artifact {
  filename: string;
  download_url: string;
}

export interface RunDetail {
  run_id: string;
  topic: string;
  mode: GenerationMode;
  max_retries: number;
  status: string;
  job_status: "queued" | "running" | "completed" | "failed" | "unknown";
  current_stage: string;
  current_attempt: number | null;
  run: ExecutionRun | null;
  attempts: GenerationAttempt[];
  evaluations: EvaluationResult[];
  feedback_sent: Record<string, string[]>;
  rejections: RejectionRecord[];
  failed_generation_attempts: FailedGenerationAttempt[];
  failed_evaluation_attempts: FailedEvaluationAttempt[];
  progress_events: ProgressEvent[];
  artifacts: Artifact[];
  output_error: string | null;
  failure_reason: string | null;
}

export interface RunSummary {
  run_id: string;
  topic: string;
  mode: GenerationMode;
  status: string;
  created_at: string;
  updated_at: string;
  attempt_count: number;
  evaluation_count: number;
  failure_reason: string | null;
}

export interface RunList {
  items: RunSummary[];
  total: number;
  offset: number;
  limit: number;
}

export interface Dashboard {
  total_executions: number;
  approved_executions: number;
  rejected_executions: number;
  failed_executions: number;
  total_generation_attempts: number;
  active_learned_rules: number;
  approval_rate: number | null;
  mean_checkpoint_pass_rate: number | null;
  checkpoint_failures: { checkpoint_id: CheckpointId; failure_count: number }[];
  executions_by_day: {
    date: string;
    approved: number;
    rejected: number;
    failed: number;
  }[];
  recent_runs: RunSummary[];
}

export interface AppSettings {
  topic: string;
  provider: string | null;
  model: string | null;
  provider_configured: boolean;
  database_connected: boolean;
  max_generation_attempts: number;
  max_generation_retries: number;
  evaluator_api_retries: number;
  evaluator_max_retry_after_seconds: number;
  mandatory_checkpoints: CheckpointId[];
  target_audience: string;
}

export interface RejectionListItem {
  rejection: RejectionRecord;
  topic: string | null;
  final_status: string | null;
  feedback_sent: string[];
  retry_attempt_status: CheckpointStatus | null;
}

export interface RejectionFailureItem {
  failure_id: string;
  run_id: string;
  topic: string | null;
  mode: GenerationMode | null;
  attempt_number: number;
  failure_kind: "generation" | "evaluation";
  failure_stage: string;
  error_category: string;
  error_type: string;
  error_description: string;
  recorded_at: string;
}

export interface RejectionLogResponse {
  items: RejectionListItem[];
  failures: RejectionFailureItem[];
}

export interface LearnedRule {
  rule: {
    rule_id: string;
    rule_description: string;
    rationale: string;
    related_checkpoint: CheckpointId;
    failure_count: number;
    confidence: number;
    source_rejection_ids: string[];
    active_status: boolean;
    created_at: string;
    updated_at: string;
  };
  distinct_supporting_runs: number;
}

export interface KnowledgeSource {
  source_id: string;
  title: string;
  url: string;
}

export interface KnowledgeDocument {
  document_id: string;
  title: string;
  source_type: "manual" | "url" | "upload";
  source_url: string | null;
  created_at: string;
  chunk_count: number;
}

export interface Knowledge {
  reference_material: {
    title: string;
    version: string;
    content: string;
    sources: KnowledgeSource[];
  };
  active: true;
}

export interface StartRunResponse {
  run_id: string;
  request_id: string;
  topic: string;
  mode: GenerationMode;
  job_status: string;
  duplicate_request: boolean;
}

export interface ApprovedNote {
  run_id: string;
  topic: string;
  mode: GenerationMode;
  title: string;
  created_at: string;
  evaluation_status: "APPROVED";
  full_markdown: string;
}

export type ApprovedNoteSummary = Omit<ApprovedNote, "full_markdown">;

export interface KnowledgeSearchResult {
  document_id: string;
  title: string;
  chunk_index: number;
  content: string;
}
