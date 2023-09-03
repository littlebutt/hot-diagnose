import concurrent.futures
import sys
from concurrent.futures import Future
from typing import Callable, Any, MutableSequence, Dict


class Dispatcher:

    def __init__(self,
                 callable_group: MutableSequence[Callable[[...], Any]] = [],
                 max_workers: int = 2,
                 **kwargs):
        self.pool_executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        self.callable_group = callable_group
        self.future_map: Dict[str, Future] = dict()

    def add_callable(self, _callable: Callable[[...], Any]):
        self.callable_group.append(_callable)

    def dispatch(self):
        with self.pool_executor as executor:
            for cb in self.callable_group:
                self.future_map.update({cb.__name__:
                                            executor.submit(cb)})
        for name, future in self.future_map.items():
            if exc := future.exception():
                raise exc
            while future.done():
                break
        sys.exit(-1)


