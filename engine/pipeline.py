import os.path
from typing import List, Optional

import fileutils
from engine.dispatch import Dispatcher
from engine.report import Reporter
from engine.run import PyRunner
from fs import FS
from fs import Path
from logs import Logger
from server import RenderServer
from typings import LoggerLike
from engine.manage import PluginManager


class Pipeline:

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
        self.reporter = Reporter(self.fs, os.path.join(fileutils.get_package_dir(), f'server{os.path.sep}templates'), logger=self.logger)

    def do_process(self):
        Pipeline.do_preprocess()
        self.logger.info("finish doing preprocess")

        runner = PyRunner(source=self.source,
                          args=self.args,
                          tracer_callbacks=[p.plugin.tracer_callback for _, p in PluginManager.plugins.items()
                                            if p.plugin and hasattr(p.plugin, 'tracer_callback')],
                          logger=self.logger)
        runner.run()
        Pipeline.do_postprocess()
        self.logger.info("finish doing postprocess")

    def do_server(self):
        self.render_server.run()

    def prepare(self):
        self.reporter.prepare()
        self.reporter.build_htmls()
        self.reporter.report()
        self.dispatcher.add_callable(self.do_process)
        self.dispatcher.add_callable(self.do_server)

    @classmethod
    def do_preprocess(cls):
        for name, disc in PluginManager.plugins.items():
            if disc.enable:
                assert hasattr(disc.plugin, 'on_preprocess')
                disc.plugin.on_preprocess()

    @classmethod
    def do_postprocess(cls):
        for name, disc in PluginManager.plugins.items():
            if disc.enable:
                assert hasattr(disc.plugin, 'on_postprocess')
                disc.plugin.on_postprocess()

    def run(self):
        self.prepare()
        self.dispatcher.dispatch()
