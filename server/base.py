import asyncio
import concurrent.futures
import functools
from typing import Optional, Union, Sequence

from logs import Logger
from queues import Q
from server.parse import parse_to_action, parse_from_trace
from server.ws import serve, Websocket

from typings import LoggerLike


class RenderServer:

    def __init__(self,
                 hostname: Union[str, Sequence[str]] = 'localhost',
                 port: int = 8765,
                 *,
                 ws_serve: Optional['serve'] = None,
                 logger: Optional['LoggerLike'] = None):
        self.websocket_holder = None
        self.running = False
        self.serve = None
        if ws_serve is not None:
            self.serve = lambda: ws_serve
            return

        if logger is None:
            logger = Logger.get_logger('server')
        self.hostname = hostname
        self.port = port
        self.logger = logger

    async def ws_send_loop(self, loop: asyncio.AbstractEventLoop):
        while self.websocket_holder is None:
            pass

        async def _send_loop():
            while True:
                for message in Q.request_queue:
                    await self.websocket_holder.send(parse_from_trace(message))

        with concurrent.futures.ProcessPoolExecutor() as pool:
            await loop.run_in_executor(pool, _send_loop)

    def _build_serve(self):
        assert self.serve is None

        async def _ws_handler(ws: Websocket):
            async for message in ws:
                if self.websocket_holder is None:
                    self.websocket_holder = ws
                Q.put_response(parse_to_action(message))

        self.serve = functools.partial(serve,
                                       ws_handler=_ws_handler,
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
        async def _run():
            async with self._run():
                await asyncio.Future()
                await self.ws_send_loop(self.loop)
        asyncio.run(_run())

if __name__ == '__main__':

    rs = RenderServer()
    rs.run()
