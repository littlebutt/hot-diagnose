import logging
from types import FrameType, ModuleType
from typing import Literal, Callable, Any, Protocol, Optional, NamedTuple, TypeVar


class Pair(NamedTuple):
    first: Any
    second: Any


T_event = Literal['call', 'line', 'return', 'exception', 'opcode']


T_frame = FrameType


T_tracefunc = Callable[[FrameType, str, Any], Callable[[FrameType, str, Any], Any] | None]


T_tracer_callback_func = Callable[[T_frame, T_event, Any], str]


class TPlugin(Protocol):

    def __init__(self, *args, **kwargs):
        pass

    def on_preprocess(self, *args, **kwargs):
        pass

    def on_postprocess(self, *args, **kwargs):
        pass

    def tracer_callback(self, frame: T_frame, event: T_event, args: Any) -> Any:
        pass


LoggerLike = TypeVar('LoggerLike', bound=logging.Logger)
