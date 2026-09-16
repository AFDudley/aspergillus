"""Fixture for asp-d88.2 acceptance clause c8.

Labeled for the Bellon et al. (2007) reference-clone benchmark: a
validate-then-normalize routine copy-pasted into two callers, each wrapping
the shared core in its own setup/teardown code — the kind of real-world
type-2 clone Bellon's tool comparison catalogued.
"""


def parse_widget(cleaned):
    return cleaned


def import_widget(raw, source):
    if raw is None:
        raise ValueError("missing widget")
    cleaned = raw.strip()
    if not cleaned:
        raise ValueError("empty widget")
    widget = parse_widget(cleaned)
    return widget


def import_gadget(raw, source, retries):
    attempt = 0
    if raw is None:
        raise ValueError("missing widget")
    cleaned = raw.strip()
    if not cleaned:
        raise ValueError("empty widget")
    widget = parse_widget(cleaned)
    return widget, attempt
