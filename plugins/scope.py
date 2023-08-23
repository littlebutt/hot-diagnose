import os
import re
from typing import Any, Optional, Callable, List

from engine import Pipeline
from queues import MessageQueue
from typed import TPlugin, T_frame, T_event


def self_dismiss(filename: str) -> bool:
    if filename.endswith(os.path.join(os.path.abspath(os.path.curdir).rstrip('plugins'),
                                      'engine' + os.path.sep + 'tracer.py')):
        return False
    if filename.startswith('inner file'):
        return False
    return True


@Pipeline.add_plugin(True)
class ScopePlugin(TPlugin):
    scope_funcs = [self_dismiss]

    def set_scope_funcs(self, scope_funcs: List[Callable[[str], bool]]):
        assert isinstance(scope_funcs, list)
        self.scope_funcs.extend(scope_funcs)

    @staticmethod
    def _mangle_path(path: str) -> str:
        if re.match(r'^<.*>$', path) is not None:
            return f'inner file {path}'
        return os.path.abspath(path)

    def pre_process_hook(self, *args, **kwargs):
        pass

    def post_process_hook(self, *args, **kwargs):
        pass

    def tracer_callback(self, frame: T_frame, event: T_event, args: Any) -> Optional[str]:
        for func in self.scope_funcs:
            if not func(self._mangle_path(frame.f_code.co_filename)):
                return "False"
        return "True"
