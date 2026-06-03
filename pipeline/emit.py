import requests
import time
import logging
from typing import List, Dict, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("event_emitter")

class EventEmitter:
    def __init__(self, api_url: str = "http://localhost:8000/events/ingest"):
        self.api_url = api_url

    def emit_batch(self, events: List[Dict[str, Any]], max_retries: int = 5) -> bool:
        """
        Transmits a batch of events to the backend API ingestion endpoint.
        Retries with exponential backoff if the endpoint returns a 503 or has connection issues.
        """
        if not events:
            return True
            
        retry_delay = 1.0  # start with 1 second delay
        
        for attempt in range(max_retries):
            try:
                response = requests.post(self.api_url, json=events, timeout=10)
                
                if response.status_code == 201:
                    logger.info(f"Successfully ingested {len(events)} events.")
                    return True
                elif response.status_code == 503:
                    logger.warning(
                        f"Database busy (503). Retrying attempt {attempt+1}/{max_retries} "
                        f"in {retry_delay}s..."
                    )
                else:
                    logger.error(
                        f"Failed to ingest events. Status={response.status_code} "
                        f"Response={response.text}"
                    )
                    return False
                    
            except requests.RequestException as e:
                logger.warning(
                    f"Network error on attempt {attempt+1}/{max_retries}: {str(e)}. "
                    f"Retrying in {retry_delay}s..."
                )
                
            time.sleep(retry_delay)
            retry_delay *= 2.0  # exponential backoff
            
        logger.error(f"Failed to emit {len(events)} events after {max_retries} attempts.")
        return False
