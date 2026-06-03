from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

class EventMetadata(BaseModel):
    queue_depth: Optional[int] = None
    sku_zone: Optional[str] = None
    session_seq: Optional[int] = None

class StoreEvent(BaseModel):
    event_id: str = Field(..., description="UUID-v4 unique event identifier")
    store_id: str
    camera_id: str
    visitor_id: str
    event_type: str
    timestamp: datetime
    zone_id: Optional[str] = None
    dwell_ms: int = 0
    is_staff: bool = False
    confidence: float
    metadata: Optional[EventMetadata] = None

class IngestResponse(BaseModel):
    success: bool
    processed_count: int
    failed_count: int
    errors: List[Dict[str, Any]] = []

class StoreMetrics(BaseModel):
    store_id: str
    unique_visitors: int
    conversion_rate: float
    avg_dwell_by_zone: Dict[str, float]
    current_queue_depth: int
    abandonment_rate: float

class FunnelStage(BaseModel):
    stage_name: str
    count: int
    drop_off_percentage: float

class StoreFunnel(BaseModel):
    store_id: str
    funnel: List[FunnelStage]

class HeatmapItem(BaseModel):
    zone_id: str
    visit_frequency: float
    avg_dwell_ms: float

class StoreHeatmap(BaseModel):
    store_id: str
    heatmap: List[HeatmapItem]
    data_confidence: bool

class AnomalyItem(BaseModel):
    type: str
    severity: str  # INFO / WARN / CRITICAL
    description: str
    suggested_action: str
    timestamp: datetime

class StoreAnomalies(BaseModel):
    store_id: str
    anomalies: List[AnomalyItem]

class HealthStatus(BaseModel):
    status: str
    last_event_timestamps: Dict[str, Optional[datetime]]
    warnings: List[str]
