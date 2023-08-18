import os.path
import sys
from typing import Any, cast, Optional, List

from engine.logs import Log
from typed import T_frame, T_event, T_tracefunc, T_tracer_callback_func


class Tracer:

    def __init__(self, callbacks: Optional[List[T_tracer_callback_func]]):
        self.callbacks = callbacks

    def mangle_path(self, path: str) -> str:
        return os.path.abspath(path)

    def _trace_func(self, frame: T_frame, event: T_event, args: Any):
        Log.debug(f"filename: {self.mangle_path(frame.f_code.co_filename)}, lineno: {frame.f_lineno}")
        if self.callbacks is not None:
            for cb in self.callbacks:
                cb(frame, event, args)
        return self._trace_func

    def start(self):
        trace_func = sys.gettrace()
        if trace_func is not None:
            Log.warn("Trace function has been already amounted")
            sys.settrace(None)
        cast(self._trace_func, T_tracefunc)
        Log.info("Trace function is amounted")
        sys.settrace(self._trace_func)

    def stop(self):
        sys.settrace(None)
        Log.info("Trace function is unamounted")
