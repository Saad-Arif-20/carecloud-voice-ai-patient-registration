import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import config
from .database import init_db
from .envelope import fail
from .logging_conf import setup_logging
from .routes.patients import router as patients_router
from .routes.vapi_webhook import router as vapi_router
from .seed import seed_if_empty

setup_logging()
logger = logging.getLogger("carecloud.main")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    seed_if_empty()
    logger.info("Startup complete. DB=%s", config.DATABASE_PATH)
    yield


app = FastAPI(title="CareCloud Voice AI Patient Registration", version="1.0.0", lifespan=lifespan)

app.include_router(patients_router)
app.include_router(vapi_router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/dashboard")
def dashboard():
    return FileResponse(STATIC_DIR / "dashboard.html")


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return fail(str(exc.detail), exc.status_code)


@app.exception_handler(ValidationError)
async def pydantic_exception_handler(request: Request, exc: ValidationError):
    return fail("Validation failed.", 422, details=exc.errors())


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return fail("Internal server error.", 500)
