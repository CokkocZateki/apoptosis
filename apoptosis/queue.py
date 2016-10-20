import tornado.ioloop
import tornado.gen

import itertools

import uuid


_tasks = []


async def _recurring(key, interval, f, *args, **kwargs):
    while True:
        if not key in _tasks:
            return

        f(*args, **kwargs)
        await tornado.gen.sleep(interval)


def add_once(f, *args, **kwargs):
    tornado.ioloop.IOLoop.current().spawn_callback(f, *args, **kwargs)

def add_recurring(interval, f, *args, **kwargs):
    key = uuid.uuid4()

    _tasks.append(key)

    tornado.ioloop.IOLoop.current().spawn_callback(_recurring, key, interval, f, *args, **kwargs)

    return key

def stop_recurring(key):
    _tasks.remove(key)

def setup():
    add_once(lambda x: print(x), 1)
    add_recurring(60, lambda x: print(x), 1)
