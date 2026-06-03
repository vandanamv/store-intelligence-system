from sqlalchemy.orm import Session
from app.database import VisitorSession
from app.models import StoreHeatmap, HeatmapItem

def get_store_heatmap(db: Session, store_id: str) -> StoreHeatmap:
    # Fetch all non-staff sessions
    sessions = db.query(VisitorSession).filter(
        VisitorSession.store_id == store_id,
        VisitorSession.is_staff == False
    ).all()

    total_sessions = len(sessions)
    data_confidence = total_sessions >= 20

    # Count frequencies and total dwell times by zone
    zone_visit_counts = {}
    zone_dwell_sums = {}
    zone_visit_sessions = {}

    for s in sessions:
        dwell_times = s.get_dwell_times()
        for zone_id, dwell_ms in dwell_times.items():
            zone_visit_counts[zone_id] = zone_visit_counts.get(zone_id, 0) + 1
            zone_dwell_sums[zone_id] = zone_dwell_sums.get(zone_id, 0) + dwell_ms

    # Compute averages
    raw_heatmap = []
    max_freq = 0
    max_dwell = 0.0

    for zone_id, count in zone_visit_counts.items():
        total_dwell = zone_dwell_sums[zone_id]
        avg_dwell = (total_dwell / count) if count > 0 else 0.0
        
        raw_heatmap.append({
            "zone_id": zone_id,
            "frequency": count,
            "avg_dwell_ms": avg_dwell
        })
        
        if count > max_freq:
            max_freq = count
        if avg_dwell > max_dwell:
            max_dwell = avg_dwell

    # Normalize frequency and avg dwell time 0 to 100
    heatmap_items = []
    for item in raw_heatmap:
        norm_freq = (item["frequency"] / max_freq * 100.0) if max_freq > 0 else 0.0
        norm_dwell = (item["avg_dwell_ms"] / max_dwell * 100.0) if max_dwell > 0.0 else 0.0
        
        heatmap_items.append(HeatmapItem(
            zone_id=item["zone_id"],
            visit_frequency=round(norm_freq, 2),
            avg_dwell_ms=round(norm_dwell, 2)  # Return normalized avg dwell for grid rendering (0-100)
        ))

    return StoreHeatmap(
        store_id=store_id,
        heatmap=heatmap_items,
        data_confidence=data_confidence
    )
