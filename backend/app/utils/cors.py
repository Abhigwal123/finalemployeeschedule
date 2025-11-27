from __future__ import annotations

from flask import current_app, request


def get_request_origin() -> str | None:
    """Return the request Origin header if it is explicitly allowed."""
    try:
        origin = request.headers.get("Origin")
    except RuntimeError:
        origin = None

    allowed = current_app.config.get("CORS_ALLOWED_ORIGINS", []) or []
    if origin and origin in allowed:
        return origin
    return None


def apply_cors_headers(
    response,
    *,
    methods: str = "GET, POST, PUT, DELETE, OPTIONS",
    headers: str = "Content-Type, Authorization",
):
    """Apply standardized CORS headers using the env-driven allow list."""
    origin = get_request_origin()
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin

    response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Allow-Headers"] = headers
    response.headers["Access-Control-Allow-Methods"] = methods
    response.headers["Access-Control-Max-Age"] = "3600"
    return response

