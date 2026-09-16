"""Fixture for asp-d88.2 acceptance clause c5 (boilerplate exclusion).

Alpha and Beta share a trivial pass-only __init__ and a one-line getter,
verbatim identical after normalization. Neither must be reported as a
duplicate.
"""


class Alpha:
    def __init__(self):
        pass

    def name(self):
        return self._name


class Beta:
    def __init__(self):
        pass

    def name(self):
        return self._name
