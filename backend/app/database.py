"""
Database connection and session management.
"""
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.config import settings

# Create database engine with connection pooling
# Pool configuration for production readiness:
# - pool_size: Number of connections to maintain in the pool (default: 5)
# - max_overflow: Maximum connections above pool_size (default: 10)
# - pool_timeout: Seconds to wait before giving up on getting a connection (default: 30)
# - pool_recycle: Recycle connections after this many seconds (default: 3600)
# - pool_pre_ping: Validate connections before using them
if settings.DATABASE_URL.startswith("sqlite"):
    # SQLite (local development): allow use across FastAPI worker threads
    engine = create_engine(
        settings.DATABASE_URL,
        connect_args={"check_same_thread": False},
        echo=False
    )
else:
    engine = create_engine(
        settings.DATABASE_URL,
        pool_size=5,              # Number of connections to maintain
        max_overflow=10,          # Maximum connections above pool_size
        pool_timeout=30,           # Seconds to wait before timing out
        pool_recycle=3600,         # Recycle connections after 1 hour
        pool_pre_ping=True,        # Validate connections before using
        echo=False                 # Set to True for SQL query logging
    )

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()


def get_db():
    """
    Dependency function for FastAPI to get database session.
    Yields a database session and closes it after use.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()



def ensure_schema():
    """
    Create missing tables and add columns that create_all cannot add to existing tables.
    Keeps older local SQLite databases working without running Alembic.
    """
    from app import models  # noqa: F401  register all models on Base
    Base.metadata.create_all(bind=engine)
    columns = {c["name"] for c in inspect(engine).get_columns("chat_sessions")}
    if "channel" not in columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE chat_sessions ADD COLUMN channel VARCHAR"))
