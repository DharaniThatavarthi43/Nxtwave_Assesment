import { ChevronLeft, ChevronRight, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api";
import type { RunList } from "../types";
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

const pageSize = 25;

export function HistoryPage() {
  const { t } = useLanguage();
  const [data, setData] = useState<RunList | null>(null);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    void api.history({ query, status: status || undefined, offset, limit: pageSize }).then(
      (result) => {
        if (active) {
          setData(result);
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
  }, [query, status, offset]);

  return (
    <>
      <PageTitle
        eyebrow="WORKSPACE / PERSISTENCE"
        title="Execution history"
        description="A searchable view of runs persisted by the Python workflow in SQLite."
      />
      <section className="panel history-panel">
        <div className="history-toolbar">
          <label className="search-field">
            <Search size={16} />
            <input
              aria-label={t("Search by topic or run ID")}
              placeholder={t("Search topic or run ID")}
              value={query}
              onChange={(event) => {
                setOffset(0);
                setQuery(event.target.value);
              }}
            />
          </label>
          <label className="select-field">
            <span className="visually-hidden">{t("Filter by execution status")}</span>
            <select
              value={status}
              onChange={(event) => {
                setOffset(0);
                setStatus(event.target.value);
              }}
            >
              <option value="">{t("All statuses")}</option>
              <option value="APPROVED">{t("Approved")}</option>
              <option value="REJECTED">{t("Rejected")}</option>
              <option value="FAILED">{t("Failed")}</option>
              <option value="IN_PROGRESS">{t("In progress")}</option>
            </select>
          </label>
        </div>
        {error && <ErrorState message={error} />}
        {loading && <LoadingState />}
        {data && !loading && data.items.length === 0 && (
          <EmptyState
            title={t(query || status ? "No matching runs" : "No runs in SQLite yet")}
            description={
              query || status
                ? t("Try a different search or status filter.")
                : t("Start a generation to create the first execution record.")
            }
          />
        )}
        {data && data.items.length > 0 && (
          <>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>{t("Run")}</th>
                    <th>{t("Started")}</th>
                    <th>{t("Updated")}</th>
                    <th>{t("Attempts")}</th>
                    <th>{t("Evaluations")}</th>
                    <th>{t("Status")}</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((run) => (
                    <tr key={run.run_id}>
                      <td>
                        <strong>{run.topic}</strong>
                        <span className="mode-history-label">
                          {run.mode === "rag" ? "NXTWAVE RAG" : "NXTWAVE GPT"}
                        </span>
                        <code className="sub-cell">{run.run_id}</code>
                        {run.failure_reason && <span className="table-failure">{run.failure_reason}</span>}
                      </td>
                      <td>{formatDate(run.created_at)}</td>
                      <td>{formatDate(run.updated_at)}</td>
                      <td>{run.attempt_count}</td>
                      <td>{run.evaluation_count}</td>
                      <td><StatusPill status={run.status} /></td>
                      <td><RunLink runId={run.run_id} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="pagination">
              <span>
                {data.total === 0
                  ? t("No runs")
                  : `${offset + 1}â€“${Math.min(offset + data.items.length, data.total)} of ${data.total}`}
              </span>
              <div>
                <button
                  className="icon-button"
                  aria-label={t("Previous page")}
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - pageSize))}
                >
                  <ChevronLeft size={17} />
                </button>
                <button
                  className="icon-button"
                  aria-label={t("Next page")}
                  disabled={offset + pageSize >= data.total}
                  onClick={() => setOffset(offset + pageSize)}
                >
                  <ChevronRight size={17} />
                </button>
              </div>
            </div>
          </>
        )}
      </section>
    </>
  );
}
