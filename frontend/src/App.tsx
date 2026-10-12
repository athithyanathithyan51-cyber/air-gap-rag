import { useEffect, useState, type ComponentType, type SVGProps } from "react";
import { api, type Me } from "./api";
import Admin from "./components/Admin";
import Chat from "./components/Chat";
import Documents from "./components/Documents";
import Help from "./components/Help";
import { ChatIcon, FileIcon, HelpIcon, LogoutIcon, SettingsIcon, ShieldIcon } from "./components/icons";
import IsolationBadge from "./components/IsolationBadge";
import Login from "./components/Login";
import { SUBTITLE, TITLE } from "./constants";

type Tab = "chat" | "documents" | "admin" | "help";
type TabDef = { key: Tab; label: string; Icon: ComponentType<SVGProps<SVGSVGElement>> };

export default function App() {
  const [me, setMe] = useState<Me | null | undefined>(undefined);
  const [tab, setTab] = useState<Tab>("chat");

  useEffect(() => {
    api
      .me()
      .then(setMe)
      .catch(() => setMe(null));
  }, []);

  if (me === undefined)
    return (
      <div className="flex h-full items-center justify-center">
        <span className="flex gap-1 text-brand-500">
          <span className="typing-dot" />
          <span className="typing-dot" />
          <span className="typing-dot" />
        </span>
        <span className="sr-only">Loading…</span>
      </div>
    );
  if (me === null)
    return (
      <Login
        onLogin={(m) => {
          setTab("chat");
          setMe(m);
        }}
      />
    );

  const tabs: TabDef[] = [
    { key: "chat", label: "Chat", Icon: ChatIcon },
    { key: "documents", label: "Documents", Icon: FileIcon },
    ...(me.role === "admin" ? [{ key: "admin" as Tab, label: "Admin", Icon: SettingsIcon }] : []),
    { key: "help", label: "Help & limits", Icon: HelpIcon },
  ];

  return (
    <div className="flex h-full flex-col font-sans text-slate-900">
      <header className="flex items-center gap-3 border-b border-slate-200 bg-white px-3 py-2 sm:px-4">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-brand-500 to-brand-800 text-xl text-white shadow-sm">
          <ShieldIcon />
        </div>
        <div className="mr-auto min-w-0">
          <h1 className="truncate text-sm font-bold leading-tight sm:text-base" title={TITLE}>
            {TITLE}
          </h1>
          <p className="truncate text-xs text-slate-500">{SUBTITLE}</p>
        </div>
        <IsolationBadge />
        <div className="flex items-center gap-2 border-l border-slate-200 pl-3">
          <span
            className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-800 text-xs font-semibold uppercase text-white"
            title={`${me.username} (${me.role})`}
            aria-hidden="true"
          >
            {me.username.slice(0, 2)}
          </span>
          <span className="hidden text-sm leading-tight lg:block">
            {me.username}
            <span className="block text-[11px] text-slate-400">{me.role}</span>
          </span>
          <button
            className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-900"
            title="Sign out"
            aria-label="Sign out"
            onClick={() => {
              api.logout().finally(() => setMe(null));
            }}
          >
            <LogoutIcon />
          </button>
        </div>
      </header>

      {/* One nav: a tab strip under the header on wide screens, a bottom bar on phones. */}
      <nav
        className="order-last flex border-t border-slate-200 bg-white md:order-none md:gap-1 md:border-b md:border-t-0 md:px-4 md:py-1.5"
        aria-label="Main"
      >
        {tabs.map(({ key, label, Icon }) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            aria-current={tab === key ? "page" : undefined}
            className={`flex flex-1 flex-col items-center gap-0.5 py-2 text-[11px] transition md:flex-none md:flex-row md:gap-1.5 md:rounded-lg md:px-3 md:py-1.5 md:text-sm md:font-medium ${
              tab === key ? "text-brand-700 md:bg-brand-50 md:text-brand-800" : "text-slate-500 md:text-slate-600 md:hover:bg-slate-100 md:hover:text-slate-900"
            }`}
          >
            <Icon className="text-lg md:text-base" />
            {label}
          </button>
        ))}
      </nav>

      <main className="min-h-0 flex-1 overflow-hidden">
        {/* Chat stays mounted so the conversation and an in-flight answer survive tab switches. */}
        <div className={tab === "chat" ? "h-full" : "hidden"}>
          <Chat me={me} />
        </div>
        {tab === "documents" && <Documents me={me} />}
        {tab === "admin" && me.role === "admin" && <Admin me={me} />}
        {tab === "help" && <Help />}
      </main>
    </div>
  );
}
