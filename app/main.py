import argparse
import logging
import sqlite3
from collections.abc import Sequence

from app.config import ConfigurationError, DEFAULT_TOPIC, load_settings
from app.knowledge.reference_loader import ReferenceLoadError
from app.memory.memory_manager import MemoryManager
from app.services.output_service import (
    OutputGenerationError,
    generate_execution_outputs,
)
from app.utils.logger import configure_logging
from app.workflow import (
    WorkflowExecutionError,
    WorkflowPersistenceError,
    run_lesson_workflow,
)


logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Self-Evaluating Lesson Content Generator"
    )
    parser.add_argument(
        "--topic",
        default=None,
        help=f"Lesson topic (the assessment topic is {DEFAULT_TOPIC})",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        topic = args.topic if args.topic is not None else input("Lesson topic: ")
    except EOFError:
        logger.error("No topic was provided.")
        return 2

    topic = topic.strip()
    if not topic:
        parser.error("A non-empty --topic is required.")
    if topic.casefold() != DEFAULT_TOPIC.casefold():
        parser.error(f"This assessment supports only the topic: {DEFAULT_TOPIC}.")

    try:
        settings = load_settings()
    except ConfigurationError as exc:
        logging.basicConfig(level=logging.ERROR)
        logger.error("Configuration error: %s", exc)
        return 2

    configure_logging(settings.log_level)
    if not all(
        (settings.llm_provider, settings.llm_model, settings.llm_api_key)
    ):
        logger.error(
            "Generation requires LLM_PROVIDER, LLM_MODEL, and LLM_API_KEY configuration."
        )
        return 2

    try:
        memory_manager = MemoryManager(settings.database_path)
        result = run_lesson_workflow(
            topic=DEFAULT_TOPIC,
            memory_manager=memory_manager,
            settings=settings,
        )
    except ConfigurationError:
        logger.error("Application configuration is invalid.")
        return 2
    except ReferenceLoadError:
        logger.error("Trusted reference material could not be loaded.")
        return 1
    except (TypeError, ValueError) as exc:
        logger.error("Workflow validation failed: %s", exc)
        return 1
    except WorkflowExecutionError as exc:
        logger.error(
            "Workflow failed safely during attempt %d (run %s).",
            exc.attempt_number,
            exc.run_id,
        )
        return 1
    except WorkflowPersistenceError:
        logger.error("Workflow history could not be persisted.")
        return 1
    except (OSError, sqlite3.Error) as exc:
        logger.error("Unable to initialize persistent storage (%s).", type(exc).__name__)
        return 1

    print(f"Execution decision: {result.run.status.value}")
    print(f"Run ID: {result.run.run_id}")
    print(f"Generations: {len(result.attempt_history)}")
    try:
        artifacts = generate_execution_outputs(result, memory_manager)
    except OutputGenerationError as exc:
        logger.error("Output generation failed: %s", exc)
        print("The workflow decision is unchanged; output files were not completed.")
        return 1

    print(f"Output directory: {artifacts.directory}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
