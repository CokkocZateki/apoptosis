import socket

from tornado.ioloop import IOLoop
from tornado.iostream import IOStream
from tornado import gen

from hkauth.log import svc_log
from hkauth.helpers import cached

from hkauth import config


class TS3Client:
    def __init__(self, io_loop=None):
        self._io_loop = io_loop or IOLoop.instance()
        self._stream = None
        self._clients = []

    @gen.coroutine
    def connect(self, host, port):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)

        self._stream = IOStream(sock, io_loop=self._io_loop)
        self._stream.connect((host, port))

        # Skip the banner messages XXX validate?
        yield self._stream.read_until("\n\r")
        yield self._stream.read_until("\n\r")

        svc_log.debug("ts3_client connected")

        self.login(config.ts3_username, config.ts3_password)

    @gen.coroutine
    def _command(self, command, **params):
        self._stream.write(command + "\n\r")

        response = yield self._stream.read_until("\n\r")

        raise gen.Return(response)

    @gen.coroutine
    def login(self, username, password):
        response = yield self._command("login {} {}".format(username, password))
        svc_log.debug("ts3_client logged in: {}".format(repr(response)))

        self.select_vm(1)

    @gen.coroutine
    def select_vm(self, server=1):
        response = yield self._command("use {}".format(server))
        svc_log.debug("ts3_client selected vm {}: {}".format(server, repr(response)))

    @gen.coroutine
    def ts3_uid_to_cldbid(self, ts3_uid):
        #response = yield self._command("clientgetnamefromuid cluid=1lgnZ0OcGx3O1P4hXseZAdu5cyA=")
        response = yield self._command("servergrouplist")
        print self._parse_response(response)

    @gen.coroutine
    @cached(600)
    def group_slug_to_sgid(self, group_slug):
        response = yield self._command("servergrouplist")
        groups = self._parse_response(response)

        group_sgid = None

        for group in groups:
            if group["name"] == group_slug:
                group_sgid = group["sgid"]
                break
        else:
            raise ValueError("Group not found")

        raise gen.Return(group_sgid)

    def _parse_response(self, response_line):
        responses = response_line.split("|")

        parsed = []

        for response in responses:
            pairs = response.split(" ")

            item = {}

            for pair in pairs:
                key, _, value = pair.partition("=")
                item[key] = value.replace("\s", " ").strip()

            parsed.append(item)

        return parsed

ts3_client = TS3Client()
ts3_client.connect("ts.hardknocksinc.net", 10011)
