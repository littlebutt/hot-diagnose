import asyncio
from typing import Iterable, Mapping, MutableMapping, NewType, Tuple, Union


ConnectionOption = NewType("ConnectionOption", str)


UpgradeProtocol = NewType("UpgradeProtocol", str)


HeadersLike = Union[
    MutableMapping[str, str],
    Mapping[str, str],
    Iterable[Tuple[str, str]]
]


Data = Union[str, bytes]


ServerLike = NewType('ServerLike', asyncio.Server)


BytesLike = bytes, bytearray, memoryview