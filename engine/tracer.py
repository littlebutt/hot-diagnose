import sys
from typing import Any, cast, Callable

from engine.logs import Log
from engine.typed import T_frame, T_event, T_tracefunc


class Tracer:

    def _trace_func(self, frame: T_frame, event: T_event, args: Any):
        Log.info(f"filename: {frame.f_code.co_filename}, lineno: {frame.f_lineno}, position: {frame.f_code.co_positions()}")
        return self._trace_func

    def start(self):
        trace_func = sys.gettrace()
        if trace_func is not None:
            Log.warn("Trace function has been already amounted")
            return
        cast(self._trace_func, T_tracefunc)
        sys.settrace(self._trace_func)
        Log.info("Trace function is amounted")

    def stop(self):
        sys.settrace(None)
        Log.info("Trace function is unamounted")
