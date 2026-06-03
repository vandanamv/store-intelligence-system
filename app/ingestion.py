import json
import uuid
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.database import RawEvent, VisitorSession, POSTransaction
from app.models import StoreEvent
from datetime import datetime, timedelta
import logging

logger = logging.getLogger("store_intelligence")

def ingest_events_batch(db: Session, events: list[StoreEvent]) -> dict:
    """
    Ingests a batch of events with deduplication and session state machine updates.
    Optimized for concurrent writes with transaction batching.
    """
    processed_count = 0
    failed_count = 0
    errors = []
    
    # First pass: deduplicate against existing events to reduce DB load
    existing_event_ids = set()
    if events:
        event_ids = [e.event_id for e in events]
        existing = db.query(RawEvent.event_id).filter(RawEvent.event_id.in_(event_ids)).all()
        existing_event_ids = set(e[0] for e in existing)

    for event in events:
        try:
            # 1. Idempotency Check (Deduplication)
            if event.event_id in existing_event_ids:
                # Event already processed, skip silently (Idempotent success)
                processed_count += 1
                continue

            # 2. Write raw event
            raw_ev = RawEvent(
                event_id=event.event_id,
                store_id=event.store_id,
                camera_id=event.camera_id,
                visitor_id=event.visitor_id,
                event_type=event.event_type,
                timestamp=event.timestamp,
                zone_id=event.zone_id,
                dwell_ms=event.dwell_ms,
                is_staff=event.is_staff,
                confidence=event.confidence,
                metadata_json=json.dumps(event.metadata.model_dump() if event.metadata else {})
            )
            db.add(raw_ev)

            # 3. Update Visitor Session State Machine
            update_session_state(db, event)
            
            # Flush periodically to reduce memory pressure with large batches
            if processed_count % 50 == 0:
                db.flush()
            
            processed_count += 1

        except Exception as e:
            logger.error(f"Event ingestion error for {event.event_id}: {str(e)}")
            failed_count += 1
            errors.append({"event_id": event.event_id, "error": str(e)})
            db.rollback()  # Rollback failed event, continue with next

    # Commit all processed events
    try:
        db.commit()
        logger.info(f"Batch commit successful: {processed_count} events processed")
    except Exception as e:
        logger.error(f"Batch commit failed: {str(e)}")
        db.rollback()
        return {
            "success": False,
            "processed_count": 0,
            "failed_count": failed_count + processed_count,
            "errors": errors + [{"batch": "commit failed", "error": str(e)}]
        }

    # Proactively check and correlate POS transactions after batch update
    try:
        correlate_pending_pos_transactions(db)
    except Exception as e:
        logger.warning(f"POS correlation failed (non-critical): {str(e)}")

    return {
        "success": failed_count == 0,
        "processed_count": processed_count,
        "failed_count": failed_count,
        "errors": errors
    }

def update_session_state(db: Session, event: StoreEvent):
    # Lookup active session for this visitor
    session = db.query(VisitorSession).filter(VisitorSession.visitor_id == event.visitor_id).first()

    if not session:
        # Create session if it doesn't exist (e.g. ENTRY event or out-of-order event)
        session = VisitorSession(
            session_id=str(uuid.uuid4()),
            visitor_id=event.visitor_id,
            store_id=event.store_id,
            session_start=event.timestamp,
            is_staff=event.is_staff,
            group_id=event.metadata.sku_zone if (event.metadata and event.metadata.sku_zone and event.metadata.sku_zone.startswith("GROUP_")) else None, # We can pass group_id here or derive it
            re_entry_count=0,
            zones_visited_json=json.dumps([]),
            dwell_times_json=json.dumps({}),
            queue_joined=False,
            queue_abandoned=False,
            purchased=False,
            last_active=event.timestamp
        )
        db.add(session)
        db.flush()  # Populate session fields

    # Apply State-Machine Transitions
    session.last_active = max(session.last_active, event.timestamp)
    
    # If is_staff becomes true at any point, flag the session as staff
    if event.is_staff:
        session.is_staff = True

    if event.event_type == "ENTRY":
        session.session_start = min(session.session_start, event.timestamp)
        # Clear exit if they re-enter on same visitor ID
        session.session_end = None

    elif event.event_type == "EXIT":
        session.session_end = event.timestamp

    elif event.event_type == "REENTRY":
        session.re_entry_count += 1
        session.session_end = None  # Re-activate session

    elif event.event_type == "ZONE_ENTER":
        zones = session.get_zones_visited()
        if event.zone_id and event.zone_id not in zones:
            zones.append(event.zone_id)
            session.set_zones_visited(zones)

    elif event.event_type == "ZONE_DWELL":
        # Record dwell times
        dwells = session.get_dwell_times()
        if event.zone_id:
            dwells[event.zone_id] = dwells.get(event.zone_id, 0) + event.dwell_ms
            session.set_dwell_times(dwells)
        
        # Also ensure zone is marked as visited
        zones = session.get_zones_visited()
        if event.zone_id and event.zone_id not in zones:
            zones.append(event.zone_id)
            session.set_zones_visited(zones)

    elif event.event_type == "BILLING_QUEUE_JOIN":
        session.queue_joined = True
        # Mark billing zone as visited
        zones = session.get_zones_visited()
        if event.zone_id and event.zone_id not in zones:
            zones.append(event.zone_id)
            session.set_zones_visited(zones)

    elif event.event_type == "BILLING_QUEUE_ABANDON":
        session.queue_abandoned = True

    # If the metadata contains a custom group_id, capture it
    if event.metadata and event.metadata.sku_zone and event.metadata.sku_zone.startswith("GROUP_"):
        session.group_id = event.metadata.sku_zone

def correlate_pending_pos_transactions(db: Session):
    """
    Correlates unlinked POS transactions with visitor sessions.
    Correlation rule: A visitor who was in the billing zone in the 5-minute window
    before a transaction timestamp counts as a converted visitor for that session.
    """
    # Get all POS transactions that are not yet correlated
    transactions = db.query(POSTransaction).filter(POSTransaction.correlated_session_id == None).all()

    for tx in transactions:
        tx_time = tx.timestamp
        window_start = tx_time - timedelta(minutes=5)

        # Look for a visitor session in the same store that:
        # - Is not staff
        # - Had billing queue join or spent time in the billing zone
        # - Was active in the billing zone during [tx_time - 5min, tx_time]
        # - Has not been matched to a purchase yet
        candidate = db.query(VisitorSession).filter(
            VisitorSession.store_id == tx.store_id,
            VisitorSession.is_staff == False,
            VisitorSession.purchased == False,
            VisitorSession.session_start <= tx_time,
            VisitorSession.last_active >= window_start
        ).first()

        if candidate:
            candidate.purchased = True
            candidate.transaction_id = tx.transaction_id
            tx.correlated_session_id = candidate.session_id
            db.add(candidate)
            db.add(tx)
            db.flush()
    
    # Commit all POS transaction correlations
    db.commit()
