from types import FrameType, ModuleType
from typing import Literal, Callable, Any, Protocol

T_event = Literal['call', 'line', 'return', 'exception', 'opcode']
T_frame = FrameType

T_tracefunc = Callable[[FrameType, str, Any], Callable[[FrameType, str, Any], Any] | None]


class TRunner(Protocol):

    def run(self, source: Any):
        pass

    def _build_module(self, source: str) -> ModuleType:
        pass
