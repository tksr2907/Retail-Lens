"""
Structured logging using structlog.
Every request logs: trace_id, store_id, endpoint, latency_ms, event_count, status_code.
"""

import uuid
import time
import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.processors.JSONRenderer(),
    ]
)

logger = structlog.get_logger()


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        trace_id = str(uuid.uuid4())
        request.state.trace_id = trace_id
        start = time.perf_counter()

        # Extract store_id from path if present
        store_id = None
        path_parts = request.url.path.split("/")
        if "stores" in path_parts:
            idx = path_parts.index("stores")
            if idx + 1 < len(path_parts):
                store_id = path_parts[idx + 1]

        response: Response = await call_next(request)
        latency_ms = round((time.perf_counter() - start) * 1000, 2)

        logger.info(
            "request",
            trace_id=trace_id,
            method=request.method,
            endpoint=request.url.path,
            store_id=store_id,
            status_code=response.status_code,
            latency_ms=latency_ms,
        )
        response.headers["X-Trace-Id"] = trace_id
        return response
