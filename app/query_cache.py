"""
Query result caching for expensive computations.
Simple in-memory cache with TTL for scale optimization.
"""
import time
from functools import wraps
from typing import Any, Callable, Dict, Tuple

_cache: Dict[str, Tuple[Any, float]] = {}
CACHE_TTL = 30  # seconds

def cache_result(key_prefix: str, ttl: int = CACHE_TTL):
    """Decorator to cache function results by store_id with TTL."""
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(db, store_id: str, *args, **kwargs):
            cache_key = f"{key_prefix}:{store_id}"
            current_time = time.time()
            
            # Return cached result if fresh
            if cache_key in _cache:
                cached_result, cached_time = _cache[cache_key]
                if current_time - cached_time < ttl:
                    return cached_result
            
            # Compute fresh result
            result = func(db, store_id, *args, **kwargs)
            _cache[cache_key] = (result, current_time)
            return result
        
        return wrapper
    return decorator

def clear_cache(store_id: str = None):
    """Clear cache entries, optionally filtered by store_id."""
    global _cache
    if store_id:
        keys_to_remove = [k for k in _cache.keys() if store_id in k]
        for k in keys_to_remove:
            del _cache[k]
    else:
        _cache.clear()
