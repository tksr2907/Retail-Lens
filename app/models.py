"""
Pydantic models for the Store Intelligence API.
All event schema validation happens here.
"""

from __future__ import annotations
from typing import Optional, List, Literal, Any
from pydantic import BaseModel, Field, field_validator
import uuid
from datetime import datetime


EVENT_TYPES = Literal[
    "ENTRY", "EXIT", "ZONE_ENTER", "ZONE_EXIT",
    "ZONE_DWELL", "BILLING_QUEUE_JOIN", "BILLING_QUEUE_ABANDON", "REENTRY"
]


class EventMetadata(BaseModel):
    queue_depth: Optional[int] = None
    sku_zone: Optional[str] = None
    session_seq: int = 0


class StoreEvent(BaseModel):
    event_id: str = Field(..., description="UUID v4 — globally unique")
    store_id: str
    camera_id: str
    visitor_id: str
    event_type: EVENT_TYPES
    timestamp: str = Field(..., description="ISO-8601 UTC")
    zone_id: Optional[str] = None
    dwell_ms: int = Field(default=0, ge=0)
    is_staff: bool = False
    confidence: float = Field(..., ge=0.0, le=1.0)
    metadata: EventMetadata = Field(default_factory=EventMetadata)

    @field_validator("event_id")
    @classmethod
    def validate_uuid(cls, v: str) -> str:
        try:
            uuid.UUID(v)
        except ValueError:
            raise ValueError(f"event_id must be a valid UUID: {v}")
        return v

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, v: str) -> str:
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError(f"timestamp must be ISO-8601: {v}")
        return v


class IngestRequest(BaseModel):
    events: List[StoreEvent] = Field(..., max_length=500)


class IngestResponse(BaseModel):
    accepted: int
    rejected: int
    duplicate: int
    errors: List[dict] = []


# --- Metric response models ---

class ZoneDwell(BaseModel):
    zone_id: str
    avg_dwell_ms: float
    visit_count: int


class StoreMetrics(BaseModel):
    store_id: str
    as_of: str
    unique_visitors: int
    conversion_rate: float
    avg_dwell_ms: float
    queue_depth: int
    abandonment_rate: float
    zone_dwells: List[ZoneDwell]


class FunnelStage(BaseModel):
    stage: str
    count: int
    drop_off_pct: float


class FunnelResponse(BaseModel):
    store_id: str
    as_of: str
    stages: List[FunnelStage]
    total_sessions: int


class HeatmapZone(BaseModel):
    zone_id: str
    visit_frequency: int
    avg_dwell_ms: float
    score: float  # normalised 0-100
    data_confidence: bool  # False if < 20 sessions


class HeatmapResponse(BaseModel):
    store_id: str
    as_of: str
    zones: List[HeatmapZone]


class Anomaly(BaseModel):
    anomaly_id: str
    anomaly_type: str
    severity: Literal["INFO", "WARN", "CRITICAL"]
    description: str
    suggested_action: str
    detected_at: str
    store_id: str
    zone_id: Optional[str] = None
    value: Optional[float] = None
    threshold: Optional[float] = None


class AnomalyResponse(BaseModel):
    store_id: str
    as_of: str
    anomalies: List[Anomaly]


class StoreHealth(BaseModel):
    store_id: str
    status: Literal["OK", "STALE_FEED", "NO_DATA"]
    last_event_at: Optional[str]
    lag_minutes: Optional[float]


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    as_of: str
    stores: List[StoreHealth]
