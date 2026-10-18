import logging
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging

logger = logging.getLogger("app.request")


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(
        title="School Management System API",
        version="0.1.0",
        description="FastAPI backend for the School Management System.",
        docs_url="/docs",
        redoc_url=None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        request.state.request_id = request_id
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        if request.url.path != "/api/v1/health":
            logger.info(
                "request",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                },
            )
        return response

    register_exception_handlers(app)

    # Only photos and logos are public (login page shows the logo); random UUID filenames. Mounted per
    # folder and BEFORE the API routes: every other folder under the prefix (diary, homework, materials)
    # falls through to the authenticated, row-scoped GET in api/v1/content.py. Swap for signed bucket
    # URLs when storage moves to S3.
    upload_root = Path(settings.upload_dir)
    for folder in ("photos", "logos"):
        (upload_root / folder).mkdir(parents=True, exist_ok=True)
        app.mount(f"{settings.upload_url_prefix}/{folder}", StaticFiles(directory=upload_root / folder), name=folder)
    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
