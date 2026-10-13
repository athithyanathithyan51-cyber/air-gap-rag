import { useCallback, useEffect, useRef, useState, type DragEvent } from "react";
import { api, type DocumentInfo, type Me } from "../api";
import { AlertIcon, CheckIcon, FileIcon, SearchIcon, TrashIcon, UploadIcon } from "./icons";

function size(n: number) {
  return n > 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`;
}

const KIND: Record<string, string> = {
  pdf: "bg-red-50 text-red-700",
  docx: "bg-blue-50 text-blue-700",
  md: "bg-violet-50 text-violet-700",
  markdown: "bg-violet-50 text-violet-700",
  txt: "bg-slate-100 text-slate-700",
};
const ACCEPT = [".pdf", ".docx", ".md", ".markdown", ".txt"];

function ext(name: string) {
  return name.split(".").pop()?.toLowerCase() ?? "";
}

type LogLine = { name: string; state: "busy" | "ok" | "fail"; msg: string };

export default function Documents({ me }: { me: Me }) {
  const [docs, setDocs] = useState<DocumentInfo[] | null>(null);
  const [log, setLog] = useState<LogLine[]>([]);
  const [busy, setBusy] = useState(false);
  const [drag, setDrag] = useState(false);
  const [filter, setFilter] = useState("");
  const [error, setError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const isAdmin = me.role === "admin";

  const load = useCallback(() => {
    api
      .documents()
      .then(setDocs)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, []);
  useEffect(load, [load]);

  const setLine = (name: string, state: LogLine["state"], msg: string) =>
    setLog((l) => [{ name, state, msg }, ...l.filter((x) => x.name !== name)].slice(0, 20));

  async function upload(files: FileList | File[] | null) {
    const list = Array.from(files ?? []);
    if (!list.length) return;
    setBusy(true);
    for (const f of list) {
      if (!ACCEPT.includes(`.${ext(f.name)}`)) {
        setLine(f.name, "fail", "unsupported file type");
        continue;
      }
      setLine(f.name, "busy", "uploading and indexing…");
      try {
        const r = await api.upload(f);
        if (r.outcome === "failed") setLine(f.name, "fail", r.document.error ?? "unknown error");
        else
          setLine(
            f.name,
            "ok",
            `${r.outcome} · ${r.document.chunk_count} chunks${r.document.pages ? ` · ${r.document.pages} pages` : ""}`,
          );
      } catch (e) {
        setLine(f.name, "fail", `rejected: ${e instanceof Error ? e.message : String(e)}`);
      }
      load();
    }
    setBusy(false);
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setDrag(false);
    if (isAdmin && !busy) void upload(e.dataTransfer.files);
  }

  async function remove(d: DocumentInfo) {
    if (!window.confirm(`Remove ${d.filename} and its index entries?`)) return;
    try {
      await api.deleteDocument(d.id);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  const shown = (docs ?? []).filter((d) => d.filename.toLowerCase().includes(filter.trim().toLowerCase()));
  const totalChunks = (docs ?? []).reduce((n, d) => n + d.chunk_count, 0);

  return (
    <div className="scroll-thin h-full overflow-y-auto p-4">
      <div className="mx-auto max-w-5xl space-y-4 py-2">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-xl font-semibold tracking-tight">Documents</h2>
            <p className="text-sm text-slate-500">
              {docs ? `${docs.length} document${docs.length === 1 ? "" : "s"} · ${totalChunks} searchable passages` : "Loading…"}
            </p>
          </div>
          <label className="relative block w-full sm:w-64">
            <span className="sr-only">Filter documents</span>
            <SearchIcon className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Filter by name…"
              className="w-full rounded-lg border border-slate-300 bg-white py-2 pl-9 pr-3 text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
            />
          </label>
        </div>

        {isAdmin && (
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDrag(true);
            }}
            onDragLeave={() => setDrag(false)}
            onDrop={onDrop}
            className={`rounded-xl border-2 border-dashed p-6 text-center transition ${drag ? "border-brand-500 bg-brand-50" : "border-slate-300 bg-white"}`}
          >
            <UploadIcon className={`mx-auto mb-2 text-3xl ${drag ? "text-brand-600" : "text-slate-400"}`} />
            <p className="text-sm font-medium">
              Drop files here or{" "}
              <button
                type="button"
                disabled={busy}
                onClick={() => fileRef.current?.click()}
                className="text-brand-700 underline underline-offset-2 hover:text-brand-800 disabled:opacity-50"
              >
                browse
              </button>
            </p>
            <p className="mt-1 text-xs text-slate-500">
              PDF, DOCX, Markdown or text · max 50 MB each · a changed file with the same name replaces the old version
            </p>
            <input
              ref={fileRef}
              type="file"
              multiple
              disabled={busy}
              accept={ACCEPT.join(",")}
              aria-label="Add documents"
              className="sr-only"
              onChange={(e) => {
                void upload(e.target.files);
                e.target.value = "";
              }}
            />
            {log.length > 0 && (
              <ul className="mx-auto mt-4 max-w-xl space-y-1 text-left text-xs">
                {log.map((l) => (
                  <li key={l.name} className="flex items-center gap-2 rounded-md bg-slate-50 px-2 py-1.5">
                    {l.state === "busy" && (
                      <span className="h-3 w-3 shrink-0 animate-spin rounded-full border-2 border-brand-500 border-t-transparent" />
                    )}
                    {l.state === "ok" && <CheckIcon className="shrink-0 text-emerald-600" />}
                    {l.state === "fail" && <AlertIcon className="shrink-0 text-red-600" />}
                    <span className="truncate font-medium">{l.name}</span>
                    <span className={`ml-auto shrink-0 ${l.state === "fail" ? "text-red-700" : "text-slate-500"}`}>{l.msg}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {error && (
          <p className="flex items-center gap-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">
            <AlertIcon /> {error}
          </p>
        )}

        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          {docs === null && <p className="p-6 text-center text-sm text-slate-400">Loading documents…</p>}
          {docs !== null && shown.length === 0 && (
            <div className="p-10 text-center text-slate-500">
              <FileIcon className="mx-auto mb-2 text-3xl text-slate-300" />
              {docs.length === 0 ? (
                <p>No documents yet.{isAdmin ? " Upload some above." : " Ask an admin to add documents."}</p>
              ) : (
                <p>No document matches &ldquo;{filter}&rdquo;.</p>
              )}
            </div>
          )}
          <ul className="divide-y divide-slate-100">
            {shown.map((d) => (
              <li key={d.id} className="flex flex-wrap items-center gap-3 px-4 py-3 transition hover:bg-slate-50">
                <span
                  className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-[10px] font-bold uppercase ${KIND[ext(d.filename)] ?? "bg-slate-100 text-slate-700"}`}
                >
                  {ext(d.filename)}
                </span>
                <div className="min-w-0 flex-1">
                  <a className="block truncate font-medium text-slate-900 hover:text-brand-700 hover:underline" href={`/api/documents/${d.id}/file`}>
                    {d.filename}
                  </a>
                  <p className="text-xs text-slate-500">
                    {d.pages ? `${d.pages} pages · ` : ""}
                    {d.chunk_count} chunks · {size(d.size_bytes)} · added {new Date(d.created_at).toLocaleString()} by {d.uploaded_by}
                  </p>
                  <p className="font-mono text-[10px] text-slate-400" title={`SHA-256 ${d.sha256}`}>
                    sha256 {d.sha256.slice(0, 16)}…
                  </p>
                </div>
                <span
                  title={d.error ?? ""}
                  className={`rounded-full px-2 py-0.5 text-xs font-medium ring-1 ${d.status === "ready" ? "bg-emerald-50 text-emerald-800 ring-emerald-200" : "bg-red-50 text-red-800 ring-red-200"}`}
                >
                  {d.status}
                </span>
                {isAdmin && (
                  <button
                    onClick={() => void remove(d)}
                    className="rounded-lg p-2 text-slate-400 transition hover:bg-red-50 hover:text-red-700"
                    aria-label={`Remove ${d.filename}`}
                    title="Remove"
                  >
                    <TrashIcon />
                  </button>
                )}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
