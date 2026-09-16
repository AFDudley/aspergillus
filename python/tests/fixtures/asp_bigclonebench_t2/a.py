"""Fixture for asp-d88.2 acceptance clause c9.

Labeled for the BigCloneBench (Svajlenko et al. 2014) T2 category: two
functions syntactically identical apart from identifier renames and literal
value changes -- a whole-body type-2 clone.
"""


def compute_checksum(data, seed):
    total = seed
    for byte in data:
        total = (total * 31 + byte) % 65521
    return total


def compute_digest(payload, start):
    total = start
    for octet in payload:
        total = (total * 31 + octet) % 65521
    return total
