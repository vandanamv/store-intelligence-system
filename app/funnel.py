from sqlalchemy.orm import Session
from app.database import VisitorSession
from app.models import StoreFunnel, FunnelStage

def get_store_funnel(db: Session, store_id: str) -> StoreFunnel:
    # Fetch all non-staff visitor sessions for the store
    sessions = db.query(VisitorSession).filter(
        VisitorSession.store_id == store_id,
        VisitorSession.is_staff == False
    ).all()

    # Stage 1: Entry
    entry_count = len(sessions)

    # Stage 2: Zone Visit (visited at least one browsing zone outside entry/exit/billing)
    # Let's count sessions where they visited any zone.
    zone_visit_count = sum(1 for s in sessions if len(s.get_zones_visited()) > 0)

    # Stage 3: Billing Queue
    billing_queue_count = sum(1 for s in sessions if s.queue_joined)

    # Stage 4: Purchase
    purchase_count = sum(1 for s in sessions if s.purchased)

    # Calculate drop-off percentages relative to the previous stage
    # Drop-off rate is the percentage of visitors who failed to move to the next stage.
    drop_off_zone = 0.0
    if entry_count > 0:
        drop_off_zone = ((entry_count - zone_visit_count) / entry_count) * 100.0

    drop_off_queue = 0.0
    if zone_visit_count > 0:
        drop_off_queue = ((zone_visit_count - billing_queue_count) / zone_visit_count) * 100.0

    drop_off_purchase = 0.0
    if billing_queue_count > 0:
        drop_off_purchase = ((billing_queue_count - purchase_count) / billing_queue_count) * 100.0

    return StoreFunnel(
        store_id=store_id,
        funnel=[
            FunnelStage(stage_name="Entry", count=entry_count, drop_off_percentage=0.0),
            FunnelStage(stage_name="Zone Visit", count=zone_visit_count, drop_off_percentage=round(drop_off_zone, 2)),
            FunnelStage(stage_name="Billing Queue", count=billing_queue_count, drop_off_percentage=round(drop_off_queue, 2)),
            FunnelStage(stage_name="Purchase", count=purchase_count, drop_off_percentage=round(drop_off_purchase, 2))
        ]
    )
