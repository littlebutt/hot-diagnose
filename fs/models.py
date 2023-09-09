import os
from abc import ABC
from dataclasses import dataclass, field
from os import PathLike
from typing import List, Union, Any

__all__ = ['Path', 'Line', 'File', 'Directory']


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
        return self.content


@dataclass
class File:
    filename: PathLike | str
    basename: str
    extension: str | None = field(default_factory=str)
    lines: List['Line'] = field(default_factory=list)

    def __repr__(self):
        return f'<File filename={os.fspath(self.filename)} extension={self.extension}>'

    def __str__(self):
        return ''.join([line.content for line in self.lines])


@dataclass
class Directory:
    dirname: PathLike | str
    files_or_directories: List[Union['File', 'Directory']] = field(default_factory=list)

    def __repr__(self):
        return f'<Directory dirname={os.fspath(self.dirname)}>'

    def __str__(self):
        return self.__repr__()
