import { ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api";
import type { RunDetail, RunList } from "../types";
import { CheckpointCards } from "../components/CheckpointCards";
import { useLanguage } from "../language";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  PageTitle,
  StatusPill,
} from "../components/Shared";

async function loadAllRuns(): Promise<RunList> {
  const pageSize = 100;
  const firstPage = await api.history({ offset: 0, limit: pageSize });
  const items = [...firstPage.items];
  for (let offset = items.length; offset < firstPage.total; offset += pageSize) {
    const page = await api.history({ offset, limit: pageSize });
    items.push(...page.items);
  }
  return { ...firstPage, items, total: items.length, offset: 0, limit: items.length };
}

function evaluationFailureReason(errorCategory: string, errorDescription: string) {
  if (
    errorCategory === "evaluation_validation_error" &&
    errorDescription === "Evaluator output failed application validation."
  ) {
    return "The evaluator response failed validation before any C1–C6 decision could be saved. The evaluator must provide a clear reason and exact lesson evidence for each check, use valid knowledge-base citations, and provide a correction for every failed check. This older run did not save which validation rule failed. No specific checkpoint can be marked failed from this record.";
  }
  return errorDescription;
}

export function EvaluationPage() {
  const { t } = useLanguage();
  const [history, setHistory] = useState<RunList | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void loadAllRuns().then(
      (result) => {
        setHistory(result);
        const latestEvaluated = result.items.find((run) => run.evaluation_count > 0);
        setSelectedId(latestEvaluated?.run_id ?? result.items[0]?.run_id ?? "");
        setLoading(false);
      },
      (reason: Error) => {
        setError(reason.message);
        setLoading(false);
      },
    );
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    let active = true;
    let timer: number | undefined;
    const refresh = async (initial = false) => {
      if (initial) setLoading(true);
      try {
        const result = await api.run(selectedId);
        if (!active) return;
        setDetail(result);
        setError(null);
        setLoading(false);
        if (result.job_status === "running" || result.job_status === "queued") {
          timer = window.setTimeout(() => void refresh(), 1500);
        }
      } catch (reason) {
        if (!active) return;
        setError(reason instanceof Error ? reason.message : String(reason));
        setLoading(false);
        timer = window.setTimeout(() => void refresh(), 3000);
      }
    };
    void refresh(true);
    return () => {
      active = false;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [selectedId]);

  return (
    <>
      <PageTitle
        eyebrow="WORKSPACE / QUALITY"
        title="Evaluation lab"
        description="Inspect the evaluator's persisted C1–C6 decisions, evidence, and requested corrections."
      />
      <section className="panel evaluation-selector">
        <div className="selector-copy">
          <div className="metric-icon metric-violet"><ShieldCheck size={17} /></div>
          <div>
            <strong>{t("Choose an execution")}</strong>
            <span>{t("All executions are shown; failed evaluator runs include their saved diagnostics.")}</span>
          </div>
        </div>
        <select
          aria-label={t("Select an execution to inspect")}
          value={selectedId}
          onChange={(event) => setSelectedId(event.target.value)}
        >
          <option value="">{t("Select an execution")}</option>
          {history?.items
            .map((run) => (
              <option value={run.run_id} key={run.run_id}>
                {run.topic} · {run.run_id.slice(0, 8)} · {run.status} · {run.evaluation_count > 0 ? t("{count} saved evaluations", { count: run.evaluation_count }) : t("No saved evaluation")}
              </option>
            ))}
        </select>
      </section>
      {error && <ErrorState message={error} />}
      {loading && <LoadingState label="Loading persisted evaluation" />}
      {!loading && history?.total === 0 && (
        <EmptyState
          title="No executions yet"
          description="Start a lesson generation run to see its saved evaluation and checkpoint evidence here."
        />
      )}
      {!loading && selectedId && detail && (
        <>
          {detail.evaluations.length === 0 ? (
            <section className="panel no-evaluation-panel">
              <StatusPill status={detail.status} />
              {detail.job_status === "running" || detail.job_status === "queued" ? (
                <div className="evaluation-no-result">
                  <strong>{t("Evaluation is still in progress.")}</strong>
                  <p>{t("The C1–C6 feedback will appear here as soon as the evaluator saves its result.")}</p>
                </div>
              ) : (
                <>
                  <h2>{t("No evaluation result was saved")}</h2>
                  {detail.failed_evaluation_attempts.map((failure) => (
                    <div className="evaluation-no-result" key={failure.failure_id}>
                      <strong>{t(failure.error_category === "evaluation_validation_error" ? "Evaluator validation failed" : "Evaluation request failed")}</strong>
                      <span>{failure.failure_stage.replaceAll("_", " ")} · {failure.error_category} · {failure.error_type}</span>
                      <p><b>{t("Reason")}:</b> {t(evaluationFailureReason(failure.error_category, failure.error_description))}</p>
                    </div>
                  ))}
                  {detail.failed_evaluation_attempts.length === 0 && (
                    <div className="evaluation-no-result">
                      <strong>{t("No C1–C6 checkpoint decision is available for this attempt.")}</strong>
                      <p>{detail.failure_reason ?? t("The run stopped before the evaluator saved a result.")}</p>
                    </div>
                  )}
                </>
              )}
              {detail.rejections.map((rejection) => (
                <div className="evaluation-failed-checks" key={rejection.rejection_id}>
                  <strong>{t("Attempt {count} failed checks", { count: rejection.attempt_number })}</strong>
                  {rejection.failed_checkpoints.map((checkpoint) => (
                    <article key={checkpoint}>
                      <b>{checkpoint}</b>
                      <p><strong>{t("Why it failed")}:</strong> {rejection.failure_reasons[checkpoint] ?? t("No reason was saved.")}</p>
                      <p><strong>{t("Required correction")}:</strong> {rejection.correction_instructions.find((instruction) => instruction.startsWith(`${checkpoint}:`)) ?? t("No correction was saved.")}</p>
                    </article>
                  ))}
                </div>
              ))}
              {detail.failure_reason && detail.failed_evaluation_attempts.length === 0 && (
                <p>{detail.failure_reason}</p>
              )}
              {detail.failed_generation_attempts.map((failure) => (
                <div className="diagnostic-card" key={failure.failure_id}>
                  <strong>{failure.failure_stage.replaceAll("_", " ")}</strong>
                  <span>{failure.error_category} · {failure.error_type}</span>
                  <p><strong>{t("Failure reason")}:</strong> {failure.error_description}</p>
                </div>
              ))}
            </section>
          ) : (
            detail.evaluations.map((evaluation) => (
              <section className="panel evaluation-attempt-panel" key={evaluation.evaluation_id}>
                <div className="panel-heading">
                  <div>
                    <span className="eyebrow">ATTEMPT {evaluation.attempt_number}</span>
                    <h2>{t("Six-checkpoint evaluation")}</h2>
                  </div>
                  <StatusPill status={evaluation.overall_status} />
                </div>
                <p className="evaluation-overall">{evaluation.overall_reason}</p>
                {evaluation.failed_checkpoints.length > 0 && (
                  <div className="evaluation-failed-checks" aria-live="polite">
                    <span className="eyebrow">{t("FAILED CHECKS AND REQUIRED CORRECTIONS")}</span>
                    {evaluation.failed_checkpoints.map((checkpointId) => {
                      const checkpoint = evaluation.checkpoints.find(
                        (item) => item.checkpoint_id === checkpointId,
                      );
                      const correction = evaluation.correction_instructions.find(
                        (instruction) => instruction.trim().toUpperCase().startsWith(`${checkpointId}:`),
                      );
                      return (
                        <article key={checkpointId}>
                          <strong>{checkpointId} · {t("Fail")}</strong>
                          <p><b>{t("Why it failed")}:</b> {checkpoint?.reason ?? t("No reason was saved.")}</p>
                          <p><b>{t("Required correction")}:</b> {correction ?? t("No correction was saved.")}</p>
                        </article>
                      );
                    })}
                  </div>
                )}
                <CheckpointCards evaluation={evaluation} />
              </section>
            ))
          )}
        </>
      )}
    </>
  );
}

