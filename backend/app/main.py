import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.api.routes import router as api_router
from app.storage.object_storage import storage_client

app = FastAPI(title="Dairy Forecast API", version="0.1.0")
logger = logging.getLogger(__name__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    storage_client.ensure_buckets()


def _error_payload(error_code: str, message: str, details: dict | None = None) -> dict:
    return {"detail": {"error_code": error_code, "message": message, "details": details or None}}


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=_error_payload(
            "REQUEST_VALIDATION_ERROR",
            "Request validation failed",
            {"errors": exc.errors()},
        ),
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail
    if isinstance(detail, dict) and "error_code" in detail and "message" in detail:
        return JSONResponse(status_code=exc.status_code, content={"detail": detail})

    return JSONResponse(
        status_code=exc.status_code,
        content=_error_payload("HTTP_ERROR", str(detail) if detail else "HTTP error"),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content=_error_payload("INTERNAL_SERVER_ERROR", "Internal server error"),
    )


app.include_router(api_router, prefix="/api")
