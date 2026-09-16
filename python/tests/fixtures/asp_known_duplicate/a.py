"""Fixture for asp-d88.2 acceptance clauses c3/c4 (label + similarity score).

fetch_a and fetch_b are a plain whole-body type-2 clone: identical up to
identifier renaming, nothing else changed.
"""

from subprocess import run


def fetch_a(repo, name):
    result = run(["git", "-C", repo, name], check=True)
    return result.stdout.strip()


def fetch_b(project, arg):
    outcome = run(["git", "-C", project, arg], check=True)
    return outcome.stdout.strip()
