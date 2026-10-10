import { useEffect, useState } from "react";

type Health = { status: string; version: string };
type State = { kind: "loading" } | { kind: "ok"; health: Health } | { kind: "error"; message: string };

export const TITLE = "Offline LLM-Based Intelligent Conversational Assistant";
export const SUBTITLE = "for Secure Air-Gapped Networks";

export default function App() {
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    const ctrl = new AbortController();
    fetch("/health", { signal: ctrl.signal, credentials: "same-origin" })
      .then(async (r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        setState({ kind: "ok", health: (await r.json()) as Health });
      })
      .catch((e: unknown) => {
        if (ctrl.signal.aborted) return;
        setState({ kind: "error", message: e instanceof Error ? e.message : String(e) });
      });
    return () => ctrl.abort();
  }, []);

  return (
    <main className="mx-auto max-w-3xl p-8 font-sans text-slate-900">
      <h1 className="text-2xl font-bold">{TITLE}</h1>
      <p className="text-slate-600">{SUBTITLE}</p>
      <section className="mt-6 rounded border border-slate-200 p-4" aria-live="polite">
        {state.kind === "loading" && <p>Checking server…</p>}
        {state.kind === "ok" && (
          <p>
            Server status: <strong>{state.health.status}</strong> (v{state.health.version})
          </p>
        )}
        {state.kind === "error" && <p className="text-red-700">Server unreachable: {state.message}</p>}
      </section>
    </main>
  );
}
