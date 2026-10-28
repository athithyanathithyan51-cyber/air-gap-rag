// Finds the passage sentence that an answer sentence was drawn from.
//
// Pure text matching, no model call: the answer sentences that cite a source are compared
// word by word with each sentence of that source's passage, and the closest one wins.

export type Evidence = { start: number; end: number; score: number };

const CITATION = /\s*\[S\d+\]/g;
const MIN_SCORE = 0.5;
const MIN_WORD = 4;

const STOP = new Set(["that", "this", "with", "from", "have", "were", "they", "their", "which", "into", "than", "also", "such", "been"]);

function words(text: string): Set<string> {
  return new Set(
    (text.toLowerCase().match(/[a-z0-9]+/g) ?? []).filter((w) => w.length >= MIN_WORD && !STOP.has(w)),
  );
}

// Answer sentences that carry the given citation label, with the citation markers removed.
export function citedSentences(answer: string, label: string): string {
  const marker = `[${label}]`;
  // A sentence keeps the citation markers that follow its full stop: "...examination. [S1]".
  const sentences = answer.match(/[^.!?\n]+[.!?]?(?:\s*\[S\d+\])*/g) ?? [];
  return sentences
    .filter((s) => s.includes(marker))
    .map((s) => s.replace(CITATION, "").trim())
    .filter(Boolean)
    .join(" ");
}

// Best-matching sentence of the passage for the cited answer text, or null if nothing is close enough.
export function findEvidence(passage: string, cited: string): Evidence | null {
  const target = words(cited);
  if (target.size === 0) return null;

  let best: Evidence | null = null;
  const pattern = /[^.!?\n]+[.!?]?/g;
  for (const match of passage.matchAll(pattern)) {
    const sentence = match[0];
    const own = words(sentence);
    if (own.size === 0) continue;
    let shared = 0;
    for (const w of target) if (own.has(w)) shared += 1;
    const score = shared / target.size;
    if (score >= MIN_SCORE && (best === null || score > best.score)) {
      const lead = sentence.length - sentence.trimStart().length;
      const start = (match.index ?? 0) + lead;
      best = { start, end: (match.index ?? 0) + sentence.trimEnd().length, score };
    }
  }
  return best;
}
