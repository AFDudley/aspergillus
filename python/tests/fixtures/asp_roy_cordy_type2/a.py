"""Fixture for asp-d88.2 acceptance clause c7.

Labeled for the Roy & Cordy (2007) type-2 editing-scenario taxonomy: a
type-2 clone (renamed identifiers, changed literals) produced by the
"statement insertion" editing scenario — extra statements added around the
copied core so the clone is no longer the whole function body.
"""


def summarize_a(rows):
    total = 0
    count = 0
    for row in rows:
        total += row.value
        count += 1
    average = total / count
    print("a summary computed")
    return average


def summarize_b(entries, label):
    total = 0
    count = 0
    for entry in entries:
        total += entry.value
        count += 1
    average = total / count
    print(label)
    log_summary(label, average)
    return average
