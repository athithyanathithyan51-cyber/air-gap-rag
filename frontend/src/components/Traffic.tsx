import { useEffect, useState } from "react";
import { api, type CaptureDetail, type CaptureRow, type Me } from "../api";
import { AlertIcon, CheckIcon, TrafficIcon } from "./icons";

const PAGE = 100;

function clock(seconds: number): string {
  const d = new Date(seconds * 1000);
  return `${d.toLocaleTimeString("en-GB")}.${String(d.getMilliseconds()).padStart(3, "0")}`;
}

function bytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

function duration(first: number | null, last: number | null): string {
  if (first === null || last === null) return "–";
  const s = Math.max(0, last - first);
  return s < 60 ? `${s.toFixed(1)} s` : `${Math.floor(s / 60)} min ${Math.round(s % 60)} s`;
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-slate-200 bg-white px-4 py-3">
      <p className="text-xs text-slate-500">{label}</p>
      <p className="mt-1 font-mono text-lg tabular-nums text-slate-900">{value}</p>
    </div>
  );
}

function Verdict({ text }: { text: string | null }) {
  if (text === null) {
    return (
      <p className="rounded-md border border-slate-200 bg-white px-4 py-3 text-sm text-slate-500">
        No verdict file in this capture.
      </p>
    );
  }
  const pass = text.startsWith("PASS");
  return (
    <p
      role="status"
      className={`flex items-center gap-2 rounded-md px-4 py-3 text-sm font-medium ${pass ? "bg-emerald-50 text-emerald-800 ring-1 ring-emerald-200" : "bg-red-50 text-red-800 ring-1 ring-red-200"}`}
    >
      {pass ? <CheckIcon /> : <AlertIcon />} {text}
    </p>
  );
}

export default function Traffic({ me }: { me: Me }) {
  const [captures, setCaptures] = useState<CaptureRow[] | null>(null);
  const [name, setName] = useState<string | null>(null);
  const [detail, setDetail] = useState<CaptureDetail | null>(null);
  // Offsets of the pages visited so far; the last one is the page on screen.
  const [pages, setPages] = useState<number[]>([0]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api
      .captures()
      .then((rows) => {
        setCaptures(rows);
        setName(rows[0]?.name ?? null);
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
  }, []);

  const offset = pages[pages.length - 1];
  useEffect(() => {
    if (!name) return;
    let cancelled = false;
    setLoading(true);
    setError("");
    api
      .capture(name, offset, PAGE)
      .then((d) => !cancelled && setDetail(d))
      .catch((err: unknown) => !cancelled && setError(err instanceof Error ? err.message : String(err)))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [name, offset]);

  function pick(next: string) {
    setName(next);
    setPages([0]);
    setDetail(null);
  }

  const summary = detail?.summary;
  const maxProtocol = Math.max(1, ...(summary?.protocols.map((p) => p.count) ?? [1]));
  const last = detail?.packets.at(-1)?.number ?? offset;

  return (
    <div className="scroll-thin h-full overflow-y-auto px-4 py-6">
      <div className="mx-auto max-w-5xl space-y-6">
        <header className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="font-display text-2xl text-brand-900">Network traffic</h2>
            <p className="mt-1 text-sm text-slate-500">
              Packets recorded by the capture script while the laptop was offline. Read-only, for administrators.
            </p>
          </div>
          {captures && captures.length > 0 && (
            <label className="flex items-center gap-2 text-sm text-slate-600">
              Capture
              <select
                value={name ?? ""}
                onChange={(e) => pick(e.target.value)}
                className="rounded-lg border border-slate-200 bg-slate-50 px-2 py-1.5 font-mono text-xs text-slate-700 outline-none focus:border-brand-500"
              >
                {captures.map((c) => (
                  <option key={c.name} value={c.name}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>
          )}
        </header>

        {error && (
          <p role="alert" className="rounded-md bg-red-50 px-4 py-3 text-sm text-red-800">
            {error}
          </p>
        )}

        {captures && captures.length === 0 && (
          <section className="rounded-md border border-dashed border-slate-300 bg-white p-6">
            <h3 className="flex items-center gap-2 font-medium text-slate-900">
              <TrafficIcon /> No capture yet
            </h3>
            <p className="mt-2 text-sm text-slate-600">
              Turn Wi-Fi off, open PowerShell as administrator in the project folder, and run:
            </p>
            <code className="mt-3 block overflow-x-auto rounded-md bg-slate-100 px-3 py-2 font-mono text-xs text-slate-800">
              powershell -ExecutionPolicy Bypass -File scripts\capture-windows.ps1 -Seconds 120
            </code>
            <p className="mt-3 text-sm text-slate-500">
              Use the assistant while it runs. Then reload this page to see the packets.
            </p>
          </section>
        )}

        {detail && summary && (
          <>
            <Verdict text={detail.verdict} />

            <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <Stat label="Packets" value={summary.packets.toLocaleString()} />
              <Stat label="Data" value={bytes(summary.bytes)} />
              <Stat label="Duration" value={duration(summary.first, summary.last)} />
              <Stat label="Addresses seen" value={summary.talkers.length.toString()} />
            </section>

            {summary.truncated && (
              <p className="text-xs text-amber-700">Only the first 500,000 packets were counted.</p>
            )}

            <section className="grid gap-4 md:grid-cols-2">
              <div className="rounded-md border border-slate-200 bg-white p-4">
                <h3 className="mb-3 text-sm font-medium text-slate-900">Protocols</h3>
                {summary.protocols.length === 0 && <p className="text-sm text-slate-500">No decodable packets.</p>}
                <ul className="space-y-2">
                  {summary.protocols.map((p) => (
                    <li key={p.name} className="grid grid-cols-[6rem_1fr_3.5rem] items-center gap-3 text-xs">
                      <span className="truncate font-mono text-slate-700">{p.name}</span>
                      <span className="h-2 overflow-hidden rounded-full bg-slate-100">
                        <span
                          className="block h-full rounded-full bg-brand-500"
                          style={{ width: `${(p.count / maxProtocol) * 100}%` }}
                        />
                      </span>
                      <span className="text-right font-mono tabular-nums text-slate-500">{p.count}</span>
                    </li>
                  ))}
                </ul>
              </div>
              <div className="rounded-md border border-slate-200 bg-white p-4">
                <h3 className="mb-3 text-sm font-medium text-slate-900">Busiest addresses</h3>
                {summary.talkers.length === 0 && <p className="text-sm text-slate-500">None.</p>}
                <ul className="space-y-1.5 font-mono text-xs">
                  {summary.talkers.map((t) => (
                    <li key={t.address} className="flex justify-between gap-3 text-slate-700">
                      <span className="truncate">{t.address}</span>
                      <span className="tabular-nums text-slate-500">{t.count}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </section>

            <section className="rounded-md border border-slate-200 bg-white">
              <div className="flex items-center justify-between border-b border-slate-200 px-4 py-2.5">
                <h3 className="text-sm font-medium text-slate-900">Packets</h3>
                <div className="flex items-center gap-2 text-xs text-slate-500">
                  <button
                    type="button"
                    disabled={pages.length < 2 || loading}
                    onClick={() => setPages(pages.slice(0, -1))}
                    className="rounded-md border border-slate-200 px-2.5 py-1 hover:bg-slate-50 disabled:opacity-40"
                  >
                    Previous
                  </button>
                  <button
                    type="button"
                    disabled={loading || detail.packets.length < PAGE || last >= summary.packets}
                    onClick={() => setPages([...pages, last])}
                    className="rounded-md border border-slate-200 px-2.5 py-1 hover:bg-slate-50 disabled:opacity-40"
                  >
                    Next
                  </button>
                </div>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[44rem] text-left font-mono text-xs">
                  <thead className="text-slate-500">
                    <tr className="border-b border-slate-200">
                      <th className="px-3 py-2 font-medium">No.</th>
                      <th className="px-3 py-2 font-medium">Time</th>
                      <th className="px-3 py-2 font-medium">Source</th>
                      <th className="px-3 py-2 font-medium">Destination</th>
                      <th className="px-3 py-2 font-medium">Protocol</th>
                      <th className="px-3 py-2 text-right font-medium">Length</th>
                      <th className="px-3 py-2 font-medium">Info</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail.packets.map((p) => (
                      <tr key={p.number} className="border-b border-slate-100 text-slate-700 last:border-0">
                        <td className="px-3 py-1.5 tabular-nums text-slate-500">{p.number}</td>
                        <td className="px-3 py-1.5 tabular-nums">{clock(p.time)}</td>
                        <td className="px-3 py-1.5">{p.src}</td>
                        <td className="px-3 py-1.5">{p.dst}</td>
                        <td className="px-3 py-1.5">{p.protocol}</td>
                        <td className="px-3 py-1.5 text-right tabular-nums">{p.length}</td>
                        <td className="px-3 py-1.5 text-slate-500">
                          {[p.ports, p.info].filter(Boolean).join("  ")}
                        </td>
                      </tr>
                    ))}
                    {detail.packets.length === 0 && (
                      <tr>
                        <td colSpan={7} className="px-3 py-6 text-center text-slate-500">
                          No packets on this page.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </section>
          </>
        )}

        {loading && !detail && <p className="text-sm text-slate-500">Reading capture…</p>}
        <p className="text-xs text-slate-400">Signed in as {me.username}. Captures stay on this machine.</p>
      </div>
    </div>
  );
}
