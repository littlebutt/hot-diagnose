import concurrent.futures
from concurrent.futures import Future
from typing import Callable, Any, Dict


class Dispatcher:

    def __init__(self,
                 max_workers: int = 2,):
        self.pool_executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        self.callable_group = list()
        self.future_map: Dict[str, Future] = dict()

    def add_callable(self, _callable: Callable[[...], Any]):
        self.callable_group.append(_callable)

    def dispatch(self):
        with self.pool_executor as executor:
            for cb in self.callable_group:
                self.future_map.update({cb.__name__:
                                        executor.submit(cb)})
