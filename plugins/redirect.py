import sys
from typing import Any, Optional

from engine import Pipeline
from typed import T_err, T_event, T_frame, T_out, TPlugin


@Pipeline.add_plugin(False)
class RedirectPlugin(TPlugin):

    def set_out(self, io_out: T_out) -> None:
        self.out = io_out

    def pre_process_hook(self):
        assert sys.stdout == sys.__stdout__
        assert sys.stderr == sys.__stderr__
        sys.stdout = self.out
        sys.stderr = self.out

    def post_process_hook(self):
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__
    
    def tracer_callback(self, frame: T_frame, event: T_event, args: Any) -> Optional[str]:
        pass