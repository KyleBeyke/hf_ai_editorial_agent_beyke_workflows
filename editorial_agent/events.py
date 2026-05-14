"""Hook-based event logging.

The event system is deliberately simple:

- each important lifecycle step emits an event;
- hooks can observe the event stream;
- events are written as JSON Lines;
- each event contains a previous hash and current hash.

The hash chain is not a security boundary, but it is a useful teaching pattern:
if a log line changes, the following hashes no longer match. This makes the raw
agent trace more auditable than casual print statements.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from .schemas import utc_now_iso


@dataclass
class AgentEvent:
    """One raw event emitted by the agent workflow."""

    event_id: str
    trace_id: str
    run_id: str
    type: str
    timestamp: str
    payload: dict[str, Any]
    prev_hash: str
    event_hash: str


Hook = Callable[[AgentEvent], None]


class EventBus:
    """Small hook bus for observing agent lifecycle events."""

    def __init__(self) -> None:
        self._hooks: list[Hook] = []

    def register(self, hook: Hook) -> None:
        """Register a hook that will receive every emitted event."""
        self._hooks.append(hook)

    def emit(self, event: AgentEvent) -> None:
        """Send one event to all registered hooks."""
        for hook in self._hooks:
            hook(event)


class JsonlEventLogger:
    """Append-only JSONL event logger with hash chaining."""

    def __init__(self, path: Path, trace_id: str | None = None, run_id: str | None = None) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.trace_id = trace_id or f"trace_{uuid4().hex[:12]}"
        self.run_id = run_id or f"run_{uuid4().hex[:12]}"
        self._prev_hash = "GENESIS"

    def emit(self, event_type: str, payload: dict[str, Any] | None = None) -> AgentEvent:
        """Create, hash, persist, and return an event."""
        payload = payload or {}
        base = {
            "event_id": f"evt_{uuid4().hex[:12]}",
            "trace_id": self.trace_id,
            "run_id": self.run_id,
            "type": event_type,
            "timestamp": utc_now_iso(),
            "payload": payload,
            "prev_hash": self._prev_hash,
        }
        event_hash = hashlib.sha256(
            json.dumps(base, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        event = AgentEvent(event_hash=event_hash, **base)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")
        self._prev_hash = event_hash
        return event


def console_event_hook(event: AgentEvent) -> None:
    """Human-friendly event printer used by --show-events."""
    compact_payload = json.dumps(event.payload, ensure_ascii=False)
    if len(compact_payload) > 300:
        compact_payload = compact_payload[:297] + "..."
    print(f"[{event.timestamp}] {event.type}: {compact_payload}")
