from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RuntimeContext:
    """Shared packet passed through lane, adapter, and endpoint stages.

    RuntimeContext is a data contract. Creating or mutating one does not execute
    tools, endpoints, shell commands, network calls, or Agent dispatch.
    """

    raw_input: str
    lane: str
    args: list[str]
    prompt: str
    endpoint: str | None = None
    packets: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)

    def set_packet(self, name: str, value: Any) -> Any:
        """Store and return a packet value."""
        self.packets[name] = value
        return value

    def get_packet(self, name: str, default: Any = None) -> Any:
        """Read a packet value."""
        return self.packets.get(name, default)

    def set_metadata(self, name: str, value: Any) -> Any:
        """Store and return a metadata value."""
        self.metadata[name] = value
        return value

    def add_diagnostic(
        self,
        *,
        stage: str,
        status: str,
        message: str | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        """Append a diagnostic entry and return it."""
        entry: dict[str, Any] = {"stage": stage, "status": status}
        if message is not None:
            entry["message"] = message
        entry.update(extra)
        self.diagnostics.append(entry)
        return entry
