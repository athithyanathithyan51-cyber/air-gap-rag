// Fails the build if the built frontend references any remote origin.
//
// HTML/CSS: any src/href/url()/@import pointing at http(s):// or protocol-relative //.
// JS: any absolute http(s) URL passed to fetch/EventSource/WebSocket/import/XMLHttpRequest,
// plus every other absolute URL literal unless it is a known inert string
// (React's error-decoder link and XML namespace URIs never trigger a request).
// The Content-Security-Policy (connect-src 'self') is the runtime backstop.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { extname, join, relative } from "node:path";

const root = process.argv[2] ?? "dist";
const INERT = [
  /^https:\/\/react\.dev\/errors\//,
  /^http:\/\/www\.w3\.org\//,
  /^https:\/\/reactjs\.org\/docs\/error-decoder/,
];

function walk(dir) {
  return readdirSync(dir).flatMap((name) => {
    const p = join(dir, name);
    return statSync(p).isDirectory() ? walk(p) : [p];
  });
}

const problems = [];
const inertSeen = new Set();

for (const file of walk(root)) {
  const ext = extname(file);
  const text = readFileSync(file, "utf8");
  const rel = relative(root, file);
  if (ext === ".html" || ext === ".css") {
    const re = /(?:src|href)\s*=\s*["'](?:https?:)?\/\/[^"']+|url\(\s*["']?(?:https?:)?\/\/[^)"']+|@import\s+["'](?:https?:)?\/\//gi;
    for (const m of text.matchAll(re)) problems.push(`${rel}: ${m[0]}`);
  }
  if (ext === ".js" || ext === ".mjs") {
    const call = /(?:fetch|EventSource|WebSocket|import|open)\s*\(\s*[`"'](?:https?:|wss?:)?\/\/[^`"']+/g;
    for (const m of text.matchAll(call)) problems.push(`${rel}: network call ${m[0]}`);
    for (const m of text.matchAll(/["'`](https?:\/\/[^"'`\s]+)/g)) {
      const url = m[1];
      if (INERT.some((r) => r.test(url))) inertSeen.add(url.replace(/\?.*$/, ""));
      else problems.push(`${rel}: absolute URL literal ${url}`);
    }
  }
}

if (inertSeen.size) console.log(`inert URL strings (never fetched): ${[...inertSeen].join(", ")}`);
if (problems.length) {
  console.error("External references found in built frontend:\n" + problems.map((p) => "  " + p).join("\n"));
  process.exit(1);
}
console.log(`check-no-external: OK (${walk(root).length} files scanned, 0 external references)`);
