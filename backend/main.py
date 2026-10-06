from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.routes import router as api_router
from backend.config import settings
from backend.database.session import init_db
from backend.utils.validators import ValidationError


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle event handler: initializes database and storage on startup."""
    # Ensure storage paths exist
    settings.get_absolute_upload_dir()
    settings.get_absolute_processed_dir()
    settings.get_absolute_database_dir()

    # Initialize SQLite tables
    init_db()

    yield


# FastAPI Application Instance
app = FastAPI(
    title=settings.APP_NAME,
    description="Production-style backend for automated document ingestion, OCR, and AI understanding.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Enable CORS for local Streamlit frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ValidationError)
async def validation_exception_handler(request: Request, exc: ValidationError):
    """Handle custom domain validation errors as 400 Bad Request."""
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": str(exc)},
    )


# Register API Routes under /api/v1
app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/", tags=["Root"])
def root_info():
    """Application root metadata."""
    return {
        "app_name": settings.APP_NAME,
        "environment": settings.APP_ENV,
        "api_docs": "/docs",
        "health_check": f"{settings.API_V1_PREFIX}/health",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host=settings.BACKEND_HOST,
        port=settings.BACKEND_PORT,
        reload=settings.DEBUG,
    )
