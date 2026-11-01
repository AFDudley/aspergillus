"""ASP416: parse, don't validate — a parse boundary must return a type
stronger than its input.

FSM-verification-integrity family; sibling to ASP408 anti-special-casing,
ASP409 shell-to-self, ASP410 in-process-e2e, ASP411 fsm-redundant-branches,
ASP412 fsm-edge-duration, ASP413 fsm-enum-dispatch-exhaustive, and ASP414
fsm-stringly-dispatch. ASP413 and ASP414 guard the exhaustiveness and the
honesty of a dispatch over an already-parsed value. ASP416 guards the seam
one step earlier: the parse boundary that produces the value in the first
place.

Alexis King's "Parse, don't validate" (2019) [1] names the discipline this
rule enforces (process.md step 3.2 in this pack's own doctrine): a function
that can reject its input must return a type that proves, on success, that
the input satisfied a stronger invariant. A function whose return
annotation is a union with an arm identical to one of its parameter
annotations does the opposite. It can still reject — the union's other arm
carries the rejection — but a successful call hands back the exact type it
received. The proof that the check ran is discarded at the one place it
could have been recorded, so every caller must re-check, or worse, assumes
the check already happened.

Trigger (the signature plus one syntactic look at the `return` values):

- the function's return annotation is a union (`A | B`, `Optional[...]`,
  or `Union[...]`), AND
- at least one arm of that union is type-equal, by normalized source, to
  the annotation of a parameter that some `return` hands back: the
  parameter itself, or a slice, attribute, or method-call chain rooted at
  it (`return x`, `return x if x else None`, `return text[a:b].strip()`).

The signature alone is not enough in Python. `str` and `Path` carry
almost every value, so `def find(key: str) -> str | None` shares a type
with its input while it returns an unrelated value it looked up. Measured
over exophial's src + tests on 2026-11-01: the signature-only trigger
reported 56 functions, 49 of them on a `str` arm. Only 4 of the 56 return
their own parameter or a view of it.

A parser is exempt: its return type appears in no parameter, so no union
arm can match it. A bare, non-union return (`X -> X`, `X -> int`) is
exempt too — without a rejection arm it is a transform, not a validation.
A function whose returns never hand back a parameter is exempt: it
returns a new value, so it is a lookup or a parser, not a validation.

[1] Alexis King, "Parse, don't validate", 2019.
https://lexi-lambda.github.io/blog/2019/11/05/parse-don-t-validate/

**Ships without autofix** (Tier 2, detection-only, per
`docs/decisions/2026-05-19-severity-graduation.md`). The fix — introducing
a stronger type that encodes the successful parse, and updating every call
site to use it — is a judgment call the rule cannot make mechanically.

Escape hatch
------------
A function carrying a `# asp-fsm: boundary-parse` comment anywhere in its
body is exempt, matching ASP414's marker exactly. A genuine parse boundary
may legitimately re-affirm its own input type on success (for example, a
guard that narrows a wire value and returns it unchanged once the seam has
already done the real parsing one call up).
"""

from __future__ import annotations

import ast
import textwrap

import libcst as cst
from fixit import Invalid, LintRule, Valid
from libcst.metadata import PositionProvider

#: Comment marker that silences this rule for the function it appears in,
#: matching ASP414's `BOUNDARY_MARKER` exactly.
BOUNDARY_MARKER = "asp-fsm: boundary-parse"

_MESSAGE = (
    "ASP416: validate, not parse — this function's return type includes an "
    "arm identical to one of its parameter types, so a successful call "
    "hands back the same type it received instead of a stronger type that "
    "proves the check succeeded (Alexis King, 'Parse, don't validate', "
    "2019). Introduce a type that encodes the successful parse and return "
    "that (or add '# asp-fsm: boundary-parse' if this is a genuine parse "
    "boundary)."
)


def _normalize_expr(node: cst.BaseExpression) -> str:
    """Pure: canonical string for an annotation expression, blind to source
    formatting (whitespace, parenthesization)."""
    code = cst.Module(body=[]).code_for_node(node)
    tree = ast.parse(textwrap.dedent(code), mode="eval")
    return ast.dump(tree.body, include_attributes=False)


def _union_arms(node: cst.BaseExpression) -> list[cst.BaseExpression] | None:
    """Pure: the arms of a union type annotation, or None if `node` isn't
    one. Handles `A | B` (recursively flattened), `Optional[X]` (returned
    as `[X, None]`), and `Union[A, B, ...]`."""
    if isinstance(node, cst.BinaryOperation) and isinstance(node.operator, cst.BitOr):
        return [
            *(_union_arms(node.left) or [node.left]),
            *(_union_arms(node.right) or [node.right]),
        ]
    if isinstance(node, cst.Subscript):
        base = node.value
        if isinstance(base, cst.Name):
            base_name = base.value
        elif isinstance(base, cst.Attribute):
            base_name = base.attr.value
        else:
            return None
        elements = [el.slice.value for el in node.slice if isinstance(el.slice, cst.Index)]
        if base_name == "Optional" and len(elements) == 1:
            return [elements[0], cst.Name("None")]
        if base_name == "Union" and elements:
            return elements
    return None


def _annotated_params(node: cst.FunctionDef) -> list[cst.Param]:
    """Pure: every annotated parameter, across positional-only,
    positional-or-keyword, keyword-only, `*args`, and `**kwargs` params."""
    params = node.params
    all_params = [*params.posonly_params, *params.params, *params.kwonly_params]
    for star in (params.star_arg, params.star_kwarg):
        if isinstance(star, cst.Param):
            all_params.append(star)
    return [p for p in all_params if p.annotation is not None]


def _root_name(expr: cst.BaseExpression) -> str | None:
    """Pure: the name an expression hands back unchanged in kind -- the
    root of an attribute, subscript, or method-call chain (`x`,
    `x[1:]`, `x.strip()`), or None for any other expression."""
    if isinstance(expr, cst.Name):
        return expr.value
    if isinstance(expr, (cst.Attribute, cst.Subscript)):
        return _root_name(expr.value)
    if isinstance(expr, cst.Call) and isinstance(expr.func, cst.Attribute):
        return _root_name(expr.func.value)
    return None


def _returned_alternatives(expr: cst.BaseExpression) -> list[cst.BaseExpression]:
    """Pure: the values a returned expression can evaluate to -- both arms
    of `a if c else b` and both operands of `a or b` / `a and b`."""
    if isinstance(expr, cst.IfExp):
        return [*_returned_alternatives(expr.body), *_returned_alternatives(expr.orelse)]
    if isinstance(expr, cst.BooleanOperation):
        return [*_returned_alternatives(expr.left), *_returned_alternatives(expr.right)]
    return [expr]


def _returned_root_names(node: cst.CSTNode) -> set[str]:
    """Pure: the root name of every value a `return` in `node`'s own scope
    can hand back. Nested functions, classes, and lambdas are skipped:
    their returns belong to their own signatures."""
    names: set[str] = set()
    for child in node.children:
        if isinstance(child, (cst.FunctionDef, cst.ClassDef, cst.Lambda)):
            continue
        if isinstance(child, cst.Return) and child.value is not None:
            for alternative in _returned_alternatives(child.value):
                root = _root_name(alternative)
                if root is not None:
                    names.add(root)
        names.update(_returned_root_names(child))
    return names


def _validates_not_parses(node: cst.FunctionDef) -> bool:
    """Pure: True iff `node`'s return annotation is a union with an arm
    type-equal to the annotation of a parameter that a `return` hands back
    -- the parameter itself, or a slice, attribute, or method-call chain
    rooted at it.

    The signature alone is not enough in Python. `str` and `Path` carry
    almost every value, so `def find(key: str) -> str | None` shares a type
    with its input while it returns an unrelated value. Only a function
    that returns its own input (or a view of it) hands back "the exact type
    it received" after a check."""
    if node.returns is None:
        return False
    arms = _union_arms(node.returns.annotation)
    if not arms:
        return False
    returned = _returned_root_names(node.body)
    returned_norms = {
        _normalize_expr(param.annotation.annotation)
        for param in _annotated_params(node)
        if param.annotation is not None and param.name.value in returned
    }
    return any(_normalize_expr(arm) in returned_norms for arm in arms)


class FsmValidateNotParse(LintRule):
    """ASP416: a function whose return annotation unions in one of its own
    parameter types validates its input instead of parsing it — the
    successful-return type must be stronger than the input, per King
    (2019) "Parse, don't validate".

    Detection-only (no autofix): the fix is introducing a new type that
    encodes the successful parse, which is a judgment call.
    """

    MESSAGE = _MESSAGE
    METADATA_DEPENDENCIES = (PositionProvider,)

    #: The current file's source, split into lines (1-indexed by callers).
    _source_lines: list[str]

    VALID = [
        # Return type appears in no parameter -> a parser, not a validator.
        Valid("class Parsed: ...\n\n\ndef parse(x: str) -> Parsed: ...\n"),
        # Bare, non-union return -> a transform, no rejection arm.
        Valid("def transform(x: int) -> int: ...\n"),
        # The escape hatch: a genuine parse boundary re-affirming its input.
        Valid(
            "def h(x: str) -> str | None:\n"
            "    # asp-fsm: boundary-parse\n"
            "    return x if x else None\n"
        ),
        # Union, but no arm equals a parameter type.
        Valid("class Foo: ...\nclass Bar: ...\n\n\ndef k(x: Foo) -> Bar | None: ...\n"),
        # A `str` arm matches the `str` parameter, but the function returns
        # a value it looked up, never its input: a lookup, not a validation.
        Valid(
            "def find(table: dict[str, str], key: str) -> str | None:\n"
            "    value = table.get(key)\n"
            "    if value is None:\n"
            "        return None\n"
            "    return value\n"
        ),
    ]
    INVALID = [
        # Success arm (`str`) equals the parameter's type (`str`).
        Invalid("def f(x: str) -> str | None:\n    return x if x else None\n"),
        # Success arm equals the parameter type; refusal arm is not None,
        # proving the rule isn't just the Optional/None special case.
        Invalid(
            "class Foo: ...\nclass Refused: ...\n\n\n"
            "def g(x: Foo) -> Foo | Refused:\n    return x\n"
        ),
        # Two-parameter case: the success arm equals the SECOND parameter's
        # type, not the first.
        Invalid(
            "class Bar: ...\n\n\ndef merge(count: int, item: Bar) -> Bar | None:\n    return item\n"
        ),
        # A view of the input (a slice, then a method call) is still the
        # input's own type handed back after a check.
        Invalid(
            "def trimmed(text: str) -> str | None:\n"
            "    if not text.strip():\n"
            "        return None\n"
            "    return text[1:].strip()\n"
        ),
    ]

    def visit_Module(self, node: cst.Module) -> None:
        # Reset per-file state — a rule instance may be reused across files
        # by the fixit engine.
        self._source_lines = node.code.splitlines()

    def visit_FunctionDef(self, node: cst.FunctionDef) -> None:
        if not _validates_not_parses(node):
            return
        pos = self.get_metadata(PositionProvider, node)
        lines = self._source_lines[pos.start.line - 1 : pos.end.line]
        if any(BOUNDARY_MARKER in line for line in lines):
            return
        self.report(node, self.MESSAGE)
