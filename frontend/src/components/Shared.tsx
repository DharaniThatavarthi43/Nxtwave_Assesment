import { ArrowUpRight, CircleDashed, FileQuestion, RefreshCw } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import type { RunStatus } from "../types";
import { useLanguage, translateText } from "../language";

export function PageTitle({
  eyebrow,
  title,
  description,
  action,
  titleIsDynamic = false,
}: {
  eyebrow: string;
  title: string;
  description?: string;
  action?: ReactNode;
  titleIsDynamic?: boolean;
}) {
  const { t } = useLanguage();
  return (
    <div className="page-title-row">
      <div>
        <div className="eyebrow page-eyebrow">{t(eyebrow)}</div>
        <h1>{titleIsDynamic ? title : t(title)}</h1>
        {description && <p className="page-description">{t(description)}</p>}
      </div>
      {action && <div className="page-title-action">{action}</div>}
    </div>
  );
}

export function StatusPill({ status }: { status: string }) {
  const { t } = useLanguage();
  const normalized = status.toLowerCase();
  const labels: Record<string, string> = {
    APPROVED: "Approved",
    REJECTED: "Rejected",
    FAILED: "Failed",
    IN_PROGRESS: "In progress",
    QUEUED: "Queued",
    PASS: "Pass",
    FAIL: "Fail",
  };
  return (
    <span className={`status-pill status-${normalized}`}>
      <span className="status-dot" />
      {t(labels[status] ?? status.replaceAll("_", " "))}
    </span>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  const { t } = useLanguage();
  return (
    <div className="empty-state">
      <div className="empty-icon"><FileQuestion size={22} /></div>
      <h3>{t(title)}</h3>
      <p>{t(description)}</p>
      {action}
    </div>
  );
}

export function LoadingState({ label = "Loading persisted data" }: { label?: string }) {
  const { t } = useLanguage();
  return (
    <div className="loading-state" role="status">
      <CircleDashed className="spin" size={19} />
      <span>{t(label)}</span>
    </div>
  );
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  const { t } = useLanguage();
  return (
    <div className="error-state" role="alert">
      <div>
        <strong>{t("Something needs attention")}</strong>
        <p>{t(message)}</p>
      </div>
      {onRetry && (
        <button className="button button-secondary button-small" onClick={onRetry}>
          <RefreshCw size={14} /> {t("Retry")}
        </button>
      )}
    </div>
  );
}

export function RunLink({ runId }: { runId: string }) {
  const { t } = useLanguage();
  return (
    <Link className="text-link" to={`/runs/${runId}`}>
      {t("View run")} <ArrowUpRight size={14} />
    </Link>
  );
}

export function formatDate(value: string) {
  const date = new Date(value);
  const locale = document.documentElement.lang || "en-IN";
  if (Number.isNaN(date.getTime())) {
    const language = locale.startsWith("hi") ? "hi" : locale.startsWith("te") ? "te" : "en";
    return translateText("Unknown date", language);
  }
  return new Intl.DateTimeFormat(locale, {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function statusClass(status: RunStatus | string) {
  return `status-${status.toLowerCase()}`;
}
