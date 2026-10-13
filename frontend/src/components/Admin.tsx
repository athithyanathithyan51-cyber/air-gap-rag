import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api, type AttestationStatus, type AuditEntry, type ChainReport, type Me, type Role } from "../api";
import { AlertIcon, CheckIcon, DownloadIcon, RetryIcon, ShieldIcon, XIcon } from "./icons";

const btn = "inline-flex items-center gap-1.5 rounded-lg border border-slate-300 px-3 py-1.5 text-sm transition hover:bg-slate-50";
const field = "rounded-lg border border-slate-300 px-3 py-1.5 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100";

export default function Admin({ me }: { me: Me }) {
  const [users, setUsers] = useState<(Me & { active: boolean })[]>([]);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [status, setStatus] = useState<AttestationStatus | null>(null);
  const [report, setReport] = useState<ChainReport | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [msg, setMsg] = useState<{ text: string; ok: boolean } | null>(null);
  const [form, setForm] = useState({ username: "", password: "", role: "user" as Role });

  const fail = (e: unknown) => setMsg({ text: e instanceof Error ? e.message : String(e), ok: false });
  const load = useCallback(() => {
    api.users().then(setUsers).catch(fail);
    api.audit().then(setAudit).catch(fail);
    api.attestationStatus().then(setStatus).catch(fail);
  }, []);
  useEffect(load, [load]);

  async function create(e: FormEvent) {
    e.preventDefault();
    try {
      await api.createUser(form.username, form.password, form.role);
      setMsg({ text: `Created ${form.username}`, ok: true });
      setForm({ username: "", password: "", role: "user" });
      load();
    } catch (err) {
      fail(err);
    }
  }

  function verifyAll() {
    setVerifying(true);
    api
      .verifyAll()
      .then(setReport)
      .catch(fail)
      .finally(() => setVerifying(false));
  }

  return (
    <div className="scroll-thin h-full overflow-y-auto p-4">
      <div className="mx-auto grid max-w-6xl gap-4 py-2 lg:grid-cols-2">
        <h2 className="text-xl font-semibold tracking-tight lg:col-span-2">Administration</h2>
        {msg && (
          <p
            role="status"
            className={`flex items-center gap-2 rounded-lg px-3 py-2 text-sm lg:col-span-2 ${msg.ok ? "bg-emerald-50 text-emerald-800" : "bg-red-50 text-red-800"}`}
          >
            {msg.ok ? <CheckIcon /> : <AlertIcon />}
            <span className="flex-1">{msg.text}</span>
            <button onClick={() => setMsg(null)} aria-label="Dismiss" className="rounded p-0.5 hover:bg-black/5">
              <XIcon />
            </button>
          </p>
        )}

        <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <h3 className="mb-3 flex items-center gap-2 font-semibold">
            <ShieldIcon className="text-brand-600" /> Isolation attestation
          </h3>
          {status && (
            <>
              <div className="grid grid-cols-3 gap-2 text-center">
                <div className={`rounded-lg p-2 ${status.state === "ISOLATED" ? "bg-emerald-50 text-emerald-800" : "bg-red-50 text-red-800"}`}>
                  <p className="text-[11px] uppercase tracking-wide opacity-70">Monitor</p>
                  <p className="text-sm font-semibold">{status.state}</p>
                </div>
                <div className="rounded-lg bg-slate-50 p-2">
                  <p className="text-[11px] uppercase tracking-wide text-slate-500">Records</p>
                  <p className="text-sm font-semibold">{status.blocks}</p>
                </div>
                <div className="rounded-lg bg-slate-50 p-2">
                  <p className="text-[11px] uppercase tracking-wide text-slate-500">Policy</p>
                  <p className="text-sm font-semibold">{status.policy.mode}</p>
                </div>
              </div>
              <p className="mt-2 text-xs text-slate-500">Allowed interfaces: {status.policy.allow.join(", ") || "none"}</p>
              {status.break && (
                <div className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-800">
                  <p className="font-medium">Break at {status.break.ts_utc}</p>
                  <p className="mt-0.5">{status.break.reasons.join("; ")}</p>
                  <button
                    className="mt-2 rounded-lg border border-red-300 bg-white px-2.5 py-1 text-xs font-medium hover:bg-red-100"
                    onClick={() =>
                      api
                        .acknowledge()
                        .then((s) => {
                          setStatus({ ...status, ...s });
                          setMsg({ text: "Break acknowledged; new answers will be recorded as isolated again.", ok: true });
                        })
                        .catch(fail)
                    }
                  >
                    Acknowledge (machine is isolated again)
                  </button>
                </div>
              )}
              <p className="mt-2 break-all font-mono text-[10px] text-slate-400">signing key id {status.key_id}</p>
            </>
          )}
          <div className="mt-4 flex flex-wrap gap-2">
            <button className={btn} onClick={verifyAll} disabled={verifying}>
              <CheckIcon /> {verifying ? "Verifying…" : "Verify whole chain"}
            </button>
            <a className={btn} href="/api/attestation/export">
              <DownloadIcon /> Export chain (.jsonl)
            </a>
            <a className={btn} href="/api/attestation/pubkey">
              <DownloadIcon /> Public key
            </a>
          </div>
          {report && (
            <p className={`mt-3 rounded-lg px-3 py-2 text-sm ${report.valid ? "bg-emerald-50 text-emerald-800" : "bg-red-50 text-red-800"}`}>
              {report.valid ? "✔ Chain valid" : `✘ Chain BROKEN at #${report.first_broken}: ${report.broken_reason}`} · {report.blocks}{" "}
              records · {report.not_isolated_count} not isolated
              {report.first_not_isolated != null && ` (first #${report.first_not_isolated})`}
            </p>
          )}
          <p className="mt-3 text-xs text-slate-500">
            Auditors can check the exported chain offline:{" "}
            <code className="rounded bg-slate-100 px-1">python verify_chain.py chain.jsonl --pubkey attestation.pub</code>
          </p>
        </section>

        <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <h3 className="mb-3 font-semibold">Users</h3>
          <form onSubmit={create} className="mb-4 flex flex-wrap gap-2 text-sm [&>input]:min-w-0 [&>input]:flex-1 [&>input]:basis-36">
            <input
              className={field}
              placeholder="username"
              aria-label="New username"
              value={form.username}
              onChange={(e) => setForm({ ...form, username: e.target.value })}
              required
            />
            <input
              className={field}
              placeholder="password (min 10)"
              aria-label="New user password"
              type="password"
              minLength={10}
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              required
            />
            <select
              className={field}
              aria-label="Role"
              value={form.role}
              onChange={(e) => setForm({ ...form, role: e.target.value as Role })}
            >
              <option value="user">user</option>
              <option value="admin">admin</option>
            </select>
            <button className="whitespace-nowrap rounded-lg bg-brand-700 px-3 py-1.5 font-medium text-white hover:bg-brand-800">Add user</button>
          </form>
          <ul className="divide-y divide-slate-100 text-sm">
            {users.map((u) => (
              <li key={u.id} className="flex items-center gap-3 py-2">
                <span className="flex h-7 w-7 items-center justify-center rounded-full bg-slate-200 text-[11px] font-semibold uppercase text-slate-700">
                  {u.username.slice(0, 2)}
                </span>
                <span className="flex-1 font-medium">
                  {u.username}
                  {u.id === me.id && <span className="ml-1 text-xs font-normal text-slate-400">(you)</span>}
                </span>
                <span className={`rounded-full px-2 py-0.5 text-xs ${u.role === "admin" ? "bg-brand-50 text-brand-800" : "bg-slate-100 text-slate-600"}`}>{u.role}</span>
                <span className={`rounded-full px-2 py-0.5 text-xs ${u.active ? "bg-emerald-50 text-emerald-800" : "bg-slate-100 text-slate-400"}`}>
                  {u.active ? "active" : "disabled"}
                </span>
                <span className="w-16 text-right">
                  {u.id !== me.id && (
                    <button
                      className="text-xs text-brand-700 hover:underline"
                      onClick={() => api.updateUser(u.id, { active: !u.active }).then(load).catch(fail)}
                    >
                      {u.active ? "Disable" : "Enable"}
                    </button>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </section>

        <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm lg:col-span-2">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="font-semibold">Audit log (latest 200)</h3>
            <button className={btn} onClick={load}>
              <RetryIcon /> Refresh
            </button>
          </div>
          <div className="scroll-thin max-h-96 overflow-auto">
            <table className="w-full text-left text-xs">
              <thead className="sticky top-0 bg-white text-slate-500">
                <tr>
                  <th className="py-1.5 pr-2 font-medium">Time</th>
                  <th className="pr-2 font-medium">Actor</th>
                  <th className="pr-2 font-medium">Action</th>
                  <th className="font-medium">Detail</th>
                </tr>
              </thead>
              <tbody>
                {audit.map((a) => (
                  <tr key={a.id} className="border-t border-slate-100 align-top hover:bg-slate-50">
                    <td className="whitespace-nowrap py-1.5 pr-2 text-slate-500">{new Date(a.ts).toLocaleString()}</td>
                    <td className="pr-2">{a.actor}</td>
                    <td className="pr-2">
                      <span
                        className={`rounded px-1.5 py-0.5 font-medium ${a.action.includes("fail") ? "bg-red-50 text-red-800" : "bg-slate-100 text-slate-700"}`}
                      >
                        {a.action}
                      </span>
                    </td>
                    <td className="break-all font-mono text-slate-600">{JSON.stringify(a.detail)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </div>
  );
}
