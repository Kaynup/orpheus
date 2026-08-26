"""Orpheus Application Package."""

import sys

# 1. Compatibility shim for sqlite3 with older Linux versions
try:
    __import__("pysqlite3")
    sys.modules["sqlite3"] = sys.modules.pop("pysqlite3")
except ImportError:
    pass

# 2. Compatibility shim for typing.NotRequired in Python 3.10
import typing
try:
    import typing_extensions
    if not hasattr(typing, "NotRequired"):
        typing.NotRequired = getattr(typing_extensions, "NotRequired", None)
    if not hasattr(typing, "Required"):
        typing.Required = getattr(typing_extensions, "Required", None)
except ImportError:
    pass

from app.version import __version__, __version_info__

__all__ = ["__version__", "__version_info__"]
