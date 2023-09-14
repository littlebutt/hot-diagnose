import os
import re
from typing import Any, Optional, Callable, List

from engine.manage import PluginManager
from typings import TPlugin, T_frame, T_event


@PluginManager.add_plugin(enabled=True)
class ScopePlugin(TPlugin):
    scope_funcs = []
    # TODO: rewrite here
    # And make it callable

    def set_scope_funcs(self, scope_funcs: List[Callable[[str], bool]]):
        assert isinstance(scope_funcs, list)
        self.scope_funcs.extend(scope_funcs)

    @staticmethod
    def _mangle_path(path: str) -> str:
        if re.match(r'^<.*>$', path) is not None:
            return f'inner file {path}'
        return os.path.abspath(path)

    def on_preprocess(self, *args, **kwargs):
        pass

    def on_postprocess(self, *args, **kwargs):
        pass

    def tracer_callback(self, frame: T_frame, event: T_event, args: Any) -> Any:
        for func in self.scope_funcs:
            if not func(self._mangle_path(frame.f_code.co_filename)):
                return "False"
        return "True"
