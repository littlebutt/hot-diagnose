from diagnose.queues import Q
from diagnose.server.parse import parse_from_trace
from diagnose.server.ws import Websocket


class WebsocketHandler:

    # todo: Use signal to make bi-comunication
    def __init__(self, signal: 'Signal' = None, queue: 'Q' = None):
        self.signal = signal
        self.queue = queue

    async def _do_start(self):
        for _message in Q:
            await self.ws.send(parse_from_trace(_message))

    async def _do_pause(self):
        pass

    async def _do_resume(self):
        pass

    async def _do_stop(self):
        pass

    async def __call__(self, ws: Websocket):
        self.ws = ws
        async for message in ws:
            if message == 'start':
                await self._do_start()
            elif message == 'pause':
                await self._do_pause()
            elif message == 'resume':
                await self._do_resume()
            elif message == 'stop':
                await self._do_stop()
            else:
                raise RuntimeError(f"Unexpected message from clinet {message}")



