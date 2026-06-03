from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import VisitorSession, RawEvent
from app.models import StoreMetrics
import json
from datetime import datetime, timedelta

def get_store_metrics(db: Session, store_id: str) -> StoreMetrics:
    # 1. Fetch all customer sessions (is_staff = False) for the store
    sessions = db.query(VisitorSession).filter(
        VisitorSession.store_id == store_id,
        VisitorSession.is_staff == False
    ).all()

    total_visitors = len(sessions)

    # 2. Conversion Rate: Purchased sessions / Total sessions
    purchased_count = sum(1 for s in sessions if s.purchased)
    conversion_rate = (purchased_count / total_visitors) if total_visitors > 0 else 0.0

    # 3. Average Dwell Time by Zone
    # Accumulate dwell times across all customer sessions
    zone_dwells = {}
    zone_counts = {}
    
    for s in sessions:
        dwell_times = s.get_dwell_times()
        for zone_id, dwell_ms in dwell_times.items():
            zone_dwells[zone_id] = zone_dwells.get(zone_id, 0) + dwell_ms
            zone_counts[zone_id] = zone_counts.get(zone_id, 0) + 1

    avg_dwell_by_zone = {}
    for zone_id, total_dwell in zone_dwells.items():
        count = zone_counts[zone_id]
        # Convert ms to seconds
        avg_dwell_by_zone[zone_id] = round((total_dwell / count) / 1000.0, 2) if count > 0 else 0.0

    # 4. Current Queue Depth
    # Defined as visitors who entered the billing zone in the last 10 minutes and have not exited
    # or finished transaction, and whose session is still active (session_end is null)
    # We can check raw events or active sessions. Let's look at active sessions where
    # queue_joined = True, purchased = False, session_end is None, and last_active > (now - 10 min)
    now = datetime.utcnow()
    ten_min_ago = now - timedelta(minutes=10)
    
    active_in_queue = db.query(VisitorSession).filter(
        VisitorSession.store_id == store_id,
        VisitorSession.is_staff == False,
        VisitorSession.queue_joined == True,
        VisitorSession.purchased == False,
        VisitorSession.session_end == None,
        VisitorSession.last_active >= ten_min_ago
    ).all()

    current_queue_depth = len(active_in_queue)

    # 5. Abandonment Rate: queue_abandoned / queue_joined
    joined_queue_count = sum(1 for s in sessions if s.queue_joined)
    abandoned_queue_count = sum(1 for s in sessions if s.queue_abandoned)
    
    abandonment_rate = (abandoned_queue_count / joined_queue_count) if joined_queue_count > 0 else 0.0

    return StoreMetrics(
        store_id=store_id,
        unique_visitors=total_visitors,
        conversion_rate=round(conversion_rate, 4),
        avg_dwell_by_zone=avg_dwell_by_zone,
        current_queue_depth=current_queue_depth,
        abandonment_rate=round(abandonment_rate, 4)
    )
