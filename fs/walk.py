import os
from os import PathLike
from typing import List, Literal, Tuple, Optional

from engine.logs import Log
from fs.models import Directory, File


class Walker:

    def __init__(self, path: PathLike[str] | str, exclude_dir: Optional[List[str]] = None, exclude_file: Optional[List[str]] = None):
        self.path = os.path.abspath(os.fspath(path))
        self.exclude_dir = exclude_dir
        self.exclude_file = exclude_file

    @staticmethod
    def _scanf_dir(path: str) -> Optional[Tuple[str, str]]:
        assert os.path.isabs(path)
        try:
            for info in os.listdir(path):
                yield path, info
        except Exception as e:
            Log.error(f'Fail to walk path {path}', e)
            return None

    def walk(self, root_dir: Directory):
        stack = [
            (self.path, root_dir)
        ]
        while len(stack) > 0:
            _parent_path, _dir = stack.pop(0)
            for _p, _d in self._scanf_dir(_parent_path):
                _d = os.path.join(_p, _d)
                if os.path.isdir(_d):
                    _new_dir = Directory(dirname=_d, content=[])
                    _dir.content.append(_new_dir)
                    stack.append((_d, _new_dir))
                elif os.path.isfile(_d):
                    _new_file = File(filename=_d)
                    _dir.content.append(_new_file)
                else:
                    continue

if __name__ == '__main__':
    w = Walker('..')
    root_dir = Directory(dirname='..', content=[])
    w.walk(root_dir)
    print(root_dir)

