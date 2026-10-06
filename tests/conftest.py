import os
import shutil
import tempfile
from pathlib import Path
from typing import Generator
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from backend.config import settings
from backend.database.base import Base
from backend.database.session import get_db
from backend.main import app

# Create in-memory SQLite engine for fast, isolated test runs
TEST_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="session", autouse=True)
def setup_test_directories():
    """Ensure temporary directory structure for tests and clean up on exit."""
    temp_dir = tempfile.mkdtemp(prefix="invoice_test_")
    temp_path = Path(temp_dir)
    original_upload_dir = settings.UPLOAD_DIR
    settings.UPLOAD_DIR = temp_path / "uploads"
    settings.get_absolute_upload_dir()

    yield

    settings.UPLOAD_DIR = original_upload_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture(scope="function")
def db_session() -> Generator[Session, None, None]:
    """Create a fresh database schema for every test function."""
    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="function")
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """Create a FastAPI TestClient with database session dependency override."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
