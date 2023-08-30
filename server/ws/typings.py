from typing import NewType, Union


Subprotocol = NewType("Subprotocol", str)


ConnectionOption = NewType("ConnectionOption", str)


UpgradeProtocol = NewType("UpgradeProtocol", str)


Data = Union[str, bytes]