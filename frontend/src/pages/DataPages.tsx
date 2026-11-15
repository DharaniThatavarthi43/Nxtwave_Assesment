import {
  BookOpen,
  BrainCircuit,
  Database,
  Network,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import type {
  AppSettings,
  Knowledge,
  LearnedRule,
  RejectionFailureItem,
  RejectionLogResponse,
  RejectionListItem,
} from "../types";
import { MarkdownContent } from "../components/MarkdownContent";
import { useLanguage } from "../language";
import {
  EmptyState,
  ErrorState,
  formatDate,
  LoadingState,
  PageTitle,
  RunLink,
  StatusPill,
} from "../components/Shared";

const checkpointLabel: Record<string, string> = {
  C1: "Accuracy & grounding",
  C2: "Beginner-friendly language",
  C3: "Teaching through examples",
  C4: "Clear explanations",
  C5: "Key concept coverage",
  C6: "Teaching flow",
};

export function RejectionsPage() {
  const { t } = useLanguage();
  const [records, setRecords] = useState<RejectionListItem[] | null>(null);
  const [failures, setFailures] = useState<RejectionFailureItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const refreshRef = useRef<((manual?: boolean) => Promise<void>) | undefined>(undefined);

  useEffect(() => {
    let active = true;
    let timer: number | undefined;

    const refresh = async (manual = false) => {
      if (timer !== undefined) {
        window.clearTimeout(timer);
        timer = undefined;
      }
      if (manual) setRefreshing(true);
      try {
        const value: RejectionLogResponse = await api.rejections();
        if (active) {
          setRecords(value.items);
          setFailures(value.failures);
          setError(null);
          setLastUpdated(new Date());
        }
      } catch (reason) {
        if (active) {
          setError(
            reason instanceof Error ? reason.message : String(reason),
          );
        }
      } finally {
        if (active) {
          setLoading(false);
          setRefreshing(false);
          timer = window.setTimeout(() => void refresh(), 1500);
        }
      }
    };

    refreshRef.current = refresh;

    void refresh();
    return () => {
      active = false;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, []);

  const groupedRecords = useMemo(() => {
    const groups = new Map<
      string,
      { topic: string | null; finalStatus: string | null; records: RejectionListItem[] }
    >();
    for (const item of records ?? []) {
      let group = groups.get(item.rejection.run_id);
      if (!group) {
        group = { topic: item.topic, finalStatus: item.final_status, records: [] };
        groups.set(item.rejection.run_id, group);
      }
      group.records.push(item);
    }
    for (const group of groups.values()) {
      group.records.sort(
        (left, right) =>
          left.rejection.attempt_number - right.rejection.attempt_number,
      );
    }
    return [...groups.entries()];
  }, [records]);

  const counts = useMemo(() => {
    const result = new Map<string, number>();
    for (const item of records ?? []) {
      for (const checkpoint of item.rejection.failed_checkpoints) {
        result.set(checkpoint, (result.get(checkpoint) ?? 0) + 1);
      }
    }
    return [...result.entries()].sort((a, b) => b[1] - a[1]);
  }, [records]);

  return (
    <>
      <PageTitle
        eyebrow="WORKSPACE / FEEDBACK"
        title="Rejection logs"
        description="Understand which quality checks failed and what correction guidance was persisted."
        action={<button className="button button-secondary" onClick={() => void refreshRef.current?.(true)} disabled={refreshing}><RefreshCw size={15} /> {refreshing ? t("Refreshing") : t("Refresh rejection log")}</button>}
      />
      {error && <ErrorState message={error} />}
      {loading && <LoadingState />}
      {records && (
        <>
          <div className="rejection-refresh-status">{lastUpdated ? t("Saved rejection log refreshed {date}", { date: formatDate(lastUpdated.toISOString()) }) : t("Loading saved rejection recordsâ€¦")}</div>
          <section className="rejection-summary-grid">
            <div className="panel rejection-summary-card">
              <span className="eyebrow">{t("PERSISTED REJECTIONS")}</span>
              <strong>{records.length}</strong>
              <span>{t("Showing the latest {count} records available to the API.", { count: records.length })}</span>
            </div>
            <div className="panel rejection-summary-card">
              <span className="eyebrow">{t("WORKFLOW FAILURES")}</span>
              <strong>{failures.length}</strong>
              <span>{t("Generation and evaluator failures from saved run diagnostics.")}</span>
            </div>
            <div className="panel rejection-summary-card wide">
              <span className="eyebrow">{t("CHECKPOINT FAILURE FREQUENCY")}</span>
              {counts.length === 0 ? (
                <p>{t("No checkpoint rejections have been recorded.")}</p>
              ) : (
                <div className="frequency-list">
                  {counts.map(([checkpoint, count]) => (
                    <div className="frequency-row" key={checkpoint}>
                      <span>{checkpoint} Â· {t(checkpointLabel[checkpoint])}</span>
                      <div className="frequency-track">
                        <i style={{ width: `${Math.min(100, (count / counts[0][1]) * 100)}%` }} />
                      </div>
                      <strong>{count}</strong>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </section>

          {failures.length > 0 && (
            <section className="panel rejection-list-panel" aria-live="polite">
              <div className="panel-heading">
                <div>
                  <span className="eyebrow">{t("GENERATION / EVALUATION FAILURES")}</span>
                  <h2>{t("Runs that stopped before a checkpoint decision")}</h2>
                </div>
              </div>
              <div className="rejection-list">
                {failures.map((failure) => (
                  <article className="diagnostic-card" key={failure.failure_id}>
                    <strong>
                      {failure.topic ?? t("Unknown topic")} · {failure.failure_kind === "evaluation" ? t("Evaluator") : t("Generation")} A{failure.attempt_number}
                    </strong>
                    <span>{failure.failure_stage.replaceAll("_", " ")} · {failure.error_category} · {failure.error_type}</span>
                    <p>
                      <strong>{t("Failure reason")}:</strong>{" "}
                      {failure.error_category === "evaluation_validation_error" &&
                      failure.error_description === "Evaluator output failed application validation."
                        ? t("The evaluator response failed validation before C1–C6 results were saved. No checkpoint-specific reason is available for this attempt.")
                        : failure.error_description}
                    </p>
                    <RunLink runId={failure.run_id} />
                  </article>
                ))}
              </div>
            </section>
          )}

          <section className="panel rejection-list-panel">
            <div className="panel-heading">
              <div>
                <span className="eyebrow">{t("RUN FEEDBACK")}</span>
                <h2>{t("Why an attempt was rejected")}</h2>
              </div>
            </div>
            {records.length === 0 ? (
              <EmptyState
                title="No rejection records"
                description={failures.length > 0 ? "This run stopped before a checkpoint rejection could be recorded. See the workflow failure details above." : "The rejection log will show actual checkpoint failures once an evaluation rejects an attempt."}
              />
            ) : (
              <div className="rejection-list">
                {groupedRecords.map(([runId, group]) => (
                  <section className="rejection-run-group" key={runId}>
                    <div className="rejection-run-heading">
                      <div>
                        <span className="eyebrow">{t("RUN HISTORY")}</span>
                        <strong>{group.topic ?? t("Unknown topic")}</strong>
                        <code>{runId}</code>
                      </div>
                      {group.finalStatus && <StatusPill status={group.finalStatus} />}
                    </div>
                    {group.records.map(({ rejection, feedback_sent, retry_attempt_status }) => (
                      <article className="rejection-entry" key={rejection.rejection_id}>
                        <div className="rejection-entry-header">
                          <span className="rejection-attempt">A{rejection.attempt_number}</span>
                          <span className="rejection-summary-copy">
                            <strong>{rejection.failed_checkpoints.join(", ")}</strong>
                            <span>{formatDate(rejection.created_at)}</span>
                          </span>
                          <span
                            className={`retry-outcome ${
                              retry_attempt_status === "PASS"
                                ? "passed"
                                : retry_attempt_status === "FAIL"
                                  ? "failed"
                                  : ""
                            }`}
                          >
                            {rejection.retry_attempt_number === null
                              ? t("No retry")
                              : `${t("Retry")} A${rejection.retry_attempt_number}: ${
                                  retry_attempt_status ?? t("Not evaluated")
                                }`}
                          </span>
                        </div>
                        <div className="rejection-summary-reasons" aria-label={t("Failure reasons")}>
                          {rejection.failed_checkpoints.map((checkpoint) => (
                            <p key={checkpoint}>
                              <strong>{checkpoint} · {t(checkpointLabel[checkpoint])}</strong>
                              <span><b>{t("Reason")}:</b> {rejection.failure_reasons[checkpoint] ?? t("No reason was persisted.")}</span>
                            </p>
                          ))}
                        </div>
                        <details className="rejection-more">
                          <summary>
                            <span>{t("View evidence and retry details")}</span>
                            <span className="disclosure-chevron" />
                          </summary>
                        <div className="rejection-entry-body">
                          {rejection.failed_checkpoints.map((checkpoint) => (
                            <div className="rejection-checkpoint" key={checkpoint}>
                              <strong>{checkpoint} Â· {t(checkpointLabel[checkpoint])}</strong>
                              <p>{rejection.failure_reasons[checkpoint] ?? t("No reason was persisted.")}</p>
                              <blockquote>{rejection.evidence[checkpoint] ?? t("No evidence was persisted.")}</blockquote>
                              <span className="eyebrow">{t("CORRECTION REQUIRED")}</span>
                              <p>
                                {rejection.correction_instructions.find((instruction) =>
                                  instruction.startsWith(`${checkpoint}:`),
                                ) ?? t("No checkpoint-specific correction was persisted.")}
                              </p>
                            </div>
                          ))}
                          <div className="feedback-columns">
                            <div>
                              <span className="eyebrow">{t("EXACT FEEDBACK SENT TO GENERATOR")}</span>
                              {feedback_sent.length > 0 ? (
                                feedback_sent.map((feedback) => (
                                  <pre className="rejection-feedback" key={feedback}>{feedback}</pre>
                                ))
                              ) : (
                                <p>{t("No retry feedback was sent for this attempt.")}</p>
                              )}
                            </div>
                            <div>
                              <span className="eyebrow">{t("CORRECTION / CHANGE RECORD")}</span>
                              <p>{rejection.correction_applied || t("No correction status was recorded.")}</p>
                              <p>{rejection.changes_made || t("No change description was recorded.")}</p>
                            </div>
                          </div>
                          <RunLink runId={rejection.run_id} />
                        </div>
                        </details>
                      </article>
                    ))}
                  </section>
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </>
  );
}

export function LearningPage() {
  const { t } = useLanguage();
  const [rules, setRules] = useState<LearnedRule[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void api.learnedRules().then(
      (value) => {
        setRules(value);
        setLoading(false);
      },
      (reason: Error) => {
        setError(reason.message);
        setLoading(false);
      },
    );
  }, []);

  const active = rules?.filter((item) => item.rule.active_status).length ?? 0;
  return (
    <>
      <PageTitle
        eyebrow="WORKSPACE / SELF-EVOLUTION"
        title="Learning memory"
        description="Persistent rules created from repeated failures in distinct runsâ€”not default prompt instructions."
      />
      <section className="learning-flow panel">
        <div><Network size={18} /><span>{t("Repeated failure")}</span></div>
        <i />
        <div><BrainCircuit size={18} /><span>{t("Pattern threshold")}</span></div>
        <i />
        <div><ShieldCheck size={18} /><span>{t("Validated guidance")}</span></div>
        <i />
        <div><SparkleIcon /><span>{t("Future generation")}</span></div>
      </section>
      {error && <ErrorState message={error} />}
      {loading && <LoadingState />}
      {rules && (
        <>
          <div className="memory-stats">
            <div className="panel memory-stat"><span>{t("Stored rules")}</span><strong>{rules.length}</strong></div>
            <div className="panel memory-stat"><span>{t("Active")}</span><strong>{active}</strong></div>
            <div className="panel memory-stat"><span>{t("Inactive / rejected")}</span><strong>{rules.length - active}</strong></div>
          </div>
          {rules.length === 0 ? (
            <EmptyState
              title="No learned rules yet"
              description="Rules are persisted only after the same checkpoint failure recurs across distinct runs and passes the safety allowlist."
            />
          ) : (
            <div className="rule-grid">
              {rules.map(({ rule, distinct_supporting_runs }) => (
                <article className={`panel rule-card ${rule.active_status ? "" : "rule-inactive"}`} key={rule.rule_id}>
                  <div className="rule-card-top">
                    <span className="checkpoint-id">{rule.related_checkpoint}</span>
                    <span className={`rule-status ${rule.active_status ? "active" : "inactive"}`}>
                      <i /> {t(rule.active_status ? "ACTIVE" : "INACTIVE")}
                    </span>
                  </div>
                  <h3>{rule.rule_description}</h3>
                  <p>{rule.rationale}</p>
                  <div className="rule-meta">
                    <span>{t("{count} distinct runs", { count: distinct_supporting_runs })}</span>
                    <span>{t("{percent}% confidence", { percent: Math.round(rule.confidence * 100) })}</span>
                  </div>
                  <div className="rule-dates">
                    <span>{t("Created {date}", { date: formatDate(rule.created_at) })}</span>
                    <span>{t("Updated {date}", { date: formatDate(rule.updated_at) })}</span>
                  </div>
                </article>
              ))}
            </div>
          )}
          <div className="safety-note">
            <ShieldCheck size={16} />
            {t("Learned rules are validated against an approved checkpoint-specific allowlist. They cannot change or remove C1â€“C6.")}
          </div>
        </>
      )}
    </>
  );
}

export function KnowledgePage() {
  const { t } = useLanguage();
  const [knowledge, setKnowledge] = useState<Knowledge | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void api.knowledge().then(
      (value) => {
        setKnowledge(value);
        setLoading(false);
      },
      (reason: Error) => {
        setError(reason.message);
        setLoading(false);
      },
    );
  }, []);

  return (
    <>
      <PageTitle
        eyebrow="WORKSPACE / SOURCES"
        title="Knowledge base"
        description="Curated reference notes used to ground lesson generation and evaluation."
      />
      {error && <ErrorState message={error} />}
      {loading && <LoadingState label="Loading curated references" />}
      {knowledge && (
        <>
          <section className="panel knowledge-hero">
            <div className="knowledge-hero-icon"><Database size={22} /></div>
            <div>
              <span className="eyebrow">{t("ACTIVE REFERENCE MATERIAL Â· {version}", { version: knowledge.reference_material.version })}</span>
              <h2>{knowledge.reference_material.title}</h2>
              <p>{t("{count} validated sources Â· Curated Markdown Â· Loaded by the Python reference loader", { count: knowledge.reference_material.sources.length })}</p>
            </div>
            <span className="source-active"><i /> {t("ACTIVE")}</span>
          </section>
          <div className="source-grid">
            {knowledge.reference_material.sources.map((source) => (
              <article className="panel source-card" key={source.source_id}>
                <span className="source-id">{source.source_id}</span>
                <h3>{source.title}</h3>
                <a href={source.url} target="_blank" rel="noreferrer">
                  {t("Open original source")} <BookOpen size={13} />
                </a>
              </article>
            ))}
          </div>
          <section className="panel knowledge-notes">
            <div className="panel-heading">
              <div>
                <span className="eyebrow">{t("CANONICAL NOTES")}</span>
                <h2>{t("Reference content used by the workflow")}</h2>
              </div>
              <span className="no-vector-badge">{t("No vector database claimed")}</span>
            </div>
            <MarkdownContent content={knowledge.reference_material.content} />
          </section>
        </>
      )}
    </>
  );
}

export function SettingsPage() {
  const { t } = useLanguage();
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void api.settings().then(
      (value) => {
        setSettings(value);
        setLoading(false);
      },
      (reason: Error) => {
        setError(reason.message);
        setLoading(false);
      },
    );
  }, []);

  return (
    <>
      <PageTitle
        eyebrow="WORKSPACE / CONFIGURATION"
        title="Settings"
        description="Review safe backend configuration. Secrets are never sent to the browser."
      />
      {error && <ErrorState message={error} />}
      {loading && <LoadingState label="Reading safe configuration" />}
      {settings && (
        <div className="settings-grid">
          <section className="panel settings-panel">
            <div className="panel-heading">
              <div><span className="eyebrow">{t("APPLICATION")}</span><h2>{t("Runtime configuration")}</h2></div>
              <ShieldCheck size={18} className="green-icon" />
            </div>
            <SettingRow label="Assessment topic" value={settings.topic} />
            <SettingRow label="Provider" value={settings.provider ?? t("Not configured")} />
            <SettingRow label="Model" value={settings.model ?? t("Not configured")} />
            <SettingRow label="Provider credentials" value={settings.provider_configured ? t("Configured Â· hidden") : t("Not configured")} />
            <SettingRow label="SQLite status" value={settings.database_connected ? t("Connected") : t("Unavailable")} />
            <SettingRow label="Maximum generations" value={`${settings.max_generation_attempts} (${t("{count} retries", { count: settings.max_generation_retries })})`} />
            <SettingRow label="Evaluator API retries" value={`${settings.evaluator_api_retries}`} />
            <SettingRow label="Evaluator Retry-After cap" value={t("{count} seconds", { count: settings.evaluator_max_retry_after_seconds })} />
          </section>
          <section className="panel settings-panel">
            <div className="panel-heading">
              <div><span className="eyebrow">{t("IMMUTABLE RUBRIC")}</span><h2>{t("Mandatory checkpoints")}</h2></div>
              <span className="fixed-badge">{t("FIXED")}</span>
            </div>
            <p className="settings-intro">{t("Every checkpoint is required. The UI cannot adjust the rubric.")}</p>
            <div className="settings-checkpoints">
              {settings.mandatory_checkpoints.map((checkpoint) => (
                <div key={checkpoint}><span className="checkpoint-id">{checkpoint}</span><strong>{t(checkpointLabel[checkpoint])}</strong><ShieldCheck size={15} /></div>
              ))}
            </div>
            <div className="audience-setting">
              <span className="eyebrow">{t("TARGET AUDIENCE")}</span>
              <p>{settings.target_audience}</p>
            </div>
          </section>
        </div>
      )}
    </>
  );
}

function SettingRow({ label, value }: { label: string; value: string }) {
  const { t } = useLanguage();
  return (
    <div className="setting-row">
      <span>{t(label)}</span>
      <strong>{value}</strong>
    </div>
  );
}

function SparkleIcon() {
  return <BrainCircuit size={18} />;
}
