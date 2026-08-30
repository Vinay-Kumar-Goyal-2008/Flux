_MEMORY_CACHE = {}

def get(key: str):
    return _MEMORY_CACHE.get(key)

def set(key: str, val):
    _MEMORY_CACHE[key] = val
