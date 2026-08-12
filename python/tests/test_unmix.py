"""Tests for the unmix codemod — the program that removes what ASP206 reports.

The rule reports the entanglement. These tests assert the codemod removes
it where the removal is mechanical, and REFUSES by name where the split is
a design decision — never quietly, and never by moving an effect into the
core it just created.
"""

from __future__ import annotations

from aspergillus.codemods.unmix import (
    effect_closure,
    mixed_function_names,
    unmix_source,
)

_MIXED = (
    "import json\n"
    "import subprocess\n"
    "\n"
    "\n"
    "def read_report(path):\n"
    '    """Read and shape."""\n'
    "    proc = subprocess.run(['cat', path], capture_output=True, text=True)\n"
    "    data = json.loads(proc.stdout)\n"
    "    rows = [r for r in data if r > 0]\n"
    "    total = sum(rows) * 2\n"
    "    scaled = total // 3\n"
    "    label = 'big' if scaled > 10 else 'small'\n"
    "    return label, scaled\n"
)


def test_the_effects_stay_and_the_logic_moves() -> None:
    """The template: the shell keeps `subprocess.run`, the core takes the
    result as a parameter and holds every computing statement."""
    result = unmix_source(_MIXED)
    assert [lift.core_name for lift in result.lifts] == ["_read_report_core"]
    assert result.lifts[0].params == ("proc",)
    assert result.lifts[0].form == "suffix"
    assert "def _read_report_core(proc):" in result.source
    assert (
        "subprocess.run"
        not in result.source.split("def read_report")[0].split("def _read_report_core")[1]
    )
    assert "return _read_report_core(proc)" in result.source


def test_the_finding_the_codemod_answered_is_gone() -> None:
    """A conversion the rule does not agree with is not a conversion."""
    assert mixed_function_names(_MIXED) == ("read_report",)
    assert mixed_function_names(unmix_source(_MIXED).source) == ()


def test_the_shell_keeps_its_own_docstring() -> None:
    """A docstring performs no effect, so it opens the first pure run. Lifted
    with that run it leaves the shell undocumented and documents the core
    with prose about a function the core is not."""
    result = unmix_source(_MIXED)
    shell = result.source.split("def read_report(path):")[1]
    assert '"""Read and shape."""' in shell


def test_a_run_that_reaches_an_effect_is_refused_by_name() -> None:
    """`_find_io_calls` reads the call site, not the callee. Lifting a run
    that calls an effect-bearing helper would move the effect INTO the
    core, which is the opposite of the point."""
    source = (
        "import subprocess\n"
        "\n"
        "\n"
        "def emit(line):\n"
        "    print(line)\n"
        "\n"
        "\n"
        "def run(path):\n"
        "    proc = subprocess.run(['cat', path])\n"
        "    total = proc.returncode * 2\n"
        "    scaled = total // 3\n"
        "    label = 'big' if scaled > 1 else 'small'\n"
        "    emit(label)\n"
        "    return scaled > 0\n"
    )
    result = unmix_source(source)
    assert result.lifts == ()
    assert "emit" in result.refusals[0].reason
    assert result.source == source


def test_a_single_computing_statement_is_a_threshold_shave_and_is_refused() -> None:
    """ASP206 fires above three computing statements, so moving one out
    clears the finding while the boundary stays as mixed as it was. A count
    that falls because the detector stopped looking is the evasion."""
    source = (
        "import subprocess\n"
        "\n"
        "\n"
        "def run(path):\n"
        "    a = subprocess.run(['1', path])\n"
        "    x = a.returncode * 2\n"
        "    b = subprocess.run(['2', path])\n"
        "    y = b.returncode * 3\n"
        "    c = subprocess.run(['3', path])\n"
        "    z = c.returncode * 4\n"
        "    d = subprocess.run(['4', path])\n"
        "    w = x + y + z + d.returncode\n"
        "    return w\n"
    )
    assert mixed_function_names(source) == ("run",)
    result = unmix_source(source)
    assert result.lifts == ()
    assert "two computing statements" in result.refusals[0].reason


def test_logic_that_reads_self_is_refused() -> None:
    source = (
        "import subprocess\n"
        "\n"
        "\n"
        "class Runner:\n"
        "    def run(self, path):\n"
        "        proc = subprocess.run(['cat', path])\n"
        "        total = proc.returncode * 2\n"
        "        scaled = total + self.offset\n"
        "        label = 'big' if scaled > 1 else 'small'\n"
        "        return label, scaled > 0\n"
    )
    result = unmix_source(source)
    assert result.lifts == ()
    assert "self" in result.refusals[0].reason


def test_the_closure_reaches_an_effect_two_calls_away() -> None:
    """A caller of a caller of an effect is effect-bearing. The census
    reports only the direct call, so the closure is what the guard needs."""
    source = (
        "def writes(path):\n"
        "    path.write_text('x')\n"
        "\n"
        "\n"
        "def calls_writes(path):\n"
        "    writes(path)\n"
        "\n"
        "\n"
        "def calls_that(path):\n"
        "    calls_writes(path)\n"
        "\n"
        "\n"
        "def pure(a):\n"
        "    return a + 1\n"
    )
    closure = effect_closure({"m.py": source})
    assert {"writes", "calls_writes", "calls_that"} <= closure
    assert "pure" not in closure


def test_a_filesystem_probe_is_an_effect_for_the_codemod() -> None:
    """`io_blocklist` cannot grow without changing what ASP202 and ASP206
    measure, and the census must reproduce ASP205 exactly. The codemod has
    the other job, so it guards on the wider list."""
    assert "is_dir" in effect_closure({})
    assert "exists" in effect_closure({})
