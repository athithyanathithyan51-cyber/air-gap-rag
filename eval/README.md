# eval/

- `gold_set.jsonl`: questions over the real BIT documents, including unanswerable ones (Phase 4).
- `run_eval.py`: measures hit-rate@k, citation accuracy, refusal precision/recall, latency p50/p95, RAM and CPU.
- `results/`: measured outputs only. Every file names the date, model, hardware and commit it came from.
