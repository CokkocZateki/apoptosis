import tornado.ioloop
import tornado.gen

import itertools


async def loop():
    for x in itertools.count():
        print("minute: {}".format(x))
        await tornado.gen.sleep(60)


def setup():
    tornado.ioloop.IOLoop.current().spawn_callback(loop)
