import os.path
import re
import sys
from typing import Any, cast, Optional, List, Callable

from queues import TraceMessageEntry, Q
from typings import T_frame, T_event, T_tracefunc, T_tracer_callback_func, \
    LoggerLike


THIS_FILE = __file__.rstrip('co')


class Tracer:

    def __init__(self,
                 callbacks: Optional[List[T_tracer_callback_func]],
                 logger: LoggerLike):
        self.callbacks = callbacks
        self.logger = logger

    def _mangle_path(self, path: str) -> str:
        return os.path.abspath(path)

    def _is_inner_module(self, path: str) -> bool:
        if re.match(r'^<.*>$', path) is not None:
            return True
        return False

    @staticmethod
    def mangle_func_name(cb: Callable):
        return cb.__qualname__.split('.')[0]

    def _trace_func(self, frame: T_frame, event: T_event, args: Any):
        if frame.f_code.co_filename in THIS_FILE \
                or self._is_inner_module(frame.f_code.co_filename):
            return None
        cb_rt = []
        if self.callbacks is not None:
            for cb in self.callbacks:
                cb_rt.append(
                    f'{self.mangle_func_name(cb)}:'
                    f'{cb(frame, event, args) if cb(frame, event, args) is not None else ""}')
        cb_rt = '|'.join(cb_rt)
        self.logger.info(f"filename: {self._mangle_path(frame.f_code.co_filename)}, "
                         f"lineno: {frame.f_lineno}, cb_rt: {cb_rt}")
        Q.put(TraceMessageEntry(0,
                                self._mangle_path(frame.f_code.co_filename),
                                frame.f_lineno, cb_rt))
        return self._trace_func

    def start(self):
        trace_func = sys.gettrace()
        if trace_func is not None:
            self.logger.warning("Trace function has been already amounted")
            sys.settrace(None)
        self._trace_func = cast(T_tracefunc, self._trace_func)
        self.logger.info("Trace function is amounted")
        sys.settrace(self._trace_func)

    def stop(self):
        sys.settrace(None)
        self.logger.info("Trace function is unamounted")
