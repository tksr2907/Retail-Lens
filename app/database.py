"""
Database setup using SQLAlchemy (SQLite).

SQLite chosen: zero-ops, sufficient for take-home scale.
Production upgrade: swap DATABASE_URL env var to PostgreSQL — no code changes.
Uses /tmp for SQLite file (mounted network filesystems don't support SQLite journals).
"""

import os
from sqlalchemy import (
    create_engine, Column, String, Integer, Float, Boolean, Index
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.exc import OperationalError

# Default DB path: use 'db/' folder inside the project (works on Windows + Linux)
# On Linux/Docker: override with DATABASE_URL=sqlite:////tmp/store_intelligence.db
_default_db = os.path.join(os.path.dirname(os.path.dirname(__file__)), "db", "store_intelligence.db")
os.makedirs(os.path.dirname(_default_db), exist_ok=True)
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{_default_db}")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class EventRecord(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String(36), nullable=False, unique=True, index=True)
    store_id = Column(String(64), nullable=False, index=True)
    camera_id = Column(String(64), nullable=False)
    visitor_id = Column(String(64), nullable=False, index=True)
    event_type = Column(String(32), nullable=False, index=True)
    timestamp = Column(String(32), nullable=False, index=True)
    zone_id = Column(String(64), nullable=True, index=True)
    dwell_ms = Column(Integer, default=0)
    is_staff = Column(Boolean, default=False)
    confidence = Column(Float, default=1.0)
    queue_depth = Column(Integer, nullable=True)
    sku_zone = Column(String(64), nullable=True)
    session_seq = Column(Integer, default=0)
    ingested_at = Column(String(32), nullable=False)

    __table_args__ = (
        Index("idx_store_type", "store_id", "event_type"),
        Index("idx_store_visitor", "store_id", "visitor_id"),
        Index("idx_store_ts", "store_id", "timestamp"),
    )


def create_tables():
    Base.metadata.create_all(bind=engine)


def get_db():
    """Dependency injector for FastAPI routes."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db_session() -> Session:
    return SessionLocal()
