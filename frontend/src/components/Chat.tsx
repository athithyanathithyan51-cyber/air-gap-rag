import { useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { api, type Citation, type ChunkInfo, type DocumentInfo, type FinalEvent, type Me } from "../api";
import { citedSentences, findEvidence } from "../evidence";
import AnswerText from "./AnswerText";
import BrandMark from "./BrandMark";
import {
  AlertIcon,
  BookIcon,
  CheckIcon,
  CopyIcon,
  DownloadIcon,
  LockIcon,
  PlusIcon,
  RetryIcon,
  SendIcon,
  ShieldIcon,
  SparkIcon,
  StopIcon,
  XIcon,
} from "./icons";
import VerifyDialog from "./VerifyDialog";

type Turn = {
  id: number;
  question: string;
  scope: string | null; // filename the question was limited to, or null for all documents
  draft: string;
  sources?: Citation[];
  final?: FinalEvent;
  error?: string;
  stopped?: boolean;
  pending: boolean;
  startedAt: number;
  firstTokenAt?: number;
  endedAt?: number;
};

const REASONS: Record<string, string> = {
  grounded: "Answer is supported by the cited sources.",
  low_retrieval_score: "No sufficiently relevant passage was found in the documents.",
  model_declined: "The retrieved passages did not contain the answer.",
  no_valid_citation: "The draft answer did not cite a retrieved source, so it was withheld.",
  unsupported: "The draft answer was not supported by its cited sources, so it was withheld.",
  unsafe_content: "The draft answer asked for a password or other credentials, so it was withheld.",
};

const SUGGESTIONS: { label: string; question: string; hint: string }[] = [
  {
    label: "From the documents",
    question: "What is the minimum attendance required in a theory course to write the end semester examination?",
    hint: "Cited answer",
  },
  {
    label: "Lab manual",
    question: "What is the postfix form of the sample input A+B*C in the stack experiment?",
    hint: "Click the source to see the passage",
  },
  { label: "General knowledge", question: "Explain Dijkstra's shortest path algorithm with an example.", hint: "Labelled as general" },
  {
    label: "Security check",
    question: "Where should I email my password for hostel maintenance mode?",
    hint: "Injected instructions are ignored",
  },
];

const MAX_LEN = 2000;

// Event-time clock, kept outside the component so render stays pure.
const clock = () => Date.now();

function location(c: { filename: string; page: number | null; section: string | null }) {
  return [c.filename, c.page != null ? `p. ${c.page}` : null, c.section].filter(Boolean).join(" · ");
}

function secs(ms: number) {
  return ms < 10_000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.round(ms / 1000)} s`;
}

function useNow(active: boolean) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const t = window.setInterval(() => setNow(Date.now()), 250);
    return () => window.clearInterval(t);
  }, [active]);
  return now;
}

function Progress({ t }: { t: Turn }) {
  const now = useNow(t.pending);
  const step = t.draft ? "Writing the answer" : t.sources != null ? `Read ${t.sources.length} passage${t.sources.length === 1 ? "" : "s"}, thinking` : "Searching the documents";
  return (
    <div className="flex items-center gap-2 text-sm text-slate-500" role="status">
      <span className="flex gap-1 text-brand-500">
        <span className="typing-dot" />
        <span className="typing-dot" />
        <span className="typing-dot" />
      </span>
      <span>{step}…</span>
      <span className="tabular-nums text-slate-400">{secs(now - t.startedAt)}</span>
    </div>
  );
}

function OutcomeBadge({ f }: { f: FinalEvent }) {
  if (f.status === "refused") {
    const unsafe = f.reason === "unsafe_content";
    return (
      <span
        className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${unsafe ? "bg-red-50 text-red-800 ring-1 ring-red-200" : "bg-slate-100 text-slate-700 ring-1 ring-slate-200"}`}
      >
        {unsafe ? <AlertIcon /> : <LockIcon />} {unsafe ? "Blocked for safety" : "Not in the documents"}
      </span>
    );
  }
  if (f.reason === "about")
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-brand-50 px-2 py-0.5 text-xs font-medium text-brand-800 ring-1 ring-brand-200">
        <ShieldIcon /> About this assistant
      </span>
    );
  if (f.reason === "general")
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-900 ring-1 ring-amber-200">
        <SparkIcon /> General knowledge
      </span>
    );
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-800 ring-1 ring-emerald-200">
      <BookIcon /> From your documents
    </span>
  );
}

function CopyButton({ text }: { text: string }) {
  const [done, setDone] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      ta.remove();
    }
    setDone(true);
    window.setTimeout(() => setDone(false), 1500);
  }
  return (
    <button type="button" onClick={() => void copy()} className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 hover:bg-slate-100 hover:text-slate-800">
      {done ? <CheckIcon className="text-emerald-600" /> : <CopyIcon />} {done ? "Copied" : "Copy"}
    </button>
  );
}

export default function Chat({ me }: { me: Me }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState("");
  const [chunk, setChunk] = useState<ChunkInfo | null>(null);
  const [chunkLabel, setChunkLabel] = useState("");
  const [chunkAnswer, setChunkAnswer] = useState("");
  const [chunkError, setChunkError] = useState("");
  // The passage sentence the cited answer sentence was drawn from, when one is close enough.
  const evidence = useMemo(
    () => (chunk && chunkAnswer ? findEvidence(chunk.text, citedSentences(chunkAnswer, chunkLabel)) : null),
    [chunk, chunkAnswer, chunkLabel],
  );
  const [verifyIndex, setVerifyIndex] = useState<number | null>(null);
  const [docs, setDocs] = useState<DocumentInfo[]>([]);
  const [reportState, setReportState] = useState<"idle" | "busy" | "saved" | "failed">("idle");
  const [scope, setScope] = useState<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const busy = turns.some((t) => t.pending);

  // Block body: newer browsers return a Promise from scrollIntoView, which React would call as a cleanup.
  useEffect(() => {
    endRef.current?.scrollIntoView?.({ behavior: "smooth", block: "end" });
  }, [turns]);
  useEffect(() => () => abortRef.current?.abort(), []);
  // Documents that can be searched; a failed list just leaves the picker on "All documents".
  useEffect(() => {
    api
      .documents()
      .then((all) => setDocs(all.filter((d) => d.status === "ready")))
      .catch(() => setDocs([]));
  }, []);

  // Grow the question box with its content, up to a limit.
  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [question]);

  const update = (id: number, f: (t: Turn) => Turn) => setTurns((ts) => ts.map((t) => (t.id === id ? f(t) : t)));

  async function send(raw: string) {
    const q = raw.trim();
    if (q.length < 2 || busy) return;
    const id = clock();
    setQuestion("");
    const scopeName = scope === null ? null : (docs.find((d) => d.id === scope)?.filename ?? null);
    setTurns((ts) => [...ts, { id, question: q, scope: scopeName, draft: "", pending: true, startedAt: clock() }]);
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      for await (const ev of api.chat(q, ctrl.signal, scope)) {
        if (ev.type === "sources") update(id, (t) => ({ ...t, sources: ev.sources }));
        else if (ev.type === "token") update(id, (t) => ({ ...t, draft: t.draft + ev.text, firstTokenAt: t.firstTokenAt ?? clock() }));
        else if (ev.type === "final") update(id, (t) => ({ ...t, final: ev, pending: false, endedAt: clock() }));
        else if (ev.type === "error") update(id, (t) => ({ ...t, error: ev.message, pending: false, endedAt: clock() }));
      }
    } catch (err) {
      if (ctrl.signal.aborted) update(id, (t) => ({ ...t, stopped: true }));
      else update(id, (t) => ({ ...t, error: err instanceof Error ? err.message : String(err) }));
    } finally {
      update(id, (t) => ({ ...t, pending: false, endedAt: t.endedAt ?? clock() }));
      inputRef.current?.focus();
    }
  }

  // Downloads a signed JSON report of this session's answers and their isolation records.
  async function exportReport() {
    const indexes = turns.flatMap((t) => (t.final ? [t.final.attestation.index] : []));
    if (indexes.length === 0) return;
    setReportState("busy");
    try {
      const report = await api.attestationReport(indexes);
      const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], { type: "application/json" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = `attestation-report-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
      setReportState("saved");
    } catch {
      setReportState("failed");
    }
    window.setTimeout(() => setReportState("idle"), 2000);
  }

  function ask(e: FormEvent) {
    e.preventDefault();
    void send(question);
  }

  function onKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      void send(question);
    }
  }

  async function openCitation(c: Citation, answer: string) {
    setChunkError("");
    setChunkLabel(c.label);
    setChunkAnswer(answer);
    try {
      setChunk(await api.chunk(c.chunk_id));
    } catch (err) {
      setChunk(null);
      setChunkError(err instanceof Error ? err.message : String(err));
    }
  }

  function closePassage() {
    setChunk(null);
    setChunkError("");
  }

  useEffect(() => {
    if (!chunk && !chunkError) return;
    const onEsc = (e: globalThis.KeyboardEvent) => {
      if (e.key === "Escape" && verifyIndex === null) closePassage();
    };
    window.addEventListener("keydown", onEsc);
    return () => window.removeEventListener("keydown", onEsc);
  }, [chunk, chunkError, verifyIndex]);

  return (
    <div className="relative flex h-full">
      <section className="flex min-w-0 flex-1 flex-col">
        <div className="scroll-thin flex-1 overflow-y-auto px-4 py-6" aria-live="polite">
          {turns.length === 0 && (
            <div className="mx-auto mt-6 max-w-3xl animate-fade-in text-center sm:mt-12">
              <BrandMark className="mx-auto mb-5 h-14 w-14" />
              <h2 className="font-display text-3xl leading-tight text-brand-900">
                Hello {me.username}, what would you like to know?
              </h2>
              <p className="mx-auto mt-2 max-w-xl text-sm text-slate-500">
                Questions about your documents are answered with clickable sources. Anything else gets a clearly labelled
                general answer. Everything runs on this machine, with no internet.
              </p>
              <div className="mt-8 grid gap-3 text-left sm:grid-cols-2">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s.question}
                    type="button"
                    onClick={() => void send(s.question)}
                    className="group rounded-md border border-slate-200 bg-white p-4 text-left transition hover:border-brand-300"
                  >
                    <span className="text-xs font-medium text-brand-600">{s.label}</span>
                    <span className="mt-1 block text-sm text-slate-800">{s.question}</span>
                    <span className="mt-2 block text-xs text-slate-400 group-hover:text-slate-500">{s.hint} →</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {turns.map((t) => (
            <article key={t.id} className="mx-auto mb-8 max-w-3xl animate-fade-in">
              <div className="mb-3 flex flex-col items-end gap-1">
                {t.scope && <p className="max-w-[85%] truncate text-xs text-slate-500">Searching in {t.scope}</p>}
                <p className="max-w-[85%] whitespace-pre-wrap rounded-md bg-brand-700 px-4 py-2.5 text-white shadow-sm">
                  {t.question}
                </p>
              </div>
              <div className="flex gap-3">
                <BrandMark className="mt-1 hidden h-8 w-8 shrink-0 sm:block" />
                <div className="min-w-0 flex-1 rounded-md border border-slate-200 bg-white p-4 shadow-sm">
                  {t.error && (
                    <div className="flex flex-wrap items-center gap-3 text-red-700">
                      <AlertIcon className="shrink-0" />
                      <span className="flex-1">{t.error}</span>
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => void send(t.question)}
                        className="inline-flex items-center gap-1 rounded-md border border-red-200 px-2 py-1 text-sm hover:bg-red-50 disabled:opacity-50"
                      >
                        <RetryIcon /> Try again
                      </button>
                    </div>
                  )}

                  {!t.error && !t.final && (
                    <>
                      {t.draft && (
                        <div className="mb-2 text-slate-800">
                          <AnswerText text={t.draft} citations={t.sources} onCite={(c) => void openCitation(c, t.draft)} />
                        </div>
                      )}
                      {t.pending && <Progress t={t} />}
                      {t.stopped && (
                        <div className="flex items-center gap-3 text-sm text-slate-500">
                          <span>Stopped.</span>
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => void send(t.question)}
                            className="inline-flex items-center gap-1 rounded-md border border-slate-200 px-2 py-1 hover:bg-slate-50 disabled:opacity-50"
                          >
                            <RetryIcon /> Ask again
                          </button>
                        </div>
                      )}
                    </>
                  )}

                  {t.final && (
                    <>
                      <div className="mb-3">
                        <OutcomeBadge f={t.final} />
                      </div>
                      <div className={t.final.status === "refused" ? "text-slate-600" : "text-slate-800"}>
                        <AnswerText text={t.final.answer} citations={t.final.citations} onCite={(c) => void openCitation(c, t.final!.answer)} />
                      </div>
                      {t.final.reason === "general" && (
                        <p className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900">
                          General answer, not from your documents. Verify important facts.
                        </p>
                      )}
                      {t.final.status === "refused" && (
                        <p className="mt-2 text-xs text-slate-500">{REASONS[t.final.reason] ?? t.final.reason}</p>
                      )}
                      {t.final.citations.length > 0 && (
                        <div className="mt-4">
                          <p className="mb-2 text-xs font-medium text-slate-500">Sources</p>
                          <div className="flex flex-wrap gap-2">
                            {t.final.citations.map((c) => (
                              <button
                                key={c.label}
                                type="button"
                                onClick={() => void openCitation(c, t.final!.answer)}
                                aria-label={`[${c.label}] ${location(c)}`}
                                className={`flex max-w-full items-center gap-2 rounded-lg border px-2.5 py-1.5 text-left text-xs transition hover:border-brand-300 hover:bg-brand-50 ${chunkLabel === c.label && chunk?.chunk_id === c.chunk_id ? "border-brand-300 bg-brand-50" : "border-slate-200 bg-slate-50"}`}
                                title="Show the cited passage"
                              >
                                <span className="rounded bg-brand-100 px-1.5 font-semibold text-brand-800">{c.label}</span>
                                <span className="min-w-0 truncate text-slate-700">{location(c)}</span>
                              </button>
                            ))}
                          </div>
                        </div>
                      )}
                      <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-slate-100 pt-3 text-xs text-slate-500">
                        <CopyButton text={t.final.answer} />
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => void send(t.question)}
                          className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 hover:bg-slate-100 hover:text-slate-800 disabled:opacity-50"
                        >
                          <RetryIcon /> Ask again
                        </button>
                        <button
                          type="button"
                          onClick={() => setVerifyIndex(t.final!.attestation.index)}
                          className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 hover:bg-slate-100 hover:text-slate-800"
                        >
                          <ShieldIcon /> Verify this answer
                        </button>
                        <span className="ml-auto flex items-center gap-2">
                          {t.endedAt && (
                            <span className="tabular-nums" title="Time to answer">
                              {secs(t.endedAt - t.startedAt)}
                            </span>
                          )}
                          <span
                            className={`font-mono text-[11px] ${t.final.attestation.isolated && t.final.attestation.monitor_state === "ISOLATED" ? "text-emerald-700" : "text-red-700"}`}
                            title="Network-isolation state recorded with this answer"
                          >
                            Record #{t.final.attestation.index}:{" "}
                            {t.final.attestation.isolated && t.final.attestation.monitor_state === "ISOLATED" ? "isolated" : "NOT isolated"}
                          </span>
                        </span>
                      </div>
                    </>
                  )}
                </div>
              </div>
            </article>
          ))}
          <div ref={endRef} />
        </div>

        <form onSubmit={ask} className="border-t border-slate-200 bg-white/80 px-3 pb-3 pt-3 backdrop-blur">
          <div className="mx-auto max-w-3xl">
            <div className="flex items-end gap-2 rounded-xl border border-slate-300 bg-white p-2 shadow-[0_12px_40px_-12px_rgb(0_0_0/0.6)] transition focus-within:border-brand-500 focus-within:shadow-[0_0_0_3px_rgb(47_179_166/0.18),0_12px_40px_-12px_rgb(0_0_0/0.6)]">
              {turns.length > 0 && (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => {
                    setTurns([]);
                    closePassage();
                    inputRef.current?.focus();
                  }}
                  title="New chat"
                  aria-label="New chat"
                  className="mb-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-lg text-slate-500 hover:bg-slate-100 hover:text-slate-800 disabled:opacity-40"
                >
                  <PlusIcon />
                </button>
              )}
              {turns.some((t) => t.final) && (
                <button
                  type="button"
                  onClick={() => void exportReport()}
                  disabled={busy || reportState === "busy"}
                  title="Download a signed report of this session's answers"
                  className="mb-0.5 inline-flex h-9 shrink-0 items-center gap-1.5 rounded-lg border border-slate-200 px-2.5 text-xs text-slate-600 transition hover:bg-slate-100 hover:text-slate-900 disabled:opacity-40"
                >
                  <ShieldIcon />
                  {reportState === "busy"
                    ? "Signing…"
                    : reportState === "saved"
                      ? "Report saved"
                      : reportState === "failed"
                        ? "Export failed"
                        : "Export report"}
                </button>
              )}
              <select
                value={scope ?? ""}
                onChange={(e) => setScope(e.target.value ? Number(e.target.value) : null)}
                disabled={busy}
                aria-label="Search in"
                title="Limit the answer to one document"
                className="mb-0.5 h-9 max-w-[10rem] shrink-0 truncate rounded-lg border border-slate-200 bg-slate-50 px-2 text-xs text-slate-600 outline-none transition hover:border-slate-300 focus:border-brand-500 disabled:opacity-50"
              >
                <option value="">All documents</option>
                {docs.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.filename}
                  </option>
                ))}
              </select>
              <label htmlFor="q" className="sr-only">
                Question
              </label>
              <textarea
                id="q"
                ref={inputRef}
                rows={1}
                autoFocus
                className="max-h-[200px] min-h-9 flex-1 resize-none bg-transparent px-2 py-1.5 outline-none placeholder:text-slate-400"
                placeholder={`Ask a question, ${me.username}…`}
                value={question}
                maxLength={MAX_LEN}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={onKey}
              />
              {busy ? (
                <button
                  type="button"
                  onClick={() => abortRef.current?.abort()}
                  aria-label="Stop"
                  className="flex h-9 shrink-0 items-center gap-1.5 rounded-xl border border-slate-300 px-3 text-sm font-medium text-slate-700 hover:bg-slate-100"
                >
                  <StopIcon /> Stop
                </button>
              ) : (
                <button
                  type="submit"
                  aria-label="Ask"
                  disabled={question.trim().length < 2}
                  className="flex h-9 shrink-0 items-center gap-1.5 rounded-xl bg-brand-700 px-3 text-sm font-medium text-white transition hover:bg-brand-800 disabled:bg-slate-300"
                >
                  <SendIcon /> <span className="hidden sm:inline">Ask</span>
                </button>
              )}
            </div>
            <p className="mt-1.5 flex justify-between px-2 text-[11px] text-slate-400">
              <span>Enter to send · Shift+Enter for a new line</span>
              {question.length > MAX_LEN - 200 && (
                <span className="tabular-nums">
                  {question.length}/{MAX_LEN}
                </span>
              )}
            </p>
          </div>
        </form>
      </section>

      {(chunk || chunkError) && (
        <>
          <div className="fixed inset-0 z-20 bg-slate-900/30 lg:hidden" onClick={closePassage} aria-hidden="true" />
          <aside
            className="scroll-thin fixed inset-y-0 right-0 z-30 w-full max-w-md animate-slide-in overflow-y-auto border-l border-slate-200 bg-white p-5 shadow-xl lg:static lg:z-auto lg:shadow-none"
            aria-label="Cited passage"
          >
            <div className="mb-3 flex items-start justify-between gap-2">
              <h2 className="flex items-center gap-2 font-semibold">
                {chunkLabel && <span className="rounded bg-brand-100 px-1.5 text-sm text-brand-800">{chunkLabel}</span>}
                Cited passage
              </h2>
              <button onClick={closePassage} className="rounded p-1 text-slate-500 hover:bg-slate-100 hover:text-slate-900" aria-label="Close">
                <XIcon />
              </button>
            </div>
            {chunkError && <p className="text-sm text-red-700">{chunkError}</p>}
            {chunk && (
              <>
                <p className="mb-1 text-sm font-medium text-slate-700">{location(chunk)}</p>
                <p className="mb-4 break-all font-mono text-[10px] text-slate-400">sha256 {chunk.sha256}</p>
                {evidence ? (
                  <>
                    <p className="mb-2 flex items-center gap-2 text-xs text-slate-500">
                      <span className="inline-block h-2 w-2 rounded-full bg-amber-400" aria-hidden="true" />
                      Highlighted: the sentence this answer used ({Math.round(evidence.score * 100)}% word match)
                    </p>
                    <blockquote className="whitespace-pre-wrap rounded-lg border-l-4 border-brand-300 bg-slate-50 p-3 text-sm leading-relaxed text-slate-800">
                      {chunk.text.slice(0, evidence.start)}
                      <mark className="rounded bg-amber-300/25 px-0.5 text-slate-900 ring-1 ring-amber-300/40">
                        {chunk.text.slice(evidence.start, evidence.end)}
                      </mark>
                      {chunk.text.slice(evidence.end)}
                    </blockquote>
                  </>
                ) : (
                  <blockquote className="whitespace-pre-wrap rounded-lg border-l-4 border-brand-300 bg-slate-50 p-3 text-sm leading-relaxed text-slate-800">
                    {chunk.text}
                  </blockquote>
                )}
                <a
                  className="mt-4 inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-brand-700 hover:bg-brand-50"
                  href={`/api/documents/${chunk.document_id}/file`}
                >
                  <DownloadIcon /> Download original document
                </a>
              </>
            )}
          </aside>
        </>
      )}
      {verifyIndex !== null && <VerifyDialog index={verifyIndex} onClose={() => setVerifyIndex(null)} />}
    </div>
  );
}
