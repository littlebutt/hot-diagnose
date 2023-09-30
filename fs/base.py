import os
import re
from os import PathLike
from typing import List, Tuple, Optional, Generator, Any, Callable

import fileutils
from logs import Logger
from fs.models import Directory, File, Line
from typings import LoggerLike


IS_PYCACHE = lambda d: d.endswith('__pycache__')


class FS:
    """
    A file system used for caching traversed :class:`File` or :class:`Directory` with the given path

    Attributes:
        path: The given path to be traversed.
        exclude_dirs: The excluded directories. It also support wildcard matches.
        exclude_files: The excluded files. It also support wildcard matches.
        logger: The logger for logging information.
        root: The root node of the file system. It can be a :class:`File` node or :class:`Directory` node.
    """

    def __init__(self,
                 path: PathLike | str,
                 exclude_dir: Optional[List[str]] = None,
                 exclude_file: Optional[List[str]] = None,
                 logger: Optional['LoggerLike'] = None):
        self.path = os.path.abspath(os.fspath(path))
        self.exclude_dirs = exclude_dir if exclude_dir is not None else []
        self.exclude_files = exclude_file if exclude_file is not None else []
        if logger is None:
            logger = Logger.get_logger('fs')
        self.logger = logger

        self.root = None
        self.build()

    # Copied from https://github.com/nedbat/coveragepy
    def _translate(self, pattern: str, case_sensitive=True):
        if not case_sensitive:
            pattern = pattern.lower()
        i, n = 0, len(pattern)
        res = []
        while i < n:
            c = pattern[i]
            i = i + 1
            if c == "*":
                res.append("[^/]*")
            elif c == "?":
                res.append(".")
            elif c == "[":
                j = i
                if j < n and pattern[j] == "!":
                    j = j + 1
                if j < n and pattern[j] == "]":
                    j = j + 1
                while j < n and pattern[j] != "]":
                    j = j + 1
                if j >= n:
                    res.append("\\[")
                else:
                    stuff = pattern[i:j].replace("\\", "\\\\")
                    i = j + 1
                    if stuff[0] == "!":
                        stuff = "^" + stuff[1:]
                    elif stuff[0] == "^":
                        stuff = "\\" + stuff
                    res.append("[%s]" % stuff)
            else:
                res.append(re.escape(c))
        return "".join(res)

    def match(self, pattern: str, name: str) -> bool:
        """
        Check if the given ``name`` can be matched with the ``pattern``. If it can be matched, the :meth:`match` method
        will return :obj:`True` , otherwise :obj:`False`.

        Args:
            pattern: matching pattern with ``*`` in it
            name: matched path

        Returns:
            if it can be matched
        """
        res = "(?ms)" + self._translate(pattern) + r"\Z"
        re_pat = re.compile(res)
        return re_pat.match(name) is not None

    def _scanf_dir(self, path: PathLike | str) -> Optional[Tuple[str, str]]:
        assert os.path.isabs(path)
        try:
            for info in os.listdir(path):
                yield path, info
        except OSError:
            self.logger.error(f'Fail to walk path {path}', exc_info=True)
            return None

    def _inspect_file(self, file: PathLike | str):
        assert os.path.isabs(file)
        file = os.fspath(file)
        _, ext = os.path.splitext(file)
        content = list()
        if ext == '.py' or ext == '.pyw':
            for (lineno, line) in fileutils.read_source_py_with_line(file):
                content.append(Line(lineno=lineno, content=str(line, encoding='UTF-8'), filename=file))
        else:
            try:
                content.append(
                    Line(lineno=1, content=str(fileutils.read_source(file), encoding='utf-8'), filename=file))
            except UnicodeDecodeError:
                self.logger.warning(f"Fail to inspect file {file}, which may be a binary file", exc_info=True)
        return ext, content

    def build(self):
        """
        Try to build the whole file system with inited ``path``, eg::

            fs = FS('..', exclude_dir=['.foo', '.bar'])
            fs.build('..')

        The method must be called before :meth:`walk` and :meth:`find`

        Returns:
            None
        """
        if os.path.isfile(self.path):
            f = File(filename=self.path, basename=os.path.basename(self.path))
            f.extension, f.lines = self._inspect_file(self.path)
            self.root = f
            return f

        self.root = Directory(dirname=self.path, basename=os.path.basename(self.path), files_or_directories=[])
        # The stack for memoizing Directory node. When a directory is found and its children nodes (sub-directory or
        # sub-file) are not scaned yet, it will be cached into the stack temporarily. Commonly, the nodes in the stack
        # for one time are in the same layer.
        stack = [
            (self.path, self.root)
        ]
        while len(stack) > 0:
            _parent_path, _dir = stack.pop(0)
            for _p, _d in self._scanf_dir(_parent_path):
                # XXX: Store the relative path for a while.
                _short_d = _d
                _d = os.path.join(_p, _d)
                if os.path.isdir(_d) and not IS_PYCACHE(_d):
                    self.logger.info(f"FS.build: Scanning the directory {_d}")
                    # Exclude the directories in `exclude_dirs`
                    if any([self.match(pattern, _d)
                            or self.match(pattern, _short_d)
                            for pattern in self.exclude_dirs]):
                        self.logger.info(f"FS.build: The directory {_d} is excluded")
                        continue
                    _new_dir = Directory(dirname=_d, basename=_short_d, files_or_directories=[])
                    _dir.files_or_directories.append(_new_dir)
                    stack.append((_d, _new_dir))
                elif os.path.isfile(_d):
                    self.logger.info(f"FS.build: Scanning the file {_d}")
                    # Exclude the files in `exclude_files`
                    if any(([self.match(pattern, _d)
                             or self.match(pattern, _short_d)
                             for pattern in self.exclude_files])):
                        self.logger.info(f"FS.build: The file {_d} is excluded")
                        continue
                    _new_file = File(filename=_d, basename=os.path.basename(_d))
                    _new_file.extension, _new_file.lines = self._inspect_file(_d)
                    _dir.files_or_directories.append(_new_file)
                else:
                    self.logger.warning(f"FS.build: Unexpected target {_d}")
                    continue

    def _walk(self, root_dir: Directory, hook: Callable[[File | Directory], Any]) -> Generator[File, Any, Any]:
        stack = [
            root_dir
        ]
        while len(stack) > 0:
            _d = stack.pop(0)
            if isinstance(_d, File):
                self.logger.info(f"FS.walk: Walking the file {_d}")
                hook(_d)
                yield _d
            elif isinstance(_d, Directory):
                hook(_d)
                self.logger.info(f"FS.walk: Walking the directory {_d}")
                for _e in _d.files_or_directories:
                    if isinstance(_e, File):
                        self.logger.info(f"FS.walk: Walking the file {_e}")
                        hook(_e)
                        yield _e
                    elif isinstance(_e, Directory):
                        stack.append(_e)
                    else:
                        raise RuntimeError(f'Unknown File in Directory {_d!r}')
            else:
                raise RuntimeError(f'Unknown File {_d!r}')

    def find(self, path: PathLike | str) -> Directory | File | None:
        """
        Try to find the :class:`Directory` or :class:`File` with given ``path``. If it exists, the method will return
        it, otherwise :obj:`None`.

        Note that this method must be invoked after :meth:`build`

        Args:
            path: The given path.

        Returns:
            The object the method found.

        Raises:
            RuntimeError: The object is neither :class:`File` nor :class:`Directory` RuntimeError: The :class:`FS` was
            not built.
        """
        path = os.fspath(path)
        path = os.path.abspath(path)
        stack = [
            self.root
        ]
        while len(stack) > 0:
            _d = stack.pop(0)
            if isinstance(_d, File):
                self.logger.info(f"FS.find: Finding the file {_d}")
                if _d.filename == path:
                    return _d
                else:
                    continue
            elif isinstance(_d, Directory):
                self.logger.info(f"FS.find: Finding the directory {_d}")
                if _d.dirname == path:
                    return _d
                else:
                    for _e in _d.files_or_directories:
                        stack.append(_e)
            else:
                raise RuntimeError(f'Unknown File {_d!r}')
        return None

    def _wrap_hook(self, hook: Optional[Callable[[File | Directory], None]] = None):
        return lambda x: hook(x) if hook is not None else None

    def walk(self,
             path: Optional[PathLike[str]] = None,
             hook: Optional[Callable[[File | Directory], None]] = None) -> Generator[File, Any, Any]:
        """
        Walk all :class:`Directory` or :class:`File` in the :class:`FS`.

        This method must be invoked after :meth:`build`::

            w = FS('..')
            w.build()
            for _w in w.walk('path\\to\\file'):
                print(_w)

        Args:
            path: The root directory for the walking if given.
            hook: The hook function invoked when walking to a :class:`File` or :class:`Directory`.

        Return:
            Files

        Raises:
            RuntimeError: The :class:`FS` was not built
            RuntimeError: The given path is not found
        """
        hook = self._wrap_hook(hook)
        if path is not None:
            res = self.find(path)
            if res is None:
                raise RuntimeError(f"Given file path {path} is not found")
            if isinstance(res, File):
                return res
            else:
                yield from self._walk(res, hook=hook)
        else:
            yield from self._walk(self.root, hook=hook)


if __name__ == '__main__':
    fs = FS('.')
    for i in fs.walk():
        print(i)
