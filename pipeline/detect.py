import time
import argparse
import uuid
import random
from datetime import datetime, timedelta
import numpy as np

from pipeline.tracker import ReEntryTracker
from pipeline.emit import EventEmitter

class VLMStaffClassifier:
    """Simulates VLM crop evaluation logic based on uniform guidelines"""
    def __init__(self, use_mock: bool = True):
        self.use_mock = use_mock

    def evaluate_person_uniform(self, frame_crop: np.ndarray, visitor_id: str) -> dict:
        # Prompt and logic documented in CHOICES.md
        # If running in mock mode, randomly classify with realistic distribution
        # Seeded by visitor_id to guarantee consistency for the same visitor
        seed = sum(ord(c) for c in visitor_id)
        rng = random.Random(seed)
        
        # 10% chance of being staff
        is_staff = rng.random() < 0.10
        confidence = rng.uniform(0.92, 0.99) if is_staff else rng.uniform(0.85, 0.95)
        
        reasoning = (
            "Royal blue polo shirt detected with yellow emblem on left chest." 
            if is_staff else "Casual civilian attire. No official uniform markers found."
        )

        return {
            "is_staff": is_staff,
            "confidence": round(confidence, 2),
            "reasoning": reasoning
        }

class GroupDetector:
    """Identifies spatial-temporal proximity of entrants to flag group arrivals"""
    def __init__(self, max_delta_t_sec: float = 1.5):
        self.max_delta_t_sec = max_delta_t_sec
        self.recent_entrants = [] # list of tuples: (timestamp, visitor_id)

    def process_entry(self, visitor_id: str) -> str:
        now = time.time()
        self.recent_entrants = [e for e in self.recent_entrants if now - e[0] <= self.max_delta_t_sec]
        
        if self.recent_entrants:
            # Match existing group identifier from recent entrant
            group_id = self.recent_entrants[0][2]
        else:
            group_id = f"GROUP_{uuid.uuid4().hex[:6]}"
            
        self.recent_entrants.append((now, visitor_id, group_id))
        return group_id

def run_simulation(emitter: EventEmitter, store_id: str, duration_sec: int = 120):
    print(f"[*] Starting Detection Pipeline Simulation for store: {store_id}...")
    print(f"[*] Streaming events to API at {emitter.api_url}...")
    
    tracker = ReEntryTracker()
    vlm_classifier = VLMStaffClassifier()
    group_detector = GroupDetector()
    
    start_time = datetime.utcnow()
    simulation_end = time.time() + duration_sec
    
    # Store layout zones
    zones = ["SKINCARE", "MOISTURISER", "PERFUME", "MAKEUP"]
    billing_zone = "BILLING_COUNTER"
    
    # Track sequence of events per visitor: visitor_id -> current_seq
    session_sequences = {}
    # Track active visitor zones: visitor_id -> (zone_id, enter_time)
    visitor_active_zones = {}
    # Track visitor details: visitor_id -> {is_staff, group_id, last_event_time}
    visitor_registry = {}
    
    # Active visitors inside store (list of IDs)
    active_visitors = []
    
    # Store metrics for simulated queues
    queue_depth = 0
    
    # Simulation loop
    loop_count = 0
    while time.time() < simulation_end:
        loop_count += 1
        now_dt = start_time + timedelta(seconds=loop_count)
        timestamp_str = now_dt.isoformat() + "Z"
        
        # 1. Periodically simulate empty store periods (Edge Case 5)
        # Every 90 seconds, clear store and pause for 15 seconds
        cycle_time = loop_count % 120
        if 70 <= cycle_time <= 90:
            if active_visitors:
                print("[Empty Store Cycle] Discharging remaining visitors...")
                # Exit all remaining visitors
                for vis_id in list(active_visitors):
                    event = create_event(
                        store_id, "CAM_ENTRY_01", vis_id, "EXIT", timestamp_str,
                        None, 0, visitor_registry[vis_id]["is_staff"], 0.95,
                        session_sequences[vis_id], queue_depth, visitor_registry[vis_id]["group_id"]
                    )
                    emitter.emit_batch([event])
                    active_visitors.remove(vis_id)
            print("[Empty Store Cycle] Store is empty. Waiting...")
            time.sleep(1)
            continue
            
        events_batch = []
        
        # 2. Simulate Group Entries (Edge Case 1)
        # 8% chance to spawn a group entry of 2-3 people
        if random.random() < 0.08 and len(active_visitors) < 15:
            group_size = random.randint(2, 3)
            print(f"[Group Entry] Spawning group of {group_size} customers...")
            group_id = None
            
            for _ in range(group_size):
                # Simulated OSNet appearance embedding
                mock_emb = tracker.simulate_mock_embedding()
                vis_id, is_re = tracker.update_and_match(mock_emb)
                
                # VLM uniform check
                vlm_res = vlm_classifier.evaluate_person_uniform(None, vis_id)
                
                # Determine group ID
                if not group_id:
                    group_id = group_detector.process_entry(vis_id)
                else:
                    group_detector.recent_entrants.append((time.time(), vis_id, group_id))
                
                visitor_registry[vis_id] = {
                    "is_staff": vlm_res["is_staff"],
                    "group_id": group_id,
                    "re_entry_count": 0
                }
                session_sequences[vis_id] = 1
                active_visitors.append(vis_id)
                
                # Create ENTRY event
                ev = create_event(
                    store_id, "CAM_ENTRY_01", vis_id, "ENTRY", timestamp_str,
                    None, 0, vlm_res["is_staff"], vlm_res["confidence"],
                    1, queue_depth, group_id
                )
                events_batch.append(ev)
                
            emitter.emit_batch(events_batch)
            time.sleep(1)
            continue

        # 3. Simulate Single Entry / Re-entry (Edge Case 3)
        # 12% chance to spawn an entry
        if random.random() < 0.12 and len(active_visitors) < 20:
            # We simulate a customer who might have been seen before (re-entry)
            is_reentry_scenario = random.random() < 0.25 and len(tracker.gallery) > 0
            
            if is_reentry_scenario:
                # Reuse an embedding from the tracker gallery (simulating returning physical person)
                prev_vis_id = random.choice(list(tracker.gallery.keys()))
                mock_emb = tracker.simulate_mock_embedding(prev_vis_id)
            else:
                mock_emb = tracker.simulate_mock_embedding()
                
            vis_id, is_reentry = tracker.update_and_match(mock_emb)
            
            # VLM uniform check
            vlm_res = vlm_classifier.evaluate_person_uniform(None, vis_id)
            
            # Staff Movement (Edge Case 2)
            # If staff, print log
            if vlm_res["is_staff"]:
                print(f"[Staff Movement] Uniform detected for {vis_id} (VLM Confidence: {vlm_res['confidence']})")
            
            # Add to registry
            if vis_id not in visitor_registry:
                visitor_registry[vis_id] = {
                    "is_staff": vlm_res["is_staff"],
                    "group_id": None,
                    "re_entry_count": 0
                }
                session_sequences[vis_id] = 1
            else:
                session_sequences[vis_id] += 1
                
            if is_reentry:
                print(f"[Re-entry matched] Visitor {vis_id} returned to the store (OSNet similarity > 0.85)")
                visitor_registry[vis_id]["re_entry_count"] += 1
                
            active_visitors.append(vis_id)
            
            event_type = "REENTRY" if is_reentry else "ENTRY"
            ev = create_event(
                store_id, "CAM_ENTRY_01", vis_id, event_type, timestamp_str,
                None, 0, visitor_registry[vis_id]["is_staff"], vlm_res["confidence"],
                session_sequences[vis_id], queue_depth, visitor_registry[vis_id]["group_id"]
            )
            emitter.emit_batch([ev])
            time.sleep(1)
            continue

        # 4. Simulate active customer steps (Zone moves, dwell, checkout, queue joins)
        if active_visitors:
            vis_id = random.choice(active_visitors)
            seq = session_sequences[vis_id]
            is_staff = visitor_registry[vis_id]["is_staff"]
            group_id = visitor_registry[vis_id]["group_id"]
            
            # Decide what this visitor does
            action = random.choice(["ZONE_MOVE", "DWELL", "LEAVE"])
            
            # Staff do not checkout at POS, they just walk around and leave
            if is_staff and action == "LEAVE":
                print(f"[Staff exit] Staff member {vis_id} left store.")
                session_sequences[vis_id] += 1
                ev = create_event(
                    store_id, "CAM_ENTRY_01", vis_id, "EXIT", timestamp_str,
                    None, 0, True, 0.95, session_sequences[vis_id], queue_depth, group_id
                )
                emitter.emit_batch([ev])
                active_visitors.remove(vis_id)
                time.sleep(0.5)
                continue

            if action == "ZONE_MOVE":
                current_zone = visitor_active_zones.get(vis_id)
                if current_zone:
                    # Emit EXIT from current zone
                    session_sequences[vis_id] += 1
                    exit_ev = create_event(
                        store_id, "CAM_FLOOR_01", vis_id, "ZONE_EXIT", timestamp_str,
                        current_zone, 0, is_staff, 0.90, session_sequences[vis_id], queue_depth, group_id
                    )
                    events_batch.append(exit_ev)
                
                # Enter a new zone (could be billing zone)
                # Overlap camera detection warning (Edge Case 7)
                # If they transition to checkout, we flag Billing Queue Join
                next_zone = random.choice(zones + [billing_zone])
                
                if next_zone == billing_zone:
                    # Queue buildup (Edge Case 4)
                    queue_depth += 1
                    session_sequences[vis_id] += 1
                    visitor_active_zones[vis_id] = billing_zone
                    
                    enter_ev = create_event(
                        store_id, "CAM_BILLING_01", vis_id, "BILLING_QUEUE_JOIN", timestamp_str,
                        billing_zone, 0, is_staff, 0.92, session_sequences[vis_id], queue_depth, group_id
                    )
                    events_batch.append(enter_ev)
                    print(f"[Queue Join] {vis_id} joined billing queue. Queue Depth={queue_depth}")
                else:
                    session_sequences[vis_id] += 1
                    visitor_active_zones[vis_id] = next_zone
                    enter_ev = create_event(
                        store_id, "CAM_FLOOR_01", vis_id, "ZONE_ENTER", timestamp_str,
                        next_zone, 0, is_staff, 0.94, session_sequences[vis_id], queue_depth, group_id
                    )
                    events_batch.append(enter_ev)
                    
                emitter.emit_batch(events_batch)

            elif action == "DWELL":
                current_zone = visitor_active_zones.get(vis_id)
                if current_zone:
                    session_sequences[vis_id] += 1
                    dwell_ms = random.randint(30000, 45000) # 30+ seconds dwell
                    
                    # Partial Occlusion Handling (Edge Case 4)
                    # Occasionally emit events with lower confidence due to display blockers
                    confidence = 0.55 if random.random() < 0.15 else 0.93
                    if confidence < 0.6:
                        print(f"[Partial Occlusion] Tracking {vis_id} behind display panel. Confidence reduced to {confidence}")
                        
                    ev = create_event(
                        store_id, "CAM_FLOOR_01" if current_zone != billing_zone else "CAM_BILLING_01",
                        vis_id, "ZONE_DWELL", timestamp_str, current_zone, dwell_ms,
                        is_staff, confidence, session_sequences[vis_id], queue_depth, group_id
                    )
                    emitter.emit_batch([ev])
                    
            elif action == "LEAVE":
                current_zone = visitor_active_zones.get(vis_id)
                
                # Check if leaving from billing queue (Queue Abandonment / Conversion Check)
                if current_zone == billing_zone:
                    queue_depth = max(0, queue_depth - 1)
                    
                    # 30% chance to abandon queue, 70% to exit following a transaction
                    is_abandon = random.random() < 0.30
                    session_sequences[vis_id] += 1
                    
                    if is_abandon:
                        print(f"[Queue Abandon] {vis_id} abandoned the billing queue.")
                        ev = create_event(
                            store_id, "CAM_BILLING_01", vis_id, "BILLING_QUEUE_ABANDON", timestamp_str,
                            billing_zone, 0, is_staff, 0.91, session_sequences[vis_id], queue_depth, group_id
                        )
                        emitter.emit_batch([ev])
                    else:
                        print(f"[Purchase Flow] {vis_id} completed billing checkout.")
                        
                    # Remove from zone tracking
                    del visitor_active_zones[vis_id]
                
                # Emit global EXIT event to close session
                session_sequences[vis_id] += 1
                exit_ev = create_event(
                    store_id, "CAM_ENTRY_01", vis_id, "EXIT", timestamp_str,
                    None, 0, is_staff, 0.96, session_sequences[vis_id], queue_depth, group_id
                )
                emitter.emit_batch([exit_ev])
                active_visitors.remove(vis_id)
                
        time.sleep(1)

def create_event(store_id, camera_id, visitor_id, event_type, timestamp, zone_id, dwell_ms, is_staff, confidence, seq, q_depth, group_id):
    return {
        "event_id": str(uuid.uuid4()),
        "store_id": store_id,
        "camera_id": camera_id,
        "visitor_id": visitor_id,
        "event_type": event_type,
        "timestamp": timestamp,
        "zone_id": zone_id,
        "dwell_ms": dwell_ms,
        "is_staff": is_staff,
        "confidence": round(confidence, 2),
        "metadata": {
            "queue_depth": q_depth if event_type in ["BILLING_QUEUE_JOIN", "BILLING_QUEUE_ABANDON"] else None,
            "sku_zone": group_id if group_id else (zone_id + "_ITEM" if zone_id else None),
            "session_seq": seq
        }
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Apex Store Analytics Detection Pipeline")
    parser.add_argument("--store", type=str, default="STORE_BLR_002", help="Store Identifier")
    parser.add_argument("--url", type=str, default="http://localhost:8000/events/ingest", help="Ingest Endpoint URL")
    parser.add_argument("--duration", type=int, default=60, help="Simulation duration in seconds")
    args = parser.parse_args()
    
    emitter = EventEmitter(args.url)
    run_simulation(emitter, args.store, args.duration)
