from typing import List, Optional, ClassVar, Dict

from engine.dispatch import Dispatcher
from engine.report import Reporter
from engine.run import PyRunner
from fs.base import FS
from fs import Path
from logs import Logger
from server import RenderServer
from typings import TPlugin, Pair, LoggerLike


class Pipeline:
    plugins: ClassVar[Dict[str, Pair[TPlugin, bool]]] = dict()

    def __init__(self,
                 source: str,
                 args: List[str],
                 scope_path: str,
                 *,
                 exclude_dir: Optional[List[str]] = None,
                 exclude_file: Optional[List[str]] = None,
                 max_workers: int = 2,
                 server_hostname: str = 'localhost',
                 port: int = 8765,
                 logger: Optional['LoggerLike'] = None):
        if logger is None:
            logger = Logger.get_logger('engine')
        self.source = source
        self.args = args
        self.exclude_dir = exclude_dir
        self.exclude_file = exclude_file
        self.logger = logger

        self.fs = FS(Path(scope_path),
                     exclude_dir=self.exclude_dir,
                     exclude_file=self.exclude_file)
        self.dispatcher = Dispatcher(max_workers=max_workers)
        self.render_server = RenderServer(hostname=server_hostname, port=port)
        self.reporter = Reporter(self.fs, './server/templates', logger=self.logger)

    def do_process(self):
        Pipeline.do_preprocess()
        self.logger.info("finish doing preprocess")

        runner = PyRunner(source=self.source,
                          args=self.args,
                          tracer_callbacks=[p[0].tracer_callback for _, p in Pipeline.plugins.items()
                                            if p[1] and hasattr(p[0], 'tracer_callback')],
                          logger=self.logger)
        runner.run()
        Pipeline.do_postprocess()
        self.logger.info("finish doing postprocess")

    def do_server(self):
        self.render_server.run()

    def prepare(self):
        self.fs.build()
        self.reporter.prepare()
        self.reporter.build_htmls()
        self.dispatcher.add_callable(self.do_process)
        self.dispatcher.add_callable(self.do_server)

    @classmethod
    def do_preprocess(cls):
        for key, (plugin, enabled) in cls.plugins.items():
            if enabled:
                assert hasattr(plugin, 'on_preprocess')
                plugin.on_preprocess()

    @classmethod
    def do_postprocess(cls):
        for key, (plugin, enabled) in cls.plugins.items():
            if enabled:
                assert hasattr(plugin, 'on_postprocess')
                plugin.on_postprocess()

    def run(self):
        self.prepare()
        self.dispatcher.dispatch()

    @classmethod
    def add_plugin(cls, enabled: bool = False):
        def _inner(plugin_cls: type(TPlugin)):
            plugin = plugin_cls()
            cls.plugins[plugin_cls.__name__] = ([plugin, enabled])
        return _inner

    @classmethod
    def enable_plugin(cls, plugin_cls_name: str) -> None:
        for _key, (_plugin, _enable) in cls.plugins.items():
            if _key == plugin_cls_name:
                cls.plugins[_key][1] = True
                return
        Logger.get_logger('engine.pipeline')\
            .warning(f"Cannot find target plugin {plugin_cls_name}")

    @classmethod
    def get_plugin(cls, plugin_cls_name: str) -> Optional[TPlugin]:
        for _key, (_plugin, _enable)  in cls.plugins.items():
            if _key == plugin_cls_name:
                return _plugin
        Logger.get_logger('engine')\
            .warning(f"Cannot find target plugin {plugin_cls_name}")
        return None

