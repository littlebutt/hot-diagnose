import base64
import binascii
import email
import enum
import hashlib
import http
from typing import List, Optional, Generator, Union

from engine import logs
from http11 import Request, Response, Headers
from parse import parse_connection, ConnectionOption, parse_upgrade, UpgradeProtocol
from server.ws.exception import WebsocketException
from server.ws.frames import Frame, CloseCode, Close, OP_CLOSE, OP_TEXT, OP_BINARY, OP_CONT, OP_PING, OP_PONG
from server.ws.reader import StreamReader


class State(enum.IntEnum):
    """A WebSocket connection is in one of these four states."""

    CONNECTING, OPEN, CLOSING, CLOSED = range(4)


GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

SEND_EOF = b""
"""Sentinel signaling that the TCP connection must be half-closed."""

Event = Union[Request, Response, Frame]
"""Events that :meth:`~Protocol.events_received` may return."""


def accept_key(key: str) -> str:
    """
    Compute the value of the Sec-WebSocket-Accept header.

    Args:
        key: value of the Sec-WebSocket-Key header.

    """
    sha1 = hashlib.sha1((key + GUID).encode()).digest()
    return base64.b64encode(sha1).decode()


class ServerProtocol:
    """
    Sans-I/O implementation of a WebSocket server connection.

    Args:
        state: initial state of the WebSocket connection.
        max_size: maximum size of incoming messages in bytes;
            :obj:`None` disables the limit.
        logger: logger for this connection;

    """

    def __init__(
            self,
            *,
            state: State = State.CONNECTING,
            max_size: Optional[int] = 2 ** 20,
    ):
        self.state = state
        self.max_size = max_size
        self.logger = logs.Log
        self.reader = StreamReader()
        self.writes: List[bytes] = []
        self.events: List[Event] = []
        self.cur_size: Optional[int] = None
        # Track if send_eof() was called.
        self.eof_sent = False
        self.debug = True

    def accept(self, request: Request) -> Response:
        """
        Create a handshake response to accept the connection.

        If the connection cannot be established, the handshake response
        actually rejects the handshake.

        You must send the handshake response with :meth:`send_response`.

        You may modify it before sending it, for example to add HTTP headers.

        Args:
            request: WebSocket handshake request event received from the client.

        Returns:
            WebSocket handshake response event to send to the client.

        """
        try:
            (
                accept_header,
                extensions_header,
                protocol_header,
            ) = self.process_request(request)
        except WebsocketException as exc:
            if exc.type == 'InvalidOrigin':  # InvalidOrigin
                request._exception = exc
                self.handshake_exc = exc
                if self.debug:
                    self.logger.debug("! invalid origin" + exc)
                return self.reject(
                    http.HTTPStatus.FORBIDDEN,
                    f"Failed to open a WebSocket connection: {exc}.\n",
                )
            elif exc.type == 'InvalidUpgrade':  # InvalidUpgrade
                request._exception = exc
                self.handshake_exc = exc
                if self.debug:
                    self.logger.debug("! invalid upgrade" + exc)
                response = self.reject(
                    http.HTTPStatus.UPGRADE_REQUIRED,
                    (
                        f"Failed to open a WebSocket connection: {exc}.\n"
                        f"\n"
                        f"You cannot access a WebSocket server directly "
                        f"with a browser. You need a WebSocket client.\n"
                    ),
                )
                response.headers["Upgrade"] = "websocket"
                return response
            elif exc.type == 'InvalidHandshake':
                request._exception = exc
                self.handshake_exc = exc
                if self.debug:
                    self.logger.debug("! invalid handshake" + exc)
                return self.reject(
                    http.HTTPStatus.BAD_REQUEST,
                    f"Failed to open a WebSocket connection: {exc}.\n",
                )
            else:
                # Handle exceptions raised by user-provided select_subprotocol and
                # unexpected errors.
                request._exception = exc
                self.handshake_exc = exc
                self.logger.error("opening handshake failed" + exc)
                return self.reject(
                    http.HTTPStatus.INTERNAL_SERVER_ERROR,
                    (
                        "Failed to open a WebSocket connection.\n"
                        "See server log for more information.\n"
                    ),
                )

        headers = Headers()

        headers["Date"] = email.utils.formatdate(usegmt=True)

        headers["Upgrade"] = "websocket"
        headers["Connection"] = "Upgrade"
        headers["Sec-WebSocket-Accept"] = accept_header

        if extensions_header is not None:
            headers["Sec-WebSocket-Extensions"] = extensions_header

        if protocol_header is not None:
            headers["Sec-WebSocket-Protocol"] = protocol_header

        self.logger.info("connection open")
        return Response(101, "Switching Protocols", headers)

    def process_request(
            self,
            request: Request,
    ) -> str:
        """
        Check a handshake request and negotiate extensions and subprotocol.

        This function doesn't verify that the request is an HTTP/1.1 or higher
        GET request and doesn't check the ``Host`` header. These controls are
        usually performed earlier in the HTTP request handling code. They're
        the responsibility of the caller.

        Args:
            request: WebSocket handshake request received from the client.

        Returns:
            the value of the Sec-WebSocket-Accept header.

        Raises:
            WebsocketException

        """
        headers = request.headers

        connection: List[ConnectionOption] = sum(
            [parse_connection(value) for value in headers.get_all("Connection")], []
        )

        if not any(value.lower() == "upgrade" for value in connection):
            raise WebsocketException(
                f"InvalidUpgrade: Connection {', '.join(connection) if connection else None}")

        upgrade: List[UpgradeProtocol] = sum(
            [parse_upgrade(value) for value in headers.get_all("Upgrade")], []
        )

        # For compatibility with non-strict implementations, ignore case when
        # checking the Upgrade header. The RFC always uses "websocket", except
        # in section 11.2. (IANA registration) where it uses "WebSocket".
        if not (len(upgrade) == 1 and upgrade[0].lower() == "websocket"):
            raise WebsocketException(f"InvalidUpgrade: Upgrade {','.join(upgrade) if upgrade else None}")

        try:
            key = headers["Sec-WebSocket-Key"]
        except KeyError as exc:
            raise WebsocketException("InvalidHeader: Sec-WebSocket-Key") from exc
        except Exception as exc:
            raise WebsocketException(
                "InvalidHeader: Sec-WebSocket-Key more than one Sec-WebSocket-Key header found"
            ) from exc

        try:
            raw_key = base64.b64decode(key.encode(), validate=True)
        except binascii.Error as exc:
            raise WebsocketException(f"InvalidHeaderValue: Sec-WebSocket-Key {key}") from exc
        if len(raw_key) != 16:
            raise WebsocketException(f"InvalidHeaderValue: Sec-WebSocket-Key {key}")

        try:
            version = headers["Sec-WebSocket-Version"]
        except KeyError as exc:
            raise WebsocketException("InvalidHeader: Sec-WebSocket-Version") from exc
        except Exception as exc:
            raise WebsocketException(
                "InvalidHeader: Sec-WebSocket-Version more than one Sec-WebSocket-Version header found"
            ) from exc

        if version != "13":
            raise WebsocketException(f"InvalidHeaderValue: Sec-WebSocket-Version {version}")

        accept_header = accept_key(key)

        return accept_header

    def reject(
            self,
            status: http.HTTPStatus,
            text: str,
    ) -> Response:
        """
        Create a handshake response to reject the connection.

        A short plain text response is the best fallback when failing to
        establish a WebSocket connection.

        You must send the handshake response with :meth:`send_response`.

        You can modify it before sending it, for example to alter HTTP headers.

        Args:
            status: HTTP status code.
            text: HTTP response body; will be encoded to UTF-8.

        Returns:
            Response: WebSocket handshake response event to send to the client.

        """
        # If a user passes an int instead of a HTTPStatus, fix it automatically.
        status = http.HTTPStatus(status)
        body = text.encode()
        headers = Headers(
            [
                ("Date", email.utils.formatdate(usegmt=True)),
                ("Connection", "close"),
                ("Content-Length", str(len(body))),
                ("Content-Type", "text/plain; charset=utf-8"),
            ]
        )
        response = Response(status.value, status.phrase, headers, body)
        # When reject() is called from accept(), handshake_exc is already set.
        # If a user calls reject(), set handshake_exc to guarantee invariant:
        # "handshake_exc is None if and only if opening handshake succeeded."
        if self.handshake_exc is None:
            self.handshake_exc = WebsocketException(response)
        self.logger.info(f"connection failed ({status.value} {status.phrase})")
        return response

    def send_eof(self) -> None:
        assert not self.eof_sent
        self.eof_sent = True
        if self.debug:
            self.logger.debug("> EOF")
        self.writes.append(SEND_EOF)

    def discard(self) -> Generator[None, None, None]:
        """
        Discard incoming data.

        This coroutine replaces :meth:`parse`:

        - after receiving a close frame, during a normal closure (1.4);
        - after sending a close frame, during an abnormal closure (7.1.7).

        """
        # The server close the TCP connection in the same circumstances where
        # discard() replaces parse(). The client closes the connection later,
        # after the server closes the connection or a timeout elapses.
        # (The latter case cannot be handled in this Sans-I/O layer.)
        assert self.eof_sent
        while not (yield from self.reader.at_eof()):
            self.reader.discard()
        if self.debug:
            self.logger.debug("< EOF")
        self.state = State.CLOSED
        # If discard() completes normally, execution ends here.
        yield
        # Once the reader reaches EOF, its feed_data/eof() methods raise an
        # error, so our receive_data/eof() methods don't step the generator.
        raise AssertionError("discard() shouldn't step after EOF")

    def send_response(self, response: Response) -> None:
        """
        Send a handshake response to the client.

        Args:
            response: WebSocket handshake response event to send.

        """
        if self.debug:
            code, phrase = response.status_code, response.reason_phrase
            self.logger.debug(f"> HTTP/1.1 {code} {phrase}")
            for key, value in response.headers.raw_items():
                self.logger.debug(f"> {key}: {value}")
            if response.body is not None:
                self.logger.debug(f"> [body] ({len(response.body)} bytes)")

        self.writes.append(response.serialize())

        if response.status_code == 101:
            assert self.state is State.CONNECTING
            self.state = State.OPEN
        else:
            self.send_eof()
            self.parser = self.discard()
            next(self.parser)  # start coroutine

    def send_frame(self, frame: Frame) -> None:
        if self.state is not State.OPEN:
            raise WebsocketException(f"InvalidState: cannot write to a WebSocket in the {self.state.name} state")

        if self.debug:
            self.logger.debug("> frame")
        self.writes.append(
            frame.serialize(mask=False)
        )

    def fail(self, code: int, reason: str = "") -> None:
        """
        `Fail the WebSocket connection`_.

        .. _Fail the WebSocket connection:
            https://datatracker.ietf.org/doc/html/rfc6455#section-7.1.7

        Parameters:
            code: close code
            reason: close reason

        Raises:
            ProtocolError: if the code isn't valid.
        """
        # 7.1.7. Fail the WebSocket Connection

        # Send a close frame when the state is OPEN (a close frame was already
        # sent if it's CLOSING), except when failing the connection because
        # of an error reading from or writing to the network.
        if self.state is State.OPEN:
            if code != CloseCode.ABNORMAL_CLOSURE:
                close = Close(code, reason)
                data = close.serialize()
                self.send_frame(Frame(OP_CLOSE, data))
                self.close_sent = close
                self.state = State.CLOSING

        # When failing the connection, a server closes the TCP connection
        # without waiting for the client to complete the handshake, while a
        # client waits for the server to close the TCP connection, possibly
        # after sending a close frame that the client will ignore.
        if not self.eof_sent:
            self.send_eof()

        # 7.1.7. Fail the WebSocket Connection "An endpoint MUST NOT continue
        # to attempt to process data(including a responding Close frame) from
        # the remote endpoint after being instructed to _Fail the WebSocket
        # Connection_."
        self.parser = self.discard()
        next(self.parser)  # start coroutine

    def recv_frame(self, frame: Frame) -> None:
        """
        Process an incoming frame.

        """
        if frame.opcode is OP_TEXT or frame.opcode is OP_BINARY:
            if self.cur_size is not None:
                raise WebsocketException("ProtocolError: expected a continuation frame")
            if frame.fin:
                self.cur_size = None
            else:
                self.cur_size = len(frame.data)

        elif frame.opcode is OP_CONT:
            if self.cur_size is None:
                raise WebsocketException("ProtocolError: unexpected continuation frame")
            if frame.fin:
                self.cur_size = None
            else:
                self.cur_size += len(frame.data)

        elif frame.opcode is OP_PING:
            # 5.5.2. Ping: "Upon receipt of a Ping frame, an endpoint MUST
            # send a Pong frame in response"
            pong_frame = Frame(OP_PONG, frame.data)
            self.send_frame(pong_frame)

        elif frame.opcode is OP_PONG:
            # 5.5.3 Pong: "A response to an unsolicited Pong frame is not
            # expected."
            pass

        elif frame.opcode is OP_CLOSE:
            # 7.1.5.  The WebSocket Connection Close Code
            # 7.1.6.  The WebSocket Connection Close Reason
            self.close_rcvd = Close.parse(frame.data)
            if self.state is State.CLOSING:
                assert self.close_sent is not None
                self.close_rcvd_then_sent = False

            if self.cur_size is not None:
                raise WebsocketException("ProtocolError: incomplete fragmented message")

            # 5.5.1 Close: "If an endpoint receives a Close frame and did
            # not previously send a Close frame, the endpoint MUST send a
            # Close frame in response. (When sending a Close frame in
            # response, the endpoint typically echos the status code it
            # received.)"

            if self.state is State.OPEN:
                # Echo the original data instead of re-serializing it with
                # Close.serialize() because that fails when the close frame
                # is empty and Close.parse() synthesizes a 1005 close code.
                # The rest is identical to send_close().
                self.send_frame(Frame(OP_CLOSE, frame.data))
                self.close_sent = self.close_rcvd
                self.close_rcvd_then_sent = True
                self.state = State.CLOSING

            # 7.1.2. Start the WebSocket Closing Handshake: "Once an
            # endpoint has both sent and received a Close control frame,
            # that endpoint SHOULD _Close the WebSocket Connection_"

            # A server closes the TCP connection immediately, while a client
            # waits for the server to close the TCP connection.
            self.send_eof()

            # 1.4. Closing Handshake: "after receiving a control frame
            # indicating the connection should be closed, a peer discards
            # any further data received."
            self.parser = self.discard()
            next(self.parser)  # start coroutine

        else:
            # This can't happen because Frame.parse() validates opcodes.
            raise AssertionError(f"unexpected opcode: {frame.opcode:02x}")

        self.events.append(frame)

    def _parse(self) -> Generator[None, None, None]:
        """
        Parse incoming data into frames.

        :meth:`receive_data` and :meth:`receive_eof` run this generator
        coroutine until it needs more data or reaches EOF.

        :meth:`parse` never raises an exception. Instead, it sets the
        :attr:`parser_exc` and yields control.

        """
        try:
            while True:
                if (yield from self.reader.at_eof()):
                    if self.debug:
                        self.logger.debug("< EOF")
                    # If the WebSocket connection is closed cleanly, with a
                    # closing handhshake, recv_frame() substitutes parse()
                    # with discard(). This branch is reached only when the
                    # connection isn't closed cleanly.
                    raise EOFError("unexpected end of stream")

                if self.max_size is None:
                    max_size = None
                elif self.cur_size is None:
                    max_size = self.max_size
                else:
                    max_size = self.max_size - self.cur_size

                # During a normal closure, execution ends here on the next
                # iteration of the loop after receiving a close frame. At
                # this point, recv_frame() replaced parse() by discard().
                frame = yield from Frame.parse(
                    self.reader.read_exact,
                    mask=True,
                    max_size=max_size
                )

                if self.debug:
                    self.logger.debug(f"< {frame}")

                self.recv_frame(frame)

        except WebsocketException as exc:
            if exc.type == 'ProtocolError':  # ProtocolError
                self.fail(CloseCode.PROTOCOL_ERROR, str(exc))
                self.parser_exc = exc
            elif exc.type == 'PayloadTooBig':  # PayloadTooBig
                self.fail(CloseCode.MESSAGE_TOO_BIG, str(exc))
                self.parser_exc = exc

        except EOFError as exc:
            self.fail(CloseCode.ABNORMAL_CLOSURE, str(exc))
            self.parser_exc = exc

        except UnicodeDecodeError as exc:
            self.fail(CloseCode.INVALID_DATA, f"{exc.reason} at position {exc.start}")
            self.parser_exc = exc

        except Exception as exc:
            self.logger.error(f"parser failed {exc}")
            # Don't include exception details, which may be security-sensitive.
            self.fail(CloseCode.INTERNAL_ERROR)
            self.parser_exc = exc

        # During an abnormal closure, execution ends here after catching an
        # exception. At this point, fail() replaced parse() by discard().
        yield
        raise AssertionError("parse() shouldn't step after error")

    def parse(self) -> Generator[None, None, None]:
        if self.state is State.CONNECTING:
            try:
                request = yield from Request.parse(
                    self.reader.read_line,
                )
            except Exception as exc:
                self.handshake_exc = exc
                self.send_eof()
                self.parser = self.discard()
                next(self.parser)  # start coroutine
                yield

            if self.debug:
                self.logger.debug(f"< GET {request.path} HTTP/1.1", )
                for key, value in request.headers.raw_items():
                    self.logger.debug(f"< {key}: {value}")

            self.events.append(request)

        yield from self._parse()
