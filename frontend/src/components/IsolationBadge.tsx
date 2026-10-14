import { useEffect, useState } from "react";
import { api, type AttestationStatus } from "../api";

// Three looks: isolated (green), isolated now but a past break is still unacknowledged (amber),
// and not isolated right now (red). The amber state keeps answers flagged until an admin acknowledges.
const TONE = {
  ok: { pill: "bg-emerald-50 text-emerald-800 ring-emerald-200", ping: "bg-emerald-400", dot: "bg-emerald-500" },
  ack: { pill: "bg-amber-50 text-amber-800 ring-amber-300", ping: "bg-amber-400", dot: "bg-amber-500" },
  bad: { pill: "bg-red-50 text-red-800 ring-red-200", ping: "bg-red-400", dot: "bg-red-500" },
};

export default function IsolationBadge({ isAdmin = false }: { isAdmin?: boolean }) {
  const [status, setStatus] = useState<AttestationStatus | null>(null);
  const [busy, setBusy] = useState(false);

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
  const canAck = kind === "ack" && isAdmin;
  const title =
    kind === "ok"
      ? "No disallowed network interface or default route detected by the monitor."
      : kind === "bad"
        ? `Not isolated: ${status.current_reasons.join("; ") || "see Admin"}`
        : `Isolated now, but a break at ${status.break?.ts_utc ?? "an earlier time"} is unacknowledged ` +
          `(${status.break?.reasons.join("; ") ?? ""}). Answers stay flagged until an admin acknowledges` +
          (canAck ? ". Click to acknowledge." : ".");

  const body = (
    <>
      <span className="relative flex h-2 w-2">
        <span className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-60 ${tone.ping}`} />
        <span className={`relative inline-flex h-2 w-2 rounded-full ${tone.dot}`} />
      </span>
      {kind === "bad" ? "NOT ISOLATED" : "ISOLATED"}
      {kind === "ack" && (
        <span className="font-normal">· {canAck ? (busy ? "acknowledging…" : "acknowledge break") : "break pending ack"}</span>
      )}
    </>
  );
  const cls = `inline-flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ${tone.pill}`;

  if (canAck)
    return (
      <button
        type="button"
        title={title}
        disabled={busy}
        className={`${cls} hover:bg-amber-100`}
        onClick={() => {
          setBusy(true);
          api
            .acknowledge()
            .then((s) => setStatus({ ...status, ...s }))
            .catch(() => undefined)
            .finally(() => setBusy(false));
        }}
      >
        {body}
      </button>
    );
  return (
    <span title={title} className={cls}>
      {body}
    </span>
  );
}
