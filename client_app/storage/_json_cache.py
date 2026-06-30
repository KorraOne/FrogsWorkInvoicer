"""In-memory JSON file cache keyed by mtime."""

import copy
import os

_json_cache = {}


def _file_mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


def cached_read(path, loader):
    mtime = _file_mtime(path)
    entry = _json_cache.get(path)
    if entry and entry[0] == mtime:
        return copy.deepcopy(entry[1])
    data = loader()
    _json_cache[path] = (mtime, data)
    return copy.deepcopy(data)


def invalidate(path):
    _json_cache.pop(path, None)
