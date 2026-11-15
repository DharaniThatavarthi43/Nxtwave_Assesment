import {
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  Bot,
  CheckCircle2,
  CircleAlert,
  Clock3,
  Layers3,
  Sparkles,
} from "lucide-react";
import { useEffect, useState } from "react";
import { lazy, Suspense } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Link } from "react-router-dom";
import { api } from "../api";
import type { Dashboard } from "../types";
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

const KnowledgeEngine = lazy(async () => ({
  default: (await import("../components/KnowledgeEngine")).KnowledgeEngine,
}));

export function OverviewPage() {
  const { t } = useLanguage();
  const [data, setData] = useState<Dashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    setError(null);
    void api.dashboard().then(
      (value) => {
        setData(value);
        setLoading(false);
      },
      (reason: Error) => {
        setError(reason.message);
        setLoading(false);
      },
    );
  };

  useEffect(load, []);

  return (
    <>
      <PageTitle
        eyebrow="OVERVIEW / WORKSPACE"
        title="Your AI learning engine"
        description="Generate. Evaluate. Improve. Learn."
        action={
          <Link className="button button-primary" to="/generate">
            <Sparkles size={16} /> {t("New generation")}
          </Link>
        }
      />
      {error && <ErrorState message={error} onRetry={load} />}
      {loading && <LoadingState />}
      {data && (
        <>
          <div className="metric-grid">
            <MetricCard
              label={t("Total executions")}
              value={data.total_executions}
              icon={<Layers3 size={17} />}
              note={t("{count} failed safely", { count: data.failed_executions })}
              tone="violet"
            />
            <MetricCard
              label={t("Approved lessons")}
              value={data.approved_executions}
              icon={<CheckCircle2 size={17} />}
              note={
                data.approval_rate === null
                  ? t("No completed decisions yet")
                  : t("{percent}% of completed runs", { percent: Math.round(data.approval_rate * 100) })
              }
              tone="green"
            />
            <MetricCard
              label={t("Rejected executions")}
              value={data.rejected_executions}
              icon={<CircleAlert size={17} />}
              note={t("Final lesson was not approved")}
              tone="orange"
            />
            <MetricCard
              label={t("Generation attempts")}
              value={data.total_generation_attempts}
              icon={<Clock3 size={17} />}
              note={t("Maximum 3 per execution")}
              tone="cyan"
            />
            <MetricCard
              label={t("Mean checkpoint pass")}
              value={
                data.mean_checkpoint_pass_rate === null
                  ? "—"
                  : `${Math.round(data.mean_checkpoint_pass_rate * 100)}%`
              }
              icon={<Bot size={17} />}
              note={t("Across persisted evaluations")}
              tone="blue"
            />
            <MetricCard
              label={t("Active learned rules")}
              value={data.active_learned_rules}
              icon={<Sparkles size={17} />}
              note={t("Validated, persistent guidance")}
              tone="pink"
            />
          </div>

          <div className="overview-feature-grid">
            <Suspense fallback={<div className="engine-loading panel">{t("Loading knowledge visualization…")}</div>}>
              <KnowledgeEngine />
            </Suspense>
            <section className="panel quick-start-panel">
              <span className="eyebrow">{t("READY WHEN YOU ARE")}</span>
              <div className="quick-start-icon"><Sparkles size={20} /></div>
              <h2>{t("Make the next lesson better.")}</h2>
              <p>
                {t("Start an Introduction to RAG run. The evaluator checks six fixed criteria, and the workflow stores every completed attempt.")}
              </p>
              <Link className="button button-primary button-wide" to="/generate">
                {t("Open generation studio")} <ArrowRight size={15} />
              </Link>
              <div className="quick-facts">
                <span><i /> {t("6 mandatory checkpoints")}</span>
                <span><i /> {t("Up to 3 generations")}</span>
                <span><i /> {t("SQLite-backed history")}</span>
              </div>
            </section>
          </div>

          <div className="chart-grid">
            <section className="panel chart-panel">
              <div className="panel-heading">
                <div>
                  <span className="eyebrow">{t("QUALITY SIGNAL")}</span>
                  <h2>{t("Checkpoint failure frequency")}</h2>
                </div>
                <span className="panel-note">{t("From persisted evaluations")}</span>
              </div>
              {data.checkpoint_failures.every((item) => item.failure_count === 0) ? (
                <EmptyState
                  title="No failures recorded"
                  description="Checkpoint trends appear after real evaluations are stored."
                />
              ) : (
                <div className="chart-wrap chart-wrap-bar">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={data.checkpoint_failures} barSize={30}>
                      <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
                      <XAxis
                        dataKey="checkpoint_id"
                        tickLine={false}
                        axisLine={false}
                        tick={{ fill: "var(--muted)", fontSize: 9 }}
                      />
                      <YAxis
                        allowDecimals={false}
                        tickLine={false}
                        axisLine={false}
                        tick={{ fill: "var(--muted)", fontSize: 9 }}
                      />
                      <Tooltip
                        contentStyle={{
                          background: "var(--tooltip-bg)",
                          border: "1px solid var(--tooltip-border)",
                          borderRadius: 12,
                        }}
                      />
                      <Bar dataKey="failure_count" fill="var(--chart-failure)" radius={[6, 6, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </section>
            <section className="panel chart-panel">
              <div className="panel-heading">
                <div>
                  <span className="eyebrow">{t("RUN ACTIVITY")}</span>
                  <h2>{t("Execution outcomes")}</h2>
                </div>
                <span className="panel-note">{t("By persisted start date")}</span>
              </div>
              {data.executions_by_day.length === 0 ? (
                <EmptyState
                  title="No activity yet"
                  description="Completed runs will appear here with their actual final status."
                />
              ) : (
                <div className="chart-wrap">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={data.executions_by_day}>
                      <defs>
                        <linearGradient id="approvedGradient" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="var(--chart-approved)" stopOpacity={0.28} />
                          <stop offset="95%" stopColor="var(--chart-approved)" stopOpacity={0} />
                        </linearGradient>
                        <linearGradient id="rejectedGradient" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="var(--chart-rejected)" stopOpacity={0.2} />
                          <stop offset="95%" stopColor="var(--chart-rejected)" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
                      <XAxis
                        dataKey="date"
                        tickLine={false}
                        axisLine={false}
                        tick={{ fill: "var(--muted)", fontSize: 9 }}
                      />
                      <YAxis
                        allowDecimals={false}
                        tickLine={false}
                        axisLine={false}
                        tick={{ fill: "var(--muted)", fontSize: 9 }}
                      />
                      <Tooltip
                        contentStyle={{
                          background: "var(--tooltip-bg)",
                          border: "1px solid var(--tooltip-border)",
                          borderRadius: 12,
                        }}
                      />
                      <Area
                        type="monotone"
                        dataKey="approved"
                        stroke="var(--chart-approved)"
                        fill="url(#approvedGradient)"
                      />
                      <Area
                        type="monotone"
                        dataKey="rejected"
                        stroke="var(--chart-rejected)"
                        fill="url(#rejectedGradient)"
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              )}
              <div className="chart-legend">
                <span><i className="legend-green" /> {t("Approved")}</span>
                <span><i className="legend-orange" /> {t("Rejected")}</span>
              </div>
            </section>
          </div>

          <section className="panel recent-panel">
            <div className="panel-heading">
              <div>
                <span className="eyebrow">{t("PERSISTED ACTIVITY")}</span>
                <h2>{t("Recent executions")}</h2>
              </div>
              <Link className="text-link" to="/history">
                {t("All executions")} <ArrowUpRight size={14} />
              </Link>
            </div>
            {data.recent_runs.length === 0 ? (
              <EmptyState
                title="Your run history starts here"
                description="No execution records exist in SQLite yet. Start a run to see its real lifecycle."
                action={
                  <Link className="button button-secondary button-small" to="/generate">
                    {t("Create first run")} <ArrowRight size={14} />
                  </Link>
                }
              />
            ) : (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>{t("Topic / run ID")}</th>
                      <th>{t("Started")}</th>
                      <th>{t("Generations")}</th>
                      <th>{t("Status")}</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {data.recent_runs.map((run) => (
                      <tr key={run.run_id}>
                        <td>
                          <strong>{run.topic}</strong>
                          <code className="sub-cell">{run.run_id.slice(0, 8)}…</code>
                        </td>
                        <td>{formatDate(run.created_at)}</td>
                        <td>{run.attempt_count}</td>
                        <td><StatusPill status={run.status} /></td>
                        <td><RunLink runId={run.run_id} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
          <div className="footer-note">
            <ArrowDownRight size={14} />
            {t("Metrics are calculated from persisted SQLite records; no sample statistics are shown.")}
          </div>
        </>
      )}
    </>
  );
}

function MetricCard({
  label,
  value,
  icon,
  note,
  tone,
}: {
  label: string;
  value: string | number;
  icon: React.ReactNode;
  note: string;
  tone: string;
}) {
  return (
    <article className="metric-card panel">
      <div className={`metric-icon metric-${tone}`}>{icon}</div>
      <span className="metric-label">{label}</span>
      <strong className="metric-value">{value}</strong>
      <span className="metric-note">{note}</span>
    </article>
  );
}
