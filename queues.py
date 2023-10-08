import queue
from dataclasses import dataclass, field

from typing import List, TypeVar, Any, Tuple, ClassVar

__all__ = ['TraceMessageEntry', 'ActionMessageEntry', 'Q']


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
    classsname: int
    file_classname: str
    cb_rts: str
    type: str = field(default='TraceMessage')

    def __repr__(self):
        return f"<TraceMessageEntry id={self.id} filename={self.filename} lineno={self.lineno} cb_rts={self.cb_rts}>"


@dataclass
class ActionMessageEntry(MessageEntry):
    id: int
    action: str
    value: str
    type: str = field(default='ActionMessage')

    def __repr__(self):
        return f"<ActionMessageEntry id={self.id} action={self.action} value={self.value}>"


T = TypeVar('T', bound=MessageEntry)


class MessageQueue(queue.Queue):
    _self_id: int = 0
    _get_id: int = -1

    queue: List[T]

    def _init(self, maxsize):
        self.queue = list()

    def _put(self, message_entry: T) -> None:
        message_entry.id = self._self_id
        self._self_id += 1
        self.queue.append(message_entry)

    def _get(self) -> T:
        return self.queue.pop(0)

    def _qsize(self) -> int:
        return len(self.queue)

    def clear(self):
        self._self_id = 0
        self.queue.clear()

    def __iter__(self):
        return self

    def __next__(self):
        try:
            return self.queue.pop(0)
        except IndexError:
            raise StopIteration
        

Q = MessageQueue()
