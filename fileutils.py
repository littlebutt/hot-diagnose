import hashlib
import ntpath
import os.path
import pathlib
import re
from os import PathLike
from typing import Tuple


def read_source_py(filename: str) -> bytes:  # also for pyw
    filename_base, filename_ext = os.path.splitext(filename)
    assert filename_ext == '.py' or filename_ext == '.pyw'
    if not os.path.exists(filename):
        raise IOError(f"Cannot find target filename: {filename}")
    with open(filename, 'rb') as f:
        source = f.read()
    return source.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def read_source(filename: str) -> bytes:
    if not os.path.exists(filename):
        raise IOError(f"Cannot find target filename: {filename}")
    with open(filename, 'rb') as f:
        source = f.read()
    return source.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def read_source_py_with_line(filename: str) -> Tuple[int, str]:
    filename_base, filename_ext = os.path.splitext(filename)
    assert filename_ext == '.py' or filename_ext == '.pyw'
    if not os.path.exists(filename):
        raise IOError(f"Cannot find target filename: {filename}")
    lineno = 0
    with open(filename, 'rb') as f:
        while line := f.readline():
            lineno += 1
            yield lineno, line


# Copied from https://github.com/nedbat/coveragepy
def flat_filename(filename: PathLike | str):
    filename = os.fspath(filename)
    dirname, basename = ntpath.split(filename)
    if dirname:
        fp = hashlib.new('sha3_256', dirname.encode('UTF-8')).hexdigest()[:16]
        prefix = f'f_{fp}_'
    else:
        prefix = ''
    return prefix + basename.replace('.', '_')


def flat_dirname(dirname: PathLike | str):
    dirname = os.fspath(dirname)
    fp = hashlib.new('sha3_256', dirname.encode('UTF-8')).hexdigest()[:16]
    return 'd_' + fp


def get_home_dir() -> str:
    return str(pathlib.Path.home())


def mkdir(location: PathLike | str, dirname: str):
    path = os.path.join(location, dirname)
    if os.path.exists(path):
        return path
    os.mkdir(path)
    return path


def write_file(filename: str, content: str | bytes):
    content = re.sub(r"(\A\s+)|(\s+$)", "", content, flags=re.MULTILINE) + "\n"
    with open(filename, "wb") as fout:
        fout.write(content.encode("ascii", "xmlcharrefreplace"))


def generate_classname(full_pathname: str, lineno: int):
    assert os.path.isabs(full_pathname) and isinstance(lineno, int)
    return hash(full_pathname) + hash(lineno)

