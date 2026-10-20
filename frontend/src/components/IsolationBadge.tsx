import { useEffect, useRef, useState } from "react";
import { api, type AttestationStatus, type TrafficStatus } from "../api";

// Three looks: isolated (green), isolated now but a past break is still unacknowledged (amber),
// and not isolated right now (red). The amber state keeps answers flagged until an admin acknowledges.
const TONE = {
  ok: { pill: "bg-emerald-50 text-emerald-800 ring-emerald-200", ping: "bg-emerald-400", dot: "bg-emerald-500" },
  ack: { pill: "bg-amber-50 text-amber-800 ring-amber-300", ping: "bg-amber-400", dot: "bg-amber-500" },
  bad: { pill: "bg-red-50 text-red-800 ring-red-200", ping: "bg-red-400", dot: "bg-red-500" },
};

function bytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

function since(ts: string): string {
  const s = Math.max(0, Math.round((Date.now() - Date.parse(ts)) / 1000));
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m ${s % 60}s`;
  return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
}

function Traffic({ t }: { t: TrafficStatus | null }) {
  if (!t) return <p className="text-slate-500">Traffic meter not available.</p>;
  if (!t.since) return <p className="text-red-700">Counting starts once the machine is isolated.</p>;
  const zero = t.sent_bytes + t.recv_bytes + t.sent_packets + t.recv_packets === 0;
  const sockets = t.app_remote_sockets.length;
  return (
    <div className="space-y-2">
      <p className="text-slate-500">
        External network traffic since isolated <span className="font-medium text-slate-700">({since(t.since)} ago)</span>
      </p>
      <div className="grid grid-cols-2 gap-2">
        {[
          ["Sent", t.sent_bytes, t.sent_packets],
          ["Received", t.recv_bytes, t.recv_packets],
        ].map(([label, b, p]) => (
          <div key={label} className={`rounded-lg p-2 text-center ${zero ? "bg-emerald-50" : "bg-red-50"}`}>
            <p className="text-[11px] uppercase tracking-wide text-slate-500">{label}</p>
            <p className={`text-lg font-bold tabular-nums ${zero ? "text-emerald-700" : "text-red-700"}`} data-testid={`traffic-${label}`}>
              {bytes(Number(b))}
            </p>
            <p className="text-[11px] tabular-nums text-slate-500">{Number(p)} packets</p>
          </div>
        ))}
      </div>
      <p className={sockets ? "text-red-700" : "text-slate-600"}>
        App connections to non-local addresses: <span className="font-semibold tabular-nums">{sockets}</span>
        {sockets > 0 && ` (${t.app_remote_sockets.slice(0, 3).join(", ")})`}
      </p>
      <p className="text-[11px] text-slate-400">
        Counted on: {t.interfaces.join(", ") || "none"}. OS interface counters, live every 2 s; the packet capture is the
        stronger evidence.
      </p>
    </div>
  );
}

export default function IsolationBadge({ isAdmin = false }: { isAdmin?: boolean }) {
  const [status, setStatus] = useState<AttestationStatus | null>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let alive = true;
    const load = () =>
      api
        .attestationStatus()
        .then((s) => alive && setStatus(s))
        .catch(() => alive && setStatus(null));
    load();
    const t = window.setInterval(load, 2000);
    return () => {
      alive = false;
      window.clearInterval(t);
    };
  }, []);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  if (!status)
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-600">
        <span className="h-2 w-2 rounded-full bg-slate-400" />
        <span className="hidden sm:inline">isolation:</span> unknown
      </span>
    );

  const latched = status.state === "ISOLATED";
  const now = status.isolated_now ?? latched;
  const kind = !now ? "bad" : latched ? "ok" : "ack";
  const tone = TONE[kind];

  return (
    <div ref={box} className="relative shrink-0">
      <button
        type="button"
        aria-expanded={open}
        title="Network isolation and traffic"
        onClick={() => setOpen((o) => !o)}
        className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ${tone.pill}`}
      >
        <span className="relative flex h-2 w-2">
          <span className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-60 ${tone.ping}`} />
          <span className={`relative inline-flex h-2 w-2 rounded-full ${tone.dot}`} />
        </span>
        {kind === "bad" ? "NOT ISOLATED" : "ISOLATED"}
        {kind === "ack" && <span className="hidden font-normal sm:inline">· break pending ack</span>}
      </button>
      {open && (
        <div
          role="dialog"
          aria-label="Network isolation"
          className="absolute right-0 z-20 mt-2 w-[min(20rem,calc(100vw-2rem))] space-y-3 rounded-xl border border-slate-200 bg-white p-3 text-xs shadow-lg"
        >
          {kind === "bad" && (
            <p className="rounded-lg bg-red-50 p-2 text-red-800">
              Not isolated: {status.current_reasons.join("; ") || "see Admin"}
            </p>
          )}
          {kind === "ok" && (
            <p className="rounded-lg bg-emerald-50 p-2 text-emerald-800">No network interface or default route is up.</p>
          )}
          {kind === "ack" && (
            <div className="rounded-lg bg-amber-50 p-2 text-amber-900">
              <p>
                Isolated now. A break at {status.break?.ts_utc ?? "an earlier time"} ({status.break?.reasons.join("; ")}) is
                not acknowledged, so answers are still flagged.
              </p>
              {isAdmin ? (
                <button
                  type="button"
                  disabled={busy}
                  className="mt-2 rounded-lg border border-amber-300 bg-white px-2.5 py-1 font-medium hover:bg-amber-100"
                  onClick={() => {
                    setBusy(true);
                    setErr(null);
                    api
                      .acknowledge()
                      .then((s) => setStatus({ ...status, ...s }))
                      .catch((e: unknown) => setErr(e instanceof Error ? e.message : String(e)))
                      .finally(() => setBusy(false));
                  }}
                >
                  {busy ? "Acknowledging…" : "Acknowledge break"}
                </button>
              ) : (
                <p className="mt-1">An admin must acknowledge it.</p>
              )}
              {err && <p className="mt-1 text-red-700">{err}</p>}
            </div>
          )}
          <Traffic t={status.traffic} />
        </div>
      )}
    </div>
  );
}
