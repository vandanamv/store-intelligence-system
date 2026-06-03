#!/usr/bin/env python
"""
Quick test script to identify API endpoint errors without Docker.
"""
import sys
import json
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.database import init_db, SessionLocal
from app.models import StoreEvent, EventMetadata
from app.ingestion import ingest_events_batch
from app.metrics import get_store_metrics
from app.funnel import get_store_funnel
from app.heatmap import get_store_heatmap
from app.anomalies import get_store_anomalies
from app.health import get_system_health

def test_endpoints():
    print("[*] Initializing database...")
    init_db()
    db = SessionLocal()
    
    try:
        # Create sample events
        print("[*] Creating test events...")
        base_time = datetime.utcnow()
        
        events = [
            StoreEvent(
                event_id="test-entry-1",
                store_id="STORE_BLR_002",
                camera_id="CAM_ENTRY_01",
                visitor_id="VIS_001",
                event_type="ENTRY",
                timestamp=base_time,
                zone_id=None,
                dwell_ms=0,
                is_staff=False,
                confidence=0.95,
                metadata=EventMetadata(queue_depth=0, sku_zone="ENTRY", session_seq=1)
            ),
            StoreEvent(
                event_id="test-zone-1",
                store_id="STORE_BLR_002",
                camera_id="CAM_FLOOR_01",
                visitor_id="VIS_001",
                event_type="ZONE_ENTER",
                timestamp=base_time + timedelta(seconds=5),
                zone_id="SKINCARE",
                dwell_ms=0,
                is_staff=False,
                confidence=0.92,
                metadata=EventMetadata(queue_depth=0, sku_zone="SKINCARE", session_seq=2)
            ),
            StoreEvent(
                event_id="test-dwell-1",
                store_id="STORE_BLR_002",
                camera_id="CAM_FLOOR_01",
                visitor_id="VIS_001",
                event_type="ZONE_DWELL",
                timestamp=base_time + timedelta(seconds=35),
                zone_id="SKINCARE",
                dwell_ms=30000,
                is_staff=False,
                confidence=0.91,
                metadata=EventMetadata(queue_depth=0, sku_zone="SKINCARE", session_seq=3)
            ),
            StoreEvent(
                event_id="test-billing-1",
                store_id="STORE_BLR_002",
                camera_id="CAM_BILLING_01",
                visitor_id="VIS_001",
                event_type="BILLING_QUEUE_JOIN",
                timestamp=base_time + timedelta(seconds=45),
                zone_id="BILLING_COUNTER",
                dwell_ms=0,
                is_staff=False,
                confidence=0.94,
                metadata=EventMetadata(queue_depth=2, sku_zone="BILLING_COUNTER", session_seq=4)
            ),
            StoreEvent(
                event_id="test-exit-1",
                store_id="STORE_BLR_002",
                camera_id="CAM_ENTRY_01",
                visitor_id="VIS_001",
                event_type="EXIT",
                timestamp=base_time + timedelta(seconds=60),
                zone_id=None,
                dwell_ms=0,
                is_staff=False,
                confidence=0.96,
                metadata=EventMetadata(queue_depth=1, sku_zone=None, session_seq=5)
            )
        ]
        
        # Test 1: Ingest events
        print("[*] Test 1: Ingesting events...")
        try:
            result = ingest_events_batch(db, events)
            print(f"    ✓ Ingestion result: {result}")
        except Exception as e:
            print(f"    ✗ INGESTION ERROR: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
        
        # Test 2: Get metrics
        print("[*] Test 2: Fetching metrics...")
        try:
            metrics = get_store_metrics(db, "STORE_BLR_002")
            print(f"    ✓ Metrics: {metrics.model_dump()}")
        except Exception as e:
            print(f"    ✗ METRICS ERROR: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
        
        # Test 3: Get funnel
        print("[*] Test 3: Fetching funnel...")
        try:
            funnel = get_store_funnel(db, "STORE_BLR_002")
            print(f"    ✓ Funnel: {funnel.model_dump()}")
        except Exception as e:
            print(f"    ✗ FUNNEL ERROR: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
        
        # Test 4: Get heatmap
        print("[*] Test 4: Fetching heatmap...")
        try:
            heatmap = get_store_heatmap(db, "STORE_BLR_002")
            print(f"    ✓ Heatmap: {heatmap.model_dump()}")
        except Exception as e:
            print(f"    ✗ HEATMAP ERROR: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
        
        # Test 5: Get anomalies
        print("[*] Test 5: Fetching anomalies...")
        try:
            anomalies = get_store_anomalies(db, "STORE_BLR_002")
            print(f"    ✓ Anomalies: {anomalies.model_dump()}")
        except Exception as e:
            print(f"    ✗ ANOMALIES ERROR: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
        
        # Test 6: Get health
        print("[*] Test 6: Fetching health status...")
        try:
            health = get_system_health(db)
            print(f"    ✓ Health: {health.model_dump()}")
        except Exception as e:
            print(f"    ✗ HEALTH ERROR: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
        
        print("\n[✓] All endpoint tests passed!")
        return True
        
    finally:
        db.close()

if __name__ == "__main__":
    success = test_endpoints()
    sys.exit(0 if success else 1)
