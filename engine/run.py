import os.path
import sys
from typing import Any, Optional

from engine.fs import read_source_py
from engine.logs import Log
from engine.typed import TRunner


class ScriptRunner(TRunner):

    def run(self, source: str):
        source_byte = read_source_py(source)
        code: Optional[bytes] = None
        try:
            code = compile(source_byte, source, "exec", dont_inherit=True)
        except Exception as e:
            Log.error(f"Fail to compile code: {source}", e)
            return
        try:
            exec(code)
        except Exception as e:
            Log.error(f"Fail to execute code: {source}", e)


class ModuleRunnrer(TRunner):

    def run(self, source: str):
        pass


class PyRunner:

    __runner_class__: TRunner = ScriptRunner
    source: Optional[str] = None

    def __init__(self,
                source: str,
                target_is_dir: bool):
        if os.path.isabs(source):
            self.source = source
        else:
            for path in [os.curdir] + sys.path:
                if path is None:
                    continue
                f = os.path.join(path, source)
                try:
                    exists = os.path.exists(f)
                except UnicodeError:
                    exists = False
                if exists:
                    self.source = f
                    break
        if target_is_dir:
            self.__runner_class__ = ModuleRunnrer
        else:
            self.__runner_class__ = ScriptRunner

    def run(self):
        assert self.source is not None
        runner = self.__runner_class__()
        runner.run(self.source)
