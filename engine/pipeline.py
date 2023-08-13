from typing import List, Optional, Callable
import threading

from engine.run import PyRunner


class Pipeline:

    def __init__(self, sources: List[str], args: List[str], current_path: str, tracer_callback: Optional[Callable]):
        self.sources = sources
        self.args = args
        self.current_path = current_path
        self.tracer_callback = tracer_callback

    def pre_process_hook(self):
        pass

    def post_process_hook(self):
        pass

    def run(self):

        # def _run(source: str, args: List[str]):
        #     runner = PyRunner(source=source, args=args, target_is_dir=False)
        #     runner.run()

        self.pre_process_hook()

        # for source in self.sources:
        #     thread = threading.Thread(target=_run, args=[source, self.args])
        #     thread.run()
        runner = PyRunner(source=self.sources[0], args=self.args,
                          target_is_dir=False, current_path=self.current_path, tracer_callback=self.tracer_callback)
        runner.run()
        self.post_process_hook()

