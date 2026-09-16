"""Acceptance oracle for asp-d88.2 clause c2: normalizer unchanged.

Emits ONE observation: whether two functions that differ only in variable
names and literal values still hash equal under the normalizer -- exactly
as before this pebble's fragment-granular change. Judges nothing -- the
spec's ``then`` predicate owns the verdict.
"""

from __future__ import annotations

import json

from aspergillus.duplicates import extract_function_records

_A = """
def fetch(repo, name):
    result = run(["git", "-C", repo, name], check=True)
    return result.stdout.strip()
"""
_B = """
def pull(project, arg):
    outcome = run(["git", "-C", project, arg], check=True)
    return outcome.stdout.strip()
"""


def main() -> None:
    (record_a,) = extract_function_records(_A, "a.py")
    (record_b,) = extract_function_records(_B, "b.py")
    print(json.dumps({"hashes_equal": record_a.normalized_hash == record_b.normalized_hash}))


if __name__ == "__main__":
    main()
