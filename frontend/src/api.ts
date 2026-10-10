// Same-origin API client. Cookies carry the session; the CSRF token is echoed from its cookie.

export type Role = "admin" | "user";
export type Me = { id: number; username: string; role: Role };

export type Citation = {
  label: string;
  chunk_id: number;
  document_id: number;
  filename: string;
  doc_sha256: string;
  page: number | null;
  section: string | null;
  score: number;
  chunk_sha256: string;
};

export type Attestation = { index: number; block_hash: string; isolated: boolean; monitor_state: string };

export type FinalEvent = {
  type: "final";
  status: "answered" | "refused";
  reason: string;
  answer: string;
  citations: Citation[];
  support: number;
  best_score: number;
  attestation: Attestation;
};

export type ChatEvent =
  | { type: "sources"; sources: Citation[] }
  | { type: "token"; text: string }
  | FinalEvent
  | { type: "error"; message: string };

export type DocumentInfo = {
  id: number;
  filename: string;
  sha256: string;
  mime: string;
  size_bytes: number;
  pages: number;
  chunk_count: number;
  status: string;
  error: string | null;
  uploaded_by: string;
  created_at: string;
};

export type ChunkInfo = {
  chunk_id: number;
  document_id: number;
  filename: string;
  page: number | null;
  section: string | null;
  text: string;
  sha256: string;
};

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

function csrfToken(): string {
  const m = document.cookie.match(/(?:^|;\s*)airgap_csrf=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : "";
}

async function raw(path: string, init: RequestInit = {}, retry = true): Promise<Response> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (method !== "GET") headers.set("X-CSRF-Token", csrfToken());
  const res = await fetch(path, { ...init, headers, credentials: "same-origin" });
  if (res.status === 401 && retry && !path.startsWith("/api/auth/")) {
    const r = await fetch("/api/auth/refresh", { method: "POST", credentials: "same-origin" });
    if (r.ok) return raw(path, init, false);
  }
  return res;
}

async function json<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await raw(path, init);
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") msg = body.detail;
      else if (Array.isArray(body.detail)) msg = "invalid input";
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, msg);
  }
  return (await res.json()) as T;
}

const body = (data: unknown): RequestInit => ({
  body: JSON.stringify(data),
  headers: { "Content-Type": "application/json" },
});

export const api = {
  me: () => json<Me>("/api/auth/me"),
  refresh: () => json<Me>("/api/auth/refresh", { method: "POST" }),
  login: (username: string, password: string) =>
    json<Me>("/api/auth/login", { method: "POST", ...body({ username, password }) }),
  logout: () => json<unknown>("/api/auth/logout", { method: "POST" }),

  documents: () => json<DocumentInfo[]>("/api/documents"),
  upload: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return json<{ outcome: string; document: DocumentInfo }>("/api/documents", { method: "POST", body: fd });
  },
  deleteDocument: (id: number) => json<unknown>(`/api/documents/${id}`, { method: "DELETE" }),
  chunk: (id: number) => json<ChunkInfo>(`/api/documents/chunks/${id}`),

  attestationStatus: () => json<AttestationStatus>("/api/attestation/status"),
  verifyBlock: (index: number) => json<BlockVerification>(`/api/attestation/blocks/${index}`),
  verifyAll: () => json<ChainReport>("/api/attestation/verify"),
  acknowledge: () => json<AttestationStatus>("/api/attestation/acknowledge", { method: "POST" }),

  users: () => json<(Me & { active: boolean })[]>("/api/admin/users"),
  createUser: (username: string, password: string, role: Role) =>
    json<Me>("/api/admin/users", { method: "POST", ...body({ username, password, role }) }),
  updateUser: (id: number, patch: { active?: boolean; role?: Role; password?: string }) =>
    json<Me>(`/api/admin/users/${id}`, { method: "PATCH", ...body(patch) }),
  audit: () => json<AuditEntry[]>("/api/admin/audit?limit=200"),

  async *chat(question: string, signal: AbortSignal): AsyncGenerator<ChatEvent> {
    const res = await raw("/api/chat", { method: "POST", signal, ...body({ question }) });
    if (!res.ok || !res.body) {
      let msg = `HTTP ${res.status}`;
      try {
        const b = (await res.json()) as { detail?: string };
        if (b.detail) msg = b.detail;
      } catch {
        /* ignore */
      }
      throw new ApiError(res.status, msg);
    }
    const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
    let buf = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += value;
      let cut: number;
      while ((cut = buf.indexOf("\n\n")) >= 0) {
        const frame = buf.slice(0, cut);
        buf = buf.slice(cut + 2);
        for (const line of frame.split("\n")) {
          if (line.startsWith("data: ")) yield JSON.parse(line.slice(6)) as ChatEvent;
        }
      }
    }
  },
};

export type AttestationStatus = {
  state: "ISOLATED" | "NOT-ISOLATED";
  break: { ts_utc: string; reasons: string[] } | null;
  last_check: string | null;
  current_reasons: string[];
  policy: { mode: string; allow: string[] };
  blocks: number;
  key_id: string;
  limits: string[];
};

export type ChainReport = {
  blocks: number;
  valid: boolean;
  first_broken: number | null;
  broken_reason: string | null;
  first_not_isolated: number | null;
  not_isolated_count: number;
  not_isolated_reasons: string[];
  warnings: string[];
  exit_code: number;
};

export type BlockVerification = {
  block: Record<string, unknown> & {
    index: number;
    ts_utc: string;
    counter: number;
    block_hash: string;
    prev_hash: string;
    key_id: string;
    net: { platform: string; interfaces: { name: string; up: boolean; addrs: string[]; kind: string }[]; default_route_v4: boolean; default_route_v6: boolean };
    monitor_state: string;
  };
  chain_valid_up_to_block: boolean;
  chain_report: ChainReport;
  isolated: boolean;
  isolation_reasons: string[];
  limits: string[];
};

export type AuditEntry = { id: number; ts: string; actor: string; action: string; detail: Record<string, unknown> };
