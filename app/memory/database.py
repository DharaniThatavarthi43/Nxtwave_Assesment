import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS execution_runs (
        run_id TEXT PRIMARY KEY NOT NULL,
        topic TEXT NOT NULL CHECK (length(trim(topic)) > 0),
        mode TEXT NOT NULL DEFAULT 'assessment' CHECK (
            mode IN ('assessment', 'gpt', 'rag', 'demo')
        ),
        max_retries INTEGER NOT NULL DEFAULT 2 CHECK (max_retries BETWEEN 0 AND 2),
        status TEXT NOT NULL CHECK (
            status IN ('IN_PROGRESS', 'APPROVED', 'REJECTED', 'FAILED')
        ),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS generation_attempts (
        attempt_id TEXT PRIMARY KEY NOT NULL,
        run_id TEXT NOT NULL,
        attempt_number INTEGER NOT NULL CHECK (attempt_number BETWEEN 1 AND 3),
        generated_lesson_json TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        UNIQUE (run_id, attempt_number),
        FOREIGN KEY (run_id) REFERENCES execution_runs(run_id) ON DELETE RESTRICT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS failed_generation_attempts (
        failure_id TEXT PRIMARY KEY NOT NULL,
        run_id TEXT NOT NULL,
        attempt_number INTEGER NOT NULL CHECK (attempt_number BETWEEN 1 AND 3),
        status TEXT NOT NULL CHECK (status = 'FAILED'),
        failure_stage TEXT NOT NULL CHECK (failure_stage IN (
            'unknown', 'provider_request', 'structured_output_parsing',
            'schema_validation', 'lesson_content_validation'
        )),
        error_category TEXT NOT NULL CHECK (error_category IN (
            'generation_error', 'provider_request_error', 'structured_output_error',
            'schema_validation_error', 'lesson_content_validation_error',
            'configuration_error'
        )),
        validation_subcode TEXT CHECK (validation_subcode IS NULL OR
            validation_subcode IN (
                'missing_required_section', 'duplicate_required_section',
                'duplicate_section', 'unknown_reference_id',
                'missing_factual_citation', 'invalid_citation_format'
            )
        ),
        error_type TEXT NOT NULL CHECK (length(trim(error_type)) > 0),
        error_description TEXT NOT NULL CHECK (length(trim(error_description)) > 0),
        timestamp TEXT NOT NULL,
        UNIQUE (run_id, attempt_number),
        FOREIGN KEY (run_id) REFERENCES execution_runs(run_id) ON DELETE RESTRICT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS evaluation_results (
        evaluation_id TEXT PRIMARY KEY NOT NULL,
        run_id TEXT NOT NULL,
        attempt_number INTEGER NOT NULL,
        overall_status TEXT NOT NULL CHECK (overall_status IN ('PASS', 'FAIL')),
        checkpoints_json TEXT NOT NULL,
        failed_checkpoints_json TEXT NOT NULL,
        correction_instructions_json TEXT NOT NULL,
        overall_reason TEXT NOT NULL,
        evaluated_at TEXT NOT NULL,
        UNIQUE (run_id, attempt_number),
        FOREIGN KEY (run_id, attempt_number)
            REFERENCES generation_attempts(run_id, attempt_number)
            ON DELETE RESTRICT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS failed_evaluation_attempts (
        failure_id TEXT PRIMARY KEY NOT NULL,
        run_id TEXT NOT NULL,
        attempt_number INTEGER NOT NULL CHECK (attempt_number BETWEEN 1 AND 3),
        status TEXT NOT NULL CHECK (status = 'FAILED'),
        failure_stage TEXT NOT NULL CHECK (failure_stage IN (
            'unknown', 'api_request', 'structured_output_parsing',
            'schema_validation', 'evaluation_validation'
        )),
        error_category TEXT NOT NULL CHECK (error_category IN (
            'evaluator_error', 'rate_limited', 'provider_server_error',
            'provider_permanent_error', 'provider_error', 'configuration_error',
            'structured_output_error', 'schema_validation_error',
            'evaluation_validation_error'
        )),
        retry_disposition TEXT CHECK (retry_disposition IS NULL OR
            retry_disposition IN (
                'retry_skipped', 'retries_exhausted',
                'retry_after_exceeds_cap', 'permanent_provider_failure'
            )
        ),
        error_type TEXT NOT NULL CHECK (length(trim(error_type)) > 0),
        error_description TEXT NOT NULL CHECK (length(trim(error_description)) > 0),
        timestamp TEXT NOT NULL,
        UNIQUE (run_id, attempt_number),
        FOREIGN KEY (run_id, attempt_number)
            REFERENCES generation_attempts(run_id, attempt_number)
            ON DELETE RESTRICT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rejection_logs (
        rejection_id TEXT PRIMARY KEY NOT NULL,
        run_id TEXT NOT NULL,
        attempt_number INTEGER NOT NULL,
        failed_checkpoints_json TEXT NOT NULL,
        failure_reasons_json TEXT NOT NULL,
        evidence_json TEXT NOT NULL,
        correction_instructions_json TEXT NOT NULL,
        correction_applied TEXT NOT NULL,
        changes_made TEXT NOT NULL,
        created_at TEXT NOT NULL,
        retry_attempt_number INTEGER CHECK (
            retry_attempt_number IS NULL OR retry_attempt_number BETWEEN 2 AND 3
        ),
        UNIQUE (run_id, attempt_number),
        FOREIGN KEY (run_id, attempt_number)
            REFERENCES generation_attempts(run_id, attempt_number)
            ON DELETE RESTRICT,
        FOREIGN KEY (run_id, attempt_number)
            REFERENCES evaluation_results(run_id, attempt_number)
            ON DELETE RESTRICT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS learned_rules (
        rule_id TEXT PRIMARY KEY NOT NULL,
        rule_description TEXT NOT NULL CHECK (length(trim(rule_description)) > 0),
        rationale TEXT NOT NULL CHECK (length(trim(rationale)) > 0),
        related_checkpoint TEXT NOT NULL CHECK (
            related_checkpoint IN ('C1', 'C2', 'C3', 'C4', 'C5', 'C6')
        ),
        failure_count INTEGER NOT NULL CHECK (failure_count >= 1),
        confidence REAL NOT NULL CHECK (confidence BETWEEN 0.0 AND 1.0),
        active_status INTEGER NOT NULL CHECK (active_status IN (0, 1)),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS learned_rule_rejections (
        rule_id TEXT NOT NULL,
        rejection_id TEXT NOT NULL,
        PRIMARY KEY (rule_id, rejection_id),
        FOREIGN KEY (rule_id) REFERENCES learned_rules(rule_id) ON DELETE RESTRICT,
        FOREIGN KEY (rejection_id) REFERENCES rejection_logs(rejection_id)
            ON DELETE RESTRICT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS knowledge_documents (
        document_id TEXT PRIMARY KEY NOT NULL,
        title TEXT NOT NULL CHECK (length(trim(title)) > 0),
        source_type TEXT NOT NULL CHECK (source_type IN ('manual', 'url', 'upload')),
        source_url TEXT,
        content TEXT NOT NULL CHECK (length(trim(content)) > 0),
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS knowledge_chunks (
        chunk_id TEXT PRIMARY KEY NOT NULL,
        document_id TEXT NOT NULL,
        chunk_index INTEGER NOT NULL CHECK (chunk_index >= 0),
        content TEXT NOT NULL CHECK (length(trim(content)) > 0),
        embedding_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (document_id) REFERENCES knowledge_documents(document_id)
            ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_runs_created_at ON execution_runs(created_at)",
    """
    CREATE INDEX IF NOT EXISTS idx_attempts_run_number
    ON generation_attempts(run_id, attempt_number)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_failed_attempts_run_number
    ON failed_generation_attempts(run_id, attempt_number)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_failed_evaluation_run_number
    ON failed_evaluation_attempts(run_id, attempt_number)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_rejections_run
    ON rejection_logs(run_id, attempt_number)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_rules_active_checkpoint
    ON learned_rules(active_status, related_checkpoint)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_rule_rejections_rejection
    ON learned_rule_rejections(rejection_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_knowledge_documents_created_at
    ON knowledge_documents(created_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_document
    ON knowledge_chunks(document_id, chunk_index)
    """,
)


@contextmanager
def connect(database_path: Path | str) -> Iterator[sqlite3.Connection]:
    path = Path(database_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=5.0)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database(database_path: Path | str) -> None:
    with connect(database_path) as connection:
        for statement in SCHEMA_STATEMENTS:
            connection.execute(statement)
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(execution_runs)")}
        if "max_retries" not in columns:
            connection.execute(
                "ALTER TABLE execution_runs ADD COLUMN max_retries INTEGER NOT NULL DEFAULT 2 CHECK (max_retries BETWEEN 0 AND 2)"
            )
        _migrate_execution_run_mode(connection)
        _migrate_failed_generation_attempts(connection)
        _migrate_failed_evaluation_attempts(connection)
        _migrate_rejection_retry_attempt(connection)


def _migrate_execution_run_mode(connection: sqlite3.Connection) -> None:
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(execution_runs)")
    }
    if "mode" not in columns:
        connection.execute(
            """
            ALTER TABLE execution_runs
            ADD COLUMN mode TEXT NOT NULL DEFAULT 'assessment'
            """
        )


def _migrate_failed_generation_attempts(
    connection: sqlite3.Connection,
) -> None:
    columns = {
        row["name"]
        for row in connection.execute(
            "PRAGMA table_info(failed_generation_attempts)"
        )
    }
    if "failure_stage" not in columns:
        connection.execute(
            """
            ALTER TABLE failed_generation_attempts
            ADD COLUMN failure_stage TEXT NOT NULL DEFAULT 'unknown'
            """
        )
    if "error_category" not in columns:
        connection.execute(
            """
            ALTER TABLE failed_generation_attempts
            ADD COLUMN error_category TEXT NOT NULL DEFAULT 'generation_error'
            """
        )
    if "validation_subcode" not in columns:
        connection.execute(
            """
            ALTER TABLE failed_generation_attempts
            ADD COLUMN validation_subcode TEXT
            """
        )


def _migrate_failed_evaluation_attempts(
    connection: sqlite3.Connection,
) -> None:
    columns = {
        row["name"]
        for row in connection.execute(
            "PRAGMA table_info(failed_evaluation_attempts)"
        )
    }
    if "retry_disposition" not in columns:
        connection.execute(
            """
            ALTER TABLE failed_evaluation_attempts
            ADD COLUMN retry_disposition TEXT
            """
        )


def _migrate_rejection_retry_attempt(connection: sqlite3.Connection) -> None:
    columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(rejection_logs)")
    }
    if "retry_attempt_number" not in columns:
        connection.execute(
            "ALTER TABLE rejection_logs ADD COLUMN retry_attempt_number INTEGER"
        )
    connection.execute(
        """
        UPDATE rejection_logs
        SET retry_attempt_number = attempt_number + 1
        WHERE retry_attempt_number IS NULL
          AND attempt_number < 3
          AND (
              EXISTS (
                  SELECT 1 FROM generation_attempts
                  WHERE generation_attempts.run_id = rejection_logs.run_id
                    AND generation_attempts.attempt_number =
                        rejection_logs.attempt_number + 1
              )
              OR EXISTS (
                  SELECT 1 FROM failed_generation_attempts
                  WHERE failed_generation_attempts.run_id = rejection_logs.run_id
                    AND failed_generation_attempts.attempt_number =
                        rejection_logs.attempt_number + 1
              )
          )
        """
    )
