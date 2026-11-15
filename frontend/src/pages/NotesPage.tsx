import {
  ArrowLeft,
  Clipboard,
  Download,
  StickyNote,
} from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { API_ORIGIN, ApiError, api } from "../api";
import { MarkdownContent } from "../components/MarkdownContent";
import {
  EmptyState,
  ErrorState,
  formatDate,
  LoadingState,
  PageTitle,
  StatusPill,
} from "../components/Shared";
import type { ApprovedNote, ApprovedNoteSummary } from "../types";

export function NotesPage() {
  const { runId } = useParams();
  const navigate = useNavigate();
  const [notes, setNotes] = useState<ApprovedNoteSummary[] | null>(null);
  const [selected, setSelected] = useState<ApprovedNote | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [downloadFormat, setDownloadFormat] = useState<"md" | "txt">("md");

  useEffect(() => {
    let active = true;
    void api.notes().then(
      async (result) => {
        if (!active) return;
        setNotes(result.items);
        if (runId) {
          try {
            setSelected(await api.note(runId));
          } catch (reason) {
            if (active) {
              setError(
                reason instanceof ApiError
                  ? reason.message
                  : "The approved note could not be loaded.",
              );
            }
          }
        } else {
          setSelected(null);
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

  const copy = async () => {
    if (!selected) return;
    try {
      await navigator.clipboard.writeText(selected.full_markdown);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      setError("Clipboard access is unavailable in this browser.");
    }
  };

  return (
    <>
      {selected && (
        <div className="back-link-row">
          <Link className="text-link" to="/notes"><ArrowLeft size={14} /> Notes</Link>
          <span className="breadcrumb-slash">/</span>
          <code>{selected.run_id}</code>
        </div>
      )}
      <PageTitle
        eyebrow="WORKSPACE / SAVED LESSONS"
        title={selected?.title ?? "Notes"}
        description={
          selected
            ? "A complete lesson saved from an approved run."
            : "Approved lessons are available here after all six mandatory checkpoints pass."
        }
        action={
          selected ? (
            <StatusPill status={selected.evaluation_status} />
          ) : undefined
        }
        titleIsDynamic={Boolean(selected)}
      />
      {error && <ErrorState message={error} />}
      {loading && <LoadingState label="Loading approved notes from SQLite" />}
      {!loading && notes && !selected && notes.length === 0 && (
        <EmptyState
          title="No approved lessons yet"
          description="Only lessons from approved runs with all six checkpoints passing appear in Notes."
        />
      )}
      {!loading && notes && (
        <div className="notes-layout">
          <section className="panel notes-list-panel">
            <div className="panel-heading">
              <div>
                <span className="eyebrow">APPROVED LESSONS</span>
                <h2>Notes library</h2>
              </div>
              <span className="panel-note">{notes.length} saved</span>
            </div>
            {notes.map((note) => (
              <button
                className={`note-list-item ${selected?.run_id === note.run_id ? "selected" : ""}`}
                key={note.run_id}
                onClick={() => navigate(`/notes/${note.run_id}`)}
              >
                <span className="note-list-icon"><StickyNote size={17} /></span>
                <span className="note-list-copy">
                  <strong>{note.title}</strong>
                  <small>{note.topic}</small>
                  <small>{formatDate(note.created_at)}</small>
                </span>
                <StatusPill status={note.evaluation_status} />
              </button>
            ))}
          </section>

          {selected ? (
            <section className="notes-reader">
              <div className="panel notes-meta">
                <div><span>Topic</span><strong>{selected.topic}</strong></div>
                <div><span>Created</span><strong>{formatDate(selected.created_at)}</strong></div>
                <div><span>Run ID</span><code>{selected.run_id}</code></div>
                <div>
                  <span>Mode / evaluation</span>
                  <strong>{selected.mode === "rag" ? "NXTWAVE RAG" : "NXTWAVE GPT"}</strong>
                  <StatusPill status={selected.evaluation_status} />
                </div>
              </div>
              <div className="reader-actions notes-actions">
                <button className="button button-secondary button-small" onClick={() => void copy()}>
                  <Clipboard size={14} /> {copied ? "Copied" : "Copy lesson"}
                </button>
                <label className="form-label" htmlFor="note-download-format">Format</label>
                <select id="note-download-format" value={downloadFormat} onChange={(event) => setDownloadFormat(event.target.value as "md" | "txt")}>
                  <option value="md">Markdown (.md)</option>
                  <option value="txt">Plain text (.txt)</option>
                </select>
                <a
                  className="button button-secondary button-small"
                  href={`${API_ORIGIN}/api/notes/${selected.run_id}/download?format=${downloadFormat}`}
                  download
                >
                  <Download size={14} /> Download {downloadFormat === "md" ? ".md" : ".txt"}
                </a>
              </div>
              <article className="panel notes-document">
                <MarkdownContent content={selected.full_markdown} />
              </article>
            </section>
          ) : (
            notes.length > 0 && (
              <section className="panel notes-empty-reader">
                <EmptyState
                  title="Open a saved lesson"
                  description="Choose a note to read the full lesson, copy it, or download it as Markdown or text."
                />
              </section>
            )
          )}
        </div>
      )}
    </>
  );
}
