from typing import Any

from engine.manage import PluginManager
from logs import Logger
from typings import T_event, T_frame, TPlugin


@PluginManager.add_plugin(enabled=False)
class RedirectPlugin(TPlugin):

    def __init__(self, *args, **kwargs):
        self.filename = None

    def set_filename(self, filename: str) -> None:
        self.filename = filename

    def on_preprocess(self):
        Logger.redirect_to_file(self.filename, logger=Logger.get_logger('engine'))

    def on_postprocess(self):
        pass

    def tracer_callback(self, frame: T_frame, event: T_event, args: Any) -> Any:
        pass