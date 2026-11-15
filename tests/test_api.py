import time
from pathlib import Path
from threading import Lock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.config import DEFAULT_TOPIC, Settings
from app.schemas import (
    CheckpointId,
    CheckpointStatus,
    EvaluationCheckpoint,
    EvaluationResult,
    Lesson,
)
from app.workflow import run_lesson_workflow


def make_settings(
    database_path: Path,
    *,
    api_key: str = "test-api-key-do-not-expose",
) -> Settings:
    return Settings(
        app_env="test",
        log_level="INFO",
        database_path=database_path,
        max_retries=2,
        llm_provider="groq",
        llm_model="test-model",
        llm_api_key=api_key,
    )


def make_unconfigured_settings(
    database_path: Path,
    *,
    max_retries: int = 2,
) -> Settings:
    return Settings(
        app_env="test",
        log_level="INFO",
        database_path=database_path,
        max_retries=max_retries,
    )


def make_lesson(attempt_number: int) -> Lesson:
    content = f"RAG uses retrieved information. Version {attempt_number}. [R1]"
    return Lesson(
        topic=DEFAULT_TOPIC,
        title=f"RAG lesson {attempt_number}",
        attempt_number=attempt_number,
        sections={"Introduction": content},
        full_markdown=f"# RAG\n\n## Introduction\n\n{content}",
        reference_ids=("R1",),
    )


def make_successful_runner(call_counter: list[int] | None = None):
    counter_lock = Lock()

    def runner(**kwargs):
        if call_counter is not None:
            with counter_lock:
                call_counter.append(1)

        def generator(**generation_kwargs):
            return make_lesson(generation_kwargs["attempt_number"])

        def evaluator(**evaluation_kwargs):
            lesson = evaluation_kwargs["lesson"]
            return EvaluationResult(
                run_id=evaluation_kwargs["run_id"],
                attempt_number=lesson.attempt_number,
                overall_status=CheckpointStatus.PASS,
                checkpoints=tuple(
                    EvaluationCheckpoint(
                        checkpoint_id=checkpoint_id,
                        status=CheckpointStatus.PASS,
                        reason=f"The lesson meets the requirement for {checkpoint_id.value}.",
                        evidence=lesson.sections["Introduction"],
                    )
                    for checkpoint_id in CheckpointId
                ),
                failed_checkpoints=(),
                correction_instructions=(),
                overall_reason="All six mandatory checkpoints passed.",
            )

        return run_lesson_workflow(
            **kwargs,
            generator_fn=generator,
            evaluator_fn=evaluator,
        )

    return runner


def make_rejected_runner():
    def generator(**generation_kwargs):
        return make_lesson(generation_kwargs["attempt_number"])

    def evaluator(**evaluation_kwargs):
        lesson = evaluation_kwargs["lesson"]
        checkpoints = tuple(
            EvaluationCheckpoint(
                checkpoint_id=checkpoint_id,
                status=(
                    CheckpointStatus.FAIL
                    if checkpoint_id is CheckpointId.ACCURACY_AND_GROUNDING
                    else CheckpointStatus.PASS
                ),
                reason=f"Scripted rejection for {checkpoint_id.value}.",
                evidence=lesson.sections["Introduction"],
            )
            for checkpoint_id in CheckpointId
        )
        return EvaluationResult(
            run_id=evaluation_kwargs["run_id"],
            attempt_number=lesson.attempt_number,
            overall_status=CheckpointStatus.FAIL,
            checkpoints=checkpoints,
            failed_checkpoints=(CheckpointId.ACCURACY_AND_GROUNDING,),
            correction_instructions=("C1: Correct the factual claim.",),
            overall_reason="The C1 checkpoint failed.",
        )

    def runner(**kwargs):
        return run_lesson_workflow(
            **kwargs,
            generator_fn=generator,
            evaluator_fn=evaluator,
        )

    return runner


def make_mismatched_evaluator_runner():
    def evaluator(**kwargs):
        lesson = kwargs["lesson"]
        return EvaluationResult(
            run_id=uuid4(),
            attempt_number=lesson.attempt_number,
            overall_status=CheckpointStatus.PASS,
            checkpoints=tuple(
                EvaluationCheckpoint(
                    checkpoint_id=checkpoint_id,
                    status=CheckpointStatus.PASS,
                    reason=f"The lesson meets the requirement for {checkpoint_id.value}.",
                    evidence=lesson.sections["Introduction"],
                )
                for checkpoint_id in CheckpointId
            ),
            failed_checkpoints=(),
            correction_instructions=(),
            overall_reason="All six mandatory checkpoints passed.",
        )

    def runner(**kwargs):
        return run_lesson_workflow(
            **kwargs,
            generator_fn=lambda **generation_kwargs: make_lesson(
                generation_kwargs["attempt_number"]
            ),
            evaluator_fn=evaluator,
        )

    return runner


def wait_for_status(client: TestClient, run_id: str) -> dict:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        response = client.get(f"/api/runs/{run_id}")
        assert response.status_code == 200
        data = response.json()
        if data["job_status"] in {"completed", "failed"}:
            return data
        time.sleep(0.01)
    raise AssertionError("The mocked background run did not finish in time.")


def test_api_health_settings_and_knowledge_are_safe(tmp_path: Path) -> None:
    secret = "never-return-this-test-key"
    application = create_app(
        settings=make_settings(tmp_path / "api.sqlite3", api_key=secret),
        output_root=tmp_path / "outputs",
    )
    with TestClient(application) as client:
        assert client.get("/api/health").json() == {
            "status": "ok",
            "database_connected": True,
        }
        config = client.get("/api/config")
        assert config.status_code == 200
        assert config.json()["provider"] == "groq"
        assert config.json()["model"] == "test-model"
        assert config.json()["max_generation_attempts"] == 3
        assert len(config.json()["mandatory_checkpoints"]) == 6
        assert secret not in config.text
        knowledge = client.get("/api/knowledge")
        assert knowledge.status_code == 200
        assert knowledge.json()["reference_material"]["sources"]


def test_api_rejects_non_assessment_topics(tmp_path: Path) -> None:
    application = create_app(
        settings=make_settings(tmp_path / "api.sqlite3"),
        output_root=tmp_path / "outputs",
    )
    with TestClient(application) as client:
        response = client.post(
            "/api/runs",
            json={"request_id": str(uuid4()), "topic": "Unrelated subject"},
        )

    assert response.status_code == 422
    assert "Introduction to RAG" in response.text


def test_api_run_is_backgrounded_deduplicated_and_persisted(
    tmp_path: Path,
) -> None:
    calls: list[int] = []
    application = create_app(
        settings=make_settings(tmp_path / "api.sqlite3"),
        output_root=tmp_path / "outputs",
        workflow_runner=make_successful_runner(calls),
    )
    request_id = str(uuid4())
    with TestClient(application) as client:
        first = client.post(
            "/api/runs",
            json={"request_id": request_id, "topic": DEFAULT_TOPIC},
        )
        assert first.status_code == 202
        run_id = first.json()["run_id"]

        duplicate = client.post(
            "/api/runs",
            json={"request_id": request_id, "topic": DEFAULT_TOPIC},
        )
        assert duplicate.status_code == 200
        assert duplicate.json()["run_id"] == run_id
        assert duplicate.json()["duplicate_request"] is True

        result = wait_for_status(client, run_id)
        assert result["status"] == "APPROVED"
        assert result["job_status"] == "completed"
        assert result["attempts"][0]["attempt_number"] == 1
        assert result["evaluations"][0]["overall_status"] == "PASS"
        assert result["current_stage"] == "approved"
        progress_stages = {event["stage"] for event in result["progress_events"]}
        assert {
            "validating_topic",
            "loading_reference_knowledge",
            "retrieving_learned_rules",
            "generating_lesson",
            "evaluating_lesson",
            "approved",
        } <= progress_stages
        assert len(calls) == 1

        files = {item["filename"] for item in result["artifacts"]}
        assert "final_lesson.md" in files
        assert "rejected_lesson.md" not in files
        lesson_download = client.get(
            f"/api/runs/{run_id}/artifacts/final_lesson.md"
        )
        assert lesson_download.status_code == 200
        assert "APPROVED" in lesson_download.text
        assert client.get(f"/api/runs/{run_id}/artifacts/rejected_lesson.md").status_code == 404

        history = client.get("/api/runs?q=Introduction")
        assert history.status_code == 200
        assert history.json()["total"] == 1
        dashboard = client.get("/api/dashboard")
        assert dashboard.status_code == 200
        assert dashboard.json()["approved_executions"] == 1
        assert dashboard.json()["total_generation_attempts"] == 1
        assert dashboard.json()["approval_rate"] == 1.0


def test_api_runner_failure_is_safe_and_not_reported_as_in_progress(
    tmp_path: Path,
) -> None:
    def failing_runner(**kwargs):
        raise RuntimeError("sensitive provider response must not be exposed")

    output_root = tmp_path / "outputs"
    application = create_app(
        settings=make_settings(tmp_path / "api.sqlite3"),
        output_root=output_root,
        workflow_runner=failing_runner,
    )
    with TestClient(application) as client:
        started = client.post(
            "/api/runs",
            json={"request_id": str(uuid4()), "topic": DEFAULT_TOPIC},
        )
        assert started.status_code == 202
        result = wait_for_status(client, started.json()["run_id"])

    assert result["status"] == "FAILED"
    assert result["job_status"] == "failed"
    assert result["failure_reason"]
    assert "sensitive provider response" not in str(result)
    assert result["attempts"] == []
    assert result["evaluations"] == []
    assert result["artifacts"] == []
    assert not output_root.exists()


def test_rejection_log_includes_evaluator_failures_without_checkpoint_rejections(
    tmp_path: Path,
) -> None:
    application = create_app(
        settings=make_settings(tmp_path / "evaluation-failure.sqlite3"),
        output_root=tmp_path / "evaluation-failure-outputs",
        workflow_runner=make_mismatched_evaluator_runner(),
    )
    with TestClient(application) as client:
        document = client.app.state.runtime.knowledge_base.ingest_upload(
            filename="rag-reference.txt",
            content="Introduction to RAG. Retrieval augmented generation uses retrieved knowledge to support an LLM answer.",
        )
        started = client.post(
            "/api/runs",
            json={
                "request_id": str(uuid4()),
                "topic": DEFAULT_TOPIC,
                "mode": "rag",
                "knowledge_base_id": str(document.document_id),
            },
        )
        assert started.status_code == 202
        run_id = started.json()["run_id"]
        result = wait_for_status(client, run_id)
        assert result["status"] == "FAILED"

        log = client.get("/api/rejections", params={"run_id": run_id})
        assert log.status_code == 200
        assert log.json()["items"] == []
        assert len(log.json()["failures"]) == 1
        failure = log.json()["failures"][0]
        assert failure["failure_kind"] == "evaluation"
        assert failure["attempt_number"] == 1
        assert failure["error_category"] == "evaluation_validation_error"
        assert "different run or attempt" in failure["error_description"]


def test_output_failure_does_not_change_approved_decision(tmp_path: Path) -> None:
    from app.services.output_service import OutputGenerationError

    def failing_output(*args, **kwargs):
        raise OutputGenerationError("safe output error")

    application = create_app(
        settings=make_settings(tmp_path / "api.sqlite3"),
        output_root=tmp_path / "outputs",
        workflow_runner=make_successful_runner(),
        output_generator=failing_output,
    )
    with TestClient(application) as client:
        started = client.post(
            "/api/runs",
            json={"request_id": str(uuid4()), "topic": DEFAULT_TOPIC},
        )
        assert started.status_code == 202
        result = wait_for_status(client, started.json()["run_id"])

    assert result["status"] == "APPROVED"
    assert result["job_status"] == "completed"
    assert result["output_error"] == (
        "The decision was saved, but report files could not be generated."
    )
    assert result["artifacts"] == []


def test_api_cors_only_allows_local_frontend_origins(tmp_path: Path) -> None:
    application = create_app(
        settings=make_settings(tmp_path / "api.sqlite3"),
        output_root=tmp_path / "outputs",
    )
    with TestClient(application) as client:
        allowed = client.options(
            "/api/runs",
            headers={
                "Origin": "http://127.0.0.1:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        denied = client.options(
            "/api/runs",
            headers={
                "Origin": "https://example.invalid",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
    assert "access-control-allow-origin" not in denied.headers


def test_api_requires_backend_provider_configuration(tmp_path: Path) -> None:
    unconfigured = Settings(
        app_env="test",
        log_level="INFO",
        database_path=tmp_path / "api.sqlite3",
        max_retries=2,
    )
    application = create_app(settings=unconfigured, output_root=tmp_path / "outputs")
    with TestClient(application) as client:
        response = client.post(
            "/api/runs",
            json={"request_id": str(uuid4()), "topic": DEFAULT_TOPIC},
        )

    assert response.status_code == 503
    assert "LLM provider" in response.text


def test_rag_run_does_not_fall_back_when_knowledge_base_is_empty(
    tmp_path: Path,
) -> None:
    application = create_app(
        settings=make_settings(tmp_path / "empty-rag.sqlite3"),
        output_root=tmp_path / "outputs",
    )
    with TestClient(application) as client:
        response = client.post(
            "/api/runs",
            json={
                "request_id": str(uuid4()),
                "topic": "RAG for beginners",
                "mode": "rag",
            },
        )

    assert response.status_code == 422
    assert "RAG needs a selected knowledge-base document" in response.text


def test_demo_run_uses_three_attempts_and_persists_approved_note_across_restart(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "demo.sqlite3"
    application = create_app(
        settings=make_unconfigured_settings(database_path, max_retries=0),
        output_root=tmp_path / "demo-outputs",
    )
    with TestClient(application) as client:
        started = client.post(
            "/api/runs",
            json={
                "request_id": str(uuid4()),
                "topic": DEFAULT_TOPIC,
                "mode": "demo",
            },
        )
        assert started.status_code == 202
        assert started.json()["mode"] == "demo"
        detail = wait_for_status(client, started.json()["run_id"])

        assert detail["mode"] == "demo"
        assert detail["status"] == "APPROVED"
        assert len(detail["attempts"]) == 3
        assert len(detail["evaluations"]) == 3
        assert [
            evaluation["failed_checkpoints"]
            for evaluation in detail["evaluations"]
        ] == [["C2", "C3"], ["C1", "C4"], []]
        assert [
            sum(checkpoint["status"] == "PASS" for checkpoint in evaluation["checkpoints"])
            for evaluation in detail["evaluations"]
        ] == [4, 4, 6]
        assert len(detail["rejections"]) == 2
        for rejection, evaluation in zip(
            detail["rejections"],
            detail["evaluations"][:2],
            strict=True,
        ):
            assert rejection["correction_instructions"] == evaluation["correction_instructions"]
            assert all(
                instruction in rejection["correction_instructions"]
                for instruction in evaluation["correction_instructions"]
            )
        assert "C2 (Beginner-friendly language) failed." in detail["feedback_sent"]["1"][0]
        assert "Supporting evidence:" in detail["feedback_sent"]["1"][0]
        assert detail["evaluations"][0]["correction_instructions"][0] in (
            detail["feedback_sent"]["1"][0]
        )
        assert "C1 (Accuracy and grounding) failed." in detail["feedback_sent"]["2"][0]
        assert "3" not in detail["feedback_sent"]

        run_id = started.json()["run_id"]
        rejection_response = client.get(
            "/api/rejections",
            params={"run_id": run_id},
        )
        assert rejection_response.status_code == 200
        rejection_items = rejection_response.json()["items"]
        assert [item["rejection"]["attempt_number"] for item in rejection_items] == [
            2,
            1,
        ]
        assert [item["rejection"]["retry_attempt_number"] for item in rejection_items] == [
            3,
            2,
        ]
        assert [item["retry_attempt_status"] for item in rejection_items] == [
            "PASS",
            "FAIL",
        ]
        assert all(item["feedback_sent"] for item in rejection_items)
        assert all(
            item["rejection"]["run_id"] == run_id for item in rejection_items
        )
        assert rejection_items[0]["rejection"]["evidence"]["C1"]

        notes = client.get("/api/notes")
        assert notes.status_code == 200
        assert notes.json()["total"] == 1
        note = client.get(f"/api/notes/{run_id}")
        assert note.status_code == 200
        assert note.json()["evaluation_status"] == "APPROVED"
        assert note.json()["mode"] == "demo"
        final_markdown = detail["attempts"][-1]["generated_lesson"]["full_markdown"]
        assert "DEMO MODE" in final_markdown
        assert note.json()["full_markdown"] == final_markdown

        markdown_download = client.get(f"/api/notes/{run_id}/download?format=md")
        text_download = client.get(f"/api/notes/{run_id}/download?format=txt")
        assert markdown_download.status_code == text_download.status_code == 200
        assert markdown_download.text == text_download.text == final_markdown
        assert markdown_download.headers["content-disposition"].endswith(".md\"")
        assert text_download.headers["content-disposition"].endswith(".txt\"")

    restarted_application = create_app(
        settings=make_unconfigured_settings(database_path),
        output_root=tmp_path / "restarted-outputs",
    )
    with TestClient(restarted_application) as restarted_client:
        persisted_notes = restarted_client.get("/api/notes")
        assert persisted_notes.status_code == 200
        assert persisted_notes.json()["total"] == 1
        assert persisted_notes.json()["items"][0]["run_id"] == run_id
        persisted_note = restarted_client.get(f"/api/notes/{run_id}")
        assert persisted_note.status_code == 200
        assert persisted_note.json()["full_markdown"] == final_markdown
        persisted_rejections = restarted_client.get(
            "/api/rejections",
            params={"run_id": run_id},
        )
        assert persisted_rejections.status_code == 200
        assert [
            item["rejection"]["attempt_number"]
            for item in persisted_rejections.json()["items"]
        ] == [2, 1]


def test_rejection_api_filters_records_by_run_and_returns_retry_feedback(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "rejections.sqlite3"
    application = create_app(
        settings=make_settings(database_path),
        output_root=tmp_path / "rejection-outputs",
        workflow_runner=make_rejected_runner(),
    )
    run_ids = []
    with TestClient(application) as client:
        for _ in range(2):
            started = client.post(
                "/api/runs",
                json={
                    "request_id": str(uuid4()),
                    "topic": DEFAULT_TOPIC,
                    "mode": "gpt",
                },
            )
            assert started.status_code == 202
            run_ids.append(started.json()["run_id"])
            assert wait_for_status(client, run_ids[-1])["status"] == "REJECTED"

        assert len(client.get("/api/rejections").json()["items"]) == 6
        first_run_items = client.get(
            "/api/rejections",
            params={"run_id": run_ids[0]},
        ).json()["items"]
        assert len(first_run_items) == 3
        assert all(item["rejection"]["run_id"] == run_ids[0] for item in first_run_items)
        by_attempt = {
            item["rejection"]["attempt_number"]: item for item in first_run_items
        }
        assert by_attempt[1]["rejection"]["retry_attempt_number"] == 2
        assert by_attempt[1]["retry_attempt_status"] == "FAIL"
        assert "Failure reason: Scripted rejection for C1." in (
            by_attempt[1]["feedback_sent"][0]
        )
        assert by_attempt[3]["rejection"]["retry_attempt_number"] is None
        assert by_attempt[3]["retry_attempt_status"] is None
        assert by_attempt[3]["feedback_sent"] == []

    restarted_application = create_app(
        settings=make_settings(database_path),
        output_root=tmp_path / "restarted-rejection-outputs",
        workflow_runner=make_rejected_runner(),
    )
    with TestClient(restarted_application) as restarted_client:
        persisted = restarted_client.get(
            "/api/rejections",
            params={"run_id": run_ids[0]},
        )
        assert persisted.status_code == 200
        assert len(persisted.json()["items"]) == 3
        assert {item["rejection"]["run_id"] for item in persisted.json()["items"]} == {
            run_ids[0]
        }


def test_rejected_run_is_never_returned_as_an_approved_note(tmp_path: Path) -> None:
    application = create_app(
        settings=make_settings(tmp_path / "rejected.sqlite3"),
        output_root=tmp_path / "rejected-outputs",
        workflow_runner=make_rejected_runner(),
    )
    with TestClient(application) as client:
        started = client.post(
            "/api/runs",
            json={
                "request_id": str(uuid4()),
                "topic": DEFAULT_TOPIC,
                "mode": "gpt",
            },
        )
        assert started.status_code == 202
        detail = wait_for_status(client, started.json()["run_id"])
        assert detail["status"] == "REJECTED"
        assert len(detail["attempts"]) == 3
        assert client.get("/api/notes").json() == {"items": [], "total": 0}
        assert client.get(f"/api/notes/{started.json()['run_id']}").status_code == 404


@pytest.mark.parametrize(
    ("query", "expected_status"),
    [
        ("?status=APPROVED", 200),
        ("?status=NOT_A_STATUS", 422),
    ],
)
def test_run_history_status_filter_is_validated(
    tmp_path: Path,
    query: str,
    expected_status: int,
) -> None:
    application = create_app(
        settings=make_settings(tmp_path / "api.sqlite3"),
        output_root=tmp_path / "outputs",
    )
    with TestClient(application) as client:
        response = client.get(f"/api/runs{query}")

    assert response.status_code == expected_status
