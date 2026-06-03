from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import RawEvent
from app.models import HealthStatus
from datetime import datetime, timedelta

def get_system_health(db: Session) -> HealthStatus:
    warnings = []
    
    try:
        # Check database connectivity by querying distinct store IDs
        store_ids = db.query(RawEvent.store_id).distinct().all()
        store_ids = [s[0] for s in store_ids]
    except Exception as e:
        return HealthStatus(
            status="UNHEALTHY",
            last_event_timestamps={},
            warnings=[f"Database connection failed: {str(e)}"]
        )

    last_event_timestamps = {}
    now = datetime.utcnow()
    ten_minutes_ago = now - timedelta(minutes=10)

    for store_id in store_ids:
        # Get the timestamp of the latest event for this store
        latest_event = db.query(func.max(RawEvent.timestamp)).filter(
            RawEvent.store_id == store_id
        ).scalar()
        
        last_event_timestamps[store_id] = latest_event

        if latest_event:
            # If the event timestamp is older than 10 minutes, raise a STALE_FEED warning
            if latest_event < ten_minutes_ago:
                warnings.append(f"STALE_FEED: Store '{store_id}' has not emitted events since {latest_event.isoformat()} (lag > 10m).")
        else:
            warnings.append(f"STALE_FEED: Store '{store_id}' has no ingested events.")

    status = "HEALTHY" if not warnings else "DEGRADED"

    return HealthStatus(
        status=status,
        last_event_timestamps=last_event_timestamps,
        warnings=warnings
    )
