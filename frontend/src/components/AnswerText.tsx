// Renders model output as React elements (never as HTML): paragraphs, bullet/numbered lists,
// **bold**, `code`, and [S1] citation markers as clickable chips.
import type { ReactNode } from "react";
import type { Citation } from "../api";

const MARKER = /\[(S\d+(?:\s*,\s*S\d+)*)\]|\*\*([^*]+)\*\*|`([^`]+)`/g;

function inline(text: string, cite: Map<string, Citation>, onCite: (c: Citation) => void, key: string): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  let n = 0;
  for (const m of text.matchAll(MARKER)) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const k = `${key}-${n++}`;
    if (m[1]) {
      const labels = m[1].split(",").map((s) => s.trim());
      const known = labels.filter((l) => cite.has(l));
      if (known.length === 0) out.push(m[0]);
      for (const l of known) {
        const c = cite.get(l)!;
        out.push(
          <button
            key={`${k}-${l}`}
            type="button"
            onClick={() => onCite(c)}
            title={`${c.filename}${c.page != null ? `, p. ${c.page}` : ""}`}
            aria-label={`Source ${l}`}
            className="mx-0.5 inline-flex -translate-y-px items-center rounded bg-brand-100 px-1.5 align-baseline text-[11px] font-semibold leading-4 text-brand-800 transition hover:bg-brand-200"
          >
            {l}
          </button>,
        );
      }
    } else if (m[2]) {
      out.push(<strong key={k}>{m[2]}</strong>);
    } else if (m[3]) {
      out.push(
        <code key={k} className="rounded bg-slate-100 px-1 font-mono text-[0.9em]">
          {m[3]}
        </code>,
      );
    }
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

const BULLET = /^\s*(?:[-*•]|\d+[.)])\s+/;

export default function AnswerText({
  text,
  citations = [],
  onCite = () => {},
}: {
  text: string;
  citations?: Citation[];
  onCite?: (c: Citation) => void;
}) {
  const cite = new Map(citations.map((c) => [c.label, c]));
  const blocks: ReactNode[] = [];
  // Group consecutive lines into runs of list items or plain text; blank lines end a run.
  const runs: { list: boolean; lines: string[] }[] = [];
  for (const line of text.split("\n")) {
    if (line.trim() === "") {
      runs.push({ list: false, lines: [] });
      continue;
    }
    const list = BULLET.test(line);
    const cur = runs[runs.length - 1];
    if (cur && cur.list === list && (list || cur.lines.length > 0)) cur.lines.push(line);
    else runs.push({ list, lines: [line] });
  }
  runs.forEach((run, ri) => {
    if (run.lines.length === 0) return;
    if (run.list) {
      const ordered = /^\s*\d/.test(run.lines[0]);
      const items = run.lines.map((l, li) => <li key={li}>{inline(l.replace(BULLET, ""), cite, onCite, `${ri}-${li}`)}</li>);
      blocks.push(
        ordered ? (
          <ol key={ri} className="ml-5 list-decimal space-y-1">
            {items}
          </ol>
        ) : (
          <ul key={ri} className="ml-5 list-disc space-y-1">
            {items}
          </ul>
        ),
      );
    } else {
      blocks.push(
        <p key={ri} className="whitespace-pre-wrap">
          {inline(run.lines.join("\n"), cite, onCite, String(ri))}
        </p>,
      );
    }
  });
  return <div className="space-y-3 leading-relaxed">{blocks}</div>;
}
