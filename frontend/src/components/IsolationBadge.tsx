import { useEffect, useState } from "react";
import { api, type AttestationStatus } from "../api";

export default function IsolationBadge() {
  const [status, setStatus] = useState<AttestationStatus | null>(null);

  useEffect(() => {
    let alive = true;
    const load = () =>
      api
        .attestationStatus()
        .then((s) => alive && setStatus(s))
        .catch(() => alive && setStatus(null));
    load();
    const t = window.setInterval(load, 5000);
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
  const ok = status.state === "ISOLATED";
  const reasons = status.break?.reasons ?? status.current_reasons ?? [];
  const title = ok
    ? "No disallowed network interface or default route detected by the monitor."
    : `Isolation break: ${reasons.join("; ") || "see Admin"}`;
  return (
    <span
      title={title}
      className={`inline-flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ${ok ? "bg-emerald-50 text-emerald-800 ring-emerald-200" : "bg-red-50 text-red-800 ring-red-200"}`}
    >
      <span className="relative flex h-2 w-2">
        <span className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-60 ${ok ? "bg-emerald-400" : "bg-red-400"}`} />
        <span className={`relative inline-flex h-2 w-2 rounded-full ${ok ? "bg-emerald-500" : "bg-red-500"}`} />
      </span>
      {ok ? "ISOLATED" : "NOT ISOLATED"}
    </span>
  );
}
