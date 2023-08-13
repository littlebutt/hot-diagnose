import datetime
import enum
import traceback
from typing import ClassVar, Optional


class LogLevel(enum.Enum):
    FATAL = 0
    ERROR = 1
    WARNING = 2
    INFO = 3
    DEBUG = 4
    TRACE = 5


class LogColor(enum.Enum):
    RED = 31
    GREEN = 32
    YELLOW = 33
    DEFAUT = 38


class Log:

    # TODO: log_level set
    log_level: ClassVar[LogLevel] = LogLevel.INFO

    @classmethod
    def _log(cls, message: str, color: LogColor) -> None:
        now = datetime.datetime.now()
        print(f'\033[{color.value}m[{now.strftime("%Y-%m-%d %H:%M:%S")}]{message}\033[0m')

    @classmethod
    def warn(cls, message: str) -> None:
        if cls.log_level.value < 2:
            return
        cls._log(message, LogColor.YELLOW)

    @classmethod
    def info(cls, message: str) -> None:
        if cls.log_level.value < 3:
            return
        cls._log(message, LogColor.DEFAUT)

    @classmethod
    def error(cls, message: str, e: Optional[Exception]) -> None:
        if cls.log_level.value < 1:
            return
        cls._log(message + f" Caused by {e if e is not None else '' !r}", LogColor.RED)
        traceback.print_exc()
