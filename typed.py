from io import TextIOWrapper
from types import FrameType, ModuleType
from typing import Literal, Callable, Any, Protocol, List, Optional, NewType, Tuple

Pair = NewType('Paor', Tuple[Any, Any])

T_event = Literal['call', 'line', 'return', 'exception', 'opcode']


T_frame = FrameType


T_tracefunc = Callable[[FrameType, str, Any], Callable[[FrameType, str, Any], Any] | None]


class TRunner(Protocol):

    def run(self, source: str, args: List[str]):
        pass

    def _build_module(self, source: str) -> ModuleType:
        pass


T_pre_process_hook_func = Callable[..., None]


T_post_process_hook_func = Callable[..., None]


T_tracer_callback_func = Callable[[T_frame, T_event, Any], str]


class TPlugin(Protocol):

    def pre_process_hook(self, *args, **kwargs):
        pass

    def post_process_hook(self, *args, **kwargs):
        pass

    def tracer_callback(self, frame: T_frame, event: T_event, args: Any) -> Optional[str]:
        pass


T_out = NewType('T_stdout', TextIOWrapper)


T_err = NewType('T_stderr', TextIOWrapper)