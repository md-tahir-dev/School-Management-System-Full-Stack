"""One consistent error shape for the whole API (Phase 2 format):

    {"detail": "...", "code": "VALIDATION_ERROR", "fields": {"father_cnic": "Invalid format"}, "request_id": "..."}

`fields` is present for validation problems, `details` carries extra machine-readable data
(retry_after_seconds, password problems, ...)."""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("app.errors")

_STATUS_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    413: "PAYLOAD_TOO_LARGE",
    422: "VALIDATION_ERROR",
    429: "TOO_MANY_REQUESTS",
}


class AppError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: Any = None,
        headers: dict[str, str] | None = None,
        fields: dict[str, str] | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.code = code.upper()
        self.message = message
        self.details = details
        self.headers = headers
        self.fields = fields


def unauthorized(message: str = "Authentication required.", code: str = "unauthorized") -> AppError:
    return AppError(401, code, message, headers={"WWW-Authenticate": "Bearer"})


def forbidden(message: str = "You don't have permission to do this.", code: str = "forbidden") -> AppError:
    return AppError(403, code, message)


def not_found(what: str = "Resource") -> AppError:
    return AppError(404, "not_found", f"{what} not found.")


def conflict(message: str, code: str = "conflict", details: Any = None) -> AppError:
    return AppError(409, code, message, details=details)


def invalid(message: str, fields: dict[str, str]) -> AppError:
    """Business-rule validation failure attributed to specific input fields."""
    return AppError(422, "validation_error", message, fields=fields)


def _body(
    request: Request, code: str, message: str, *, fields: dict[str, str] | None = None, details: Any = None
) -> dict:
    body: dict[str, Any] = {"detail": message, "code": code.upper()}
    if fields:
        body["fields"] = fields
    if details is not None:
        body["details"] = details
    rid = getattr(request.state, "request_id", None)
    if rid:
        body["request_id"] = rid
    return body


def error_response(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        _body(request, exc.code, exc.message, fields=exc.fields, details=exc.details),
        status_code=exc.status_code,
        headers=exc.headers,
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        return error_response(request, exc)

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: StarletteHTTPException):
        code = _STATUS_CODES.get(exc.status_code, f"HTTP_{exc.status_code}")
        message = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return JSONResponse(_body(request, code, message), status_code=exc.status_code, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        # Deliberately drop `input`/`ctx`: they can echo passwords back to the client.
        fields: dict[str, str] = {}
        for err in exc.errors():
            name = ".".join(str(p) for p in err["loc"] if p not in ("body", "query", "path")) or "body"
            message = str(err["msg"]).removeprefix("Value error, ")
            fields.setdefault(name, message)
        return JSONResponse(
            _body(request, "VALIDATION_ERROR", "Some fields are invalid.", fields=fields), status_code=422
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception):
        logger.exception("unhandled error", extra={"path": request.url.path, "method": request.method})
        return JSONResponse(
            _body(request, "INTERNAL_ERROR", "Something went wrong on our side. Please try again."),
            status_code=500,
        )
