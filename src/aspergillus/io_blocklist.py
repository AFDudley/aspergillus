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
