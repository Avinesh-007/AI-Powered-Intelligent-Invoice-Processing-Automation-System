from pathlib import Path
from typing import Set
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables and .env file."""

    # Project metadata
    APP_NAME: str = "AI-Powered Intelligent Invoice Processing & Automation System"
    APP_ENV: str = "development"
    DEBUG: bool = True

    # Server settings
    BACKEND_HOST: str = "127.0.0.1"
    BACKEND_PORT: int = 8000
    API_V1_PREFIX: str = "/api/v1"

    # Base workspace directory (resolved relative to this file)
    BASE_DIR: Path = Path(__file__).resolve().parent.parent

    # Storage paths
    DATABASE_URL: str = "sqlite:///./data/database/invoices.db"
    UPLOAD_DIR: Path = Path("data/uploads")
    PROCESSED_DIR: Path = Path("data/processed")
    DATABASE_DIR: Path = Path("data/database")

    # Upload validation settings
    MAX_UPLOAD_SIZE_MB: int = 10
    ALLOWED_EXTENSIONS: Set[str] = {".pdf", ".png", ".jpg", ".jpeg"}

    # OCR Engine Settings
    TESSERACT_CMD: str | None = None

    # Threshold of extracted characters to distinguish text-based from scanned PDFs
    PDF_MIN_TEXT_CHARS: int = 40

    # External APIs (Keep empty by default; never hardcode credentials)
    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL: str = "gemini-2.5-flash"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def get_absolute_upload_dir(self) -> Path:
        """Return absolute path for upload directory and ensure it exists."""
        target = self.BASE_DIR / self.UPLOAD_DIR if not self.UPLOAD_DIR.is_absolute() else self.UPLOAD_DIR
        target.mkdir(parents=True, exist_ok=True)
        return target

    def get_absolute_database_dir(self) -> Path:
        """Return absolute path for database directory and ensure it exists."""
        target = self.BASE_DIR / self.DATABASE_DIR if not self.DATABASE_DIR.is_absolute() else self.DATABASE_DIR
        target.mkdir(parents=True, exist_ok=True)
        return target

    def get_absolute_processed_dir(self) -> Path:
        """Return absolute path for processed directory and ensure it exists."""
        target = self.BASE_DIR / self.PROCESSED_DIR if not self.PROCESSED_DIR.is_absolute() else self.PROCESSED_DIR
        target.mkdir(parents=True, exist_ok=True)
        return target


# Global settings instance
settings = Settings()
