"""Regression fixture for asp-d88.2 acceptance clause c6.

Approximates the shape originally observed in exophial3's
src/e_new_model/shell/drive.py:drive versus driver.py:put: an identical inner
closure plus an identical call, plus a duplicated statement sequence,
embedded in two structurally different functions. The old whole-body hash
detector reported 'no duplicate functions found' for this pair, because
drive and put diverge at the start and the end.
"""

import subprocess


def drive(cfg, worktree):
    def _run(cmd):
        result = subprocess.run(cmd, cwd=worktree, check=True, capture_output=True)
        return result.stdout.decode()

    branch = cfg.branch
    _run(["git", "checkout", branch])

    output = _run(["git", "status", "--short"])
    if output.strip():
        raise RuntimeError("dirty worktree")

    return branch
