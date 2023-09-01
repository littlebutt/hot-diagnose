from typing import Any, Optional

from engine import Pipeline
from logs import Logger
from typings import T_event, T_frame, TPlugin


@Pipeline.add_plugin(False)
class RedirectPlugin(TPlugin):

    def set_out(self, filename: str) -> None:
        self.filename = filename

    def on_preprocess(self):
        Logger.redirect_to_file(self.filename,
                                logger=Logger.get_logger('engine'))

    def on_postprocess(self):
        pass

    def tracer_callback(self, frame: T_frame, event: T_event, args: Any) \
            -> Optional[str]:
        pass