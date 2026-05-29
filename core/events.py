from __future__ import annotations

from dataclasses import dataclass, field
from queue import Empty, Queue
from typing import Any, Dict, List, Optional

from core.helpers import now_str

# EVENTS
# ============================================================

@dataclass
class AgentEvent:
    event_type: str
    payload: Dict[str, Any]
    created_at: str = field(default_factory=now_str)


class TuiEventBus:
    def __init__(self) -> None:
        self.queue: Queue[AgentEvent] = Queue()

    def emit(self, event_type: str, payload: Optional[Dict[str, Any]] = None) -> None:
        self.queue.put(AgentEvent(event_type=event_type, payload=payload or {}))

    def drain(self, limit: int = 250) -> List[AgentEvent]:
        events: List[AgentEvent] = []
        for _ in range(limit):
            try:
                events.append(self.queue.get_nowait())
            except Empty:
                break
        return events


# ============================================================
