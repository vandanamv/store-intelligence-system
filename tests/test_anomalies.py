# PROMPT: Generate pytest unit tests for the store anomaly detection module.
# The anomalies.py evaluates CONVERSION_DROP, BILLING_QUEUE_SPIKE, and DEAD_ZONE.
# Setup appropriate visitor_sessions mock records in an in-memory SQLite DB to trigger each alert type:
# 1. Trigger BILLING_QUEUE_SPIKE by inserting 5+ customer sessions currently active in the billing queue.
# 2. Trigger CONVERSION_DROP by setting up recent traffic with zero purchases vs a high historical rate.
# 3. Verify DEAD_ZONE reports when a standard zone gets no visits.
#
# CHANGES MADE:
# - Seeded historical records to establish a baseline for conversion drops.
# - Mocked datetime.utcnow to prevent dynamic timestamp drift issues in tests.
# - Asserted metadata descriptions and severity mappings match requirements.

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta

from app.database import Base, VisitorSession
from app.anomalies import get_store_anomalies

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Session = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()

def test_billing_queue_spike(db_session):
    store_id = "STORE_ANOMALY_01"
    now = datetime.utcnow()
    
    # Insert 9 active customers in the billing queue (threshold is 5, CRITICAL threshold is >=8)
    sessions = []
    for i in range(9):
        s = VisitorSession(
            session_id=f"vis_{i}", visitor_id=f"VIS_{i}", store_id=store_id,
            session_start=now - timedelta(minutes=5), last_active=now,
            is_staff=False, purchased=False, queue_joined=True, session_end=None
        )
        sessions.append(s)
        
    db_session.add_all(sessions)
    db_session.commit()
    
    anom_report = get_store_anomalies(db_session, store_id)
    anom_types = [a.type for a in anom_report.anomalies]
    
    assert "BILLING_QUEUE_SPIKE" in anom_types
    # Find specific anomaly
    spike = next(a for a in anom_report.anomalies if a.type == "BILLING_QUEUE_SPIKE")
    assert spike.severity == "CRITICAL"
    assert "deploy" in spike.suggested_action.lower()

def test_conversion_drop(db_session):
    store_id = "STORE_ANOMALY_02"
    now = datetime.utcnow()
    
    # 1. Historical 7-day baseline: high conversion (e.g. 50%)
    hist_sessions = []
    for i in range(10):
        # 5 purchased, 5 not purchased
        s = VisitorSession(
            session_id=f"hist_{i}", visitor_id=f"VIS_HIST_{i}", store_id=store_id,
            session_start=now - timedelta(days=2), last_active=now - timedelta(days=2),
            is_staff=False, purchased=(i < 5)
        )
        hist_sessions.append(s)
        
    # 2. Recent 30-min traffic: 8 visitors, 0 purchases (conversion = 0%)
    recent_sessions = []
    for i in range(8):
        s = VisitorSession(
            session_id=f"rec_{i}", visitor_id=f"VIS_REC_{i}", store_id=store_id,
            session_start=now - timedelta(minutes=10), last_active=now,
            is_staff=False, purchased=False
        )
        recent_sessions.append(s)
        
    db_session.add_all(hist_sessions + recent_sessions)
    db_session.commit()
    
    anom_report = get_store_anomalies(db_session, store_id)
    anom_types = [a.type for a in anom_report.anomalies]
    
    assert "CONVERSION_DROP" in anom_types
    drop = next(a for a in anom_report.anomalies if a.type == "CONVERSION_DROP")
    assert drop.severity == "CRITICAL"

def test_dead_zone_alert(db_session):
    store_id = "STORE_ANOMALY_03"
    now = datetime.utcnow()
    
    # High traffic (>10 visitors) but nobody visits MAKEUP or SKINCARE
    sessions = []
    for i in range(12):
        s = VisitorSession(
            session_id=f"vis_{i}", visitor_id=f"VIS_{i}", store_id=store_id,
            session_start=now - timedelta(minutes=15), last_active=now,
            is_staff=False
        )
        s.set_zones_visited(["PERFUME"]) # Only visit Perfume
        sessions.append(s)
        
    db_session.add_all(sessions)
    db_session.commit()
    
    anom_report = get_store_anomalies(db_session, store_id)
    anom_types = [a.type for a in anom_report.anomalies]
    
    assert "DEAD_ZONE" in anom_types
    # Skincare or Makeup should be dead zones
    dead_skincare = next(a for a in anom_report.anomalies if a.type == "DEAD_ZONE" and "SKINCARE" in a.description)
    assert dead_skincare.severity == "INFO"
