import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api, type AttestationStatus, type AuditEntry, type ChainReport, type Me, type Role } from "../api";

export default function Admin({ me }: { me: Me }) {
  const [users, setUsers] = useState<(Me & { active: boolean })[]>([]);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [status, setStatus] = useState<AttestationStatus | null>(null);
  const [report, setReport] = useState<ChainReport | null>(null);
  const [msg, setMsg] = useState("");
  const [form, setForm] = useState({ username: "", password: "", role: "user" as Role });

  const fail = (e: unknown) => setMsg(e instanceof Error ? e.message : String(e));
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
      setMsg(`Created ${form.username}`);
      setForm({ username: "", password: "", role: "user" });
      load();
    } catch (err) {
      fail(err);
    }
  }

  return (
    <div className="h-full overflow-y-auto p-4">
      <div className="mx-auto grid max-w-6xl gap-6 lg:grid-cols-2">
        {msg && <p className="rounded bg-slate-200 p-2 text-sm lg:col-span-2">{msg}</p>}

        <section className="rounded-lg bg-white p-4 shadow-sm">
          <h2 className="mb-2 font-semibold">Isolation attestation</h2>
          {status && (
            <>
              <p className={status.state === "ISOLATED" ? "text-green-700" : "text-red-700"}>
                Monitor state: <strong>{status.state}</strong> · {status.blocks} answer record(s) · policy {status.policy.mode}{" "}
                (allow: {status.policy.allow.join(", ") || "none"})
              </p>
              {status.break && (
                <div className="mt-2 rounded bg-red-50 p-2 text-sm text-red-800">
                  Break at {status.break.ts_utc}: {status.break.reasons.join("; ")}
                  <button
                    className="ml-2 rounded border border-red-300 px-2 py-0.5 text-xs"
                    onClick={() =>
                      api
                        .acknowledge()
                        .then((s) => {
                          setStatus({ ...status, ...s });
                          setMsg("Break acknowledged; new answers will be recorded as isolated again.");
                        })
                        .catch(fail)
                    }
                  >
                    Acknowledge (machine is isolated again)
                  </button>
                </div>
              )}
              <p className="mt-1 break-all font-mono text-[10px] text-slate-400">signing key id {status.key_id}</p>
            </>
          )}
          <div className="mt-3 flex flex-wrap gap-2 text-sm">
            <button className="rounded border border-slate-300 px-2 py-1" onClick={() => api.verifyAll().then(setReport).catch(fail)}>
              Verify whole chain
            </button>
            <a className="rounded border border-slate-300 px-2 py-1" href="/api/attestation/export">
              Export chain (.jsonl)
            </a>
            <a className="rounded border border-slate-300 px-2 py-1" href="/api/attestation/pubkey">
              Public key
            </a>
          </div>
          {report && (
            <p className={`mt-2 text-sm ${report.valid ? "text-green-700" : "text-red-700"}`}>
              {report.valid ? "Chain valid" : `Chain BROKEN at #${report.first_broken}: ${report.broken_reason}`} ·{" "}
              {report.blocks} records · {report.not_isolated_count} not isolated
              {report.first_not_isolated != null && ` (first #${report.first_not_isolated})`}
            </p>
          )}
          <p className="mt-2 text-xs text-slate-500">
            Auditors can check the exported chain offline: <code>python verify_chain.py chain.jsonl --pubkey attestation.pub</code>
          </p>
        </section>

        <section className="rounded-lg bg-white p-4 shadow-sm">
          <h2 className="mb-2 font-semibold">Users</h2>
          <form onSubmit={create} className="mb-3 flex flex-wrap gap-2 text-sm">
            <input
              className="rounded border border-slate-300 px-2 py-1"
              placeholder="username"
              aria-label="New username"
              value={form.username}
              onChange={(e) => setForm({ ...form, username: e.target.value })}
              required
            />
            <input
              className="rounded border border-slate-300 px-2 py-1"
              placeholder="password (min 10)"
              aria-label="New user password"
              type="password"
              minLength={10}
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              required
            />
            <select
              className="rounded border border-slate-300 px-2 py-1"
              aria-label="Role"
              value={form.role}
              onChange={(e) => setForm({ ...form, role: e.target.value as Role })}
            >
              <option value="user">user</option>
              <option value="admin">admin</option>
            </select>
            <button className="rounded bg-blue-700 px-3 py-1 text-white">Add user</button>
          </form>
          <table className="w-full text-left text-sm">
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className="border-t border-slate-100">
                  <td className="py-1">{u.username}</td>
                  <td>{u.role}</td>
                  <td className={u.active ? "text-green-700" : "text-slate-400"}>{u.active ? "active" : "disabled"}</td>
                  <td>
                    {u.id !== me.id && (
                      <button
                        className="text-xs text-blue-700 hover:underline"
                        onClick={() => api.updateUser(u.id, { active: !u.active }).then(load).catch(fail)}
                      >
                        {u.active ? "Disable" : "Enable"}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="rounded-lg bg-white p-4 shadow-sm lg:col-span-2">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-semibold">Audit log (latest 200)</h2>
            <button className="text-sm text-blue-700 hover:underline" onClick={load}>
              Refresh
            </button>
          </div>
          <div className="max-h-96 overflow-y-auto">
            <table className="w-full text-left text-xs">
              <tbody>
                {audit.map((a) => (
                  <tr key={a.id} className="border-t border-slate-100 align-top">
                    <td className="whitespace-nowrap py-1 pr-2 text-slate-500">{new Date(a.ts).toLocaleString()}</td>
                    <td className="pr-2">{a.actor}</td>
                    <td className="pr-2 font-medium">{a.action}</td>
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
