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


import asyncio
import re
from typing import Any, Dict, Iterator, List, MutableMapping, Tuple

from diagnose.server.ws.exception import WebsocketException
from diagnose.server.ws.typings import HeadersLike

# Maximum total size of headers is around 128 * 8 KiB = 1 MiB.

MAX_HEADERS = 128

# Limit request line and header lines. 8KiB is the most common default
# configuration of popular HTTP servers.

MAX_LINE = 8192


# Regex for validating header names.

_token_re = re.compile(rb"[-!#$%&\'*+.^_`|~0-9a-zA-Z]+")

# Regex for validating header values.

_value_re = re.compile(rb"[\x09\x20-\x7e\x80-\xff]*")


class Headers(MutableMapping[str, str]):
    __slots__ = ["_dict", "_list"]

    # Like dict, Headers accepts an optional "mapping or iterable" argument.
    def __init__(self, *args: HeadersLike, **kwargs: str) -> None:
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


def d(value: bytes) -> str:
    """
    Decode a bytestring for interpolating into an error message.

    """
    return value.decode(errors="backslashreplace")


async def read_request(stream: asyncio.StreamReader) -> Tuple[str, Headers]:
    """
    Read an HTTP/1.1 GET request and return ``(path, headers)``.

    ``path`` isn't URL-decoded or validated in any way.

    ``path`` and ``headers`` are expected to contain only ASCII characters.
    Other characters are represented with surrogate escapes.

    :func:`read_request` doesn't attempt to read the request body because
    WebSocket handshake requests don't have one. If the request contains a
    body, it may be read from ``stream`` after this coroutine returns.

    Args:
        stream: input to read the request from

    Raises:
        EOFError: if the connection is closed without a full HTTP request
        SecurityError: if the request exceeds a security limit
        ValueError: if the request isn't well formatted

    """
    # https://www.rfc-editor.org/rfc/rfc7230.html#section-3.1.1

    # Parsing is simple because fixed values are expected for method and
    # version and because path isn't checked. Since WebSocket software tends
    # to implement HTTP/1.1 strictly, there's little need for lenient parsing.

    try:
        request_line = await read_line(stream)
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

    headers = await read_headers(stream)

    return path, headers


async def read_response(stream: asyncio.StreamReader) -> Tuple[int, str, Headers]:
    """
    Read an HTTP/1.1 response and return ``(status_code, reason, headers)``.

    ``reason`` and ``headers`` are expected to contain only ASCII characters.
    Other characters are represented with surrogate escapes.

    :func:`read_request` doesn't attempt to read the response body because
    WebSocket handshake responses don't have one. If the response contains a
    body, it may be read from ``stream`` after this coroutine returns.

    Args:
        stream: input to read the response from

    Raises:
        EOFError: if the connection is closed without a full HTTP response
        SecurityError: if the response exceeds a security limit
        ValueError: if the response isn't well formatted

    """
    # https://www.rfc-editor.org/rfc/rfc7230.html#section-3.1.2

    # As in read_request, parsing is simple because a fixed value is expected
    # for version, status_code is a 3-digit number, and reason can be ignored.

    try:
        status_line = await read_line(stream)
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
        raise ValueError(f"invalid HTTP status code: {d(raw_status_code)}") from None
    if not 100 <= status_code < 1000:
        raise ValueError(f"unsupported HTTP status code: {d(raw_status_code)}")
    if not _value_re.fullmatch(raw_reason):
        raise ValueError(f"invalid HTTP reason phrase: {d(raw_reason)}")
    reason = raw_reason.decode()

    headers = await read_headers(stream)

    return status_code, reason, headers


async def read_headers(stream: asyncio.StreamReader) -> Headers:
    """
    Read HTTP headers from ``stream``.

    Non-ASCII characters are represented with surrogate escapes.

    """
    # https://www.rfc-editor.org/rfc/rfc7230.html#section-3.2

    # We don't attempt to support obsolete line folding.

    headers = Headers()
    for _ in range(MAX_HEADERS + 1):
        try:
            line = await read_line(stream)
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
        raise WebsocketException("SecurityError too many HTTP headers")

    return headers


async def read_line(stream: asyncio.StreamReader) -> bytes:
    """
    Read a single line from ``stream``.

    CRLF is stripped from the return value.

    """
    # Security: this is bounded by the StreamReader's limit (default = 32 KiB).
    line = await stream.readline()
    # Security: this guarantees header values are small (hard-coded = 8 KiB)
    if len(line) > MAX_LINE:
        raise WebsocketException("SecurityError line too long")
    # Not mandatory but safe - https://www.rfc-editor.org/rfc/rfc7230.html#section-3.5
    if not line.endswith(b"\r\n"):
        raise EOFError("line without CRLF")
    return line[:-2]