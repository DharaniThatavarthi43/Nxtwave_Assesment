from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

import app.main as main_module
from app.config import DEFAULT_TOPIC, Settings
from app.schemas import RunStatus
from app.services.output_service import OutputArtifacts, OutputGenerationError
from app.workflow import WorkflowExecutionError


def _settings(tmp_path: Path, *, configured: bool = True) -> Settings:
    return Settings(
        app_env="test",
        log_level="ERROR",
        database_path=tmp_path / "lesson.sqlite3",
        max_retries=2,
        llm_provider="google" if configured else None,
        llm_model="test-model" if configured else None,
        llm_api_key="not-a-real-api-key" if configured else None,
    )


def _result(status: RunStatus = RunStatus.APPROVED):
    return SimpleNamespace(
        run=SimpleNamespace(run_id=uuid4(), status=status),
        attempt_history=(object(),),
    )


def test_cli_prompts_for_topic_and_runs_complete_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = _result()
    manager = object()
    artifacts = OutputArtifacts(
        directory=tmp_path / "outputs" / "run",
        files=(tmp_path / "outputs" / "run" / "final_lesson.md",),
    )
    workflow_calls = []
    output_calls = []
    monkeypatch.setattr(main_module, "load_settings", lambda: _settings(tmp_path))
    monkeypatch.setattr(main_module, "MemoryManager", lambda path: manager)
    monkeypatch.setattr(
        main_module,
        "run_lesson_workflow",
        lambda **kwargs: workflow_calls.append(kwargs) or result,
    )
    monkeypatch.setattr(
        main_module,
        "generate_execution_outputs",
        lambda execution, memory: output_calls.append((execution, memory)) or artifacts,
    )
    monkeypatch.setattr("builtins.input", lambda prompt: DEFAULT_TOPIC)

    exit_code = main_module.main([])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert workflow_calls[0]["topic"] == DEFAULT_TOPIC
    assert workflow_calls[0]["memory_manager"] is manager
    assert output_calls == [(result, manager)]
    assert "Execution decision: APPROVED" in output
    assert f"Run ID: {result.run.run_id}" in output
    assert "Generations: 1" in output
    assert str(artifacts.directory) in output


def test_cli_rejects_unrelated_topics_before_loading_settings() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main_module.main(["--topic", "Introduction to databases"])

    assert exc_info.value.code == 2


def test_cli_handles_missing_interactive_topic(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def no_input(prompt: str) -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", no_input)

    assert main_module.main([]) == 2
    assert "No topic was provided." in caplog.text


def test_cli_requires_llm_configuration_before_starting_a_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        main_module,
        "load_settings",
        lambda: _settings(tmp_path, configured=False),
    )
    monkeypatch.setattr(
        main_module,
        "MemoryManager",
        lambda path: pytest.fail("A run must not start without LLM settings."),
    )

    assert main_module.main(["--topic", DEFAULT_TOPIC]) == 2


def test_cli_workflow_failure_is_safe_and_does_not_generate_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    sensitive_details = "provider-key-or-response-must-not-be-logged"
    monkeypatch.setattr(main_module, "load_settings", lambda: _settings(tmp_path))
    monkeypatch.setattr(main_module, "MemoryManager", lambda path: object())

    def fail_workflow(**kwargs):
        raise WorkflowExecutionError(uuid4(), 2, sensitive_details)

    monkeypatch.setattr(main_module, "run_lesson_workflow", fail_workflow)
    monkeypatch.setattr(
        main_module,
        "generate_execution_outputs",
        lambda *args, **kwargs: pytest.fail("No outputs follow a failed workflow."),
    )

    assert main_module.main(["--topic", DEFAULT_TOPIC]) == 1
    assert sensitive_details not in caplog.text
    assert "Workflow failed safely during attempt 2" in caplog.text


def test_cli_handles_invalid_workflow_input_safely(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(main_module, "load_settings", lambda: _settings(tmp_path))
    monkeypatch.setattr(main_module, "MemoryManager", lambda path: object())

    def fail_workflow(**kwargs):
        raise ValueError("topic must not be empty")

    monkeypatch.setattr(main_module, "run_lesson_workflow", fail_workflow)
    monkeypatch.setattr(
        main_module,
        "generate_execution_outputs",
        lambda *args, **kwargs: pytest.fail("No outputs follow invalid workflow input."),
    )

    assert main_module.main(["--topic", DEFAULT_TOPIC]) == 1
    assert "Workflow validation failed" in caplog.text


def test_cli_reports_output_error_without_changing_rejected_decision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = _result(RunStatus.REJECTED)
    monkeypatch.setattr(main_module, "load_settings", lambda: _settings(tmp_path))
    monkeypatch.setattr(main_module, "MemoryManager", lambda path: object())
    monkeypatch.setattr(main_module, "run_lesson_workflow", lambda **kwargs: result)

    def fail_outputs(*args, **kwargs):
        raise OutputGenerationError("simulated report disk failure")

    monkeypatch.setattr(main_module, "generate_execution_outputs", fail_outputs)

    assert main_module.main(["--topic", DEFAULT_TOPIC]) == 1
    output = capsys.readouterr().out
    assert "Execution decision: REJECTED" in output
    assert "workflow decision is unchanged" in output
