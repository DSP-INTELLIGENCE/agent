from __future__ import annotations

from core.runtime.context import RuntimeContext
from core.runtime.result import EndpointResult


def test_runtime_context_defaults_are_independent() -> None:
    one = RuntimeContext(raw_input="/prompt one", lane="prompt", args=["one"], prompt="one")
    two = RuntimeContext(raw_input="/ground two", lane="ground", args=["two"], prompt="two")

    one.set_packet("evidence", {"sources": []})
    one.set_metadata("llm_context", "context")
    one.add_diagnostic(stage="normalize", status="ok")

    assert two.packets == {}
    assert two.metadata == {}
    assert two.diagnostics == []


def test_runtime_context_packet_metadata_and_diagnostics_helpers() -> None:
    ctx = RuntimeContext(
        raw_input="/ground what is pie?",
        lane="ground",
        args=["what", "is", "pie?"],
        prompt="what is pie?",
        endpoint="default_llm",
    )

    packet = ctx.set_packet("evidence", {"claims": 1})
    metadata = ctx.set_metadata("llm_context", "rendered evidence")
    diagnostic = ctx.add_diagnostic(
        stage="ground",
        status="ok",
        message="evidence collected",
        sources=2,
    )

    assert packet == {"claims": 1}
    assert ctx.get_packet("evidence") == {"claims": 1}
    assert ctx.get_packet("missing", "fallback") == "fallback"
    assert metadata == "rendered evidence"
    assert diagnostic == {
        "stage": "ground",
        "status": "ok",
        "message": "evidence collected",
        "sources": 2,
    }


def test_endpoint_result_success_failure_and_diagnostics() -> None:
    ok = EndpointResult.success("hello", model="static")
    fail = EndpointResult.failure("boom", code="test")

    ok_diag = ok.add_diagnostic(stage="endpoint", status="ok")
    fail_diag = fail.add_diagnostic(stage="endpoint", status="error", message="boom")

    assert ok.ok is True
    assert ok.output == "hello"
    assert ok.data == {"model": "static"}
    assert ok.error is None
    assert ok_diag == {"stage": "endpoint", "status": "ok"}

    assert fail.ok is False
    assert fail.error == "boom"
    assert fail.data == {"code": "test"}
    assert fail_diag == {"stage": "endpoint", "status": "error", "message": "boom"}


def test_runtime_context_imports_from_package_root() -> None:
    from core.runtime import EndpointResult as ExportedEndpointResult
    from core.runtime import RuntimeContext as ExportedRuntimeContext

    assert ExportedRuntimeContext is RuntimeContext
    assert ExportedEndpointResult is EndpointResult
