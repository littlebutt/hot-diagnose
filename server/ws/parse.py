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


import re
from typing import Callable, List, NewType, Optional, Tuple, TypeVar, cast

from server.ws.typings import ConnectionOption, UpgradeProtocol


def peek_ahead(header: str, pos: int) -> Optional[str]:
    """
    Return the next character from ``header`` at the given position.

    Return :obj:`None` at the end of ``header``.

    We never need to peek more than one character ahead.

    """
    return None if pos == len(header) else header[pos]


_OWS_re = re.compile(r"[\t ]*")


def parse_OWS(header: str, pos: int) -> int:
    """
    Parse optional whitespace from ``header`` at the given position.

    Return the new position.

    The whitespace itself isn't returned because it isn't significant.

    """
    # There's always a match, possibly empty, whose content doesn't matter.
    match = _OWS_re.match(header, pos)
    assert match is not None
    return match.end()


T = TypeVar('T')


def parse_list(
    parse_item: Callable[[str, int, str], Tuple[T, int]],
    header: str,
    pos: int,
    header_name: str,
) -> List[T]:
    """
    Parse a comma-separated list from ``header`` at the given position.

    This is appropriate for parsing values with the following grammar:

        1#item

    ``parse_item`` parses one item.

    ``header`` is assumed not to start or end with whitespace.

    (This function is designed for parsing an entire header value and
    :func:`read_headers` strips whitespace from values.)

    Return a list of items.

    Raises:
        RuntimeError: on invalid inputs.

    """
    # Per https://www.rfc-editor.org/rfc/rfc7230.html#section-7, "a recipient
    # MUST parse and ignore a reasonable number of empty list elements";
    # hence while loops that remove extra delimiters.

    # Remove extra delimiters before the first item.
    while peek_ahead(header, pos) == ",":
        pos = parse_OWS(header, pos + 1)

    items = []
    while True:
        # Loop invariant: an item starts at pos in header.
        item, pos = parse_item(header, pos, header_name)
        items.append(item)
        pos = parse_OWS(header, pos)

        # We may have reached the end of the header.
        if pos == len(header):
            break

        # There must be a delimiter after each element except the last one.
        if peek_ahead(header, pos) == ",":
            pos = parse_OWS(header, pos + 1)
        else:
            raise RuntimeError(
                header_name, "expected comma", header, pos
            )

        # Remove extra delimiters before the next item.
        while peek_ahead(header, pos) == ",":
            pos = parse_OWS(header, pos + 1)

        # We may have reached the end of the header.
        if pos == len(header):
            break

    # Since we only advance in the header by one character with peek_ahead()
    # or with the end position of a regex match, we can't overshoot the end.
    assert pos == len(header)

    return items


_token_re = re.compile(r"[-!#$%&\'*+.^_`|~0-9a-zA-Z]+")


def parse_token(header: str, pos: int, header_name: str) -> Tuple[str, int]:
    """
    Parse a token from ``header`` at the given position.

    Return the token value and the new position.

    Raises:
        RuntimeError: on invalid inputs.

    """
    match = _token_re.match(header, pos)
    if match is None:
        raise RuntimeError(header_name, "expected token", header, pos)
    return match.group(), match.end()


def parse_connection_option(
    header: str, pos: int, header_name: str
) -> Tuple[ConnectionOption, int]:
    """
    Parse a Connection option from ``header`` at the given position.

    Return the protocol value and the new position.

    Raises:
        RuntimeError: on invalid inputs.

    """
    item, pos = parse_token(header, pos, header_name)
    return cast(ConnectionOption, item), pos


def parse_connection(header: str) -> List[ConnectionOption]:
    """
    Parse a ``Connection`` header.

    Return a list of HTTP connection options.

    Args
        header: value of the ``Connection`` header.

    Raises:
        RuntimeError: on invalid inputs.

    """
    return parse_list(parse_connection_option, header, 0, "Connection")


_protocol_re = re.compile(
    r"[-!#$%&\'*+.^_`|~0-9a-zA-Z]+(?:/[-!#$%&\'*+.^_`|~0-9a-zA-Z]+)?"
)


def parse_upgrade_protocol(
    header: str, pos: int, header_name: str
) -> Tuple[UpgradeProtocol, int]:
    """
    Parse an Upgrade protocol from ``header`` at the given position.

    Return the protocol value and the new position.

    Raises:
        RuntimeError: on invalid inputs.

    """
    match = _protocol_re.match(header, pos)
    if match is None:
        raise RuntimeError(
            f"{header_name}, 'expected protocol', {header}, {pos}"
        )
    return cast(UpgradeProtocol, match.group()), match.end()


def parse_upgrade(header: str) -> List[UpgradeProtocol]:
    """
    Parse an ``Upgrade`` header.

    Return a list of HTTP protocols.

    Args:
        header: value of the ``Upgrade`` header.

    Raises:
        RuntimeError: on invalid inputs.

    """
    return parse_list(parse_upgrade_protocol, header, 0, "Upgrade")