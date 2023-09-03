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
                 hostname: Union[str, Sequence[str]],
                 port: int,
                 *,
                 logger: Optional['LoggerLike'] = None):
        self.websocket_holder = None
        self.running = False
        self.serve = None

        if logger is None:
            logger = Logger.get_logger('server')
        self.hostname = hostname
        self.port = port
        self.logger = logger

    async def ws_send_loop(self, loop: asyncio.AbstractEventLoop):
        while self.websocket_holder is None:
            print("GET HERE")
            pass

        async def _send_loop():
            while True:
                for message in Q.response_queue:
                    await self.websocket_holder.send(parse_from_trace(message))

        with concurrent.futures.ProcessPoolExecutor() as pool:
            await loop.run_in_executor(pool, _send_loop)

    def _build_serve(self):
        assert self.serve is None

        async def _ws_handler(ws: Websocket):
            async for message in ws:
                for message in Q.response_queue:
                    await self.websocket_holder.send(parse_from_trace(message))
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
        async def _inner():
            async with self._run():
                # await self.ws_send_loop(self.loop)
                await asyncio.Future()
                # await asyncio.sleep(0)

        asyncio.run(_inner())

if __name__ == '__main__':

    rs = RenderServer(hostname='localhost', port=8765)
    rs.run()
