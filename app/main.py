import time
import uuid
import logging
from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError
from typing import List

from app.database import init_db, get_db
from app.models import StoreEvent, IngestResponse, StoreMetrics, StoreFunnel, StoreHeatmap, StoreAnomalies, HealthStatus
from app.ingestion import ingest_events_batch
from app.metrics import get_store_metrics
from app.funnel import get_store_funnel
from app.heatmap import get_store_heatmap
from app.anomalies import get_store_anomalies
from app.health import get_system_health
from app.query_cache import clear_cache

# Initialize Logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("store_intelligence")

app = FastAPI(
    title="Apex Retail Store Intelligence API",
    description="Containerised intelligence API computing real-time store metrics, funnels, heatmaps, and anomalies.",
    version="1.0.0"
)

# Enable CORS for frontend dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Startup DB Initialization
@app.on_event("startup")
def on_startup():
    init_db()
    logger.info("Database initialised.")

# Structured Logging Middleware
@app.middleware("http")
async def structured_logging_middleware(request: Request, call_next):
    trace_id = str(uuid.uuid4())
    request.state.trace_id = trace_id
    
    start_time = time.time()
    
    # Check if ingest request to log event count
    event_count = 0
    if request.url.path == "/events/ingest" and request.method == "POST":
        try:
            body = await request.json()
            if isinstance(body, list):
                event_count = len(body)
            elif isinstance(body, dict):
                event_count = 1
        except Exception:
            pass

    response = await call_next(request)
    
    latency_ms = round((time.time() - start_time) * 1000.0, 2)
    store_id = request.path_params.get("id", "GLOBAL")
    
    # Log structured data
    logger.info(
        f"trace_id={trace_id} store_id={store_id} endpoint={request.url.path} "
        f"method={request.method} latency_ms={latency_ms} event_count={event_count} "
        f"status_code={response.status_code}"
    )
    
    response.headers["X-Trace-ID"] = trace_id
    return response

# Graceful Database Error Handler
@app.exception_handler(OperationalError)
async def db_operational_error_handler(request: Request, exc: OperationalError):
    trace_id = getattr(request.state, "trace_id", "N/A")
    logger.error(f"trace_id={trace_id} Database connection failed: {str(exc)}")
    return JSONResponse(
        status_code=503,
        content={
            "error": "Service Temporarily Unavailable",
            "message": "Database is currently busy or unreachable. Please try again.",
            "trace_id": trace_id
        }
    )

# WebSocket Connection Manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket client connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.info(f"WebSocket client disconnected. Total connections: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Failed to send WS message: {str(e)}")

ws_manager = ConnectionManager()

# WebSocket Endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep connection open and listen for heartbeat
            data = await websocket.receive_text()
            await websocket.send_json({"heartbeat": "ok", "timestamp": time.time()})
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}")
        ws_manager.disconnect(websocket)

# --- REST Endpoints ---

@app.post("/events/ingest", response_model=IngestResponse, status_code=201)
async def ingest_events(events: List[StoreEvent], db: Session = Depends(get_db)):
    result = ingest_events_batch(db, events)
    
    # Clear cache for affected stores after processing events
    if result["processed_count"] > 0:
        affected_stores = set(e.store_id for e in events)
        for store_id in affected_stores:
            clear_cache(store_id)
        
        # Broadcast events to connected WebSocket clients in real-time
        serialized_events = []
        for e in events:
            ev_dict = e.model_dump()
            # Serialize datetime fields for JSON transmission
            ev_dict["timestamp"] = ev_dict["timestamp"].isoformat()
            serialized_events.append(ev_dict)
        
        await ws_manager.broadcast({
            "type": "NEW_EVENTS",
            "events": serialized_events
        })
        
    if not result["success"] and result["failed_count"] > 0:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Some events failed to ingest",
                "errors": result["errors"],
                "processed_count": result["processed_count"],
                "failed_count": result["failed_count"]
            }
        )
        
    return IngestResponse(
        success=True,
        processed_count=result["processed_count"],
        failed_count=result["failed_count"],
        errors=[]
    )

@app.get("/stores/{id}/metrics", response_model=StoreMetrics)
def get_metrics(id: str, db: Session = Depends(get_db)):
    return get_store_metrics(db, id)

@app.get("/stores/{id}/funnel", response_model=StoreFunnel)
def get_funnel(id: str, db: Session = Depends(get_db)):
    return get_store_funnel(db, id)

@app.get("/stores/{id}/heatmap", response_model=StoreHeatmap)
def get_heatmap(id: str, db: Session = Depends(get_db)):
    return get_store_heatmap(db, id)

@app.get("/stores/{id}/anomalies", response_model=StoreAnomalies)
def get_anomalies(id: str, db: Session = Depends(get_db)):
    return get_store_anomalies(db, id)

@app.get("/health", response_model=HealthStatus)
def health_check(db: Session = Depends(get_db)):
    return get_system_health(db)
