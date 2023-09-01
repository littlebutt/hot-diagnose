"""
This package implements the smallest websocket according to `RFC 6455`_.

The code in this package is mostly from the famous Python project `websockets`_
by Aymeric Augustin and other contributors. To make the websocket simple and
fit the senario of the current project, a lot of details and features are removed, 
including origin checking, extensions, extra headers, and request processing, etc.
Actually, it only covers the server-side websocket implementation and all exceptions
appearing in the project are flattened into :exc:`WebsocketException`.

As described in the ``websockets``, the using of the websocket framwork is quite
easy::

    from server.ws import Websocket, serve


    async def echo(ws: Websocket):
        async for message in ws:
            await ws.send(message)

    async def main():
        async with serve(echo, "localhost", 8765):
            await asyncio.Future()

    asyncio.run(main())


.. _`RFC 6455`: https://datatracker.ietf.org/doc/html/rfc6455.html
.. _`websockets`: https://github.com/python-websockets/websockets
"""

from protocol import WebSocketServerProtocol as Websocket
from serve import serve
from exception import WebsocketException


__all__ = ['Websocket', 'serve', 'WebsocketException']