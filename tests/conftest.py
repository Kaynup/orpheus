"""Pytest configuration and environment shims."""

import sys
import typing
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

# Ensure sqlite3 shim
try:
    __import__("pysqlite3")
    sys.modules["sqlite3"] = sys.modules.pop("pysqlite3")
except ImportError:
    pass

# Ensure typing_extensions shim for python 3.10

try:
    import typing_extensions

    if not hasattr(typing, "NotRequired"):
        typing.NotRequired = getattr(typing_extensions, "NotRequired", None)
    if not hasattr(typing, "Required"):
        typing.Required = getattr(typing_extensions, "Required", None)
except ImportError:
    pass
