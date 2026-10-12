import { useEffect, useState } from "react";
import { api, type BlockVerification } from "../api";
import { AlertIcon, CheckIcon, ShieldIcon, XIcon } from "./icons";

export default function VerifyDialog({ index, onClose }: { index: number; onClose: () => void }) {
  const [result, setResult] = useState<BlockVerification | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .verifyBlock(index)
      .then(setResult)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, [index]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const b = result?.block;
  return (
    <div
      className="fixed inset-0 z-40 flex items-center justify-center bg-slate-900/50 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="verify-title"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="scroll-thin max-h-[90vh] w-full max-w-2xl animate-fade-in overflow-y-auto rounded-2xl bg-white shadow-2xl">
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-slate-100 bg-white/95 px-6 py-4 backdrop-blur">
          <h2 id="verify-title" className="flex items-center gap-2 text-lg font-semibold">
            <ShieldIcon className="text-brand-600" /> Verify answer record #{index}
          </h2>
          <button onClick={onClose} aria-label="Close" className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-900">
            <XIcon />
          </button>
        </div>
        <div className="space-y-5 px-6 py-5">
          {error && <p className="text-red-700">{error}</p>}
          {!result && !error && <p className="text-slate-500">Verifying the chain…</p>}
          {result && b && (
            <>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className={`rounded-xl p-4 ring-1 ${result.chain_valid_up_to_block ? "bg-emerald-50 ring-emerald-200" : "bg-red-50 ring-red-200"}`}>
                  <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Chain integrity</p>
                  <p className={`mt-1 flex items-center gap-1.5 text-lg ${result.chain_valid_up_to_block ? "text-emerald-800" : "text-red-800"}`}>
                    {result.chain_valid_up_to_block ? <CheckIcon /> : <AlertIcon />}
                    <strong>{result.chain_valid_up_to_block ? "valid" : "BROKEN"}</strong>
                  </p>
                  <p className="mt-1 text-xs text-slate-600">
                    {result.chain_valid_up_to_block
                      ? `Hashes, Ed25519 signatures, links and counters of ${result.chain_report.blocks} record(s) checked.`
                      : `At record #${result.chain_report.first_broken}: ${result.chain_report.broken_reason}`}
                  </p>
                </div>
                <div className={`rounded-xl p-4 ring-1 ${result.isolated ? "bg-emerald-50 ring-emerald-200" : "bg-red-50 ring-red-200"}`}>
                  <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Network at this answer</p>
                  <p className={`mt-1 flex items-center gap-1.5 text-lg ${result.isolated ? "text-emerald-800" : "text-red-800"}`}>
                    {result.isolated ? <CheckIcon /> : <AlertIcon />}
                    <strong>{result.isolated ? "ISOLATED" : "NOT ISOLATED"}</strong>
                  </p>
                  {result.isolated ? (
                    <p className="mt-1 text-xs text-slate-600">No disallowed interface or default route was up.</p>
                  ) : (
                    <ul className="mt-1 space-y-0.5 text-xs text-red-800">
                      {result.isolation_reasons.map((r) => (
                        <li key={r}>• {r}</li>
                      ))}
                      {b.monitor_state !== "ISOLATED" && <li>• an earlier isolation break was not yet acknowledged (Admin page)</li>}
                    </ul>
                  )}
                </div>
              </div>

              <section>
                <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
                  <h3 className="text-sm font-semibold">Network snapshot ({b.net.platform})</h3>
                  <p className="text-xs text-slate-500">
                    Default route: IPv4 <strong>{b.net.default_route_v4 ? "present" : "none"}</strong> · IPv6{" "}
                    <strong>{b.net.default_route_v6 ? "present" : "none"}</strong>
                  </p>
                </div>
                <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200">
                  {[...b.net.interfaces]
                    .sort((x, y) => Number(y.up) - Number(x.up))
                    .map((i) => (
                      <li key={i.name} className={`px-3 py-2 ${i.up ? "" : "opacity-60"}`}>
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="min-w-0 flex-1 truncate text-sm font-medium" title={i.name}>
                            {i.name}
                          </span>
                          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] text-slate-600">{i.kind}</span>
                          <span
                            className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${i.up ? "bg-amber-100 text-amber-900" : "bg-slate-100 text-slate-500"}`}
                          >
                            {i.up ? "up" : "down"}
                          </span>
                        </div>
                        {i.addrs.length > 0 && <p className="mt-0.5 break-all font-mono text-[11px] text-slate-500">{i.addrs.join(" · ")}</p>}
                      </li>
                    ))}
                </ul>
              </section>

              <details className="group rounded-xl border border-slate-200 px-4 py-3">
                <summary className="cursor-pointer text-sm font-semibold text-slate-700">Record details (hashes, signing key)</summary>
                <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-xs">
                  <dt className="text-slate-500">Time (UTC)</dt>
                  <dd>{b.ts_utc}</dd>
                  <dt className="text-slate-500">Counter</dt>
                  <dd>{b.counter}</dd>
                  <dt className="text-slate-500">Record hash</dt>
                  <dd className="break-all font-mono">{b.block_hash}</dd>
                  <dt className="text-slate-500">Previous hash</dt>
                  <dd className="break-all font-mono">{b.prev_hash}</dd>
                  <dt className="text-slate-500">Signing key id</dt>
                  <dd className="break-all font-mono">{b.key_id}</dd>
                </dl>
              </details>

              <details className="rounded-xl bg-amber-50 px-4 py-3 text-xs text-amber-900">
                <summary className="cursor-pointer text-sm font-semibold">What this does and does not show</summary>
                <ul className="ml-4 mt-2 list-disc space-y-1">
                  {result.limits.map((l) => (
                    <li key={l}>{l}</li>
                  ))}
                </ul>
              </details>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
