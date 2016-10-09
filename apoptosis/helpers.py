import json
import hashlib

from apoptosis.log import app_log
from apoptosis.cache import redis_cache


def cached(time=60):
    """Cache a function call for `time` in redis."""

    def decorator(func):

        async def wrapper(*args, **kwargs):
            cache_key = "{}({}, {})".format(
                func.__name__,
                ", ".join("{}".format(a) for a in args),
                ", ".join("{}={}".format(k, v) for k, v in kwargs.items())
            ).encode("utf-8")

            cache_key = hashlib.sha256(cache_key).hexdigest()

            if redis_cache.get(cache_key):
                app_log.debug("serving {} from cache".format(cache_key))
                return json.loads(redis_cache.get(cache_key))

            data = await func(*args, **kwargs)

            redis_cache.setex(cache_key, time, json.dumps(data))
            app_log.debug("put {} in cache".format(cache_key))

            return data

        return wrapper

    return decorator
