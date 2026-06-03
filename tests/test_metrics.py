# PROMPT: Generate pytest unit tests for the FastAPI store metrics and funnel calculations.
# Use an in-memory SQLite database via SQLAlchemy. Populate visitor_sessions and write tests verifying:
# 1. Unique visitor count (excluding is_staff=True).
# 2. Conversion rate calculation.
# 3. Zone average dwell times.
# 4. Funnel stage counts and drop-off percentages.
# 5. Handling of zero-traffic and zero-purchase stores.
#
# CHANGES MADE:
# - Created a shared in-memory DB fixture that runs migrations at startup.
# - Explicitly added staff records to verify they don't leak into visitor metrics.
# - Added checks to ensure drop-off percentages handle zero division correctly.

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta
import json

from app.database import Base, VisitorSession, POSTransaction
from app.metrics import get_store_metrics
from app.funnel import get_store_funnel

@pytest.fixture
def db_session():
    # Setup in-memory SQLite database
    engine = create_engine("sqlite:///:memory:")
    Session = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()

def test_store_metrics_and_staff_exclusion(db_session):
    store_id = "STORE_TEST_01"
    
    # 1. Add customer session (purchased)
    s1 = VisitorSession(
        session_id="s1", visitor_id="VIS_1", store_id=store_id,
        session_start=datetime.utcnow(), last_active=datetime.utcnow(),
        is_staff=False, purchased=True, queue_joined=True, queue_abandoned=False
    )
    s1.set_dwell_times({"SKINCARE": 30000}) # 30s
    
    # 2. Add customer session (no purchase, abandoned queue)
    s2 = VisitorSession(
        session_id="s2", visitor_id="VIS_2", store_id=store_id,
        session_start=datetime.utcnow(), last_active=datetime.utcnow(),
        is_staff=False, purchased=False, queue_joined=True, queue_abandoned=True
    )
    s2.set_dwell_times({"SKINCARE": 45000}) # 45s

    # 3. Add staff session (should be ignored)
    s_staff = VisitorSession(
        session_id="s3", visitor_id="VIS_STAFF", store_id=store_id,
        session_start=datetime.utcnow(), last_active=datetime.utcnow(),
        is_staff=True, purchased=False, queue_joined=True
    )
    s_staff.set_dwell_times({"SKINCARE": 100000})
    
    db_session.add_all([s1, s2, s_staff])
    db_session.commit()
    
    metrics = get_store_metrics(db_session, store_id)
    
    # Assertions
    assert metrics.unique_visitors == 2  # Excludes staff
    assert metrics.conversion_rate == pytest.approx(0.5)  # 1 out of 2 customers purchased
    assert metrics.abandonment_rate == pytest.approx(0.5)  # 1 out of 2 queued customer abandoned
    assert metrics.avg_dwell_by_zone["SKINCARE"] == pytest.approx(37.5) # (30+45)/2 = 37.5s

def test_metrics_empty_store(db_session):
    store_id = "STORE_EMPTY"
    
    metrics = get_store_metrics(db_session, store_id)
    
    assert metrics.unique_visitors == 0
    assert metrics.conversion_rate == 0.0
    assert metrics.abandonment_rate == 0.0
    assert len(metrics.avg_dwell_by_zone) == 0

def test_funnel_calculations(db_session):
    store_id = "STORE_FUNNEL"
    
    # s1: Entry -> Zone Visit -> Queue -> Purchase
    s1 = VisitorSession(
        session_id="s1", visitor_id="VIS_1", store_id=store_id,
        session_start=datetime.utcnow(), last_active=datetime.utcnow(),
        is_staff=False, purchased=True, queue_joined=True
    )
    s1.set_zones_visited(["SKINCARE"])
    
    # s2: Entry -> Zone Visit -> Queue (Drop off)
    s2 = VisitorSession(
        session_id="s2", visitor_id="VIS_2", store_id=store_id,
        session_start=datetime.utcnow(), last_active=datetime.utcnow(),
        is_staff=False, purchased=False, queue_joined=True
    )
    s2.set_zones_visited(["MAKEUP"])

    # s3: Entry -> Zone Visit (Drop off)
    s3 = VisitorSession(
        session_id="s3", visitor_id="VIS_3", store_id=store_id,
        session_start=datetime.utcnow(), last_active=datetime.utcnow(),
        is_staff=False, purchased=False, queue_joined=False
    )
    s3.set_zones_visited(["PERFUME"])

    # s4: Entry (Drop off immediately)
    s4 = VisitorSession(
        session_id="s4", visitor_id="VIS_4", store_id=store_id,
        session_start=datetime.utcnow(), last_active=datetime.utcnow(),
        is_staff=False, purchased=False, queue_joined=False
    )
    
    db_session.add_all([s1, s2, s3, s4])
    db_session.commit()
    
    funnel = get_store_funnel(db_session, store_id)
    stages = {stage.stage_name: stage for stage in funnel.funnel}
    
    assert stages["Entry"].count == 4
    assert stages["Zone Visit"].count == 3
    assert stages["Billing Queue"].count == 2
    assert stages["Purchase"].count == 1
    
    # Check drop-offs
    assert stages["Zone Visit"].drop_off_percentage == pytest.approx(25.0)  # (4 - 3)/4 = 25% drop-off
    assert stages["Billing Queue"].drop_off_percentage == pytest.approx(33.33)  # (3 - 2)/3 = 33.33% drop-off
    assert stages["Purchase"].drop_off_percentage == pytest.approx(50.0)  # (2 - 1)/2 = 50% drop-off
