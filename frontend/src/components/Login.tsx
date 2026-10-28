import { useState, type FormEvent } from "react";
import { api, type Me } from "../api";
import { SUBTITLE, TITLE } from "../constants";
import BrandMark from "./BrandMark";
import { AlertIcon, EyeIcon, EyeOffIcon, LockIcon } from "./icons";

export default function Login({ onLogin }: { onLogin: (me: Me) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      onLogin(await api.login(username, password));
    } catch (err) {
      const msg = err instanceof Error ? err.message : "sign-in failed";
      setError(msg === "HTTP 429" ? "Too many attempts. Wait a minute and try again." : msg);
    } finally {
      setBusy(false);
    }
  }

  const input =
    "mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 outline-none transition focus:border-brand-500 focus:ring-2 focus:ring-brand-100";

  return (
    <main className="flex min-h-full items-center justify-center bg-slate-50 p-4 font-sans">
      <div className="w-full max-w-sm animate-fade-in">
        <div className="mb-8 flex flex-col items-center text-center">
          <BrandMark className="mb-4 h-14 w-14" />
          <h1 className="font-display text-2xl leading-tight text-brand-900">{TITLE}</h1>
          <p className="mt-1 text-sm text-slate-500">{SUBTITLE}</p>
        </div>
        <form onSubmit={submit} className="rounded-md border border-slate-200 bg-white p-6 shadow-sm">
          <label className="mb-4 block text-sm font-medium text-slate-700">
            Username
            <input
              className={input}
              autoComplete="username"
              autoFocus
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
            />
          </label>
          <label htmlFor="password" className="block text-sm font-medium text-slate-700">
            Password
          </label>
          <div className="relative mb-4">
            <input
              id="password"
              className={`${input} pr-10`}
              type={show ? "text" : "password"}
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
            <button
              type="button"
              onClick={() => setShow((s) => !s)}
              className="absolute right-2 top-1/2 mt-0.5 -translate-y-1/2 rounded p-1 text-slate-400 hover:text-slate-700"
              aria-label={show ? "Hide password" : "Show password"}
            >
              {show ? <EyeOffIcon /> : <EyeIcon />}
            </button>
          </div>
          {error && (
            <p role="alert" className="mb-4 flex items-center gap-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">
              <AlertIcon className="shrink-0" /> {error}
            </p>
          )}
          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-lg bg-brand-700 py-2.5 font-medium text-white shadow-sm transition hover:bg-brand-800 disabled:opacity-60"
          >
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
        <p className="mt-4 flex items-center justify-center gap-1.5 text-xs text-slate-500">
          <LockIcon /> Runs fully offline. No data leaves this machine.
        </p>
      </div>
    </main>
  );
}
