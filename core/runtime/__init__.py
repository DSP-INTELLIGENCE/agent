"""Runtime contract primitives for Agent.

This package intentionally contains data contracts only at v1.
It does not alter dispatch, lane execution, endpoint invocation, or registry state.
"""

from .context import RuntimeContext
from .result import EndpointResult

__all__ = ["RuntimeContext", "EndpointResult"]
