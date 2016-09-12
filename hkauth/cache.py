import redis

from hkauth import config


redis_cache = redis.StrictRedis(
    host=config.redis_host,
    port=config.redis_port
)
