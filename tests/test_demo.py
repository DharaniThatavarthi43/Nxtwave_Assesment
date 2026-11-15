from pathlib import Path

from app.demo import run_demonstration
from app.prompts.generator_prompt import REQUIRED_LESSON_SECTIONS
from app.schemas import CheckpointId, CheckpointStatus, RunStatus


def test_corrected_demo_delivers_targeted_feedback_and_approves(
    tmp_path: Path,
) -> None:
    demonstration = run_demonstration(
        "corrected",
        output_root=tmp_path / "corrected",
    )
    result = demonstration.workflow

    assert result.run.status is RunStatus.APPROVED
    assert len(result.attempt_history) == 2
    assert result.evaluation_history[0].failed_checkpoints == (
        CheckpointId.ACCURACY_AND_GROUNDING,
    )
    assert result.evaluation_history[1].overall_status is CheckpointStatus.PASS
    assert "C1: Replace the retraining claim" in demonstration.generation_prompts[1]
    assert (demonstration.artifacts.directory / "final_lesson.md").is_file()
    assert not (demonstration.artifacts.directory / "rejected_lesson.md").exists()
    lesson = (demonstration.artifacts.directory / "final_lesson.md").read_text(
        encoding="utf-8"
    )
    assert "MOCKED DEMONSTRATION ONLY" in lesson
    assert "Retrieval-Augmented Generation" in lesson
    assert "RAG retrains the language model" not in lesson
    assert all(f"## {heading}" in lesson for heading in REQUIRED_LESSON_SECTIONS)


def test_rejected_demo_stops_after_three_failed_generations(
    tmp_path: Path,
) -> None:
    demonstration = run_demonstration(
        "rejected",
        output_root=tmp_path / "rejected",
    )
    result = demonstration.workflow

    assert result.run.status is RunStatus.REJECTED
    assert len(result.attempt_history) == 3
    assert all(
        evaluation.failed_checkpoints
        == (CheckpointId.ACCURACY_AND_GROUNDING,)
        for evaluation in result.evaluation_history
    )
    assert (demonstration.artifacts.directory / "rejected_lesson.md").is_file()
    assert not (demonstration.artifacts.directory / "final_lesson.md").exists()
    lesson = (demonstration.artifacts.directory / "rejected_lesson.md").read_text(
        encoding="utf-8"
    )
    assert "MOCKED DEMONSTRATION ONLY" in lesson
    assert "RAG retrains the language model whenever a document changes." in lesson
    assert all(f"## {heading}" in lesson for heading in REQUIRED_LESSON_SECTIONS)
