import socket

from typing import List, Dict

from tornado.ioloop import IOLoop
from tornado.iostream import IOStream

from apoptosis.log import svc_log
from apoptosis.helpers import cached

from apoptosis import config


class TS3Client:
    def __init__(self, io_loop=None):
        self._io_loop = io_loop or IOLoop.instance()
        self._stream = None
        self._clients = []

    async def connect(self, host: str, port: int) -> str:
        svc_log.debug("ts3_client connecting to {}:{}".format(host, port))

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)

        self._stream = IOStream(sock, io_loop=self._io_loop)
        self._stream.connect((host, port))

        # Skip the banner messages
        await self._stream.read_until("\n\r")
        await self._stream.read_until("\n\r")

        svc_log.debug("ts3_client connected")

        return await self.login(config.ts3_username, config.ts3_password)

    async def _command(self, command: str, **params) -> str:
        await self._stream.write(command + "\n\r")
        return await self._stream.read_until("\n\r")

    async def login(self, username: str, password: str) -> str:
        response = await self._command("login {} {}".format(username, password))
        svc_log.debug("ts3_client logged in: {}".format(repr(response)))

        return self.select_vm(1)

    async def select_vm(self, server: int = 1) -> str:
        svc_log.debug("ts3_client selecting vm {}: {}".format(server, repr(response)))
        return await self._command("use {}".format(server))

    async def ts3_uid_to_cldbid(self, ts3_uid: str) -> str:
        return await self._command("servergrouplist")

    @cached(600)
    async def group_slug_to_sgid(self, group_slug: str) -> int:
        response = await self._command("servergrouplist")

        groups = self._parse_response(response)

        for group in groups:
            if group["name"] == group_slug:
                return int(group_sgid)
        else:
            raise ValueError("TeamSpeak 3 group not found")

    def _parse_response(self, response_line: str) -> List[Dict[str, str]]:
        """Parse a TeamSpeak 3 answer to its parts. Responses are delimited
           by | and whitespace is replaced by \s. Key/values in responses are
           delimited by =."""

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


ts3_client = TS3Client().connect(config.ts3_server, config.ts3_port)
