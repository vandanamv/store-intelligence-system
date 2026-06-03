import json
from sqlalchemy import create_engine, Column, String, Integer, Float, Boolean, DateTime, Text, ForeignKey, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.pool import QueuePool
import os
import logging

logger = logging.getLogger("store_intelligence")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./store_intelligence.db")

# Connection pool configuration
if "sqlite" in DATABASE_URL:
    # SQLite: Use check_same_thread=False for multi-threaded access
    # Note: For production with 40 stores, consider PostgreSQL
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False, "timeout": 30},
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,  # Verify connections are alive before using
    )
else:
    # PostgreSQL or other DB: Use connection pool
    engine = create_engine(
        DATABASE_URL,
        poolclass=QueuePool,
        pool_size=20,
        max_overflow=30,
        pool_pre_ping=True,
        echo_pool=False,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class RawEvent(Base):
    __tablename__ = "raw_events"

    event_id = Column(String(36), primary_key=True, index=True)
    store_id = Column(String(50), index=True, nullable=False)
    camera_id = Column(String(50), nullable=False)
    visitor_id = Column(String(50), index=True, nullable=False)
    event_type = Column(String(50), index=True, nullable=False)
    timestamp = Column(DateTime, index=True, nullable=False)
    zone_id = Column(String(50), index=True, nullable=True)
    dwell_ms = Column(Integer, default=0)
    is_staff = Column(Boolean, default=False, index=True)
    confidence = Column(Float, nullable=False)
    metadata_json = Column(Text, nullable=True)  # JSON serialized

    def to_dict(self):
        return {
            "event_id": self.event_id,
            "store_id": self.store_id,
            "camera_id": self.camera_id,
            "visitor_id": self.visitor_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "zone_id": self.zone_id,
            "dwell_ms": self.dwell_ms,
            "is_staff": self.is_staff,
            "confidence": self.confidence,
            "metadata": json.loads(self.metadata_json) if self.metadata_json else {}
        }

class VisitorSession(Base):
    __tablename__ = "visitor_sessions"

    session_id = Column(String(36), primary_key=True, index=True)
    visitor_id = Column(String(50), unique=True, index=True, nullable=False)
    store_id = Column(String(50), index=True, nullable=False)
    session_start = Column(DateTime, nullable=False)
    session_end = Column(DateTime, nullable=True)
    is_staff = Column(Boolean, default=False, index=True)
    group_id = Column(String(50), index=True, nullable=True)
    re_entry_count = Column(Integer, default=0)
    zones_visited_json = Column(Text, default="[]")  # JSON list
    dwell_times_json = Column(Text, default="{}")    # JSON dict zone_id -> dwell_ms
    queue_joined = Column(Boolean, default=False)
    queue_abandoned = Column(Boolean, default=False)
    purchased = Column(Boolean, default=False)
    transaction_id = Column(String(50), nullable=True)
    last_active = Column(DateTime, nullable=False)

    def get_zones_visited(self):
        return json.loads(self.zones_visited_json or "[]")

    def set_zones_visited(self, zones_list):
        self.zones_visited_json = json.dumps(zones_list)

    def get_dwell_times(self):
        return json.loads(self.dwell_times_json or "{}")

    def set_dwell_times(self, dwell_dict):
        self.dwell_times_json = json.dumps(dwell_dict)

class POSTransaction(Base):
    __tablename__ = "pos_transactions"

    transaction_id = Column(String(50), primary_key=True)
    store_id = Column(String(50), index=True, nullable=False)
    timestamp = Column(DateTime, nullable=False)
    basket_value_inr = Column(Float, nullable=False)
    correlated_session_id = Column(String(36), ForeignKey("visitor_sessions.session_id"), nullable=True)

    session = relationship("VisitorSession")

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
