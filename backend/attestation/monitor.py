"""Continuous isolation monitor.

Polls the interface snapshot. The first time the policy says NOT isolated, it
records a break event and latches the state to NOT-ISOLATED. The latch stays
until an admin acknowledges while the machine is isolated again, so every
answer generated after a break is flagged, even if the interface went back down.
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from attestation.traffic import TrafficMeter
from attestation.verify_chain import evaluate_isolation
from db.audit import audit
from db.models import KV

log = logging.getLogger("airgap.monitor")

STATE_KEY = "monitor_state"
ISOLATED = "ISOLATED"
NOT_ISOLATED = "NOT-ISOLATED"

Snapshotter = Callable[[], dict[str, Any]]


class IsolationMonitor:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        snapshotter: Snapshotter,
        policy: dict[str, Any],
        interval_s: float = 1.0,
        traffic: TrafficMeter | None = None,
    ) -> None:
        self._sf = session_factory
        self._snap = snapshotter
        self.policy = policy
        self.interval_s = interval_s
        self.traffic = traffic
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_check: str | None = None
        self.last_reasons: list[str] = []
        self.last_isolated: bool | None = None
        with self._sf() as s:
            row = s.get(KV, STATE_KEY)
            self._state = json.loads(row.value) if row else {"state": ISOLATED, "break": None}

    # ---- state ------------------------------------------------------------

    @property
    def state(self) -> str:
        with self._lock:
            return str(self._state["state"])

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "state": self._state["state"],
                "break": self._state.get("break"),
                "last_check": self.last_check,
                "current_reasons": list(self.last_reasons),
                # Live verdict of the latest check; "state" stays latched until an admin acknowledges.
                "isolated_now": self.last_isolated,
                "policy": self.policy,
                "interval_s": self.interval_s,
                "traffic": self.traffic.status() if self.traffic else None,
            }

    def _persist(self, s: Session) -> None:
        row = s.get(KV, STATE_KEY)
        value = json.dumps(self._state)
        if row is None:
            s.add(KV(key=STATE_KEY, value=value))
        else:
            row.value = value
        s.commit()

    # ---- checking ---------------------------------------------------------

    def check_once(self) -> tuple[dict[str, Any], bool, list[str]]:
        net = self._snap()
        isolated, reasons = evaluate_isolation(net, self.policy)
        if self.traffic is not None:
            self.traffic.update(net, isolated, list(self.policy.get("allow", [])))
        now = datetime.now(UTC).isoformat(timespec="milliseconds")
        with self._lock:
            self.last_check = now
            self.last_reasons = reasons
            self.last_isolated = isolated
            newly_broken = not isolated and self._state["state"] == ISOLATED
            if newly_broken:
                self._state = {"state": NOT_ISOLATED, "break": {"ts_utc": now, "reasons": reasons}}
        if newly_broken:
            with self._sf() as s:
                self._persist(s)
                audit(s, "system", "isolation.break", reasons=reasons, net=net)
            log.warning("isolation_break", extra={"reasons": reasons})
        return net, isolated, reasons

    def acknowledge(self, actor: str) -> dict[str, Any]:
        _, isolated, reasons = self.check_once()
        if not isolated:
            raise RuntimeError("cannot acknowledge: machine is still not isolated: " + "; ".join(reasons))
        with self._lock:
            previous = self._state.get("break")
            self._state = {"state": ISOLATED, "break": None}
        with self._sf() as s:
            self._persist(s)
            audit(s, actor, "isolation.acknowledge", previous_break=previous)
        return self.status()

    # ---- thread -----------------------------------------------------------

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.check_once()
            except Exception:
                log.exception("monitor_check_failed")
            self._stop.wait(self.interval_s)

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="isolation-monitor", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
