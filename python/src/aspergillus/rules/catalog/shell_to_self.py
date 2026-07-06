"""ASP409: shell-to-self — invoking your own package via subprocess.

Verification-integrity family; sibling to ASP408 anti-special-casing.
Where ASP408 guards against special-casing the value under test, ASP409
guards the *seam*: it flags implementation code that reaches its own
importable code through a subprocess (argv in, exit code out) instead of
importing the function and calling it.

**Ships without autofix** (Tier 2, detection-only, per
``aspergillus/docs/decisions/2026-05-19-severity-graduation.md`` and
``docs/decisions/2026-05-19-mtm-past-warn-promotion-phase.md``). Lands at
**warn** and promotes to error once the tree is clean, per the
severity-graduation workflow. The fix — which function to import and how
to call it — requires human/agent judgment, so the rule reports the
opportunity without a ``replacement=``.

Type-level rationale
--------------------
``argv -> int`` is not a function; ``(T) -> U`` is. A subprocess boundary
to your OWN code erases the types at the seam: the caller marshals typed
values into a list of strings, the callee re-parses those strings back
into values, and the only thing that crosses the process line is an
exit code plus whatever text lands on stdout. Every guarantee the type
checker gives you inside the process is dropped at that boundary and must
be re-established by hand on the far side. A stringly-typed seam drifts
(the argv contract is unchecked and rots), and it can be pointed
elsewhere (nothing pins ``sys.executable -m yourpkg`` to *this* checkout
of yourpkg). Import the function and call it: the types hold, the call
graph is legible to tooling, and refactors are mechanical.

What is a smell vs. what is fine
--------------------------------
The line is ownership. Running your OWN library code out-of-process is
the smell. Running an EXTERNAL tool, or the ARTIFACT UNDER TEST, is fine:

- External tools (``git``, ``uv``, ``docker``, ``pb``, ``gh``, ``pytest``
  as a CLI) have no importable-function equivalent in this codebase;
  a subprocess is the only interface they expose.
- ``python -m build`` / ``python -m pip`` / ``python -m pytest`` and
  other stdlib/dependency modules are dependencies, not the project.
- The artifact under test (a built binary, a compiled emitter exercised
  end-to-end) legitimately MUST run out of process — that IS the thing
  being verified.

Detection
---------
Recognised subprocess spawners: ``subprocess.run`` / ``.Popen`` /
``.check_output`` / ``.check_call`` / ``.call``, and
``asyncio.create_subprocess_exec`` / ``create_subprocess_shell``; plus
the distinctive bare names ``Popen`` / ``check_output`` / ``check_call``
/ ``create_subprocess_exec`` (from-import forms). Ambiguous bare
``run`` / ``call`` are intentionally NOT matched — too many unrelated
functions share those names to stay high-signal.

From the resolved argv (the list literal for ``subprocess.*``, or the
positional args for ``create_subprocess_exec``) the rule flags two
shapes, both requiring the interpreter (``sys.executable`` or a
``python`` / ``python3`` argv[0]) as the program:

1. **Primary** — ``[sys.executable, "-m", "<own-package>", ...]``: an
   in-process import expressed as a process spawn.
2. **Secondary (best-effort)** — ``["python", "path/to/intree.py", ...]``:
   argv[0] is the interpreter and the next argument is a ``.py`` path.

Own-package resolution (the one real design decision)
-----------------------------------------------------
A single-file CST rule cannot read ``pyproject.toml``, so it cannot know
the project's top-level package name from the AST alone. fixit 2.x has no
per-rule option plumbing that survives ``add_lint_rule_tests_to_module``
(rules are instantiated with no arguments), so a config-driven
``own_package`` string cannot be the *only* mechanism. The rule therefore
uses a **denylist heuristic by default**: for ``-m <name>`` it flags any
``<name>`` whose top-level component is NOT a known stdlib/external module
(``build``, ``pip``, ``pytest``, ``venv``, ``mypy``, ``ruff``, ...). An
optional ``own_package`` class attribute narrows this to precise mode:
when set (by subclassing), only ``-m <own_package>`` is flagged.

Scope / limitations (honest)
----------------------------
- The denylist default flags ``-m <unknown-module>`` even for a
  third-party module not on the list. That is deliberately biased toward
  surfacing seams; a project that hits false positives sets
  ``own_package`` for precision. This is the "best-effort" fallback the
  pebble authorises.
- The secondary script form flags any ``python <file>.py``, including
  ``python setup.py ...``. In-tree-ness and importability are not
  verifiable from a single file's AST; the ``.py``-path heuristic is the
  approximation. Same escape hatch applies.
- ``shell=True`` string commands and ``create_subprocess_shell`` strings
  are not parsed (the argv is an opaque string); those are out of scope.
"""

from __future__ import annotations

import libcst as cst
from fixit import Invalid, LintRule, Valid

# Attribute-qualified spawners: matched as ``subprocess.<fn>`` /
# ``asyncio.<fn>`` regardless of the base name (any alias for the module).
_SUBPROCESS_ATTRS: frozenset[str] = frozenset(
    {
        "run",
        "Popen",
        "check_output",
        "check_call",
        "call",
        "create_subprocess_exec",
        "create_subprocess_shell",
    }
)

# Distinctive bare names safe to match via ``from subprocess import ...``.
# ``run`` / ``call`` are excluded on purpose — too ambiguous bare.
_SUBPROCESS_BARE: frozenset[str] = frozenset(
    {
        "Popen",
        "check_output",
        "check_call",
        "create_subprocess_exec",
        "create_subprocess_shell",
    }
)

# ``create_subprocess_exec(prog, *args)`` passes argv as positional args
# rather than a single list literal.
_EXEC_POSITIONAL: frozenset[str] = frozenset({"create_subprocess_exec"})

# Top-level module names that are stdlib or external dependencies — a
# ``-m`` against these is NOT running the project's own code.
_MODULE_DENYLIST: frozenset[str] = frozenset(
    {
        "build",
        "pip",
        "pytest",
        "venv",
        "unittest",
        "mypy",
        "ruff",
        "black",
        "isort",
        "flake8",
        "pylint",
        "twine",
        "wheel",
        "setuptools",
        "coverage",
        "tox",
        "pdb",
        "cProfile",
        "profile",
        "timeit",
        "trace",
        "ensurepip",
        "compileall",
        "zipapp",
        "zipfile",
        "tarfile",
        "gzip",
        "json",  # json.tool
        "http",  # http.server
        "smtpd",
        "site",
        "sysconfig",
        "platform",
        "this",
        "antigravity",
        "IPython",
        "uvicorn",
        "gunicorn",
        "flask",
        "celery",
        "gettext",
        "webbrowser",
    }
)


class ShellToSelf(LintRule):
    """ASP409: invoking your own package via subprocess — import the
    function and call it (typed in, typed out).

    Detection-only (no autofix); the fix requires knowing which function
    to import, which is human/agent judgment.
    """

    #: Optional precise-mode knob. When a subclass sets this to the
    #: project's top-level package name, only ``-m <own_package>`` is
    #: flagged; when empty (the default) the denylist heuristic applies.
    own_package: str = ""

    MESSAGE = (
        "ASP409: invoking your own package via subprocess (argv→exit "
        "code) — import the function and call it (typed in, typed out); "
        "a subprocess boundary to your own code is a stringly-typed seam "
        "that drifts and can be pointed elsewhere."
    )

    VALID = [
        # External tools — no importable equivalent in this codebase.
        Valid('subprocess.run(["git", "status"])\n'),
        Valid('subprocess.run(["uv", "run", "pytest"])\n'),
        Valid('subprocess.check_call(["docker", "build", "."])\n'),
        # pytest driven as a CLI is an external test runner.
        Valid('subprocess.run(["pytest", "-q", "tests/"])\n'),
        # ``-m`` against stdlib/dependency modules: not the project.
        Valid('subprocess.run([sys.executable, "-m", "build"])\n'),
        Valid('subprocess.run([sys.executable, "-m", "pip", "install", "."])\n'),
        Valid('subprocess.run([sys.executable, "-m", "pytest"])\n'),
        Valid('subprocess.run([sys.executable, "-m", "http.server"])\n'),
        # Artifact under test — the built binary MUST run out of process.
        Valid('subprocess.run([emitter_bin, "--emit", spec])\n'),
        Valid('subprocess.run(["./dist/emitter", "--emit"])\n'),
        # shell string form is opaque argv — out of scope, not flagged.
        Valid('subprocess.run("git status", shell=True)\n'),
        # Non-subprocess call named ``run`` must not be matched bare.
        Valid('run([sys.executable, "-m", "aspergillus"])\n'),
    ]
    INVALID = [
        # Primary: own package via ``-m``.
        Invalid('subprocess.run([sys.executable, "-m", "aspergillus", "check"])\n'),
        Invalid('subprocess.check_output([sys.executable, "-m", "aspergillus"])\n'),
        # ``-m`` against an unknown (non-denylisted) module — best-effort.
        Invalid('subprocess.run([sys.executable, "-m", "myproj.cli"])\n'),
        # asyncio exec form: argv as positional args.
        Invalid('asyncio.create_subprocess_exec(sys.executable, "-m", "aspergillus")\n'),
        # Secondary: interpreter + in-tree script path.
        Invalid('subprocess.Popen(["python", "tools/emit.py", "--fast"])\n'),
        Invalid('subprocess.run([sys.executable, "scripts/run.py"])\n'),
    ]

    def visit_Call(self, node: cst.Call) -> None:
        if not _is_subprocess_spawn(node):
            return
        argv = _resolve_argv(node)
        if len(argv) < 1:
            return
        if not _is_interpreter(argv[0]):
            return

        module = _dash_m_module(argv)
        if module:
            top = module.split(".", 1)[0]
            if self.own_package:
                if top == self.own_package:
                    self.report(node, self.MESSAGE)
            elif top not in _MODULE_DENYLIST:
                self.report(node, self.MESSAGE)
            return

        if _has_script_path(argv[1:]):
            self.report(node, self.MESSAGE)


def _is_subprocess_spawn(node: cst.Call) -> bool:
    """True if the call is one of the recognised subprocess spawners."""
    func = node.func
    if isinstance(func, cst.Attribute):
        return func.attr.value in _SUBPROCESS_ATTRS
    if isinstance(func, cst.Name):
        return func.value in _SUBPROCESS_BARE
    return False


def _resolve_argv(node: cst.Call) -> list[cst.BaseExpression]:
    """Return the argv expressions, or an empty list if not resolvable.

    For ``create_subprocess_exec`` argv is the positional args directly;
    for the other spawners it is the elements of the first positional
    argument when that argument is a list literal. A ``shell=True`` string
    (or any non-list first arg) resolves to an empty list — out of scope.
    """
    positional = [a.value for a in node.args if a.keyword is None and not a.star]
    if not positional:
        return []

    func = node.func
    exec_form = isinstance(func, cst.Attribute) and func.attr.value in _EXEC_POSITIONAL
    exec_form = exec_form or (isinstance(func, cst.Name) and func.value in _EXEC_POSITIONAL)
    if exec_form:
        return positional

    first = positional[0]
    if isinstance(first, cst.List):
        return [el.value for el in first.elements if isinstance(el, cst.Element)]
    return []


def _is_interpreter(expr: cst.BaseExpression) -> bool:
    """True if ``expr`` is ``sys.executable`` or a ``python``/``python3``
    program string (bare or path-suffixed, e.g. ``/usr/bin/python3``).
    """
    if (
        isinstance(expr, cst.Attribute)
        and isinstance(expr.value, cst.Name)
        and expr.value.value == "sys"
        and expr.attr.value == "executable"
    ):
        return True
    text = _string_value(expr)
    if not text:
        return False
    basename = text.rsplit("/", 1)[-1]
    return (
        basename == "python" or basename.startswith("python2") or (basename.startswith("python3"))
    )


def _dash_m_module(argv: list[cst.BaseExpression]) -> str:
    """Return the module named by a ``-m <module>`` pair in argv, else ""."""
    for index, element in enumerate(argv):
        if _string_value(element) == "-m" and index + 1 < len(argv):
            return _string_value(argv[index + 1])
    return ""


def _has_script_path(argv: list[cst.BaseExpression]) -> bool:
    """True if any argv element is a ``.py`` path string."""
    return any(_string_value(el).endswith(".py") for el in argv)


def _string_value(expr: cst.BaseExpression) -> str:
    """Return the Python string a literal evaluates to, or "" otherwise.

    Returns the "" sentinel rather than ``str | None`` to keep the seam
    single-typed (ASP302); "" is not a valid argv token here, so it is an
    unambiguous "not a resolvable string" marker.
    """
    if isinstance(expr, cst.SimpleString):
        value = expr.evaluated_value
        if isinstance(value, str):
            return value
    return ""
