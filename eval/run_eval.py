#!/usr/bin/env python3
"""Evaluate the running assistant against the gold set. Every number it writes is measured.

    python eval/run_eval.py --base http://127.0.0.1:8000 --user admin --password-file pw.txt \
        [--gold eval/gold_set.jsonl] [--label qwen7b]

Gold set lines (JSONL):
  {"id": "q01", "question": "...", "answerable": true,
   "expected_docs": ["CS-Lab-Manual.pdf"], "expected_pages": [12], "must_contain": ["75"]}
  {"id": "u01", "question": "...", "answerable": false}

Metrics:
  hit_rate_at_k        answerable questions whose retrieved top-k contains an expected doc (and page, if given)
  citation_accuracy    share of citations (on answered, answerable questions) that point to an expected doc/page
  keyword_match_rate   answered+answerable answers containing all `must_contain` strings (a proxy, not correctness)
  refusal precision/recall (positive class = "refused"; ground truth = answerable false)
  latency              time to first token and total, p50/p95 (seconds)
  host resources       peak/mean RAM used and CPU % sampled every 0.5 s during the run (whole host)
  threshold sweep      refusal metrics re-computed for higher min_score values from recorded retrieval scores
Hallucination rate needs human judgement: review.csv is written for manual marking.
"""

from __future__ import annotations

import argparse
import csv
import json
import platform
import statistics
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import psutil


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return round(s[lo] + (s[hi] - s[lo]) * (k - lo), 3)


class Sampler(threading.Thread):
    def __init__(self) -> None:
        super().__init__(daemon=True)
        self.stop_evt = threading.Event()
        self.ram: list[float] = []
        self.cpu: list[float] = []

    def run(self) -> None:
        psutil.cpu_percent(None)
        while not self.stop_evt.wait(0.5):
            self.cpu.append(psutil.cpu_percent(None))
            self.ram.append(psutil.virtual_memory().used / 2**30)


def matches(src: dict[str, Any], item: dict[str, Any]) -> bool:
    docs = [d.lower() for d in item.get("expected_docs", [])]
    if docs and src["filename"].lower() not in docs:
        return False
    pages = item.get("expected_pages") or []
    return not pages or src.get("page") in pages


def ask(client: httpx.Client, question: str) -> dict[str, Any]:
    """Ask once; on HTTP 429 (the server's chat rate limit) wait and retry. Latency is from the answered attempt."""
    for _ in range(24):
        r = _ask_once(client, question)
        if r.get("error") != "HTTP 429":
            return r
        time.sleep(5)
    return r


def _ask_once(client: httpx.Client, question: str) -> dict[str, Any]:
    start = time.perf_counter()
    first: float | None = None
    sources: list[dict[str, Any]] = []
    final: dict[str, Any] | None = None
    error: str | None = None
    with client.stream("POST", "/api/chat", json={"question": question}, timeout=600) as r:
        if r.status_code != 200:
            return {"error": f"HTTP {r.status_code}", "total_s": time.perf_counter() - start}
        for line in r.iter_lines():
            if not line.startswith("data: "):
                continue
            ev = json.loads(line[6:])
            if ev["type"] == "sources":
                sources = ev["sources"]
            elif ev["type"] == "token" and first is None:
                first = time.perf_counter() - start
            elif ev["type"] == "final":
                final = ev
            elif ev["type"] == "error":
                error = ev["message"]
    total = time.perf_counter() - start
    return {"sources": sources, "final": final, "error": error, "ttft_s": first, "total_s": total}


def from_documents(r: dict[str, Any]) -> bool:
    """Answered from the documents. A "general" answer (model's own knowledge) counts as not answered."""
    return r["status"] == "answered" and r.get("reason") != "general"


def refusal_metrics(rows: list[dict[str, Any]], threshold: float | None = None) -> dict[str, Any]:
    tp = fp = fn = tn = 0
    for r in rows:
        if r.get("error"):
            continue
        refused = not from_documents(r) or (threshold is not None and r["best_score"] < threshold)
        unanswerable = not r["answerable"]
        tp += refused and unanswerable
        fp += refused and not unanswerable
        fn += (not refused) and unanswerable
        tn += (not refused) and not unanswerable
    prec = tp / (tp + fp) if tp + fp else None
    rec = tp / (tp + fn) if tp + fn else None
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": prec, "recall": rec,
            "false_refusal_rate": fp / (fp + tn) if fp + tn else None}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--user", required=True)
    ap.add_argument("--password-file", required=True, type=Path)
    ap.add_argument("--gold", type=Path, default=Path(__file__).with_name("gold_set.jsonl"))
    ap.add_argument("--label", default="run")
    ap.add_argument("--out", type=Path, default=Path(__file__).with_name("results"))
    args = ap.parse_args()

    gold = [json.loads(line) for line in args.gold.read_text(encoding="utf-8").splitlines() if line.strip()]
    client = httpx.Client(base_url=args.base, trust_env=False, timeout=60)
    r = client.post("/api/auth/login", json={"username": args.user, "password": args.password_file.read_text().strip()})
    r.raise_for_status()
    client.headers["X-CSRF-Token"] = client.cookies["airgap_csrf"]
    ready = client.get("/ready").json()
    docs = client.get("/api/documents").json()

    sampler = Sampler()
    sampler.start()
    rows: list[dict[str, Any]] = []
    t0 = time.perf_counter()
    for n, item in enumerate(gold, 1):
        if n % 5 == 0:  # access token lasts 15 min; refresh keeps long runs alive
            client.post("/api/auth/refresh")
            client.headers["X-CSRF-Token"] = client.cookies["airgap_csrf"]
        res = ask(client, item["question"])
        final = res.get("final") or {}
        row = {
            "id": item["id"],
            "question": item["question"],
            "answerable": bool(item.get("answerable", True)),
            "error": res.get("error"),
            "status": final.get("status"),
            "reason": final.get("reason"),
            "answer": final.get("answer"),
            "best_score": final.get("best_score", 0.0),
            "support": final.get("support"),
            "retrieved": [{"filename": s["filename"], "page": s.get("page"), "score": s["score"]} for s in res.get("sources", [])],
            "citations": [{"filename": c["filename"], "page": c.get("page"), "section": c.get("section")} for c in final.get("citations", [])],
            "attestation_index": (final.get("attestation") or {}).get("index"),
            "isolated": (final.get("attestation") or {}).get("isolated"),
            "ttft_s": res.get("ttft_s"),
            "total_s": round(res["total_s"], 3),
        }
        row["hit"] = any(matches(s, item) for s in row["retrieved"]) if row["answerable"] else None
        if row["answerable"] and from_documents(row):
            row["citation_correct"] = [matches(c, item) for c in row["citations"]]
            must = [m.lower() for m in item.get("must_contain", [])]
            row["keyword_match"] = all(m in (row["answer"] or "").lower() for m in must) if must else None
        rows.append(row)
        print(f"[{n}/{len(gold)}] {item['id']}: {row['status'] or row['error']}:{row['reason']} ({row['total_s']:.1f}s)", flush=True)
    wall = time.perf_counter() - t0
    sampler.stop_evt.set()
    sampler.join()

    answerable = [r for r in rows if r["answerable"] and not r["error"]]
    hits = [r["hit"] for r in answerable]
    cites = [c for r in answerable if r.get("citation_correct") for c in r["citation_correct"]]
    kw = [r["keyword_match"] for r in answerable if r.get("keyword_match") is not None]
    totals = [r["total_s"] for r in rows if not r["error"]]
    ttft = [r["ttft_s"] for r in rows if r["ttft_s"] is not None]
    sweep = {f"{t:.2f}": refusal_metrics(rows, t) for t in [x / 100 for x in range(40, 86, 5)]}

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = args.out / f"{stamp}-{args.label}"
    out.mkdir(parents=True, exist_ok=True)
    summary = {
        "label": args.label,
        "timestamp_utc": stamp,
        "base": args.base,
        "host": {"platform": platform.platform(), "cpus": psutil.cpu_count(), "ram_gb": round(psutil.virtual_memory().total / 2**30, 1)},
        "ready": ready,
        "documents": [{"filename": d["filename"], "chunks": d["chunk_count"], "status": d["status"]} for d in docs],
        "questions": len(rows),
        "answerable": sum(r["answerable"] for r in rows),
        "unanswerable": sum(not r["answerable"] for r in rows),
        "errors": sum(bool(r["error"]) for r in rows),
        "hit_rate_at_k": round(sum(hits) / len(hits), 3) if hits else None,
        "citation_accuracy": round(sum(cites) / len(cites), 3) if cites else None,
        "keyword_match_rate": round(sum(kw) / len(kw), 3) if kw else None,
        "answered_rate_on_answerable": round(sum(from_documents(r) for r in answerable) / len(answerable), 3) if answerable else None,
        "general_answers": sum(r.get("reason") == "general" for r in rows),
        "refusal": refusal_metrics(rows),
        "threshold_sweep": sweep,
        "latency_total_s": {"p50": percentile(totals, 0.5), "p95": percentile(totals, 0.95), "mean": round(statistics.mean(totals), 3) if totals else None},
        "latency_first_token_s": {"p50": percentile(ttft, 0.5), "p95": percentile(ttft, 0.95)},
        "host_ram_used_gb": {"peak": round(max(sampler.ram), 2) if sampler.ram else None, "mean": round(statistics.mean(sampler.ram), 2) if sampler.ram else None},
        "host_cpu_percent": {"peak": max(sampler.cpu) if sampler.cpu else None, "mean": round(statistics.mean(sampler.cpu), 1) if sampler.cpu else None},
        "wall_clock_s": round(wall, 1),
        "all_blocks_isolated": all(r["isolated"] for r in rows if r["isolated"] is not None),
        "hallucination_rate": "not measured by this script: fill review.csv manually",
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    with (out / "per_question.jsonl").open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    with (out / "review.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "answerable", "status", "reason", "question", "answer", "citations", "hallucination (y/n)", "notes"])
        for r in rows:
            w.writerow([r["id"], r["answerable"], r["status"], r["reason"], r["question"], r["answer"],
                        "; ".join(f"{c['filename']} p{c['page']}" for c in r["citations"]), "", ""])
    print(json.dumps({k: summary[k] for k in ("hit_rate_at_k", "citation_accuracy", "refusal", "latency_total_s", "host_ram_used_gb")}, indent=2))
    print(f"results: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
