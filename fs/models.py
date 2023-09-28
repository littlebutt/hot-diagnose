import os
from abc import ABC
from dataclasses import dataclass, field
from os import PathLike
from typing import List, Union, Any

__all__ = ['Path', 'Line', 'File', 'Directory']

import fileutils


@dataclass
class Path(PathLike, ABC):
    _path: str

    def __fspath__(self) -> Any:
        return self._path


@dataclass
class Line:
    filename: str  # abs filename
    content: str
    lineno: int

    def __repr__(self):
        return f'<Line content={self.content} lineno={self.lineno} filename={self.filename}>'

    def __str__(self):
        return self.content

    def __hash__(self):
        """
        Generate the hash of the :class:`Line`.

        The hash can be used as the classname of the element for a line in code when rendered in the HTML file. Note
        that this magic method :meth:`__hash__` will return a string as a hash rather than an int.

        Returns:
            str: The hash of the :class:`line`.
        """

        # XXX: Hack to the megic method __hash__ and make it returns a string rather than an int.
        return fileutils.generate_classname(self.filename, self.lineno)


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

    def __hash__(self):
        hash(self.filename)
        return hash(self.filename)


@dataclass
class Directory:
    dirname: PathLike | str
    basename: str
    files_or_directories: List[Union['File', 'Directory']] = field(default_factory=list)

    def __repr__(self):
        return f'<Directory dirname={os.fspath(self.dirname)}>'

    def __str__(self):
        return self.__repr__()

    def __hash__(self):
        base = hash(self.dirname)
        for target in self.files_or_directories:
            base += hash(target)
        return base
