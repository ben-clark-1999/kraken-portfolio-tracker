"""Global exception handler — logs traceback, returns sanitized JSON."""

import logging

from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


async def handle_uncaught_exception(request: Request, exc: Exception) -> JSONResponse:
    """Catch any uncaught exception, log traceback, return a sanitized 500.

    The response body never contains exception text. Operators correlate
    via the request_id which is stable across log line + response body +
    response header.
    """
    request_id = getattr(request.state, "request_id", "unknown")
    logger.exception(
        "[error] request_id=%s method=%s path=%s",
        request_id,
        request.method,
        request.url.path,
    )
    # X-Request-ID is set explicitly here, not just via RequestIDMiddleware:
    # BaseHTTPMiddleware.dispatch does NOT run after an uncaught exception,
    # so the middleware's response.headers assignment never fires on this path.
    # Without this explicit set the header would be missing on 500 responses.
    return JSONResponse(
        status_code=500,
        content={
            "error_code": "internal_error",
            "message": "Something went wrong. Please try again.",
            "request_id": request_id,
        },
        headers={"X-Request-ID": request_id},
    )
