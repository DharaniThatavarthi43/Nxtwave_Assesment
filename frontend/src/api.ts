import type {
  AppSettings,
  ApprovedNote,
  ApprovedNoteSummary,
  Artifact,
  Dashboard,
  GenerationMode,
  Knowledge,
  KnowledgeDocument,
  KnowledgeSearchResult,
  LearnedRule,
  RejectionLogResponse,
  RunDetail,
  RunList,
  StartRunResponse,
} from "./types";

// Production deployments should serve the API and UI from one origin. A
// development-only Vite proxy forwards /api to the local FastAPI service.
const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    const body = init?.body;
    const isFormData = typeof FormData !== "undefined" && body instanceof FormData;
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(body && !isFormData ? { "Content-Type": "application/json" } : {}),
        ...init?.headers,
      },
    });
  } catch {
    throw new ApiError(
      `Cannot connect to the API at ${API_BASE || window.location.origin}. Check that the backend is running and reachable.`,
      0,
    );
  }

  if (!response.ok) {
    let message = `Request failed (${response.status}).`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") message = body.detail;
    } catch {
      // Keep the generic message when the server does not return JSON.
    }
    throw new ApiError(message, response.status);
  }
  return (await response.json()) as T;
}

export const api = {
  health: () => requestJson<{ status: string; database_connected: boolean }>("/api/health"),
  settings: () => requestJson<AppSettings>("/api/config"),
  dashboard: () => requestJson<Dashboard>("/api/dashboard"),
  history: (options: {
    query?: string;
    status?: string;
    offset?: number;
    limit?: number;
  } = {}) => {
    const params = new URLSearchParams();
    if (options.query) params.set("q", options.query);
    if (options.status) params.set("status", options.status);
    if (options.offset !== undefined) params.set("offset", String(options.offset));
    if (options.limit !== undefined) params.set("limit", String(options.limit));
    const suffix = params.size ? `?${params.toString()}` : "";
    return requestJson<RunList>(`/api/runs${suffix}`);
  },
  notes: () =>
    requestJson<{ items: ApprovedNoteSummary[]; total: number }>("/api/notes"),
  note: (runId: string) =>
    requestJson<ApprovedNote>(`/api/notes/${runId}`),
  run: (runId: string) => requestJson<RunDetail>(`/api/runs/${runId}`),
  startRun: (requestId: string, topic: string, mode: GenerationMode, knowledgeBaseId?: string) =>
    requestJson<StartRunResponse>("/api/runs", {
      method: "POST",
      body: JSON.stringify({
        request_id: requestId,
        topic,
        mode,
        ...(knowledgeBaseId ? { knowledge_base_id: knowledgeBaseId } : {}),
        max_retries: 2,
      }),
    }),
  rejections: (runId?: string) => {
    const params = new URLSearchParams({ limit: "300" });
    if (runId) params.set("run_id", runId);
    return requestJson<RejectionLogResponse>(`/api/rejections?${params.toString()}`);
  },
  learnedRules: () =>
    requestJson<LearnedRule[]>("/api/learning/rules"),
  knowledge: () => requestJson<Knowledge>("/api/knowledge"),
  knowledgeDocuments: () =>
    requestJson<{ documents: KnowledgeDocument[]; total_documents: number }>(
      "/api/studio/knowledge-base",
    ),
  addKnowledgeUrl: (url: string) =>
    requestJson<{ document_id: string; title: string; source_type: string; source_url: string | null }>(
      "/api/studio/knowledge-base/url",
      {
        method: "POST",
        body: JSON.stringify({ url }),
      },
    ),
  uploadKnowledgeDocument: (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return requestJson<{ document_id: string; title: string; source_type: string }>(
      "/api/studio/knowledge-base/upload",
      {
        method: "POST",
        body: formData,
      },
    );
  },
  deleteKnowledgeDocument: async (documentId: string) => {
    let response: Response;
    try {
      response = await fetch(`${API_BASE}/api/studio/knowledge-base/${documentId}`, { method: "DELETE" });
    } catch {
      throw new ApiError(`Cannot connect to the API at ${API_BASE || window.location.origin}.`, 0);
    }
    if (!response.ok) throw new ApiError("The knowledge-base document could not be deleted.", response.status);
  },
  searchKnowledgeBase: (query: string) =>
    requestJson<{ query: string; results: KnowledgeSearchResult[] }>(
      "/api/studio/knowledge-base/search",
      {
        method: "POST",
        body: JSON.stringify({ query }),
      },
    ),
  artifacts: (runId: string) =>
    requestJson<Artifact[]>(`/api/runs/${runId}/artifacts`),
  artifactText: async (runId: string, filename: string) => {
    const allowed = new Set([
      "final_lesson.md",
      "rejected_lesson.md",
      "evaluation_report.md",
      "execution_summary.md",
      "attempt_history.md",
      "rejection_log.md",
      "learned_rules.md",
    ]);
    if (!allowed.has(filename)) throw new ApiError("Unknown output file.", 400);
    let response: Response;
    try {
      response = await fetch(
        `${API_BASE}/api/runs/${runId}/artifacts/${filename}`,
      );
    } catch {
      throw new ApiError(`Cannot connect to the API at ${API_BASE || window.location.origin}.`, 0);
    }
    if (!response.ok) {
      throw new ApiError("This output file is not available.", response.status);
    }
    return response.text();
  },
};

export const API_ORIGIN = API_BASE || window.location.origin;
