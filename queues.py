import queue
from dataclasses import dataclass, field

from typing import List, TypeVar, Any, Tuple

__all__ = ['TraceMessageEntry', 'DualMessageQueue']


class MessageEntry:

    type: str

    def __str__(self):
        return self.__repr__()

    def __getitem__(self, item):
        return self.__getattribute__(item)


@dataclass
class TraceMessageEntry(MessageEntry):
    id: int
    filename: str
    lineno: int
    cb_rts: str
    type: str = field(default='TraceMessage')

    def __repr__(self):
        return f"<TraceMessageEntry id={self.id} filename={self.filename} lineno={self.lineno} cb_rts={self.cb_rts}>"


class ActionMessageEntry(MessageEntry):
    id: int
    action: str
    value: str
    type = field(default='ActionMessage')

    def __repr__(self):
        return f"<ActionMessageEntry id={self.id} action={self.action} value={self.value}>"


T = TypeVar('T', bound=MessageEntry)

class MessageQueue(queue.Queue):

    _self_id: int = 0
    _get_id: int = -1

    queue: List[T]

    def _init(self, maxsize):
        self.queue = []

    def _put(self, message_entry: T) -> None:
        message_entry.id = self._self_id
        self._self_id += 1
        self.queue.append(message_entry)

    def _get(self) -> T:
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


class DualMessageQueue:
    request_queue: MessageQueue
    response_queue: MessageQueue

    def __init__(self):
        self.request_queue = MessageQueue()
        self.response_queue = MessageQueue()

    def put_request(self, message_entry: T):
        self.request_queue.put(message_entry)

    def get_request(self):
        return self.request_queue.get()

    def put_response(self, message_entry: T):
        self.response_queue.put(message_entry)

    def get_response(self):
        return self.response_queue.get()

    def size(self)-> Tuple[int, int]:
        return self.request_queue.qsize(), self.response_queue.qsize()

    def reset(self):
        self.request_queue.clear()
        self.response_queue.clear()

    def get_request_queue(self):
        return self.request_queue

    def get_response_queue(self):
        return self.response_queue