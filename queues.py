import queue

from typing import List


class MessageEntry:

    def __init__(self, id: int, filename: str, lineno: int, cb_rts: str):
        self.id = id
        self.filename = filename
        self.lineno = lineno
        self.cb_rts = cb_rts

    def __repr__(self):
        return f"<MessageEntry id={self.id} filename={self.filename} lineno={self.lineno} cb_rts={self.cb_rts}>"

    def __str__(self):
        return self.__repr__()


class MessageQueue(queue.Queue):

    _self_id: int = 0
    _get_id: int = -1

    queue: List['MessageEntry']

    def _init(self, maxsize):
        self.queue = []

    def _put(self, message_entry: 'MessageEntry') -> None:
        message_entry.id = self._self_id
        self._self_id += 1
        self.queue.append(message_entry)

    def _get(self) -> 'MessageEntry':
        assert self._get_id < self._self_id
        self._get_id += 1
        return self.queue[self._get_id]

    def _qsize(self) -> int:
        return self._self_id - self._get_id - 1

    def play_back(self):
        self._get_id = -1

    def clear(self):
        self._get_id = -1
        self._self_id = 0
        self.queue.clear()

    def enumerate(self):
        while self._get_id < self._self_id - 1:
            self._self_id += 1
            yield self.queue[self._self_id]

