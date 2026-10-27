"""Minimal Prometheus text-format metrics. No dependency: the bundle must stay small and offline-installable."""

from __future__ import annotations

import threading
from collections import defaultdict

# Upper bounds in seconds, the usual Prometheus default buckets trimmed for a local app.
BUCKETS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0)


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _labels(pairs: tuple[tuple[str, str], ...]) -> str:
    return "{" + ",".join(f'{k}="{_escape(v)}"' for k, v in pairs) + "}"


class Registry:
    """Thread-safe counters and one histogram family, keyed by label tuples."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._requests: dict[tuple[tuple[str, str], ...], int] = defaultdict(int)
        self._buckets: dict[tuple[tuple[str, str], ...], list[int]] = {}
        self._sum: dict[tuple[tuple[str, str], ...], float] = defaultdict(float)
        self._count: dict[tuple[tuple[str, str], ...], int] = defaultdict(int)

    def observe_request(self, method: str, route: str, status: int, seconds: float) -> None:
        key = (("method", method), ("route", route), ("status", str(status)))
        with self._lock:
            self._requests[key] += 1
            counts = self._buckets.setdefault(key, [0] * len(BUCKETS))
            for i, bound in enumerate(BUCKETS):
                if seconds <= bound:
                    counts[i] += 1
            self._sum[key] += seconds
            self._count[key] += 1

    def render(self) -> str:
        lines = [
            "# HELP airgap_http_requests_total HTTP requests by method, route template and status.",
            "# TYPE airgap_http_requests_total counter",
        ]
        with self._lock:
            for key in sorted(self._requests):
                lines.append(f"airgap_http_requests_total{_labels(key)} {self._requests[key]}")
            lines += [
                "# HELP airgap_http_request_duration_seconds Request latency by route template.",
                "# TYPE airgap_http_request_duration_seconds histogram",
            ]
            for key in sorted(self._buckets):
                for bound, n in zip(BUCKETS, self._buckets[key], strict=True):
                    lines.append(
                        f"airgap_http_request_duration_seconds_bucket{_labels(key + (('le', str(bound)),))} {n}"
                    )
                lines.append(
                    f"airgap_http_request_duration_seconds_bucket{_labels(key + (('le', '+Inf'),))} {self._count[key]}"
                )
                lines.append(f"airgap_http_request_duration_seconds_sum{_labels(key)} {self._sum[key]:.6f}")
                lines.append(f"airgap_http_request_duration_seconds_count{_labels(key)} {self._count[key]}")
        return "\n".join(lines) + "\n"
