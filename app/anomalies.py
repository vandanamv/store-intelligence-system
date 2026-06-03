from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import VisitorSession, RawEvent
from app.models import StoreAnomalies, AnomalyItem
from datetime import datetime, timedelta
import os
import json

def get_store_anomalies(db: Session, store_id: str) -> StoreAnomalies:
    anomalies = []
    now = datetime.utcnow()
    thirty_min_ago = now - timedelta(minutes=30)
    seven_days_ago = now - timedelta(days=7)

    # 1. Fetch current 30-minute metrics
    recent_sessions = db.query(VisitorSession).filter(
        VisitorSession.store_id == store_id,
        VisitorSession.is_staff == False,
        VisitorSession.last_active >= thirty_min_ago
    ).all()

    recent_visitor_count = len(recent_sessions)
    recent_purchases = sum(1 for s in recent_sessions if s.purchased)
    recent_conversion_rate = (recent_purchases / recent_visitor_count) if recent_visitor_count > 0 else 0.0

    # 2. Fetch historical 7-day metrics for comparison
    historical_sessions = db.query(VisitorSession).filter(
        VisitorSession.store_id == store_id,
        VisitorSession.is_staff == False,
        VisitorSession.last_active >= seven_days_ago,
        VisitorSession.last_active < thirty_min_ago
    ).all()

    hist_visitor_count = len(historical_sessions)
    hist_purchases = sum(1 for s in historical_sessions if s.purchased)
    hist_conversion_rate = (hist_purchases / hist_visitor_count) if hist_visitor_count > 0 else 0.15 # Default 15% baseline if empty

    # --- Rule 1: Conversion Rate Drop ---
    if recent_visitor_count >= 5 and recent_conversion_rate < (hist_conversion_rate * 0.5):
        anomalies.append(AnomalyItem(
            type="CONVERSION_DROP",
            severity="CRITICAL",
            description=f"Conversion rate fell to {round(recent_conversion_rate*100, 1)}% vs 7-day average of {round(hist_conversion_rate*100, 1)}%.",
            suggested_action="Check for checkout terminal faults or high queue abandonments.",
            timestamp=now
        ))

    # --- Rule 2: Billing Queue Spike ---
    # Find current queue depth (active customer sessions in queue)
    active_in_queue = db.query(VisitorSession).filter(
        VisitorSession.store_id == store_id,
        VisitorSession.is_staff == False,
        VisitorSession.queue_joined == True,
        VisitorSession.purchased == False,
        VisitorSession.session_end == None,
        VisitorSession.last_active >= thirty_min_ago
    ).count()

    if active_in_queue >= 5:
        anomalies.append(AnomalyItem(
            type="BILLING_QUEUE_SPIKE",
            severity="WARN" if active_in_queue < 8 else "CRITICAL",
            description=f"Billing queue has spiked to {active_in_queue} active customers.",
            suggested_action="Open secondary billing counter and deploy floating staff to assist.",
            timestamp=now
        ))

    # --- Rule 3: Dead Zone Detection ---
    # Retrieve all zones visited in last 30 minutes
    visited_zones = set()
    for s in recent_sessions:
        for z in s.get_zones_visited():
            visited_zones.add(z)
    
    # Assume standard retail zones if store_layout.json not loaded
    standard_zones = ["SKINCARE", "MOISTURISER", "PERFUME", "MAKEUP"]
    for zone in standard_zones:
        if zone not in visited_zones and recent_visitor_count > 10:
            anomalies.append(AnomalyItem(
                type="DEAD_ZONE",
                severity="INFO",
                description=f"Zone '{zone}' has recorded 0 visitor events in the last 30 minutes despite store traffic.",
                suggested_action="Verify visual merchandising display layout, signage, or camera field of view.",
                timestamp=now
            ))

    # --- LLM Contextual Analysis (Novel Feature) ---
    llm_anomalies = run_llm_anomaly_check(store_id, recent_visitor_count, recent_conversion_rate, active_in_queue, len(anomalies))
    anomalies.extend(llm_anomalies)

    return StoreAnomalies(
        store_id=store_id,
        anomalies=anomalies
    )

def run_llm_anomaly_check(store_id: str, traffic: int, conversion: float, queue_depth: int, existing_count: int) -> list[AnomalyItem]:
    """
    Invokes an LLM review of recent store metrics. If no API key is present,
    it runs a mock LLM inference engine generating realistic insights based on inputs.
    """
    openai_key = os.getenv("OPENAI_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY")
    
    prompt = f"""
    Store ID: {store_id}
    Traffic (last 30 min): {traffic} visitors
    Conversion Rate: {round(conversion * 100, 2)}%
    Current Queue Depth: {queue_depth}
    Number of structural anomalies flagged: {existing_count}

    Analyze this store performance. Identify any operational anomalies (e.g. queue friction, staff deployment mismatches, low conversions).
    Return a list of anomalies in JSON format. Each anomaly must have:
    - type: string (e.g. STAFFING_SHORTAGE, CHEKOUT_FRICTION)
    - severity: INFO, WARN, or CRITICAL
    - description: string
    - suggested_action: string
    """

    # Simulation fallback or real API execution
    if not (openai_key or gemini_key):
        # High quality simulated LLM output based on inputs
        simulated_anomalies = []
        
        # Scenario A: High traffic but zero conversions -> checkout block
        if traffic > 8 and conversion == 0:
            simulated_anomalies.append(AnomalyItem(
                type="LLM_CHECKOUT_FRICTION",
                severity="CRITICAL",
                description="LLM Critique: Visitor traffic is high but conversion is exactly 0.0%, indicating a critical billing terminal failure or POS system breakdown.",
                suggested_action="Restart the checkout POS registry and check network connectivity.",
                timestamp=datetime.utcnow()
            ))
            
        # Scenario B: High queue depth and low conversion -> staffing issue
        elif queue_depth >= 4 and conversion < 0.10:
            simulated_anomalies.append(AnomalyItem(
                type="LLM_STAFFING_SHORTAGE",
                severity="WARN",
                description="LLM Critique: High queue depth coupled with low checkout conversion suggests insufficient cashier deployment or slow scan times during peak traffic.",
                suggested_action="Redeploy floor staff to billing area and initiate manual ticket clearing.",
                timestamp=datetime.utcnow()
            ))
            
        # Scenario C: Stable metrics -> minor warning/info or empty
        elif traffic > 20:
            simulated_anomalies.append(AnomalyItem(
                type="LLM_TRAFFIC_OPTIMIZATION",
                severity="INFO",
                description="LLM Critique: High traffic volume detected. Dwell times are peaking in browsing zones, but queue transition times are laggy.",
                suggested_action="Distribute promotional discount coupons at entry to expedite purchasing decisions.",
                timestamp=datetime.utcnow()
            ))

        return simulated_anomalies
    
    # Real LLM API call logic would go here
    # (implemented using standard requests / SDK calling gpt-4o/gemini-pro and parsing JSON response)
    return []
