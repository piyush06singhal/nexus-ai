"""Structured error handling.

Defines a typed exception hierarchy and the FastAPI handlers that render
them into a consistent JSON error envelope:

    {"error": {"code", "detail", "context"}}

Generic unhandled exceptions are logged and returned as a generic 500 with
no internal details leaked to the client.
"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.logging import get_logger

logger = get_logger(__name__)

DEFAULT_ERROR_CODE = "internal_error"


class NexusError(Exception):
    """Base class for all expected application errors."""

    status_code: int = 500
    code: str = DEFAULT_ERROR_CODE

    def __init__(
        self,
        detail: str,
        *,
        code: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        if code is not None:
            self.code = code
        self.context = context or {}


class NotFoundError(NexusError):
    status_code = 404
    code = "not_found"


class ConflictError(NexusError):
    status_code = 409
    code = "conflict"


class ValidationError(NexusError):
    status_code = 422
    code = "validation_error"


class ServiceUnavailableError(NexusError):
    status_code = 503
    code = "service_unavailable"


class PermissionDeniedError(NexusError):
    status_code = 403
    code = "permission_denied"


def _error_envelope(error: NexusError) -> dict[str, Any]:
    return {"error": {"code": error.code, "detail": error.detail, "context": error.context}}


def register_exception_handlers(app: FastAPI) -> None:
    """Attach exception handlers to the FastAPI application."""

    @app.exception_handler(NexusError)
    async def nexus_error_handler(_request: Request, exc: NexusError) -> JSONResponse:
        logger.warning("handled_error", extra={"error_code": exc.code, "detail": exc.detail})
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_envelope(exc),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = exc.errors()
        content = {
            "error": {
                "code": "request_validation_error",
                "detail": "Request validation failed.",
                "context": {"errors": errors},
            }
        }
        return JSONResponse(status_code=422, content=content)

    @app.exception_handler(Exception)
    async def unhandled_error_handler(_request: Request, exc: Exception) -> JSONResponse:
        # Log full traceback server-side; expose nothing sensitive to the client.
        logger.exception("unhandled_error", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content=_error_envelope(
                NexusError(
                    "An unexpected error occurred.",
                    code=DEFAULT_ERROR_CODE,
                )
            ),
        )
