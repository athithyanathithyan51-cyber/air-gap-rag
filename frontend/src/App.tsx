import { useEffect, useState } from "react";
import { api, type Me } from "./api";
import Admin from "./components/Admin";
import Chat from "./components/Chat";
import Documents from "./components/Documents";
import Help from "./components/Help";
import IsolationBadge from "./components/IsolationBadge";
import Login from "./components/Login";
import { SUBTITLE, TITLE } from "./constants";

type Tab = "chat" | "documents" | "admin" | "help";

export default function App() {
  const [me, setMe] = useState<Me | null | undefined>(undefined);
  const [tab, setTab] = useState<Tab>("chat");

  useEffect(() => {
    api
      .me()
      .then(setMe)
      .catch(() => setMe(null));
  }, []);

  if (me === undefined) return <p className="p-8 text-slate-500">Loading…</p>;
  if (me === null) return <Login onLogin={setMe} />;

  const tabs: [Tab, string][] = [
    ["chat", "Chat"],
    ["documents", "Documents"],
    ...(me.role === "admin" ? ([["admin", "Admin"]] as [Tab, string][]) : []),
    ["help", "Help & limits"],
  ];

  return (
    <div className="flex h-screen flex-col font-sans text-slate-900">
      <header className="flex flex-wrap items-center gap-4 border-b border-slate-200 bg-white px-4 py-2">
        <div className="mr-auto">
          <h1 className="text-base font-bold leading-tight">{TITLE}</h1>
          <p className="text-xs text-slate-500">{SUBTITLE}</p>
        </div>
        <IsolationBadge />
        <nav className="flex gap-1" aria-label="Main">
          {tabs.map(([key, label]) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              aria-current={tab === key ? "page" : undefined}
              className={`rounded px-3 py-1.5 text-sm ${tab === key ? "bg-blue-700 text-white" : "hover:bg-slate-100"}`}
            >
              {label}
            </button>
          ))}
        </nav>
        <span className="text-sm text-slate-600">
          {me.username} <span className="text-xs text-slate-400">({me.role})</span>
        </span>
        <button
          className="rounded border border-slate-300 px-2 py-1 text-sm hover:bg-slate-100"
          onClick={() => {
            api.logout().finally(() => setMe(null));
          }}
        >
          Sign out
        </button>
      </header>
      <main className="min-h-0 flex-1 overflow-hidden bg-slate-50">
        {tab === "chat" && <Chat me={me} />}
        {tab === "documents" && <Documents me={me} />}
        {tab === "admin" && me.role === "admin" && <Admin me={me} />}
        {tab === "help" && <Help />}
      </main>
    </div>
  );
}
