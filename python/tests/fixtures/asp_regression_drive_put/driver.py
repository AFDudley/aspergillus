"""Regression fixture for asp-d88.2 acceptance clause c6. See drive.py."""

import subprocess


def put(cfg, worktree):
    def _run(cmd):
        result = subprocess.run(cmd, cwd=worktree, check=True, capture_output=True)
        return result.stdout.decode()

    ref = cfg.ref
    _run(["git", "fetch", ref])

    output = _run(["git", "status", "--short"])
    if output.strip():
        raise RuntimeError("dirty worktree")

    status = _run(["git", "rev-parse", "HEAD"])
    return status
