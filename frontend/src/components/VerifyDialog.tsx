import { useEffect, useState } from "react";
import { api, type BlockVerification } from "../api";

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
    <div className="fixed inset-0 z-10 flex items-center justify-center bg-black/40 p-4" role="dialog" aria-modal="true" aria-labelledby="verify-title">
      <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-lg bg-white p-5 shadow-xl">
        <div className="mb-3 flex items-start justify-between">
          <h2 id="verify-title" className="text-lg font-semibold">
            Verify answer record #{index}
          </h2>
          <button onClick={onClose} aria-label="Close" className="text-slate-500 hover:text-slate-900">
            ✕
          </button>
        </div>
        {error && <p className="text-red-700">{error}</p>}
        {!result && !error && <p className="text-slate-500">Verifying the chain…</p>}
        {result && b && (
          <>
            <ul className="mb-4 space-y-2">
              <li className={result.chain_valid_up_to_block ? "text-green-800" : "text-red-800"}>
                {result.chain_valid_up_to_block ? "✔" : "✘"} Chain integrity up to this record:{" "}
                <strong>{result.chain_valid_up_to_block ? "valid" : "BROKEN"}</strong>
                {!result.chain_valid_up_to_block && (
                  <span>
                    {" "}
                    at record #{result.chain_report.first_broken}: {result.chain_report.broken_reason}
                  </span>
                )}
                <span className="block text-xs text-slate-500">
                  Hashes, Ed25519 signatures, links and counters of {result.chain_report.blocks} record(s) checked.
                </span>
              </li>
              <li className={result.isolated ? "text-green-800" : "text-red-800"}>
                {result.isolated ? "✔" : "✘"} Network isolation at this answer:{" "}
                <strong>{result.isolated ? "ISOLATED" : "NOT ISOLATED"}</strong>
                {!result.isolated && (
                  <ul className="ml-5 list-disc text-sm">
                    {result.isolation_reasons.map((r) => (
                      <li key={r}>{r}</li>
                    ))}
                    {b.monitor_state !== "ISOLATED" && <li>an earlier isolation break was not yet acknowledged</li>}
                  </ul>
                )}
              </li>
            </ul>
            <h3 className="mb-1 text-sm font-semibold">Network snapshot ({b.net.platform})</h3>
            <table className="mb-3 w-full text-left text-xs">
              <thead>
                <tr className="border-b">
                  <th className="py-1">Interface</th>
                  <th>Kind</th>
                  <th>State</th>
                  <th>Addresses</th>
                </tr>
              </thead>
              <tbody>
                {b.net.interfaces.map((i) => (
                  <tr key={i.name} className="border-b border-slate-100">
                    <td className="py-1 font-mono">{i.name}</td>
                    <td>{i.kind}</td>
                    <td className={i.up ? "font-semibold" : "text-slate-400"}>{i.up ? "up" : "down"}</td>
                    <td className="font-mono">{i.addrs.join(", ") || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mb-3 text-xs">
              Default route: IPv4 {b.net.default_route_v4 ? "present" : "none"}, IPv6 {b.net.default_route_v6 ? "present" : "none"}
            </p>
            <dl className="mb-4 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
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
            <div className="rounded bg-amber-50 p-3 text-xs text-amber-900">
              <p className="mb-1 font-semibold">What this does and does not show</p>
              <ul className="ml-4 list-disc space-y-0.5">
                {result.limits.map((l) => (
                  <li key={l}>{l}</li>
                ))}
              </ul>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
