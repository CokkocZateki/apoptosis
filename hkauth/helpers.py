import json
import hashlib

from hkauth.log import app_log
from hkauth.cache import redis_cache


def cached(time=60):
    def decorator(func):
        def wrapper(*args, **kwargs):
            cache_key = "{}({}, {})".format(func.__name__, ", ".join(str(a) for a in args), ", ".join("{}={}".format(k, v) for k, v in kwargs.items()))
            cache_key = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()

            if redis_cache.get(cache_key):
                app_log.debug("serving {} from cache".format(cache_key))
                return json.loads(redis_cache.get(cache_key))

            data = func(*args, **kwargs)

            redis_cache.setex(cache_key, time, json.dumps(data))
            app_log.debug("put {} in cache".format(cache_key))

            return data
        return wrapper
    return decorator
