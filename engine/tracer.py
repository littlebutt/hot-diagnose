import os.path
import re
import sys
from typing import Any, cast, Optional, List, Callable

from queues import TraceMessageEntry, Q
from typings import T_frame, T_event, T_tracefunc, T_tracer_callback_func, \
    LoggerLike


class Tracer:

    def __init__(self,
                 callbacks: Optional[List[T_tracer_callback_func]],
                 logger: LoggerLike):
        self.callbacks = callbacks
        self.logger = logger

    @staticmethod
    def mangle_path(path: str) -> str:
        if re.match(r'^<.*>$', path) is not None:
            return f'inner file {path}'
        return os.path.abspath(path)

    @staticmethod
    def manble_func_name(cb: Callable):
        return cb.__qualname__.split('.')[0]

    def _trace_func(self, frame: T_frame, event: T_event, args: Any):
        cb_rt = []
        if self.callbacks is not None:
            for cb in self.callbacks:
                cb_rt.append(
                    f'{self.manble_func_name(cb)}:'
                    f'{cb(frame, event, args) if cb(frame, event, args) is not None else ""}')
        cb_rt = '|'.join(cb_rt)
        self.logger.info(f"filename: {self.mangle_path(frame.f_code.co_filename)}, "
                            f"lineno: {frame.f_lineno}, cb_rt: {cb_rt}")
        Q.put_response(TraceMessageEntry(0,
                                         self.mangle_path(frame.f_code.co_filename),
                                         frame.f_lineno, cb_rt))
        return self._trace_func

    def start(self):
        trace_func = sys.gettrace()
        if trace_func is not None:
            self.logger.warning("Trace function has been already amounted")
            sys.settrace(None)
        cast(self._trace_func, T_tracefunc)
        self.logger.info("Trace function is amounted")
        sys.settrace(self._trace_func)

    def stop(self):
        sys.settrace(None)
        self.logger.info("Trace function is unamounted")
