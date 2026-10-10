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

  if (!status) return <span className="rounded bg-slate-200 px-2 py-1 text-xs">isolation: unknown</span>;
  const ok = status.state === "ISOLATED";
  const title = ok
    ? "No disallowed network interface or default route detected by the monitor."
    : `Isolation break: ${(status.break?.reasons ?? status.current_reasons).join("; ")}`;
  return (
    <span
      title={title}
      className={`rounded px-2 py-1 text-xs font-semibold ${ok ? "bg-green-100 text-green-800" : "bg-red-100 text-red-800"}`}
    >
      {ok ? "● ISOLATED" : "● NOT ISOLATED"}
    </span>
  );
}
