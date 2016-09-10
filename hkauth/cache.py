import toredis

from hkauth import config


redis_cache = toredis.Client()
redis_cache.connect(
    host=config.redis_host,
    port=config.redis_port
)
