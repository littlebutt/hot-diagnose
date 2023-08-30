import asyncio
import codecs
import collections
import email
import http
import logging
import ssl
import struct
import time
import random
from typing import Callable, Awaitable, Any, Optional, cast, Tuple, List, Deque, Dict, AsyncIterator, AsyncIterable, \
    Iterable, Mapping, Union

from server.ws.misc import State, build_response, check_request
from server.ws.exception import WebsocketException
from server.ws.frames import Close, OP_CLOSE, Frame, Opcode, OK_CLOSE_CODES, OP_TEXT, OP_BINARY, OP_PING, OP_PONG, \
    OP_CONT, prepare_ctrl, prepare_data
from server.ws.http11 import Headers, read_request
from server.ws.typings import Data


class WebSocketServerProtocol(asyncio.Protocol):
    """
    WebSocket server connection.

    :class:`WebSocketServerProtocol` provides :meth:`recv` and :meth:`send`
    coroutines for receiving and sending messages.

    It supports asynchronous iteration to receive messages::

        async for message in websocket:
            await process(message)

    The iterator exits normally when the connection is closed with close code
    1000 (OK) or 1001 (going away) or without a close code. It raises
    a :exc:`~websockets.exceptions.ConnectionClosedError` when the connection
    is closed with any other code.

    You may customize the opening handshake in a subclass by
    overriding :meth:`process_request` or :meth:`select_subprotocol`.

    Args:
        ws_server: WebSocket server that created this connection.

    See :func:`serve` for the documentation of ``ws_handler``, ``logger``, ``origins``,
    ``extensions``, ``subprotocols``, ``extra_headers``, and ``server_header``.

    See :class:`~websockets.legacy.protocol.WebSocketCommonProtocol` for the
    documentation of ``ping_interval``, ``ping_timeout``, ``close_timeout``,
    ``max_size``, ``max_queue``, ``read_limit``, and ``write_limit``.

    """

    def __init__(
        self,
        ws_handler: Callable[['WebSocketServerProtocol'], Awaitable[Any]],
        ws_server: 'WebSocketServer',
        *,
        read_limit: int = 2 ** 16,
        write_limit: int = 2 ** 16,
        max_size: Optional[int] = 2 ** 20,
        max_queue: Optional[int] = 2 ** 5,
        loop: Optional[asyncio.AbstractEventLoop] = None,
        close_timeout = 10,
        logger: Optional = None,
        ping_interval: Optional[float] = 20,
        ping_timeout: Optional[float] = 20,
        **kwargs: Any,
    ) -> None:
        if logger is None:
            logger = logging.getLogger("websockets.server")
        self.ws_handler = ws_handler
        self.ws_server = ws_server
        self.read_limit = read_limit
        self.write_limit = write_limit
        self.max_size = max_size
        self.max_queue = max_queue
        self.loop = loop
        self.close_timeout = close_timeout
        self.connection_lost_waiter: asyncio.Future[None] = loop.create_future()
        self.reader = asyncio.StreamReader(limit=read_limit // 2, loop=loop)
        self.debug = True
        self.logger = logger
        self.ping_interval = ping_interval
        self.ping_timeout = ping_timeout

        self.state = State.CONNECTING

        # Protect sending fragmented messages.
        self._fragmented_message_waiter: Optional[asyncio.Future[None]] = None

        self.close_rcvd: Optional[Close] = None
        self.close_sent: Optional[Close] = None
        self.close_rcvd_then_sent: Optional[bool] = None

        self._paused = False
        self._drain_waiter: Optional[asyncio.Future[None]] = None
        self._drain_lock = asyncio.Lock()

        # Mapping of ping IDs to pong waiters, in chronological order.
        self.pings: Dict[bytes, Tuple[asyncio.Future[float], float]] = {}

        # Task running the data transfer.
        self.transfer_data_task: asyncio.Task[None]

        # Exception that occurred during data transfer, if any.
        self.transfer_data_exc: Optional[BaseException] = None

        # Task sending keepalive pings.
        self.keepalive_ping_task: asyncio.Task[None]

        # Task closing the TCP connection.
        self.close_connection_task: asyncio.Task[None]

        # Queue of received messages.
        self.messages: Deque[Data] = collections.deque()
        self._pop_message_waiter: Optional[asyncio.Future[None]] = None
        self._put_message_waiter: Optional[asyncio.Future[None]] = None

    @property
    def open(self) -> bool:
        """
        :obj:`True` when the connection is open; :obj:`False` otherwise.

        This attribute may be used to detect disconnections. However, this
        approach is discouraged per the EAFP_ principle. Instead, you should
        handle :exc:`~websockets.exceptions.ConnectionClosed` exceptions.

        .. _EAFP: https://docs.python.org/3/glossary.html#term-eafp

        """
        return self.state is State.OPEN and not self.transfer_data_task.done()

    @property
    def closed(self) -> bool:
        """
        :obj:`True` when the connection is closed; :obj:`False` otherwise.

        Be aware that both :attr:`open` and :attr:`closed` are :obj:`False`
        during the opening and closing sequences.

        """
        return self.state is State.CLOSED

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        """
        Register connection and initialize a task to handle it.

        """
        transport = cast(asyncio.Transport, transport)
        transport.set_write_buffer_limits(self.write_limit)
        self.transport = transport

        # Copied from asyncio.StreamReaderProtocol
        self.reader.set_transport(transport)
        # Register the connection with the server before creating the handler
        # task. Registering at the beginning of the handler coroutine would
        # create a race condition between the creation of the task, which
        # schedules its execution, and the moment the handler starts running.
        self.ws_server.register(self)
        self.handler_task = self.loop.create_task(self.handler())

    async def wait_for_connection_lost(self) -> bool:
        """
        Wait until the TCP connection is closed or ``self.close_timeout`` elapses.

        Return :obj:`True` if the connection is closed and :obj:`False`
        otherwise.

        """
        if not self.connection_lost_waiter.done():
            try:
                await asyncio.wait_for(
                    asyncio.shield(self.connection_lost_waiter),
                    self.close_timeout,
                )
            except asyncio.TimeoutError:
                pass
        # Re-check self.connection_lost_waiter.done() synchronously because
        # connection_lost() could run between the moment the timeout occurs
        # and the moment this coroutine resumes running.
        return self.connection_lost_waiter.done()

    async def close_transport(self) -> None:
        """
        Close the TCP connection.

        """
        # If connection_lost() was called, the TCP connection is closed.
        # However, if TLS is enabled, the transport still needs closing.
        # Else asyncio complains: ResourceWarning: unclosed transport.
        if self.connection_lost_waiter.done() and self.transport.is_closing():
            return

        # Close the TCP connection. Buffers are flushed asynchronously.
        if self.debug:
            self.logger.debug("x closing TCP connection")
        self.transport.close()

        if await self.wait_for_connection_lost():
            return
        if self.debug:
            self.logger.debug("! timed out waiting for TCP close")

        # Abort the TCP connection. Buffers are discarded.
        if self.debug:
            self.logger.debug("x aborting TCP connection")
        self.transport.abort()

        # connection_lost() is called quickly after aborting.
        # Coverage marks this line as a partially executed branch.
        # I suspect a bug in coverage. Ignore it for now.
        await self.wait_for_connection_lost()  # pragma: no cover

    def write_frame_sync(self, fin: bool, opcode: int, data: bytes) -> None:
        frame = Frame(Opcode(opcode), data, fin)
        if self.debug:
            self.logger.debug(f"> {frame}")
        frame.write(
            self.transport.write,
            mask=False,
        )

    # Copied from asyncio.FlowControlMixin
    async def _drain_helper(self) -> None:  # pragma: no cover
        if self.connection_lost_waiter.done():
            raise ConnectionResetError("Connection lost")
        if not self._paused:
            return
        waiter = self._drain_waiter
        assert waiter is None or waiter.cancelled()
        waiter = self.loop.create_future()
        self._drain_waiter = waiter
        await waiter

    # Copied from asyncio.StreamWriter
    async def _drain(self) -> None:  # pragma: no cover
        if self.reader is not None:
            exc = self.reader.exception()
            if exc is not None:
                raise exc
        if self.transport is not None:
            if self.transport.is_closing():
                # Yield to the event loop so connection_lost() may be
                # called.  Without this, _drain_helper() would return
                # immediately, and code that calls
                #     write(...); yield from drain()
                # in a loop would never call connection_lost(), so it
                # would not see an error when the socket is closed.
                await asyncio.sleep(0)
        await self._drain_helper()

    async def close_connection(self) -> None:
        """
        When the opening handshake succeeds, :meth:`connection_open` starts
        this coroutine in a task. It waits for the data transfer phase to
        complete then it closes the TCP connection cleanly.

        When the opening handshake fails, :meth:`fail_connection` does the
        same. There's no data transfer phase in that case.
        """
        try:
            # Wait for the data transfer phase to complete.
            if hasattr(self, "transfer_data_task"):
                try:
                    await self.transfer_data_task
                except asyncio.CancelledError:
                    pass

            # Cancel the keepalive ping task.
            if hasattr(self, "keepalive_ping_task"):
                self.keepalive_ping_task.cancel()

            # Half-close the TCP connection if possible (when there's no TLS).
            if self.transport.can_write_eof():
                if self.debug:
                    self.logger.debug("x half-closing TCP connection")
                # write_eof() doesn't document which exceptions it raises.
                # "[Errno 107] Transport endpoint is not connected" happens,
                # but it isn't completely clear under which circumstances.
                # uvloop can raise RuntimeError here.
                try:
                    self.transport.write_eof()
                except (OSError, RuntimeError):  # pragma: no cover
                    pass

                if await self.wait_for_connection_lost():
                    return  # pragma: no cover
                if self.debug:
                    self.logger.debug("! timed out waiting for TCP close")

        finally:
            # The try/finally ensures that the transport never remains open,
            # even if this coroutine is canceled (for example).
            await self.close_transport()

    def fail_connection(self, code: int = 1006, reason: str = "") -> None:
        """
        Fail the WebSocket Connection
        """
        if self.debug:
            self.logger.debug(f"! failing connection with code {code}")

        # Cancel transfer_data_task if the opening handshake succeeded.
        # cancel() is idempotent and ignored if the task is done already.
        if hasattr(self, "transfer_data_task"):
            self.transfer_data_task.cancel()

        # Send a close frame when the state is OPEN (a close frame was already
        # sent if it's CLOSING), except when failing the connection because of
        # an error reading from or writing to the network.
        # Don't send a close frame if the connection is broken.
        if code != 1006 and self.state is State.OPEN:
            close = Close(code, reason)

            # Write the close frame without draining the write buffer.

            # Keeping fail_connection() synchronous guarantees it can't
            # get stuck and simplifies the implementation of the callers.
            # Not drainig the write buffer is acceptable in this context.

            # This duplicates a few lines of code from write_close_frame().

            self.state = State.CLOSING
            if self.debug:
                self.logger.debug("= connection is CLOSING")

            # If self.close_rcvd was set, the connection state would be
            # CLOSING. Therefore, self.close_rcvd isn't set, and we don't
            # have to set self.close_rcvd_then_sent.
            assert self.close_rcvd is None
            self.close_sent = close

            self.write_frame_sync(True, OP_CLOSE, close.serialize())

        # Start close_connection_task if the opening handshake didn't succeed.
        if not hasattr(self, "close_connection_task"):
            self.close_connection_task = self.loop.create_task(self.close_connection())

    def connection_closed_exc(self) -> WebsocketException:
        exc: WebsocketException
        if (
                self.close_rcvd is not None
                and self.close_rcvd.code in OK_CLOSE_CODES
                and self.close_sent is not None
                and self.close_sent.code in OK_CLOSE_CODES
        ):
            exc = WebsocketException(f"ConnectionClosedOK: {self.close_rcvd} {self.close_sent} {self.close_rcvd_then_sent}")
        else:
            exc = WebsocketException(f"ConnectionClosedError: {self.close_rcvd} {self.close_sent} {self.close_rcvd_then_sent}")
        # Chain to the exception that terminated data transfer, if any.
        exc.__cause__ = self.transfer_data_exc
        return exc

    async def ensure_open(self) -> None:
        """
        Check that the WebSocket connection is open.

        Raise :exc:`~websockets.exceptions.ConnectionClosed` if it isn't.

        """
        # Handle cases from most common to least common for performance.
        if self.state is State.OPEN:
            # If self.transfer_data_task exited without a closing handshake,
            # self.close_connection_task may be closing the connection, going
            # straight from OPEN to CLOSED.
            if self.transfer_data_task.done():
                await asyncio.shield(self.close_connection_task)
                raise self.connection_closed_exc()
            else:
                return

        if self.state is State.CLOSED:
            raise self.connection_closed_exc()

        if self.state is State.CLOSING:
            # If we started the closing handshake, wait for its completion to
            # get the proper close code and reason. self.close_connection_task
            # will complete within 4 or 5 * close_timeout after close(). The
            # CLOSING state also occurs when failing the connection. In that
            # case self.close_connection_task will complete even faster.
            await asyncio.shield(self.close_connection_task)
            raise self.connection_closed_exc()

        # Control may only reach this point in buggy third-party subclasses.
        assert self.state is State.CONNECTING
        raise WebsocketException("InvalidState: WebSocket connection isn't established yet")

    async def drain(self) -> None:
        try:
            async with self._drain_lock:
                # Handle flow control automatically.
                await self._drain()
        except ConnectionError:
            # Terminate the connection if the socket died.
            self.fail_connection()
            # Wait until the connection is closed to raise ConnectionClosed
            # with the correct code and reason.
            await self.ensure_open()

    async def write_frame(
            self, fin: bool, opcode: int, data: bytes, *, _state: int = State.OPEN
    ) -> None:
        # Defensive assertion for protocol compliance.
        if self.state is not _state:
            raise WebsocketException(f"InvalidState: Cannot write to a WebSocket in the {self.state.name} state")
        self.write_frame_sync(fin, opcode, data)
        await self.drain()

    async def write_close_frame(
            self, close: Close, data: Optional[bytes] = None
    ) -> None:
        """
        Write a close frame if and only if the connection state is OPEN.

        This dedicated coroutine must be used for writing close frames to
        ensure that at most one close frame is sent on a given connection.

        """
        # Test and set the connection state before sending the close frame to
        # avoid sending two frames in case of concurrent calls.
        if self.state is State.OPEN:
            # 7.1.3. The WebSocket Closing Handshake is Started
            self.state = State.CLOSING
            if self.debug:
                self.logger.debug("= connection is CLOSING")

            self.close_sent = close
            if self.close_rcvd is not None:
                self.close_rcvd_then_sent = True
            if data is None:
                data = close.serialize()

            # 7.1.2. Start the WebSocket Closing Handshake
            await self.write_frame(True, OP_CLOSE, data, _state=State.CLOSING)

    async def close(self, code: int = 1000, reason: str = "") -> None:
        """
        Perform the closing handshake.

        :meth:`close` waits for the other end to complete the handshake and
        for the TCP connection to terminate. As a consequence, there's no need
        to await :meth:`wait_closed` after :meth:`close`.

        :meth:`close` is idempotent: it doesn't do anything once the
        connection is closed.

        Wrapping :func:`close` in :func:`~asyncio.create_task` is safe, given
        that errors during connection termination aren't particularly useful.

        Canceling :meth:`close` is discouraged. If it takes too long, you can
        set a shorter ``close_timeout``. If you don't want to wait, let the
        Python process exit, then the OS will take care of closing the TCP
        connection.

        Args:
            code: WebSocket close code.
            reason: WebSocket close reason.

        """
        try:
            await asyncio.wait_for(
                self.write_close_frame(Close(code, reason)),
                self.close_timeout
            )
        except asyncio.TimeoutError:
            # If the close frame cannot be sent because the send buffers
            # are full, the closing handshake won't complete anyway.
            # Fail the connection to shut down faster.
            self.fail_connection()

        # If no close frame is received within the timeout, wait_for() cancels
        # the data transfer task and raises TimeoutError.

        # If close() is called multiple times concurrently and one of these
        # calls hits the timeout, the data transfer task will be canceled.
        # Other calls will receive a CancelledError here.

        try:
            # If close() is canceled during the wait, self.transfer_data_task
            # is canceled before the timeout elapses.
            await asyncio.wait_for(
                self.transfer_data_task,
                self.close_timeout,
            )
        except (asyncio.TimeoutError, asyncio.CancelledError):
            pass

        # Wait for the close connection task to close the TCP connection.
        await asyncio.shield(self.close_connection_task)

    async def handler(self) -> None:
        """
        Handle the lifecycle of a WebSocket connection.

        Since this method doesn't have a caller able to handle exceptions, it
        attempts to log relevant ones and guarantees that the TCP connection is
        closed before exiting.

        """
        try:

            try:
                await self.handshake()
            except asyncio.CancelledError:
                raise
            except ConnectionError:
                raise
            except WebsocketException as exc:
                if exc.type == 'AbortHandshake':
                    status, headers, body = None, None, None
                elif exc.type == 'InvalidUpgrade':
                    if self.debug:
                        self.logger.debug(f"! invalid upgrade {exc}")
                    status, headers, body = (
                        http.HTTPStatus.UPGRADE_REQUIRED,
                        Headers([("Upgrade", "websocket")]),
                        (
                            f"Failed to open a WebSocket connection: {exc}.\n"
                            f"\n"
                            f"You cannot access a WebSocket server directly "
                            f"with a browser. You need a WebSocket client.\n"
                        ).encode(),
                    )
                elif exc.type == 'InvalidHandshake':
                    if self.debug:
                        self.logger.debug(f"! invalid handshake {exc}")
                    status, headers, body = (
                        http.HTTPStatus.BAD_REQUEST,
                        Headers(),
                        f"Failed to open a WebSocket connection: {exc}.\n".encode(),
                    )
                else:
                    self.logger.error(f"opening handshake failed {exc}")
                    status, headers, body = (
                        http.HTTPStatus.INTERNAL_SERVER_ERROR,
                        Headers(),
                        (
                            b"Failed to open a WebSocket connection.\n"
                            b"See server log for more information.\n"
                        ),
                    )

                headers.setdefault("Date", email.utils.formatdate(usegmt=True))

                headers.setdefault("Content-Length", str(len(body)))
                headers.setdefault("Content-Type", "text/plain")
                headers.setdefault("Connection", "close")

                self.write_http_response(status, headers, body)
                self.logger.info(
                    f"connection failed ({status.value} {status.phrase})"
                )
                await self.close_transport()
                return

            try:
                await self.ws_handler(self)
            except Exception as exc:
                self.logger.error(f"connection handler failed {exc}")
                if not self.closed:
                    self.fail_connection(1011)
                raise

            try:
                await self.close()
            except ConnectionError:
                raise
            except Exception as exc:
                self.logger.error(f"closing handshake failed {exc}")
                raise

        except Exception:
            # Last-ditch attempt to avoid leaking connections on errors.
            try:
                self.transport.close()
            except Exception:
                pass

        finally:
            # Unregister the connection with the server when the handler task
            # terminates. Registration is tied to the lifecycle of the handler
            # task because the server waits for tasks attached to registered
            # connections before terminating.
            self.ws_server.unregister(self)
            self.logger.info("connection closed")

    async def read_http_request(self) -> Tuple[str, Headers]:
        """
        Read request line and headers from the HTTP request.

        If the request contains a body, it may be read from ``self.reader``
        after this coroutine returns.

        Raises:
            InvalidMessage: if the HTTP message is malformed or isn't an
                HTTP/1.1 GET request.

        """
        try:
            path, headers = await read_request(self.reader)
        except asyncio.CancelledError:  # pragma: no cover
            raise
        except Exception as exc:
            raise WebsocketException("InvalidMessage did not receive a valid HTTP request") from exc

        if self.debug:
            self.logger.debug("< GET %s HTTP/1.1", path)
            for key, value in headers.raw_items():
                self.logger.debug("< %s: %s", key, value)

        self.path = path
        self.request_headers = headers

        return path, headers

    def write_http_response(
        self, status: http.HTTPStatus, headers: Headers, body: Optional[bytes] = None
    ) -> None:
        """
        Write status line and headers to the HTTP response.

        This coroutine is also able to write a response body.

        """
        self.response_headers = headers

        if self.debug:
            self.logger.debug("> HTTP/1.1 %d %s", status.value, status.phrase)
            for key, value in headers.raw_items():
                self.logger.debug("> %s: %s", key, value)
            if body is not None:
                self.logger.debug("> [body] (%d bytes)", len(body))

        # Since the status line and headers only contain ASCII characters,
        # we can keep this simple.
        response = f"HTTP/1.1 {status.value} {status.phrase}\r\n"
        response += str(headers)

        self.transport.write(response.encode())

        if body is not None:
            self.transport.write(body)

    async def read_frame(self, max_size: Optional[int]) -> Frame:
        """
        Read a single frame from the connection.

        """
        frame = await Frame.read(
            self.reader.readexactly,
            mask=True,
            max_size=max_size
        )
        if self.debug:
            self.logger.debug(f"< {frame}")
        return frame

    async def pong(self, data: Data = b"") -> None:
        """
        Send a Pong_.

        .. _Pong: https://www.rfc-editor.org/rfc/rfc6455.html#section-5.5.3

        An unsolicited pong may serve as a unidirectional heartbeat.

        Canceling :meth:`pong` is discouraged. If :meth:`pong` doesn't return
        immediately, it means the write buffer is full. If you don't want to
        wait, you should close the connection.

        Args:
            data (Data): payload of the pong; a string will be encoded to
                UTF-8.

        Raises:
            ConnectionClosed: when the connection is closed.

        """
        await self.ensure_open()

        data = prepare_ctrl(data)

        await self.write_frame(True, OP_PONG, data)

    async def ping(self, data: Optional[Data] = None) -> Awaitable[None]:
        """
        Send a Ping_.

        .. _Ping: https://www.rfc-editor.org/rfc/rfc6455.html#section-5.5.2

        A ping may serve as a keepalive, as a check that the remote endpoint
        received all messages up to this point, or to measure :attr:`latency`.

        Canceling :meth:`ping` is discouraged. If :meth:`ping` doesn't return
        immediately, it means the write buffer is full. If you don't want to
        wait, you should close the connection.

        Canceling the :class:`~asyncio.Future` returned by :meth:`ping` has no
        effect.

        Args:
            data (Optional[Data]): payload of the ping; a string will be
                encoded to UTF-8; or :obj:`None` to generate a payload
                containing four random bytes.

        Returns:
            ~asyncio.Future[float]: A future that will be completed when the
            corresponding pong is received. You can ignore it if you don't
            intend to wait. The result of the future is the latency of the
            connection in seconds.

            ::

                pong_waiter = await ws.ping()
                # only if you want to wait for the corresponding pong
                latency = await pong_waiter

        Raises:
            ConnectionClosed: when the connection is closed.
            RuntimeError: if another ping was sent with the same data and
                the corresponding pong wasn't received yet.

        """
        await self.ensure_open()

        if data is not None:
            data = prepare_ctrl(data)

        # Protect against duplicates if a payload is explicitly set.
        if data in self.pings:
            raise RuntimeError("already waiting for a pong with the same data")

        # Generate a unique random payload otherwise.
        while data is None or data in self.pings:
            data = struct.pack("!I", random.getrandbits(32))

        pong_waiter = self.loop.create_future()
        # Resolution of time.monotonic() may be too low on Windows.
        ping_timestamp = time.perf_counter()
        self.pings[data] = (pong_waiter, ping_timestamp)

        await self.write_frame(True, OP_PING, data)

        return asyncio.shield(pong_waiter)

    async def read_data_frame(self, max_size: Optional[int]) -> Optional[Frame]:
        """
        Read a single data frame from the connection.

        Process control frames received before the next data frame.

        Return :obj:`None` if a close frame is encountered before any data frame.

        """
        # 6.2. Receiving Data
        while True:
            frame = await self.read_frame(max_size)

            # 5.5. Control Frames
            if frame.opcode == OP_CLOSE:
                # 7.1.5.  The WebSocket Connection Close Code
                # 7.1.6.  The WebSocket Connection Close Reason
                self.close_rcvd = Close.parse(frame.data)
                if self.close_sent is not None:
                    self.close_rcvd_then_sent = False
                try:
                    # Echo the original data instead of re-serializing it with
                    # Close.serialize() because that fails when the close frame
                    # is empty and Close.parse() synthesizes a 1005 close code.
                    await self.write_close_frame(self.close_rcvd, frame.data)
                except WebsocketException as exc:
                    # Connection closed before we could echo the close frame.
                    if exc.type == 'ConnectionClosed':
                        pass
                return None

            elif frame.opcode == OP_PING:
                # Answer pings, unless connection is CLOSING.
                if self.state is State.OPEN:
                    try:
                        await self.pong(frame.data)
                    except WebsocketException:
                        # Connection closed while draining write buffer.
                        pass

            elif frame.opcode == OP_PONG:
                if frame.data in self.pings:
                    pong_timestamp = time.perf_counter()
                    # Sending a pong for only the most recent ping is legal.
                    # Acknowledge all previous pings too in that case.
                    ping_id = None
                    ping_ids = []
                    for ping_id, (pong_waiter, ping_timestamp) in self.pings.items():
                        ping_ids.append(ping_id)
                        if not pong_waiter.done():
                            pong_waiter.set_result(pong_timestamp - ping_timestamp)
                        if ping_id == frame.data:
                            self.latency = pong_timestamp - ping_timestamp
                            break
                    else:  # pragma: no cover
                        assert False, "ping_id is in self.pings"
                    # Remove acknowledged pings from self.pings.
                    for ping_id in ping_ids:
                        del self.pings[ping_id]

            # 5.6. Data Frames
            else:
                return frame

    async def read_message(self) -> Optional[Data]:
        """
        Read a single message from the connection.

        Re-assemble data frames if the message is fragmented.

        Return :obj:`None` when the closing handshake is started.

        """
        frame = await self.read_data_frame(max_size=self.max_size)

        # A close frame was received.
        if frame is None:
            return None

        if frame.opcode == OP_TEXT:
            text = True
        elif frame.opcode == OP_BINARY:
            text = False
        else:  # frame.opcode == OP_CONT
            raise WebsocketException("ProtocolError: unexpected opcode")

        # Shortcut for the common case - no fragmentation
        if frame.fin:
            return frame.data.decode("utf-8") if text else frame.data

        # 5.4. Fragmentation
        fragments: List[Data] = []
        max_size = self.max_size
        if text:
            decoder_factory = codecs.getincrementaldecoder("utf-8")
            decoder = decoder_factory(errors="strict")
            if max_size is None:

                def append(frame: Frame) -> None:
                    nonlocal fragments
                    fragments.append(decoder.decode(frame.data, frame.fin))

            else:

                def append(frame: Frame) -> None:
                    nonlocal fragments, max_size
                    fragments.append(decoder.decode(frame.data, frame.fin))
                    assert isinstance(max_size, int)
                    max_size -= len(frame.data)

        else:
            if max_size is None:

                def append(frame: Frame) -> None:
                    nonlocal fragments
                    fragments.append(frame.data)

            else:

                def append(frame: Frame) -> None:
                    nonlocal fragments, max_size
                    fragments.append(frame.data)
                    assert isinstance(max_size, int)
                    max_size -= len(frame.data)

        append(frame)

        while not frame.fin:
            frame = await self.read_data_frame(max_size=max_size)
            if frame is None:
                raise WebsocketException("ProtocolError: incomplete fragmented message")
            if frame.opcode != OP_CONT:
                raise WebsocketException("ProtocolError: unexpected opcode")
            append(frame)

        return ("" if text else b"").join(fragments)

    async def transfer_data(self) -> None:
        """
        Read incoming messages and put them in a queue.

        This coroutine runs in a task until the closing handshake is started.

        """
        try:
            while True:
                message = await self.read_message()

                # Exit the loop when receiving a close frame.
                if message is None:
                    break

                # Wait until there's room in the queue (if necessary).
                if self.max_queue is not None:
                    while len(self.messages) >= self.max_queue:
                        self._put_message_waiter = self.loop.create_future()
                        try:
                            await asyncio.shield(self._put_message_waiter)
                        finally:
                            self._put_message_waiter = None

                # Put the message in the queue.
                self.messages.append(message)

                # Notify recv().
                if self._pop_message_waiter is not None:
                    self._pop_message_waiter.set_result(None)
                    self._pop_message_waiter = None

        except asyncio.CancelledError as exc:
            self.transfer_data_exc = exc
            # If fail_connection() cancels this task, avoid logging the error
            # twice and failing the connection again.
            raise

        except WebsocketException as exc:
            if exc.type == 'ProtocolError':
                self.transfer_data_exc = exc
                self.fail_connection(1002)
            elif exc.type == 'PayloadTooBig':
                self.transfer_data_exc = exc
                self.fail_connection(1009)

        except (ConnectionError, TimeoutError, EOFError, ssl.SSLError) as exc:
            # Reading data with self.reader.readexactly may raise:
            # - most subclasses of ConnectionError if the TCP connection
            #   breaks, is reset, or is aborted;
            # - TimeoutError if the TCP connection times out;
            # - IncompleteReadError, a subclass of EOFError, if fewer
            #   bytes are available than requested;
            # - ssl.SSLError if the other side infringes the TLS protocol.
            self.transfer_data_exc = exc
            self.fail_connection(1006)

        except UnicodeDecodeError as exc:
            self.transfer_data_exc = exc
            self.fail_connection(1007)

        except Exception as exc:
            # This shouldn't happen often because exceptions expected under
            # regular circumstances are handled above. If it does, consider
            # catching and handling more exceptions.
            self.logger.error("data transfer failed", exc_info=True)

            self.transfer_data_exc = exc
            self.fail_connection(1011)

    async def keepalive_ping(self) -> None:
        """
        Send a Ping frame and wait for a Pong frame at regular intervals.

        This coroutine exits when the connection terminates and one of the
        following happens:

        - :meth:`ping` raises :exc:`ConnectionClosed`, or
        - :meth:`close_connection` cancels :attr:`keepalive_ping_task`.

        """
        if self.ping_interval is None:
            return

        try:
            while True:
                await asyncio.sleep(
                    self.ping_interval
                )

                # ping() raises CancelledError if the connection is closed,
                # when close_connection() cancels self.keepalive_ping_task.

                # ping() raises ConnectionClosed if the connection is lost,
                # when connection_lost() calls abort_pings().

                self.logger.debug("% sending keepalive ping")
                pong_waiter = await self.ping()

                if self.ping_timeout is not None:
                    try:
                        await asyncio.wait_for(
                            pong_waiter,
                            self.ping_timeout
                        )
                        self.logger.debug("% received keepalive pong")
                    except asyncio.TimeoutError:
                        if self.debug:
                            self.logger.debug("! timed out waiting for keepalive pong")
                        self.fail_connection(1011, "keepalive ping timeout")
                        break

        # Remove this branch when dropping support for Python < 3.8
        # because CancelledError no longer inherits Exception.
        except asyncio.CancelledError:
            raise

        except WebsocketException:
            pass

        except Exception:
            self.logger.error("keepalive ping failed", exc_info=True)

    def connection_open(self) -> None:
        """
        Callback when the WebSocket opening handshake completes.

        Enter the OPEN state and start the data transfer phase.

        """
        # 4.1. The WebSocket Connection is Established.
        assert self.state is State.CONNECTING
        self.state = State.OPEN
        if self.debug:
            self.logger.debug("= connection is OPEN")
        # Start the task that receives incoming WebSocket messages.
        self.transfer_data_task = self.loop.create_task(self.transfer_data())
        # Start the task that sends pings at regular intervals.
        self.keepalive_ping_task = self.loop.create_task(self.keepalive_ping())
        # Start the task that eventually closes the TCP connection.
        self.close_connection_task = self.loop.create_task(self.close_connection())

    async def handshake(
        self
    ) -> str:
        """
        Perform the server side of the opening handshake.

        Returns:
            str: path of the URI of the request.

        Raises:
            WebsocketException: if the handshake fails.

        """
        path, request_headers = await self.read_http_request()

        # The connection may drop while process_request is running.
        if self.state is State.CLOSED:
            # This subclass of ConnectionError is silently ignored in handler().
            raise BrokenPipeError("connection closed during opening handshake")

        key = check_request(request_headers)

        response_headers = Headers()

        build_response(response_headers, key)

        response_headers.setdefault("Date", email.utils.formatdate(usegmt=True))

        self.write_http_response(http.HTTPStatus.SWITCHING_PROTOCOLS, response_headers)

        self.logger.info("connection open")

        self.connection_open()

        return path

    def data_received(self, data: bytes) -> None:
        self.reader.feed_data(data)

    def abort_pings(self) -> None:
        """
        Raise ConnectionClosed in pending keepalive pings.

        They'll never receive a pong once the connection is closed.

        """
        assert self.state is State.CLOSED
        exc = self.connection_closed_exc()

        for pong_waiter, _ping_timestamp in self.pings.values():
            pong_waiter.set_exception(exc)
            # If the exception is never retrieved, it will be logged when ping
            # is garbage-collected. This is confusing for users.
            # Given that ping is done (with an exception), canceling it does
            # nothing, but it prevents logging the exception.
            pong_waiter.cancel()

    def connection_lost(self, exc: Optional[Exception]) -> None:
        """
        7.1.4. The WebSocket Connection is Closed.

        """
        self.state = State.CLOSED
        self.logger.debug("= connection is CLOSED")

        self.abort_pings()

        # If self.connection_lost_waiter isn't pending, that's a bug, because:
        # - it's set only here in connection_lost() which is called only once;
        # - it must never be canceled.
        self.connection_lost_waiter.set_result(None)

        if True:  # pragma: no cover
            # Copied from asyncio.StreamReaderProtocol
            if self.reader is not None:
                if exc is None:
                    self.reader.feed_eof()
                else:
                    self.reader.set_exception(exc)

            # Copied from asyncio.FlowControlMixin
            # Wake up the writer if currently paused.
            if not self._paused:
                return
            waiter = self._drain_waiter
            if waiter is None:
                return
            self._drain_waiter = None
            if waiter.done():
                return
            if exc is None:
                waiter.set_result(None)
            else:
                waiter.set_exception(exc)

    def pause_writing(self) -> None:  # pragma: no cover
        assert not self._paused
        self._paused = True

    async def recv(self) -> Data:
        """
        Receive the next message.

        When the connection is closed, :meth:`recv` raises
        :exc:`~websockets.exceptions.ConnectionClosed`. Specifically, it
        raises :exc:`~websockets.exceptions.ConnectionClosedOK` after a normal
        connection closure and
        :exc:`~websockets.exceptions.ConnectionClosedError` after a protocol
        error or a network failure. This is how you detect the end of the
        message stream.

        Canceling :meth:`recv` is safe. There's no risk of losing the next
        message. The next invocation of :meth:`recv` will return it.

        This makes it possible to enforce a timeout by wrapping :meth:`recv`
        in :func:`~asyncio.wait_for`.

        Returns:
            Data: A string (:class:`str`) for a Text_ frame. A bytestring
            (:class:`bytes`) for a Binary_ frame.

            .. _Text: https://www.rfc-editor.org/rfc/rfc6455.html#section-5.6
            .. _Binary: https://www.rfc-editor.org/rfc/rfc6455.html#section-5.6

        Raises:
            ConnectionClosed: when the connection is closed.
            RuntimeError: if two coroutines call :meth:`recv` concurrently.

        """
        if self._pop_message_waiter is not None:
            raise RuntimeError(
                "cannot call recv while another coroutine "
                "is already waiting for the next message"
            )

        # Don't await self.ensure_open() here:
        # - messages could be available in the queue even if the connection
        #   is closed;
        # - messages could be received before the closing frame even if the
        #   connection is closing.

        # Wait until there's a message in the queue (if necessary) or the
        # connection is closed.
        while len(self.messages) <= 0:
            pop_message_waiter: asyncio.Future[None] = self.loop.create_future()
            self._pop_message_waiter = pop_message_waiter
            try:
                # If asyncio.wait() is canceled, it doesn't cancel
                # pop_message_waiter and self.transfer_data_task.
                await asyncio.wait(
                    [pop_message_waiter, self.transfer_data_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )
            finally:
                self._pop_message_waiter = None

            # If asyncio.wait(...) exited because self.transfer_data_task
            # completed before receiving a new message, raise a suitable
            # exception (or return None if legacy_recv is enabled).
            if not pop_message_waiter.done():
                    await self.ensure_open()

        # Pop a message from the queue.
        message = self.messages.popleft()

        # Notify transfer_data().
        if self._put_message_waiter is not None:
            self._put_message_waiter.set_result(None)
            self._put_message_waiter = None

        return message

    async def send(
            self,
            message: Union[Data, Iterable[Data], AsyncIterable[Data]],
    ) -> None:
        """
        Send a message.

        A string (:class:`str`) is sent as a Text_ frame. A bytestring or
        bytes-like object (:class:`bytes`, :class:`bytearray`, or
        :class:`memoryview`) is sent as a Binary_ frame.

        .. _Text: https://www.rfc-editor.org/rfc/rfc6455.html#section-5.6
        .. _Binary: https://www.rfc-editor.org/rfc/rfc6455.html#section-5.6

        :meth:`send` also accepts an iterable or an asynchronous iterable of
        strings, bytestrings, or bytes-like objects to enable fragmentation_.
        Each item is treated as a message fragment and sent in its own frame.
        All items must be of the same type, or else :meth:`send` will raise a
        :exc:`TypeError` and the connection will be closed.

        .. _fragmentation: https://www.rfc-editor.org/rfc/rfc6455.html#section-5.4

        :meth:`send` rejects dict-like objects because this is often an error.
        (If you want to send the keys of a dict-like object as fragments, call
        its :meth:`~dict.keys` method and pass the result to :meth:`send`.)

        Canceling :meth:`send` is discouraged. Instead, you should close the
        connection with :meth:`close`. Indeed, there are only two situations
        where :meth:`send` may yield control to the event loop and then get
        canceled; in both cases, :meth:`close` has the same effect and is
        more clear:

        1. The write buffer is full. If you don't want to wait until enough
           data is sent, your only alternative is to close the connection.
           :meth:`close` will likely time out then abort the TCP connection.
        2. ``message`` is an asynchronous iterator that yields control.
           Stopping in the middle of a fragmented message will cause a
           protocol error and the connection will be closed.

        When the connection is closed, :meth:`send` raises
        :exc:`~websockets.exceptions.ConnectionClosed`. Specifically, it
        raises :exc:`~websockets.exceptions.ConnectionClosedOK` after a normal
        connection closure and
        :exc:`~websockets.exceptions.ConnectionClosedError` after a protocol
        error or a network failure.

        Args:
            message (Union[Data, Iterable[Data], AsyncIterable[Data]): message
                to send.

        Raises:
            ConnectionClosed: when the connection is closed.
            TypeError: if ``message`` doesn't have a supported type.

        """
        await self.ensure_open()

        # While sending a fragmented message, prevent sending other messages
        # until all fragments are sent.
        while self._fragmented_message_waiter is not None:
            await asyncio.shield(self._fragmented_message_waiter)

        # Unfragmented message -- this case must be handled first because
        # strings and bytes-like objects are iterable.

        if isinstance(message, (str, bytes, bytearray, memoryview)):
            opcode, data = prepare_data(message)
            await self.write_frame(True, opcode, data)

        # Catch a common mistake -- passing a dict to send().

        elif isinstance(message, Mapping):
            raise TypeError("data is a dict-like object")

        # Fragmented message -- regular iterator.

        elif isinstance(message, Iterable):

            # Work around https://github.com/python/mypy/issues/6227
            message = cast(Iterable[Data], message)

            iter_message = iter(message)
            try:
                fragment = next(iter_message)
            except StopIteration:
                return
            opcode, data = prepare_data(fragment)

            self._fragmented_message_waiter = asyncio.Future()
            try:
                # First fragment.
                await self.write_frame(False, opcode, data)

                # Other fragments.
                for fragment in iter_message:
                    confirm_opcode, data = prepare_data(fragment)
                    if confirm_opcode != opcode:
                        raise TypeError("data contains inconsistent types")
                    await self.write_frame(False, OP_CONT, data)

                # Final fragment.
                await self.write_frame(True, OP_CONT, b"")

            except (Exception, asyncio.CancelledError):
                # We're half-way through a fragmented message and we can't
                # complete it. This makes the connection unusable.
                self.fail_connection(1011)
                raise

            finally:
                self._fragmented_message_waiter.set_result(None)
                self._fragmented_message_waiter = None

        # Fragmented message -- asynchronous iterator

        elif isinstance(message, AsyncIterable):
            # Implement aiter_message = aiter(message) without aiter
            # Work around https://github.com/python/mypy/issues/5738
            aiter_message = cast(
                Callable[[AsyncIterable[Data]], AsyncIterator[Data]],
                type(message).__aiter__,
            )(message)
            try:
                # Implement fragment = anext(aiter_message) without anext
                # Work around https://github.com/python/mypy/issues/5738
                fragment = await cast(
                    Callable[[AsyncIterator[Data]], Awaitable[Data]],
                    type(aiter_message).__anext__,
                )(aiter_message)
            except StopAsyncIteration:
                return
            opcode, data = prepare_data(fragment)

            self._fragmented_message_waiter = asyncio.Future()
            try:
                # First fragment.
                await self.write_frame(False, opcode, data)

                # Other fragments.
                # coverage reports this code as not covered, but it is
                # exercised by tests - changing it breaks the tests!
                async for fragment in aiter_message:  # pragma: no cover
                    confirm_opcode, data = prepare_data(fragment)
                    if confirm_opcode != opcode:
                        raise TypeError("data contains inconsistent types")
                    await self.write_frame(False, OP_CONT, data)

                # Final fragment.
                await self.write_frame(True, OP_CONT, b"")

            except (Exception, asyncio.CancelledError):
                # We're half-way through a fragmented message and we can't
                # complete it. This makes the connection unusable.
                self.fail_connection(1011)
                raise

            finally:
                self._fragmented_message_waiter.set_result(None)
                self._fragmented_message_waiter = None

        else:
            raise TypeError("data must be str, bytes-like, or iterable")

    async def __aiter__(self) -> AsyncIterator[Data]:
        """
        Iterate on incoming messages.

        The iterator  exits normally when the connection is closed with the
        close code 1000 (OK) or 1001(going away) or without a close code. It
        raises a :exc:`~websockets.exceptions.ConnectionClosedError` exception
        when the connection is closed with any other code.

        """
        try:
            while True:
                yield await self.recv()
        except RuntimeError:
            return
