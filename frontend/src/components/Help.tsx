import type { ReactNode } from "react";
import { BookIcon, LockIcon, ShieldIcon, SparkIcon } from "./icons";

function Card({ icon, title, tone, children }: { icon: ReactNode; title: string; tone: string; children: ReactNode }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className={`mb-2 flex h-9 w-9 items-center justify-center rounded-lg text-lg ${tone}`}>{icon}</div>
      <h3 className="font-semibold">{title}</h3>
      <p className="mt-1 text-sm text-slate-600">{children}</p>
    </div>
  );
}

export default function Help() {
  return (
    <div className="scroll-thin h-full overflow-y-auto p-4">
      <div className="mx-auto max-w-4xl space-y-6 py-2">
        <div>
          <h2 className="text-xl font-semibold tracking-tight">How answers work</h2>
          <p className="mt-1 text-sm text-slate-500">
            Everything runs on this machine: a local language model, a local search index, no internet.
          </p>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <Card icon={<BookIcon />} title="From your documents" tone="bg-emerald-50 text-emerald-700">
            When a passage in the documents is relevant, the answer is built from it and cites the document, page or section.
            Click a source to read the exact passage.
          </Card>
          <Card icon={<SparkIcon />} title="General knowledge" tone="bg-amber-50 text-amber-700">
            If nothing in the documents is relevant, the model answers from its own training and the answer is labelled
            &ldquo;General knowledge&rdquo;. Verify important facts.
          </Card>
          <Card icon={<LockIcon />} title="Honest refusals" tone="bg-slate-100 text-slate-700">
            If a draft answer is not supported by the passages it cites, it is withheld and you get &ldquo;I don&apos;t
            know&rdquo; instead of a guess.
          </Card>
          <Card icon={<ShieldIcon />} title="Injection protection" tone="bg-red-50 text-red-700">
            Document text is treated as data, never as instructions. Passages that try to instruct the assistant are dropped,
            and answers that ask for passwords or credentials are blocked.
          </Card>
        </div>

        <article className="space-y-4 rounded-xl border border-slate-200 bg-white p-6 text-sm leading-relaxed shadow-sm">
          <h2 className="text-lg font-semibold">Isolation records (&ldquo;Verify this answer&rdquo;)</h2>
          <p>
            Every answer, including &ldquo;I don&apos;t know&rdquo;, is written to a signed, hash-chained record together with a
            snapshot of the machine&apos;s network interfaces and default routes. This is a{" "}
            <strong>tamper-evident record of network-interface state at the moment of each answer</strong>.
          </p>
          <div className="rounded-lg bg-amber-50 p-4 text-amber-950">
            <h3 className="mb-2 font-semibold">Limits: please read</h3>
            <ul className="ml-5 list-disc space-y-1">
              <li>
                It is <strong>not proof that no packet was ever sent</strong>. Packet captures taken during operation are the
                separate evidence for &ldquo;no network traffic&rdquo;.
              </li>
              <li>
                It is <strong>tamper-evident, not tamper-proof</strong>: someone with administrator access to this machine and
                the signing key could create a new, consistent-looking chain.
              </li>
              <li>A snapshot shows the interface state at one moment; an interface could go up and down between checks.</li>
              <li>Changing the system clock changes timestamps. The monotonic counter and hash links still preserve order.</li>
              <li>On Windows or macOS with Docker Desktop, the record describes Docker&apos;s virtual machine, not the physical computer.</li>
            </ul>
          </div>
          <p>
            If the monitor detects a network interface coming up, every later answer is marked <em>NOT ISOLATED</em> until an
            admin acknowledges the event after the machine is isolated again.
          </p>
        </article>

        <article className="rounded-xl border border-slate-200 bg-white p-6 text-sm shadow-sm">
          <h2 className="mb-3 text-lg font-semibold">Tips</h2>
          <ul className="ml-5 list-disc space-y-1 text-slate-700">
            <li>Ask specific questions (&ldquo;What is the condonation fee per course?&rdquo;) for the best-cited answers.</li>
            <li>
              Press <kbd className="rounded border border-slate-300 bg-slate-50 px-1 font-mono text-xs">Enter</kbd> to send,{" "}
              <kbd className="rounded border border-slate-300 bg-slate-50 px-1 font-mono text-xs">Shift</kbd>+
              <kbd className="rounded border border-slate-300 bg-slate-50 px-1 font-mono text-xs">Enter</kbd> for a new line.
            </li>
            <li>Answers on a CPU-only machine can take 10–30 seconds; the progress line shows what the assistant is doing.</li>
            <li>Your conversation is kept while you switch tabs; &ldquo;New chat&rdquo; clears it.</li>
          </ul>
        </article>
      </div>
    </div>
  );
}
