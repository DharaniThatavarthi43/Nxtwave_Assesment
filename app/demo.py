import argparse
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal
from unittest.mock import patch

from app.agents.evaluator import evaluate_lesson
from app.agents.generator import generate_lesson
from app.config import (
    DEFAULT_TOPIC,
    MAX_ALLOWED_RETRIES,
    PROJECT_ROOT,
    Settings,
    load_settings,
)
from app.knowledge.reference_loader import load_reference_material
from app.memory.memory_manager import MemoryManager
from app.prompts.generator_prompt import REQUIRED_LESSON_SECTIONS
from app.schemas import (
    CheckpointId,
    CheckpointStatus,
    EvaluationCheckpoint,
    EvaluationResult,
    Lesson,
)
from app.services.output_service import OutputArtifacts, generate_execution_outputs
from app.workflow import WorkflowResult, run_lesson_workflow


DemoScenario = Literal["corrected", "rejected"]
DELIBERATE_ERROR = "RAG retrains the language model whenever a document changes. [R2]"
MOCKED_BANNER = (
    "> MOCKED DEMONSTRATION ONLY: generator and evaluator responses are scripted; "
    "this is not a Gemini-generated lesson.\n\n"
)


@dataclass(frozen=True)
class DemonstrationResult:
    scenario: DemoScenario
    workflow: WorkflowResult
    artifacts: OutputArtifacts
    generation_prompts: tuple[str, ...]


def run_api_demo_workflow(**workflow_kwargs: object) -> WorkflowResult:
    topic = str(workflow_kwargs.pop("topic", DEFAULT_TOPIC))
    settings = workflow_kwargs.get("settings")
    if not isinstance(settings, Settings):
        settings = load_settings()
    workflow_kwargs["settings"] = replace(
        settings,
        max_retries=MAX_ALLOWED_RETRIES,
    )
    expected_feedback = {
        2: {CheckpointId.BEGINNER_FRIENDLY_LANGUAGE, CheckpointId.TEACHING_THROUGH_EXAMPLES},
        3: {CheckpointId.ACCURACY_AND_GROUNDING, CheckpointId.CLEAR_EXPLANATIONS},
    }

    def generate_demo_lesson(
        *,
        attempt_number: int,
        previous_feedback: tuple[str, ...],
        reference_material: object,
        **_: object,
    ) -> Lesson:
        expected = expected_feedback.get(attempt_number, set())
        supplied = {
            checkpoint
            for feedback in previous_feedback
            for checkpoint in CheckpointId
            if feedback.startswith(f"{checkpoint.value} (")
        }
        if supplied != expected:
            raise AssertionError(
                f"Demo attempt {attempt_number} received feedback for "
                f"{sorted(item.value for item in supplied)} instead of "
                f"{sorted(item.value for item in expected)}."
            )

        sections = _lesson_sections(
            deliberate_error=attempt_number == 2,
        )
        if attempt_number == 1:
            sections["Introduction"] = (
                "RAG combines retrieval-augmented generation, embedding-indexed "
                "corpora, semantic similarity, and model inference. [R1, R2]"
            )
            sections["Simple Real-World Example"] = (
                "A RAG system retrieves and generates using documents. [R2]"
            )
        elif attempt_number == 2:
            sections["Key Terms"] = (
                "- **Retriever:** a module that executes nearest-neighbor search "
                "across vectorized corpus representations.\n"
                "- **Chunk:** a segment of a larger document.\n"
                "- **Embedding:** a list of numbers used to compare text.\n"
                "- **Context:** information given to the model. [R1, R2, R3]"
            )

        title = "RAG: Finding Helpful Information Before Answering"
        return Lesson(
            topic=topic,
            title=title,
            attempt_number=attempt_number,
            sections=sections,
            full_markdown=(
                "> **DEMO MODE — scripted lesson; this is not live LLM output.**\n\n"
                + _lesson_markdown(title, sections)
            ),
            reference_ids=("R1", "R2", "R3"),
        )

    def evaluate_demo_lesson(
        *,
        lesson: Lesson,
        run_id: object,
        **_: object,
    ) -> EvaluationResult:
        failures_by_attempt = {
            1: {
                CheckpointId.BEGINNER_FRIENDLY_LANGUAGE,
                CheckpointId.TEACHING_THROUGH_EXAMPLES,
            },
            2: {
                CheckpointId.ACCURACY_AND_GROUNDING,
                CheckpointId.CLEAR_EXPLANATIONS,
            },
            3: set(),
        }
        failed = failures_by_attempt[lesson.attempt_number]
        evidence_by_checkpoint = {
            CheckpointId.ACCURACY_AND_GROUNDING: lesson.sections["What Is RAG?"],
            CheckpointId.BEGINNER_FRIENDLY_LANGUAGE: lesson.sections["Introduction"],
            CheckpointId.TEACHING_THROUGH_EXAMPLES: lesson.sections["Simple Real-World Example"],
            CheckpointId.CLEAR_EXPLANATIONS: lesson.sections["Key Terms"],
            CheckpointId.KEY_CONCEPT_COVERAGE: lesson.sections["Recap"],
            CheckpointId.TEACHING_FLOW: lesson.sections["How Does RAG Work?"],
        }
        failure_reasons = {
            CheckpointId.ACCURACY_AND_GROUNDING: (
                "The lesson incorrectly claims that changing a document retrains "
                "the language model."
            ),
            CheckpointId.BEGINNER_FRIENDLY_LANGUAGE: (
                "The introduction uses advanced terms without explaining them for "
                "a beginner."
            ),
            CheckpointId.TEACHING_THROUGH_EXAMPLES: (
                "The example does not show a familiar situation or explain the "
                "retrieval and answer steps."
            ),
            CheckpointId.CLEAR_EXPLANATIONS: (
                "The key terms use technical search language without defining it "
                "in simple words."
            ),
        }
        pass_reasons = {
            CheckpointId.ACCURACY_AND_GROUNDING: (
                "The lesson accurately explains that RAG retrieves document "
                "passages without retraining the model for each update."
            ),
            CheckpointId.BEGINNER_FRIENDLY_LANGUAGE: (
                "The introduction defines RAG and its main words in beginner-friendly "
                "language."
            ),
            CheckpointId.TEACHING_THROUGH_EXAMPLES: (
                "The lesson gives a familiar example and describes how retrieved "
                "information helps answer the question."
            ),
            CheckpointId.CLEAR_EXPLANATIONS: (
                "The lesson defines technical terms in plain language."
            ),
            CheckpointId.KEY_CONCEPT_COVERAGE: (
                "The recap covers retrieval, context, generation, and limitations."
            ),
            CheckpointId.TEACHING_FLOW: (
                "The lesson moves from the definition through steps and examples "
                "to a recap."
            ),
        }
        corrections = {
            CheckpointId.ACCURACY_AND_GROUNDING: (
                "C1: Correct the claim: RAG retrieves current document passages; "
                "updating a document does not retrain the language model."
            ),
            CheckpointId.BEGINNER_FRIENDLY_LANGUAGE: (
                "C2: Replace advanced terminology with simple English and explain "
                "technical terms before using them."
            ),
            CheckpointId.TEACHING_THROUGH_EXAMPLES: (
                "C3: Add a familiar, step-by-step real-world example showing the "
                "question, retrieved passage, and answer."
            ),
            CheckpointId.CLEAR_EXPLANATIONS: (
                "C4: Define each technical term in plain language before describing "
                "how it works."
            ),
        }
        checkpoints = tuple(
            EvaluationCheckpoint(
                checkpoint_id=checkpoint_id,
                status=(
                    CheckpointStatus.FAIL
                    if checkpoint_id in failed
                    else CheckpointStatus.PASS
                ),
                reason=(
                    failure_reasons[checkpoint_id]
                    if checkpoint_id in failed
                    else pass_reasons[checkpoint_id]
                ),
                evidence=evidence_by_checkpoint[checkpoint_id],
            )
            for checkpoint_id in CheckpointId
        )
        return EvaluationResult(
            run_id=run_id,
            attempt_number=lesson.attempt_number,
            overall_status=(
                CheckpointStatus.FAIL if failed else CheckpointStatus.PASS
            ),
            checkpoints=checkpoints,
            failed_checkpoints=tuple(
                checkpoint_id
                for checkpoint_id in CheckpointId
                if checkpoint_id in failed
            ),
            correction_instructions=tuple(
                corrections[checkpoint_id]
                for checkpoint_id in CheckpointId
                if checkpoint_id in failed
            ),
            overall_reason=(
                f"DEMO MODE — scripted evaluator result: {len(CheckpointId) - len(failed)}"
                f"/{len(CheckpointId)} mandatory checkpoints passed."
            ),
        )

    return run_lesson_workflow(
        topic=topic,
        generator_fn=generate_demo_lesson,
        evaluator_fn=evaluate_demo_lesson,
        mode="demo",
        **workflow_kwargs,
    )


class _QueuedChatModel:
    def __init__(self, responses: list[object]) -> None:
        self.responses = list(responses)
        self.prompts: list[list[object]] = []

    def with_structured_output(self, schema: type) -> "_QueuedChatModel":
        return self

    def invoke(self, messages: list[object]) -> object:
        if not self.responses:
            raise AssertionError("The demonstration used more mocked responses than expected.")
        self.prompts.append(messages)
        return self.responses.pop(0)


def _lesson_sections(*, deliberate_error: bool) -> dict[str, str]:
    rag_definition = (
        DELIBERATE_ERROR
        if deliberate_error
        else (
            "RAG retrieves useful passages from a document collection and gives them "
            "to a language model. Updating the collection does not require retraining "
            "the model for every document change. [R2]"
        )
    )
    return {
        "Learning Objectives": (
            "By the end, you can explain RAG, describe its main steps, and name one "
            "benefit and one limitation."
        ),
        "Introduction": (
            "RAG means Retrieval-Augmented Generation. Retrieval means finding "
            "useful information, and generation means writing a response. A language "
            "model is software that works with text and can write answers. RAG gives "
            "it useful information found in documents. [R1, R2]"
        ),
        "What Is RAG?": rag_definition,
        "Why Is RAG Needed?": (
            "A model may not know a private handbook or a recent change. RAG can "
            "search a selected document collection at question time and provide "
            "useful passages without retraining the model for every update. [R1, R2]"
        ),
        "How Does RAG Work?": (
            "First, prepare and split documents into smaller pieces called chunks. "
            "Next, search for passages related to the question. Then, give the "
            "passages and question to the model so it can write an answer. [R1, R2]"
        ),
        "Main Components of a RAG System": (
            "A RAG system can include a knowledge collection, document preparation, "
            "a retriever that searches for passages, code that connects the steps, "
            "and a language model that writes the answer. [R2, R3]"
        ),
        "Simple Real-World Example": (
            "A student asks, 'What papers do I need for a college scholarship?' The "
            "system searches the current college handbook, finds the passage about "
            "application documents, and gives it to a language model to explain in "
            "simple words. If it finds the wrong page or no answer, the result can "
            "still be wrong. [R2, R3]"
        ),
        "Technical Workflow Example": (
            "A college prepares its handbook and splits long text into chunks. An "
            "embedding is a list of numbers that helps search for text with related "
            "meaning. When a student asks a question, retrieval finds possible "
            "passages. The system adds those passages to the question as context, "
            "then asks the model to answer. [R2, R3]"
        ),
        "RAG Compared with a Normal LLM Response": (
            "A large language model (LLM) can answer from patterns learned during "
            "training and from the question. A RAG response first retrieves selected "
            "material from an external collection and gives it to the model with the "
            "question. This provides extra information but does not retrain the "
            "model. [R1, R2]"
        ),
        "Benefits": (
            "RAG can connect a model to selected private or changing documents, and "
            "the collection can be updated separately from the model. These are "
            "possible benefits, not guarantees of a correct answer. [R2, R3]"
        ),
        "Limitations": (
            "Search may miss useful information or find an irrelevant passage. A "
            "model can misunderstand the retrieved text or add unsupported details, "
            "so RAG cannot remove every error. [R2]"
        ),
        "Common Applications": (
            "RAG can help answer questions about product guides, workplace policies, "
            "research collections, and customer-support material. The sources and "
            "retrieval still need to fit the task. [R2, R3]"
        ),
        "Key Terms": (
            "- **Retriever:** a part that searches for useful passages.\n"
            "- **Chunk:** a small piece of a longer document.\n"
            "- **Embedding:** a list of numbers representing text for search; it "
            "does not prove that the text is true.\n"
            "- **Context:** information given to the model along with the question.\n"
            "- **Prompt:** the instructions and information supplied to the model. "
            "[R1, R2, R3]"
        ),
        "Recap": (
            "RAG searches a chosen collection, retrieves useful passages, adds them "
            "as context, and asks a language model to answer. It can provide access "
            "to changing information, but retrieval and generated answers can still "
            "be wrong. [R1, R2]"
        ),
        "Knowledge Check": (
            "1. What does a retriever do?\n"
            "2. Does RAG guarantee that every answer is correct?"
        ),
        "Answers": (
            "1. A retriever searches for passages that may help answer the question. "
            "[R2]\n"
            "2. No. Search can miss useful text, and a model can misunderstand what "
            "it finds. [R2]"
        ),
    }


def _lesson_markdown(title: str, sections: dict[str, str]) -> str:
    parts = [f"# {title}"]
    parts.extend(
        f"## {heading}\n\n{sections[heading]}"
        for heading in REQUIRED_LESSON_SECTIONS
    )
    return "\n\n".join(parts)


def _generation_payload(*, deliberate_error: bool) -> dict[str, object]:
    return {
        "title": "RAG: Finding Helpful Information Before Answering",
        "sections": _lesson_sections(deliberate_error=deliberate_error),
    }


def _evaluation_payload(
    sections: dict[str, str],
    *,
    fail_accuracy: bool,
) -> dict[str, object]:
    evidence_by_checkpoint = {
        CheckpointId.ACCURACY_AND_GROUNDING: sections["What Is RAG?"],
        CheckpointId.BEGINNER_FRIENDLY_LANGUAGE: sections["Introduction"],
        CheckpointId.TEACHING_THROUGH_EXAMPLES: sections["Simple Real-World Example"],
        CheckpointId.CLEAR_EXPLANATIONS: sections["Key Terms"],
        CheckpointId.KEY_CONCEPT_COVERAGE: sections["Recap"],
        CheckpointId.TEACHING_FLOW: sections["Technical Workflow Example"],
    }
    checkpoints = []
    for checkpoint_id in CheckpointId:
        failed = (
            fail_accuracy
            and checkpoint_id is CheckpointId.ACCURACY_AND_GROUNDING
        )
        if failed:
            reason = (
                "The lesson incorrectly says document changes retrain the model; "
                "the trusted notes explain that documents can be updated without "
                "retraining for each update. [R2]"
            )
        else:
            reason = (
                f"The lesson provides relevant, beginner-appropriate evidence for "
                f"{checkpoint_id.value}."
            )
        checkpoints.append(
            {
                "checkpoint_id": checkpoint_id.value,
                "status": "FAIL" if failed else "PASS",
                "reason": reason,
                "evidence": evidence_by_checkpoint[checkpoint_id],
            }
        )

    return {
        "checkpoints": checkpoints,
        "correction_instructions": (
            [
                "C1: Replace the retraining claim with the accurate explanation "
                "that RAG retrieves current documents without retraining the model "
                "for each update."
            ]
            if fail_accuracy
            else []
        ),
    }


def _prompt_text(prompts: list[list[object]]) -> tuple[str, ...]:
    return tuple(
        "\n".join(str(getattr(message, "content", message)) for message in messages)
        for messages in prompts
    )


def _label_artifacts(artifacts: OutputArtifacts) -> None:
    for path in artifacts.files:
        content = path.read_text(encoding="utf-8")
        path.write_text(MOCKED_BANNER + content, encoding="utf-8", newline="\n")


def run_demonstration(
    scenario: DemoScenario,
    *,
    output_root: Path | str | None = None,
) -> DemonstrationResult:
    if scenario not in {"corrected", "rejected"}:
        raise ValueError("Scenario must be 'corrected' or 'rejected'.")

    destination = (
        Path(output_root)
        if output_root is not None
        else PROJECT_ROOT / "outputs" / "examples" / scenario
    ).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)

    attempts = 2 if scenario == "corrected" else 3
    generation_payloads = [
        _generation_payload(
            deliberate_error=(
                scenario == "rejected"
                or attempt_number == 1
            )
        )
        for attempt_number in range(1, attempts + 1)
    ]
    evaluator_payloads = [
        _evaluation_payload(
            _lesson_sections(
                deliberate_error=(
                    scenario == "rejected"
                    or attempt_number == 1
                )
            ),
            fail_accuracy=(
                scenario == "rejected"
                or attempt_number == 1
            ),
        )
        for attempt_number in range(1, attempts + 1)
    ]
    generation_model = _QueuedChatModel(generation_payloads)
    evaluator_model = _QueuedChatModel(evaluator_payloads)

    with tempfile.TemporaryDirectory(prefix="rag-demo-") as temporary_directory:
        database_path = Path(temporary_directory) / "demo.sqlite3"
        settings = Settings(
            app_env="test",
            log_level="ERROR",
            database_path=database_path,
            max_retries=2,
        )
        memory = MemoryManager(database_path)
        with (
            patch(
                "app.agents.generator.create_chat_model",
                return_value=generation_model,
            ),
            patch(
                "app.agents.evaluator.create_chat_model",
                return_value=evaluator_model,
            ),
        ):
            result = run_lesson_workflow(
                topic=DEFAULT_TOPIC,
                generator_fn=generate_lesson,
                evaluator_fn=evaluate_lesson,
                memory_manager=memory,
                reference_material=load_reference_material(),
                settings=settings,
            )
            artifacts = generate_execution_outputs(
                result,
                memory,
                output_root=destination,
            )

    _label_artifacts(artifacts)
    generation_prompts = _prompt_text(generation_model.prompts)
    if scenario == "corrected":
        if (
            not result.approved
            or len(result.attempt_history) != 2
            or "C1: Replace the retraining claim" not in generation_prompts[1]
        ):
            raise AssertionError(
                "The corrected demonstration did not deliver targeted C1 feedback "
                "and approve on its second generation."
            )
    elif result.approved or len(result.attempt_history) != 3:
        raise AssertionError(
            "The rejected demonstration did not stop as REJECTED after three generations."
        )

    manifest = destination / "README.md"
    manifest.write_text(
        "\n".join(
            [
                "# Mocked workflow demonstration",
                "",
                "This output uses scripted generator and evaluator responses. "
                "It is not a Gemini-generated artifact and does not demonstrate "
                "live model semantics.",
                "",
                f"- Scenario: **{scenario}**",
                f"- Decision: **{result.run.status.value}**",
                f"- Generations: **{len(result.attempt_history)}**",
                f"- Output folder: `{artifacts.directory}`",
                "",
            ]
        ),
        encoding="utf-8",
        newline="\n",
    )
    return DemonstrationResult(
        scenario=scenario,
        workflow=result,
        artifacts=artifacts,
        generation_prompts=generation_prompts,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a deterministic, mocked workflow demonstration."
    )
    parser.add_argument(
        "--scenario",
        choices=("corrected", "rejected"),
        required=True,
        help="Show a corrected lesson or rejection after three failing generations.",
    )
    args = parser.parse_args(argv)
    demonstration = run_demonstration(args.scenario)
    workflow = demonstration.workflow
    for evaluation in workflow.evaluation_history:
        failed = ", ".join(item.value for item in evaluation.failed_checkpoints)
        print(
            f"Generation {evaluation.attempt_number}: "
            f"{evaluation.overall_status.value}"
            + (f" ({failed})" if failed else "")
        )
        for checkpoint in evaluation.checkpoints:
            if checkpoint.status.value == "FAIL":
                print(f"  {checkpoint.checkpoint_id.value}: {checkpoint.reason}")
                print(
                    "  Feedback: "
                    + "; ".join(evaluation.correction_instructions)
                )
    print(f"Final decision: {workflow.run.status.value}")
    print(f"Mocked output directory: {demonstration.artifacts.directory}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
