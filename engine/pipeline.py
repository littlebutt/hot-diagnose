import os.path
from typing import List, Optional, ClassVar, Dict

from engine.logs import Log
from engine.run import PyRunner
from fs.base import FS
from fs.models import Path, Directory
from queues import DualMessageQueue
from typed import TPlugin, Pair


class Pipeline:
    plugins: ClassVar[Dict[str, Pair[TPlugin, bool]]] = {}

    def __init__(self,
                 sources: List[str],
                 args: List[str],
                 scope_path: str,
                 exclude_dir: Optional[List[str]] = None,
                 exclude_file: Optional[List[str]] = None):
        assert len(sources) > 0
        if len(sources) > 1:
            raise NotImplementedError("Cannot support multiple sources")
        self.source = sources[0]
        self.args = args
        self.exclude_dir = exclude_dir
        self.exclude_file = exclude_file

        self.dmq = DualMessageQueue()
        self.fs = FS(Path(scope_path), exclude_dir=self.exclude_dir, exclude_file=self.exclude_file)
        self.root_dir = Directory(dirname=os.path.abspath(self.source), content=[])

    def _prepare(self):
        self.fs.build(self.root_dir)

    @classmethod
    def pre_process_hook(cls):
        for key, (plugin, enabled) in cls.plugins.items():
            if enabled:
                assert hasattr(plugin, 'pre_process_hook')
                plugin.pre_process_hook()

    @classmethod
    def post_process_hook(cls):
        for key, (plugin, enabled) in cls.plugins.items():
            if enabled:
                assert hasattr(plugin, 'post_process_hook')
                plugin.post_process_hook()

    def run(self):
        self._prepare()
        Pipeline.pre_process_hook()

        runner = PyRunner(source=self.source, args=self.args,
                          tracer_callbacks=[p[0].tracer_callback
                                            for _, p in Pipeline.plugins.items()
                                            if p[1] and hasattr(p[0], 'tracer_callback')],
                          dual_message_queue=self.dmq)
        runner.run()
        Pipeline.post_process_hook()

    @classmethod
    def add_plugin(cls, enabled: bool = False):
        def __inner__(plugin_cls: type(TPlugin)):
            plugin = plugin_cls()
            cls.plugins[plugin_cls.__name__] = ([plugin, enabled])
        return __inner__

    @classmethod
    def enable_plugin(cls, plugin_cls_name: str) -> None:
        for _key, (_plugin, _enable) in cls.plugins.items():
            if _key == plugin_cls_name:
                cls.plugins[_key][1] = True
        Log.warn(f"Cannot find target plugin {plugin_cls_name}")

    @classmethod
    def get_plugin(cls, plugin_cls_name: str) -> Optional[TPlugin]:
        for _key, (_plugin, _enable)  in cls.plugins.items():
            if _key == plugin_cls_name:
                return _plugin
        Log.warn(f"Cannot find target plugin {plugin_cls_name}")
        return None

