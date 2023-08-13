import os.path


def read_source_py(filename: str) -> bytes: # also for pyw
    filename_base, filename_ext = os.path.splitext(filename)
    assert filename_ext == '.py' or filename_ext == '.pyw'
    if not os.path.exists(filename):
        raise IOError(f"Cannot find target filename: {filename}")
    with open(filename, "rb") as f:
        source = f.read()
    return source.replace(b"\r\n", b"\n").replace(b"\r", b"\n")