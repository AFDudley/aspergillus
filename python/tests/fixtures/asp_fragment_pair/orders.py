"""Fixture for asp-d88.2 acceptance clause c1 (fragment-granular detection).

process_orders and process_items share an inner helper and a duplicated
statement block, but the surrounding code differs, so their whole bodies do
not hash equal. Only fragment-granular matching catches this pair.
"""


def process_orders(orders):
    def _clean(x):
        return x.strip().lower()

    total = 0
    for order in orders:
        name = _clean(order.name)
        total += order.amount
    return total, name


def process_items(items, tax_rate):
    def _clean(y):
        return y.strip().lower()

    total = 0
    for item in items:
        name = _clean(item.name)
        total += item.amount
    total *= 1 + tax_rate
    return total, name
