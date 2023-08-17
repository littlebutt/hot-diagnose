from typing import List, Optional, Callable, ClassVar, Type, Tuple

from engine.logs import Log
from engine.run import PyRunner
from typed import T_post_process_hook_func, T_pre_process_hook_func, TPlugin, Pair


class Pipeline:
    plugins: ClassVar[List[Tuple[TPlugin, bool]]] = []

    def __init__(self, sources: List[str], args: List[str], tracer_callback: Optional[Callable]):
        self.sources = sources
        self.args = args
        self.tracer_callback = tracer_callback

    @classmethod
    def pre_process_hook(cls):
        for plugin, enabled in cls.plugins:
            if enabled:
                plugin.pre_process_hook()

    @classmethod
    def post_process_hook(cls):
        for plugin, enabled in cls.plugins:
            if enabled:
                plugin.post_process_hook()

    def run(self):

        Pipeline.pre_process_hook()

        if len(self.sources) > 1:
            raise NotImplementedError("Cannot support multiple sources")
        runner = PyRunner(source=self.sources[0], args=self.args,
                          tracer_callbacks=[p[0].tracer_callback for p in Pipeline.plugins if p[1]])
        runner.run()
        Pipeline.post_process_hook()

    @classmethod
    def add_plugin(cls, enabled: bool = False):
        def __inner__(plugin_cls: type(TPlugin)):
            plugin = plugin_cls()
            cls.plugins.append((plugin, enabled))
        return __inner__

    @classmethod
    def enable_plugin(cls, plugin_cls: Type[TPlugin]) -> None:
        for _plugin, _enable in cls.plugins:
            if type(_plugin) == plugin_cls:
                _enable = True
        Log.warn(f"Cannot find target plugin {plugin_cls}")

    @classmethod
    def get_plugin(cls, plugin_cls: Type[TPlugin]) -> Optional[TPlugin]:
        for plugin in cls.plugins:
            if type(plugin) == plugin_cls:
                return plugin
        Log.warn(f"Cannot find target plugin {plugin}")
        return None

