import os
from abc import ABC
from dataclasses import dataclass, field
from os import PathLike
from typing import List, Union, Any

__all__ = ['Line', 'File', 'Directory']


@dataclass
class Path(PathLike, ABC):

    _path: str

    def __fspath__(self) -> Any:
        return self._path


@dataclass
class Line:
    content: str
    lineno: int

    def __repr__(self):
        return f'<Line content={self.content} lineno={self.lineno}>'

    def __str__(self):
        return self.content.strip()


@dataclass
class File:
    filename: PathLike[str]
    extension: str | None = field(default_factory=str)
    content: List['Line'] = field(default_factory=list)

    def __repr__(self):
        return f'<File filename={os.fspath(self.filename)} ' \
               f'extension={self.extension}>'

    def __str__(self):
        return self.__repr__()


@dataclass
class Directory:
    dirname: PathLike[str]
    content: List[Union['File', 'Directory']] = field(default_factory=list)

    def __repr__(self):
        return f'<Directory dirname={os.fspath(self.dirname)}>'

    def __str__(self):
        return self.__repr__()