import os
import re
from os import PathLike
from typing import List, Tuple, Optional

import fileutils
from engine.logs import Log
from fs.models import Directory, File, Line


class FS:

    def __init__(self,
                 path: PathLike[str] | str,
                 exclude_dir: Optional[List[str]] = None,
                 exclude_file: Optional[List[str]] = None):
        self.path = os.path.abspath(os.fspath(path))
        self.exclude_dir = exclude_dir if exclude_dir is not None else []
        self.exclude_file = exclude_file if exclude_file is not None else []

    @staticmethod
    def _translate(pattern: str, case_sensitive=True):
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
        method for wildcard path matching

        :param pattern: matching pattern with `*` in it
        :param name: matched path
        :return: if it can be matched
        """
        res = "(?ms)" + self._translate(pattern) + r"\Z"
        re_pat = re.compile(res)
        return re_pat.match(name) is not None

    @staticmethod
    def _scanf_dir(path: str) -> Optional[Tuple[str, str]]:
        assert os.path.isabs(path)
        try:
            for info in os.listdir(path):
                yield path, info
        except Exception as e:
            Log.error(f'Fail to walk path {path}', e)
            return None

    @staticmethod
    def _inspect_file(file: str):
        assert os.path.isabs(file)
        _, ext = os.path.splitext(file)
        content = []
        if ext == '.py' or ext == '.pyw':
            for (lineno, line) in fileutils.read_source_py_with_line(file):
                content.append(Line(lineno=lineno, content=line))
        else:
            content.append(Line(lineno=1, content=fileutils.read_source(file)))
        return ext, content

    def build(self, root_dir: Directory):
        """
        build the whole file system with inited path, eg:

        ```
            fs = FS('..', exclude_dir=['.venv', '.git'])
            root_dir = Directory(dirname='..', content=[])
            fs.build(root_dir)
        ```
        :param root_dir: the given directory
        :return: None
        """
        assert root_dir is not None
        self.root = root_dir
        stack = [
            (self.path, root_dir)
        ]
        while len(stack) > 0:
            _parent_path, _dir = stack.pop(0)
            for _p, _d in self._scanf_dir(_parent_path):
                _short_d = _d
                _d = os.path.join(_p, _d)
                if os.path.isdir(_d):
                    if any([self.match(pattern, _d) or self.match(pattern, _short_d) for pattern in self.exclude_dir]):
                        continue
                    _new_dir = Directory(dirname=_d, content=[])
                    _dir.content.append(_new_dir)
                    stack.append((_d, _new_dir))
                elif os.path.isfile(_d):
                    if any(([self.match(pattern, _d) or self.match(pattern, _short_d) for pattern in
                             self.exclude_file])):
                        continue
                    _new_file = File(filename=_d)
                    _new_file.extension, _new_file.content = self._inspect_file(_d)
                    _dir.content.append(_new_file)
                else:
                    continue

    @staticmethod
    def _walk(root_dir: Directory):
        stack = [
            root_dir
        ]
        while len(stack) > 0:
            _d = stack.pop(0)
            if isinstance(_d, File):
                yield _d
            elif isinstance(_d, Directory):
                for _e in _d.content:
                    if isinstance(_e, File):
                        yield _e
                    elif isinstance(_e, Directory):
                        stack.append(_e)
                    else:
                        raise RuntimeError(f'Unknown File in Directory {_d!r}')
            else:
                raise RuntimeError(f'Unknown File {_d!r}')

    def find(self, path: PathLike) -> Directory | File | None:
        """
        find the Directory or File with given path. If not exists, it will return None.
        This method must be invoked after `build`

        :param path: given path
        :return: Directory, File or None
        """
        if self.root is None:
            raise RuntimeError("FS must be built before walking")
        path = os.fspath(path)
        path = os.path.abspath(path)
        stack = [
            self.root
        ]
        while len(stack) > 0:
            _d = stack.pop(0)
            if isinstance(_d, File):
                if _d.filename == path:
                    return _d
                else:
                    continue
            elif isinstance(_d, Directory):
                if _d.dirname == path:
                    return _d
                else:
                    for _e in _d.content:
                        stack.append(_e)
            else:
                raise RuntimeError(f'Unknown File {_d!r}')
        return None

    def walk(self, path: Optional[PathLike[str]] = None) -> File:
        """
        walk all files or directory in the fs. This method must be invoked after `build`.

        ```
            w = FS('..', exclude_dir=['.venv', '.git'])
            root_dir = Directory(dirname='..', content=[])
            w.build(root_dir)
            for _w in w.walk('path\to\file'):
                print(_w)
        ```

        :param path: Optional, the root directory for the walking if given.
        :return: File
        """
        if self.root is None:
            raise RuntimeError("FS must be built before walking")
        if path is not None:
            res = self.find(path)
            if res is None:
                raise RuntimeError(f"Given file path {path} is not found")
            if isinstance(res, File):
                return res
            else:
                for _res in self._walk(res):
                    yield _res
        else:
            for _res in self._walk(self.root):
                yield _res
