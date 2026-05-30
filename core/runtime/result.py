from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class EndpointResult:
    """Result returned by an endpoint or future dispatch call.

    EndpointResult is a data contract only. It does not invoke models, tools,
    shell commands, network calls, or Agent dispatch.
    """

    ok: bool
    output: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    diagnostics: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def success(cls, output: str | None = None, **data: Any) -> "EndpointResult":
        return cls(ok=True, output=output, data=dict(data))

    @classmethod
    def failure(
        cls,
        error: str,
        *,
        output: str | None = None,
        **data: Any,
    ) -> "EndpointResult":
        return cls(ok=False, output=output, error=error, data=dict(data))

    def add_diagnostic(
        self,
        *,
        stage: str,
        status: str,
        message: str | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        entry: dict[str, Any] = {"stage": stage, "status": status}
        if message is not None:
            entry["message"] = message
        entry.update(extra)
        self.diagnostics.append(entry)
        return entry
