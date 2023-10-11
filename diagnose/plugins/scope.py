import os
import re
from typing import Any, Callable, List

from diagnose.engine import PluginManager
from diagnose.typings import TPlugin, T_frame, T_event


@PluginManager.add_plugin(enabled=True)
class ScopePlugin(TPlugin):

    def set_scope_funcs(self, scope_funcs: List[Callable[[str], bool]]):
        assert isinstance(scope_funcs, list)
        self.scope_funcs.extend(scope_funcs)

    @staticmethod
    def _mangle_path(path: str) -> str:
        if re.match(r'^<.*>$', path) is not None:
            return f'inner file {path}'
        return os.path.abspath(path)

    def __init__(self):
        self.scope_funcs = list()

    def on_preprocess(self, *args, **kwargs):
        pass

    def on_postprocess(self, *args, **kwargs):
        pass

    def tracer_callback(self, frame: T_frame, event: T_event, args: Any) -> bool:
        for func in self.scope_funcs:
            if not func(self._mangle_path(frame.f_code.co_filename)):
                return False
        return True
