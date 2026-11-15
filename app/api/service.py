import json
import sqlite3
from pathlib import Path
from uuid import UUID

from app.api.schemas import (
    CheckpointFailureCount,
    DailyRunCount,
    DashboardResponse,
    RunListResponse,
    RunSummaryResponse,
)
from app.memory.database import connect
from app.schemas import CheckpointId, CheckpointStatus, RunStatus


def get_dashboard(
    database_path: Path,
    *,
    active_rule_count: int,
) -> DashboardResponse:
    with connect(database_path) as connection:
        status_rows = connection.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM execution_runs
            GROUP BY status
            """
        ).fetchall()
        execution_counts = {row["status"]: row["count"] for row in status_rows}
        total_attempts = connection.execute(
            "SELECT COUNT(*) FROM generation_attempts"
        ).fetchone()[0]
        evaluation_rows = connection.execute(
            "SELECT checkpoints_json FROM evaluation_results"
        ).fetchall()
        days = connection.execute(
            """
            SELECT substr(created_at, 1, 10) AS date, status, COUNT(*) AS count
            FROM execution_runs
            GROUP BY date, status
            ORDER BY date DESC
            LIMIT 42
            """
        ).fetchall()

    checkpoint_failures = {checkpoint: 0 for checkpoint in CheckpointId}
    passed_checkpoints = 0
    evaluated_checkpoints = 0
    for row in evaluation_rows:
        try:
            checkpoints = json.loads(row["checkpoints_json"])
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(checkpoints, list):
            continue
        for item in checkpoints:
            if not isinstance(item, dict):
                continue
            try:
                checkpoint_id = CheckpointId(item.get("checkpoint_id"))
                status = CheckpointStatus(item.get("status"))
            except (TypeError, ValueError):
                continue
            evaluated_checkpoints += 1
            if status is CheckpointStatus.PASS:
                passed_checkpoints += 1
            else:
                checkpoint_failures[checkpoint_id] += 1

    daily_counts: dict[str, dict[str, int]] = {}
    for row in days:
        daily_counts.setdefault(row["date"], {"approved": 0, "rejected": 0, "failed": 0})
        if row["status"] in {"APPROVED", "REJECTED", "FAILED"}:
            daily_counts[row["date"]][row["status"].lower()] = row["count"]

    completed_runs = execution_counts.get("APPROVED", 0) + execution_counts.get(
        "REJECTED", 0
    )
    run_list = list_runs(database_path, limit=8)
    return DashboardResponse(
        total_executions=sum(execution_counts.values()),
        approved_executions=execution_counts.get("APPROVED", 0),
        rejected_executions=execution_counts.get("REJECTED", 0),
        failed_executions=execution_counts.get("FAILED", 0),
        total_generation_attempts=total_attempts,
        active_learned_rules=active_rule_count,
        approval_rate=(
            execution_counts.get("APPROVED", 0) / completed_runs
            if completed_runs
            else None
        ),
        mean_checkpoint_pass_rate=(
            passed_checkpoints / evaluated_checkpoints
            if evaluated_checkpoints
            else None
        ),
        checkpoint_failures=tuple(
            CheckpointFailureCount(
                checkpoint_id=checkpoint_id,
                failure_count=checkpoint_failures[checkpoint_id],
            )
            for checkpoint_id in CheckpointId
        ),
        executions_by_day=tuple(
            DailyRunCount(date=date, **counts)
            for date, counts in sorted(daily_counts.items())
        ),
        recent_runs=run_list.items,
    )


def list_runs(
    database_path: Path,
    *,
    query: str | None = None,
    status: RunStatus | None = None,
    offset: int = 0,
    limit: int = 50,
) -> RunListResponse:
    filters: list[str] = []
    parameters: list[object] = []
    if query and query.strip():
        filters.append(
            "(instr(lower(r.topic), lower(?)) > 0 "
            "OR instr(lower(r.run_id), lower(?)) > 0)"
        )
        parameters.extend((query.strip(), query.strip()))
    if status is not None:
        filters.append("r.status = ?")
        parameters.append(RunStatus(status).value)
    where_clause = f" WHERE {' AND '.join(filters)}" if filters else ""

    with connect(database_path) as connection:
        total = connection.execute(
            f"SELECT COUNT(*) FROM execution_runs AS r{where_clause}",
            parameters,
        ).fetchone()[0]
        rows = connection.execute(
            f"""
            SELECT r.run_id, r.topic, r.mode, r.status, r.created_at, r.updated_at,
                   COUNT(DISTINCT g.attempt_number) AS attempt_count,
                   COUNT(DISTINCT e.evaluation_id) AS evaluation_count,
                   COALESCE(
                       (SELECT f.error_description
                        FROM failed_evaluation_attempts AS f
                        WHERE f.run_id = r.run_id
                        ORDER BY f.attempt_number DESC LIMIT 1),
                       (SELECT f.error_description
                        FROM failed_generation_attempts AS f
                        WHERE f.run_id = r.run_id
                        ORDER BY f.attempt_number DESC LIMIT 1)
                   ) AS failure_reason
            FROM execution_runs AS r
            LEFT JOIN generation_attempts AS g ON g.run_id = r.run_id
            LEFT JOIN evaluation_results AS e ON e.run_id = r.run_id
            {where_clause}
            GROUP BY r.run_id
            ORDER BY r.created_at DESC, r.run_id
            LIMIT ? OFFSET ?
            """,
            [*parameters, limit, offset],
        ).fetchall()

    return RunListResponse(
        items=tuple(
            RunSummaryResponse(
                run_id=row["run_id"],
                topic=row["topic"],
                mode=row["mode"],
                status=row["status"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                attempt_count=row["attempt_count"],
                evaluation_count=row["evaluation_count"],
                failure_reason=row["failure_reason"],
            )
            for row in rows
        ),
        total=total,
        offset=offset,
        limit=limit,
    )


def find_output_directory(outputs_root: Path, run_id: UUID) -> Path | None:
    root = outputs_root.resolve()
    if not root.is_dir():
        return None
    candidates = []
    pattern = f"*-run-{run_id}-*"
    for candidate in root.glob(pattern):
        if not candidate.is_dir():
            continue
        resolved = candidate.resolve()
        if resolved.parent == root:
            candidates.append(resolved)
    if len(candidates) != 1:
        return None
    return candidates[0]


def database_is_available(database_path: Path) -> bool:
    try:
        with connect(database_path) as connection:
            connection.execute("SELECT 1").fetchone()
        return True
    except (OSError, sqlite3.Error):
        return False
