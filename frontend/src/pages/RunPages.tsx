import {
  ArrowDownToLine,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Clipboard,
  Clock3,
  Download,
  FileText,
  Printer,
  ShieldCheck,
  ShieldAlert,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { API_ORIGIN, api } from "../api";
import type { GenerationAttempt, RunDetail } from "../types";
import { useLanguage } from "../language";
import { CheckpointCards } from "../components/CheckpointCards";
import { headingSlug, MarkdownContent } from "../components/MarkdownContent";
import {
  EmptyState,
  ErrorState,
  formatDate,
  LoadingState,
  PageTitle,
  StatusPill,
} from "../components/Shared";

const workflowSteps = [
  { id: "prepare", title: "A · Prepare", description: "Check the topic, load trusted references, open the saved run record, and retrieve relevant learned guidance.", stages: ["queued", "starting", "validating_topic", "loading_reference_knowledge", "initializing_persistence", "retrieving_learned_rules"] },
  { id: "generate", title: "B · Generate", description: "Create the lesson using the selected mode, trusted context, and any feedback from an earlier failed attempt.", stages: ["generating_lesson"] },
  { id: "evaluate", title: "C · Evaluate", description: "Check the lesson against all six criteria. If any check fails and retries remain, save the rejection and send targeted corrections before generating again.", stages: ["evaluating_lesson", "processing_feedback"] },
  { id: "decision", title: "D · Decide", description: "Approve only when all six checks pass. Otherwise mark the run rejected when its retry limit is reached; saved rejection details remain in the log.", stages: ["approved", "rejected", "failed"] },
];

export function RunPage() {
  const { t } = useLanguage();
  const { runId = "" } = useParams();
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedAttempt, setSelectedAttempt] = useState<number | null>(null);

  useEffect(() => {
    let active = true;
    let timer: number | undefined;
    const refresh = async () => {
      try {
        const result = await api.run(runId);
        if (!active) return;
        setDetail(result);
        setError(null);
        setLoading(false);
        if (result.job_status === "running" || result.job_status === "queued") {
          timer = window.setTimeout(refresh, 1200);
        }
      } catch (reason) {
        if (!active) return;
        setError(reason instanceof Error ? reason.message : t("Run status is unavailable."));
        setLoading(false);
        timer = window.setTimeout(refresh, 3500);
      }
    };
    void refresh();
    return () => {
      active = false;
      if (timer) window.clearTimeout(timer);
    };
  }, [runId]);

  useEffect(() => {
    if (detail?.attempts.length) {
      setSelectedAttempt(detail.attempts[detail.attempts.length - 1].attempt_number);
    }
  }, [detail?.attempts.length]);

  const attempt = detail?.attempts.find(
    (item) => item.attempt_number === selectedAttempt,
  );
  const evaluation = detail?.evaluations.find(
    (item) => item.attempt_number === selectedAttempt,
  );
  const finalStatus = detail?.run?.status ?? detail?.status ?? "IN_PROGRESS";
  const terminal = ["APPROVED", "REJECTED", "FAILED"].includes(finalStatus);
  const currentStepIndex = workflowSteps.findIndex((step) => step.stages.includes(detail?.current_stage ?? ""));
  const resolvedStepIndex = currentStepIndex < 0 ? 0 : currentStepIndex;
  const completedStepIndex = terminal ? 3 : currentStepIndex;

  return (
    <>
      <div className="back-link-row">
        <Link className="text-link" to="/history"><ArrowLeft size={14} /> {t("Execution history")}</Link>
        <span className="breadcrumb-slash">/</span>
        <code>{runId}</code>
      </div>
      {detail && (
        <PageTitle
          eyebrow={`${t("Execution")} / ${t(detail.job_status.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase()))}`}
          title={detail.topic}
          description={`${detail.mode === "rag" ? "Knowledge-base grounded · " : "Direct LLM generation · "}Run ${detail.run_id}`}
          action={
            <div className="run-title-actions">
              <StatusPill status={finalStatus} />
            </div>
          }
          titleIsDynamic
        />
      )}
      {loading && !detail &&       <LoadingState label="Connecting to the workflow record" />}
      {error && <ErrorState message={error} />}
      {detail && (
        <>
          <section className="panel live-status-panel" aria-live="polite">
              <div className="live-status-heading">
                <span className="live-pulse" />
                <div>
                  <span className="eyebrow">{t("LIVE WORKFLOW STATUS")}</span>
                  <h2>{stageLabel(detail.current_stage, t)}</h2>
                </div>
                {detail.current_attempt && (
                  <span className="attempt-badge">{t("ATTEMPT {count} / {total}", { count: detail.current_attempt, total: detail.max_retries + 1 })} · {t("{count} retries", { count: detail.max_retries })}</span>
                )}
              </div>
              <p className="workflow-progress-intro">{t("Follow the lesson from input to decision. Hover over or focus a step for details.")}</p>
              <div className="workflow-stepbar" aria-label="Four step lesson workflow">
                {workflowSteps.map((step, index) => {
                  const stepState = index < completedStepIndex ? "complete" : index === resolvedStepIndex && !terminal ? "active" : terminal && index === 3 ? finalStatus.toLowerCase() : "pending";
                  return (
                    <div className={`workflow-stepbar-item ${stepState}`} key={step.id}>
                      <button type="button" className="workflow-step-node" title={step.description} aria-label={`${step.title}: ${step.description}`}>
                        <span>{step.title}</span>
                        <span className="workflow-step-tooltip" role="tooltip">{step.description}</span>
                      </button>
                      {index < workflowSteps.length - 1 && <i className="workflow-step-connector" aria-hidden="true" />}
                    </div>
                  );
                })}
              </div>
              <div className="workflow-current-detail">
                <strong>{t(workflowSteps[terminal ? 3 : resolvedStepIndex].title)}</strong>
                <span>{t(workflowSteps[terminal ? 3 : resolvedStepIndex].description)}</span>
                {detail.current_attempt !== null && <small>{t("Attempt {count} of {total} generations · {retries} retries allowed", { count: detail.current_attempt ?? detail.attempts.length + 1, total: detail.max_retries + 1, retries: detail.max_retries })}</small>}
              </div>
              {detail.rejections.length > 0 && <p className="workflow-retry-explanation">{t("{count} rejection(s) recorded so far. Each rejection shows the failed checks, evidence, and feedback sent for its retry.", { count: detail.rejections.length })}</p>}
              <p className="actual-progress-note">
                {terminal ? t("This is the completed workflow path. Open each step to review what happened.") : t("This view updates from workflow callback events and persisted records. No estimated completion percentage is shown.")}
              </p>
          </section>

          {terminal && (
            <section className={`decision-banner decision-${finalStatus.toLowerCase()}`}>
              <div className="decision-mark">
                {finalStatus === "APPROVED" ? <CheckCircle2 size={22} /> : <ShieldAlert size={22} />}
              </div>
              <div>
                <span className="eyebrow">{t("FINAL WORKFLOW DECISION")}</span>
                <h2>{t(finalStatus === "APPROVED" ? "Lesson approved" : finalStatus === "REJECTED" ? "Lesson rejected" : "Run failed safely")}</h2>
                <p>
                  {t("{count} generation(s) persisted", { count: detail.attempts.length })}
                  {detail.run && ` Â· ${t("Started {date}", { date: formatDate(detail.run.created_at) })}`}
                </p>
              </div>
              {finalStatus === "APPROVED" && (
                <div className="decision-actions">
                  <Link className="button button-primary" to={`/runs/${runId}/lesson`}>
                    {t("Read approved lesson")} <ArrowRight size={15} />
                  </Link>
                  <Link className="button button-secondary" to={`/notes/${runId}`}>
                    Open in Notes
                  </Link>
                </div>
              )}
              {finalStatus === "REJECTED" && (
                <div className="decision-actions">
                  <Link className="button button-secondary" to="/rejections">Open rejection log</Link>
                </div>
              )}
            </section>
          )}

          {detail.output_error && (
            <div className="inline-warning" role="status">{detail.output_error} {t("The decision remains unchanged.")}</div>
          )}

          {detail.failure_reason && finalStatus === "FAILED" && (
            <section className="panel failure-panel">
              <span className="eyebrow">{t("SAFE FAILURE DETAIL")}</span>
              <p>{detail.failure_reason}</p>
              {detail.failed_evaluation_attempts.map((failure) => (
                <div className="diagnostic-card" key={failure.failure_id}>
                  <strong>{failure.failure_stage.replaceAll("_", " ")}</strong>
                  <span>{failure.error_category} Â· {failure.error_type}</span>
                  <p>{failure.error_description}</p>
                </div>
              ))}
              {detail.failed_generation_attempts.map((failure) => (
                <div className="diagnostic-card" key={failure.failure_id}>
                  <strong>{failure.failure_stage.replaceAll("_", " ")}</strong>
                  <span>{failure.error_category} Â· {failure.error_type}</span>
                  {failure.validation_subcode && <span>{failure.validation_subcode}</span>}
                  <p>{failure.error_description}</p>
                </div>
              ))}
            </section>
          )}

          <div className="run-content-grid">
            <section className="panel run-steps-panel">
              <div className="panel-heading">
                <div>
                  <span className="eyebrow">{t("PERSISTED HISTORY")}</span>
                  <h2>{t("Generation timeline")}</h2>
                </div>
                <span className="panel-note">{t("{count} attempts", { count: detail.attempts.length })}</span>
              </div>
              {detail.attempts.length === 0 ? (
                <EmptyState
                  title="No lesson attempt persisted"
                  description="The run stopped before a generated lesson was stored."
                />
              ) : (
                <div className="attempt-list">
                  {detail.attempts.map((item) => {
                    const itemEvaluation = detail.evaluations.find(
                      (result) => result.attempt_number === item.attempt_number,
                    );
                    const passedCount = itemEvaluation?.checkpoints.filter(
                      (checkpoint) => checkpoint.status === "PASS",
                    ).length ?? 0;
                    const hasFailed = itemEvaluation?.overall_status === "FAIL";
                    return (
                      <button
                        key={item.attempt_id}
                        className={`attempt-row ${selectedAttempt === item.attempt_number ? "selected" : ""}`}
                        onClick={() => setSelectedAttempt(item.attempt_number)}
                      >
                        <span className="attempt-number">0{item.attempt_number}</span>
                        <span className="attempt-info">
                          <strong>{t("Generation {count}", { count: item.attempt_number })}</strong>
                          <small>
                            {item.attempt_number === 1 ? "Generated" : "Regenerated"} Â·{" "}
                            {itemEvaluation
                              ? `Evaluated Â· ${passedCount}/6 passed Â· ${
                                  hasFailed
                                    ? item.attempt_number >= 3 || finalStatus === "REJECTED"
                                      ? "Rejected Â· retry limit reached"
                                      : "Retry required"
                                    : "Approved"
                                }`
                              : "Awaiting evaluation"}
                          </small>
                          <small>{item.generated_lesson.title}</small>
                          <time>{formatDate(item.timestamp)}</time>
                        </span>
                        {itemEvaluation ? (
                          <StatusPill status={itemEvaluation.overall_status} />
                        ) : (
                          <span className="status-pill status-failed">{t("No result")}</span>
                        )}
                      </button>
                    );
                  })}
                </div>
              )}
            </section>

            <section className="panel run-evaluation-panel">
              <div className="panel-heading">
                <div>
                  <span className="eyebrow">
                    {evaluation ? t("ATTEMPT {count}", { count: evaluation.attempt_number }) : t("EVALUATION")}
                  </span>
                  <h2>{t("Checkpoint results")}</h2>
                </div>
                {evaluation && <StatusPill status={evaluation.overall_status} />}
              </div>
              {evaluation ? (
                <>
                  <p className="evaluation-overall">
                    <strong>
                      {evaluation.checkpoints.filter((checkpoint) => checkpoint.status === "PASS").length}/6 passed
                    </strong>
                    {" Â· "}{evaluation.overall_reason}
                  </p>
                  <CheckpointCards evaluation={evaluation} />
                  {detail.feedback_sent[String(evaluation.attempt_number)]?.length > 0 && (
                    <div className="feedback-sent">
                      <span className="eyebrow">EXACT FEEDBACK SENT TO THE GENERATOR</span>
                      {detail.feedback_sent[String(evaluation.attempt_number)].map((feedback) => (
                        <pre key={feedback}>{feedback}</pre>
                      ))}
                    </div>
                  )}
                </>
              ) : (
                <EmptyState
                  title={t(attempt ? "Evaluation not persisted" : "Waiting for a lesson")}
                  description={
                    attempt
                      ? t("No successful evaluation result exists for this generation. See the safe diagnostic if the run failed.")
                      : t("Checkpoint evidence appears after the evaluator completes.")
                  }
                />
              )}
            </section>
          </div>

          {selectedAttempt && selectedAttempt > 1 && attempt && (
            <AttemptComparison
              previous={detail.attempts.find(
                (item) => item.attempt_number === selectedAttempt - 1,
              )}
              current={attempt}
            />
          )}

          {detail.rejections.length > 0 && (
            <section className="panel run-feedback-panel">
              <div className="panel-heading">
                <div>
                    <span className="eyebrow">{t("REJECTION LOG Â· {count} RETRIES MAX", { count: detail.max_retries })}</span>
                    <h2>{t("Why lessons failed and what changed")}</h2>
                </div>
              </div>
              <div className="feedback-history">
                {detail.rejections.map((record) => (
                  <article key={record.rejection_id}>
                    <span className="attempt-badge">{t("REJECTED ATTEMPT {count}", { count: record.attempt_number })} Â· {record.retry_attempt_number === null ? t("No retries remaining") : t("Retry {count} of {total}", { count: record.retry_attempt_number - 1, total: detail.max_retries })}</span>
                    <div className="retry-reason">
                      <strong>Retry required Â· {record.failed_checkpoints.join(", ")}</strong>
                      {record.failed_checkpoints.map((checkpoint) => (
                        <p key={checkpoint}>
                          <b>{checkpoint}:</b> {record.failure_reasons[checkpoint]}
                        </p>
                      ))}
                    </div>
                    <p><strong>{t("Requested:")}</strong> {record.correction_instructions.join(" Â· ")}</p>
                    <p><strong>{t("Changes:")}</strong> {record.changes_made || t("Not recorded")}</p>
                  </article>
                ))}
              </div>
            </section>
          )}

          {detail.artifacts.length > 0 && (
            <section className="panel artifact-panel">
              <div className="panel-heading">
                <div><span className="eyebrow">{t("SAVED REPORT FILES")}</span><h2>{t("Execution outputs")}</h2></div>
                <FileText size={17} />
              </div>
              <div className="artifact-grid">
                {detail.artifacts.map((artifact) => (
                  <a
                    className="artifact-link"
                    key={artifact.filename}
                    href={`${API_ORIGIN}${artifact.download_url}`}
                    download
                  >
                    <FileText size={16} />
                    <span>{artifact.filename}</span>
                    <ArrowDownToLine size={14} />
                  </a>
                ))}
              </div>
            </section>
          )}
        </>
      )}
    </>
  );
}

function AttemptComparison({
  previous,
  current,
}: {
  previous: GenerationAttempt | undefined;
  current: GenerationAttempt;
}) {
  if (!previous) return null;
  const headings = [...new Set([
    ...Object.keys(previous.generated_lesson.sections),
    ...Object.keys(current.generated_lesson.sections),
  ])];
  const changedHeadings = headings.filter(
    (heading) =>
      previous.generated_lesson.sections[heading] !==
      current.generated_lesson.sections[heading],
  );
  return (
    <section className="panel attempt-comparison">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">ATTEMPT COMPARISON</span>
          <h2>Generation {previous.attempt_number} â†’ {current.attempt_number}</h2>
        </div>
        <span className="panel-note">
          {changedHeadings.length} changed section{changedHeadings.length === 1 ? "" : "s"}
        </span>
      </div>
      {changedHeadings.length === 0 ? (
        <p className="evaluation-overall">No section content changes were recorded between these attempts.</p>
      ) : (
        <div className="comparison-list">
          {changedHeadings.map((heading) => (
            <article className="comparison-item" key={heading}>
              <h3>{heading}</h3>
              <div className="comparison-columns">
                <div>
                  <span className="eyebrow">ATTEMPT {previous.attempt_number}</span>
                  <pre>{previous.generated_lesson.sections[heading] ?? "Section not present."}</pre>
                </div>
                <div>
                  <span className="eyebrow">ATTEMPT {current.attempt_number}</span>
                  <pre>{current.generated_lesson.sections[heading] ?? "Section not present."}</pre>
                </div>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

export function LessonPage() {
  const { t } = useLanguage();
  const { runId = "" } = useParams();
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [progress, setProgress] = useState(0);
  const article = useRef<HTMLElement>(null);

  useEffect(() => {
    void api.run(runId).then(
      (value) => {
        setDetail(value);
        setLoading(false);
      },
      (reason: Error) => {
        setError(reason.message);
        setLoading(false);
      },
    );
  }, [runId]);

  const chosen = useMemo(() => {
    if (!detail?.attempts.length) return null;
    if (detail.status === "APPROVED") return detail.attempts.at(-1) ?? null;
    if (detail.status === "REJECTED") return bestRejectedCandidate(detail);
    return detail.attempts.at(-1) ?? null;
  }, [detail]);

  useEffect(() => {
    const update = () => {
      const element = article.current;
      if (!element) return;
      const top = element.offsetTop;
      const total = element.offsetHeight - window.innerHeight;
      setProgress(total > 0 ? Math.min(100, Math.max(0, ((window.scrollY - top) / total) * 100)) : 100);
    };
    window.addEventListener("scroll", update, { passive: true });
    update();
    return () => window.removeEventListener("scroll", update);
  }, [chosen]);

  if (loading) return <LoadingState label="Loading persisted lesson" />;
  if (error) return <ErrorState message={error} />;
  if (!detail || !chosen) {
    return (
      <EmptyState
        title="No lesson is available"
        description="This run has no persisted generation attempt to display."
      />
    );
  }

  const approved = detail.status === "APPROVED";
  const markdown = chosen.generated_lesson.full_markdown;
  const download = () => {
    const url = URL.createObjectURL(new Blob([markdown], { type: "text/markdown" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${approved ? "approved" : "rejected"}-lesson-${detail.run_id}.md`;
    anchor.click();
    URL.revokeObjectURL(url);
  };
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(markdown);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      setError(t("Clipboard access is unavailable in this browser."));
    }
  };

  return (
    <div className="reader-page">
      <div className="reading-progress"><i style={{ width: `${progress}%` }} /></div>
      <div className="reader-topline">
        <Link className="text-link" to={`/runs/${runId}`}><ArrowLeft size={14} /> {t("Back to execution")}</Link>
        <StatusPill status={approved ? "APPROVED" : detail.status} />
      </div>
      <header className="reader-header">
        <span className={`reader-decision ${approved ? "approved" : "not-approved"}`}>
          {approved ? <CheckCircle2 size={14} /> : <ShieldAlert size={14} />}
          {t(approved ? "APPROVED LESSON" : detail.status === "REJECTED" ? "REJECTED CANDIDATE Â· NOT APPROVED" : "PERSISTED CANDIDATE")}
        </span>
        <h1>{chosen.generated_lesson.title}</h1>
        <p>{chosen.generated_lesson.topic} Â· {t("Generation {count}", { count: chosen.attempt_number })}</p>
        <div className="reader-meta">
          <span><Clock3 size={14} /> {t("Generated {date}", { date: formatDate(chosen.generated_lesson.generation_timestamp) })}</span>
          <span><ShieldCheck size={14} /> {detail.evaluations.find((item) => item.attempt_number === chosen.attempt_number)?.overall_status ?? t("Evaluation unavailable")}</span>
        </div>
        <div className="reader-actions">
          <button className="button button-secondary button-small" onClick={() => void copy()}>
            <Clipboard size={14} /> {t(copied ? "Copied" : "Copy lesson")}
          </button>
          <button className="button button-secondary button-small" onClick={download}>
            <Download size={14} /> {t("Download Markdown")}
          </button>
          <button className="button button-secondary button-small" onClick={() => window.print()}>
            <Printer size={14} /> {t("Print")}
          </button>
        </div>
      </header>
      <div className="reader-layout">
        <aside className="reader-toc">
          <span className="eyebrow">{t("IN THIS LESSON")}</span>
          {Object.keys(chosen.generated_lesson.sections).map((heading) => (
            <a href={`#${headingSlug(heading)}`} key={heading}>{heading}</a>
          ))}
          <span className="reader-references">
            {t("Sources:")} {chosen.generated_lesson.reference_ids.join(", ")}
          </span>
        </aside>
        <article className="reader-content panel" ref={article}>
          <MarkdownContent content={markdown} />
          {detail.evaluations.find((item) => item.attempt_number === chosen.attempt_number) && (
            <div className="reader-evaluation-note">
              {t("Evaluation:")}{" "}
              <StatusPill
                status={
                  detail.evaluations.find((item) => item.attempt_number === chosen.attempt_number)!
                    .overall_status
                }
              />
            </div>
          )}
        </article>
      </div>
    </div>
  );
}

export function ReportPage() {
  const { t } = useLanguage();
  const { runId = "" } = useParams();
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [report, setReport] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void api.run(runId).then(
      async (value) => {
        if (!active) return;
        setDetail(value);
        const reportArtifact = value.artifacts.find((item) => item.filename === "evaluation_report.md");
        if (reportArtifact) {
          try {
            setReport(await api.artifactText(runId, "evaluation_report.md"));
          } catch {
            if (active) setError(t("The saved report file is unavailable; persisted evaluation data is still shown."));
          }
        }
        if (active) setLoading(false);
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
  }, [runId]);

  if (loading) return <LoadingState label="Loading report and persisted evaluation data" />;
  if (error && !detail) return <ErrorState message={error} />;
  return (
    <>
      <div className="back-link-row">
        <Link className="text-link" to={`/runs/${runId}`}><ArrowLeft size={14} /> {t("Back to execution")}</Link>
      </div>
      <PageTitle
        eyebrow="EXECUTION / REPORT"
        title="Evaluation report"
        description={detail ? `Run ${detail.run_id} Â· ${detail.status}` : undefined}
        action={
          detail?.artifacts.some((item) => item.filename === "evaluation_report.md") ? (
            <a className="button button-secondary" href={`${API_ORIGIN}/api/runs/${runId}/artifacts/evaluation_report.md`} download>
              <Download size={15} /> {t("Download report")}
            </a>
          ) : undefined
        }
      />
      {error && <div className="inline-warning">{error}</div>}
      {report ? (
        <section className="panel report-document"><MarkdownContent content={report} /></section>
      ) : detail?.evaluations.length ? (
        <div className="report-evaluations">
          <div className="report-source-note">
            {t("Saved report file is unavailable. Showing evaluation data persisted in SQLite.")}
          </div>
          {detail.evaluations.map((evaluation) => (
            <section className="panel evaluation-attempt-panel" key={evaluation.evaluation_id}>
              <div className="panel-heading">
                <div><span className="eyebrow">{t("ATTEMPT {count}", { count: evaluation.attempt_number })}</span><h2>{t("Evaluation")}</h2></div>
                <StatusPill status={evaluation.overall_status} />
              </div>
              <p className="evaluation-overall">{evaluation.overall_reason}</p>
              <CheckpointCards evaluation={evaluation} />
            </section>
          ))}
        </div>
      ) : (
        <section className="panel no-evaluation-panel">
          <EmptyState
            title="No persisted evaluation result"
            description={detail?.failure_reason ?? "A report cannot be created for an incomplete or failed evaluation."}
          />
        </section>
      )}
    </>
  );
}

function bestRejectedCandidate(detail: RunDetail): GenerationAttempt | null {
  if (!detail.attempts.length) return null;
  const scores = new Map<number, number>();
  for (const evaluation of detail.evaluations) {
    scores.set(
      evaluation.attempt_number,
      evaluation.checkpoints.filter((checkpoint) => checkpoint.status === "PASS").length,
    );
  }
  return [...detail.attempts].sort(
    (left, right) =>
      (scores.get(right.attempt_number) ?? -1) -
        (scores.get(left.attempt_number) ?? -1) ||
      right.attempt_number - left.attempt_number,
  )[0];
}

function stageLabel(stage: string, t: (text: string) => string) {
  const step = workflowSteps.find((item) => item.stages.includes(stage));
  return t(step?.title ?? stage.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase()));
}
