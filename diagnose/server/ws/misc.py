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


import base64
import binascii
import enum
import hashlib
from typing import List

from diagnose.server.ws.exception import WebsocketException
from diagnose.server.ws.http11 import Headers
from diagnose.server.ws.parse import parse_upgrade, parse_connection
from diagnose.server.ws.typings import UpgradeProtocol, ConnectionOption


class State(enum.IntEnum):
    """A WebSocket connection is in one of these four states."""

    CONNECTING, OPEN, CLOSING, CLOSED = range(4)


GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def accept_key(key: str) -> str:
    """
    Compute the value of the Sec-WebSocket-Accept header.

    Args:
        key: value of the Sec-WebSocket-Key header.

    """
    sha1 = hashlib.sha1((key + GUID).encode()).digest()
    return base64.b64encode(sha1).decode()


def check_request(headers: Headers) -> str:
    """
    Check a handshake request received from the client.

    This function doesn't verify that the request is an HTTP/1.1 or higher GET
    request and doesn't perform ``Host`` and ``Origin`` checks. These controls
    are usually performed earlier in the HTTP request handling code. They're
    the responsibility of the caller.

    Args:
        headers: handshake request headers.

    Returns:
        str: ``key`` that must be passed to :func:`build_response`.

    Raises:
        InvalidHandshake: if the handshake request is invalid;
            then the server must return 400 Bad Request error.

    """
    connection: List[ConnectionOption] = sum(
        [parse_connection(value) for value in headers.get_all("Connection")], []
    )

    if not any(value.lower() == "upgrade" for value in connection):
        raise WebsocketException(f"InvalidUpgrade: Connection {','.join(connection)}")

    upgrade: List[UpgradeProtocol] = sum(
        [parse_upgrade(value) for value in headers.get_all("Upgrade")], []
    )

    # For compatibility with non-strict implementations, ignore case when
    # checking the Upgrade header. The RFC always uses "websocket", except
    # in section 11.2. (IANA registration) where it uses "WebSocket".
    if not (len(upgrade) == 1 and upgrade[0].lower() == "websocket"):
        raise WebsocketException(f"InvalidUpgrade: Upgrade {','.join(upgrade)}")

    try:
        s_w_key = headers["Sec-WebSocket-Key"]
    except KeyError as exc:
        raise WebsocketException("InvalidHeader: Sec-WebSocket-Key") from exc
    except Exception as exc:
        raise WebsocketException(
            "InvalidHeader: Sec-WebSocket-Key more than one Sec-WebSocket-Key header found"
        ) from exc

    try:
        raw_key = base64.b64decode(s_w_key.encode(), validate=True)
    except binascii.Error as exc:
        raise WebsocketException(f"InvalidHeaderValue: Sec-WebSocket-Key {s_w_key}") from exc
    if len(raw_key) != 16:
        raise WebsocketException(f"InvalidHeaderValue: Sec-WebSocket-Key {s_w_key}")

    try:
        s_w_version = headers["Sec-WebSocket-Version"]
    except KeyError as exc:
        raise WebsocketException("InvalidHeader: Sec-WebSocket-Version") from exc
    except Exception as exc:
        raise WebsocketException(
            "InvalidHeader: Sec-WebSocket-Version more than one Sec-WebSocket-Version header found"
        ) from exc

    if s_w_version != "13":
        raise WebsocketException(f"InvalidHeaderValue: Sec-WebSocket-Version {s_w_version}")

    return s_w_key


def build_response(headers: Headers, key: str) -> None:
    """
    Build a handshake response to send to the client.

    Update response headers passed in argument.

    Args:
        headers: handshake response headers.
        key: returned by :func:`check_request`.

    """
    headers["Upgrade"] = "websocket"
    headers["Connection"] = "Upgrade"
    headers["Sec-WebSocket-Accept"] = accept_key(key)
