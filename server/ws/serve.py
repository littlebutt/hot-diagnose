import asyncio
import functools
import logging
import socket
import sys
import warnings
from http.client import HTTPResponse
from types import TracebackType
from typing import Optional, Set, Iterable, Type, Union, Callable, Awaitable, Any, Sequence, Generator

from server.ws.base import State
from server.ws.http11 import Headers
from server.ws.protocol import WebSocketServerProtocol


class WebSocketServer:
    """
    WebSocket server returned by :func:`serve`.

    This class provides the same interface as :class:`~asyncio.Server`,
    notably the :meth:`~asyncio.Server.close`
    and :meth:`~asyncio.Server.wait_closed` methods.

    It keeps track of WebSocket connections in order to close them properly
    when shutting down.

    Args:
        logger: logger for this server;
            defaults to ``logging.getLogger("websockets.server")``;
            see the :doc:`logging guide <../topics/logging>` for details.

    """

    def __init__(self, logger: Optional = None):
        if logger is None:
            logger = logging.getLogger("websockets.server")
        self.logger = logger

        # Keep track of active connections.
        self.websockets: Set['WebSocketServerProtocol'] = set()

        # Task responsible for closing the server and terminating connections.
        self.close_task: Optional[asyncio.Task[None]] = None

        # Completed when the server is closed and connections are terminated.
        self.closed_waiter: asyncio.Future[None]

    def wrap(self, server: asyncio.base_events.Server) -> None:
        """
        Attach to a given :class:`~asyncio.Server`.

        Since :meth:`~asyncio.loop.create_server` doesn't support injecting a
        custom ``Server`` class, the easiest solution that doesn't rely on
        private :mod:`asyncio` APIs is to:

        - instantiate a :class:`WebSocketServer`
        - give the protocol factory a reference to that instance
        - call :meth:`~asyncio.loop.create_server` with the factory
        - attach the resulting :class:`~asyncio.Server` with this method

        """
        self.server = server
        for sock in server.sockets:
            if sock.family == socket.AF_INET:
                name = "%s:%d" % sock.getsockname()
            elif sock.family == socket.AF_INET6:
                name = "[%s]:%d" % sock.getsockname()[:2]
            elif sock.family == socket.AF_UNIX:
                name = sock.getsockname()
            # In the unlikely event that someone runs websockets over a
            # protocol other than IP or Unix sockets, avoid crashing.
            else:  # pragma: no cover
                name = str(sock.getsockname())
            self.logger.info("server listening on %s", name)

        # Initialized here because we need a reference to the event loop.
        # This should be moved back to __init__ when dropping Python < 3.10.
        self.closed_waiter = server.get_loop().create_future()

    def register(self, protocol: 'WebSocketServerProtocol') -> None:
        """
        Register a connection with this server.

        """
        self.websockets.add(protocol)

    def unregister(self, protocol: 'WebSocketServerProtocol') -> None:
        """
        Unregister a connection with this server.

        """
        self.websockets.remove(protocol)

    def close(self, close_connections: bool = True) -> None:
        """
        Close the server.

        * Close the underlying :class:`~asyncio.Server`.
        * When ``close_connections`` is :obj:`True`, which is the default,
          close existing connections. Specifically:

          * Reject opening WebSocket connections with an HTTP 503 (service
            unavailable) error. This happens when the server accepted the TCP
            connection but didn't complete the opening handshake before closing.
          * Close open WebSocket connections with close code 1001 (going away).

        * Wait until all connection handlers terminate.

        :meth:`close` is idempotent.

        """
        if self.close_task is None:
            self.close_task = self.get_loop().create_task(
                self._close(close_connections)
            )

    async def _close(self, close_connections: bool) -> None:
        """
        Implementation of :meth:`close`.

        This calls :meth:`~asyncio.Server.close` on the underlying
        :class:`~asyncio.Server` object to stop accepting new connections and
        then closes open connections with close code 1001.

        """
        self.logger.info("server closing")

        # Stop accepting new connections.
        self.server.close()

        # Wait until self.server.close() completes.
        await self.server.wait_closed()

        # Wait until all accepted connections reach connection_made() and call
        # register(). See https://bugs.python.org/issue34852 for details.
        await asyncio.sleep(0)

        if close_connections:
            # Close OPEN connections with status code 1001. Since the server was
            # closed, handshake() closes OPENING connections with an HTTP 503
            # error. Wait until all connections are closed.

            close_tasks = [
                asyncio.create_task(websocket.close(1001))
                for websocket in self.websockets
                if websocket.state is not State.CONNECTING
            ]
            # asyncio.wait doesn't accept an empty first argument.
            if close_tasks:
                await asyncio.wait(
                    close_tasks
                )

        # Wait until all connection handlers are complete.

        # asyncio.wait doesn't accept an empty first argument.
        if self.websockets:
            await asyncio.wait(
                [websocket.handler_task for websocket in self.websockets]
            )

        # Tell wait_closed() to return.
        self.closed_waiter.set_result(None)

        self.logger.info("server closed")

    async def wait_closed(self) -> None:
        """
        Wait until the server is closed.

        When :meth:`wait_closed` returns, all TCP connections are closed and
        all connection handlers have returned.

        To ensure a fast shutdown, a connection handler should always be
        awaiting at least one of:

        * :meth:`~WebSocketServerProtocol.recv`: when the connection is closed,
          it raises :exc:`~websockets.exceptions.ConnectionClosedOK`;
        * :meth:`~WebSocketServerProtocol.wait_closed`: when the connection is
          closed, it returns.

        Then the connection handler is immediately notified of the shutdown;
        it can clean up and exit.

        """
        await asyncio.shield(self.closed_waiter)

    def get_loop(self) -> asyncio.AbstractEventLoop:
        """
        See :meth:`asyncio.Server.get_loop`.

        """
        return self.server.get_loop()

    def is_serving(self) -> bool:
        """
        See :meth:`asyncio.Server.is_serving`.

        """
        return self.server.is_serving()

    async def start_serving(self) -> None:
        """
        See :meth:`asyncio.Server.start_serving`.

        Typical use::

            server = await serve(..., start_serving=False)
            # perform additional setup here...
            # ... then start the server
            await server.start_serving()

        """
        await self.server.start_serving()  # pragma: no cover

    async def serve_forever(self) -> None:
        """
        See :meth:`asyncio.Server.serve_forever`.

        Typical use::

            server = await serve(...)
            # this coroutine doesn't return
            # canceling it stops the server
            await server.serve_forever()

        This is an alternative to using :func:`serve` as an asynchronous context
        manager. Shutdown is triggered by canceling :meth:`serve_forever`
        instead of exiting a :func:`serve` context.

        """
        await self.server.serve_forever()  # pragma: no cover

    @property
    def sockets(self) -> Iterable[socket.socket]:
        """
        See :attr:`asyncio.Server.sockets`.

        """
        return self.server.sockets

    async def __aenter__(self) -> 'WebSocketServer':
        return self  # pragma: no cover

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        self.close()
        await self.wait_closed()


class Serve:
    """
    Start a WebSocket server listening on ``host`` and ``port``.

    Whenever a client connects, the server creates a
    :class:`WebSocketServerProtocol`, performs the opening handshake, and
    delegates to the connection handler, ``ws_handler``.

    The handler receives the :class:`WebSocketServerProtocol` and uses it to
    send and receive messages.

    Once the handler completes, either normally or with an exception, the
    server performs the closing handshake and closes the connection.

    Awaiting :func:`serve` yields a :class:`WebSocketServer`. This object
    provides a :meth:`~WebSocketServer.close` method to shut down the server::

        stop = asyncio.Future()  # set this future to exit the server

        server = await serve(...)
        await stop
        await server.close()

    :func:`serve` can be used as an asynchronous context manager. Then, the
    server is shut down automatically when exiting the context::

        stop = asyncio.Future()  # set this future to exit the server

        async with serve(...):
            await stop

    Args:
        ws_handler: connection handler. It receives the WebSocket connection,
            which is a :class:`WebSocketServerProtocol`, in argument.
        host: network interfaces the server is bound to;
            see :meth:`~asyncio.loop.create_server` for details.
        port: TCP port the server listens on;
            see :meth:`~asyncio.loop.create_server` for details.
        create_protocol: factory for the :class:`asyncio.Protocol` managing
            the connection; defaults to :class:`WebSocketServerProtocol`; may
            be set to a wrapper or a subclass to customize connection handling.
        logger: logger for this server;
            defaults to ``logging.getLogger("websockets.server")``;
            see the :doc:`logging guide <../topics/logging>` for details.
        compression: shortcut that enables the "permessage-deflate" extension
            by default; may be set to :obj:`None` to disable compression;
            see the :doc:`compression guide <../topics/compression>` for details.
        origins: acceptable values of the ``Origin`` header; include
            :obj:`None` in the list if the lack of an origin is acceptable.
            This is useful for defending against Cross-Site WebSocket
            Hijacking attacks.
        extensions: list of supported extensions, in order in which they
            should be tried.
        subprotocols: list of supported subprotocols, in order of decreasing
            preference.
        extra_headers (Union[HeadersLike, Callable[[str, Headers], HeadersLike]]):
            arbitrary HTTP headers to add to the request; this can be
            a :data:`~websockets.datastructures.HeadersLike` or a callable
            taking the request path and headers in arguments and returning
            a :data:`~websockets.datastructures.HeadersLike`.
        server_header: value of  the ``Server`` response header;
            defaults to ``"Python/x.y.z websockets/X.Y"``;
            :obj:`None` removes the header.
        process_request (Optional[Callable[[str, Headers], \
            Awaitable[Optional[Tuple[http.HTTPStatus, HeadersLike, bytes]]]]]):
            intercept HTTP request before the opening handshake;
            see :meth:`~WebSocketServerProtocol.process_request` for details.
        select_subprotocol: select a subprotocol supported by the client;
            see :meth:`~WebSocketServerProtocol.select_subprotocol` for details.

    See :class:`~websockets.legacy.protocol.WebSocketCommonProtocol` for the
    documentation of ``ping_interval``, ``ping_timeout``, ``close_timeout``,
    ``max_size``, ``max_queue``, ``read_limit``, and ``write_limit``.

    Any other keyword arguments are passed the event loop's
    :meth:`~asyncio.loop.create_server` method.

    For example:

    * You can set ``ssl`` to a :class:`~ssl.SSLContext` to enable TLS.

    * You can set ``sock`` to a :obj:`~socket.socket` that you created
      outside websockets.

    Returns:
        WebSocketServer: WebSocket server.

    """

    def __init__(
        self,
        ws_handler: Callable[['WebSocketServerProtocol'], Awaitable[Any]],
        host: Optional[Union[str, Sequence[str]]] = None,
        port: Optional[int] = None,
        *,
        create_protocol: Optional[Callable[..., 'WebSocketServerProtocol']] = None,
        logger: Optional = logging.getLogger("websockets.server"),
        process_request: Optional[
            Callable[[str, Headers], Awaitable[Optional[HTTPResponse]]]
        ] = None,
        ping_interval: Optional[float] = 20,
        ping_timeout: Optional[float] = 20,
        close_timeout: Optional[float] = None,
        max_size: Optional[int] = 2**20,
        max_queue: Optional[int] = 2**5,
        read_limit: int = 2**16,
        write_limit: int = 2**16,
        **kwargs: Any,
    ) -> None:
        # Backwards compatibility: close_timeout used to be called timeout.
        timeout: Optional[float] = kwargs.pop("timeout", None)
        if timeout is None:
            timeout = 10
        else:
            warnings.warn("rename timeout to close_timeout", DeprecationWarning)
        # If both are specified, timeout is ignored.
        if close_timeout is None:
            close_timeout = timeout

        # Backwards compatibility: create_protocol used to be called klass.
        klass: Optional[Type['WebSocketServerProtocol']] = kwargs.pop("klass", None)
        if klass is None:
            klass = WebSocketServerProtocol
        else:
            warnings.warn("rename klass to create_protocol", DeprecationWarning)
        # If both are specified, klass is ignored.
        if create_protocol is None:
            create_protocol = klass

        ws_server = WebSocketServer(logger=logger)

        secure = kwargs.get("ssl") is not None

        loop = asyncio.get_event_loop()

        factory = functools.partial(
            create_protocol,
            # For backwards compatibility with 10.0 or earlier. Done here in
            # addition to WebSocketServerProtocol to trigger the deprecation
            # warning once per serve() call rather than once per connection.
            ws_handler,
            ws_server,
            host=host,
            port=port,
            secure=secure,
            ping_interval=ping_interval,
            ping_timeout=ping_timeout,
            close_timeout=close_timeout,
            max_size=max_size,
            max_queue=max_queue,
            read_limit=read_limit,
            write_limit=write_limit,
            loop=loop,
            legacy_recv=False,
            process_request=process_request,
            logger=logger,
        )

        if kwargs.pop("unix", False):
            path: Optional[str] = kwargs.pop("path", None)
            # unix_serve(path) must not specify host and port parameters.
            assert host is None and port is None
            create_server = functools.partial(
                loop.create_unix_server, factory, path, **kwargs
            )
        else:
            create_server = functools.partial(
                loop.create_server, factory, host, port, **kwargs
            )

        # This is a coroutine function.
        self._create_server = create_server
        self.ws_server = ws_server

    # async with serve(...)

    async def __aenter__(self) -> WebSocketServer:
        return await self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        self.ws_server.close()
        await self.ws_server.wait_closed()

    # await serve(...)

    def __await__(self) -> Generator[Any, None, WebSocketServer]:
        # Create a suitable iterator by calling __await__ on a coroutine.
        return self.__await_impl__().__await__()

    async def __await_impl__(self) -> WebSocketServer:
        server = await self._create_server()
        self.ws_server.wrap(server)
        return self.ws_server

    # yield from serve(...) - remove when dropping Python < 3.10

    __iter__ = __await__


serve = Serve

if __name__ == '__main__':

    async def echo(ws):
        async for message in ws:
            await ws.send(message)

    async def main():
        async with serve(echo, "localhost", 8765):
            await asyncio.Future()

    asyncio.run(main())
