import os
from typing import Mapping, Tuple, cast

import fileutils
from fs.models import Directory, File
from fs.typings import HTML_text, HTML_classname, HTML_href


def convert_directory_to_context(directory: Directory) -> Mapping[str, Tuple[HTML_text, HTML_classname, HTML_href]]:
    context = dict()
    for content in directory.files_or_directories:
        if isinstance(content, File):
            content = cast(File, content)
            f_hash = fileutils.flat_filename(content.filename)
            context[f_hash] = (os.path.basename(content.filename), f_hash, f_hash + '.html')
        elif isinstance(content, Directory):
            content = cast(content, Directory)
            d_hash = fileutils.flat_dirname(content.dirname)
            context[d_hash] = (os.path.basename(content.dirname), d_hash, d_hash + '.html')
    return context


def convert_directory_to_title(directory: Directory) -> str:
    return fileutils.flat_dirname(directory.dirname) + '.html'


def convert_file_to_context(file: File) -> Mapping[str, Tuple[HTML_text, HTML_text, HTML_classname]]:
    context = dict()
    for line in file.lines:
        context[line.lineno] = (line.lineno, line.content, 'c_' + line.lineno)
    return context


def convert_file_to_title(file: File) -> str:
    return fileutils.flat_filename(file.filename) + '.html'

