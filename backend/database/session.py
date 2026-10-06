from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from backend.config import settings
from backend.database.base import Base

# Ensure the database directory exists before SQLite connects
settings.get_absolute_database_dir()

# Configure SQLite engine
# check_same_thread: False allows FastAPI request threads to interact with SQLite safely
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {},
    echo=False,
)

# Session factory for database operations
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Initialize database tables defined in models and run lightweight migrations."""
    # Import all models here to register them with Base.metadata
    from backend.models.invoice import Invoice, InvoiceLineItem, AuditLog  # noqa: F401

    Base.metadata.create_all(bind=engine)

    # Lightweight automatic schema migration for SQLite
    with engine.connect() as conn:
        try:
            result = conn.exec_driver_sql("PRAGMA table_info(invoices);")
            columns = [row[1] for row in result.fetchall()]
            if columns:
                new_cols = [
                    ("extraction_method", "VARCHAR(50)"),
                    ("vendor_address", "TEXT"),
                    ("vendor_gstin", "VARCHAR(50)"),
                    ("purchase_order_number", "VARCHAR(100)"),
                    ("payment_terms", "VARCHAR(255)"),
                    ("expense_category", "VARCHAR(100)"),
                    ("classification_method", "VARCHAR(50)"),
                    ("validation_status", "VARCHAR(50)"),
                    ("validation_errors", "TEXT"),
                    ("validation_warnings", "TEXT"),
                    ("duplicate_flag", "BOOLEAN DEFAULT 0"),
                    ("duplicate_invoice_id", "INTEGER"),
                    ("duplicate_reason", "VARCHAR(255)"),
                    ("anomaly_flag", "BOOLEAN DEFAULT 0"),
                    ("anomaly_reasons", "TEXT"),
                    ("risk_score", "INTEGER"),
                    ("risk_level", "VARCHAR(20)"),
                    ("risk_reasons", "TEXT"),
                    ("approval_recommendation", "VARCHAR(50)"),
                    ("approval_reason", "TEXT"),
                    ("automation_processed_at", "DATETIME"),
                ]
                for col_name, col_type in new_cols:
                    if col_name not in columns:
                        conn.exec_driver_sql(f"ALTER TABLE invoices ADD COLUMN {col_name} {col_type};")
                conn.commit()
        except Exception:
            pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session and closes it on completion."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
