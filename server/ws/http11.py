"""
Copyright (c) Aymeric Augustin and contributors

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

    * Redistributions of source code must retain the above copyright notice,
      this list of conditions and the following disclaimer.
    * Redistributions in binary form must reproduce the above copyright notice,
      this list of conditions and the following disclaimer in the documentation
      and/or other materials provided with the distribution.
    * Neither the name of the copyright holder nor the names of its contributors
      may be used to endorse or promote products derived from this software
      without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""
import dataclasses
import re
from typing import Any, Callable, Dict, Generator, Iterable, Iterator, List, Mapping, MutableMapping, Optional, Tuple, Union

from engine.logs import Log


# Maximum total size of headers is around 128 * 8 KiB = 1 MiB.
MAX_HEADERS = 128

# Limit request line and header lines. 8KiB is the most common default
# configuration of popular HTTP servers.
MAX_LINE = 8192

# Support for HTTP response bodies is intended to read an error message
# returned by a server. It isn't designed to perform large file transfers.
MAX_BODY = 2**20  # 1 MiB

# Regex for validating header names.

_token_re = re.compile(rb"[-!#$%&\'*+.^_`|~0-9a-zA-Z]+")

# Regex for validating header values.

_value_re = re.compile(rb"[\x09\x20-\x7e\x80-\xff]*")


class Headers(MutableMapping[str, str]):
    __slots__ = ["_dict", "_list"]

    # Like dict, Headers accepts an optional "mapping or iterable" argument.
    def __init__(self, *args: 'HeadersLike', **kwargs: str) -> None:
        self._dict: Dict[str, List[str]] = {}
        self._list: List[Tuple[str, str]] = []
        self.update(*args, **kwargs)

    def __str__(self) -> str:
        return "".join(f"{key}: {value}\r\n" for key, value in self._list) + "\r\n"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self._list!r})"

    def copy(self) -> 'Headers':
        copy = self.__class__()
        copy._dict = self._dict.copy()
        copy._list = self._list.copy()
        return copy

    def serialize(self) -> bytes:
        # Since headers only contain ASCII characters, we can keep this simple.
        return str(self).encode()

    # Collection methods

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and key.lower() in self._dict

    def __iter__(self) -> Iterator[str]:
        return iter(self._dict)

    def __len__(self) -> int:
        return len(self._dict)

    # MutableMapping methods

    def __getitem__(self, key: str) -> str:
        value = self._dict[key.lower()]
        if len(value) == 1:
            return value[0]
        else:
            raise RuntimeError(f"Multiple key found {key}")

    def __setitem__(self, key: str, value: str) -> None:
        self._dict.setdefault(key.lower(), []).append(value)
        self._list.append((key, value))

    def __delitem__(self, key: str) -> None:
        key_lower = key.lower()
        self._dict.__delitem__(key_lower)
        # This is inefficient. Fortunately deleting HTTP headers is uncommon.
        self._list = [(k, v) for k, v in self._list if k.lower() != key_lower]

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Headers):
            return NotImplemented
        return self._dict == other._dict

    def clear(self) -> None:
        """
        Remove all headers.

        """
        self._dict = {}
        self._list = []

    def update(self, *args: 'HeadersLike', **kwargs: str) -> None:
        """
        Update from a :class:`Headers` instance and/or keyword arguments.

        """
        args = tuple(
            arg.raw_items() if isinstance(arg, Headers) else arg for arg in args
        )
        super().update(*args, **kwargs)

    # Methods for handling multiple values

    def get_all(self, key: str) -> List[str]:
        """
        Return the (possibly empty) list of all values for a header.

        Args:
            key: header name.

        """
        return self._dict.get(key.lower(), [])

    def raw_items(self) -> Iterator[Tuple[str, str]]:
        """
        Return an iterator of all values as ``(name, value)`` pairs.

        """
        return iter(self._list)


HeadersLike = Union[
    Headers,
    Mapping[str, str],
    Iterable[Tuple[str, str]]
]


def d(value: bytes) -> str:
    """
    Decode a bytestring for interpolating into an error message.

    """
    return value.decode(errors="backslashreplace")


@dataclasses.dataclass
class Request:
    """
    WebSocket handshake request.

    Attributes:
        path: Request path, including optional query.
        headers: Request headers.
    """

    path: str
    headers: Headers
    # body isn't useful is the context of this library.

    _exception: Optional[Exception] = None

    @property
    def exception(self) -> Optional[Exception]:
        Log.warn(
            "Request.exception is deprecated; "
            "use ServerProtocol.handshake_exc instead"
        )
        return self._exception

    @classmethod
    def parse(
        cls,
        read_line: Callable[[int], Generator[None, None, bytes]],
    ) -> Generator[None, None, 'Request']:
        """
        Parse a WebSocket handshake request.

        This is a generator-based coroutine.

        The request path isn't URL-decoded or validated in any way.

        The request path and headers are expected to contain only ASCII
        characters. Other characters are represented with surrogate escapes.

        :meth:`parse` doesn't attempt to read the request body because
        WebSocket handshake requests don't have one. If the request contains a
        body, it may be read from the data stream after :meth:`parse` returns.

        Args:
            read_line: generator-based coroutine that reads a LF-terminated
                line or raises an exception if there isn't enough data

        Raises:
            EOFError: if the connection is closed without a full HTTP request.
            SecurityError: if the request exceeds a security limit.
            ValueError: if the request isn't well formatted.

        """

        try:
            request_line = yield from parse_line(read_line)
        except EOFError as exc:
            raise EOFError("connection closed while reading HTTP request line") from exc

        try:
            method, raw_path, version = request_line.split(b" ", 2)
        except ValueError:  # not enough values to unpack (expected 3, got 1-2)
            raise ValueError(f"invalid HTTP request line: {d(request_line)}") from None

        if method != b"GET":
            raise ValueError(f"unsupported HTTP method: {d(method)}")
        if version != b"HTTP/1.1":
            raise ValueError(f"unsupported HTTP version: {d(version)}")
        path = raw_path.decode("ascii", "surrogateescape")

        headers = yield from parse_headers(read_line)

        # https://www.rfc-editor.org/rfc/rfc7230.html#section-3.3.3

        if "Transfer-Encoding" in headers:
            raise NotImplementedError("transfer codings aren't supported")

        if "Content-Length" in headers:
            raise ValueError("unsupported request body")

        return cls(path, headers)

    def serialize(self) -> bytes:
        """
        Serialize a WebSocket handshake request.

        """
        # Since the request line and headers only contain ASCII characters,
        # we can keep this simple.
        request = f"GET {self.path} HTTP/1.1\r\n".encode()
        request += self.headers.serialize()
        return request


@dataclasses.dataclass
class Response:
    """
    WebSocket handshake response.

    Attributes:
        status_code: Response code.
        reason_phrase: Response reason.
        headers: Response headers.
        body: Response body, if any.

    """

    status_code: int
    reason_phrase: str
    headers: Headers
    body: Optional[bytes] = None

    _exception: Optional[Exception] = None

    @property
    def exception(self) -> Optional[Exception]:  # pragma: no cover
        Log.warn(
            "Response.exception is deprecated; "
            "use ClientProtocol.handshake_exc instead",
        )
        return self._exception

    @classmethod
    def parse(
        cls,
        read_line: Callable[[int], Generator[None, None, bytes]],
        read_exact: Callable[[int], Generator[None, None, bytes]],
        read_to_eof: Callable[[int], Generator[None, None, bytes]],
    ) -> Generator[None, None, 'Response']:
        """
        Parse a WebSocket handshake response.

        This is a generator-based coroutine.

        The reason phrase and headers are expected to contain only ASCII
        characters. Other characters are represented with surrogate escapes.

        Args:
            read_line: generator-based coroutine that reads a LF-terminated
                line or raises an exception if there isn't enough data.
            read_exact: generator-based coroutine that reads the requested
                bytes or raises an exception if there isn't enough data.
            read_to_eof: generator-based coroutine that reads until the end
                of the stream.

        Raises:
            EOFError: if the connection is closed without a full HTTP response.
            SecurityError: if the response exceeds a security limit.
            LookupError: if the response isn't well formatted.
            ValueError: if the response isn't well formatted.

        """
        # https://www.rfc-editor.org/rfc/rfc7230.html#section-3.1.2

        try:
            status_line = yield from parse_line(read_line)
        except EOFError as exc:
            raise EOFError("connection closed while reading HTTP status line") from exc

        try:
            version, raw_status_code, raw_reason = status_line.split(b" ", 2)
        except ValueError:  # not enough values to unpack (expected 3, got 1-2)
            raise ValueError(f"invalid HTTP status line: {d(status_line)}") from None

        if version != b"HTTP/1.1":
            raise ValueError(f"unsupported HTTP version: {d(version)}")
        try:
            status_code = int(raw_status_code)
        except ValueError:  # invalid literal for int() with base 10
            raise ValueError(
                f"invalid HTTP status code: {d(raw_status_code)}"
            ) from None
        if not 100 <= status_code < 1000:
            raise ValueError(f"unsupported HTTP status code: {d(raw_status_code)}")
        if not _value_re.fullmatch(raw_reason):
            raise ValueError(f"invalid HTTP reason phrase: {d(raw_reason)}")
        reason = raw_reason.decode()

        headers = yield from parse_headers(read_line)

        # https://www.rfc-editor.org/rfc/rfc7230.html#section-3.3.3

        if "Transfer-Encoding" in headers:
            raise NotImplementedError("transfer codings aren't supported")

        # Since websockets only does GET requests (no HEAD, no CONNECT), all
        # responses except 1xx, 204, and 304 include a message body.
        if 100 <= status_code < 200 or status_code == 204 or status_code == 304:
            body = None
        else:
            content_length: Optional[int]
            try:
                # MultipleValuesError is sufficiently unlikely that we don't
                # attempt to handle it. Instead we document that its parent
                # class, LookupError, may be raised.
                raw_content_length = headers["Content-Length"]
            except KeyError:
                content_length = None
            else:
                content_length = int(raw_content_length)

            if content_length is None:
                try:
                    body = yield from read_to_eof(MAX_BODY)
                except RuntimeError:
                    raise RuntimeError(
                        f"body too large: over {MAX_BODY} bytes"
                    )
            elif content_length > MAX_BODY:
                raise RuntimeError(
                    f"body too large: {content_length} bytes"
                )
            else:
                body = yield from read_exact(content_length)

        return cls(status_code, reason, headers, body)

    def serialize(self) -> bytes:
        """
        Serialize a WebSocket handshake response.

        """
        # Since the status line and headers only contain ASCII characters,
        # we can keep this simple.
        response = f"HTTP/1.1 {self.status_code} {self.reason_phrase}\r\n".encode()
        response += self.headers.serialize()
        if self.body is not None:
            response += self.body
        return response


def parse_headers(
    read_line: Callable[[int], Generator[None, None, bytes]],
) -> Generator[None, None, Headers]:
    """
    Parse HTTP headers.

    Non-ASCII characters are represented with surrogate escapes.

    Args:
        read_line: generator-based coroutine that reads a LF-terminated line
            or raises an exception if there isn't enough data.

    Raises:
        EOFError: if the connection is closed without complete headers.
        RuntimeError: if the request exceeds a security limit.
        ValueError: if the request isn't well formatted.

    """
    # https://www.rfc-editor.org/rfc/rfc7230.html#section-3.2

    # We don't attempt to support obsolete line folding.

    headers = Headers()
    for _ in range(MAX_HEADERS + 1):
        try:
            line = yield from parse_line(read_line)
        except EOFError as exc:
            raise EOFError("connection closed while reading HTTP headers") from exc
        if line == b"":
            break

        try:
            raw_name, raw_value = line.split(b":", 1)
        except ValueError:  # not enough values to unpack (expected 2, got 1)
            raise ValueError(f"invalid HTTP header line: {d(line)}") from None
        if not _token_re.fullmatch(raw_name):
            raise ValueError(f"invalid HTTP header name: {d(raw_name)}")
        raw_value = raw_value.strip(b" \t")
        if not _value_re.fullmatch(raw_value):
            raise ValueError(f"invalid HTTP header value: {d(raw_value)}")

        name = raw_name.decode("ascii")  # guaranteed to be ASCII at this point
        value = raw_value.decode("ascii", "surrogateescape")
        headers[name] = value

    else:
        raise RuntimeError("too many HTTP headers")

    return headers


def parse_line(
    read_line: Callable[[int], Generator[None, None, bytes]],
) -> Generator[None, None, bytes]:
    """
    Parse a single line.

    CRLF is stripped from the return value.

    Args:
        read_line: generator-based coroutine that reads a LF-terminated line
            or raises an exception if there isn't enough data.

    Raises:
        EOFError: if the connection is closed without a CRLF.
        RuntimeError: if the response exceeds a security limit.

    """
    try:
        line = yield from read_line(MAX_LINE)
    except RuntimeError:
        raise RuntimeError("line too long")
    # Not mandatory but safe - https://www.rfc-editor.org/rfc/rfc7230.html#section-3.5
    if not line.endswith(b"\r\n"):
        raise EOFError("line without CRLF")
    return line[:-2]