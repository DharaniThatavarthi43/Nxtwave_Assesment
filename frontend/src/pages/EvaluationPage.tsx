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

export function EvaluationPage() {
  const { t } = useLanguage();
  const [history, setHistory] = useState<RunList | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void api.history({ limit: 100 }).then(
      (result) => {
        setHistory(result);
        const latestEvaluated = result.items.find((run) => run.evaluation_count > 0);
        if (latestEvaluated) setSelectedId(latestEvaluated.run_id);
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
    setLoading(true);
    void api.run(selectedId).then(
      (result) => {
        if (active) {
          setDetail(result);
          setError(null);
          setLoading(false);
        }
      },
      (reason: Error) => {
        if (active) {
          setError(reason.message);
          setLoading(false);
        }
      },
    );
    return () => {
      active = false;
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
            <span>{t("Only saved evaluation records are shown below.")}</span>
          </div>
        </div>
        <select
          aria-label={t("Select an execution to inspect")}
          value={selectedId}
          onChange={(event) => setSelectedId(event.target.value)}
        >
          <option value="">{t("Select an execution")}</option>
          {history?.items
            .filter((run) => run.evaluation_count > 0)
            .map((run) => (
              <option value={run.run_id} key={run.run_id}>
                {run.topic} · {run.run_id.slice(0, 8)} · {run.status}
              </option>
            ))}
        </select>
      </section>
      {error && <ErrorState message={error} />}
      {loading && <LoadingState label="Loading persisted evaluation" />}
      {!loading && history?.items.every((run) => run.evaluation_count === 0) && (
        <EmptyState
          title="No completed evaluations"
          description="An evaluation appears after a generated lesson is checked against all six mandatory criteria."
        />
      )}
      {!loading && selectedId && detail && (
        <>
          {detail.evaluations.length === 0 ? (
            <section className="panel no-evaluation-panel">
              <StatusPill status={detail.status} />
              <h2>{t("No evaluation result was saved")}</h2>
              <p>
                {detail.failure_reason ??
                  t("The evaluator did not produce a persisted result. A failure diagnostic may be available below.")}
              </p>
              {detail.failed_evaluation_attempts.map((failure) => (
                <div className="diagnostic-card" key={failure.failure_id}>
                  <strong>{failure.failure_stage.replaceAll("_", " ")}</strong>
                  <span>{failure.error_category} · {failure.error_type}</span>
                  <p>{failure.error_description}</p>
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
                <CheckpointCards evaluation={evaluation} />
              </section>
            ))
          )}
        </>
      )}
    </>
  );
}
