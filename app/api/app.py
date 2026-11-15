import logging
import os
import re
import sqlite3
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import AsyncIterator
from uuid import UUID, uuid4

from fastapi import FastAPI, File, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.api.schemas import (
    ApprovedNoteResponse,
    ApprovedNoteSummary,
    ApiHealthResponse,
    ArtifactResponse,
    DashboardResponse,
    KnowledgeResponse,
    LearnedRuleResponse,
    NoteListResponse,
    ProgressEventResponse,
    RejectionListItem,
    RunDetailResponse,
    RunListResponse,
    SettingsResponse,
    StartRunRequest,
    StartRunResponse,
)
from app.api.service import (
    database_is_available,
    find_output_directory,
    get_dashboard,
    list_runs,
)
from app.config import (
    DEFAULT_TOPIC,
    MAX_ALLOWED_RETRIES,
    PROJECT_ROOT,
    ConfigurationError,
    Settings,
    load_settings,
)
from app.knowledge.knowledge_base import KnowledgeBaseManager
from app.knowledge.reference_loader import ReferenceLoadError, load_reference_material
from app.memory.memory_manager import MemoryManager
from app.schemas import (
    CheckpointId,
    EvaluationResult,
    ExecutionRun,
    RunStatus,
)
from app.services.output_service import (
    OutputGenerationError,
    generate_execution_outputs,
)
from app.workflow import (
    WorkflowExecutionError,
    WorkflowPersistenceError,
    WorkflowProgress,
    WorkflowResult,
    build_evaluation_feedback,
    run_lesson_workflow,
)


logger = logging.getLogger(__name__)
LOCAL_FRONTEND_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)


def _configured_frontend_origins() -> list[str]:
    """Use explicit UI origins in deployments, with local Vite defaults."""
    configured = os.getenv("FRONTEND_ORIGINS", "")
    origins = [
        origin.strip().rstrip("/")
        for origin in configured.split(",")
        if origin.strip()
    ]
    return origins or list(LOCAL_FRONTEND_ORIGINS)
APPROVED_OUTPUT_FILENAMES = frozenset(
    {
        "final_lesson.md",
        "evaluation_report.md",
        "execution_summary.md",
        "attempt_history.md",
        "learned_rules.md",
    }
)
REJECTED_OUTPUT_FILENAMES = frozenset(
    {
        "rejected_lesson.md",
        "evaluation_report.md",
        "execution_summary.md",
        "attempt_history.md",
        "rejection_log.md",
        "learned_rules.md",
    }
)
TARGET_AUDIENCE = (
    "Indian students who have completed 12th standard, have limited English "
    "vocabulary, and have no AI background."
)


@dataclass
class _RunJob:
    run_id: UUID
    request_id: UUID
    topic: str
    mode: str = "assessment"
    max_retries: int = 2
    knowledge_base_id: UUID | None = None
    job_status: str = "queued"
    current_stage: str = "queued"
    current_attempt: int | None = None
    progress_events: list[ProgressEventResponse] = field(default_factory=list)
    artifact_filenames: tuple[str, ...] = ()
    output_error: str | None = None
    failure_reason: str | None = None
    future: Future[None] | None = None


@dataclass
class _Runtime:
    settings: Settings
    memory: MemoryManager
    knowledge_base: KnowledgeBaseManager
    output_root: Path
    executor: ThreadPoolExecutor
    workflow_runner: Callable[..., WorkflowResult]
    output_generator: Callable[..., object]
    jobs_by_run: dict[UUID, _RunJob] = field(default_factory=dict)
    run_by_request: dict[UUID, UUID] = field(default_factory=dict)
    lock: RLock = field(default_factory=RLock)


def create_app(
    *,
    settings: Settings | None = None,
    output_root: Path | None = None,
    workflow_runner: Callable[..., WorkflowResult] | None = None,
    output_generator: Callable[..., object] | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        current_settings = settings if settings is not None else load_settings()
        try:
            memory = MemoryManager(current_settings.database_path)
        except (OSError, sqlite3.Error) as exc:
            logger.error(
                "API persistence initialization failed (%s).",
                _safe_exception_name(exc),
            )
            raise RuntimeError(
                "The API could not initialize its persistent storage."
            ) from exc
        runtime = _Runtime(
            settings=current_settings,
            memory=memory,
            knowledge_base=KnowledgeBaseManager(current_settings.database_path),
            output_root=(
                output_root.expanduser().resolve()
                if output_root is not None
                else (PROJECT_ROOT / "outputs").resolve()
            ),
            executor=ThreadPoolExecutor(
                max_workers=2,
                thread_name_prefix="lesson-run",
            ),
            workflow_runner=workflow_runner or run_lesson_workflow,
            output_generator=output_generator or generate_execution_outputs,
        )
        application.state.runtime = runtime
        try:
            yield
        finally:
            runtime.executor.shutdown(wait=False, cancel_futures=True)

    application = FastAPI(
        title="Self-Evaluating Lesson Content Generator",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url=None,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=_configured_frontend_origins(),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @application.get("/api/health", response_model=ApiHealthResponse)
    def health(request: Request) -> ApiHealthResponse:
        runtime = _runtime(request)
        connected = database_is_available(runtime.settings.database_path)
        return ApiHealthResponse(
            status="ok" if connected else "degraded",
            database_connected=connected,
        )

    @application.get("/api/config", response_model=SettingsResponse)
    def get_settings(request: Request) -> SettingsResponse:
        runtime = _runtime(request)
        current = runtime.settings
        return SettingsResponse(
            topic=DEFAULT_TOPIC,
            provider=current.llm_provider,
            model=current.llm_model,
            provider_configured=all(
                (current.llm_provider, current.llm_model, current.llm_api_key)
            ),
            database_connected=database_is_available(current.database_path),
            max_generation_attempts=min(
                current.max_retries + 1,
                MAX_ALLOWED_RETRIES + 1,
            ),
            max_generation_retries=current.max_retries,
            evaluator_api_retries=2,
            evaluator_max_retry_after_seconds=(
                current.evaluator_max_retry_after_seconds
            ),
            mandatory_checkpoints=tuple(CheckpointId),
            target_audience=TARGET_AUDIENCE,
        )

    @application.get("/api/dashboard", response_model=DashboardResponse)
    def dashboard(request: Request) -> DashboardResponse:
        runtime = _runtime(request)
        try:
            active_rules = runtime.memory.get_active_rules()
            return get_dashboard(
                runtime.settings.database_path,
                active_rule_count=len(active_rules),
            )
        except (OSError, sqlite3.Error) as exc:
            logger.error("Dashboard query failed (%s).", _safe_exception_name(exc))
            raise HTTPException(
                status_code=503,
                detail="Dashboard data is temporarily unavailable.",
            ) from exc

    @application.get("/api/runs", response_model=RunListResponse)
    def history(
        request: Request,
        q: str | None = Query(default=None, max_length=120),
        status_filter: RunStatus | None = Query(default=None, alias="status"),
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=25, ge=1, le=100),
    ) -> RunListResponse:
        runtime = _runtime(request)
        try:
            return list_runs(
                runtime.settings.database_path,
                query=q,
                status=status_filter,
                offset=offset,
                limit=limit,
            )
        except (OSError, sqlite3.Error) as exc:
            logger.error("Run history query failed (%s).", _safe_exception_name(exc))
            raise HTTPException(
                status_code=503,
                detail="Execution history is temporarily unavailable.",
            ) from exc

    @application.post(
        "/api/runs",
        response_model=StartRunResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    def start_run(
        payload: StartRunRequest,
        request: Request,
        response: Response,
    ) -> StartRunResponse:
        runtime = _runtime(request)
        if payload.mode == "rag":
            try:
                if payload.knowledge_base_id is not None:
                    runtime.knowledge_base.build_reference_material_for_document(
                        document_id=payload.knowledge_base_id,
                        query=payload.topic,
                    )
                else:
                    runtime.knowledge_base.build_reference_material(
                        query=payload.topic,
                    )
            except ValueError as exc:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "RAG needs a selected knowledge-base document with matching "
                        "content. Add a source or choose another document."
                    ),
                ) from exc
        configured = (
            runtime.settings.llm_provider,
            runtime.settings.llm_model,
            runtime.settings.llm_api_key,
        )
        if not all(configured):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Configure the backend LLM provider before starting a run.",
            )

        with runtime.lock:
            existing_run_id = runtime.run_by_request.get(payload.request_id)
            if existing_run_id is not None:
                existing_job = runtime.jobs_by_run[existing_run_id]
                if existing_job.topic.casefold() != payload.topic.casefold():
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="This request ID was already used for a different topic.",
                    )
                if (
                    existing_job.mode != payload.mode
                    or existing_job.knowledge_base_id != payload.knowledge_base_id
                    or existing_job.max_retries != MAX_ALLOWED_RETRIES
                ):
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="This request ID was already used for a different generation configuration.",
                    )
                response.status_code = status.HTTP_200_OK
                return _start_response(existing_job, duplicate=True)

            job = _RunJob(
                run_id=uuid4(),
                request_id=payload.request_id,
                topic=payload.topic,
                mode=payload.mode,
                max_retries=MAX_ALLOWED_RETRIES,
                knowledge_base_id=payload.knowledge_base_id,
            )
            job.progress_events.append(
                ProgressEventResponse(
                    stage="queued",
                    recorded_at=datetime.now(timezone.utc),
                )
            )
            runtime.jobs_by_run[job.run_id] = job
            runtime.run_by_request[payload.request_id] = job.run_id
            try:
                job.future = runtime.executor.submit(
                    _execute_run,
                    runtime,
                    job,
                )
            except RuntimeError as exc:
                runtime.jobs_by_run.pop(job.run_id, None)
                runtime.run_by_request.pop(payload.request_id, None)
                logger.error("Run queue unavailable (%s).", _safe_exception_name(exc))
                raise HTTPException(
                    status_code=503,
                    detail="The workflow runner is temporarily unavailable.",
                ) from exc

        return _start_response(job)

    @application.get("/api/studio/knowledge-base")
    def studio_knowledge_base(request: Request) -> dict[str, object]:
        runtime = _runtime(request)
        documents = runtime.knowledge_base.list_documents()
        return {
            "documents": [
                {
                    "document_id": str(document.document_id),
                    "title": document.title,
                    "source_type": document.source_type,
                    "source_url": document.source_url,
                    "created_at": document.created_at.isoformat(),
                    "chunk_count": len(runtime.knowledge_base.retrieve(" ".join(document.content.split()[:8]), limit=1)),
                }
                for document in documents
            ],
            "total_documents": len(documents),
        }

    @application.post("/api/studio/knowledge-base/url")
    async def add_knowledge_url(request: Request) -> dict[str, object]:
        runtime = _runtime(request)
        payload = await request.json()
        value = str(payload.get("url", "")).strip()
        if not value:
            raise HTTPException(status_code=400, detail="A webpage URL is required.")
        try:
            document = runtime.knowledge_base.ingest_url(value)
        except (ValueError, OSError, Exception) as exc:
            logger.error("Knowledge-base URL ingestion failed (%s).", _safe_exception_name(exc))
            raise HTTPException(
                status_code=400,
                detail="The supplied URL could not be ingested into the knowledge base.",
            ) from exc
        return {
            "document_id": str(document.document_id),
            "title": document.title,
            "source_type": document.source_type,
            "source_url": document.source_url,
        }

    @application.post("/api/studio/knowledge-base/upload")
    async def upload_knowledge_document(
        request: Request,
        file: UploadFile = File(...),
    ) -> dict[str, object]:
        runtime = _runtime(request)
        filename = file.filename or "uploaded-document"
        raw = await file.read()
        try:
            content = runtime.knowledge_base._read_upload_bytes(filename, raw)
            document = runtime.knowledge_base.ingest_upload(
                filename=filename,
                content=content,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "document_id": str(document.document_id),
            "title": document.title,
            "source_type": document.source_type,
        }

    @application.post("/api/studio/knowledge-base/search")
    async def search_knowledge_base(request: Request) -> dict[str, object]:
        runtime = _runtime(request)
        payload = await request.json()
        query = str(payload.get("query", "")).strip()
        if not query:
            raise HTTPException(status_code=400, detail="A search query is required.")
        rows = runtime.knowledge_base.retrieve(query, limit=5)
        document_map = {document.document_id: document for document in runtime.knowledge_base.list_documents()}
        results = []
        for chunk in rows:
            document = document_map.get(chunk.document_id)
            if document is None:
                continue
            results.append(
                {
                    "document_id": str(document.document_id),
                    "title": document.title,
                    "chunk_index": chunk.chunk_index,
                    "content": chunk.content,
                }
            )
        return {"query": query, "results": results}

    @application.get("/api/runs/{run_id}", response_model=RunDetailResponse)
    def run_detail(run_id: UUID, request: Request) -> RunDetailResponse:
        runtime = _runtime(request)
        try:
            return _run_detail(runtime, run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Execution not found.") from exc
        except (OSError, sqlite3.Error) as exc:
            logger.error("Execution query failed (%s).", _safe_exception_name(exc))
            raise HTTPException(
                status_code=503,
                detail="Execution details are temporarily unavailable.",
            ) from exc

    @application.get("/api/notes", response_model=NoteListResponse)
    def list_approved_notes(request: Request) -> NoteListResponse:
        runtime = _runtime(request)
        try:
            notes = runtime.memory.get_approved_notes()
        except (OSError, sqlite3.Error) as exc:
            logger.error("Approved notes query failed (%s).", _safe_exception_name(exc))
            raise HTTPException(
                status_code=503,
                detail="Approved notes are temporarily unavailable.",
            ) from exc
        return NoteListResponse(
            items=tuple(
                ApprovedNoteSummary.model_validate(
                    note.model_dump(exclude={"full_markdown"})
                )
                for note in notes
            ),
            total=len(notes),
        )

    @application.get(
        "/api/notes/{run_id}/download",
        response_class=Response,
    )
    def download_approved_note(
        run_id: UUID,
        request: Request,
        format: str = Query(default="md", pattern="^(md|txt)$"),
    ) -> Response:
        runtime = _runtime(request)
        try:
            note = runtime.memory.get_approved_note(run_id)
        except (OSError, sqlite3.Error) as exc:
            logger.error("Approved note download failed (%s).", _safe_exception_name(exc))
            raise HTTPException(
                status_code=503,
                detail="The approved note is temporarily unavailable.",
            ) from exc
        if note is None:
            raise HTTPException(status_code=404, detail="Approved note not found.")
        extension = format
        media_type = "text/markdown; charset=utf-8" if format == "md" else "text/plain; charset=utf-8"
        return Response(
            content=note.full_markdown,
            media_type=media_type,
            headers={
                "Content-Disposition": (
                    f'attachment; filename="lesson-{note.run_id}.{extension}"'
                )
            },
        )

    @application.get(
        "/api/notes/{run_id}",
        response_model=ApprovedNoteResponse,
    )
    def get_approved_note(run_id: UUID, request: Request) -> ApprovedNoteResponse:
        runtime = _runtime(request)
        try:
            note = runtime.memory.get_approved_note(run_id)
        except (OSError, sqlite3.Error) as exc:
            logger.error("Approved note query failed (%s).", _safe_exception_name(exc))
            raise HTTPException(
                status_code=503,
                detail="The approved note is temporarily unavailable.",
            ) from exc
        if note is None:
            raise HTTPException(status_code=404, detail="Approved note not found.")
        return ApprovedNoteResponse.model_validate(note.model_dump())

    @application.get("/api/rejections", response_model=tuple[RejectionListItem, ...])
    def rejections(
        request: Request,
        run_id: UUID | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> tuple[RejectionListItem, ...]:
        runtime = _runtime(request)
        try:
            records = (
                runtime.memory.get_rejections(run_id)
                if run_id is not None
                else runtime.memory.get_previous_failures()
            )
            records.sort(key=lambda item: (item.created_at, str(item.rejection_id)))
            evaluations_by_run: dict[UUID, dict[int, EvaluationResult]] = {}
            items = []
            for record in records[:limit]:
                run = runtime.memory.get_run(record.run_id)
                if record.run_id not in evaluations_by_run:
                    evaluations_by_run[record.run_id] = {
                        evaluation.attempt_number: evaluation
                        for evaluation in runtime.memory.get_evaluation_history(
                            record.run_id
                        )
                    }
                evaluations = evaluations_by_run[record.run_id]
                rejection_evaluation = evaluations.get(record.attempt_number)
                retry_evaluation = (
                    evaluations.get(record.retry_attempt_number)
                    if record.retry_attempt_number is not None
                    else None
                )
                items.append(
                    RejectionListItem(
                        rejection=record,
                        topic=run.topic if run is not None else None,
                        final_status=run.status.value if run is not None else None,
                        feedback_sent=(
                            build_evaluation_feedback(rejection_evaluation)
                            if record.retry_attempt_number is not None
                            and rejection_evaluation is not None
                            else ()
                        ),
                        retry_attempt_status=(
                            retry_evaluation.overall_status
                            if retry_evaluation is not None
                            else None
                        ),
                    )
                )
            return tuple(items)
        except (OSError, sqlite3.Error) as exc:
            logger.error("Rejection query failed (%s).", _safe_exception_name(exc))
            raise HTTPException(
                status_code=503,
                detail="Rejection history is temporarily unavailable.",
            ) from exc

    @application.get(
        "/api/learning/rules",
        response_model=tuple[LearnedRuleResponse, ...],
    )
    def learned_rules(request: Request) -> tuple[LearnedRuleResponse, ...]:
        runtime = _runtime(request)
        try:
            return tuple(
                LearnedRuleResponse(
                    rule=rule,
                    distinct_supporting_runs=rule.failure_count,
                )
                for rule in runtime.memory.get_learned_rules()
            )
        except (OSError, sqlite3.Error) as exc:
            logger.error("Learned-rule query failed (%s).", _safe_exception_name(exc))
            raise HTTPException(
                status_code=503,
                detail="Learned rules are temporarily unavailable.",
            ) from exc

    @application.get("/api/knowledge", response_model=KnowledgeResponse)
    def knowledge() -> KnowledgeResponse:
        try:
            return KnowledgeResponse(reference_material=load_reference_material())
        except ReferenceLoadError as exc:
            logger.error("Curated reference material is unavailable.")
            raise HTTPException(
                status_code=503,
                detail="Curated reference material is unavailable.",
            ) from exc

    @application.get("/api/runs/{run_id}/artifacts")
    def list_artifacts(run_id: UUID, request: Request) -> tuple[ArtifactResponse, ...]:
        runtime = _runtime(request)
        run = runtime.memory.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Execution not found.")
        directory = find_output_directory(runtime.output_root, run_id)
        if directory is None or run.status not in {RunStatus.APPROVED, RunStatus.REJECTED}:
            return ()
        allowed = (
            APPROVED_OUTPUT_FILENAMES
            if run.status is RunStatus.APPROVED
            else REJECTED_OUTPUT_FILENAMES
        )
        return tuple(
            ArtifactResponse(
                filename=filename,
                download_url=f"/api/runs/{run_id}/artifacts/{filename}",
            )
            for filename in sorted(allowed)
            if (directory / filename).is_file()
        )

    @application.get("/api/runs/{run_id}/artifacts/{filename}")
    def download_artifact(
        run_id: UUID,
        filename: str,
        request: Request,
    ) -> FileResponse:
        runtime = _runtime(request)
        run = runtime.memory.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Execution not found.")
        directory = find_output_directory(runtime.output_root, run_id)
        if directory is None:
            raise HTTPException(status_code=404, detail="Output artifact not found.")
        allowed = (
            APPROVED_OUTPUT_FILENAMES
            if run.status is RunStatus.APPROVED
            else REJECTED_OUTPUT_FILENAMES
            if run.status is RunStatus.REJECTED
            else frozenset()
        )
        if filename not in allowed:
            raise HTTPException(status_code=404, detail="Output artifact not found.")
        artifact = directory / filename
        if not artifact.is_file() or artifact.resolve().parent != directory:
            raise HTTPException(status_code=404, detail="Output artifact not found.")
        return FileResponse(
            artifact,
            media_type="text/markdown; charset=utf-8",
            filename=filename,
        )

    return application


def _runtime(request: Request) -> _Runtime:
    runtime = getattr(request.app.state, "runtime", None)
    if not isinstance(runtime, _Runtime):
        raise HTTPException(
            status_code=503,
            detail="The API application is not ready.",
        )
    return runtime


def _start_response(
    job: _RunJob,
    *,
    duplicate: bool = False,
) -> StartRunResponse:
    return StartRunResponse(
        run_id=job.run_id,
        request_id=job.request_id,
        topic=job.topic,
        mode=job.mode,
        max_retries=job.max_retries,
        job_status=job.job_status,
        duplicate_request=duplicate,
    )


def _execute_run(runtime: _Runtime, job: _RunJob) -> None:
    with runtime.lock:
        job.job_status = "running"
        job.current_stage = "starting"
        job.progress_events.append(
            ProgressEventResponse(
                stage="starting",
                recorded_at=datetime.now(timezone.utc),
            )
        )

    def record_progress(event: WorkflowProgress) -> None:
        with runtime.lock:
            job.current_stage = event.stage
            job.current_attempt = event.attempt_number
            job.progress_events.append(
                ProgressEventResponse(
                    stage=event.stage,
                    attempt_number=event.attempt_number,
                    recorded_at=datetime.now(timezone.utc),
                )
            )

    try:
        result = runtime.workflow_runner(
            topic=job.topic,
            memory_manager=runtime.memory,
            settings=runtime.settings,
            run_id=job.run_id,
            progress_callback=record_progress,
            mode=job.mode,
            max_retries=job.max_retries,
            knowledge_base_id=job.knowledge_base_id,
            knowledge_base_manager=runtime.knowledge_base,
            )
    except WorkflowExecutionError:
        with runtime.lock:
            job.job_status = "failed"
            job.current_stage = "failed"
            job.failure_reason = "The lesson workflow failed; see safe run diagnostics."
        return
    except (WorkflowPersistenceError, ConfigurationError, ReferenceLoadError):
        _mark_failed(runtime, job)
        return
    except Exception as exc:
        logger.error(
            "Background run %s failed (%s).",
            job.run_id,
            _safe_exception_name(exc),
        )
        _mark_failed(runtime, job)
        return

    try:
        artifacts = runtime.output_generator(
            result,
            runtime.memory,
            output_root=runtime.output_root,
        )
        artifact_filenames = tuple(path.name for path in artifacts.files)
    except OutputGenerationError:
        artifact_filenames = ()
        with runtime.lock:
            job.output_error = (
                "The decision was saved, but report files could not be generated."
            )
    except Exception as exc:
        logger.error(
            "Output generation for run %s failed (%s).",
            job.run_id,
            _safe_exception_name(exc),
        )
        artifact_filenames = ()
        with runtime.lock:
            job.output_error = (
                "The decision was saved, but report files could not be generated."
            )

    with runtime.lock:
        job.artifact_filenames = artifact_filenames
        job.job_status = "completed"
        job.current_stage = result.run.status.value.casefold()


def _mark_failed(runtime: _Runtime, job: _RunJob) -> None:
    try:
        run = runtime.memory.get_run(job.run_id)
        if run is not None and run.status is RunStatus.IN_PROGRESS:
            runtime.memory.update_run_status(job.run_id, RunStatus.FAILED)
    except (OSError, sqlite3.Error):
        logger.error("Unable to persist failed status for run %s.", job.run_id)
    with runtime.lock:
        job.job_status = "failed"
        job.current_stage = "failed"
        job.failure_reason = (
            "The workflow stopped because of an application or persistence error."
        )


def _run_detail(runtime: _Runtime, run_id: UUID) -> RunDetailResponse:
    run = runtime.memory.get_run(run_id)
    with runtime.lock:
        job = runtime.jobs_by_run.get(run_id)
        if job is not None:
            topic = job.topic
            job_status = job.job_status
            stage = job.current_stage
            current_attempt = job.current_attempt
            progress_events = tuple(job.progress_events)
            output_error = job.output_error
            failure_reason = job.failure_reason
        else:
            topic = run.topic if run is not None else ""
            if run is None:
                raise KeyError(run_id)
            job_status = (
                "completed"
                if run.status in {RunStatus.APPROVED, RunStatus.REJECTED}
                else "failed"
                if run.status is RunStatus.FAILED
                else "unknown"
            )
            stage = run.status.value.casefold()
            current_attempt = None
            progress_events = ()
            output_error = None
            failure_reason = None

    if run is None:
        return RunDetailResponse(
            run_id=run_id,
            topic=topic,
            mode=job.mode if job is not None else "assessment",
            max_retries=job.max_retries if job is not None else runtime.settings.max_retries,
            status="FAILED" if job_status == "failed" else "IN_PROGRESS",
            job_status=job_status,
            current_stage=stage,
            current_attempt=current_attempt,
            progress_events=progress_events,
            output_error=output_error,
            failure_reason=failure_reason,
        )

    attempts = tuple(runtime.memory.get_attempt_history(run_id))
    evaluations = tuple(runtime.memory.get_evaluation_history(run_id))
    rejections = tuple(runtime.memory.get_rejections(run_id))
    failed_generations = tuple(runtime.memory.get_failed_generation_attempts(run_id))
    failed_evaluations = tuple(runtime.memory.get_failed_evaluation_attempts(run_id))
    subsequent_generation_numbers = {
        item.attempt_number
        for item in (*attempts, *failed_generations)
    }
    feedback_sent = {
        evaluation.attempt_number: build_evaluation_feedback(evaluation)
        for evaluation in evaluations
        if evaluation.failed_checkpoints
        and any(
            attempt_number > evaluation.attempt_number
            for attempt_number in subsequent_generation_numbers
        )
    }

    if failure_reason is None:
        diagnostics = [
            item.error_description
            for item in (*failed_generations, *failed_evaluations)
        ]
        failure_reason = diagnostics[-1] if diagnostics else None

    directory = find_output_directory(runtime.output_root, run_id)
    artifact_names = ()
    if directory is not None and run.status in {
        RunStatus.APPROVED,
        RunStatus.REJECTED,
    }:
        allowed = (
            APPROVED_OUTPUT_FILENAMES
            if run.status is RunStatus.APPROVED
            else REJECTED_OUTPUT_FILENAMES
        )
        artifact_names = tuple(
            filename for filename in sorted(allowed) if (directory / filename).is_file()
        )
    artifacts = tuple(
        ArtifactResponse(
            filename=filename,
            download_url=f"/api/runs/{run_id}/artifacts/{filename}",
        )
        for filename in artifact_names
    )
    return RunDetailResponse(
        run_id=run_id,
        topic=run.topic,
        mode=run.mode,
        max_retries=run.max_retries,
        status=run.status.value,
        job_status=job_status,
        current_stage=stage,
        current_attempt=current_attempt,
        run=run,
        attempts=attempts,
        evaluations=evaluations,
        feedback_sent=feedback_sent,
        rejections=rejections,
        failed_generation_attempts=failed_generations,
        failed_evaluation_attempts=failed_evaluations,
        progress_events=progress_events,
        artifacts=artifacts,
        output_error=output_error,
        failure_reason=failure_reason,
    )


def _safe_exception_name(error: Exception) -> str:
    name = type(error).__name__
    return name if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", name) else "Exception"


app = create_app()


