"""Small filesystem helpers shared by the whole firmware.

ROOT is "" on the device (paths are absolute from /), tests point it at a temp dir.
"""
import os

ROOT = ""


def p(path):
    """Map a device path like /config.json to the real location."""
    if not path.startswith("/"):
        path = "/" + path
    return ROOT + path


def exists(path):
    try:
        os.stat(p(path))
        return True
    except OSError:
        return False


def is_dir(path):
    try:
        return os.stat(p(path))[0] & 0x4000 != 0
    except OSError:
        return False


def makedirs(path):
    """mkdir -p for a *directory* path."""
    cur = ""
    for part in path.strip("/").split("/"):
        if not part:
            continue
        cur += "/" + part
        if not exists(cur):
            os.mkdir(p(cur))


def parent(path):
    i = path.rfind("/")
    return path[:i] if i > 0 else "/"


def remove(path):
    try:
        os.remove(p(path))
    except OSError:
        pass


def commit(tmp, path, backup=None):
    """Move tmp over path; the old file moves to `backup` if given."""
    if exists(path):
        if backup:
            remove(backup)
            os.rename(p(path), p(backup))
        else:
            remove(path)
    os.rename(p(tmp), p(path))


def write_atomic(path, data, backup=None):
    """Write to path.tmp, then rename over path (old file -> backup if given).

    A power cut leaves either the old file, or (between the two renames) the backup.
    """
    makedirs(parent(path))
    tmp = path + ".tmp"
    mode = "wb" if isinstance(data, (bytes, bytearray)) else "w"
    with open(p(tmp), mode) as f:
        f.write(data)
    commit(tmp, path, backup)


def free_bytes():
    try:
        st = os.statvfs(p("/") if ROOT else "/")
        return st[0] * st[3]
    except (OSError, AttributeError):
        return 1 << 30


def read_text(path):
    with open(p(path)) as f:
        return f.read()


def walk(path="/"):
    """Yield (path, size) for every file below path."""
    try:
        names = os.listdir(p(path))
    except OSError:
        return
    for n in sorted(names):
        full = (path.rstrip("/") + "/" + n)
        if is_dir(full):
            for item in walk(full):
                yield item
        else:
            yield full, os.stat(p(full))[6]
