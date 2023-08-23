import queue
from dataclasses import dataclass, field

from typing import List, TypeVar, Any, Tuple, ClassVar

__all__ = ['TraceMessageEntry', 'DualMessageQueue', 'MessageQueue']


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
            self._get_id += 1
            yield self.queue[self._get_id]


class DualMessageQueue:
    request_queue: ClassVar[MessageQueue] = MessageQueue()
    response_queue: ClassVar[MessageQueue] = MessageQueue()

    @classmethod
    def put_request(cls, message_entry: T):
        cls.request_queue.put(message_entry)

    @classmethod
    def get_request(cls):
        return cls.request_queue.get()

    @classmethod
    def put_response(cls, message_entry: T):
        cls.response_queue.put(message_entry)

    @classmethod
    def get_response(cls):
        return cls.response_queue.get()

    @classmethod
    def size(cls)-> Tuple[int, int]:
        return cls.request_queue.qsize(), cls.response_queue.qsize()

    @classmethod
    def reset(cls):
        cls.request_queue.clear()
        cls.response_queue.clear()

    @classmethod
    def get_request_queue(cls):
        return cls.request_queue

    @classmethod
    def get_response_queue(cls):
        return cls.response_queue