import asyncio
import functools
from typing import Optional, Union, Sequence

from diagnose.logs import Logger
from diagnose.queues import Q
from diagnose.server.handler import WebsocketHandler
from diagnose.server.ws import serve

from diagnose.typings import LoggerLike


class RenderServer:

    def __init__(self,
                 hostname: Union[str, Sequence[str]],
                 port: int,
                 *,
                 logger: Optional['LoggerLike'] = None):
        self.running = False
        self.serve = None

        if logger is None:
            logger = Logger.get_logger('server')
        self.hostname = hostname
        self.port = port
        self.logger = logger

    def _build_serve(self):
        assert self.serve is None

        ws_handler = WebsocketHandler(queue=Q)

        self.serve = functools.partial(serve,
                                       ws_handler=ws_handler,
                                       host=self.hostname,
                                       port=self.port,
                                       logger=self.logger
                                       )

    def _run(self) -> serve:
        self.running = True
        if self.serve is None:
            self._build_serve()
        _serve = self.serve()
        self.loop = _serve.loop
        return _serve

    def run(self):
        async def _inner():
            async with self._run():
                await asyncio.Future()
        asyncio.run(_inner())
