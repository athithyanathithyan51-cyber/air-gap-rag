import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, type Citation, type ChunkInfo, type FinalEvent, type Me } from "../api";
import VerifyDialog from "./VerifyDialog";

type Turn = {
  id: number;
  question: string;
  draft: string;
  final?: FinalEvent;
  error?: string;
  pending: boolean;
};

const REASONS: Record<string, string> = {
  grounded: "Answer is supported by the cited sources.",
  low_retrieval_score: "No sufficiently relevant passage was found in the documents.",
  model_declined: "The model found no answer in the retrieved passages.",
  no_valid_citation: "The draft answer did not cite a retrieved source, so it was withheld.",
  unsupported: "The draft answer was not supported by its cited sources, so it was withheld.",
  unsafe_content: "The draft answer asked for a password or other credentials, so it was withheld.",
};

function location(c: { filename: string; page: number | null; section: string | null }) {
  return [c.filename, c.page != null ? `p. ${c.page}` : null, c.section].filter(Boolean).join(" · ");
}

export default function Chat({ me }: { me: Me }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState("");
  const [chunk, setChunk] = useState<ChunkInfo | null>(null);
  const [chunkError, setChunkError] = useState("");
  const [verifyIndex, setVerifyIndex] = useState<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const busy = turns.some((t) => t.pending);

  // Block body: newer browsers return a Promise from scrollIntoView, which React would call as a cleanup.
  useEffect(() => {
    endRef.current?.scrollIntoView?.({ behavior: "smooth" });
  }, [turns]);
  useEffect(() => () => abortRef.current?.abort(), []);

  const update = (id: number, f: (t: Turn) => Turn) => setTurns((ts) => ts.map((t) => (t.id === id ? f(t) : t)));

  async function ask(e: FormEvent) {
    e.preventDefault();
    const q = question.trim();
    if (q.length < 2 || busy) return;
    const id = Date.now();
    setQuestion("");
    setTurns((ts) => [...ts, { id, question: q, draft: "", pending: true }]);
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      for await (const ev of api.chat(q, ctrl.signal)) {
        if (ev.type === "token") update(id, (t) => ({ ...t, draft: t.draft + ev.text }));
        else if (ev.type === "final") update(id, (t) => ({ ...t, final: ev, pending: false }));
        else if (ev.type === "error") update(id, (t) => ({ ...t, error: ev.message, pending: false }));
      }
    } catch (err) {
      if (!ctrl.signal.aborted)
        update(id, (t) => ({ ...t, error: err instanceof Error ? err.message : String(err), pending: false }));
    } finally {
      update(id, (t) => ({ ...t, pending: false }));
    }
  }

  async function openCitation(c: Citation) {
    setChunkError("");
    try {
      setChunk(await api.chunk(c.chunk_id));
    } catch (err) {
      setChunk(null);
      setChunkError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <div className="flex h-full">
      <section className="flex min-w-0 flex-1 flex-col">
        <div className="flex-1 overflow-y-auto p-4" aria-live="polite">
          {turns.length === 0 && (
            <div className="mx-auto mt-16 max-w-xl text-center text-slate-500">
              <p className="text-lg">Ask a question about the ingested documents.</p>
              <p className="mt-2 text-sm">
                Every answer cites its sources. If the documents do not support an answer, you will get &ldquo;I
                don&apos;t know&rdquo;. Each answer is recorded with the machine&apos;s network-isolation state.
              </p>
            </div>
          )}
          {turns.map((t) => (
            <article key={t.id} className="mx-auto mb-6 max-w-3xl">
              <p className="mb-2 ml-auto w-fit max-w-[85%] rounded-lg bg-blue-700 px-3 py-2 text-white">{t.question}</p>
              <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
                {t.error && <p className="text-red-700">⚠ {t.error}</p>}
                {!t.error && !t.final && (
                  <p className="whitespace-pre-wrap text-slate-700">
                    {t.draft || <span className="text-slate-400">Thinking…</span>}
                    {t.pending && <span className="animate-pulse">▍</span>}
                  </p>
                )}
                {t.final && (
                  <>
                    <p className={`whitespace-pre-wrap ${t.final.status === "refused" ? "text-slate-600 italic" : ""}`}>
                      {t.final.answer}
                    </p>
                    {t.final.reason === "general" && (
                      <p className="mt-2 inline-block rounded border border-amber-300 bg-amber-50 px-2 py-0.5 text-xs text-amber-900">
                        General answer, not from your documents. Verify important facts.
                      </p>
                    )}
                    {t.final.status === "refused" && (
                      <p className="mt-1 text-xs text-slate-500">{REASONS[t.final.reason] ?? t.final.reason}</p>
                    )}
                    {t.final.citations.length > 0 && (
                      <div className="mt-3 flex flex-wrap gap-2">
                        {t.final.citations.map((c) => (
                          <button
                            key={c.label}
                            onClick={() => openCitation(c)}
                            className="rounded border border-blue-200 bg-blue-50 px-2 py-1 text-left text-xs text-blue-900 hover:bg-blue-100"
                            title="Show the cited passage"
                          >
                            [{c.label}] {location(c)}
                          </button>
                        ))}
                      </div>
                    )}
                    <div className="mt-3 flex flex-wrap items-center gap-3 border-t border-slate-100 pt-2 text-xs text-slate-500">
                      <span className={t.final.attestation.isolated && t.final.attestation.monitor_state === "ISOLATED" ? "text-green-700" : "text-red-700"}>
                        Record #{t.final.attestation.index}:{" "}
                        {t.final.attestation.isolated && t.final.attestation.monitor_state === "ISOLATED"
                          ? "isolated"
                          : "NOT isolated"}
                      </span>
                      <button
                        onClick={() => setVerifyIndex(t.final!.attestation.index)}
                        className="rounded border border-slate-300 px-2 py-0.5 text-slate-700 hover:bg-slate-100"
                      >
                        Verify this answer
                      </button>
                    </div>
                  </>
                )}
              </div>
            </article>
          ))}
          <div ref={endRef} />
        </div>
        <form onSubmit={ask} className="border-t border-slate-200 bg-white p-3">
          <div className="mx-auto flex max-w-3xl gap-2">
            <label htmlFor="q" className="sr-only">
              Question
            </label>
            <input
              id="q"
              className="flex-1 rounded border border-slate-300 px-3 py-2"
              placeholder={`Ask a question, ${me.username}…`}
              value={question}
              maxLength={2000}
              onChange={(e) => setQuestion(e.target.value)}
            />
            {busy ? (
              <button type="button" onClick={() => abortRef.current?.abort()} className="rounded border border-slate-300 px-4">
                Stop
              </button>
            ) : (
              <button type="submit" className="rounded bg-blue-700 px-4 py-2 font-medium text-white hover:bg-blue-800">
                Ask
              </button>
            )}
          </div>
        </form>
      </section>

      {(chunk || chunkError) && (
        <aside className="w-full max-w-md overflow-y-auto border-l border-slate-200 bg-white p-4" aria-label="Cited passage">
          <div className="mb-2 flex items-start justify-between gap-2">
            <h2 className="font-semibold">Cited passage</h2>
            <button
              onClick={() => {
                setChunk(null);
                setChunkError("");
              }}
              className="text-sm text-slate-500 hover:text-slate-900"
              aria-label="Close"
            >
              ✕
            </button>
          </div>
          {chunkError && <p className="text-sm text-red-700">{chunkError}</p>}
          {chunk && (
            <>
              <p className="mb-1 text-sm text-slate-600">{location(chunk)}</p>
              <p className="mb-3 break-all font-mono text-[10px] text-slate-400">sha256 {chunk.sha256}</p>
              <p className="whitespace-pre-wrap text-sm leading-relaxed">{chunk.text}</p>
              <a
                className="mt-4 inline-block text-sm text-blue-700 underline"
                href={`/api/documents/${chunk.document_id}/file`}
              >
                Download original document
              </a>
            </>
          )}
        </aside>
      )}
      {verifyIndex !== null && <VerifyDialog index={verifyIndex} onClose={() => setVerifyIndex(null)} />}
    </div>
  );
}
