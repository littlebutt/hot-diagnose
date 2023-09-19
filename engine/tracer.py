import json
import os.path
import re
import sys
from typing import Any, cast, Optional, List

import fileutils
from engine.manage import PluginManager
from queues import TraceMessageEntry, Q
from typings import T_frame, T_event, T_tracefunc, T_tracer_callback_func, LoggerLike


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

    def _trace_func(self, frame: T_frame, event: T_event, args: Any):
        sp = PluginManager.get_plugin('ScopePlugin')
        if frame.f_code.co_filename in THIS_FILE or self._is_inner_module(frame.f_code.co_filename) \
                or not sp.tracer_callback(frame, event, args):
            return None
        cb_rt = list()
        if self.callbacks is not None:
            for cb in self.callbacks:
                cb_rt.append({"plugin": cb(frame, event, args)}) if cb(frame, event, args) is not None else None
        self.logger.info(f"filename: {self._mangle_path(frame.f_code.co_filename)}, "
                         f"lineno: {frame.f_lineno}, cb_rt: {json.dumps(cb_rt)}")
        Q.put(TraceMessageEntry(0,
                                self._mangle_path(frame.f_code.co_filename),
                                frame.f_lineno, self.line_hash(frame),cb_rt))
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

    def line_hash(self, frame: T_frame):
        return fileutils.generate_classname(os.path.abspath(frame.f_code.co_filename), int(frame.f_lineno) + 1)
