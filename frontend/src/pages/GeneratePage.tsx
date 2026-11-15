import {
  ArrowRight,
  Bot,
  BrainCircuit,
  Check,
  Clock3,
  Database,
  Globe2,
  ShieldCheck,
  Upload,
  Zap,
} from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, api } from "../api";
import { ErrorState, LoadingState, PageTitle } from "../components/Shared";
import { useLanguage } from "../language";
import type { AppSettings, GenerationMode, KnowledgeDocument } from "../types";

const MODE_OPTIONS: Array<{ mode: GenerationMode; title: string; short: string; description: string; badge: string; icon: typeof Bot }> = [
  { mode: "gpt", title: "NxtWave GPT", short: "Direct generation", description: "Generate lessons with the LLM and evaluate them against all six quality checks.", badge: "Prompt-first", icon: Bot },
  { mode: "rag", title: "NxtWave RAG", short: "Knowledge-grounded", description: "Retrieve relevant knowledge-base sources, generate a lesson, and evaluate it against the same six checks.", badge: "Grounded context", icon: BrainCircuit },
];

export function GeneratePage() {
  const { t } = useLanguage();
  const navigate = useNavigate();
  const [mode, setMode] = useState<GenerationMode>("gpt");
  const [topic, setTopic] = useState("");
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [settingsError, setSettingsError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [knowledgeDocs, setKnowledgeDocs] = useState<KnowledgeDocument[]>([]);
  const [selectedKnowledgeId, setSelectedKnowledgeId] = useState<string | null>(null);
  const [urlInput, setUrlInput] = useState("");
  const [knowledgeStatus, setKnowledgeStatus] = useState<{ kind: "success" | "error"; message: string } | null>(null);

  useEffect(() => {
    void api.settings().then(
      setSettings,
      (reason: Error) => setSettingsError(reason.message),
    );
    void api.knowledgeDocuments().then(
      (value) => {
        setKnowledgeDocs(value.documents);
        if (value.documents.length > 0) {
          setSelectedKnowledgeId((previous) => previous ?? value.documents[0].document_id);
        }
      },
      () => undefined,
    );
  }, []);

  const topicIsValid = topic.trim().length > 0;

  const refreshKnowledgeBase = async () => {
    const value = await api.knowledgeDocuments();
    setKnowledgeDocs(value.documents);
    if (value.documents.length > 0 && !selectedKnowledgeId) {
      setSelectedKnowledgeId(value.documents[0].document_id);
    }
  };

  const start = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    if (!topic.trim()) {
      setError(t("Enter a topic to continue."));
      return;
    }
    if (!topicIsValid) {
      setError(t("Choose a topic before starting the generation run."));
      return;
    }
    if (!settings?.provider_configured) {
      setError(t("Configure the LLM provider on the backend before starting a run."));
      return;
    }
    if (starting) return;
    setStarting(true);
    try {
      const requestId = crypto.randomUUID();
      const started = await api.startRun(
        requestId,
        topic.trim(),
        mode,
        mode === "rag" ? selectedKnowledgeId ?? undefined : undefined,
      );
      navigate(`/runs/${started.run_id}`);
    } catch (reason) {
      setError(
        reason instanceof ApiError
          ? reason.message
          : t("The run could not be started. Please try again."),
      );
      setStarting(false);
    }
  };

  const handleAddUrl = async () => {
    const candidate = urlInput.trim();
    if (!candidate) {
      setKnowledgeStatus({ kind: "error", message: "Add a webpage URL before uploading it to the knowledge base." });
      return;
    }
    try {
      await api.addKnowledgeUrl(candidate);
      await refreshKnowledgeBase();
      setUrlInput("");
      setKnowledgeStatus({ kind: "success", message: "Webpage added to the knowledge base." });
    } catch (reason) {
      setKnowledgeStatus({
        kind: "error",
        message: reason instanceof ApiError ? reason.message : "The webpage could not be ingested.",
      });
    }
  };

  const handleUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const supported = [".txt", ".md", ".markdown", ".pdf"];
    const suffix = file.name.toLowerCase();
    if (!supported.some((extension) => suffix.endsWith(extension))) {
      setKnowledgeStatus({
        kind: "error",
        message: "Upload a PDF, TXT, or Markdown document.",
      });
      event.target.value = "";
      return;
    }
    try {
      await api.uploadKnowledgeDocument(file);
      await refreshKnowledgeBase();
      setKnowledgeStatus({ kind: "success", message: `${file.name} was added to the knowledge base.` });
    } catch (reason) {
      setKnowledgeStatus({
        kind: "error",
        message: reason instanceof ApiError ? reason.message : "The document could not be uploaded.",
      });
    } finally {
      event.target.value = "";
    }
  };

  return (
    <>
      <PageTitle
        eyebrow="WORKSPACE / GENERATE"
        title="NxtWave AI Studio"
        description={t("Choose NxtWave GPT for direct generation or NxtWave RAG for Knowledge Base references. Both modes use the same six evaluation checks and two retries.")}
      />
      {settingsError && <ErrorState message={settingsError} />}
      {!settings && !settingsError && <LoadingState label="Loading backend configuration" />}
      {settings && (
        <div className="generate-layout">
          <section className="panel generate-form-panel">
            <div className="form-section-heading">
              <div className="step-number">01</div>
              <div>
                <span className="eyebrow">{t("STUDIO MODE")}</span>
                <h2>{t("Choose a generation mode")}</h2>
                <p>{t("Choose direct LLM generation or knowledge-base-grounded RAG. Both modes use the same six evaluation checkpoints and two retries.")}</p>
              </div>
            </div>

            <div className="mode-grid" aria-label="Generation mode selector">
              {MODE_OPTIONS.map(({ mode: optionMode, title, short, description, badge, icon: Icon }) => {
                const active = optionMode === mode;
                return (
                  <button
                    key={optionMode}
                    type="button"
                    className={`mode-card ${active ? "mode-card-active" : ""}`}
                    onClick={() => {
                      setMode(optionMode);
                    }}
                  >
                    <div className="mode-card-top">
                      <span className="mode-icon"><Icon size={18} /></span>
                      <span className="mode-badge">{badge}</span>
                    </div>
                    <h3>{title}</h3>
                    <p className="mode-short">{short}</p>
                    <p>{description}</p>
                    {active && <span className="mode-selected">Selected</span>}
                  </button>
                );
              })}
            </div>

            <div className="form-section-heading compact-heading">
              <div className="step-number">02</div>
              <div>
                <span className="eyebrow">{t("PROMPT")}</span>
                <h2>{t("What should the lesson explain?")}</h2>
                <p>
                  {t("Enter a topic. Both generation modes are evaluated against the same six quality checks.")}
                </p>
              </div>
            </div>

            {error && <ErrorState message={error} />}
            <form onSubmit={start}>
              <label className="form-label" htmlFor="topic-input">{t("Lesson topic")}</label>
              <div className={`topic-input-wrap ${topic && !topicIsValid ? "input-invalid" : ""}`}>
                <Bot size={17} />
                <input
                  id="topic-input"
                  name="topic"
                  value={topic}
                  maxLength={120}
                  onChange={(event) => setTopic(event.target.value)}
                  placeholder="Explain RAG for beginners"
                  aria-describedby="topic-help topic-count"
                />
                {topicIsValid && <Check size={17} className="input-check" />}
              </div>
              <div className="input-meta">
                <span id="topic-help">{topicIsValid ? t("Topic accepted for generation") : t("Choose a topic before starting the run.")}</span>
                <span id="topic-count">{topic.length}/120</span>
              </div>

              <div className="target-audience-box">
                <div className="audience-icon"><Bot size={16} /></div>
                <div>
                  <span className="eyebrow">{t("TARGET LEARNER")}</span>
                  <p>{settings.target_audience}</p>
                </div>
              </div>

              {mode === "rag" && (
                <div className="knowledge-panel panel-inset">
                  <div className="panel-heading compact-heading">
                    <div>
                      <span className="eyebrow">{t("KNOWLEDGE BASE")}</span>
                      <h2>{t("Add sources")}</h2>
                    </div>
                    <Database size={18} className="green-icon" />
                  </div>
                  <div className="knowledge-url-row">
                    <input
                      value={urlInput}
                      onChange={(event) => setUrlInput(event.target.value)}
                      placeholder="https://example.com/guide"
                    />
                    <button type="button" className="button button-secondary" onClick={handleAddUrl}>
                      <Globe2 size={14} /> {t("Add URL")}
                    </button>
                  </div>
                  <label className="upload-control" htmlFor="knowledge-upload">
                    <Upload size={15} />
                    <span>{t("Upload PDF / TXT / Markdown")}</span>
                    <input id="knowledge-upload" type="file" accept=".pdf,.txt,.md,.markdown" onChange={handleUpload} />
                  </label>
                  {knowledgeStatus && (
                    <p className={`knowledge-status ${knowledgeStatus.kind}`}>{knowledgeStatus.message}</p>
                  )}
                  {knowledgeDocs.length > 0 && (
                    <div className="knowledge-doc-list">
                      <label className="form-label" htmlFor="knowledge-document-select">{t("Selected reference document")}</label>
                      <select
                        id="knowledge-document-select"
                        value={selectedKnowledgeId ?? ""}
                        onChange={(event) => setSelectedKnowledgeId(event.target.value || null)}
                      >
                        {knowledgeDocs.map((document) => (
                          <option key={document.document_id} value={document.document_id}>
                            {document.title} ({document.chunk_count} chunks)
                          </option>
                        ))}
                      </select>
                    </div>
                  )}
                </div>
              )}

              <button
                className="button button-primary button-wide start-button"
                disabled={starting || !topicIsValid || !settings.provider_configured || (mode === "rag" && knowledgeDocs.length === 0)}
                type="submit"
              >
                {starting ? (
                  <>
                    <span className="button-spinner" /> {t("Starting workflowâ€¦")}
                  </>
                ) : (
                  <>
                    <Zap size={16} /> {t("Start generation")} <ArrowRight size={15} />
                  </>
                )}
              </button>
              {!settings.provider_configured && (
                <p className="inline-warning">
                  {t("Provider credentials are missing from backend configuration. No key is requested or shown here.")}
                </p>
              )}
            </form>
          </section>

          <aside className="generate-side">
            <section className="panel run-configuration">
              <div className="panel-heading">
                <div>
                  <span className="eyebrow">{t("RUN CONFIGURATION")}</span>
                  <h2>{t("Retry configuration")}</h2>
                </div>
                <ShieldCheck size={18} className="green-icon" />
              </div>
              <div className="config-row">
                <span>{t("Mode")}</span>
                <strong>{mode === "gpt" ? "NxtWave GPT" : "NxtWave RAG"}</strong>
              </div>
              <div className="config-row">
                <span>{t("Provider")}</span>
                <strong>{settings.provider ?? t("Not configured")}</strong>
              </div>
              <div className="config-row">
                <span>{t("Model")}</span>
                <strong className="model-name">{settings.model ?? t("Not configured")}</strong>
              </div>
              <div className="config-row">
                <span>{t("Retries after a failed evaluation")}</span>
                <strong><Clock3 size={14} /> 2</strong>
              </div>
              <label className="form-label">{t("Fixed retry limit")}</label>
              <p className="input-meta">{t("Up to 2 retries after failed evaluation (3 total generations). Stops early as soon as all six checks pass.")}</p>
              <div className="config-row">
                <span>{t("Mandatory checkpoints")}</span>
                <strong>06 / 06</strong>
              </div>
              <div className="immutable-note">
                <ShieldCheck size={14} />
                {t("All six evaluation checkpoints remain required. The retry limit is fixed at two.")}
              </div>
            </section>
            <section className="panel workflow-preview">
              <span className="eyebrow">{t("WHAT HAPPENS NEXT")}</span>
              <ol className="workflow-steps">
                <li><i /> {t("Validate topic and load curated references")}</li>
                <li><i /> {t("Generate lesson and persist attempt")}</li>
                <li><i /> {t("Evaluate all six checkpoints")}</li>
                <li><i /> {t("Apply feedback if any check fails")}</li>
                <li><i /> {t("Approve or reject with saved reports")}</li>
              </ol>
              <div className="retry-note">
                <span className="retry-dot" />
                {t("The run will retry up to {count} time(s) after failed evaluations.", { count: 2 })}
              </div>
            </section>
          </aside>
        </div>
      )}
    </>
  );
}
