"""Known I/O functions for purity detection (ASP205, ASP206).

This is a heuristic blocklist. Purity is undecidable in general, but
matching calls against known I/O functions covers ~90% of real cases.
"""

from __future__ import annotations

# Fully qualified names and common short forms.
# ASP205/206 match if any call in a function body resolves to one of these.
IO_FUNCTIONS: frozenset[str] = frozenset(
    {
        # builtins
        "print",
        "input",
        "open",
        # subprocess
        "subprocess.run",
        "subprocess.call",
        "subprocess.check_call",
        "subprocess.check_output",
        "subprocess.Popen",
        # urllib
        "urllib.request.urlopen",
        "urllib.request.build_opener",
        # os filesystem
        "os.system",
        "os.popen",
        "os.remove",
        "os.unlink",
        "os.mkdir",
        "os.makedirs",
        "os.rename",
        "os.rmdir",
        # os.path is pure — intentionally excluded
        # logging
        "logging.info",
        "logging.warning",
        "logging.error",
        "logging.debug",
        "logging.critical",
        "logging.exception",
        "log.info",
        "log.warning",
        "log.error",
        "log.debug",
        "log.critical",
        "log.exception",
        # shutil
        "shutil.copy",
        "shutil.copy2",
        "shutil.copytree",
        "shutil.move",
        "shutil.rmtree",
        # socket
        "socket.socket",
        # pathlib write operations
        "Path.write_text",
        "Path.write_bytes",
        "Path.read_text",
        "Path.read_bytes",
        "Path.unlink",
        "Path.mkdir",
        "Path.rmdir",
        "Path.rename",
        "Path.touch",
    }
)

# Bare method names that are I/O regardless of receiver type.
# Without type resolution, `path_obj.read_text()` resolves to
# `path_obj.read_text` — never matching `Path.read_text` in
# IO_FUNCTIONS. These names are unambiguously I/O on any object.
#
# `rename` is the one collision-prone name: pandas `DataFrame.rename` /
# `Series.rename` are pure in-memory transforms. The bare-name match is
# kept (so instance-form `Path.rename(target)` still counts) but the
# pandas shapes are excluded by `_is_pandas_rename` in `rules/level2.py`
# (`columns=`/`index=`/… kwargs, or a computed receiver). See asp-108.
IO_METHOD_NAMES: frozenset[str] = frozenset(
    {
        "read_text",
        "write_text",
        "read_bytes",
        "write_bytes",
        "urlopen",
        "build_opener",
        "unlink",
        "mkdir",
        "rmdir",
        "rename",
        "touch",
    }
)
