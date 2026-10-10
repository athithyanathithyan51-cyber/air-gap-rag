import { useCallback, useEffect, useState } from "react";
import { api, type DocumentInfo, type Me } from "../api";

function size(n: number) {
  return n > 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`;
}

export default function Documents({ me }: { me: Me }) {
  const [docs, setDocs] = useState<DocumentInfo[]>([]);
  const [log, setLog] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const isAdmin = me.role === "admin";

  const load = useCallback(() => {
    api
      .documents()
      .then(setDocs)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, []);
  useEffect(load, [load]);

  async function upload(files: FileList | null) {
    if (!files?.length) return;
    setBusy(true);
    for (const f of Array.from(files)) {
      setLog((l) => [`${f.name}: uploading and indexing…`, ...l]);
      try {
        const r = await api.upload(f);
        const msg =
          r.outcome === "failed"
            ? `failed: ${r.document.error ?? "unknown error"}`
            : `${r.outcome} (${r.document.chunk_count} chunks${r.document.pages ? `, ${r.document.pages} pages` : ""})`;
        setLog((l) => [`${f.name}: ${msg}`, ...l]);
      } catch (e) {
        setLog((l) => [`${f.name}: rejected: ${e instanceof Error ? e.message : String(e)}`, ...l]);
      }
      load();
    }
    setBusy(false);
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

  return (
    <div className="h-full overflow-y-auto p-4">
      <div className="mx-auto max-w-5xl">
        <h2 className="mb-3 text-lg font-semibold">Documents</h2>
        {isAdmin && (
          <div className="mb-4 rounded-lg border border-dashed border-slate-300 bg-white p-4">
            <label className="block text-sm">
              <span className="font-medium">Add documents</span> (PDF, DOCX, Markdown, text; max 50 MB each). A changed
              file with the same name replaces the old version.
              <input
                type="file"
                multiple
                disabled={busy}
                accept=".pdf,.docx,.md,.markdown,.txt"
                className="mt-2 block text-sm"
                onChange={(e) => {
                  void upload(e.target.files);
                  e.target.value = "";
                }}
              />
            </label>
            {log.length > 0 && (
              <ul className="mt-3 max-h-32 overflow-y-auto font-mono text-xs text-slate-600">
                {log.map((l, i) => (
                  <li key={i}>{l}</li>
                ))}
              </ul>
            )}
          </div>
        )}
        {error && <p className="mb-2 text-red-700">{error}</p>}
        <table className="w-full bg-white text-left text-sm shadow-sm">
          <thead className="bg-slate-100 text-xs uppercase text-slate-600">
            <tr>
              <th className="p-2">File</th>
              <th>Status</th>
              <th>Pages</th>
              <th>Chunks</th>
              <th>Size</th>
              <th>Added</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {docs.length === 0 && (
              <tr>
                <td colSpan={7} className="p-4 text-center text-slate-500">
                  No documents yet.{isAdmin ? " Upload some above." : " Ask an admin to add documents."}
                </td>
              </tr>
            )}
            {docs.map((d) => (
              <tr key={d.id} className="border-t border-slate-100">
                <td className="p-2">
                  <a className="text-blue-700 underline" href={`/api/documents/${d.id}/file`}>
                    {d.filename}
                  </a>
                  <div className="font-mono text-[10px] text-slate-400" title="SHA-256">
                    {d.sha256.slice(0, 16)}…
                  </div>
                </td>
                <td className={d.status === "ready" ? "text-green-700" : "text-red-700"} title={d.error ?? ""}>
                  {d.status}
                </td>
                <td>{d.pages || "—"}</td>
                <td>{d.chunk_count}</td>
                <td>{size(d.size_bytes)}</td>
                <td className="text-xs">
                  {new Date(d.created_at).toLocaleString()} by {d.uploaded_by}
                </td>
                <td>
                  {isAdmin && (
                    <button onClick={() => remove(d)} className="text-xs text-red-700 hover:underline">
                      Remove
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
