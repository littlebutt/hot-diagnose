import sys
from typing import Any, Optional

from engine import Pipeline
from queues import MessageQueue
from typed import T_event, T_frame, TPlugin


@Pipeline.add_plugin(False)
class RedirectPlugin(TPlugin):

    def set_out(self, out_path: str) -> None:
        self.file_handler = open(out_path, 'w')
        self.out = self.file_handler

    def pre_process_hook(self):
        assert sys.stdout == sys.__stdout__
        assert sys.stderr == sys.__stderr__
        sys.stdout = self.out
        sys.stderr = self.out

    def post_process_hook(self):
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__
        self.file_handler.close()

    def tracer_callback(self, frame: T_frame, event: T_event, args: Any, mq: 'MessageQueue') -> Optional[str]:
        pass